---
name: part
description: Runs ONE Part of an already planned phase item by item, reviewed once at the end by Opus reviewers, with a gate, then STOPS. Use for "Phase NNN Part X", "run the part", "execute part", "rode a parte", "toca a parte", with or without /goal.
argument-hint: "<NNN> <Part>  e.g. 184 B"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py rota:*), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py review-save:*), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py review-pending:*), Bash(graphify update .), Bash(command -v graphify)
---

# Run a Part

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Request: $ARGUMENTS

The JSON above is the context. Write to the user in its `language`, honoring `reply_style`; final answer short. Use document names from `names` (`goal`, `progress`, `research`, `later`, `backlog`, `need_you`, `part_closed`), never literal. Models/effort per role from `models`; if missing, use the table defaults.

You (main session, Opus, high effort, by default; Fable only when the owner opened the session in Fable; never switch to it yourself) coordinate and judge; you do not write the items' code. One Part per conversation: at the end, STOP.

## Roles

| Role | Agent | Default model | Effort |
|---|---|---|---|
| Map / recheck lines | `tune-up:mapper` | haiku | medium |
| Pick skills for an item | `tune-up:skill-finder` | haiku | medium |
| Item routed to sonnet by `rota` (simple: screen, text, test, doc) | `tune-up:executor-sonnet` | sonnet | medium |
| Item routed to opus by `rota` (risky: migration, access rules, RPC, worker, money, auth, sending, concurrency; any doubt) | `tune-up:executor-opus` | opus | medium |
| Review the Part diff (the reviewers `rota --part` lists) | `tune-up:reviewer-failures`, `tune-up:reviewer-database`, `tune-up:reviewer-security` | opus | high |
| Definition of done | `tune-up:checker` | haiku | medium |
| Edit goal/progress/docs | `tune-up:writer` | sonnet | medium |

- Independent agents go in ONE message, in background. Do not wait awake.
- Pass `model` and `effort` on every call. Never a model in `forbidden_subagent_models` (default `["fable"]`).
- Production writes, customer messages, ads: only with the owner's explicit request IN THE TURN. A "yes" to another question does not count.
- Planning documents (goal, progress, later, research, handoff) live in the LOCAL `<plans_dir>`, the main checkout, as absolute paths. Read and write them only there, never only in the worktree: the worktree copy is invisible to the other sessions and to `/tune-up:status`. Each session writes only its own Part's lines. Before the PR (Step 6), copy the phase files (never the `review-<X>/` folders) from the local folder into the worktree at the same relative path and commit them on the Part branch, so the PR carries them. The local copy stays the source.
- Commit of an item on the Part branch: yes. Push and PR only if this Part's request (message or `/goal` condition) says push/PR; otherwise leave all ready and write `names.need_you` may I push and open the PR? Branch cut from the day's `origin/<main>`. Merged PR = dead branch: a post-merge fix is a NEW PR from main; never stacked PRs.
- Never `git stash -u`. `git add` by file name only. Preserve existing changes and untracked files.
- Every `guarda.py` call (`info`, `rota`, `review-save`, `review-pending`) is ONE plain command, written as shown with the absolute plugin root in place of `${CLAUDE_PLUGIN_ROOT}`/`<plugin>` when it is not set: never `cd`, `;`, `&&`, `|`, `$VAR` or redirection around it. Any other form makes the guard ask the owner, even in bypass mode.
- Read the project profile (`profile_path`): definition of done, production, pitfalls.

## Workflow scripts

- If you orchestrate with the Workflow tool, start from `${CLAUDE_PLUGIN_ROOT}/templates/workflow-template.js`.
- Every `agent()` carries a literal `agentType` from the table above, plus `model` and `effort`. Never let an agent inherit the session model.
- A generic agent (no `agentType`, or `general-purpose`) starts with about three times the context of a `tune-up:*` agent. Use one only for work that needs MCP tools, a browser or images, and mark the line above with `// tune-up: allow-generic <reason>`. The guard warns (or blocks, with `"workflow_generic": "block"` in the profile config) otherwise.
- Pending line in progress BEFORE call 1 (Step 4). Items run in sequence; base items are reviewed at once (`reviewers` from `rota`, empty means `['failures','security']`). Then a second call with `review` filled from `rota --part` (args in the template header; empty `reviewers` means all three lenses). At most 2 fixes, rechecking only the fix diff; CRITICAL/HIGH left -> `names.need_you`, never a third fix.
- A `null` result or a "hit your ... limit" reply is an interrupted item: do not relaunch it and do not count it as done; check git before resuming.

