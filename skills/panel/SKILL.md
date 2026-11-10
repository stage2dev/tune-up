---
name: panel
description: "Starts the local tune-up panel (web dashboard) for this project: phases and Parts, running Claude sessions with their sub-agents, model and effort, buttons that launch background sessions, and project modules. Use on: open the panel, dashboard, painel, abre o painel, quero ver os agentes."
allowed-tools: Bash(python3 -B "${CLAUDE_PLUGIN_ROOT}/painel/painel.py" *)
---

# Panel

The panel is a local web page served only on `127.0.0.1`. It reads the project; it changes nothing by itself.

1. Start it in the background from the project folder:
   `python3 -B "${CLAUDE_PLUGIN_ROOT}/painel/painel.py" --projeto "$PWD" --port 8787`
   If the port is busy, try 8788, 8789.
2. Give the owner the address (`http://127.0.0.1:<port>`) and stop. Do not open sessions or click buttons for them.

What the owner needs to know, in one or two lines:
- Buttons launch `claude --bg` sessions from a closed list of actions (`painel/acoes/*.json` plus the project's own). Each action carries its own tool rules.
- Project settings live in `<project>/.tune-up/painel.json` (all optional). `"pular_permissoes": true` launches every session with `--dangerously-skip-permissions`; deny rules and action hooks still apply, ordinary permission prompts do not. It is off by default; turning it on is the owner's decision.
- Project screens and actions go in `<project>/.tune-up/painel-projeto/` (see `painel/README.md`).

The panel UI and its README are in Portuguese for now. It needs Python 3.9+; the screens are prebuilt in `painel/web/dist` (Node is only needed to rebuild). macOS and Linux only: the launcher uses file locks that Windows lacks.
