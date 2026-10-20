---
name: git-clean
description: "Git cleanup with backup, item by item. Use on: git is a mess, clean branches, old PRs, worktrees, stash; limpa as branches, git bagunçado, PRs velhas. Deletes only after the owner's ok."
argument-hint: "[repository]"
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info)
---

# Git clean

Repository: $ARGUMENTS (empty = the current one)

## Context (injected)

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

Fields: `language`, `owner`, `reply_style`, `names{}`, `models{}`, `forbidden_subagent_models` (default `["fable"]`), `profile_path`, `plans_dir`, `setup_done`, `tools`, `plugin_source`, `catalog_path`. Write every reply and document in `language`. Never hardcode marker or document names: use the values in `names` (keys such as `need_you`, `progress`, `part_closed`). Call the user `owner`. If the JSON did not load, run the command once with Bash.

Short final reply. Nothing is deleted without the owner's "ok", item by item.

## Step 1 - LIVE numbers

Run now; never use a number from memory or from a summary.

```bash
git fetch --prune
echo "remote: $(git branch -r | wc -l)"; echo "local: $(git branch | wc -l)"
gh pr list --state open --json number,title,headRefName --limit 100
git worktree list
git stash list
git status --short | wc -l
```

## Step 2 - Classify

- **Merged**: PR `MERGED`, or `git cherry origin/<main> <branch>` with no `+` line (by content, since squash changes the hash).
- **Open**: PR is open. Do not touch.
- **Orphan**: no PR and commits outside main. May be another session's work: show `git log --oneline origin/<main>..<branch>` first.
- **Worktree**: tied to a merged branch, or with dirty files? Show its `git status`.
- **Stash**: show the content (`git stash show -p stash@{n} | head`) before any suggestion. Never `stash drop` without checking.
- Untracked files and existing changes: preserve; list, do not delete.

## Step 3 - Backup before any removal

- For each candidate branch: `git tag backup/<name>-YYYYMMDD <branch>` or `git bundle create <scratchpad>/backup-YYYYMMDD.bundle --all`.
- Confirm the backup exists (`git tag -l 'backup/*'` or `git bundle verify`).

## Step 4 - Propose the order

Give the owner a numbered list: item, class, reason, exact command, how to undo. End by asking which numbers to delete ("give me the order"). Recommended first (start with merged branches that have a backup).

## Step 5 - Execute only what was ordered

- Local: `git branch -d` (use `-D` only if `git cherry` proved the content is already on main and the owner ordered it). Remote: `git push origin --delete <branch>` only for merged branches.
- Worktree: `git worktree remove` (no `--force` if dirty).
- Recheck the live numbers and show before/after.

## Rules

- Never `git stash -u`, `git reset --hard`, `git clean -f` or `push --force`.
- A branch checked out in another worktree is not deleted.
- Doubt about a branch: do not delete; mark "ask".
