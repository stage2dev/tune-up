export const meta = {
  name: 'tune-up-part',
  description: 'Items in sequence, base items reviewed at once, the whole Part reviewed once at the end, fixes in sequence, final check',
  phases: [
    { title: 'Execute', detail: 'one executor per item, one after another (sonnet, or opus when risky)' },
    { title: 'Review', detail: 'base items right away; the whole Part once at the end (lens x chunk, in parallel); first review on `models` (default failures sonnet, security and database opus); a recheck on sonnet, on that model once the unit had a CRITICAL' },
    { title: 'Fix', detail: 'fresh executors in sequence on CRITICAL/HIGH findings (sonnet; opus when round 2, CRITICAL, a non-failures lens or a Part with a risky item), then recheck only the fix diff' },
    { title: 'Check', detail: 'haiku runs the project checks once' },
  ],
}

// RULES (copy this file, change only the marked spots):
// 1. Every agent call carries agentType + model + effort as string literals. Never inherit the session model.
// 2. Generic agents only with `// tune-up: allow-generic <reason>` on the line above (MCP, browser, images).
// 3. Executors COMMIT on the work branch (never push) and return the hash; reviewers get base + commit and run the diff themselves.
//    Items run in sequence. Only BASE items are reviewed right after; the whole Part is reviewed once at the end (call 2).
//    Fixes: max MAX_FIXES, in sequence, the recheck sees only the fix diff. A fix is a NEW sonnet executor, opus when round > 1,
//    a CRITICAL finding, a finding whose lens is not failures, or a Part with a risky item. Findings keep their lens (lens: u.lens).
//    Review models: models[lens] ('sonnet'|'opus'; missing or other: failures sonnet, security/database opus); a recheck on sonnet,
//    on models[lens] once that unit had a CRITICAL in any round.
//    `order` is the order text or one line "ORDER FILE: <absolute path>"; review.orders may hold one such line per item, one per line.
//    Each executed item result carries commit (the last, after fixes; executor_commit when a fix changed it), executor, summary, tests, steps, skills_read, flags: the coordinator reads no handoff.
// 4. A null, commit-less or usage-limit reply is "interrupted" and not called again, never "approved" and never "done".
//    Same for a commit that is not a hash, is the base or was already returned: an empty range is never reviewed.
// Shared args: base, worktree, models (the `models` answer of `rota --part`, optional).
// Call 1 args (pending line already in progress, see skills/part/review.md): { base: hash, worktree, models, items: [{ id, order, risky, base: bool, reviewers: ['failures'|'security'|'database'] }] }
//   `base` true = reviewed right after (from `guarda.py rota`); `reviewers` is used only for base items.
// Call 2 (after `guarda.py rota --part`): args = { base, worktree, items: [], review: { commit, reviewers, files, chunks: [{ id, paths: [] }],
//   stat, baseReviewed: [{ id, commit }], orders, risky } }. risky: true when rota answered tune-up:executor-opus for any item of the Part. Empty or missing reviewers = all three lenses. `files` = every `git diff --name-only`
//   path; `paths` = files or folders; what no chunk takes goes to a `rest` chunk. fixes > 0 in the answer: run `rota --part` again
//   on base..commit; a lens it newly asks for = call 2 again with only that lens.

// Do not raise this: a third round only repeats noise (measured). Leftovers go to need_you.
const MAX_FIXES = 2

const FINDINGS = {
  type: 'object', required: ['verdict', 'findings'],
  properties: { verdict: { type: 'string', enum: ['approve', 'reject'] },
    findings: { type: 'array', items: { type: 'object', properties: {
      sev: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
      file: { type: 'string' }, line: { type: ['integer', 'null'] }, introduced: { type: 'boolean' }, reopened: { type: 'boolean' },
      proof: { type: 'string' }, title: { type: 'string' } },
      required: ['sev', 'file', 'line', 'introduced', 'proof', 'title'] } } },
}

