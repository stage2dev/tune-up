# CHANGELOG - tune-up-mkt

## Shipped inside tune-up 2.19.0

- No separate plugin any more. The skills are `/tune-up:connect`, `/tune-up:campaign`, `/tune-up:content`, `/tune-up:seo` and `/tune-up:preflight`. The guard runs from the core hooks. The error log is `erros-mkt.log`.

## 0.3.0

- S1: skills `campaign`, `content`, `seo` and `preflight` (generic, English, replying in the profile language). Each first checks `.tune-up/mkt/contas.json` and sends you to `connect` when a needed service is missing. Rules: campaign analysis ends in a marketing action; writes to an ad or public post only on the owner's explicit request in the current turn; everything created paused with a budget cap; preflight GO/NO-GO before paid media; no invented social proof, scarcity, urgency or price; brand from the tune-up-studio kit when present; credit estimate and ask above `credit_ask_above`.
- S1-fix: review findings closed in the four work skills (credit rule in the service's own unit, studio panel pointers, brand approval via `marca-ler`, all-blocking preflight, no real effects, stale state, scheduling only on the owner's request in the current turn (it counts as publishing), raw-data hygiene, prompt-injection line, live edits, IndexNow scope and responses).
- S2: README sections Skills, What costs money and Limits; status line and root README line updated.

## 0.2.0

- B1: anonymized fixtures of real `claude plugin list --json`, `claude mcp list` and `composio connections list` outputs in `tests/fixtures/` (scenarios on/off/missing/unknown format, all statuses `claude mcp list` can show, measured durations), with a README that marks which statuses were observed and which come only from the docs.
- B2: `servicos.json`, the declarative catalog of the 9 marketing services (what each is for, how to install and authenticate, cost notice, read-only checks, doc link, check date, and the facts still uncertain), with Composio channels (Meta Ads, Google Ads, Instagram, Facebook), plus `tests/test_servicos.py` that checks its schema.
- B3: `scripts/contas.py` (+ `contas_regras.py`), a read-only check of which services are connected: runs `claude plugin list --json`, `claude mcp list` and `composio connections list` in parallel, classifies each service and Composio channel (`ligado`, `falta_autenticar`, `nao_instalado`, `desligado`, `falhou`, `nao_sei`, `conferir_de_novo`) and writes `.tune-up/mkt/contas.json` (atomic, 0600) with only the classified state; `marcar` records session-only checks valid for 7 days, `falta` gives the next step from the catalog, `config` writes `.tune-up/mkt/config.json`; secret-looking values and e-mails are refused with exit 2.
- B review: checks run in the project folder; the catalog says which checks decide (`papel`) and whether any path is enough (`modo`); exact plugin ids and MCP server names (or URL host); separate `conta` field for the account check; marks merged under a lock; symlinked state files refused; strict `--site`/`--canais`; `config --gerar-indexnow`; argument errors never echo values; `falta` rebuilds from a recent `status` (file side split into `contas_arquivos.py`).
- B4: `connect` skill: guided, one-service-at-a-time connection of the owner's own marketing accounts (no credentials in the chat, explicit yes before any cost, read-only checks recorded through `contas.py`); README section.

## 0.1.0

- Plugin skeleton: manifest, license, README, the portable Python launcher (`scripts/py`) and a test that checks the folder contains nothing specific to a private project. No account connection, skills or panel tab yet.
- Marketing guard (`PreToolUse` hook, `scripts/guarda_mkt.py`): blocks Meta ad writes through the API, asks before Google Ads changes, public posts, `composio run` and edits to `mkt.json`; checks Bash, PowerShell, Monitor and any MCP server; messages in English or pt-BR from `user.json`; per-project loosening down to "ask" in `~/.config/tune-up/mkt.json`.
