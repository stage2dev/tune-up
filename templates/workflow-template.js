export const meta = {
  name: 'tune-up-part',
  description: 'Execute items, review with item lenses, fix at most twice, final check',
  phases: [
    { title: 'Execute', detail: 'one executor per item (sonnet, or opus when risky)' },
    { title: 'Review', detail: 'only the lenses the item asks for, in parallel' },
    { title: 'Fix', detail: 'fresh opus executor on CRITICAL/HIGH findings, then re-review only rejecting lenses' },
    { title: 'Check', detail: 'haiku runs the project checks once' },
  ],
}

// RULES (copy this file, change only the marked spots):
// 1. Every agent call carries agentType + model + effort as string literals. Never inherit the session model.
// 2. Generic agents only with `// tune-up: allow-generic <reason>` on the line above (MCP, browser, images).
// 3. Executors COMMIT on the work branch (never push) and return the hash; reviewers get base + commit and run the diff themselves.
//    Fixes: max MAX_FIXES, re-review only who rejected.
// 4. A null, commit-less or usage-limit reply is "interrupted", never "approved" and never "done".
// args: { base, worktree, items: [{ id, order, risky, reviewers: ['failures'|'security'|'database'] }] }
// Empty or missing reviewers default to DEFAULT_LENSES (when in doubt, security runs).

// Do not raise this: a third round only repeats noise (measured). Leftovers go to need_you.
const MAX_FIXES = 2

const FINDINGS = {
  type: 'object',
  properties: {
    verdict: { type: 'string', enum: ['approve', 'reject'] },
    findings: { type: 'array', items: { type: 'object', properties: {
      sev: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
      file: { type: 'string' }, line: { type: 'integer' }, introduced: { type: 'boolean' },
      proof: { type: 'string' }, title: { type: 'string' } },
      required: ['sev', 'file', 'line', 'introduced', 'proof', 'title'] } },
  },
  required: ['verdict', 'findings'],
}

const DEFAULT_LENSES = ['failures', 'security']
const KNOWN_LENSES = ['failures', 'security', 'database']
const HASH = /^[0-9a-f]{7,40}$/

const EXEC = {
  type: 'object',
  properties: { commit: { type: 'string' }, summary: { type: 'string' }, tests: { type: 'string' } },
  required: ['commit', 'summary', 'tests'],
}

// Null (agent died) or the synthetic usage-limit text ("You've hit your ... limit"), as string or in summary.
function interrupted(result) {
  if (result === null || result === undefined) return true
  const t = typeof result === 'string' ? result : (result && typeof result.summary === 'string' ? result.summary : '')
  return t.includes('hit your') && t.includes('limit')
}
// Executor/fix reply without a usable commit hash: nothing to review.
const noCommit = r => interrupted(r) || typeof r.commit !== 'string' || !HASH.test(r.commit.trim())

// Case-insensitive severity; a missing `introduced` counts as introduced (only an explicit false exempts).
const blocks = f => f.introduced !== false && ['CRITICAL', 'HIGH'].includes(String(f.sev).toUpperCase())
// Verdict text that means "rejected": starts with reject, or mentions changes / rework.
const rejects = v => /^\s*reject|changes|rework/i.test(String(v))

function ctx(item) {
  return `Base: ${args.base}\nWorktree: ${args.worktree}\nItem: ${item.id}\n`
}
const COMMIT_RULE = 'When done, COMMIT the item on the current work branch (never push) and return the commit hash in `commit`.'

