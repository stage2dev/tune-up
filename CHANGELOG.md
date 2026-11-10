# CHANGELOG - tune-up

Every new rule goes in through `/tune-up:learn`: memory + a change here + a test/eval + a version.

## 2.5.0

The panel closes the token door, masks what it shows and lets modules act.

- `GET /api/sessao` (the token) now answers only with `Sec-Fetch-Site: same-origin`. curl, other local programs and browsers that do not send `Sec-Fetch-Site` (Safari before 16.4) get 403 and can no longer run actions.
- Phones, e-mails and keys are masked in everything the panel shows from a session: transcript events (`cortar()` in `transcricao.py` is the single funnel, rules in `painel/mascara.py`), agents, tracking, and the request text and names of executions (the chat list and the first balloon). The registry still keeps the raw text.
- Module actions: `POST /api/modulos/{id}/acao` runs `agir` of an enabled module behind the same defenses as every POST; `dados` never goes to the log or to an error reply. `GET /api/modulos/{id}?fresco=1` skips the cache. A module's `INFO["negar"]` joins the deny rules of every session the panel starts, chat levels included. Fail-closed: an enabled module that does not load (or has an invalid `negar`) blocks every panel action with 409 until it is fixed or disabled in `painel.json`. Replies (`responder`) resume the session with the rules it was started with, so each session records the module deny rules it started with (`negar_modulos`) and a reply is refused with 409 before anything is stopped or resumed when an enabled module does not load or when the current module rules are not all among the recorded ones (a module enabled or changed after the session started); `pode_responder` is false in those cases (rules read with a 2 s limit, false on error). Entries recorded before this have no rules, so they can still be answered only while no module has deny rules. Session names are built from masked values (`-n`, registry) and `GET /api/estado` masks `sessoes[].nome`.
- `modulos_de_plugins` in `painel.json`: extra screens from installed plugins, as `plugin@marketplace:modulo`.
- New module blocks: `formulario`, `conversa` and `imagem`.
- `painel/web/dist` rebuilt from these sources.

## 2.4.3

Panel on Windows, from the first real CI run of the panel tests there (24 of 160 failed).

- Guard hook (`painel/travas.py`): the fixed protection of settings, the panel and the project package only understood `/`. Paths now go through one normaliser (backslash to slash, `.` and `..` resolved with `posixpath`, drive prefix, case-insensitive when the path looks like Windows or the system is Windows) on both sides of the comparison, added to the old checks, never replacing them. The allowed `dados` folder only counts when followed by a separator: `dadosx/` and `dados.json` are denied. Not yet proven on a real Windows session.
- Dates: `agora_iso` and `iso_local` build timezone-aware datetimes; the naive form raised `OSError 22` on Windows for small timestamps. Same ISO text as before in 7 time zones.

## 2.4.2

- Tests: `test_pitfall_skills_limite` hung on Windows, it was never slow. The test waited for `info` to exit before reading its stdout from a pipe; with 200 skills the answer is larger than a Windows pipe buffer (about 4 KB), so the child blocked on write and the wait timed out at any limit. stdout now goes to a temp file and the limit is back to 5 s. 2.4.1 raised the limit to 30 s on a wrong guess.

## 2.4.1

Panel groundwork (Part 0 of the studio plan).

- Panel on Windows: the run-registry lock moved to `painel/trava.py` and uses `msvcrt.locking` there (`fcntl.flock` elsewhere), same interface. Reading and replacing `execucoes.json` retry on `PermissionError` (Windows refuses to replace a file another thread has open); a persistent read error now raises instead of looking like an empty list. Panel tests run on all three systems in CI. Not yet proven on a real Windows machine: CI is the proof.
- CI: new `panel-web` job (Ubuntu) installs, tests and rebuilds the screens from an empty `dist` and fails when the committed build is stale. A rebuild must start from an empty `dist` (the CSS scanner reads the old bundle otherwise); `painel/README.md` says so.
- `info`: `pitfall_skills` does one `realpath` per plugin instead of one per file. `test_pitfall_skills_limite` went past 5 s on Windows runners; the cause was not measured, so the test now prints the time and waits up to 30 s (other tests keep 5 s).

## 2.4.0

The panel's home screen is now a chat.

- Home (`/`) is a chat: write the request, pick a level. The old home moved to `/resumo`. Each level is an action of group `chat` in `painel/acoes/chat.json`: ask only (sonnet, read-only), simple fix (opus, 1 reviewer, PR), moderate fix (opus high, executors + up to 2 reviewers, one PR), full change (fable, falling back to opus; `/tune-up:plan` with 2 Opus plan reviewers; no code), marketing (opus, drafts only).
- Any action may now set `modelos` (one alias or a preference list), `esforco` and `equipe`. The session starts with the first model the license has; the last one is the fallback. The panel probes the license once with a minimal `claude -p` (about 900 tokens), cached 7 days in the project's `dados/modelos.json`; `modelos_disponiveis` in `painel.json` overrides it.
- Reply in the same conversation: `POST /api/execucoes/{id}/responder`. It stops the idle process, waits for it to exit and runs `claude --bg --resume <sessionId> "text"` with no other option, which wakes the same session with its saved options, tool rules included (measured on CLI 2.1.322). If the CLI starts a copy instead, the copy is stopped and removed.
- The read-only level is enforced by rules, not only by the prompt: Edit/Write denied, and in Bash file writes, state-changing git, PRs and outbound data. The full-change level denies commit, push, PR and merge.
- A project package can replace a core level with the same id and `"substitui": true`, or add levels.
- Text parameters accept line breaks with `"linhas": true` (up to 6000 chars). POST body limit is 32 KB. `eventos?inteiro=1` returns full messages for the chat.
- `painel/web/dist` rebuilt from these sources.

