---
name: plan
description: Builds a phase plan (goal, progress, research, Opus plan review). Use for "plan", "plan this", "adapt this plan", "planejar", "crie o plano", "monte a fase", or a pasted outside plan. Small idea becomes a 1-part plan.
argument-hint: "<request, topic or pasted plan>"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info)
---

# Phase plan

Context: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info`

Request: $ARGUMENTS

The JSON above is the context. Write to the user in its `language` (final answer short, `reply_style` honored). Use document names from `names` (keys such as `goal`, `research`, `progress`, `plan_review`, `later`, `open_questions`, `need_you`, `part_closed`), never literal. Models and effort per role come from `models`; if a role is missing use the default in the table. If `info` failed, say so and use the defaults.

You (main session, highest effort) coordinate: think, decide, dispatch, check. You do not write the long document or map the code.

## Roles

| Role | Agent | Default model | Effort |
|---|---|---|---|
| Map code | `tune-up:mapper` | haiku | medium |
| Official external docs | `tune-up:researcher` | sonnet | medium |
| Write documents | `tune-up:writer` | sonnet | medium |
| Pick skills per item | `tune-up:skill-finder` | haiku | medium |
| Review the plan | `tune-up:plan-reviewer` | opus | high |

- Pass `model` and `effort` on every call. Never use a model listed in `forbidden_subagent_models` (default `["fable"]`).
- Independent agents go in ONE message, in background. Do not wait awake; do not read the agent's output file.
- Production: read only. No commit, push or external write unless asked.
- Planning changes no app file. A finding during planning becomes a GOAL item, never a PR.
- If the user said "research only" / "change nothing": stop after Step 2 and use `/tune-up:research`.

## Step 1 - Prepare

1. Read the project profile (`profile_path` from `info`; ask nothing) and the repo AGENTS/CLAUDE file: plans folder, production, pitfalls.
2. `git fetch`; note the hash of `origin/<main>`. Do not trust a previous session's summary.
3. Read-only worktree of `origin/<main>` in the scratchpad (`git worktree add --detach <scratchpad>/wt-main origin/<main>`). Every map uses this base and cites the hash.
4. Number the phase: `ls <plans_dir>/phases | sort -t- -k1,1n | tail -5` right BEFORE `mkdir` (parallel sessions collide). Folder `NNN-short-kebab/`.
5. Pasted request: save a verbatim copy as `ORIGINAL-REQUEST.md`. Outside plans are adapted to this format, never executed as they came.
6. If the profile mandates synced folders, run `chmod u+w` in the SAME command as `mkdir`.
7. Small idea (one behavior, few files): plan ONE part with few items; skip extra mappers and the second review round.

## Step 2 - Research (one message, all parallel)

- 2 to 4 `tune-up:mapper`, one theme each. Each request has: base (worktree + hash), numbered questions, "answer with file:line".
- 1 `tune-up:researcher` if there is an external dependency: numbered questions plus the "decisive question" (the one that can kill the plan). Ask for URL, date, status.
- You: read-only production queries to measure what the plan assumes (how many, who, since when). A measured number beats a guess.
- Collect everything in scratchpad files (`map-*.md`, `research-*.md`).

## Step 3 - Coordinator brief

Write `<scratchpad>/<phase>/` brief (name `names.brief`) from `${CLAUDE_PLUGIN_ROOT}/templates/phase/brief.md`. This is where you think: what research overturned, the design, items with size (S/M/L) and executor, criteria C as query/command, Parts, open questions with a recommendation. Be specific (file:line, column names): the writer decides nothing.

## Step 4 - Skills per item

For each item call `tune-up:skill-finder` (one message, parallel) with the item text and the absolute catalog path (`info.catalog_path`); it returns up to 3 skills (name, SKILL.md path, why). Fill "Skills" in the goal document and "Skills to read" in each work order. No catalog (`catalog_path` empty or the agent answers `none`): leave them empty and say so.

## Step 5 - Write

One `tune-up:writer` writes from the brief + maps, each file named by `names` and shaped by the template in `${CLAUDE_PLUGIN_ROOT}/templates/phase/`: `goal.md` -> `names.goal`; `research.md` -> `names.research` (suffix the date); `progress.md` -> `names.progress`; `later.md` -> `names.later`. It returns ambiguities: resolve all in the brief and apply in one round.

## Step 6 - Plan review (Opus, high)

1. Round 1: `tune-up:plan-reviewer` with the base, the paths of goal/research and your main worry. Save as `names.plan_review` (template `plan-review.md`).
2. For each finding decide the fix in `<scratchpad>/<phase>/fixes-round1.md`; verify doubtful proofs yourself.
3. The writer applies all and records a "Plan review" section in the goal document.
4. Round 2: reviewer checks ONLY that each CRITICAL/HIGH closed, plus new ones. New MEDIUM: you apply. Max 2 rounds; CRITICAL/HIGH left after round 2 -> `names.need_you` with the exact ask.

## Step 7 - Owner decisions

- `AskUserQuestion`, up to 4 questions only the owner can decide; recommended first, "(Recommended)" and why in one line. Nothing the code can answer.
- Answers go under the `names.decisions_heading` heading in goal and progress. `names.open_questions` keeps only what stays open.
- A decision that adds an item or changes the design: quick map + measurement -> brief -> writer -> focused review of that item only.

## Step 8 - Final check

Reread risky items yourself (database, trigger, access rules, external sending). Look for the pitfalls in the profile, plus the pitfall skills of the project's modules (skills whose name or description says pitfalls/armadilhas), plus: a gate that does not test what it decides, non-atomic writes, data already present at deploy, off-then-on, supposed numbers, external service without dedupe. Fix with `Edit`, confirm with `grep`.

## Step 9 - Close

1. Progress document: state, decisions, next owner action, `/goal` commands for ready Parts, each ending with ` - follow /tune-up:part. Stop when: "<names.part_closed>" in progress OR you wrote <names.need_you> OR 40 turns.`
2. If the project has a Claude memory, record a short note there (facts that change everything, Parts, decisions).
3. Short plain answer: the finding that changed the plan, what is decided, what depends on whom, the Part commands. Say nothing was committed.
