# CHANGELOG - tune-up-mkt

## 0.2.0

- B1: anonymized fixtures of real `claude plugin list --json`, `claude mcp list` and `composio connections list` outputs in `tests/fixtures/` (scenarios on/off/missing/unknown format, all statuses `claude mcp list` can show, measured durations), with a README that marks which statuses were observed and which come only from the docs.
- B2: `servicos.json`, the declarative catalog of the 9 marketing services (what each is for, how to install and authenticate, cost notice, read-only checks, doc link, check date, and the facts still uncertain), with Composio channels (Meta Ads, Google Ads, Instagram, Facebook), plus `tests/test_servicos.py` that checks its schema.
- B3: `scripts/contas.py` (+ `contas_regras.py`), a read-only check of which services are connected: runs `claude plugin list --json`, `claude mcp list` and `composio connections list` in parallel, classifies each service and Composio channel (`ligado`, `falta_autenticar`, `nao_instalado`, `desligado`, `falhou`, `nao_sei`, `conferir_de_novo`) and writes `.tune-up/mkt/contas.json` (atomic, 0600) with only the classified state; `marcar` records session-only checks valid for 7 days, `falta` gives the next step from the catalog, `config` writes `.tune-up/mkt/config.json`; secret-looking values and e-mails are refused with exit 2.
- B4: `connect` skill: guided, one-service-at-a-time connection of the owner's own marketing accounts (no credentials in the chat, explicit yes before any cost, read-only checks recorded through `contas.py`); README section.

## 0.1.0

- Plugin skeleton: manifest, license, README, the portable Python launcher (`scripts/py`) and a test that checks the folder contains nothing specific to a private project. No account connection, skills or panel tab yet.
- Marketing guard (`PreToolUse` hook, `scripts/guarda_mkt.py`): blocks Meta ad writes through the API, asks before Google Ads changes, public posts, `composio run` and edits to `mkt.json`; checks Bash, PowerShell, Monitor and any MCP server; messages in English or pt-BR from `user.json`; per-project loosening down to "ask" in `~/.config/tune-up/mkt.json`.
