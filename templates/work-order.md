# Work order for the executor

One order per item (or items in the same files). Paste the text below into the call to `tune-up:executor-sonnet` or `tune-up:executor-opus`, or write it once to `<scratchpad>/order-<n>.md` and pass the line `ORDER FILE: <absolute path>` (Workflow template). Never send "read the whole goal": paste only what the item needs; executor and reviewer never read the whole goal or progress document, everything they need is in the order (reviewers: in the order and the patch). Write it in English; the executor reports back in English.

```
ITEM <n.n> - <short title>

GOAL
<1-2 sentences>. Done when: <exact criterion C, pasted LITERALLY from the goal document, as a command or query with the expected result>.

BASE
Worktree: <absolute path>. Branch: <name>. Hash of origin/<main>: <hash>.

ROUTE: <per-item `guarda.py rota` output: executor, why>. Review: <"end of Part" or "BASE ITEM: reviewed right after">. Diverged: <reason, or "no">

FILES OWNED (current snippets, checked today; total <= 200 lines)
- <path:first-last line>
  <pasted snippet>
- <path:first-last line>
  <pasted snippet>
Edit only these paths (and new files the item needs).

WHAT TO DO
<action with concrete names: table, column, function, route>. Mirror: <file:line of an existing pattern>.

REUSE (from the mapper; file:line of what to call or extend, or "none: searched <where>"). Never empty.

REAL DATA (optional; "none" when not applicable)
<aggregates and shapes from read-only production queries: counts, NULLs, lengths, min/max dates; never raw personal values>

UI STATES (front items only)
loading, read error, empty, retry, unmount on success, same-route navigation does not remount, refetch overwriting optimistic data, double click, no permission, flag off: each one "handled at file:line" or "n/a: reason".

SKILLS TO READ (paths; read before coding; ALWAYS the pitfall skills and the side skills whose paths match an owned file, plus the goal's skills, never the whole list; they conflict: repo convention > pitfall skill > side skill)
- <absolute path to SKILL.md> - <why, 1 line>
(Empty: write "none" and the reason.)

LIBRARY DOC (optional; item that uses a library API with no skill in the catalog)
<excerpt of the official doc from `tune-up:researcher`, with URL and date, or "none">

TESTS
- While working, focused tests only: <command> | tail -40
- Before the handoff run lint, types and related tests of the TOUCHED files only, with the commands of the profile "Definition of done" (types filtered to touched files), plus the profile's "Sentinel tests" for the side touched. A missing dependency in the worktree is reported as "did not run: dependency", never installed.
- Not the full suite; the checker runs it at the gate.
- Database item: prove on a local database; never on production.

DO NOT TOUCH
<files, tables, behavior outside the item>. No neighboring refactor.

RULES
- Ponytail: smallest change that works; no new dependency; no speculative abstraction. Before creating a function, component, hook or helper, look for an existing one (REUSE first, then rg); reuse or extend it; common code goes to the shared place the mirror uses.
- Code files stay <= 450 lines. A file that must exceed it gets `tune-up: allow-long <reason>` in its first 5 lines.
- 1 item. Near ~80 steps: stop, commit what is safe, hand back a partial result and report what is missing.
- Git: commit only this item on the given branch with `git add <file names>`. Never git stash, push, PR, merge, `git add -A`, `git add .`, `commit -a`, or any write to production.
- Before declaring done, recheck with grep that the edit is on disk.

DELIVERY
Telegraphic (no preamble, do not repeat the order, fragments are fine), at most ~25 lines; n/a failure paths on one line. Handoff, with these headings: What I built / How I verified (command and observed output) / Spec conformance (criterion C) / Failure paths checked / Flags for the judge / Confidence. End with a fenced json block: {"item","commit","files":[],"tests":[{"cmd","pass","fail"}],"skills_read":[],"steps"}.
```

Coordinator notes:
- The `tune-up:mapper` map is pasted in; the executor does not re-explore what the order already located.
- Review runs once per Part (a BASE ITEM is reviewed right after it). Fix round: a NEW order (sonnet executor; opus for a CRITICAL, a database or security finding, a Part with a risky item or a second fix) for each group of files, up to ~5 CRITICAL/HIGH findings each, in sequence: the ORIGINAL order (its file path, or goal, files owned, skills) + the path of the review json to read (the executor reads the findings there) + the cumulative diff of those files. After a CRITICAL/HIGH fix, ALWAYS recheck: only the fix diff + the previous findings. Max 2 fixes, then need_you. MEDIUM/LOW never block: they go to the later document.
