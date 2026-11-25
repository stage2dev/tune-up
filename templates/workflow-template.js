export const meta = {
  name: 'tune-up-part',
  description: 'Items in sequence, base items reviewed at once, the whole Part reviewed once at the end, fixes in sequence, final check',
  phases: [
    { title: 'Execute', detail: 'one executor per item, one after another (sonnet, or opus when risky)' },
    { title: 'Review', detail: 'base items right away; the whole Part once at the end (lens x chunk, in parallel)' },
    { title: 'Fix', detail: 'fresh opus executors in sequence on CRITICAL/HIGH findings, then recheck only the fix diff' },
    { title: 'Check', detail: 'haiku runs the project checks once' },
  ],
}

// RULES (copy this file, change only the marked spots):
// 1. Every agent call carries agentType + model + effort as string literals. Never inherit the session model.
// 2. Generic agents only with `// tune-up: allow-generic <reason>` on the line above (MCP, browser, images).
// 3. Executors COMMIT on the work branch (never push) and return the hash; reviewers get base + commit and run the diff themselves.
//    Items run in sequence. Only BASE items are reviewed right after; the whole Part is reviewed once at the end (call 2).
//    Fixes: max MAX_FIXES, in sequence, the recheck sees only the fix diff.
// 4. A null, commit-less or usage-limit reply is "interrupted", never "approved" and never "done".
// Call 1 args: { base, worktree, items: [{ id, order, risky, base: bool, reviewers: ['failures'|'security'|'database'] }] }
//   `base` true = reviewed right after (from `guarda.py rota`); `reviewers` is used only for base items.
// Call 2 (after `guarda.py rota --part`): args = { base, worktree, items: [], review: { commit, reviewers, chunks: [{ id, paths: [] }],
//   stat, baseReviewed: [{ id, commit }], orders } }. Empty or missing reviewers default to DEFAULT_LENSES (when in doubt, security runs).

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


const COMMIT_RULE = 'When done, COMMIT the item on the current work branch (never push) and return the commit hash in `commit`.'
const key = u => (u.boundary ? `${u.lens}:boundary` : `${u.lens}:${u.id}`)
const bad = r => interrupted(r) || !Array.isArray(r.findings)

