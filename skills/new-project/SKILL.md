---
name: new-project
description: Creates a new project folder with git, docs, plans, tests, CI and agent rules from the talk's vision; the user picks the stack. Use for "new project", "start a project", "scaffold", "projeto novo", "criar projeto", "começar um projeto".
argument-hint: "[folder name]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info)
---

# New project

Context: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info`

Folder name (optional): $ARGUMENTS

The JSON above is the context. Talk to the user in its `language`, honoring `reply_style`. Name every document with `names` (keys `vision`, `prd`, `architecture`, `design`, `decisions`, `roadmap`, `backlog`, `agents`), never a literal name. `plans_dir` is the plans folder (default `.planning`); `tools` says what is installed. If `info` failed, say so and use defaults.

Rule: you never choose the stack. Every stack, test and CI choice comes from the user's answer. No dependency is installed, no remote is created, nothing is pushed or committed (only `git init`).

## Step 0 - Preconditions

1. A vision must exist: `docs/<names.vision>` in the current repo, or one the user points to (made by `/tune-up:talk`). If none: say so, suggest `/tune-up:talk` first, and stop unless the user insists (then ask for the one-sentence idea and write a short vision from it).
2. If talk mode is on (the hook blocks code writes), ask the user to say an exit phrase first (en: "let's build", "start building"; pt-BR: "pode construir", "comece a aplicar") and wait. Create no file before that.
3. Read the vision and, if present, the PRD (MVP, constraints, chosen tech). Anything already decided there is not asked again.

## Step 1 - Ask what is missing

Use `AskUserQuestion`, up to 4 questions per call, recommended option first, always with an "other" way out. Skip what the documents or `$ARGUMENTS` already answer.
- Folder name (kebab-case; default from the vision's name) and where to create it (default: a new subfolder of the current directory; it must not exist yet or must be empty).
- Type: web app, site/landing, API, automation, game, mobile.
- Front-end stack (if the type has a screen): common options such as React + TypeScript, Vue, Svelte, plain HTML/CSS/JS, or a game engine, plus "other".
- Back-end stack (if the type has a server side): common options such as Node + TypeScript, Python + FastAPI, Go, or none (static / managed backend), plus "other".
- Tests: which test tool per side (default: the stack's usual one) and whether to add end-to-end tests now (default no).
- CI: GitHub Actions minimal workflow, other, or none.

Which sides exist:

| Type | frontend/ | backend/ |
|---|---|---|
| web app | yes | yes |
| site / landing | yes | only if the user asks |
| API | no | yes |
| automation | no | yes (scripts and jobs) |
| game | yes (client) | only if the user asks |
| mobile | yes (app) | ask |

Show a summary (name, type, sides, stack, tests, CI) and ask "create it?" before writing anything.

## Step 2 - Create the skeleton

Work in the new folder. Everything the stack decides is marked `[STACK]` in the templates; fill every mark from the answers. Keep it minimal: manifest, one entry file and one smoke test per side; no dependency installed, no lockfile.

1. `git init -b main` (no remote, no commit, no push). If `-b` is not supported, `git init` then `git symbolic-ref HEAD refs/heads/main`.
2. `docs/`: one file per document from `${CLAUDE_PLUGIN_ROOT}/templates/project/` (`vision`, `prd`, `architecture`, `decisions`; `design` only if the type has a screen, as a stub that says to run `/tune-up:design`). File names come from `names`. Copy the vision (and PRD) from the talk if they already exist elsewhere; otherwise fill the template from the talk. Fill the stack in the "Stack" section of the architecture document (name + version asked of the user, or "latest at install time"). Translate headings to `language`; delete empty sections.
3. `<plans_dir>/`: `names.roadmap` and `names.backlog` from the same templates, with the MVP phases from the PRD (or one empty phase).
4. `frontend/` and `backend/` (only the sides from the table): the manifest with `lint` and `test` scripts/commands of the stack, `src/` with one entry file, and a tests folder (`tests/` or the stack's convention) holding one smoke test that passes without any service.
5. `.tune-up/`: `project.md` and `config.json` from `${CLAUDE_PLUGIN_ROOT}/templates/profile/` (same rules as the `profile` skill: fill all sections of `project.md` in the project language, "not defined" for the unknown; in `config.json` keep the contract keys, drop `_comment*` keys, set `project`, `language`, `plans_dir`, safe defaults). Fill the "Definition of done" table with the real lint/test commands. Do not run `trust`.
6. `<names.agents>` at the root from `${CLAUDE_PLUGIN_ROOT}/templates/project/agents.md` (it already carries the 450-line rule and the smallest-change rule; keep both). Fill commands, style, tests, plans folder.
7. `README.md` from `${CLAUDE_PLUGIN_ROOT}/skills/new-project/templates/README.md`.
8. `.gitignore` from `templates/gitignore.txt` (same folder), keeping only the blocks of the chosen stack and removing the comment lines that contain `[STACK]`.
9. `.env.example` from `templates/env.example`: variable NAMES only, never a value.
10. CI (if chosen): `.github/workflows/ci.yml` from `templates/ci.yml`; one job per existing side, running install, lint and test with the stack's commands. For another CI system, write its minimal equivalent.

Do not create `LICENSE`, `CONTRIBUTING` or any file not listed.

## Step 3 - Check

- `grep -rn "\[STACK\]\|{{" .` finds nothing (git internals excluded). Fix every hit.
- `python3 -c "import json; json.load(open('.tune-up/config.json'))"` passes.
- `.env.example` has no value that looks like a secret.
- Each code file is at or under 450 lines.
- Do not run the install, lint or test commands: nothing is installed yet.

## Step 4 - Knowledge graph (only if installed)

If `tools` says graphify is present: tell the user to run `/graphify .` to build the first map (it is a skill, not a plain command, so you do not run it); later refreshes use `graphify update .`. If it is not present, say nothing about it.

## Step 5 - Finish

Show the created tree (`find . -maxdepth 2 -not -path './.git/*' | sort`). List the commands the user must run themselves to install dependencies (from the stack, for example the package manager's install in `frontend/` and the virtualenv + install in `backend/`), then the first test run. Say what is left open (`[ASSUMPTION]` tags, empty sections, "not defined" in the profile) and that nothing was committed.

Next steps: `/tune-up:design` (if there is a screen), then `/tune-up:plan` for the first phase.
