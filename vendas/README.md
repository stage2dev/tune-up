# tune-up-vendas

A WhatsApp sales module for the [tune-up](../README.md) panel. It has two parts:

- a **panel screen** (`painel/modulos/vendas/modulo.py`, screen id `vendas`) that shows the connection, the conversations and the sending state;
- a **local service** (`servico/`, Python 3.9 standard library only) that holds the WhatsApp connection and the data, listening on `127.0.0.1` only.

Status: 0.1.0 is a skeleton. The screen has one tab, "Conexão", that says whether the service is running (from its heartbeat in the database) and, when it is stopped, shows the exact command to start it. The service runs and receives webhooks, but has no WhatsApp connection yet.

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

Routes:

| Route | Rule |
|---|---|
| `GET /saude` | health, no secrets |
| `GET /token-de-envio` | returns the send token only when `Origin` is exactly the `--painel` origin; any other origin or no `Origin` = 403. `OPTIONS` and CORS only for that origin |
| `GET /estado` | requires header `X-Vendas-Token` (compared in constant time); webhook mode and counters |
| `POST /webhook/<instance>` | JSON only, 1 MB limit; secret in header `X-Vendas-Segredo` (constant-time compare). Mode `registra_e_conta` (default) accepts and counts valid/invalid; mode `recusa` answers 401 to a wrong secret. The raw event goes to the `eventos` table |

`Host` must be `127.0.0.1` or `localhost` (and the service port); `host.docker.internal` is accepted only on the webhook route. Nothing from a request is written to logs.

The send token is new on every start and stored 0600 in the data folder (deleted on clean stop); the webhook secret is kept 0600 in the data folder across restarts. The panel screen never reads either file.

## Where data lives

Outside the project tree, in an external data folder, one subfolder per project (a hash of the project path):

- macOS: `~/Library/Application Support/tune-up-vendas/<hash>/`
- Linux: `$XDG_DATA_HOME/tune-up-vendas/<hash>/` (default `~/.local/share`)

The folder is mode 0700 and its files 0600. Keys, tokens and contact data never go inside the project, logs or route replies. Folders synced by tools such as Syncthing are refused.

## Rules to add to the project

The module declares these in `INFO["negar"]` and the panel joins them into the deny rules of every session it starts:

- `Bash(*127.0.0.1:8791*)` and `Bash(*localhost:8791*)` (default service port)
- `Bash(*/api/modulos/*/acao*)` (the panel's action route)
- `Bash(*tune-up-vendas*)`, `Read(*tune-up-vendas*)`, `Edit(*tune-up-vendas*)`, `Write(*tune-up-vendas*)` (data folder and service)
- `Bash(*security find-generic-password*)` (macOS keychain)

Sessions you start by hand do not go through the panel, so also add the same rules as "ask" rules in the project's `regras_bash`, for example:

```json
{ "regras_bash": [
  { "regex": "127\\.0\\.0\\.1:8791|localhost:8791", "acao": "perguntar", "msg": "Sales service port." },
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
