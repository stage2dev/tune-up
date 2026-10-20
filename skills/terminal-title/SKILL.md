---
name: terminal-title
description: "Make the VS Code-family terminal tab (VS Code, Cursor, Windsurf, Antigravity, VSCodium) show the conversation title instead of the Claude Code version. Use on: terminal tab title, undo terminal title; título da aba do terminal, desfazer."
argument-hint: "[undo]"
allowed-tools: Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info), Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/titulo_terminal.py"), Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/titulo_terminal.py" aplicar), Bash(python3 "${CLAUDE_PLUGIN_ROOT}/scripts/titulo_terminal.py" desfazer)
---

# Terminal title

Argument: $ARGUMENTS (`undo` / `desfazer` = remove the setting tune-up added)

Context: !`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/guarda.py" info`

Fields: `language`, `owner`, `reply_style`. Reply in `language`, in the `reply_style` format. Call the user `owner`. If the JSON did not load, run the command once with Bash.

## Why

VS Code-family editors name the terminal tab after the running process. The Claude Code executable is named after its version, so the tab reads `2.1.304`. The setting `terminal.integrated.tabs.title` = `${sequence}${separator}${process}` puts the title Claude Code writes first, e.g. `✳ Fix login - 2.1.304`.

## Steps

1. `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/titulo_terminal.py"` lists the editors found and changes nothing.
2. Run it again with `aplicar` (or `desfazer` when the argument asks to undo). It edits only each editor's user `settings.json` (and its profiles), saves `settings.json.bak-tune-up` first, never replaces a value the owner chose, and leaves an unreadable file untouched.
3. Do not edit any editor settings by hand: the script is the only writer.

## Read the JSON

| Field | Meaning |
|---|---|
| `editores[].antes` / `depois` | `falta` (missing), `aplicado` (set by tune-up), `valor_do_dono` (owner's own value, kept; shown in `valor`), `sem_arquivo` (no settings file yet), `ilegivel` (could not read or edit; see `erro`) |
| `terminal_atual.tipo` | `vscode`: the change applies here. `jetbrains`: not covered, the owner renames the tab by hand (right click on the tab). `outro`: standalone terminals (iTerm2, Ghostty, Terminal, Windows Terminal) already show the title Claude Code writes |
| `titulo_do_claude_desligado` | `true` = `CLAUDE_CODE_DISABLE_TERMINAL_TITLE` is set, so Claude Code sends no title and the tab stays the process name until the owner removes it |
| `editores` empty | No VS Code-family editor found in the user config folder (portable install or custom `--user-data-dir`): say so |

## Answer

Which editors changed and which were left as they were (and why), then: open a new terminal tab to see it; if the tab still shows only the number, rename it by hand (right click on the tab, Rename). To revert: run this skill with `undo`.
