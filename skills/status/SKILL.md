---
name: status
description: "Shows where the work stands in at most 6 lines (git, PRs, phase progress). Use on: status, where are we, how many parts left, what is missing; status, como está, quantas partes faltam, o que falta."
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info)
---

# Status

## Context (injected)

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Fields: `language`, `owner`, `reply_style`, `names{}`, `models{}`, `forbidden_subagent_models` (default `["fable"]`), `profile_path`, `plans_dir`, `setup_done`, `tools`, `plugin_source`, `catalog_path`. Write every reply and document in `language`. Never hardcode marker or document names: use the values in `names` (keys such as `need_you`, `progress`, `part_closed`). Call the user `owner`. If the JSON did not load, run the command once with Bash.

Reply in `language`, in the `reply_style` format, at most 6 lines. No long diagnosis: the owner asks for detail if wanted.

## Collect (simple commands, one per call)

Run each command as its own Bash call, with no `$(...)`, `;`, `&&`, `|` or `{}` (the permission checker refuses compound commands). Never assume the cwd is the repo. If one fails, say "not measured" for it and go on:

1. `git rev-parse --show-toplevel` (the repo; if it fails, say there is no repo and skip the git lines).
2. `git status --short --branch` (first line `## branch...origin/x [ahead N, behind M]` gives branch and upstream; the other lines are the dirty files, count them).
3. `git rev-list --left-right --count HEAD...@{upstream}` only if the first line of step 2 shows an upstream (`...origin/x`); otherwise skip it.
4. `gh pr list --author @me --state open --limit 8` only if `tools.gh` in the context is true; otherwise say "PRs: not measured".
5. List the phases with the Glob tool on `<plans_dir>/phases/*/` (no `ls` in the shell). Active phase = the highest-numbered one. If the owner names phases, report those instead.
6. The progress file in the local `<plans_dir>` (main checkout, often untracked) is the source of truth: Parts write it there, and their branches only carry a copy for the PR. Use the Grep tool on the local file for the closed-Part pattern and show the last 2 matches. Then do this per reported phase `NNN`:
   - `git branch -a --list "*NNN*"` lists the Part branches (local and `remotes/origin/`).
   - Cross-check: `git grep -n -E "<pattern>" <each branch found> -- <path>`. `<path>` is the progress file relative to the repo root from step 1. A closed line that is on a branch but missing from the local file = "local progress behind <branch>": say it on the odd line. Do not fix it.
   - For each closed Part, does its branch have a PR? Check `gh pr list --state all --head <branch>`. Closed with no PR, or only on a local branch = pushing and opening the PR depend on the owner. PR merged = landed.

Replace `<plans_dir>` with the value from the context and `<main>` with the main branch from the profile. The progress file is `names.progress` inside the phase folder. The pattern is `names.part_closed` with `{X}` turned into `.*` (never the literal word "closed"). The active phase may also be the one the progress file says is in progress.

If background agents of this session exist, count them and say what they do. Do not read their output files.

## Answer

Short lines (2 to 5 words each), one per line, covering:

- **Running:** branch, open PRs (number + 1 word), active agents.
- **Missing:** unclosed Parts of the active phase, as a number (e.g. "missing C, D"); also list the phases found in `plans_dir`.
- **Depends on the owner:** push/PR of a closed Part that has no PR, merge, migration, production test, decision. If nothing: "nothing".
- If something looks odd (branch whose PR is merged, many dirty files, behind origin), say it in 1 line. The phase folder showing as untracked in the checkout is normal: it is not odd.

Fix nothing and open nothing. Only report. If a number could not be measured, write "not measured".
