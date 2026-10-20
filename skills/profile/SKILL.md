---
name: profile
description: "Creates or updates the project profile (.tune-up/project.md and config.json) by detecting git, stack, tests, database and deploy. Use on: create the project profile, profile; cria o perfil do projeto, perfil do projeto."
argument-hint: "[project folder]"
disable-model-invocation: true
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info)
---

# Project profile

Folder: $ARGUMENTS (empty = current directory)

## Context (injected)

Context: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info`

Fields: `language`, `owner`, `reply_style`, `names{}`, `models{}`, `profile_path`, `plans_dir`, `setup_done`, `tools`. If the JSON did not load, run the command once with Bash. Reply in `language`; if the project already has a `language` in `.tune-up/config.json`, that one wins for the project files. Call the user `owner`.

Creates or updates `.tune-up/project.md` and `.tune-up/config.json` at the project root. tune-up hooks and skills read both files. A legacy `.tune-up/projeto.md` or Portuguese config keys (`branch_principal`, `merge_pelo_claude`, ...) may exist: read them as they are, show what maps to the new keys, and do NOT convert unless the owner asks.

## Step 1 - Detect (read only)

| What | How |
|---|---|
| Git repo and where it is | `git rev-parse --show-toplevel`; if the working folder is not the repo, look for `.git` in subfolders |
| Remote and main branch | `git remote -v`; `git symbolic-ref refs/remotes/origin/HEAD` |
| Stack | `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml` |
| Tests and lint (definition of done) | `package.json` scripts, `pytest`, `ruff`, `tsc`, CI files |
| Database | folders such as `supabase/`, `migrations/`, `prisma/`, `sql/` |
| Deploy | `Dockerfile`, `vercel.json`, hosting config files |
| Logs and errors | mentions of error trackers or log tools in the README or `.env.example` |
| Synced folders | ask; signs: `.stfolder`, `.stignore` |
| Plans and docs | `plans_dir`, `docs/` |

If a profile already exists: read it, show what changed and update only that.

## Step 2 - Ask (one round, only what could not be detected)

`AskUserQuestion`, up to 4 questions, recommended option first. Candidates:
1. Who does the merge? (default: the owner)
2. What is "production" and what must never be touched in it?
3. Customers or pilots that are not guinea pigs?
4. Synced folders or outbound-message rules the hooks must respect?
5. Project language, if different from the user's.

## Step 3 - Write

- `${CLAUDE_PLUGIN_ROOT}/templates/profile/project.md` is the model of `.tune-up/project.md`. Fill ALL sections; what you do not know stays "not defined". No secrets, passwords or tokens. Write it in the project language.
- `${CLAUDE_PLUGIN_ROOT}/templates/profile/config.json` is the model of `.tune-up/config.json`. Keep the contract keys (`project, main_branches, claude_may_merge, commit_on_main, synced_roots, free_repos, research_free_paths, auth_phrases, research_on_phrases, research_off_phrases, bash_rules, language, plans_dir, supabase_guard, line_limit, line_limit_exclude`), drop the `_comment*` keys and the ones you do not use. Keep the safe defaults unless the owner asked otherwise.
- If the folder is synced, run `chmod u+w` in the SAME command as the `mkdir` and the write.

## Step 4 - Check

- `python3 -c "import json; json.load(open('.tune-up/config.json'))"` must pass.
- Every command under "Definition of done" must really exist: run `--help` or check the script; mark "not tested" if you did not run it.
- Do not commit unless asked. Say whether `.tune-up/` goes into git or stays local.

## Step 5 - Trust

Run this yourself as the last step (it is a guard-relevant file, so the hook asks the owner to confirm; they approve in the prompt):

```
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" confiar <absolute path of .tune-up/config.json>
```

Warn: settings that loosen a guard (merge by Claude, commit on main, free repos, `supabase_guard: false`, a higher `line_limit`, extra authorization phrases) only take effect AFTER this command is confirmed, and again after each later edit of the file.

## Answer

Paths of the two files, what stayed "not defined", what the owner must confirm, and that the owner confirmed the trust command.
