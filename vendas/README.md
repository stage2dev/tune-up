# tune-up-vendas

A WhatsApp sales module for the [tune-up](../README.md) panel. It has two parts:

- a **panel screen** (`painel/modulos/vendas/modulo.py`, screen id `vendas`) that shows the connection, the conversations and the sending state;
- a **local service** (`servico/`, Python 3.9 standard library only) that holds the WhatsApp connection and the data, listening on `127.0.0.1` only.

Status: 0.1.0 is a skeleton. The screen has one tab, "Conexão", that says whether the service is running (from its heartbeat in the database) and, when it is stopped, shows the exact commands to start it and to prepare the local Evolution API. The service runs and receives webhooks, but has no WhatsApp connection flow (QR) yet.

## Enable it in a project

1. Install the plugin from the marketplace (`tune-up-vendas`).
2. In the project's `.tune-up/painel.json`, opt in by the exact plugin and marketplace names:

   ```json
   { "modulos_de_plugins": ["tune-up-vendas@<marketplace>:vendas"] }
   ```

   Enabling it runs this plugin's Python code inside the panel process, so only enable plugins you trust.

## Starting the service

The service starts **only** by an owner command typed in a terminal. It never starts from a Claude session, from a panel action or from a hook. The panel screen shows the command to copy. The deny rules below make a session unable to start it or to reach it.

```
python3 -B <plugin folder>/servico/servico.py --projeto <project root> [--porta 8791] [--painel http://127.0.0.1:8787]
```

- Listens on `127.0.0.1` only (default port 8791). No daemon: it runs in that terminal and stops cleanly on Ctrl+C or SIGTERM.
- One service per project: a non-blocking exclusive lock on `servico.trava` in the data folder. A second start exits with code 3 and a clear message. A data folder inside the project or under a synced folder exits with code 2.
- `--painel` is the panel's exact origin (scheme, host and port). Only that origin gets the send token.
- Writes a heartbeat to the database every 3 s; the screen shows "Serviço parado" when the heartbeat is missing or older than 15 s.
- On start it records its real port and the project marker (the data-folder hash) in its database. It also stores a fingerprint (sha256 prefix) of the webhook secret: when the secret is new or changed, the consecutive-valid counter goes back to 0 and a `recusa` mode goes back to `registra_e_conta`, with a notice on stderr.
- On start it prints a notice on stderr when the Evolution `.env` exists but is incomplete or unreadable, or when no connector is configured (sending stays off, `POST /enviar` answers 503).

Routes:

| Route | Rule |
|---|---|
| `GET /saude` | health, no secrets; includes `marca`, the project marker (data-folder hash) |
| `GET /token-de-envio` | returns the send token only when `Origin` is exactly the `--painel` origin; any other origin or no `Origin` = 403. `OPTIONS` and CORS only for that origin |
| `GET /estado` | requires header `X-Vendas-Token` (compared in constant time); webhook mode and counters |
| `POST /modo-webhook` | requires `X-Vendas-Token`; JSON `{modo}` with `registra_e_conta` or `recusa`. `recusa` answers 409 until 20 consecutive valid webhooks were received (an invalid one resets the count); going back to `registra_e_conta` is always allowed |
| `POST /enviar` | requires `X-Vendas-Token`; JSON `{telefone, texto, id_tela, confirmar_optout}`. Always origin `manual` (an `origem` field in the body is ignored) and always through the send gate. Replies `{estado, motivo, envio_id}`; 503 when the Evolution connector or the instance is not configured |
| `POST /webhook/<instance>` | JSON only, 1 MB limit; secret in header `X-Vendas-Segredo` (constant-time compare). Mode `registra_e_conta` (default) accepts and counts valid/invalid; mode `recusa` answers 401 to a wrong secret. The raw event goes to the `eventos` table; a valid webhook is counted only in the same transaction that stored its event |

`Host` must be `127.0.0.1` or `localhost` (and the service port); `host.docker.internal` is accepted only on the webhook route. Nothing from a request is written to logs.

