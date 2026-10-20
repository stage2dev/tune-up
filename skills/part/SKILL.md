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

- Pass `model` and `effort` on every call. Never a model in `forbidden_subagent_models` (default `["fable"]`).
- Production writes, customer messages, ads: only with the owner's explicit request IN THE TURN. A "yes" to another question does not count.
- Commit of an item on the Part branch: yes. Push and PR only if this Part's request (message or `/goal` condition) says push/PR; otherwise leave all ready and write `names.need_you` may I push and open the PR? Branch cut from the day's `origin/<main>`. Merged PR = dead branch: a post-merge fix is a NEW PR from main; never stacked PRs.
- Never `git stash -u`. `git add` by file name only. Preserve existing changes and untracked files.
- Read the project profile (`profile_path`): definition of done, production, pitfalls.

## Step 1 - Understand and check prerequisites

1. Read ONLY the Part's sections, the criteria C and the Execution section of the goal document, plus progress. Research is spot consultation.
2. Check `origin/<main>`, `gh pr list` and `git status`: another session may have done something unrecorded.
3. A prerequisite in the "Parts" table that depends on the owner (decision, merge, deploy, migration): say ONCE `names.need_you` + the exact action and STOP (with `/goal`, ask for `/goal clear`). Never "still waiting" in a loop.

## Step 2 - Base and map

1. `git fetch`; your OWN worktree from `origin/<main>` with the Part branch. Before committing: `git branch --show-current`.
2. One `tune-up:mapper` per item group rechecks EVERY line cited in the goal against today's base and returns current snippets (`file:line`). Line moved: adjust the work order, not the goal; note it in progress.

## Step 3 - One item at a time

Build the work order from `${CLAUDE_PLUGIN_ROOT}/templates/work-order.md` and dispatch in background. Fill "Skills to read" from the goal's "Skills" (or call `tune-up:skill-finder` with the item text and the absolute `info.catalog_path`; no catalog = none). 1 item (or items in the same files). `maxTurns` 220; past ~150 steps the executor stops and reports. Database item: the executor proves it on a local database, never production. The executor commits its own item on the Part branch with `git add` by name; push and PR go at the end through `/tune-up:ship`, only with the request above.

## Step 4 - Item review

- Up to 3 reviewers (opus, high), receiving ONLY the item's diff + criterion C: `tune-up:reviewer-failures` always; `tune-up:reviewer-database` for migration/access rules/RPC/trigger/SQL; `tune-up:reviewer-security` for auth, personal data, payment, webhook or sending.
- Only CRITICAL/HIGH introduced by the diff goes back: a NEW executor gets only the findings + the diff (never SendMessage to the old one). A MEDIUM of 1-3 obvious lines may ride along, never alone.
- MEDIUM, LOW and pre-existing -> the phase `names.later` document (1 line: file:line, finding, reviewer).
- Next round: only the reviewer that rejected, only on the fix diff. Max 2 rounds; CRITICAL/HIGH left or count not dropping -> `names.need_you` and STOP.
- Record per item in progress: executor, step count, serious findings.

## Step 5 - Part gate

1. `tune-up:checker` in the worktree runs the profile's "Definition of done", comparing with main (a pre-existing failure is not yours, but name it).
2. Criteria C measured (query/command) and written in progress with the result.
3. Project docs updated if the profile asks.
4. Migration headed for production: hand over the file and steps; apply only via `/tune-up:migration` on the owner's order.
5. Say what did NOT run (CI, test, deploy) and why.

## Step 6 - Close and STOP

1. Progress document: `names.part_closed` (date), what landed, criteria measured, what stays with the owner (merge, deploy, migration), the later document, the next Part's `/goal` command ending in ` - follow /tune-up:part. Stop when: "<names.part_closed>" in progress OR you wrote <names.need_you> OR 40 turns.`
2. Backlog: copy the open items of the phase `names.later` into the `names.backlog` document in `<plans_dir>/` (`names.roadmap` and `names.backlog` live in `plans_dir`; `names.vision`, `names.prd`, `names.architecture`, `names.design`, `names.decisions` in `docs/`; create it if missing; skip duplicates).
3. Knowledge graph: if `graphify-out/` exists AND `command -v graphify` succeeds, run `graphify update .`; otherwise skip silently.
4. If the project has a Claude memory, record a short note there (+ index line).
5. Short answer: done, what depends on the owner, next Part command. STOP. Never chain the next Part in this conversation.