const DEFAULT_LENSES = ['failures', 'security'], KNOWN_LENSES = ['failures', 'security', 'database']
const HASH = /^[0-9a-f]{7,40}$/

const EXEC = {
  type: 'object', properties: { commit: { type: 'string' }, summary: { type: 'string' }, tests: { type: 'string' },
    steps: { type: 'integer' }, skills_read: { type: 'array', items: { type: 'string' } }, flags: { type: 'string' } },
  required: ['commit', 'summary', 'tests'],
}

// Null (agent died) or the synthetic usage-limit text ("You've hit your ... limit"), as string or in summary.
function interrupted(result) {
  if (result === null || result === undefined) return true
  const t = typeof result === 'string' ? result : String(result.summary || '')
  return t.includes('hit your') && t.includes('limit')
}
const same = (a, b) => a.startsWith(b) || b.startsWith(a), seen = [args.base]   // short and full form of one commit
// The NEW commit of an executor/fix reply, or null: no reply, no hash, the base or a commit already returned (nothing to review).
function newCommit(r) {
  const c = interrupted(r) || typeof r.commit !== 'string' ? '' : r.commit.trim()
  if (!HASH.test(c) || seen.some(s => same(s, c))) return null
  seen.push(c)
  return c
}

// Case-insensitive severity; a missing `introduced` counts as introduced (only an explicit false exempts).
const blocks = f => f.introduced !== false && ['CRITICAL', 'HIGH'].includes(String(f.sev).toUpperCase())
// Recheck: whatever matches a previous finding is that finding reopened and blocks, even with introduced: false.
const norm = s => String(s).trim().toLowerCase()
const isOpen = (f, previous) => blocks(f) || (previous.length > 0 && (f.reopened === true ||
  previous.some(p => norm(p.file) === norm(f.file) && norm(p.title) === norm(f.title))))
