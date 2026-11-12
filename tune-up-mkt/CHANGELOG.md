# CHANGELOG - tune-up-mkt

## 0.1.0

- Plugin skeleton: manifest, license, README, the portable Python launcher (`scripts/py`) and a test that checks the folder contains nothing specific to a private project. No guard, skills or panel tab yet.
- Marketing guard (`PreToolUse` hook, `scripts/guarda_mkt.py`): blocks Meta ad writes through the API, asks before Google Ads changes, public posts, `composio run` and edits to `mkt.json`; checks Bash, PowerShell, Monitor and any MCP server; messages in English or pt-BR from `user.json`; per-project loosening down to "ask" in `~/.config/tune-up/mkt.json`.