// One review unit (a lens over a chunk, or the boundary unit). Recheck (previous set): ONLY the fix diff.
function unit(u, range, previous, info) {
  const prompt = `Base: ${args.base}\nWorktree: ${args.worktree}\nUnit: ${key(u)}\n` +
    `Run \`git diff ${range}\` and \`git status --porcelain\` in the worktree (a file outside the commit is a finding). Read around the diff only to prove a finding.\n` +
    'DUPLICATION: HIGH only when the copies already diverge or must change together; otherwise MEDIUM.\n' +
    (previous.length
      ? `This is a recheck of a fix: the range above is ONLY the fix diff. Look for regressions of the fix.\nPREVIOUS FINDINGS (mark each closed or reopened; list again only the reopened and anything new):\n${JSON.stringify(previous)}\n`
      : info + (u.paths ? `Only these paths: ${JSON.stringify(u.paths)}\n` : '') +
        (u.boundary ? `BOUNDARY unit: look ONLY at the seams between these chunks (front x back, caller x callee): ${JSON.stringify(u.chunks)}\n` : ''))
  const o = { label: `review:${u.lens}:${u.id}`, phase: 'Review', schema: FINDINGS }
  if (u.lens === 'security') return agent(prompt, { ...o, model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-security' })
  if (u.lens === 'database') return agent(prompt, { ...o, model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-database' })
  return agent(prompt, { ...o, model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-failures' })
}

function execute(item) {
  const prompt = `Base: ${args.base}\nWorktree: ${args.worktree}\nItem: ${item.id}\n${item.order}\n${COMMIT_RULE}`
  if (item.risky) return agent(prompt, { label: `exec:opus:${item.id}`, phase: 'Execute', model: 'opus', effort: 'medium', agentType: 'tune-up:executor-opus', schema: EXEC })
  return agent(prompt, { label: `exec:sonnet:${item.id}`, phase: 'Execute', model: 'sonnet', effort: 'medium', agentType: 'tune-up:executor-sonnet', schema: EXEC })
}

// Every fix is a NEW opus executor, on top of the previous commit.
function fix(name, orders, group, round, from, commit, n) {
  const prompt = `Base: ${args.base}\nWorktree: ${args.worktree}\nUnit: ${name}\nORIGINAL ORDER(S):\n${orders || '(not available, work from the diff)'}\n\n` +
    `Fix ONLY these CRITICAL/HIGH findings (round ${round}):\n${JSON.stringify(group)}\n` +
    `Current work: run \`git diff ${from}..${commit}\`. Make a NEW commit on top of ${commit}. ${COMMIT_RULE}`
  return agent(prompt, { label: `fix${round}.${n}:${name}`, phase: 'Fix', model: 'opus', effort: 'medium', agentType: 'tune-up:executor-opus', schema: EXEC })
}

// Findings of one file stay together; at most 5 per executor call unless one file alone has more.
function groups(open) {
  const byFile = {}
  open.forEach(f => { (byFile[f.file] = byFile[f.file] || []).push(f) })
  const out = []
  let cur = []
  for (const fs of Object.values(byFile)) {
    if (cur.length && cur.length + fs.length > 5) { out.push(cur); cur = [] }
    cur = cur.concat(fs)
  }
  if (cur.length) out.push(cur)
  return out
}

function lensesFor(asked, id) {
  asked = Array.isArray(asked) ? asked : []
  asked.filter(l => !KNOWN_LENSES.includes(l)).forEach(l => log(`unknown lens "${l}" for ${id}: ignored`))
  const known = asked.filter(l => KNOWN_LENSES.includes(l))
  return known.length ? known : DEFAULT_LENSES
}

// Shared by base items and the end review. Returns { status: approved|need_you|interrupted, fixes, open, commit, later }.
async function reviewLoop(name, units, from, commit, orders, info) {
  const st = {}, later = {}, previous = {}   // st: unit key -> { open, rejected } from its latest answer
  let fixes = 0, range = `${from}..${commit}`, run = units
  const known = () => units.flatMap(u => (st[key(u)] ? st[key(u)].open : []))
  const res = (status, open) => ({ status, fixes, open, commit, later: Object.values(later) })
  for (;;) {
    phase('Review')
    const got = await parallel(run.map(u => async () => {
      const r = await unit(u, range, previous[key(u)] || [], info)
      return bad(r) ? unit(u, range, previous[key(u)] || [], info) : r   // asked again ONCE
    }))
    let missing = 0
    run.forEach((u, i) => {
      const r = got[i]
      if (bad(r)) { missing++; return }
      st[key(u)] = { open: r.findings.filter(blocks), rejected: rejects(r.verdict) }
      r.findings.filter(f => !blocks(f)).forEach(f => { later[`${f.file}:${f.line}:${f.title}`] = f })
    })
    if (missing) { log(`INTERRUPTED ${name}: ${missing} reviewer(s) did not answer (not treated as approved)`); return res('interrupted', known()) }
    const open = known()
    const silent = units.filter(u => st[key(u)].rejected && !st[key(u)].open.length)
    if (silent.length) {
      log(`NEED_YOU ${name}: reviewer rejected without a CRITICAL/HIGH finding (${silent.map(key).join(', ')})`)
      return res('need_you', open.concat(silent.map(u => ({ unit: key(u), title: 'reviewer rejected without a CRITICAL/HIGH finding' }))))
    }
    if (!open.length) return res('approved', [])
    if (fixes >= MAX_FIXES) { log(`NEED_YOU ${name}: ${open.length} open after ${fixes} fixes`); return res('need_you', open) }
    fixes++
    log(`fix round ${fixes} for ${name}: ${open.length} CRITICAL/HIGH`)
    phase('Fix')
    const before = commit
    let n = 0
    for (const g of groups(open)) {   // sequence: each fix commits on top of the last
      const fx = await fix(name, orders, g, fixes, from, commit, ++n)
      if (noCommit(fx)) { log(`INTERRUPTED ${name}: fix did not finish or returned no commit`); return res('interrupted', open) }
      commit = fx.commit.trim()
    }
    run = units.filter(u => st[key(u)].open.length)
    run.forEach(u => { previous[key(u)] = st[key(u)].open })
    range = `${before}..${commit}`
  }
}

const results = []
let tip = args.base, stopped = false
for (const item of args.items) {
  if (stopped) { results.push({ id: item.id, status: 'not_run', fixes: 0, open: [], later: [] }); continue }
  phase('Execute')
  const ex = await execute(item)
  if (noCommit(ex)) { log(`INTERRUPTED ${item.id}: executor did not finish or returned no commit`); results.push({ id: item.id, status: 'interrupted', fixes: 0, open: [], later: [] }); stopped = true; continue }
  const from = tip
  tip = ex.commit.trim()
  if (!item.base) { results.push({ id: item.id, status: 'built', fixes: 0, open: [], later: [] }); continue }
  const units = lensesFor(item.reviewers, item.id).map(lens => ({ lens, id: item.id }))
  const r = await reviewLoop(item.id, units, from, tip, item.order, `Order:\n${item.order}\n`)
  tip = r.commit
  if (r.status !== 'approved') stopped = true
  results.push({ id: item.id, status: r.status === 'approved' ? 'built' : r.status, fixes: r.fixes, open: r.open, later: r.later })
}

let review = 'pending', check = null
const rv = args.review
if (rv && !stopped) {
  const chunks = Array.isArray(rv.chunks) ? rv.chunks : []
  const units = lensesFor(rv.reviewers, 'part').flatMap(lens => (chunks.length ? chunks.map(c => ({ lens, id: c.id, paths: c.paths })) : [{ lens, id: 'all' }]))
  if (chunks.length > 1) units.push({ lens: 'failures', id: 'boundary', boundary: true, chunks })
  const commit = (rv.commit || tip).trim()
  const info = `Whole Part diff stat:\n${rv.stat || '(none)'}\nBase items already reviewed (id, commit): ${JSON.stringify(rv.baseReviewed || [])}\n`
  const r = await reviewLoop('part', units, args.base, commit, rv.orders, info)
  review = { status: r.status, fixes: r.fixes, open: r.open, later: r.later, commit: r.commit }
  if (r.status === 'approved') {
    phase('Check')
    const CHECK = {
      type: 'object',
      properties: { passed: { type: 'boolean' }, failed: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } },
      required: ['passed'],
    }
    // Coordinator: replace with the project's "Definition of done" commands if they differ.
    check = await agent(`Base: ${args.base}\nWorktree: ${args.worktree}\nCommit: ${r.commit}\nRun the project's Definition of done commands once. passed=true only if every command passed; list the failed ones in failed.`,
      { label: 'check', phase: 'Check', model: 'haiku', effort: 'medium', agentType: 'tune-up:checker', schema: CHECK })
    if (interrupted(check) || typeof check.passed !== 'boolean') { log('check interrupted'); check = null }
    review.status = check && check.passed ? 'done' : 'unverified'   // done = review approved AND check passed
  }
}

// Examples (not executed): read-only mapping and docs.
// agent(prompt, { label: 'map', model: 'haiku', effort: 'medium', agentType: 'tune-up:mapper' })
// agent(prompt, { label: 'doc', model: 'sonnet', effort: 'medium', agentType: 'tune-up:writer' })

// items[].status: built | need_you | interrupted | not_run (never 'done': only the end review plus the check can say done).
// review: 'pending' (no `review` arg) or { status: done | unverified | need_you | interrupted, fixes, open, later, commit }. check: {passed, failed, summary} or null.
return { items: results, review, check }
