# Phase NNN - <Short name>

> Source: <where the request came from, date; "verbatim copy in `ORIGINAL-REQUEST.md`" if pasted>. Code base: `origin/<main>` <hash> (<PR/date>). Numbers measured in production on DD/MM (read only). External docs consulted on YYYY-MM-DD (URLs in `{{names.research}}`).
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
| <n.n> | <up to 3 from `tune-up:skill-finder`, or "none"> |

## Waves

### Wave 0 - <name> -> Part A

**0.1 <item>** - S/M/L (<executor or "owner + coordinator">)
- Action: <what to do, with concrete names>.
- Mirror: `<file:line>`.
- Validate: <C# or command>.

### Wave 1 - <name> -> Part B

**1.1 <item>** - L (tune-up:executor-opus)
- Action:
- Mirror:
- Validate:

## Parts (one context per part)

| Part | Waves | Prerequisite | Exit gate | Command |
|---|---|---|---|---|
| A | 0 | none | <criteria C green + what is written> | `/goal Phase NNN Part A: Wave 0 of {{names.goal}} (<summary>) - follow /tune-up:part. Stop when: "{{names.part_closed}}" in {{names.progress}} OR you wrote {{names.need_you}} OR 40 turns.` |

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

Models and effort per role come from `info` (`models`). Defaults: coordinator = main session, highest effort; reviewers = opus, high; mapper, checker, skill-finder = haiku, medium; executor-sonnet, executor-opus, writer = sonnet/opus/sonnet, medium.

- `tune-up:executor-sonnet` for simple items: <list>. `tune-up:executor-opus` for database, money, auth, external sending, concurrency: <list>.
- Reviewers, up to 3 per item: `tune-up:reviewer-failures` always; `tune-up:reviewer-database` for migration/trigger/access rules/RPC/SQL; `tune-up:reviewer-security` for auth, token, personal data, payment, webhook, sending. Only CRITICAL/HIGH from the diff goes back (NEW executor, max 2 rounds); MEDIUM/LOW -> `{{names.later}}`.
- Work order = 1 item, `maxTurns` 220, mapper map pasted, focused test; stop and report past ~150 steps.
- Production writes (migration, SQL) and any external action: only with the owner's explicit request in the turn.
- Gate = 0 CRITICAL/HIGH + definition of done (`tune-up:checker`) + the wave's criteria C + project docs updated when the profile asks.

## Plan review (DD/MM)

**Round 1 (opus, high):** N CRITICAL, N HIGH, N MEDIUM, N LOW -> <applied in which sections>. Detail in `{{names.plan_review}}`.
