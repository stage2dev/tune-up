# Work order for the executor

One order per item (or items in the same files). Paste the text below into the call to `tune-up:executor-sonnet` or `tune-up:executor-opus`. Never send "read the whole goal": paste only what the item needs. Write it in English; the executor reports back in English.

```
ITEM <n.n> - <short title>

GOAL
<1-2 sentences>. Done when: <exact criterion C, as a command or query with the expected result>.

BASE
Worktree: <absolute path>. Branch: <name>. Hash of origin/<main>: <hash>.

FILES OWNED (current snippets, checked today; total <= 200 lines)
- <path:first-last line>
  <pasted snippet>
- <path:first-last line>
  <pasted snippet>
Edit only these paths (and new files the item needs).

WHAT TO DO
<action with concrete names: table, column, function, route>. Mirror: <file:line of an existing pattern>.

SKILLS TO READ (paths; read before coding)
- <absolute path to SKILL.md> - <why, 1 line>
(Empty: write "none".)

TESTS
- While working, focused tests only: <command> | tail -40
- Not the full suite; the checker runs it at the gate.
- Database item: prove on a local database; never on production.

DO NOT TOUCH
<files, tables, behavior outside the item>. No neighboring refactor.

RULES
- Ponytail: smallest change that works; no new dependency; no speculative abstraction.
- Code files stay <= 450 lines. A file that must exceed it gets `tune-up: allow-long <reason>` in its first 5 lines.
- 1 item. Past ~150 steps: stop, commit what is safe, report what is missing.
- Git: commit only this item on the given branch with `git add <file names>`. Never git stash, push, PR, merge, `git add -A`, `git add .`, `commit -a`, or any write to production.
- Before declaring done, recheck with grep that the edit is on disk.

DELIVERY
Handoff, with these headings: What I built / How I verified (command and observed output) / Spec conformance (criterion C) / Flags for the judge / Confidence.
```

Coordinator notes:
- The `tune-up:mapper` map is pasted in; the executor does not re-explore what the order already located.
- Fix round: a NEW order with only the CRITICAL/HIGH findings + the current diff, for a new executor.
