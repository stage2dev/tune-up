---
name: skills
description: Finds the right skill for a task in the tune-up skills catalog and loads only that one. Use for "find a skill", "which skill", "is there a skill for", "qual skill usar", "tem skill para".
argument-hint: "<what you need to do>"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info)
---

# Find a skill

Context: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info`

Request: $ARGUMENTS

The JSON above is the context. Reply in its `language`, honoring `reply_style`. If it did not load, run the command once with Bash.

## Steps

1. Request: use the text above; if it is empty, use the task the user is working on now. If there is still nothing, ask one short question and stop.
2. Catalog: take `catalog_path` from the JSON. If it is empty or the file does not exist, say there is no skills catalog yet and suggest `/tune-up:setup` (ECC step). Stop.
3. Call the agent `tune-up:skill-finder` once with the request and the absolute `catalog_path`. Do not read or grep the catalog yourself.
4. The agent answers up to 3 lines `name | path | why`, or `none`.
   - `none`: say no skill fits and continue the task without one.
   - Otherwise show the lines as a short list (name and why; path last).
5. Choice: one result, or one clearly better for the request -> use it. Several close -> ask the user which (AskUserQuestion, one option per skill plus "none").
6. Read only the chosen `SKILL.md` (the path the agent gave). Do not open the other candidates or other files of the skill unless that `SKILL.md` points to them for this task.
7. Follow the chosen skill for the request.

## Rules

- Never install, copy or move skills here; copying belongs to `/tune-up:setup`.
- Never paste catalog content or a whole `SKILL.md` into the reply.
