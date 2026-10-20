# tune-up

A Claude Code plugin that turns a disciplined way of working into defaults: research that changes nothing, a written plan before code, one Part of the plan per conversation, cheap models for mapping and checking, strong models for risky work, and hooks that stop the mistakes that cost the most (a careless `git add -A`, a write to production, a stacked PR).

It is made of three things:

- **Skills** (slash commands) for the whole flow, from the first idea to the pull request.
- **Agents** with a fixed model and effort per role.
- **Hooks** ("travas") that block or ask before dangerous actions, and a line limit per code file.

Issues / source: https://github.com/stage2dev/tune-up

## Requirements

- Claude Code.
- macOS / Linux: Python 3.9 or newer.
- Windows: [Git for Windows](https://git-scm.com/download/win) (needed for `claude plugin marketplace add` and for the hooks, which run in Git Bash) and Python 3.9 or newer from python.org or `winget install Python.Python.3.12`. The Microsoft Store `python3` alias is skipped automatically.

## Install

The same commands on every OS:

```
claude plugin marketplace add stage2dev/tune-up
claude plugin install tune-up@tune-up
```

Then, inside Claude Code:

```
/reload-plugins
/tune-up:setup
```

New plugins only work after `/reload-plugins` or a new session.

## `/tune-up:setup`

A one-time guided setup. It speaks the language you pick from the first question on.

What it asks:

1. Language (`pt-BR`, `en`, or another tag).
2. What to call you.
3. Reply style: `summary` (short plain-language summary, details on request) or `plain`.
4. Kinds of use (site, landing, automation, game, app, marketing, backend, data).
5. Optional: a local checkout of the tune-up source (only if you edit the plugin itself).
6. Which optional tools to install.
7. Whether the terminal tab should show the conversation topic.

It writes `~/.config/tune-up/user.json` only after you confirm the exact JSON.

Nothing is installed without you marking it. Secrets are never typed in the chat. Commands that need a login or a system installer (`gh auth login`, `brew ...`, `winget ...`) are given to you to type yourself with `!`.

Optional tools and what leaves your machine:

| Tool | What it is | Privacy | Undo |
|---|---|---|---|
| gh | GitHub CLI | Talks to GitHub only when used; the login token is stored locally by `gh`. | `gh auth logout`; remove with your package manager |
| claude-mem | Session memory plugin (`thedotmack/claude-mem`) | Records observations of every session (they can contain code or secrets seen in tool output) and sends them to an AI provider to summarize. Sends anonymous usage telemetry to PostHog by default (setup offers to turn it off with `CLAUDE_MEM_TELEMETRY=0`). Opens a local HTTP worker on 127.0.0.1. | `claude plugin uninstall claude-mem@thedotmack`; data in `~/.claude-mem/` |
| fast-jev-compaction | Better compaction summaries (`tamaratran/fast-jev-compaction`) | Sends the whole conversation (tool outputs replaced by notes; tool inputs such as commands and edited text, up to 1000 characters each, are sent too) to TypeSafe at every compaction; needs a TypeSafe API key. Relies on an early-access Claude Code feature that may change. The key is pasted only in the `/plugin` panel or in a terminal outside Claude Code, never in the chat. | `claude plugin uninstall fast-jev-compaction@fast-jev-compaction`; remove the `env` flag or restore the dated `settings.json.bak-tune-up-<date-time>` |
| Caveman | Compression helper (`JuliusBrussee/caveman`) | The plugin has no telemetry (unverified). `/caveman-compress <file>` sends that file to the model. Its separate CLI and "Auto" need an account and are not installed. | `claude plugin uninstall caveman@caveman`; delete `~/.config/caveman/config.json` |
| Ponytail | "Smallest change" helper (`DietrichGebert/ponytail`) | Keeps a local cost/token ledger in `~/.config/ponytail/`; nothing leaves the machine unless you set its `webhookUrl` (unverified). | `claude plugin uninstall ponytail@ponytail` |
| Graphify | Code knowledge graph (PyPI `graphifyy`, two y) | Code extraction is local (no LLM); docs, PDFs and images use the session's model. `graphify install` also adds a short graphify section to `~/.claude/CLAUDE.md`, read in every session (setup says so before installing). | `graphify uninstall` from a folder without a `CLAUDE.md`, then delete the `# graphify` section of `~/.claude/CLAUDE.md` by hand, then `uv tool uninstall graphifyy` |
| ECC | Large skill collection (`affaan-m/ecc`) | Downloads the repo from GitHub. The plugin stays disabled; the catalog and the copies of up to 15 skills you accept are local. | `claude plugin uninstall ecc@ecc`; delete `~/.config/tune-up/ecc-skills/`, `ecc-agents/`, `skills-catalog.md`, `use-map.json` and the copied folders in `~/.claude/skills/` |

Settings changes (`~/.claude/settings.json`, only the `env` keys above) go through one script that saves a dated backup first, writes atomically and refuses names that look like secrets.

## The flow

```
idea ──> talk ──> new-project / design
                        │
                        v
   plan ──> part ──> ship ──> learn
    │        │         │
    │        │         └─ commit + PR with an honest body
    │        └─ ONE Part per conversation, then it stops
    └─ goal + progress + research + plan review
```

- `talk`: interview, brainstorm and a debate between personas; produces project documents, never code.
- `new-project` / `design`: scaffold from the vision; design tokens and a static prototype.
- `plan`: a phase plan. A small idea becomes a one-part plan.
- `part`: runs one Part item by item with reviewers and a gate, then stops.
- `ship`: commit and PR. The merge is yours, not Claude's (unless your profile says otherwise).
- `learn`: records a new rule (memory, project or user rules, or the plugin source) with a test and a changelog line.

## Commands

All commands are `/tune-up:<name>`.

| Command | What it does |
|---|---|
| `setup` | First-run setup: language, name, reply style, optional tools, `user.json`. |
| `talk` | Talk mode: interview, brainstorm and persona debate that turn an idea into documents; no code. |
| `new-project` | Creates a project folder with git, docs, plans, tests, CI and agent rules from the vision. You choose the stack. |
| `design` | Builds the design system (`DESIGN.md` with tokens) and a static HTML prototype from it. |
| `plan` | Builds a phase plan (goal, progress, research, plan review). |
| `part` | Runs ONE Part of a planned phase, with reviewers and a gate, then stops. |
| `research` | Research that changes NOTHING; ends in numbered questions. |
| `investigate` | Investigates a bug or failure: read-only first, cause with proof, smallest fix. |
| `ship` | Commits and opens the PR with an honest body. |
| `learn` | Records a new rule (memory, project or user rules, or the plugin source). |
| `migration` | Applies a database migration to production with a safe protocol, only on your explicit request in the turn. |
| `status` | Where the work stands in at most 6 lines (git, PRs, phase progress). |
| `handoff` | Writes a `HANDOFF.md` and a pasteable prompt to continue in a new session. |
| `git-clean` | Git cleanup with a backup, item by item; deletes only after your ok. |
| `profile` | Creates or updates the project profile (`.tune-up/project.md` and `config.json`) by detecting git, stack, tests, database and deploy. |
| `evaluate` | Evaluates a third-party repo, skill or plugin before importing it; installs only after your ok. |
| `skills` | Finds the right skill for a task in the skills catalog and loads only that one. |
| `terminal-title` | Makes the terminal tab of VS Code-family editors (VS Code, Cursor, Windsurf, Antigravity, VSCodium) show the conversation topic instead of the Claude Code version. `undo` reverts it. JetBrains is not covered: rename the tab by hand. |

## Agents

| Role | Agent | Model | Effort |
|---|---|---|---|
| Maps the code | `mapper` | haiku | medium |
| Checks facts and results | `checker` | haiku | medium |
| Plays a persona in a debate | `persona` | haiku | medium |
| Picks the right skills | `skill-finder` | haiku | medium |
| Researches | `researcher` | sonnet | medium |
| Writes documents | `writer` | sonnet | medium |
| Executes simple items | `executor-sonnet` | sonnet | medium |
| Executes database, money, auth and sending items | `executor-opus` | opus | medium |
| Reviews the plan | `plan-reviewer` | opus | high |
| Reviews for failures | `reviewer-failures` | opus | high |
| Reviews database changes | `reviewer-database` | opus | high |
| Reviews security | `reviewer-security` | opus | high |

You can override models and effort per role in the `models` key of `user.json`.

## Guards (hooks)

Hooks run as Python scripts through a small launcher (`scripts/py`) that finds `python3`, `python` or `py -3` (3.9 or newer) on its own. They block outright, or ask you to confirm; a project can add its own rules.

| Guard | What it does |
|---|---|
| Git | Blocks `git stash -u`, `git add -A` / `git add .` and `git commit -a` (other sessions may edit the same repo), commit on the main branch, force push to the main branch, push to a branch whose PR is already merged, a stacked PR, `git merge` on the main branch and `gh pr merge`. Asks before `reset --hard`, `clean -f`, `checkout -- <path>`, `restore .`, `branch -D` and `stash`. |
| Production / Supabase | Asks before a write to a production database or project (SQL, MCP Supabase tools, remote CLI) unless you asked for it in this turn. Always on; turn it off per project with `supabase_guard: false` in a trusted profile. |
| Research mode | Turns on with phrases like "research only" or "do not change anything" (English and pt-BR). While on, writes outside the scratchpad, `/tmp`, Claude's memory, `~/.claude/plans`, the plans folder and your `research_free_paths` ask for confirmation. Leaves with "go ahead" or similar. |
| Talk mode | Turns on with `/tune-up:talk`, "talk mode" or "modo conversa". Denies code writes (Write, Edit, MultiEdit and Bash) inside the project; allows notes in `.md` files under `docs/`, the plans folder and `.tune-up/`. Leaves with "let's build" or similar. |
| Forbidden models | Subagents never run on models listed in `forbidden_subagent_models` of `user.json` (default: `fable`). Reviewers are forced to opus; a missing `effort` is filled from the role table. |
| Self-protection | Asks before writing to Claude's `settings*.json`, `~/.claude/plugins/`, `~/.config/tune-up/` (profile and trust list), the plugin's own folder and any path in `protected_paths`. |
| Line limit | A code file may not grow past 450 lines (configurable with `line_limit`; generated files, `node_modules`, `migrations` and similar are exempt). Put `tune-up: allow-long <reason>` in the first 5 lines of a file to allow it. Only Write, Edit and MultiEdit are checked. |
| Prompt notices | Warns when a secret seems pasted in the prompt, when a prompt looks like a new rule (suggests `/tune-up:learn`), and after a PR is opened (reminds what the PR body must say). |
| Session start | Injects one line with language, owner name and reply style, and tells you when the profile is missing or not trusted. |

## Limits

The hooks are a safety net against the common mistakes of the model, not a sandbox. A determined process that runs arbitrary code (your own scripts, interpreters such as `python3 -c` or `node -e`) can get around guards that match on command text. For real isolation, use the Claude Code sandbox and permission rules.

Some guards only warn or ask, they do not block: research mode, self-protection, the production / Supabase guard, the "asks before" git commands (`reset --hard`, `clean -f`, `stash`...), and the prompt notices (secret pasted, new rule, PR opened).

### Windows notes

- The hooks need Git Bash. Without it Claude Code runs hooks in PowerShell and they fail. Fix: install Git for Windows, or set `CLAUDE_CODE_GIT_BASH_PATH` to its `bash.exe`.
- If no Python 3.9+ is found, the hooks switch themselves off (fail-open) and the session start says so. Install Python and reopen Claude Code.
- The `PowerShell` tool goes through the same guard as `Bash` (git/gh/psql checks, protected files, `bash_rules`). In talk and research modes only obviously read-only PowerShell passes (`Get-ChildItem`, `Get-Content`, `Select-String`, `Test-Path`, `git status/log/diff/show`...); everything else asks.
- PowerShell limits: variables, aliases and functions are not resolved (`$c = "rm"; & $c x`), nor are `Start-Process` or `-File` scripts; .NET calls (`[IO.File]::WriteAllText(...)`) are seen only by a text check. Like on Linux and macOS, this is a safety net, not a sandbox.
- Windows ACLs are not read. Trusted files (profile trust) must be inside your user profile folder.
- Paths from Git Bash (`/c/Users/...`, `/tmp`, `~`) are converted to Windows paths before they are compared with the protected folders.

## Configuration

| File | What |
|---|---|
| `~/.config/tune-up/user.json` | Personal: `language`, `owner`, `reply_style`, `use_types`, `models`, `forbidden_subagent_models`, `names_override`, `protected_paths`, `plugin_source`, `tools`. Written by `/tune-up:setup`. Delete it to return to the defaults. |
| `<project>/.tune-up/project.md` and `config.json` | Per project, created by `/tune-up:profile`. `config.json` holds `main_branches`, `plans_dir` (default `.planning`), `free_repos`, `research_free_paths`, `bash_rules`, `line_limit`, `supabase_guard`, `*_phrases` and more. |

Trust: a project profile can only tighten the rules until you trust it. Keys that loosen a guard (for example `commit_on_main`, `claude_may_merge`, `free_repos`, `supabase_guard`, `line_limit`, every `*_phrases` list) are ignored in a profile you have not trusted. Run `/tune-up:profile`, or `sh "<plugin>/scripts/py" scripts/guarda.py trust`, to trust the current one. SessionStart tells you when a profile is ignored.

## Language

Messages from the hooks and the skills come in English and Brazilian Portuguese. Pick the language in `/tune-up:setup`; a project profile can override it. Document names (`vision`, `prd`, ...) come from `templates/names.json` and can be changed per user with `names_override`. For another language, setup translates the names once.

## Reply style

If you chose `summary`, run `/output-style` and pick `tune-up:caveman-summary`. It makes the final message a short plain-language block in your language, with technical detail only on request. It is never forced on you.

## Uninstall

```
claude plugin uninstall tune-up@tune-up
claude plugin marketplace remove tune-up
```

Optional extras: delete `~/.config/tune-up/` (profile, ECC catalog and copies), run `/tune-up:terminal-title undo` before uninstalling if you applied the tab title, and use the undo column above for each optional tool.

## License: MIT

See [LICENSE](LICENSE).
