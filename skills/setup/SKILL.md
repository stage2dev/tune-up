---
name: setup
description: First-run setup of tune-up - language, owner, reply style, kinds of use, user.json, optional tools (gh, claude-mem, fast-jev, Caveman, Ponytail, Graphify, ECC). Use for "setup", "install tune-up", "configurar", "instalar".
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/titulo_terminal.py aplicar)
---

# Setup

Context: !`sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py info`

The JSON above is the current state (`setup_done`, `language`, `owner`, `reply_style`, `tools`, `plugin_source`, `catalog_path`). If it did not load, say so once and continue with defaults. If `setup_done` is true, show the current values and ask whether to redo everything or only the tools step (c).

Per tool facts (source, check, install, interactive, privacy, undo) live in `${CLAUDE_PLUGIN_ROOT}/skills/setup/reference.md`. Read only the rows you need.

## Hard rules

- Ask with the AskUserQuestion box (max 4 options per question; split longer lists into two questions of the same call). Free text only for the owner name and the language "other".
- From the moment the language is chosen, every word to the user is in that language.
- Nothing is installed or written without the user marking or confirming it. Write only to `~/.config/tune-up/`, `~/.claude/skills/` (ECC copies only through `ecc_catalog.py install`), `~/.config/caveman/` and, with its own confirmation, `~/.claude/settings.json` (only through `settings_merge.py`). Graphify's own installer also adds a block to `~/.claude/CLAUDE.md`: declared in its consent line. Editor settings: only `titulo_terminal.py` (step h).
- Run `claude plugin ...` through Bash one call at a time; each call asks permission. Never add an allow rule for it.
- `gh auth login`, `brew ...`, `winget ...`, any downloaded install script and any login by e-mail or browser: never run them. Give the user the exact `! command` to type.
- Secrets (API keys, tokens): never ask for them in chat, never put them in a command, argument, file, settings or log, never echo them. Only explain where the user pastes them (step d).
- Never run a script piped from the network.
- A plugin only works after `/reload-plugins` or a new session. Do not assume it is active in this conversation.

## (0) Prerequisites (before the questions)

One Bash call, read only: `uname -s; command -v git; sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" -c "import sys; print(sys.version)"` (the launcher prints the Python it chose; it needs 3.9 or newer). `uname -s` starting with `MINGW`, `MSYS` or `CYGWIN` means Windows (Git Bash). No Bash tool at all (Windows without Git Bash) or no `git` means Git for Windows is missing: use the PowerShell tool (`Get-Command git`) only to confirm it.

- Git missing: the user types `! winget install --id Git.Git -e`, then reopens Claude Code. Without it, the hooks of this plugin cannot run.
- Launcher error "Python 3.9 or newer not found" (or a version below 3.9): the user types `! winget install -e --id Python.Python.3.12`, then reopens Claude Code. The Microsoft Store `python3` alias does not count and is skipped.
- Everything ok, or not Windows: say nothing about it and go on. If prerequisites are missing, continue with the questions and do not install anything else until the user has them.

## (a) Questions

1. AskUserQuestion, one question: language - `pt-BR`, `en`, other (user types a tag such as `es`).
2. Plain message in that language: "What name should I call you?" Wait for the answer (trim, max 60 chars).
3. AskUserQuestion, one call with four questions:
   - Reply style: `summary` (short plain-language summary, details on request) | `plain` (normal answers).
   - Kinds of use, part 1 (multiSelect): site, landing, automation, game.
   - Kinds of use, part 2 (multiSelect): app, marketing, backend, data.
   - Local checkout of the tune-up source? "No" | "Yes" (the user types the absolute path in Other). Store it as `plugin_source` or `null`.

Language "other": translate the `en` values of `${CLAUDE_PLUGIN_ROOT}/templates/names.json` once into that language (keep `.md`, keep `{X}`, keep the keys `prd` and `agents` as in `en`) and put them in `names_override`.

## (b) Profile

Build `~/.config/tune-up/user.json` (keep keys the user already had, such as `protected_paths` and `names_override`, unless they changed now):

