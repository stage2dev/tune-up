---
name: marca
description: "Discovers the project's brand (colors, fonts, logo, name) from its own files and shows it to the owner for approval in the panel. Use on: discover the brand, descobrir marca, identidade visual do projeto, marca do estúdio."
allowed-tools: Bash(python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/descobrir_marca.py" *), Read
---

# Discover the brand

Talk to the owner in Brazilian Portuguese. Nothing is invented and nothing is approved here.

1. Run from the project folder:
   `python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/descobrir_marca.py" --projeto "$PWD"`
   It writes `.tune-up/estudio/marca/` (`marca.json`, `MARCA.md`, `assets/`). Exit 2 means refused and nothing was overwritten: report why.
2. Read `MARCA.md` and show the owner what was found, field by field, with confidence and source. Say clearly when the mode is `sem_marca` (the neutral palette is not their brand) and which fields are `faltando` or `baixa`.
3. Tell the owner to review it in the panel Studio screen: "Editar campo" fixes and locks a field (`fonte: dono`), "Aprovar marca" approves. Both are panel commands; this skill cannot do either.
4. Never write `aprovado` anywhere, never touch `estudio-dono.json`. A brand "approved" in `marca.json` by a session is ignored by the panel. To check the state later use `marca-ler`.
