---
name: plan
description: Builds a phase plan (goal, progress, Opus plan review; research only with an external dependency). Use for "plan", "plan this", "adapt this plan", "planejar", "crie o plano", "monte a fase", or a pasted outside plan. Small idea becomes a 1-part plan.
argument-hint: "<request, topic or pasted plan>"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py rota:*)
---

# Phase plan

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Request: $ARGUMENTS

The JSON above is the context. Write to the user in its `language` (final answer short, `reply_style` honored). Use document names from `names` (keys such as `goal`, `research`, `progress`, `plan_review`, `later`, `open_questions`, `need_you`, `part_closed`), never literal. Models and effort per role come from `models`; if a role is missing use the default in the table. If `info` failed, say so and use the defaults.

You (main session, Opus, high effort, by default; Fable only when the owner opened the session in Fable; never switch to it yourself) coordinate: think, decide, dispatch, check. You do not write the long document, map the code or read it yourself.

## Roles

| Role | Agent | Default model | Effort |
|---|---|---|---|
| Map code | `tune-up:mapper` | haiku | medium |
| Official external docs | `tune-up:researcher` | sonnet | medium |
| Write documents | `tune-up:writer` | sonnet | medium |
| Pick skills per item | `tune-up:skill-finder` | haiku | medium |
| Review the plan | `tune-up:plan-reviewer` | opus | high |

- Pass `model` and `effort` on every call. Never use a model listed in `forbidden_subagent_models` (default `["fable"]`).
- Your turns are the cost of a plan: each one rereads the whole conversation. Every independent tool call of a step (reads, git, queries, agents) goes in ONE message; agents whose answer the next step needs run in the FOREGROUND (`run_in_background: false`). Never poll; do not read the agent's output file.
- A question about the code, yours included (a doubtful proof, a line the reviewer cites), goes to ONE `tune-up:mapper` call with all the questions.
- Production: read only. No commit, push or external write unless asked.
- Planning changes no app file. A finding during planning becomes a GOAL item, never a PR.
- If the user said "research only" / "change nothing": stop after Step 2 and use `/tune-up:research`.

## Workflow scripts

If you orchestrate with the Workflow tool, every `agent()` carries a literal `agentType` from the table above (`tune-up:mapper`, `tune-up:researcher`, `tune-up:writer`, `tune-up:plan-reviewer`), plus `model` and `effort`.
A generic agent (no `agentType`) only for work that needs MCP tools, a browser or images, marked with `// tune-up: allow-generic <reason>` on the line above.
Template and review-loop rules: see "Workflow scripts" in the `part` skill.

## Step 1 - Prepare

1. Read the project profile (`profile_path` from `info`; ask nothing) and the repo AGENTS/CLAUDE file: plans folder, production, pitfalls.
2. `git fetch`; note the hash of `origin/<main>`. Do not trust a previous session's summary.
3. Read-only worktree of `origin/<main>` in the scratchpad (`git -c core.longpaths=true worktree add --detach <scratchpad>/wt-main origin/<main>`). Every map uses this base and cites the hash.
4. Number the phase: `ls <plans_dir>/phases | sort -t- -k1,1n | tail -5` right BEFORE `mkdir` (parallel sessions collide). Folder `NNN-short-kebab/`.
5. Pasted request: save a verbatim copy as `ORIGINAL-REQUEST.md`. Outside plans are adapted to this format, never executed as they came.
6. If the profile mandates synced folders, run `chmod u+w` (macOS/Linux; on Windows `attrib -r`) in the SAME command as `mkdir`.
7. Small idea (one behavior, few files): plan ONE part with few items; ONE mapper.

## Step 2 - Research (one message, all parallel)

- 1 or 2 `tune-up:mapper`, one theme each; a wide plan splits the questions between the two, never a third. Each request has: base (worktree + hash), numbered questions, "answer with file:line".
- 1 `tune-up:researcher` if there is an external dependency: numbered questions plus the "decisive question" (the one that can kill the plan). Ask for URL, date, status.
- You, in that same message: read-only production queries to measure what the plan assumes (how many, who, since when). A measured number beats a guess.
- Collect everything in scratchpad files (`map-*.md`, `research-*.md`). The maps stay there: what matters from them goes to the goal (conclusions with file:line), since the research document no longer always exists.

## Step 3 - Coordinator brief

Write `<scratchpad>/<phase>/` brief (name `names.brief`) from `${CLAUDE_PLUGIN_ROOT}/templates/phase/brief.md`. This is where you think: what research overturned, the design, items with size (S/M/L), files and executor (the `executor` that `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py rota --files <the item's files>` answers, all items in ONE message; with no diff it also lists the security reviewer, which is expected: read only `executor` and `why`), criteria C as query/command, Parts, open questions with a recommendation. Be specific (file:line, column names): the writer decides nothing.

