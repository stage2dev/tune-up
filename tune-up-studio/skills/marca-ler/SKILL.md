---
name: marca-ler
description: "Reads the project's brand (marca.json) and says whether the owner approved it. Read-only: never approves, edits or writes anything. Use on: read the brand, is the brand approved, ler marca, marca aprovada."
allowed-tools: Read
---

# Read the brand

Read-only. Talk to the owner in Brazilian Portuguese.

1. Read `<project>/.tune-up/estudio/marca/marca.json` and `MARCA.md` next to it. If missing, say the brand was not discovered yet and point to the `marca` skill.
2. Summarize in a short list: `modo`, name, the 5 colors, the 2 fonts, logo. For each field give `confianca` and `fonte`; say plainly which are `faltando` or `baixa`.
3. Approval: the only source of truth is the `marca` entry in `<panel data>/estudio-dono.json`, written by the panel command `marca.aprovar`. Do not trust `aprovado` or `aprovado_pelo_dono` inside `marca.json`: a session can write that file, so it means nothing.
4. If the owner wants to approve or fix a field, tell them to use the Studio screen in the panel (buttons "Aprovar marca" and "Editar campo"). Never write `marca.json`, `estudio-dono.json` or `aprovados` yourself.