## Step 1 - Understand and check prerequisites

1. Read ONLY the Part's sections, the criteria C and the Execution section of the goal document, plus progress. Research is spot consultation.
2. Check `origin/<main>`, `gh pr list` and `git status`: another session may have done something unrecorded. A sibling Part closed in the local progress counts as done for the "Parts" table, even if it is not merged; its merge/migration is the owner's prerequisite.
3. Run `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py review-pending --file "<absolute path of the LOCAL progress>" --part <X>`. An `error` (even with `lines` empty) or no JSON = pending: STOP and say it. Pending lines for this Part: first run the pending review (Step 4, from the commit in the line; empty diff = nothing to review), before any new item; last session's findings are in `review-<X>/` next to progress and the fixes already spent still count.
4. A prerequisite in the "Parts" table that depends on the owner (decision, merge, deploy, migration): say ONCE `names.need_you` + the exact action and STOP (with `/goal`, ask for `/goal clear`). Never "still waiting" in a loop.

## Step 2 - Base and map

1. `git fetch`; your OWN worktree from `origin/<main>` with the Part branch. Before committing: `git branch --show-current`.
2. One `tune-up:mapper` per item group, ALL groups in one message, rechecks EVERY line cited in the goal against today's base and returns current snippets (`file:line`) and REUSE per item. Line moved: adjust the work order, not the goal; note it in progress. In that same message call `tune-up:skill-finder` (item text, absolute `info.catalog_path`) only when `info.catalog_path` is set, the goal item has no Skills and its owned files match NO `info.side_skills` glob (rule in Step 3). `info.side_skills_missing` non-empty, or no catalog: say so ONCE in progress with the command that fixes it (`/tune-up:setup`, ECC step); never silently go without. Item that uses a library API with no skill in the catalog (example: LangChain): one `tune-up:researcher` brings the excerpt of the official doc (URL + date) for the order's LIBRARY DOC.
3. Item that reads, filters or deletes EXISTING data: while the mappers run, the main session runs 1-3 read-only queries on production (counts per status/shape, NULL counts, lengths, min/max dates). Aggregates and shapes only, never a raw value of a phone, name, e-mail or message. Paste the result under REAL DATA in the order; never copy it to progress or to a test fixture.

## Step 3 - One item at a time

Route: run `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py rota --files <the item's owned files>` and follow `executor`; after a failed Sonnet attempt rerun with `--failed sonnet`. ALWAYS write ONLY the item's action line and the base names of the owned files to `<scratchpad>/item-N.rota.txt` (never REAL DATA, pitfalls, diff or file contents) and pass `--text-file` with it; `source` in the answer says whether the router ran (`jev`) or not (`fixed`/`globs`); record suggested (`model`) vs used in progress. You may go UP from the route on your judgement, never down; note any divergence and its reason in progress. Build the work order from `${CLAUDE_PLUGIN_ROOT}/templates/work-order.md` (it carries the `ROUTE:`) and dispatch in background. "Skills to read" ALWAYS includes every entry of `info.pitfall_skills` whose `paths` globs match the absolute path of an owned file (worktree + path, no `:lines` suffix; `**/` also matches zero folders), with or without a catalog, plus every entry of `info.side_skills` whose `paths` match by the same rule, plus the goal's "Skills"; the skill-finder (Step 2) only adds extras. They conflict: repo convention > pitfall skill > generic side skill. A handoff whose json `skills_read` misses a matched pitfall OR side skill: note it in progress and tell the reviewers. Side skills go to EXECUTORS only: reviewers get the same pitfall paths under PITFALLS TO READ plus the list of side skill paths the executor had, for reference only. 1 item (or items in the same files). `maxTurns` 220; near ~80 steps the executor stops and hands back a partial result. Database item: the executor proves it on a local database, never production. The executor commits its own item on the Part branch with `git add` by name; push and PR go at the end through `/tune-up:ship`, only with the request above.

## Step 4 - Review once, at the end of the Part

Read `${CLAUDE_PLUGIN_ROOT}/skills/part/review.md` before the first review; it has the commands, formats and prompts.

