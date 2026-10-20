---
name: research
description: Research that changes NOTHING. Use for "research only", "don't change anything", "study first", "compare with our code", "só pesquisa", "não altere nada", "estude primeiro". Ends in numbered questions.
argument-hint: "<question or topic>"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info)
---

# Research - read only

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Question: $ARGUMENTS

The JSON above is the context. Write to the user in its `language`, honoring `reply_style`. Use document names from `names`, never literal. Models/effort per role from `models`; if missing use the table defaults.

Nothing is changed: no code, database, external service or git (no commit, push, PR, stash). Write only in the scratchpad or the plans folder (`plans_dir`).

## Step 1 - Understand

- Ambiguous question: echo in 1 line what you will answer and go on. Do not stop to ask what can be assumed.
- Read the project profile (`profile_path`) if present: diagnostic sources, production, pitfalls.
- Define the base: `git fetch` and the hash of `origin/<main>`; always read code from it, not from the dirty tree.

## Step 2 - Dispatch (one message, background)

| Purpose | Agent | Default model | Effort |
|---|---|---|---|
| Where it is / how it works in our code | `tune-up:mapper` | haiku | medium |
| Official docs, market, competitor, pricing | `tune-up:researcher` | sonnet | medium |

- Simple question: 1 mapper is enough; 2-4 only for a wide topic. One theme each, numbered questions, "answer with file:line" or "URL + date".
- Paid tool (SEO, video, credit API): estimate cost first and save raw data to disk BEFORE summarizing.
- Never a model in `forbidden_subagent_models` (default `["fable"]`). Do not wait awake; do not read the agent's output file.

## Step 3 - Measure (yourself)

- Database and logs: READ ONLY (select, list logs). No insert, update, migration, deploy.
- A measured number beats a guess. Note the query and date.

## Step 4 - Consolidate

Write `<scratchpad>/research-<topic>.md` (or in the phase folder, if one exists; named by `names.research` there):
- 3-line answer on top.
- Findings with `file:line` (at the cited hash), measured numbers and source (URL + date).
- What was NOT verified.
- Options with cost and risk.

## Step 5 - Answer

1. The finding that changes everything, in 1-2 sentences.
2. Numbered questions, recommended first, answerable by "1 yes / 2 no".
3. Absolute path of the saved file.
4. Final sentence: "Nothing was changed." Only if true; if something was touched, say what.

Research mode ends when the owner says "let's build", "go ahead", "pode fazer" or equivalent. Then use `/tune-up:plan` or `/tune-up:part`.
