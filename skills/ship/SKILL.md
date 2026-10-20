---
name: ship
description: Commits and opens the PR with an honest body. Use for "push and PR", "commit", "open the PR", "ship it", "entrega", "sobe a PR", "abre a pr". Merge belongs to the owner, never to you (unless the profile says otherwise).
argument-hint: "[branch or note]"
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info)
---

# Ship - commit, push and PR

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Request: $ARGUMENTS

The JSON above is the context. Write to the user in its `language`, honoring `reply_style`; final answer short. Use document names from `names`, never literal. Models/effort per role from `models`; if missing use haiku/medium for the checker. Read the project profile (`profile_path`): who merges, definition of done, deploy order, production.

## Steps

0. **Request.** Does the owner's message this turn (or the `/goal` condition they wrote) ask for commit/push/PR? If not, write `names.need_you` + the ask and stop.
1. **Where am I.** `git branch --show-current`, `git fetch`, `git status --short`. Does the branch have an earlier PR? `gh pr view --json state,number`. Merged: the branch is dead. Create a new branch from `origin/<main>`, bring the commits with `cherry-pick`, open a new PR. Never stacked PRs.
2. **Only what belongs to the task.** Other sessions edit the same repo. `git add` by file name only. Never `git add -A`, `.`, `commit -a` or `git stash`. A file you do not recognize stays out; say which.
3. **Commits.** Only what is left (the executor already committed the Part's items). One per wave or item when sensible. Short message in the repo's style (`git log --oneline -10`). End with the attribution the environment asks for.
4. **Gate.** If `tune-up:checker` has not run the profile's definition of done in this state, run it. Compare with main: a pre-existing failure is reported as such.
5. **PR body.** Write it to a scratchpad file from `${CLAUDE_PLUGIN_ROOT}/templates/pr-body.md`, in the `language`. Deploy order AT THE TOP (SQL/migration -> merge -> backend deploy -> frontend deploy). Say what did NOT run and why.
6. **Push and PR.** `git push -u origin <branch>` and `gh pr create --base <main> --body-file <file>`. Base is always the main branch.
7. **After.** Update the phase progress document (PR, state, what depends on the owner).

## Rules

- Merge is the owner's. Never run `gh pr merge`. Leave the body ready and ask.
- Secret, token or personal data in the diff: stop and warn before pushing.
- A profile with "push straight to main": only when the owner asks and the profile allows.
- A fix after merge is a new PR cut from main.
- If `gh` fails, say you could not check the PR; do not assume.

## Answer

- PR link.
- "Merge is yours."
- Deploy order in 1 line and whether a migration is pending (yes/no).
- What the owner tests in production.
- What did not run (CI, tests), in 1 line.
