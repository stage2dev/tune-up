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
- Windows: [Git for Windows](https://git-scm.com/download/win), with Git Bash, is required (needed for `claude plugin marketplace add` and for the hooks, which run in Git Bash) and Python 3.9 or newer from python.org or `winget install Python.Python.3.12`. The Microsoft Store `python3` alias is skipped automatically.

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

### Windows: `marketplace add` fails with `EPERM ... rename`

A known Claude Code bug on Windows, not specific to this plugin: Claude Code clones the repo and then renames the folder, and Windows Defender or the Search Indexer may still be holding a file in it. Install from a local clone instead:

```
git clone https://github.com/stage2dev/tune-up "%USERPROFILE%\.claude\plugins\local\tune-up"
claude plugin marketplace add "%USERPROFILE%\.claude\plugins\local\tune-up"
claude plugin install tune-up@tune-up
```

(In PowerShell, write `$env:USERPROFILE` instead of `%USERPROFILE%`.) If an earlier attempt left a half-copied folder in `%USERPROFILE%\.claude\plugins\marketplaces\`, delete it first.

A local marketplace does not update by itself. To update: `git pull` in that folder, then `claude plugin marketplace update tune-up`, then reinstall the plugin.

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
| Looks at a screen or image, or creates a visual asset (used only when the router's `visual_agent` names it) | `visual` | opus | medium |
| Retries an item that already failed on opus (used only when the router's `hard_agent` names it) | `executor-hard` | opus | medium |

You can override models and effort per role in the `models` key of `user.json`.

`fable_agents` in `user.json` lists agent types allowed to use a forbidden model: only through the Agent tool with an explicit `model`, never in a Workflow script. List namespaced names only (for example `tune-up:visual`): a bare name can be taken over by a project's own `.claude/agents` file with the same name.

## Panel (local dashboard)

`/tune-up:panel` starts a local web page (only on `127.0.0.1`) for the current project:

- **Phases**: Parts with status, findings per round, linked PR, and a button that runs the Part in a background Claude session.
- **Agents**: every Claude session of the project and, under it, its sub-agents and workflows by phase, each with model, effort, elapsed time and tool count. Refreshes every 2 s.
- **Runs**: live view of each session launched from the panel, with "open in terminal" and "stop".
- **Follow-up**: open work lists.
- **Plugins** (on the Modules screen): your Claude Code plugins in two columns, "Ligado" and "Desligado"; drag a card to the other column or press its button. It changes only the true/false of a plugin already listed in your user Claude settings file (`~/.claude/settings.json`), after saving a dated backup (the last 3 are kept), and takes effect in the next Claude session. A project or local setting that overrides your value is shown on the card; such a card is not dragged, and its button switches only your own value. Tune-up itself cannot be switched off from here.
- **Project modules**: a project can add its own screens (declarative blocks) and actions in `.tune-up/painel-projeto/`, without touching the panel code.

Buttons only launch actions from a closed list; each action carries its own tool rules. Details, configuration (`.tune-up/painel.json`) and the module contract: [`painel/README.md`](painel/README.md) (Portuguese). Works on macOS, Linux and Windows (Git Bash); Python 3.9+; no install step.

## Built-in modules

Studio, Vendas and Marketing come inside tune-up and arrive off. Open the panel's **Módulos** screen (`/modulos`) and press the button on the one you want; press it again to turn it off. No `painel.json` edit and no separate plugin install.

- **Studio** (posts, short videos and ads with your brand): five commands: `/tune-up:post`, `/tune-up:video`, `/tune-up:anuncio`, `/tune-up:marca`, `/tune-up:marca-ler`. Claude never starts them on its own. Post, video and anuncio are started from the panel's Estúdio screen (it passes the work folder, the format and the HyperFrames path); `/tune-up:marca` and `/tune-up:marca-ler` are typed by you. Works on macOS, Linux and WSL2; not on native Windows. Details: [`tune-up-studio/README.md`](tune-up-studio/README.md).
- **Vendas** (WhatsApp sales screen): first version tested only on macOS; needs Docker. Details: [`vendas/README.md`](vendas/README.md).

- **Marketing** (marketing accounts, skills and a guard for ad-account and public-post writes): part of tune-up, no install. It also has a panel tab: turn on **Marketing** in the Módulos screen and the tab "Contas" lists each marketing service with its state, when it was last checked and the next step. The button "Conferir contas" runs the account check for this project in the background (`claude plugin list --json`, `claude mcp list` and `composio connections list`, read-only commands run on your machine; `claude mcp list` and the Composio CLI contact the services they check); it spends no credits. The tab shows no keys, no account names and no command output. Details: [`tune-up-mkt/README.md`](tune-up-mkt/README.md).

Migration (2.19.0): the marketplace lists only `tune-up`. If you installed `tune-up-studio`, `tune-up-vendas` or `tune-up-mkt`, run `claude plugin marketplace update tune-up`, then `claude plugin update tune-up@tune-up`, then restart Claude Code, in this order (on a local clone, `git pull` in the clone first, as in the Windows note above). Then uninstall the old plugins: `claude plugin uninstall tune-up-studio@tune-up`, and the same for `tune-up-vendas` and `tune-up-mkt`. Keeping them is not harmless: the Studio's old commands point at files that no longer exist, and the old marketing and sales plugins duplicate the core (the marketing guard runs twice, the Vendas start hint shows twice, and the `/tune-up-mkt:*` skills appear next to `/tune-up:*`). Your data stays. This order was not yet measured on a real install.

## Guards (hooks)

Hooks run as Python scripts through a small launcher (`scripts/py`) that finds `python3`, `python` or `py -3` (3.9 or newer) on its own. They block outright, or ask you to confirm; a project can add its own rules.

| Guard | What it does |
|---|---|
| Git | Blocks `git stash -u`, `git add -A` / `git add .` and `git commit -a` (other sessions may edit the same repo), commit on the main branch, force push to the main branch, push to a branch whose PR is already merged, a stacked PR, `git merge` on the main branch and `gh pr merge`. Asks before `reset --hard`, `clean -f`, `checkout -- <path>`, `restore .`, `branch -D` and `stash`. |
| Production / Supabase | Asks before a write to a production database or project (SQL, MCP Supabase tools, remote CLI) unless you asked for it in this turn. Always on; turn it off per project with `supabase_guard: false` in a trusted profile. |
| Research mode | Turns on with phrases like "research only" or "do not change anything" (English and pt-BR). While on, writes outside the scratchpad, `/tmp`, Claude's memory, `~/.claude/plans`, the plans folder and your `research_free_paths` ask for confirmation. Leaves with "go ahead" or similar. |
| Talk mode | Turns on with `/tune-up:talk`, "talk mode" or "modo conversa". Denies code writes (Write, Edit, MultiEdit and Bash) inside the project; allows notes in `.md` files under `docs/`, the plans folder and `.tune-up/`. Leaves with "let's build" or similar. |
| Marketing | Asks or blocks writes to ad accounts and public posts, through MCP tools or commands. Fails open (the action goes through) on an internal error. Details: [`tune-up-mkt/README.md`](tune-up-mkt/README.md). |
| Forbidden models | Subagents never run on models listed in `forbidden_subagent_models` of `user.json` (default: `fable`). Reviewers are forced to opus; a missing `effort` is filled from the role table. |
| Self-protection | Asks before writing to Claude's `settings*.json`, `~/.claude/plugins/`, `~/.config/tune-up/` (profile and trust list), the plugin's own folder and any path in `protected_paths`. |
| Line limit | A code file may not grow past 450 lines (configurable with `line_limit`; generated files, `node_modules`, `migrations` and similar are exempt). Put `tune-up: allow-long <reason>` in the first 5 lines of a file to allow it. Only Write, Edit and MultiEdit are checked. |
| Prompt notices | Warns when a secret seems pasted in the prompt, when a prompt looks like a new rule (suggests `/tune-up:learn`), and after a PR is opened (reminds what the PR body must say). |
| Session start | Injects one line with language, owner name and reply style, and tells you when the profile is missing or not trusted. |

## Limits

The hooks are a safety net against the common mistakes of the model, not a sandbox. A determined process that runs arbitrary code (your own scripts, interpreters such as `python3 -c` or `node -e`) can get around guards that match on command text. For real isolation, use the Claude Code sandbox and permission rules.

Some guards only warn or ask, they do not block: research mode, self-protection, the production / Supabase guard, the "asks before" git commands (`reset --hard`, `clean -f`, `stash`...), and the prompt notices (secret pasted, new rule, PR opened).

### Windows notes

- Git Bash is REQUIRED. Without it Claude Code runs hooks in PowerShell, `sh` does not exist there, and every tune-up guard is silently OFF, with no error shown. The panel warns about it. Fix: install Git for Windows, or set `CLAUDE_CODE_GIT_BASH_PATH` to its `bash.exe`.
- If no Python 3.9+ is found, the hooks switch themselves off (fail-open) and the session start says so. Install Python and reopen Claude Code.
- The `PowerShell` tool goes through the same guard as `Bash` (git/gh/psql checks, protected files, `bash_rules`). In talk and research modes only obviously read-only PowerShell passes (`Get-ChildItem`, `Get-Content`, `Select-String`, `Test-Path`, `git status/log/diff/show`...); everything else asks.
- Wrappers are opened one level, like `bash -c` and `eval`: `cmd /c`, `powershell "..."` / `pwsh -Command`, `iex`, and a string piped into `sh`, `bash` or `iex`. `$env:NAME` and `(Join-Path ...)` with literal parts are understood. `.cmd`, `.bat`, `.ps1` and `.com` shims count as the command they wrap.
- PowerShell limits: variables, aliases and functions are not resolved (`$c = "rm"; & $c x`), nor are `Start-Process` or `-File` scripts; .NET calls (`[IO.File]::WriteAllText(...)`) are seen only by a text check. Like on Linux and macOS, this is a safety net, not a sandbox.
- Windows ACLs are not read. Trusted files (profile trust) must be inside your user profile folder.
- Paths from Git Bash (`/c/Users/...`, `/tmp`, `~`) are converted to Windows paths before they are compared with the protected folders.

Workflow scripts: the guard also warns when a Workflow script calls `agent()` without a literal `tune-up:*` `agentType` (a generic agent starts with about three times the context). Mark a justified exception with `// tune-up: allow-generic <reason>` on the line above. The `workflow_generic` key in `config.json` sets the behavior: `warn` (default), `block` or `off`. Start scripts from `templates/workflow-template.js`.

## Windows (WSL2)

The tune-up studio runs on Linux, so on Windows it runs inside WSL2. One command sets that up. Open a NORMAL PowerShell (not "Run as administrator") and run:

```
powershell -ExecutionPolicy Bypass -File scripts\wsl\instalar.ps1 -Projeto <folder>
```

What it does, in plain words:

- Creates its own Linux named `tune-up`, separate from any other Linux you have.
- Downloads 5 pinned files and checks each one against a known sha256 before using it.
- Asks for administrator only if Windows does not have WSL yet, and only for the system `wsl.exe`. It may ask for one restart and continues by itself afterwards.
- Opens a window for the Claude login.

Other modes: `-Login` (log in again), `-Atualizar` (update), `-Medir` (record measurements for the real-machine proof), `-Remover` (delete the distro and the installer folder, after you confirm), `-Forcar` (close open Claude windows in the distro without refusing), `-SemReiniciar` (do not restart Windows by itself), `-Retomar` (continue after a restart).

The studio session reads the project on `C:` through `/mnt/c`. The log is in `%LOCALAPPDATA%\tune-up\wsl\logs`. To remove everything, run the same command with `-Remover`. More detail and a troubleshooting list: `scripts/wsl/README.md`.

Not yet: the panel does not launch studio actions on Windows. That arrives with the next part. This installer was not yet tried on a real Windows machine.

## Configuration

| File | What |
|---|---|
| `~/.config/tune-up/user.json` | Personal: `language`, `owner`, `reply_style`, `use_types`, `models`, `forbidden_subagent_models`, `names_override`, `protected_paths`, `plugin_source`, `tools`. Written by `/tune-up:setup`. Delete it to return to the defaults. |
| `<project>/.tune-up/project.md` and `config.json` | Per project, created by `/tune-up:profile`. `config.json` holds `main_branches`, `plans_dir` (default `.planning`), `free_repos`, `research_free_paths`, `bash_rules`, `line_limit`, `supabase_guard`, `*_phrases`, `risk_globs`, `security_globs`, `database_globs`, `router` and more. |

Trust: a project profile can only tighten the rules until you trust it. Keys that loosen a guard (for example `commit_on_main`, `claude_may_merge`, `free_repos`, `supabase_guard`, `line_limit`, every `*_phrases` list) are ignored in a profile you have not trusted. Run `/tune-up:profile`, or `sh "<plugin>/scripts/py" scripts/guarda.py trust`, to trust the current one. SessionStart tells you when a profile is ignored.

Routing: `python3 scripts/guarda.py rota --files <path> [...] [--diff-file <patch>] [--failed sonnet|opus]` prints one JSON line `{"executor", "reviewers", "why"}` from the file paths: a path matching `risk_globs` sends the item to `tune-up:executor-opus`; `security_globs`, a security keyword in a changed diff line (added or removed; context lines never count), or no diff adds the `security` reviewer; `database_globs` adds `database`; `failures` always runs. No files (blank paths are dropped) routes up (opus + security); a diff file with no diff content counts as no diff; any error routes up with all three reviewers. The three glob lists ADD to the plugin defaults (even untrusted, since adding only tightens) and can never remove one. The `router` block is optional, off by default, and counts only in a trusted profile (an invalid block is rejected whole). When `router.enabled` is true and `rota` gets `--text-file`, the scorer sees only that file, and only when its name ends `.rota.txt` and it is not a symlink (any other name: fixed rule, nothing read): the item's action line and the file base names, cut at the first `REAL DATA`, `PITFALLS` or diff line (any case, also as a markdown heading or list item), masked for secrets, e-mail, phone, CPF and CNPJ, and cut to `max_chars`. It goes to the Jev scorer at TypeSafe; the key is `TYPESAFE_API_KEY`. A missing key, any error or no answer means the fixed rule. `risk_globs` always win (the scorer is not called). The scorer can only keep or raise the executor, never lower it. The output adds `model`, `scores` and `source` (`globs`, `fixed` or `jev`). To measure it: `python3 evals/rota/rodar.py --seco` checks the case file with no network; without `--seco` it makes one API call per case.

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