// Reviewer runs the diff itself. One literal call per lens.
function review(lens, item, commit, previous) {
  const prompt = `${ctx(item)}Commit under review: ${commit}\n` +
    `Run \`git diff ${args.base}..${commit}\` and \`git status --porcelain\` in the worktree (a file outside the commit is a finding). ` +
    `Read around the diff only to prove a finding. Order:\n${item.order}\n` +
    (previous.length ? `PREVIOUS FINDINGS (check whether each is fixed, report only what is still wrong or new):\n${JSON.stringify(previous)}\n` : '')
  if (lens === 'security') return agent(prompt, { label: `review:security:${item.id}`, phase: 'Review', model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-security', schema: FINDINGS })
  if (lens === 'database') return agent(prompt, { label: `review:database:${item.id}`, phase: 'Review', model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-database', schema: FINDINGS })
  return agent(prompt, { label: `review:failures:${item.id}`, phase: 'Review', model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-failures', schema: FINDINGS })
}

function execute(item) {
  const prompt = `${ctx(item)}${item.order}\n${COMMIT_RULE}`
  if (item.risky) return agent(prompt, { label: `exec:opus:${item.id}`, phase: 'Execute', model: 'opus', effort: 'medium', agentType: 'tune-up:executor-opus', schema: EXEC })
  return agent(prompt, { label: `exec:sonnet:${item.id}`, phase: 'Execute', model: 'sonnet', effort: 'medium', agentType: 'tune-up:executor-sonnet', schema: EXEC })
}

// Every fix is a NEW opus executor, even for simple items. Commits on top of the previous commit.
function fix(item, open, round, commit) {
  const prompt = `${ctx(item)}ORIGINAL ORDER:\n${item.order}\n\nFix ONLY these CRITICAL/HIGH findings (round ${round}):\n${JSON.stringify(open)}\n` +
    `Current work: run \`git diff ${args.base}..${commit}\`. Make a NEW commit on top of ${commit}. ${COMMIT_RULE}`
  return agent(prompt, { label: `fix${round}:${item.id}`, phase: 'Fix', model: 'opus', effort: 'medium', agentType: 'tune-up:executor-opus', schema: EXEC })
}

function lensesFor(item) {
  const asked = Array.isArray(item.reviewers) ? item.reviewers : []
  const known = asked.filter(l => KNOWN_LENSES.includes(l))
  asked.filter(l => !KNOWN_LENSES.includes(l)).forEach(l => log(`unknown lens "${l}" for ${item.id}: ignored`))
  return known.length ? known : DEFAULT_LENSES
}

async function runItem(item) {
  const lenses = lensesFor(item)
  const byLens = {}            // lens -> { open, rejected } from its latest answer
  const laterBy = {}           // lens -> { key: finding } accumulated over all rounds
  const out = (status, fixes, open) => ({ id: item.id, status, fixes, open, later: Object.values(laterBy).flatMap(m => Object.values(m)) })
  const record = (l, r) => {
    byLens[l] = { open: r.findings.filter(blocks), rejected: rejects(r.verdict) }
    laterBy[l] = laterBy[l] || {}
    r.findings.filter(f => !blocks(f)).forEach(f => { laterBy[l][`${f.file}:${f.line}:${f.title}`] = f })
  }
  const known = () => lenses.flatMap(l => (byLens[l] ? byLens[l].open : []))
  phase('Execute')
  const ex = await execute(item)
  if (noCommit(ex)) { log(`INTERRUPTED ${item.id}: executor did not finish or returned no commit`); return out('interrupted', 0, []) }
  let commit = ex.commit.trim()

  let toReview = lenses, previous = [], fixes = 0
  for (;;) {
    phase('Review')
    const res = await parallel(toReview.map(l => () => review(l, item, commit, previous)))
    const ran = toReview.map((l, i) => [l, res[i]]).filter(([, r]) => !interrupted(r) && Array.isArray(r.findings))
    ran.forEach(([l, r]) => record(l, r))
    if (ran.length < toReview.length) {
      log(`INTERRUPTED ${item.id}: a reviewer did not run (not treated as approved)`)
      return out('interrupted', fixes, known())   // lens that did not answer keeps its previous blockers
    }
    const open = known()
    const silent = lenses.filter(l => byLens[l].rejected && !byLens[l].open.length)
    if (silent.length) {
      log(`NEED_YOU ${item.id}: reviewer rejected without a CRITICAL/HIGH finding (${silent.join(', ')})`)
      return out('need_you', fixes, open.concat(silent.map(l => ({ lens: l, title: 'reviewer rejected without a CRITICAL/HIGH finding' }))))
    }
    if (!open.length) return out('done', fixes, [])
    if (fixes >= MAX_FIXES) { log(`NEED_YOU ${item.id}: ${open.length} open after ${fixes} fixes`); return out('need_you', fixes, open) }
    fixes++
    log(`fix round ${fixes} for ${item.id}: ${open.length} CRITICAL/HIGH`)
    phase('Fix')
    const fx = await fix(item, open, fixes, commit)
    if (noCommit(fx)) { log(`INTERRUPTED ${item.id}: fix did not finish or returned no commit`); return out('interrupted', fixes, open) }
    commit = fx.commit.trim()
    toReview = lenses.filter(l => byLens[l].open.length)
    log(`lenses skipped for ${item.id}: ${lenses.filter(l => !toReview.includes(l)).join(', ') || 'none'}`)
    previous = open
  }
}

const results = await pipeline(args.items, runItem)

phase('Check')
const CHECK = {
  type: 'object',
  properties: { passed: { type: 'boolean' }, failed: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } },
  required: ['passed'],
}
let items = results.map(r => r || { id: '?', status: 'interrupted', fixes: 0, open: [], later: [] })
let check = null
if (items.some(r => r.status === 'done')) {
  // Coordinator: replace with the project's "Definition of done" commands if they differ.
  check = await agent(`Base: ${args.base}\nWorktree: ${args.worktree}\nRun the project's Definition of done commands once. passed=true only if every command passed; list the failed ones in failed. Items: ${items.filter(r => r.status === 'done').map(r => r.id).join(', ')}`,
    { label: 'check', phase: 'Check', model: 'haiku', effort: 'medium', agentType: 'tune-up:checker', schema: CHECK })
  if (interrupted(check) || typeof check.passed !== 'boolean') { log('check interrupted'); check = null }
  if (!check || check.passed === false) {
    log('check did not pass: done items become unverified')
    items = items.map(r => (r.status === 'done' ? { ...r, status: 'unverified' } : r))
  }
}

// Examples (not executed): read-only mapping and docs.
// agent(prompt, { label: 'map', model: 'haiku', effort: 'medium', agentType: 'tune-up:mapper' })
// agent(prompt, { label: 'doc', model: 'sonnet', effort: 'medium', agentType: 'tune-up:writer' })

// status: done | unverified (final check failed or did not run) | need_you | interrupted. check: {passed, failed, summary} or null.
return { items, check }