```json
{
  "language": "<choice>",
  "owner": "<name>",
  "reply_style": "summary | plain",
  "use_types": ["<kinds>"],
  "plugin_source": null,
  "models": {
    "mapper": {"model": "haiku", "effort": "medium"},
    "checker": {"model": "haiku", "effort": "medium"},
    "persona": {"model": "haiku", "effort": "medium"},
    "skill-finder": {"model": "haiku", "effort": "medium"},
    "writer": {"model": "sonnet", "effort": "medium"},
    "researcher": {"model": "sonnet", "effort": "medium"},
    "executor-sonnet": {"model": "sonnet", "effort": "medium"},
    "executor-opus": {"model": "opus", "effort": "medium"},
    "plan-reviewer": {"model": "opus", "effort": "high"},
    "reviewer-failures": {"model": "opus", "effort": "high"},
    "reviewer-database": {"model": "opus", "effort": "high"},
    "reviewer-security": {"model": "opus", "effort": "high"}
  },
  "forbidden_subagent_models": ["fable"],
  "names_override": {},
  "protected_paths": [],
  "tools": {},
  "setup_done": false
}
```

Show the exact JSON, ask "Save?" (yes / change something). On yes, create `~/.config/tune-up/` and write the file with the Write tool. Nothing else in this step.

## (c) Tools

1. Detect in one Bash call (read only): `claude plugin list --json`, `command -v gh graphify node uv`, `gh auth status` (exit code only), `test -f ~/.claude/skills/graphify/SKILL.md`. Read the plugin JSON once and match the ids `claude-mem@thedotmack`, `fast-jev-compaction@fast-jev-compaction`, `caveman@caveman`, `ponytail@ponytail`, `ecc@ecc` (and whether each is enabled).
2. Show a short table: tool | present | enabled.
3. AskUserQuestion ONCE for the missing tools only (multiSelect; split into two questions if more than 4). Each option's description is its privacy line from `reference.md` (what leaves the machine). Nothing marked = nothing installed.
4. For each marked tool, in the order gh, Graphify, Caveman, Ponytail, claude-mem, fast-jev, ECC, use the install row of `reference.md`:
   - Bash (auto): `claude plugin marketplace add <source>` then `claude plugin install <id> --scope user`; `uv tool install graphifyy` then `graphify install` (its consent line says it also adds a short graphify section to `~/.claude/CLAUDE.md`).
   - User types it (`!`): installing `gh` or `uv` (the Windows `winget` commands are in `reference.md`), `gh auth login` (also offer it when `gh` exists but is not logged in).
   - Check right after with the check command and record `tools.<name>` = true/false.
5. A failure stops only that tool: report the error line and move on.

## (d) Settings flags: fast-jev-compaction and claude-mem

Every change to `~/.claude/settings.json` goes through one script (normal permission prompt): `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" skills/setup/scripts/settings_merge.py --set-env KEY=VALUE`. It stops on invalid JSON, saves a dated backup `settings.json.bak-tune-up-<date-time>`, changes only the `env` keys asked, writes atomically and refuses names that look like secrets. Show the before/after of only those `env` keys and ask first. On `error:` show it and skip that flag. Never add a key variable to this file.

fast-jev-compaction (only if marked):

- It needs `CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`. On yes: `settings_merge.py --set-env CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1`.
- The TypeSafe API key: explain, and do nothing else. The user creates the key on the TypeSafe site and pastes it in ONE of:
  - the `/plugin` panel: installed plugins, fast-jev-compaction, its options; the `apiKey` field is sensitive and goes to Claude Code's secure storage (Keychain on macOS);
  - a terminal OUTSIDE Claude Code: `claude plugin configure fast-jev-compaction@fast-jev-compaction --values-stdin`, then type `{"apiKey":"<key>"}`, Enter, Ctrl-D.
  Never in this chat, never with `!`, never as an argument. Without a key the plugin falls back to the native summary.
- Tell the user to restart Claude Code (the env flag needs it).

claude-mem (only if installed now or already present): ask apart, one question: "claude-mem sends anonymous usage telemetry to PostHog by default. Turn it off?" On yes: `settings_merge.py --set-env CLAUDE_MEM_TELEMETRY=0` (restart needed too).

