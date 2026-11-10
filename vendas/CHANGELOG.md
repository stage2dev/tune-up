# CHANGELOG - tune-up-vendas

## 0.1.0

- Plugin skeleton: manifest, license, README, a panel module `vendas` with one tab ("Conexão") that says the service is not running, and tests. No WhatsApp code yet.
- Service storage: `servico/pasta.py` (data folder outside the project, refuses a folder inside the project root or under a synced folder with `.stfolder`/`.stignore`; 0700/0600 on POSIX), `servico/banco.py` (SQLite WAL, migrations by `user_version`, unique `id_externo`, partial unique `chave_dedupe` that ignores `negado`) and `servico/telefone.py` (Brazilian 9th-digit variants, rejects `@lid`).
