---
name: part
description: Runs ONE Part of an already planned phase item by item, with Opus reviewers and a gate, then STOPS. Use for "Phase NNN Part X", "run the part", "execute part", "rode a parte", "toca a parte", with or without /goal.
argument-hint: "<NNN> <Part>  e.g. 184 B"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info), Bash(graphify update .), Bash(command -v graphify)
---

# Run a Part

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Request: $ARGUMENTS

The JSON above is the context. Write to the user in its `language`, honoring `reply_style`; final answer short. Use document names from `names` (`goal`, `progress`, `research`, `later`, `backlog`, `need_you`, `part_closed`), never literal. Models/effort per role from `models`; if missing, use the table defaults.

You (main session, highest effort) coordinate and judge; you do not write the items' code. One Part per conversation: at the end, STOP.

## Roles

| Role | Agent | Default model | Effort |
|---|---|---|---|
| Map / recheck lines | `tune-up:mapper` | haiku | medium |
| Pick skills for an item | `tune-up:skill-finder` | haiku | medium |
| Simple item (screen, text, simple route, test, doc) | `tune-up:executor-sonnet` | sonnet | medium |
| Risky item (migration, trigger, access rules, RPC, worker, money, auth, external sending, concurrency) | `tune-up:executor-opus` | opus | medium |
| Review the diff | `tune-up:reviewer-failures`, `tune-up:reviewer-database`, `tune-up:reviewer-security` | opus | high |
| Definition of done | `tune-up:checker` | haiku | medium |
| Edit goal/progress/docs | `tune-up:writer` | sonnet | medium |

- Independent agents go in ONE message, in background. Do not wait awake.
- Pass `model` and `effort` on every call. Never a model in `forbidden_subagent_models` (default `["fable"]`).
- Production writes, customer messages, ads: only with the owner's explicit request IN THE TURN. A "yes" to another question does not count.
- Planning documents (goal, progress, later, research, handoff) live in the LOCAL `<plans_dir>`, the main checkout, as absolute paths. Read and write them only there, never only in the worktree: the worktree copy is invisible to the other sessions and to `/tune-up:status`. Each session writes only its own Part's lines. Before the PR (Step 6), copy the phase files from the local folder into the worktree at the same relative path and commit them on the Part branch, so the PR carries them. The local copy stays the source.
- Commit of an item on the Part branch: yes. Push and PR only if this Part's request (message or `/goal` condition) says push/PR; otherwise leave all ready and write `names.need_you` may I push and open the PR? Branch cut from the day's `origin/<main>`. Merged PR = dead branch: a post-merge fix is a NEW PR from main; never stacked PRs.
- Never `git stash -u`. `git add` by file name only. Preserve existing changes and untracked files.
- Read the project profile (`profile_path`): definition of done, production, pitfalls.

## Workflow scripts

- If you orchestrate with the Workflow tool, start from `${CLAUDE_PLUGIN_ROOT}/templates/workflow-template.js`.
- Every `agent()` carries a literal `agentType` from the table above, plus `model` and `effort`. Never let an agent inherit the session model.
- A generic agent (no `agentType`, or `general-purpose`) starts with about three times the context of a `tune-up:*` agent. Use one only for work that needs MCP tools, a browser or images, and mark the line above with `// tune-up: allow-generic <reason>`. The guard warns (or blocks, with `"workflow_generic": "block"` in the profile config) otherwise.
- Review loop in a script: at most 2 fix rounds per item; after each fix only the reviewers that rejected run again; CRITICAL/HIGH left after the review that follows the second fix -> `names.need_you`, never a third fix.
- A `null` result or a "hit your ... limit" reply is an interrupted item: do not relaunch it and do not count it as done; check git before resuming.

## Step 1 - Understand and check prerequisites

1. Read ONLY the Part's sections, the criteria C and the Execution section of the goal document, plus progress. Research is spot consultation.
2. Check `origin/<main>`, `gh pr list` and `git status`: another session may have done something unrecorded. A sibling Part closed in the local progress counts as done for the "Parts" table, even if it is not merged; its merge/migration is the owner's prerequisite.
3. A prerequisite in the "Parts" table that depends on the owner (decision, merge, deploy, migration): say ONCE `names.need_you` + the exact action and STOP (with `/goal`, ask for `/goal clear`). Never "still waiting" in a loop.

## Step 2 - Base and map

1. `git fetch`; your OWN worktree from `origin/<main>` with the Part branch. Before committing: `git branch --show-current`.
2. One `tune-up:mapper` per item group, ALL groups in one message, rechecks EVERY line cited in the goal against today's base and returns current snippets (`file:line`). Line moved: adjust the work order, not the goal; note it in progress. In that same message call `tune-up:skill-finder` (item text, absolute `info.catalog_path`) only when `info.catalog_path` is set and the goal item has no Skills.
3. Item that reads, filters or deletes EXISTING data: while the mappers run, the main session runs 1-3 read-only queries on production (counts per status/shape, NULL counts, lengths, min/max dates). Aggregates and shapes only, never a raw value of a phone, name, e-mail or message. Paste the result under REAL DATA in the order; never copy it to progress or to a test fixture.

