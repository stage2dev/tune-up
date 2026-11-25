# Phase NNN - {{names.progress}}

## Plan

- YYYY-MM-DD: <request origin> (verbatim copy in `ORIGINAL-REQUEST.md`, if pasted).
- Research: N mappers (code), N researcher (external docs), read-only production queries by the main session. In `{{names.research}}` only if there is an external dependency; otherwise "no external dependency".
- `{{names.goal}}` written by the writer from the coordinator's brief.
- Plan review (opus, high): one round <score> -> applied; round 2 only after a CRITICAL <verdict>; or "not reviewed: <reason>". Detail in `{{names.plan_review}}`.
- Code base: `origin/<main>` <hash>. No app file was changed.
- **Nothing committed.** The phase folder exists only on disk.

## {{names.decisions_heading}} (DD/MM)

- Q1: <short answer>.
- Still open: <Qn - what it blocks>.

## State

- No Part started.
- Next owner action: <action only the owner can do>.
- Next Parts (new conversation for each):
  - Part A (<prerequisite>): `/goal Phase NNN Part A: ... (new conversation; never continue another Part's session) - follow /tune-up:part. Stop when: "{{names.part_closed}}" in {{names.progress}} OR you wrote {{names.need_you}} OR 40 turns.`

## Rules for whoever opens a Part

- Read only `{{names.goal}}`, this file and the code. `{{names.research}}` (if it exists) is for consultation.
- One Part per NEW conversation; never continue another Part's session. On closing, write the closed marker here with the next command and STOP.
- A pending-review line for your Part = run that review first.
- Recheck the cited lines against today's `origin/<main>` before starting.
- Writing SQL in production, sending messages and any external action: only with the owner's explicit request in the turn.
- Effort: orchestrating session Opus, high effort, by default (Fable only when the owner opened the session in Fable); reviewers `high`; all other agents `medium` (per `info`).
