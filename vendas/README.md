# tune-up-vendas

A WhatsApp sales module for the [tune-up](../README.md) panel. It has two parts:

- a **panel screen** (`painel/modulos/vendas/modulo.py`, screen id `vendas`) that shows the connection, the conversations and the sending state;
- a **local service** (`servico/`, Python 3.9 standard library only) that holds the WhatsApp connection and the data, listening on `127.0.0.1` only.

Status: 0.1.0 is a skeleton. The screen has one tab, "Conexão", that tells you the service is not running. The service itself arrives in later versions.

## Enable it in a project

1. Install the plugin from the marketplace (`tune-up-vendas`).
2. In the project's `.tune-up/painel.json`, opt in by the exact plugin and marketplace names:

   ```json
   { "modulos_de_plugins": ["tune-up-vendas@<marketplace>:vendas"] }
   ```

   Enabling it runs this plugin's Python code inside the panel process, so only enable plugins you trust.

## Starting the service

The service starts **only** by an owner command typed in a terminal. It never starts from a Claude session, from a panel action or from a hook. The panel screen shows the command to copy. The deny rules below make a session unable to start it or to reach it.

Placeholder until the service exists: `python3 <plugin folder>/servico/iniciar.py`.

## Where data lives

Outside the project tree, in an external data folder, one subfolder per project (a hash of the project path):

- macOS: `~/Library/Application Support/tune-up-vendas/<hash>/`
- Linux: `$XDG_DATA_HOME/tune-up-vendas/<hash>/` (default `~/.local/share`)

The folder is mode 0700 and its files 0600. Keys, tokens and contact data never go inside the project, logs or route replies. Folders synced by tools such as Syncthing are refused.

## Rules to add to the project

The module declares these in `INFO["negar"]` and the panel joins them into the deny rules of every session it starts:

- `Bash(*127.0.0.1:8791*)` and `Bash(*localhost:8791*)` (service port; placeholder until the service exists)
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
