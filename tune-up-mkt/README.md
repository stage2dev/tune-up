# tune-up-mkt

Marketing module for [tune-up](../README.md): guided connection of your own marketing accounts, campaign, content, SEO and preflight skills, and a guard that blocks or asks before writes to ad accounts and public posts.

Status: 0.1.0: skeleton + guard; account connection, skills and panel tab arrive in the next releases.

## Install

```
/plugin marketplace add stage2dev/tune-up
/plugin install tune-up-mkt@tune-up
```

Requires the core `tune-up` plugin.

## Guard

A `PreToolUse` hook (`scripts/guarda_mkt.py`) checks shell commands (Bash, PowerShell, Monitor), every MCP tool call and writes to the loosening file. Defaults:

| Action | Default | Policy key |
| --- | --- | --- |
| Write to a Meta ad object (campaign, ad set, ad, creative, budget, audience) through the API, CLI or a Graph API call | block: do it in Ads Manager in the browser, on the owner's explicit request | `meta_ads_write` |
| Google Ads change (mutate, create, update, remove, pause, enable) | ask | `google_ads_write` |
| Public post on Facebook or Instagram | ask | `organic_publish` |
| `composio run` (runs a file the guard cannot read) | ask | fixed |
| Any command or file write that names `mkt.json` | ask | fixed |
| Reads (get, list, search, insights) and everything else | pass | - |

Messages follow `language` (`en` or `pt-BR`) and `owner` in `~/.config/tune-up/user.json`; without them, English and "the owner".

Loosen per project in `~/.config/tune-up/mkt.json`. The project is `CLAUDE_PROJECT_DIR` (never the tool's working folder); without it the defaults apply.

```json
{"projetos": {"/absolute/path/to/your/project": {"meta_ads_write": "ask"}}}
```

Accepted values are `deny` and `ask` only: loosening goes down to "ask" at most, never to "pass", and `ask` can be tightened to `deny`. Any other value, an unreadable or invalid file, or a project not listed keeps the default. A loosened decision says so and names the file.

The guard is best effort, not a security boundary:

- It runs through Python and fails open (the action goes through) when no Python 3.9+ is found or the hook times out, the same as the core plugin's guards.
- Bash heredoc bodies are skipped; PowerShell here-strings are not stripped the same way.
- A server that hides tool slugs inside code is only caught by keywords.
- The core `tune-up` plugin only asks (it does not deny) on writes under `~/.config/tune-up/`.

## License

MIT, see [LICENSE](LICENSE).