## (e) Caveman (only if installed now or already present)

- Ask: "Turn Caveman's reply mode off by default? tune-up keeps its own reply style; Caveman stays for compression." On yes, write `~/.config/caveman/config.json` with `{"defaultMode":"off"}`; if the file exists, change only `defaultMode` and show the result first.
- Explain `/caveman-compress <file>`: shortens a memory file (for example `CLAUDE.md`), keeps a backup, and sends that file to the model.

## (f) ECC (only if marked or already installed)

1. Ask the source (AskUserQuestion): default `affaan-m/ecc` (upstream) | Other (owner/repo or URL).
2. One Bash call, so ECC is never left on: `claude plugin marketplace add <source> && claude plugin install ecc@ecc --scope user --config hooks_enabled=false && claude plugin disable ecc@ecc`. Check `claude plugin list --json` shows `ecc@ecc` disabled. If it is enabled (install worked, disable failed): say so, offer `claude plugin uninstall ecc@ecc` (one Bash call, normal permission prompt), run it only on yes, then stop this step.
3. `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" skills/setup/scripts/ecc_catalog.py --uses <use_types joined by comma>`. It prints JSON with `candidates`, `kept_user_files` and writes `~/.config/tune-up/skills-catalog.md`. On `error:` show it and stop this step.
4. No use types chosen: skip to step 6. Otherwise call `tune-up:skill-finder` in parallel, one call per kind of use, each with: "kind of use: <kind>; pick from these candidates only: <candidates>; catalog: <absolute catalog path>". Each answer has up to 3 lines `name | path | why`. Merge, drop duplicates and `none`, keep at most 15.
5. Copy only through the script, never by hand or with `cp`. First a dry run: `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" skills/setup/scripts/ecc_catalog.py install --names <a,b> --dest ~/.claude/skills --dry-run` (names only, never paths). Show one table: name | why (the `why` from `risky`, or "-") | removed (the `allowed-tools` value from `stripped_allowed_tools` and the `hooks` value from `stripped_hooks`, or "-") | runs shell? ("yes, left out" for names in `skipped_shell`, else "no"), plus the `rejected` and `skipped_existing` names (an existing folder is never replaced). Say that the copy drops `allowed-tools` and `hooks`, so the skill still works but asks permission for each tool and runs no hook. AskUserQuestion: copy all | let me remove some (user types names) | copy none. Then, for each name in `skipped_shell` the user still wants, ask apart, one AskUserQuestion per name: "<name> runs a shell command each time it loads. Copy it anyway?" (yes | no). Only the names answered yes go in `--allow-shell <a,b>`; never add a name the user did not confirm this way. On yes, the same command without `--dry-run` (plus `--allow-shell` if any); report its JSON (`installed`, `skipped_existing`, `rejected`, `stripped_allowed_tools`, `stripped_hooks`, `skipped_shell`).
6. Say that the rest stays in the catalog and `/tune-up:skills` finds it on demand.

## (g) Reply style

If `reply_style` is `summary`: ask the user to run `/output-style` and pick the tune-up summary style (listed as `tune-up:caveman-summary`). Do not edit settings for this.

## (h) Terminal tab title

AskUserQuestion, one question (in the chosen language): "Do you want the terminal tab to show the conversation topic instead of the Claude Code version?" yes | no. On yes: `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/titulo_terminal.py aplicar` (the only writer of editor settings; never edit them by hand). Summarize its JSON: editors changed, editors kept and why (`valor_do_dono` = owner's own value, `ilegivel` + `erro`), and, if `terminal_atual.tipo` is `jetbrains`, that the tab is renamed by hand (right click, Rename).

## (i) Close

1. Update `~/.config/tune-up/user.json`: only `tools` (from c-f) and `setup_done: true`. Show the two keys before writing.
2. Ask the user to type `/reload-plugins` (and restart Claude Code if step d changed `env`).
3. End with a table in the chosen language: step | done / skipped / failed | note (one line). Include the `!` commands still waiting for the user. If step h ran, note: undo with `/tune-up:terminal-title undo`.
