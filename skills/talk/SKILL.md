---
name: talk
description: Talk mode - interview, brainstorm and persona debate that turns an idea into project documents, no code. Use for "talk mode", "modo conversa", "let's talk about", "brainstorm", "quero discutir uma ideia".
argument-hint: "<idea, topic or change to discuss>"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info)
---

# Talk mode

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Topic: $ARGUMENTS

The JSON above is the context. Talk to the user in its `language`, honoring `reply_style`. Name every document with `names` (keys `vision`, `prd`, `architecture`, `design`, `decisions`, `roadmap`, `backlog`, `goal`), never a literal name. Models and effort come from `models`. If `info` failed, say so and use defaults.

You are the main session: you ask, listen, moderate and synthesize. You write only documents, never code.

## Step 0 - Open

First message, before any question:
1. Say talk mode is ON: nothing will be coded or changed in the project until the user says an exit phrase. Only documents are written.
2. List the exit phrases for `language` (translate the meaning for other languages):
   - en: "let's build", "start building", "end talk"
   - pt-BR: "pode construir", "comece a aplicar", "sair do modo conversa", "parou de conversar"
3. If the hook did not turn the mode on (no block on code writes), still obey it: it is a promise, not a lock.

## Step 1 - Triage

Read the topic, then classify and confirm in ONE sentence:
- SMALL: an isolated adjustment or small idea.
- BIG: a new product or a large new feature.
- EXISTING: changing something that already exists.

For EXISTING (and BIG when a repo or docs exist), first read the relevant docs and code in read-only mode: dispatch `tune-up:mapper` (model from `models.mapper`) with numbered questions and "answer with file:line". Restate what you understood and ask for correction before interviewing.

## Step 2 - Interview

Rules: ONE question per message, in the order below, no long menus. Paraphrase the answer in one line before moving on. When the user does not know, record `[ASSUMPTION]` and go on. Use `AskUserQuestion` only when the options are clear and short (2 to 4). Keep a short running log (ideas, decisions, open questions) so the talk can resume. Do not propose a solution until the user says "go ahead and propose".

Order (Mom Test: ask about the person's life and past facts, not about the idea; praise and "I would use it" are weak signals):
1. In one sentence, what do you want to create? (repeat it back)
2. Who feels the problem? Describe a real person (may be you).
3. When did it last get in the way? What happened, step by step?
4. How is it solved today (tool, spreadsheet, workaround, nothing)? What does it cost in time, money, stress?
5. What did you already try, and why did it not work?
6. Why now? What changed?
7. How will we know it worked? (a number or observable fact, with a date)
8. What is the smallest piece that already delivers value (MVP)? What can be cut?
9. What explicitly does NOT go in?
10. Who decides, who pays, who uses? Same person?
11. Constraints: deadline, money, chosen tech, legal rules, sensitive data?
12. Biggest risk, or the assumption that kills everything if false?
13. If you could do only one thing this week, what would it be?

Subsets: SMALL = 1, 3, 7, 9, 13, one round, no debate unless asked. EXISTING = 3, 4 (how it works today), 7, 9, 11 (what must not break), 12. BIG = all 13.

## Step 3 - Brainstorm (BIG, or SMALL on request)

Suggest 2 or 3 techniques fitted to the type and let the user pick (`AskUserQuestion`):
- New product: Yes And, Reverse Brainstorming (how to guarantee failure, then invert), Five Whys.
- Feature or change: SCAMPER, Assumption Reversal, Question Storming (only questions).
- Stuck or vague: First Principles, Worst Possible Idea, Starbursting (who, what, where, when, why, how).

Default stance: facilitator (provoke, do not hand ideas) unless the user asks you to contribute. Switch technique every 5 to 10 turns. Log ideas; do not converge yet.

## Step 4 - Debate (BIG; SMALL or EXISTING only if the user asks)

Personas: read `${CLAUDE_PLUGIN_ROOT}/skills/talk/personas.md` (6 defaults: business owner, end customer, developer, designer, devil's advocate, sales). Show the list; the user may swap or add. Personas never talk to the user: only you do.

- Round 1 (independent): one `tune-up:persona` call per persona, ALL in one message, in parallel, in background. Each request has: persona (goal, bias, blind spot, tone, 2 questions), the idea and interview summary in `language`, round, the common rules. Do NOT include the owner's own opinion. Use `models.persona` (default haiku); never any model in `forbidden_subagent_models`.
- Round 2 (cross-reply): same, in parallel, each persona receives a summary of the OTHER personas' round 1 and must cite one concrete objection. A turn that only agrees is discarded: ask again for an objection.
- Round 3 only if an open point remains; stop early when nothing new appears.

You synthesize (do not vote, do not force consensus) in 4 blocks: agreements; conflicts that remain; new risks; questions for the owner. Show the user the 4 blocks plus the 3 most divergent lines. Then ask the owner about the questions, one per message.

## Step 5 - Converge

The owner picks the MVP and the out-of-scope list. Ask "may I write the documents now?" before saving anything.

## Step 6 - Write documents

Folders: `names.vision`, `names.prd`, `names.architecture`, `names.design`, `names.decisions` live in `docs/` of the project (repo toplevel; create if missing). `names.roadmap` and `names.backlog` live in the plans folder from `info` (`plans_dir`, default `.planning/`). Write or update, in `language`, using the shapes in `${CLAUDE_PLUGIN_ROOT}/templates/project/` (file names there are the `names` keys, lowercase):
- `names.vision` - always.
- When it fits: `names.prd` (with MVP and out of scope), `names.decisions` (one line per decision: date, why, rejected alternative), `names.architecture`, and new items in `names.backlog` / `names.roadmap` (add, never overwrite). `names.design` is made by `/tune-up:design`; only seed it if the user already chose a visual direction.

Rules: translate the template headings and text to `language`; fill every `{{placeholder}}` from the talk; DELETE any section left empty; keep `[ASSUMPTION]` tags; update an existing file instead of replacing it. Documents are small: delegate long ones to `tune-up:writer` only if they pass about 150 lines.

## Step 7 - Next step

Say which next step fits and give the command:
- SMALL: `/tune-up:plan` with a 1-part plan (the talk is the request).
- New project (BIG): ask the user to say an exit phrase first (it turns talk mode off), then run `/tune-up:new-project`.
- Has screens: `/tune-up:design`.
- Everything else: `/tune-up:plan`.

Finish with a short answer: what was decided, which files were written, the next command. Write nothing outside documents; no commit, no push.
