# Phase NNN - <Short name>

> Source: <where the request came from, date; "verbatim copy in `ORIGINAL-REQUEST.md`" if pasted>. Code base: `origin/<main>` <hash> (<PR/date>). Numbers measured in production on DD/MM (read only). External docs consulted on YYYY-MM-DD (URLs in `{{names.research}}`), only if there is an external dependency.
> No app file was changed while writing this plan.

## GOAL

**<One target sentence: what starts to happen, for whom, with which guarantee.>**

| | Today | After |
|---|---|---|
| <dimension> | <measured state, with a number> | <target state> |

**Criterion that governs the design:** <the rule that decides doubtful cases; "when in doubt, do not X and show why">.

## What the research changed (and why the plan is not the obvious one)

1. <overturned premise> - <measured number or file:line / URL>.

## Acceptance criteria

Each is a query or command, with "today: X - target: Y". Never "got better".

- **C0 - <baseline measurement>:** `<query>` - today: X - target: recorded in {{names.progress}}.
- **C1 - <name>:** `<query or command>` - today: X - target: Y.

## Patterns to mirror

| Needs | Already exists in | Note |
|---|---|---|
| <thing> | `<file:line>` | <do not copy X; if it does not exist, say "does not exist"> |

## Skills

| Item | Skills to read (name - SKILL.md path - why) |
|---|---|
| <n.n> | <every `info.side_skills` entry that matches the item's files; no match: up to 3 from `tune-up:skill-finder`, or "none" and the reason> |

## Waves

### Wave 0 - <name> -> Part A

**0.1 <item>** - S/M/L (<executor or "owner + coordinator">)
- Action: <what to do, with concrete names>.
- Files: <owned paths, existing and new; the Part routes the executor from them>.
- Mirror: `<file:line>`.
- Validate: <C# or command>.
- Base item: yes/no (only adds; the per-item route already marks database, security and risk_globs items).

### Wave 1 - <name> -> Part B

**1.1 <item>** - L (tune-up:executor-opus)
- Action:
- Files:
- Mirror:
- Validate:
- Base item: yes/no (only adds; the per-item route already marks database, security and risk_globs items).

## Parts (one PR and one new conversation per Part; never continue another Part's session)

| Part | Waves | Prerequisite | Exit gate | Command |
|---|---|---|---|---|
| A | 0 | none | <criteria C green + what is written> | `/goal Phase NNN Part A: Wave 0 of {{names.goal}} (<summary>) (new conversation; never continue another Part's session) - follow /tune-up:part. Stop when: "{{names.part_closed}}" in {{names.progress}} OR you wrote {{names.need_you}} OR 40 turns.` |

A Part = 1-2 waves, up to ~8 items or 2 L items; a wave that depends on the owner is its own Part. On closing each Part the coordinator writes the closed marker in `{{names.progress}}` with the next command and STOPS; the owner opens a new context.

## {{names.decisions_heading}} (owner, DD/MM)

- **Q1:** <decision and consequence in the plan>.

## {{names.open_questions}}

<"All decisions are closed." or the list below, saying which Part each blocks.>

- **Q2 - <question>** (blocks Part X): (a) ... (b) ... - recommendation: (a), because ...

## Out of scope (with destination)

- <thing> -> <future phase / {{names.later}}>.

## Risks

- <risk> -> <mitigation in the plan (item) or "accepted in writing">.

## Deploy order

1. <migration applied by the owner> -> 2. <backend> -> 3. <frontend> -> 4. <turn on flag>.

## Execution, review and gate

Models and effort per role come from `info` (`models`). Defaults: coordinator = main session, Opus, high effort, by default; Fable only when the owner opened the session in Fable; never switch to it yourself; reviewers = failures on sonnet, database and security on opus, high; mapper, checker, skill-finder = haiku, medium; executor-sonnet, executor-opus, writer = sonnet/opus/sonnet, medium.

- `tune-up:executor-sonnet` for simple items: <list>. `tune-up:executor-opus` for database, money, auth, external sending, concurrency: <list>.
- Review once per Part, not per item: an item ends when the executor's tests pass and it commits (the coordinator checks the handoff and the diff stat). A BASE ITEM (database, security or risk_globs by the per-item route, or marked in the goal) is reviewed right after it. At the end of the Part: one review over `git diff <base>..HEAD` with the lenses of `guarda.py rota --part`: `tune-up:reviewer-failures` always, plus `tune-up:reviewer-security` when the Part is not low risk and `tune-up:reviewer-database` when `database_globs` matches. Only CRITICAL/HIGH goes back, grouped by files (up to ~5 findings per executor, in sequence: sonnet, or opus for a CRITICAL, a database or security finding, a Part with a risky item or a second fix), with a recheck of the fix diff after each; max 2 fixes, then `{{names.need_you}}`. `tune-up:checker` runs after the last fix, and again after any later one. MEDIUM/LOW/pre-existing -> `{{names.later}}`. Plan review: one round (round 2 only after a CRITICAL); skipped only for a one-Part plan of front or plain text files that also lists a file, has no external dependency and no item acting outside the files (production SQL or data, owner step, external sending).
- Work order = 1 item, `maxTurns` 220, mapper map pasted, focused test; stop and report near ~80 steps.
- Production writes (migration, SQL) and any external action: only with the owner's explicit request in the turn.
- Gate = 0 CRITICAL/HIGH + definition of done (`tune-up:checker` green on the final HEAD compared with main) + the wave's criteria C + project docs updated when the profile asks.

## Plan review (DD/MM)

One round; "Round 2 only after a CRITICAL"; or: "not reviewed: <reason>".

**Round 1 (opus, high):** N CRITICAL, N HIGH, N MEDIUM, N LOW -> <applied in which sections>. Detail in `{{names.plan_review}}`.