## Step 4 - Skills per item

For each item, the entries of `info.side_skills` whose `paths` globs match the absolute path of one of its files (`**/` also matches zero folders) go straight to "Skills", without calling anyone. Only for an item whose files match NO `side_skills` glob, and with `info.catalog_path` set, call `tune-up:skill-finder` (one message, parallel) with the item text and the absolute catalog path (`info.catalog_path`); it returns up to 3 skills (name, SKILL.md path, why). Fill "Skills" in the goal document and "Skills to read" in each work order. The agent answers `none`: leave them empty and say so. No catalog (`catalog_path` empty) or `info.side_skills_missing` non-empty: the plan warns ONCE, with the missing names and the command that generates it (`/tune-up:setup`, ECC step). Item that uses a library API with no skill in the catalog: `tune-up:researcher` brings the excerpt of the official doc (URL + date) for the order's LIBRARY DOC.

## Step 5 - Write

One `tune-up:writer` writes from the brief + maps, each file named by `names` and shaped by the template in `${CLAUDE_PLUGIN_ROOT}/templates/phase/`: ALWAYS `goal.md` -> `names.goal` and `progress.md` -> `names.progress`. `research.md` -> `names.research` (suffix the date) ONLY with an external dependency (the researcher ran); `later.md` -> `names.later` ONLY when there is already something to put in it. Without `names.research`, goal and progress do not reference it (measured numbers and file:line proofs stay in the goal). It returns ambiguities: resolve all in the brief and apply in one round.

## Step 6 - Plan review (Opus, high)

ONE round, always, EXCEPT a plan with ONE Part whose files are all front (`front_globs`) or plain text. Proof, never by eye: plain text = documentation or copy files only (`.md`/`.txt` docs, changelog), never a skill, agent, prompt, template, config or code file. Every other planned file, new ones included, goes to `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py rota --part --files <files>` (no diff yet): exempt only when `why` is nothing but `no diff: cannot rule risk out` plus `globs_off`/`front_globs entry rejected` notes. The exemption ALSO needs: at least one listed file, no external dependency, and no item acting outside the files (production SQL or data, owner/dashboard/env step, external sending); else review. Only plain text files: no call. Any other `why`, an error, no JSON, or an item that also changes an unlisted file = review. Skipped: the goal's plan review section and progress say "not reviewed: <reason>"; no `names.plan_review` file.

1. Round 1: `tune-up:plan-reviewer` with the base, the paths of the goal (and research, if any) and your main worry. Save as `names.plan_review` (template `plan-review.md`).
2. For each finding decide the fix in `<scratchpad>/<phase>/fixes-round1.md`; doubtful proofs go to ONE `tune-up:mapper` call.
3. The writer applies all and records a "Plan review" section in the goal document. You confirm each HIGH closed in the goal (reread + grep) and write it down. A HIGH still open after the writer's fix -> `names.need_you` with the exact ask (no round 2 without a CRITICAL).
4. Round 2 ONLY when round 1 had a CRITICAL: the reviewer checks ONLY that each CRITICAL/HIGH closed, plus new ones. CRITICAL/HIGH still open after that -> `names.need_you` with the exact ask. Never a third. MEDIUM/LOW: you apply or they go to `names.later`.

## Step 7 - Owner decisions

- `AskUserQuestion`, up to 4 questions only the owner can decide; recommended first, "(Recommended)" and why in one line. Nothing the code can answer.
- Answers go under the `names.decisions_heading` heading in goal and progress. `names.open_questions` keeps only what stays open.
- A decision that adds an item or changes the design: quick map + measurement -> brief -> writer -> focused review of that item only (if the plan is not exempt; a new item can end the exemption: rerun the check; when the rerun ends the exemption, run the FULL round 1 of Step 6 over the whole plan and replace the "not reviewed" lines in goal and progress; an already reviewed plan keeps the focused review of the new item only).

## Step 8 - Final check

Reread risky items yourself (database, trigger, access rules, external sending). Look for the pitfalls in the profile, plus the pitfall skills of the project's modules (skills whose name or description says pitfalls/armadilhas), plus: a gate that does not test what it decides, non-atomic writes, data already present at deploy, off-then-on, supposed numbers, external service without dedupe. Fix with `Edit`, confirm with `grep`.

## Step 9 - Close

1. Progress document: state, decisions, next owner action, `/goal` commands for ready Parts, each ending with `(new conversation; never continue another Part's session) - follow /tune-up:part. Stop when: "<names.part_closed>" in progress OR you wrote <names.need_you> OR 40 turns.`
2. If the project has a Claude memory, record a short note there (facts that change everything, Parts, decisions).
3. Short plain answer: the finding that changed the plan, what is decided, what depends on whom, the Part commands. Say nothing was committed.