- Items run WITHOUT a reviewer: the executor runs the item's tests and commits; you check its handoff json and `git diff --stat`, then start the next item. BEFORE the first dispatch of the Part write ONE line at the start of progress: `- <names.review_pending> - Part X - since <base> (items none yet)` ("Parte"/"desde" in Portuguese); update its items as they finish.
- BASE ITEM: automatic when `rota` WITH `--diff-file` of the item gives `database`, `security`, or opus with why `risk_globs`; the goal's "base item: yes" only ADDS (database/RPC/migration, or an item another item depends on). Review it right after its commit with the reviewers of that route; NO item starts while it is under review or fix, and its approval never erases the pending line. The route still picks the executor.
- End of the Part: review ONCE over `git diff <base>..HEAD` with the reviewers of `rota --part` (never fewer), opus, high, ALL calls in ONE message, saying which base items were already reviewed and at which commit. `chunks` > 1: split by side or item group, every changed path in exactly one chunk (the rest in a `rest` chunk), plus one reviewer-failures for the boundaries between chunks.
- Pass every reviewer answer through `review-save --answer-file` (Write tool, next free `--round`, no heredoc); keep only counts + path + at most 25 lines. `usage` true = fix the call, do not ask the reviewer again. `lens_ran` false = that lens did NOT run: ask the same reviewer once; still invalid = `names.need_you`, never counted as approved. `rejected` with `blocking` 0: ask once to justify, then `names.need_you`.
- Fix CRITICAL/HIGH introduced: groups of up to ~5 findings, executors in SEQUENCE (never parallel), a NEW `tune-up:executor-opus` each (never SendMessage the old one), reading the findings json and the original order. A MEDIUM of 1-3 obvious lines may ride along, never alone. ALWAYS recheck after a CRITICAL/HIGH: only the lenses with one open, over the fix diff + PREVIOUS FINDINGS, each closed or reopened (a reopened one keeps `introduced:true` and blocks), plus any lens `rota --part` newly asks for. Max 2 fixes; CRITICAL/HIGH left or count not dropping -> `names.need_you` and STOP.
- MEDIUM, LOW and pre-existing never block: 1 line each in `names.later` (missing: create it from `${CLAUDE_PLUGIN_ROOT}/templates/phase/later.md` on the first line); the report lists at most 3 MEDIUM and counts the rest.
- DUPLICATION: HIGH only when the copies already diverge or must change together; the rest MEDIUM.
- END review approved: only then replace the pending line by `review done at <commit>` (without the marker).
- Checker AFTER the last fix, once the end review is approved: ONE `tune-up:checker` per side (as the profile splits them; else one call), in the worktree, comparing with main (a pre-existing failure is not yours, but name it). A fix after it: pending line back, recheck that diff, run the checker again.
- Record in progress per item: executor, step count and pitfall and side skills read (from the handoff json, real numbers), and per review the CRITICAL/HIGH per round (e.g. `HIGH 2->0`, lens and 1-line finding).

## Step 5 - Part gate

1. `review-pending` for this Part must be false, and the checker green on the final HEAD compared with main (a pre-existing failure is named, not yours; any code commit since = run it again).
2. Criteria C measured (query/command) and written in progress with the result.
3. Project docs updated if the profile asks.
4. Migration headed for production: hand over the file and steps; apply only via `/tune-up:migration` on the owner's order.
5. Say what did NOT run (CI, test, deploy) and why.

## Step 6 - Close and STOP

1. Progress document (local `<plans_dir>`, then copied into the Part branch): `names.part_closed` (date), what landed, criteria measured, what stays with the owner (merge, deploy, migration), the later document (if any), the next Part's `/goal` command ending in `(new conversation; never continue another Part's session) - follow /tune-up:part. Stop when: "<names.part_closed>" in progress OR you wrote <names.need_you> OR 40 turns.`
2. Backlog: copy the open items of the phase `names.later` (no later document = nothing open to copy) into the `names.backlog` document in `<plans_dir>/` (`names.roadmap` and `names.backlog` live in `plans_dir`; `names.vision`, `names.prd`, `names.architecture`, `names.design`, `names.decisions` in `docs/`; create it if missing; skip duplicates).
3. Knowledge graph: if `graphify-out/` exists AND `command -v graphify` succeeds, run `graphify update .`; otherwise skip silently.
4. Pitfalls learned: for each CRITICAL/HIGH of this Part that can repeat (a pattern, not a one-off slip), draft 1 line for the pitfall skill of the project's modules whose `paths` match the file (name or description says pitfalls/armadilhas), in its format: **rule.** Why: what happened (Part, date). Already covered by a line: propose sharpening that line instead, never a duplicate. Show the drafts in ONE `AskUserQuestion` (multiSelect); record the approved ones via `/tune-up:learn` (it edits the module in `plugin_source`; without it, the rule goes to the project profile). No candidate: write "no new pitfall" in progress.
5. If the project has a Claude memory, record a short note there (+ index line).
6. Short answer: done, what depends on the owner, pitfalls recorded, next Part command. STOP. Never chain the next Part in this conversation.