The screen ("Conexão" tab, while the service runs) shows the webhook mode, the valid, invalid and consecutive-valid counters and a form to switch the mode. The form calls the module action `modo_webhook`. Every module action goes through `painel/modulos/vendas/cliente.py`: it reads the port from this project's database (read-only), refuses when the heartbeat is stale, checks that `GET /saude` returns this project's marker (so it never acts on another project's service on that port), then asks for the send token as the panel origin and posts to `POST /modo-webhook`; the 20-valid rule is enforced by the service, and the token never comes back in the action result.

The send token is new on every start and stored 0600 in the data folder (deleted on clean stop); the webhook secret is kept 0600 in the data folder across restarts. The panel screen never reads either file.

## Local Evolution API (Docker)

The WhatsApp connection runs in a local Evolution API v2 (Docker). Prepare its files once per project:

```
python3 -B <plugin folder>/servico/evolution_local.py preparar --projeto <project root> [--porta 8791] [--porta-evolution 8080]
```

- Writes `compose.yml` and `.env` into `<data folder>/evolution/` (the external data folder below, never the project root; a target inside the project or under a synced folder is refused with exit code 2).
- `.env` is mode 0600 and holds an API key and a Postgres password generated on the spot. The public default key of the Evolution examples is never used. An existing `.env` is never overwritten unless you pass `--refazer`, which rotates only the API key and keeps the existing `POSTGRES_PASSWORD` (Postgres keeps the password of its first start). A new database password needs `--refazer --senha-nova`, and then the old Postgres volume must be removed.
- `compose.yml` runs Evolution API v2.3.7, Postgres 15 and Redis 7. Only the Evolution port is published, bound to `127.0.0.1` (default 8080); Postgres and Redis publish nothing. Telemetry and the global webhook are off.
- It prints the command to start the containers, `docker compose -f <data folder>/evolution/compose.yml up -d`, and never runs Docker itself.
- The service reads the Evolution URL (`SERVER_URL`) and key from that `.env` when `VENDAS_EVOLUTION_URL` / `VENDAS_EVOLUTION_CHAVE` are not set in its environment. It registers each instance's webhook as `http://host.docker.internal:<service port>/webhook/<instance>` with the secret in the `X-Vendas-Segredo` header, so start the service with the same `--porta` you gave `preparar`.

**Linux limitation:** the compose maps `host.docker.internal` to the host gateway (`host-gateway`), but on Linux that is the Docker bridge address, and the service listens on `127.0.0.1` only, so the webhook may not reach it. This first release targets macOS only (the compose file was validated with `docker compose config` on macOS with colima; delivery from a running container to the service was not tested end to end). On Linux, the webhook path is not supported yet.

## Send gate

`servico/portao.py` is the only code that calls a connector's `enviar_texto`/`enviar_audio` (a test scans the source and fails otherwise). Each origin has its own function, so the origin comes from the action, never from a request body:

| Origin | Opt-out | Human pause | Window 09-19 | Rate | Dedupe key |
|---|---|---|---|---|---|
| `manual` | needs `confirmar_optout=True` | no | no | 8/min | screen id per click |
| `rascunho_aprovado` | denied | no | no | 8/min | draft id |
| `ia` | denied | denied | no | 8/min, 200/h | conversation + trigger message id + bubble |
| `campanha` | denied | denied | denied outside | 8/min, 200/h, new contacts/day hook | campaign + contact + step |
| `audio_ia` | denied | denied | no | 8/min, 200/h, audio/day (config `teto_audio_dia`, default 20) | the `ia` key + `audio` |
| `teste_audio` | no | no | no | 5/day, only to config `numero_dono` | screen id |
| `confirmacao_sair` | allowed only after opt-out | no | no | 1 per contact | contact |

- The window uses config `fuso` (`-03:00` or an IANA name; unset = the machine's zone; invalid = denied).
- The reservation runs in `BEGIN IMMEDIATE` and re-checks opt-out, pause and limits at send time. The `envios` row is written as `pendente` before the connector call, then becomes `enviado` (with `id_externo`), `falhou` (surely not sent) or `incerto` (may have been sent).
- `negado` rows carry the reason and do not hold the dedupe key; a key already held returns `duplicado` without a new row or a connector call.
- On start, every `pendente` row becomes `incerto`. Nothing is resent automatically; `portao.reenviar()` (an explicit owner action) moves the same row back to `pendente` after re-checking the rules.
- The daily new-contacts limit for campaigns is a hook (`teto_contatos_novos`) that returns no limit for now; the daily counter (`contatos_novos_no_dia`) is in place.

## Where data lives

Outside the project tree, in an external data folder, one subfolder per project (a hash of the project path):

- macOS: `~/Library/Application Support/tune-up-vendas/<hash>/`
- Linux: `$XDG_DATA_HOME/tune-up-vendas/<hash>/` (default `~/.local/share`)
- Windows: `%LOCALAPPDATA%\tune-up-vendas\<hash>\`

On case-insensitive disks (the macOS and Windows defaults) the hash uses the lower-cased real path, so the same project opened with different letter case keeps one database.

The folder is mode 0700 and its files 0600. Keys, tokens and contact data never go inside the project, logs or route replies. Folders synced by tools such as Syncthing are refused.

## Rules to add to the project

The module declares these in `INFO["negar"]` and the panel joins them into the deny rules of every session it starts:

- `Bash(*127.0.0.1:8791*)` and `Bash(*localhost:8791*)` (default service port)
- `Bash(*127.0.0.1:8080*)` and `Bash(*localhost:8080*)` (default local Evolution port)
- `Bash(*/api/modulos/*/acao*)` (the panel's action route)
- `Bash(*tune-up-vendas*)` (data folder, service and `docker compose -f <data folder>/...`)
- `Bash(*docker exec*)`, `Bash(*docker inspect*)`, `Bash(*docker compose config*)` (they print the container environment, including the Evolution key and the Postgres password)
- `Bash(*security find-generic-password*)` (macOS keychain)
- `Read`, `Edit` and `Write` on the data folder, anchored on the real paths: `~/Library/Application Support/tune-up-vendas/**` (macOS), `~/.local/share/tune-up-vendas/**` (Linux) and `~/AppData/Local/tune-up-vendas/**` (Windows)

These rules use the default ports. If you start the service or the Evolution on another port (`--porta`, `--porta-evolution`), or set `XDG_DATA_HOME` / `LOCALAPPDATA` to another folder, add a matching rule yourself (for example `Bash(*127.0.0.1:9090*)` and `Bash(*localhost:9090*)`).

**What these rules are and are not.** The deny rules and the `Origin` check on `GET /token-de-envio` are an extra layer against accidents (a session reading a file or calling the service by mistake, a transcript, a synced folder). They are **not** protection from a local process of the same user: any program you run, or a session with unrestricted Bash (for example with `pular_permissoes: true`), can read the data folder and call the service.

Sessions you start by hand do not go through the panel, so also add the same rules as "ask" rules in the project's `regras_bash`, for example:

```json
{ "regras_bash": [
  { "regex": "127\\.0\\.0\\.1:(8791|8080)|localhost:(8791|8080)", "acao": "perguntar", "msg": "Sales service or Evolution port." },
  { "regex": "docker\\s+(exec|inspect|compose\\s+config)", "acao": "perguntar", "msg": "Docker command that prints secrets." },
  { "regex": "/api/modulos/[^/ ]+/acao", "acao": "perguntar", "msg": "Panel action route." },
  { "regex": "tune-up-vendas", "acao": "perguntar", "msg": "Sales data folder or service." },
  { "regex": "security\\s+find-generic-password", "acao": "perguntar", "msg": "Keychain read." }
] }
```

## WhatsApp policy warning

Cold first-contact messaging (writing to people who never asked to hear from you) **violates the WhatsApp Business Policy** and can get the number banned. This module only allows it with `"numero_descartavel": true`, meaning a throwaway number you accept losing. Never use your real business number for it. Contact only people who gave you a legal basis to write, and honor every opt-out.

## Tests

```
cd vendas && python3 -B -m unittest discover -s testes -t .
```

## License

MIT, see `LICENSE`.
