---
name: investigate
description: Investigates a bug, pasted error, "stopped answering", failed booking or customer conversation. Read-only first, cause with proof, smallest fix. Use for "find out why", "investigar", "descobre o porquê".
argument-hint: "<symptom, error, identifier or conversation>"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info)
---

# Investigate - find the cause before touching anything

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Symptom: $ARGUMENTS

The JSON above is the context. Write to the user in its `language`, honoring `reply_style`; final answer short. Use document names from `names`, never literal. Models/effort per role from `models`; if missing use the defaults below.

## Rules

- First pass is READ ONLY: no edits, no re-enabling, no production writes, no customer messages.
- Read the project profile (`profile_path`): "diagnostic sources", production, pitfalls.
- If a project module has its own investigation skill (for example a conversation one), use it in place of step 3.
- A real customer is never a test subject.
- Secret or personal data seen in a log: do not repeat it in the answer, a file or memory.

## Method

1. **Identifier and window.** Get what identifies the case (phone suffix, id, e-mail, request) and the time window in the project's time zone. Missing one: ask ONCE, together with the partial answer you already have.
2. **Triage.** P0 = customer affected now or today; P1 = affects several, no urgency; P2 = pre-existing or cosmetic. Do P0 first.
3. **Sources.** Query those in the profile (logs, traces, database, errors) in parallel, read only. Code sweep: `tune-up:mapper` (haiku, medium unless `models` says otherwise) on today's `origin/<main>`. Check a trace/log exists before promising to find it.
4. **Timeline.** Build customer -> system, with the time of each event. Mark where the chain breaks.
5. **Classify the cause.** Code x data x configuration/prompt x external service. Say which and why; if undecidable, say what is left to measure.
6. **Hypothesis with proof.** Cite `file:line` from today's `origin/<main>` and the data that confirms it. A hypothesis without proof is marked "assumption".
7. **Smallest possible fix.** A few lines + 1 test that fails without the fix. No refactor.
8. **Phase in progress?** If a phase is being planned, ask in one line: "goes into phase NNN's plan, or fix now?"
9. **Fix only on order.** With an order: new branch from main, PR through `/tune-up:ship`. Re-enabling a conversation, resending a message and production writes need the owner's request in the turn.
10. **Memory.** Transient, external or closed cause: record it with "do NOT reinvestigate" and the evidence, so the next session does not redo it.

## Answer

- Cause in 1-2 sentences (or "not found; missing X").
- Timeline in 3-6 lines.
- Proposed minimal fix and what depends on the owner.
- Where the report is (absolute scratchpad path), if one was written.
