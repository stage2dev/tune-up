# CHANGELOG - tune-up

Every new rule goes in through `/tune-up:learn`: memory + a change here + a test/eval + a version.

## 2.0.0

First public version.

- Skills: `setup`, `talk`, `new-project`, `design`, `plan`, `part`, `research`, `investigate`, `ship`, `learn`, `migration`, `status`, `handoff`, `git-clean`, `profile`, `evaluate`, `skills`, `terminal-title`.
- `setup`: guided first run (language, name, reply style, kinds of use) that writes `~/.config/tune-up/user.json`; optional tools (gh, claude-mem, fast-jev-compaction, Caveman, Ponytail, Graphify, ECC) installed only with consent, with the privacy of each one shown first.
- `talk`: interview, brainstorm and persona debate that produce project documents without code; `new-project` and `design` turn the vision into a scaffold and a design-token prototype.
- `terminal-title`: makes the terminal tab of VS Code-family editors show the conversation topic; `undo` reverts it.
- 12 agents with a fixed model and effort per role (`mapper`, `checker`, `persona`, `skill-finder`, `researcher`, `writer`, `executor-sonnet`, `executor-opus`, `plan-reviewer`, `reviewer-failures`, `reviewer-database`, `reviewer-security`).
- Hooks: git guards, production/Supabase guard, research mode, talk mode, forbidden subagent models, self-protection of settings, plugin and profile files, secret and new-rule notices, SessionStart line.
- Line limit: code files may not pass 450 lines (`line_limit`); `tune-up: allow-long <reason>` in the first 5 lines allows an exception.
- Language: messages and names in English and Brazilian Portuguese, set per user (`user.json`) or per project; `names_override` for document names.
- Output style `caveman-summary` (optional, not forced): final answer as a short plain-language block.
- Evals: `learn-fires`, `investigate-fires`, `skills-finder-fires`, `research-no-edit`, `talk-no-code`, `status-summary`.