## 2.3.1

- Panel: `painel/web/dist` (the prebuilt screens) is now in the repo. 2.3.0 said it was and it was not: an ignore rule left it out, so a fresh install only showed "run npm run build". CI now fails if the build is missing.

## 2.3.0

The panel: a local dashboard to follow and run the work.

- New `painel/` (Python stdlib server on 127.0.0.1 + prebuilt React screens) and `/tune-up:panel` to start it. Generic: it finds the project from the folder, works with no configuration, and holds no project names.
- Screens: phases and Parts read from the plans folder; Claude sessions with their sub-agents and workflows (model, effort, time, tools); live runs; follow-up lists.
- Buttons launch `claude --bg` from a closed list of actions; tool rules (deny / allow / hook) come from each action's JSON. `pular_permissoes` in `.tune-up/painel.json` (default off) adds `--dangerously-skip-permissions`; measured on CLI 2.1.322, deny rules and hook deny/ask still apply.
- A project adds screens (declarative blocks) and actions in `.tune-up/painel-projeto/`.
- UI and panel README are in Portuguese. macOS and Linux only for now. Panel tests run in CI on those two.

## 2.2.0

Fewer HIGH findings on the first pass, more work in parallel. From an audit of 10 measured Parts.

- `info`: new `pitfall_skills` (name, absolute SKILL.md path, `paths`) from installed modules. `part` always lists the matching ones under "Skills to read" and hands the same paths to the reviewers; no catalog needed.
- `part`: independent agents go in ONE message, in background (all mappers, all reviewers of an item, one checker per touched side). Read-only production aggregates (never personal values) go into the order as REAL DATA for items that read, filter or delete existing data. All CRITICAL/HIGH of all reviewers become ONE fix round that carries the original order and the cumulative diff; the re-review marks each previous finding closed or reopened. Progress is filled from the handoff json.
- Work order: new REAL DATA and UI STATES sections; TESTS asks for lint, types and related tests of the touched files plus the profile's sentinel tests.
- Executors: "Before handoff" self-check of failure paths, red -> green test per finding on a fix round, json block at the end. Reviewers: read the pitfalls after their own pass, json block before `Verdict:`.
- Guard (`agent`): a Workflow script is no longer denied for prose (3+ words) that mentions a forbidden model; short string literals and `model:` values still deny. `scriptPath` is now checked like `script` (unreadable or over 512 KB denies when the session model is forbidden). An Agent without `model` uses the `model:` of its definition file before being denied.
- Config: `plans_dir` accepts single spaces inside a segment.

## 2.1.2

Planning always lives in the local folder.

- `part`: goal, progress, later, research and handoff are read and written in the local `plans_dir` (main checkout), never only in the worktree. At close they are copied into the Part branch, so the PR carries them; the local copy stays the source. A sibling Part closed in the local progress counts as done even before its merge.
- `status`: reads the local progress, and cross-checks it with `git grep` over the phase branches. A closed line that exists only on a branch is reported as "local progress behind". A closed Part with no PR becomes "push/PR depends on the owner". An untracked phase folder in the checkout is not reported as odd.

## 2.1.1

Pitfalls grow from review findings.

- `part`: progress records per item the pitfall skills read and CRITICAL/HIGH per round (`HIGH 2->0`).
- `part` close: each CRITICAL/HIGH that can repeat becomes a drafted line for the matching pitfall skill (or a sharper existing line); the owner approves in one question and `/tune-up:learn` records it.

## 2.1.0

Windows support (native, with Git for Windows).

- Launcher `scripts/py`: hooks and skills run Python through it. It picks `python3`, `python` or `py -3` (3.9 or newer, the Microsoft Store alias is skipped), remembers the choice in the plugin data folder, sets `PYTHONUTF8=1`. Without Python the hooks fail open and the session start says so.
- `PowerShell` tool goes through the guard (hook matcher `Bash|PowerShell`): git/gh/psql checks, protected files and `bash_rules` apply; in talk and research modes only read-only PowerShell passes. Limits (variables, aliases, `Start-Process`, `-File`, .NET calls) are in the README.
- Git Bash paths (`/c/Users/...`, `/tmp`, `~`) are converted to Windows paths before comparison; the owner/permission checks that used `os.getuid` have a Windows equivalent (ACLs are not read; trusted files must be inside the user profile).
- `setup` checks Git, the launcher and Python first, and gives the `winget` commands to type when something is missing; `reference.md` has a Windows install for each optional tool.
- README: requirements and Windows notes. Docs for synced folders say `chmod u+w` is for macOS/Linux (Windows: `attrib -r`).
- Wrappers `cmd /c`, `powershell "..."`, `iex` and strings piped into `sh`/`bash` are opened one level; `.cmd`/`.bat`/`.ps1`/`.com` shims count as the command they wrap.
- Line limit also works on files with CRLF line endings.
- `terminal-title`: the tab title is now `${sequence}` only, so it no longer repeats the name (`Claude Code - claude`) before the conversation has a topic; `aplicar` updates the old value, `desfazer` removes either.
- README: workaround for the Windows `EPERM` rename error of `marketplace add` (install from a local clone).
- CI runs the test suite on Windows, macOS and Linux.

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
