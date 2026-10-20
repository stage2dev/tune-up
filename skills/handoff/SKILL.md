---
name: handoff
description: "Writes a HANDOFF.md plus a pasteable prompt to continue in a new session. Use on: continue in new session, handoff, context is big, I will compact; prompt para continuar, nova sessão, vou compactar."
argument-hint: "[phase or topic]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info)
---

# Handoff to a new session

Focus: $ARGUMENTS

## Context (injected)

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Fields: `language`, `owner`, `reply_style`, `names{}`, `models{}`, `forbidden_subagent_models` (default `["fable"]`), `profile_path`, `plans_dir`, `setup_done`, `tools`, `plugin_source`, `catalog_path`. Write every reply and document in `language`. Never hardcode marker or document names: use the values in `names` (keys such as `need_you`, `progress`, `part_closed`). Call the user `owner`. If the JSON did not load, run the command once with Bash.

The new text must stand alone: whoever opens it has not read this conversation.

## Steps

1. **Verify the real state**, not from memory: `git branch --show-current`, `git status --short`, `git fetch`, hash of `origin/<main branch>`, `gh pr list --author @me --state open`, migrations applied or pending (per the project profile at `profile_path`), agents still running.
2. **Write `HANDOFF.md`** in the active phase folder under `plans_dir` (or in the scratchpad if there is no phase), in `language`, with:
   - Goal in 1 sentence.
   - Verified state: branch, PRs (number + state), migrations, what is committed and what is not.
   - Files to read: the goal, progress (`names.progress`) and handoff files. Nothing else; the rest is a point lookup.
   - The EXACT next step (command or action) and whose it is (owner or Claude).
   - Pitfalls of this session: what nearly went wrong, what was discarded, "do NOT re-investigate X".
   - What is left to decide (numbered questions, recommended one marked).
3. **Pasteable block** in the reply, short, in a code block: the opening prompt of the new session pointing at `HANDOFF.md` by absolute path, plus a `/goal` command with an exit condition of ONE Part:

   `/goal <goal of the Part> - finish when the Part is closed in the progress file (marker: names.part_closed) OR when you write names.need_you OR after 40 turns`

4. Update the progress file and the phase memory if they changed in this session.

## Rules

- Never paste a secret, token, password or customer personal data into the HANDOFF or the block.
- Do not invent: if something was not verified, write "not verified".
- Do not summarize the whole conversation. Only what is needed to continue.
- Anything that depends on the owner goes under `names.need_you` at the top of the HANDOFF.

## Answer

Absolute path of `HANDOFF.md` + the pasteable block. Nothing else.
