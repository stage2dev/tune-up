# tune-up-mkt

Marketing module for [tune-up](../README.md): guided connection of your own marketing accounts, campaign, content, SEO and preflight skills, and a guard that blocks or asks before writes to ad accounts and public posts.

Status: 0.2.0: guard + guided account connection (`connect`); campaign, content, SEO and preflight skills and the panel tab arrive in the next releases.

## Install

```
/plugin marketplace add stage2dev/tune-up
/plugin install tune-up-mkt@tune-up
```

Requires the core `tune-up` plugin.

## Connect your accounts

The `connect` skill (say "connect my marketing accounts") walks you through the services below one at a time: what each is for, what it costs, the sign-up link, the install commands and how to authorize. You create the accounts and authorize in the browser; the assistant never types credentials or asks you to paste a key, token or password in the chat. It checks each connection with free read-only calls and records the result through `scripts/contas.py`. Anything that costs money or credits waits for your explicit yes.

| Service | Level | What for |
| --- | --- | --- |
| Claude in Chrome | base | Drive your logged-in browser to read and change ad managers and dashboards |
| Composio | base | Meta Ads, Google Ads, Instagram and Facebook through one login (per-channel connections) |
| OpenSEO | base | Keyword research, rank tracking and site audits |
| Search Console analytics | per channel | Real search queries and traffic for your site inside OpenSEO |
| IndexNow | per channel | Tell search engines right away when a page changes |
| claude-ads | optional | Ad audit and planning skills driven by exported data |
| Anthropic marketing | optional | Content, campaign planning, brand review, SEO audit, email sequences |
| Higgsfield | optional | Images and video for ad creative |
| ElevenLabs | optional | Voice-over and transcription for ad creative |

State lives in your project: `.tune-up/mkt/contas.json` (connection state per service; manual marks expire after 7 days) and `.tune-up/mkt/config.json` (site, channels, settings). No secrets are stored. The IndexNow key is public by design: it is published at your site root.

## Guard

A `PreToolUse` hook (`scripts/guarda_mkt.py`) checks shell commands (Bash, PowerShell, Monitor), every MCP tool call and writes to the loosening file. Defaults:

| Action | Default | Policy key |
| --- | --- | --- |
| Write to a Meta ad object (campaign, ad set, ad, creative, budget, audience) through the API, CLI or a Graph API call | block: do it in Ads Manager in the browser, on the owner's explicit request | `meta_ads_write` |
| Google Ads change (mutate, create, update, remove, pause, enable) | ask | `google_ads_write` |
| Public post on Facebook or Instagram | ask | `organic_publish` |
| `composio run` (runs a file the guard cannot read), or `composio execute` whose slug is not written out (`$S`, `xargs`) | ask | fixed |
| Any command or file write that names `mkt.json` | ask | fixed |
| Reads (get, list, search, insights) and everything else | pass | - |

Messages follow `language` (`en` or `pt-BR`) and `owner` in `~/.config/tune-up/user.json`; without them, English and "the owner".

Loosen per project in `~/.config/tune-up/mkt.json`. The project is `CLAUDE_PROJECT_DIR` (never the tool's working folder); without it the defaults apply.

```json
{"projetos": {"/absolute/path/to/your/project": {"meta_ads_write": "ask"}}}
```

Accepted values are `deny` and `ask` only: loosening goes down to "ask" at most, never to "pass", and `ask` can be tightened to `deny`. Any other value, an unreadable or invalid file, a relative path (key or `CLAUDE_PROJECT_DIR`), or a project not listed keeps the default. A loosened decision says so and names the file.

The guard is best effort, not a security boundary:

- It runs through Python and fails open (the action goes through) when no Python 3.9+ is found or the hook times out, the same as the core plugin's guards.
- Covered shapes include dedicated MCP servers by name (`meta-ads`, `fb-ads`, `facebook`, `instagram`, `google-ads`, also with a suffix such as `meta-ads-mcp`, ...), remote bash/workbench tools of any server, `composio.cmd`/`.exe`/quoted/path forms, and Graph API writes through PowerShell `-Method Post`/`-Body`, `requests.post`, `fetch`, `curl --json`, `wget --post-data` and httpie.
- Bash heredoc bodies are skipped (an unterminated marker means the whole command is read); PowerShell commands are read whole.
- Not covered: `sh -c`/`eval` indirection, a heredoc fed to an interpreter, Python/Node files on disk, a globbed name like `mk?.json`. A server that hides tool slugs inside code is only caught by keywords. A write to an existing ad addressed only by its numeric id is treated as another Graph path (ask, not block).
- The core `tune-up` plugin only asks (it does not deny) on writes under `~/.config/tune-up/`.

## License

MIT, see [LICENSE](LICENSE).
