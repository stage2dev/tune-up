---
name: learn
description: Records a new rule in memory, project or user rules (or the plugin source, if set). Use for "remember this", "from now on", "new rule", "never again", "guarde na memória", "a partir de agora", "regra nova", "nunca mais".
argument-hint: "<rule or correction>"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info)
---

# Learn - memory + rules

Context: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info`

Rule: $ARGUMENTS

The JSON above is the context. Write to the user in its `language`, honoring `reply_style`; final answer short. Use marker names from `names`, never literal. The owner already asked: do not ask "may I save?". Ask only if the rule is ambiguous (one question, recommended first).

## Steps

0. **Type.** One-off correction or fact -> memory only. A working rule that holds from now on -> memory + a rule file (or the plugin, if `plugin_source`).
1. **Memory** (only if the project has a Claude memory folder). Look for a duplicate first (`grep -ril` in the project's memory folder). Exists: update it. Else create a `feedback` memory with the rule, `**Why:**` (what happened or what the owner said) and `**How to apply:**` (when it holds). Link related ones with `[[other-memory]]`. Add 1 line to the `MEMORY.md` index.
2. **Where the rule lives.** Pick ONE, in this order of preference:
   - **Hook**: mandatory and detectable in the command or call (zero context cost). Plugin change: only with `plugin_source` (step 3).
   - **Project config** (`.tune-up/config.json`, `bash_rules`): a shell lock, only for that project.
   - **Project profile** (section "Rules" of `.tune-up/project.md`): a rule for that project.
   - **User rules** (`~/.config/tune-up/rules.md`): a rule for every project of the owner.
   - **Memory only**: a fact with no repeatable action.
3. **Apply.** `info.plugin_source` is null (the usual case): write the rule at the project or user level as above, and tell the owner in 1 line that changing the core needs a checkout of the source (`plugin_source`). NEVER write into `~/.claude/plugins/cache` or any copy of the plugin. `info.plugin_source` is set: edit the plugin files in that git checkout. New hook: new test in `tests/`. New or changed skill: an eval case in `evals/` if triggering matters. Keep text short; description <= 250 characters; skill body <= 150 lines; code file <= 450 lines.
4. **Verify** (only when the plugin was edited). In the checkout: `python3 -m unittest discover -s tests` and `claude plugin validate <plugin_source> --strict`. Show the real result. Failed: fix it or say you did not.
5. **Version** (only when the plugin was edited). Add a `CHANGELOG.md` entry and bump `version` (patch) in `plugin.json`.
6. **Commit** (only when the plugin was edited), in the `plugin_source` repository, only the touched files, by name: `git -C <plugin_source> add <files> && git -C <plugin_source> commit -m "<summary>"`. Only if the owner's request allows commits.
7. **Reload.** Plugin edited: ask the owner to run `/reload-plugins` (the current session does not reread by itself).

## Rules

- A secret never goes into memory, config or a commit.
- A rule that contradicts a saved one: show both, say which wins (the owner's most recent) and update the old one.
- Do not raise fixed cost needlessly: if a hook solves it, write no skill text.

## Answer

Where it was saved (memory + the file or plugin checkout), what was tested and passed (if the plugin was edited), and `names.need_you` run `/reload-plugins` (if it was).