// Same allow-list as RE_APPROVED in scripts/tuneup/revisao.py: anything else is "rejected".
const APPROVED = /^[\s*_`>"']*(?:approved?(?:\s+with\s+(?:fixes|notes|comments|nits|suggestions))?|aprovad[oa](?:\s+com\s+(?:correcoes|ressalvas|notas|ajustes))?)(?![\p{L}\p{N}])(?:\d|(?:critical|high|medium|low|pre-?existing|pre-?existentes?|and|e)(?![\p{L}\p{N}_])|[\s*_`"',;:.()–—-])*$/u
const rejects = v => !APPROVED.test(String(v).normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase())

const ORDER_FILE = 'If the order above is an "ORDER FILE: <path>" line, Read that file first: it is the work order.'
const COMMIT_RULE = 'When done, COMMIT the item on the current work branch (never push) and return the commit hash in `commit`.'
const key = u => (u.boundary ? `${u.lens}:boundary` : `${u.lens}:${u.id}`)
const where = `Base: ${args.base}\nWorktree: ${args.worktree}\n`
const bad = r => interrupted(r) || !Array.isArray(r.findings)

// One review unit (a lens over a chunk, or the boundary unit). Recheck (previous set): ONLY the fix diff.
function unit(u, range, previous, info, again = '', hot = false) {
  const prompt = `${where}Unit: ${key(u)}\n` +
    `Run \`git diff --no-ext-diff --ignore-submodules=none ${range}\` and \`git status --porcelain\` in the worktree (a file outside the commit is a finding; an empty diff = reject with a CRITICAL). Read around the diff only to prove a finding.\n` +
    'DUPLICATION: HIGH only when the copies already diverge or must change together; otherwise MEDIUM.\n' +
    (previous.length
      ? `This is a recheck of a fix: the range above is ONLY the fix diff. Look for regressions of the fix.\nPREVIOUS FINDINGS (mark each closed or reopened; list again only the reopened, same file and title, reopened: true and introduced: true, and anything new):\n${JSON.stringify(previous)}\n`
      : info + (u.paths ? `Only these paths: ${JSON.stringify(u.paths)}\n` : '') +
        (u.boundary ? `BOUNDARY unit: look ONLY at the seams between these chunks (front x back, caller x callee): ${JSON.stringify(u.chunks)}\n` : '')) + again
  const o = { label: `review:${u.lens}:${u.id}`, phase: 'Review', schema: FINDINGS }
  const asked = (args.models || {})[u.lens], first = ['sonnet', 'opus'].includes(asked) ? asked : u.lens === 'failures' ? 'sonnet' : 'opus'
  const m = previous.length && !hot ? 'sonnet' : first   // recheck: sonnet until that unit had a CRITICAL
  if (u.lens === 'security' && m === 'sonnet') return agent(prompt, { ...o, model: 'sonnet', effort: 'high', agentType: 'tune-up:reviewer-security' })
  if (u.lens === 'security') return agent(prompt, { ...o, model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-security' })
  if (u.lens === 'database' && m === 'sonnet') return agent(prompt, { ...o, model: 'sonnet', effort: 'high', agentType: 'tune-up:reviewer-database' })
  if (u.lens === 'database') return agent(prompt, { ...o, model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-database' })
  if (m === 'opus') return agent(prompt, { ...o, model: 'opus', effort: 'high', agentType: 'tune-up:reviewer-failures' })
  return agent(prompt, { ...o, model: 'sonnet', effort: 'high', agentType: 'tune-up:reviewer-failures' })
}

function execute(item) {
  const prompt = `${where}Item: ${item.id}\n${item.order}\n${ORDER_FILE}\n${COMMIT_RULE}`
  if (item.risky) return agent(prompt, { label: `exec:opus:${item.id}`, phase: 'Execute', model: 'opus', effort: 'medium', agentType: 'tune-up:executor-opus', schema: EXEC })
  return agent(prompt, { label: `exec:sonnet:${item.id}`, phase: 'Execute', model: 'sonnet', effort: 'medium', agentType: 'tune-up:executor-sonnet', schema: EXEC })
}

// Every fix is a NEW executor on top of the previous commit: sonnet, opus when the risk rule says so (anything unknown goes up).
function fix(name, orders, group, round, from, commit, n, risky) {
  const prompt = `${where}Unit: ${name}\nORIGINAL ORDER(S):\n${orders || '(not available, work from the diff)'}\n${ORDER_FILE}\n\n` +
    `Fix ONLY these CRITICAL/HIGH findings (round ${round}):\n${JSON.stringify(group)}\n` +
    `Current work: run \`git diff ${from}..${commit}\`. Make a NEW commit on top of ${commit}. ${COMMIT_RULE}`
  const up = round > 1 || risky || group.some(f => String(f.sev).toUpperCase() === 'CRITICAL' || f.lens !== 'failures')
  if (up) return agent(prompt, { label: `fix${round}.${n}:opus:${name}`, phase: 'Fix', model: 'opus', effort: 'medium', agentType: 'tune-up:executor-opus', schema: EXEC })
  return agent(prompt, { label: `fix${round}.${n}:sonnet:${name}`, phase: 'Fix', model: 'sonnet', effort: 'medium', agentType: 'tune-up:executor-sonnet', schema: EXEC })
}

// Findings of one file stay together; at most 5 per executor call unless one file alone has more.
function groups(open) {
  const byFile = {}
  open.forEach(f => { (byFile[f.file] = byFile[f.file] || []).push(f) })
  let out = [], cur = []
  for (const fs of Object.values(byFile)) {
    if (cur.length && cur.length + fs.length > 5) { out.push(cur); cur = [] }
    cur = cur.concat(fs)
  }
  if (cur.length) out.push(cur)
  return out
}

function lensesFor(asked, id, missing) {
  asked = Array.isArray(asked) ? asked : []
  asked.filter(l => !KNOWN_LENSES.includes(l)).forEach(l => log(`unknown lens "${l}" for ${id}: ignored`))
  const known = KNOWN_LENSES.filter(l => asked.includes(l))   // each lens once
  return known.length ? known : missing
}

// Every file of the Part in exactly one chunk, what is left in `rest`. null = the split cannot be trusted.
function chunksOf(rv) {
  const c = rv.chunks, files = rv.files
  if (c === undefined || c === null || c === 1 || (Array.isArray(c) && !c.length)) return [{ id: 'all' }]
  if (!Array.isArray(c) || !Array.isArray(files) || c.some(x => !x || typeof x.id !== 'string' || !x.id.trim() || !Array.isArray(x.paths))) return null
  const out = c.map(x => ({ id: x.id, paths: [] })), rest = []
  for (const f of files) {
    const hits = out.filter((_, i) => c[i].paths.some(p => f === p || f.startsWith(p.replace(/\/+$/, '') + '/')))
    if (hits.length > 1) return null
    const to = hits.length ? hits[0].paths : rest
    to.push(f)
  }
  if (rest.length) out.push({ id: 'rest', paths: rest })
  const ids = new Set(out.map(x => x.id).concat('boundary'))   // `boundary` is the seam unit
  return ids.size === out.length + 1 && out.every(x => x.paths.length) ? out : null
}

// Shared by base items and the end review. Returns { status: approved|need_you|interrupted, fixes, open, commit, later }.
async function reviewLoop(name, units, from, commit, orders, info, risky) {
  const st = {}, later = {}, previous = {}, hot = {}   // st: unit key -> { open, rejected } from its latest answer; hot: had a CRITICAL
  let fixes = 0, last = Infinity, range = `${from}..${commit}`, run = units
  const known = () => units.flatMap(u => (st[key(u)] ? st[key(u)].open : []))
  const res = (status, open) => ({ status, fixes, open, commit, later: Object.values(later) })
  for (;;) {
    phase('Review')
    const got = await parallel(run.map(u => async () => {
      const prev = previous[key(u)] || [], r = await unit(u, range, prev, info, '', hot[key(u)])
      const why = interrupted(r) ? '' /* never called again */ : bad(r) ? 'had no findings list' : rejects(r.verdict) && !r.findings.some(f => isOpen(f, prev)) ? 'rejected without a CRITICAL/HIGH introduced: justify it with a finding or approve' : ''
      return why ? unit(u, range, prev, info, `Your previous answer ${why}.\n`, hot[key(u)]) : r   // asked again ONCE
    }))
    const missing = got.filter(bad).length
    run.forEach((u, i) => {
      const r = got[i], prev = previous[key(u)] || []
      if (bad(r)) return
      st[key(u)] = { open: r.findings.filter(f => isOpen(f, prev)).map(f => ({ ...f, lens: u.lens })), rejected: rejects(r.verdict) }
      if (st[key(u)].open.some(f => String(f.sev).toUpperCase() === 'CRITICAL')) hot[key(u)] = true
      r.findings.filter(f => !isOpen(f, prev)).forEach(f => { later[`${f.file}:${f.line}:${f.title}`] = f })
    })
    if (missing) { log(`INTERRUPTED ${name}: ${missing} reviewer(s) did not answer (not treated as approved)`); return res('interrupted', known()) }
    const open = known()
    const silent = units.filter(u => st[key(u)].rejected && !st[key(u)].open.length)
    if (silent.length) {
      log(`NEED_YOU ${name}: reviewer rejected without a CRITICAL/HIGH finding (${silent.map(key).join(', ')})`)
      return res('need_you', open.concat(silent.map(u => ({ unit: key(u), title: 'reviewer rejected without a CRITICAL/HIGH finding' }))))
    }
    if (!open.length) return res('approved', [])
    if (fixes >= MAX_FIXES || open.length >= last) { log(`NEED_YOU ${name}: ${open.length} open after ${fixes} fixes (before: ${last})`); return res('need_you', open) }
    last = open.length
    fixes++
    log(`fix round ${fixes} for ${name}: ${open.length} CRITICAL/HIGH`)
    phase('Fix')
    const before = commit, todo = groups(open)
    for (const g of todo) {   // sequence: each fix commits on top of the last
      const c = newCommit(await fix(name, orders, g, fixes, from, commit, todo.indexOf(g) + 1, risky))
      if (!c) { log(`INTERRUPTED ${name}: fix did not finish or returned no new commit`); return res('interrupted', open) }
      commit = c
    }
    run = units.filter(u => st[key(u)].open.length)
    run.forEach(u => { previous[key(u)] = st[key(u)].open })
    range = `${before}..${commit}`
  }
}

const results = [], baseOk = HASH.test(String(args.base))
if (!baseOk) log('INTERRUPTED: args.base is not a commit hash')
let tip = args.base, stopped = false
for (const item of args.items) {
  if (stopped) { results.push({ id: item.id, status: 'not_run', fixes: 0, open: [], later: [] }); continue }
  phase('Execute')
  const x = baseOk ? await execute(item) : null, c = baseOk ? newCommit(x) : null
  const said = x && typeof x === 'object' ? { summary: x.summary, tests: x.tests, steps: x.steps, skills_read: x.skills_read, flags: x.flags } : {}
  if (!c) { log(`INTERRUPTED ${item.id}: executor did not finish or returned no new commit`); results.push({ id: item.id, status: 'interrupted', fixes: 0, open: [], later: [], ...said }); stopped = true; continue }
  const from = tip, got = { commit: c, executor: item.risky ? 'opus' : 'sonnet', ...said }
  tip = c
  if (!item.base) { results.push({ id: item.id, status: 'built', fixes: 0, open: [], later: [], ...got }); continue }
  const units = lensesFor(item.reviewers, item.id, DEFAULT_LENSES).map(lens => ({ lens, id: item.id }))
  const r = await reviewLoop(item.id, units, from, tip, item.order, `Order:\n${item.order}\n${ORDER_FILE}\n`, !!item.risky)
  tip = r.commit
  if (r.status !== 'approved') stopped = true
  const last = r.commit !== c ? { commit: r.commit, executor_commit: c } : {}   // the item's commit is the one after its fixes
  results.push({ id: item.id, status: r.status === 'approved' ? 'built' : r.status, fixes: r.fixes, open: r.open, later: r.later, ...got, ...last })
}

let review = 'pending', check = null
const rv = args.review
if (rv && !stopped) {
  const chunks = chunksOf(rv) || []
  const units = lensesFor(rv.reviewers, 'part', KNOWN_LENSES).flatMap(lens => chunks.map(c => ({ lens, id: c.id, paths: c.paths })))
  if (chunks.length > 1) units.push({ lens: 'failures', id: 'boundary', boundary: true, chunks })
  const commit = String(rv.commit || tip).trim()
  const badArgs = !chunks.length ? 'chunks (a number without the array, no `files`, a path in two chunks, an empty chunk or a repeated id)'
    : !baseOk || !HASH.test(commit) || same(commit, args.base) || (args.items.length && !same(commit, tip)) ? 'commit (not a hash, the base, or not the last item)' : ''
  if (badArgs) log(`INTERRUPTED part: bad ${badArgs}`)
  seen.push(commit)
  const info = `Whole Part diff stat:\n${rv.stat || '(none)'}\nBase items already reviewed (id, commit): ${JSON.stringify(rv.baseReviewed || [])}\n`
  const r = badArgs ? { status: 'interrupted', fixes: 0, open: [], later: [], commit }
    : await reviewLoop('part', units, args.base, commit, rv.orders, info, !!rv.risky)
  review = { status: r.status, fixes: r.fixes, open: r.open, later: r.later, commit: r.commit }
  if (r.status === 'approved') {
    phase('Check')
    const CHECK = { type: 'object', required: ['passed'],
      properties: { passed: { type: 'boolean' }, failed: { type: 'array', items: { type: 'string' } }, summary: { type: 'string' } } }
    // Coordinator: replace with the project's "Definition of done" commands if they differ.
    check = await agent(`${where}Commit: ${r.commit}\nRun the project's Definition of done commands once. passed=true only if every command passed; list the failed ones in failed.`,
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