## Step 3 - One item at a time

Build the work order from `${CLAUDE_PLUGIN_ROOT}/templates/work-order.md` and dispatch in background. "Skills to read" ALWAYS includes every entry of `info.pitfall_skills` whose `paths` globs match the absolute path of an owned file (worktree + path, no `:lines` suffix; `**/` also matches zero folders), with or without a catalog, plus the goal's "Skills"; the skill-finder (Step 2) only adds extras. A handoff whose json `skills_read` misses a matched pitfall skill: note it in progress and tell the reviewers, who get the same paths under PITFALLS TO READ. 1 item (or items in the same files). `maxTurns` 220; past ~150 steps the executor stops and reports. Database item: the executor proves it on a local database, never production. The executor commits its own item on the Part branch with `git add` by name; push and PR go at the end through `/tune-up:ship`, only with the request above.

## Step 4 - Item review

- Up to 3 reviewers (opus, high), ALL in ONE message, receiving ONLY the item's diff + criterion C + `PITFALLS TO READ` (the same absolute paths as the executor's pitfall skills): `tune-up:reviewer-failures` always; `tune-up:reviewer-database` for migration/access rules/RPC/trigger/SQL; `tune-up:reviewer-security` for auth, personal data, payment, webhook or sending.
- Reviewers end with a fenced json block `{"verdict","findings":[{"sev","file","line","introduced","proof","title"}]}` (proof: observed|read|suspected) and the last line `Verdict: ...`. Route by the json: `introduced` and sev CRITICAL/HIGH goes back; the rest goes to the later document. Missing or invalid json: ask again once.
- All CRITICAL/HIGH from all reviewers become ONE fix round: a NEW executor gets the ORIGINAL order + the findings + the item's cumulative diff (never SendMessage to the old one). A MEDIUM of 1-3 obvious lines may ride along, never alone.
- MEDIUM, LOW and pre-existing -> the phase `names.later` document (1 line: file:line, finding, reviewer).
- Next round: only the reviewer(s) that rejected, receiving `PREVIOUS FINDINGS` + the cumulative item diff, marking each finding closed or reopened. Max 2 rounds; CRITICAL/HIGH left or count not dropping -> `names.need_you` and STOP.
- Record per item in progress: executor, step count and pitfall skills read (from the handoff json, real numbers, not estimates), CRITICAL/HIGH per round (e.g. `HIGH 2->0`, reviewer and 1-line finding each).

## Step 5 - Part gate

1. One `tune-up:checker` per side the Part touched (as the profile splits them; otherwise one call), all in ONE message, in the worktree; each runs the profile's "Definition of done", comparing with main (a pre-existing failure is not yours, but name it).
2. Criteria C measured (query/command) and written in progress with the result.
3. Project docs updated if the profile asks.
4. Migration headed for production: hand over the file and steps; apply only via `/tune-up:migration` on the owner's order.
5. Say what did NOT run (CI, test, deploy) and why.

## Step 6 - Close and STOP

1. Progress document (local `<plans_dir>`, then copied into the Part branch): `names.part_closed` (date), what landed, criteria measured, what stays with the owner (merge, deploy, migration), the later document, the next Part's `/goal` command ending in ` - follow /tune-up:part. Stop when: "<names.part_closed>" in progress OR you wrote <names.need_you> OR 40 turns.`
2. Backlog: copy the open items of the phase `names.later` into the `names.backlog` document in `<plans_dir>/` (`names.roadmap` and `names.backlog` live in `plans_dir`; `names.vision`, `names.prd`, `names.architecture`, `names.design`, `names.decisions` in `docs/`; create it if missing; skip duplicates).
3. Knowledge graph: if `graphify-out/` exists AND `command -v graphify` succeeds, run `graphify update .`; otherwise skip silently.
4. Pitfalls learned: for each CRITICAL/HIGH of this Part that can repeat (a pattern, not a one-off slip), draft 1 line for the pitfall skill of the project's modules whose `paths` match the file (name or description says pitfalls/armadilhas), in its format: **rule.** Why: what happened (Part, date). Already covered by a line: propose sharpening that line instead, never a duplicate. Show the drafts in ONE `AskUserQuestion` (multiSelect); record the approved ones via `/tune-up:learn` (it edits the module in `plugin_source`; without it, the rule goes to the project profile). No candidate: write "no new pitfall" in progress.
5. If the project has a Claude memory, record a short note there (+ index line).
6. Short answer: done, what depends on the owner, pitfalls recorded, next Part command. STOP. Never chain the next Part in this conversation.
