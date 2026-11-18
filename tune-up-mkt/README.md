# tune-up-mkt

Marketing module for [tune-up](../README.md): guided connection of your own marketing accounts, campaign, content, SEO and preflight skills, and a guard that blocks or asks before writes to ad accounts and public posts.

Status: 0.3.0: guard + guided account connection + campaign, content, SEO and preflight skills; the panel tab arrives next.

## Install

Nothing to install: this module comes with the `tune-up` plugin. Its skills are `/tune-up:connect`, `/tune-up:campaign`, `/tune-up:content`, `/tune-up:seo` and `/tune-up:preflight`. The separate `tune-up-mkt` plugin was removed from the marketplace in 2.19.0; if you installed it, uninstall it (`/plugin uninstall tune-up-mkt@tune-up`).

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

You run the install commands yourself in your terminal (or the assistant runs one only after your explicit yes for that exact command); a piped remote script such as `curl ... | sh` is shown with its documentation link, never run by the assistant. Several install commands change your user-level Claude configuration (`--scope user`, plugin installs).

State lives in your project: `.tune-up/mkt/contas.json` and `.tune-up/mkt/config.json`. No secrets are stored.

- `estado` is the connection, from the checks the catalog marks as deciding (for example the OpenSEO MCP server; for Composio either the CLI or the MCP server is enough; the Anthropic plugin's own connectors only inform). `conta` says whether the account itself was checked: `conferida` (a free read by the session), `confirmada_pelo_dono`, `conferir_de_novo` (older than 7 days), `nao_conferida`, `nao_se_aplica`. `falta` lists what is not connected first, then connected services whose account still needs a check; it asks for a `status` when the last one is missing or older than 24 hours.
- `config --canais` accepts only `metaads`, `googleads`, `instagram`, `facebook`, `seo`, `video`, `voz`; `--site` only `http(s)://host[/path]` without `?` or `#`.
- IndexNow: `config --gerar-indexnow` creates the key (public by design: it is published at your site root). Never put any other key in this field.
- Checks run in the project folder, so project-scoped servers count. State files reached through a symbolic link are refused.
- Limit: when a check command times out, only that command is stopped; programs it started may keep running.

## Skills

| Skill | What it does | Say, for example |
| --- | --- | --- |
| `connect` | Guided connection of your marketing accounts | "connect my marketing accounts" |
| `campaign` | Reads campaign results and plans or adjusts campaigns; the analysis always ends in a marketing action | "analyze my Meta campaign", "plan a campaign for the launch" |
| `content` | Plans and writes posts, captions, scripts and email copy | "write a week of Instagram posts" |
| `seo` | Keyword research, site audit and rank tracking | "audit my site's SEO", "find keywords for this page" |
| `preflight` | GO/NO-GO checklist before any paid media | "run preflight before I launch this ad" |

Rules shared by the work skills:

- Each one first checks `.tune-up/mkt/contas.json` and sends you to `connect` when a service it needs is missing.
- Any write to an ad or a public post happens only on the owner's explicit request in the current turn; anything created is created paused, with a budget cap.
- `preflight` runs before any paid media; a NO-GO blocks the launch.
- No invented social proof, scarcity, urgency or price.
- The brand is read through the tune-up-studio `marca-ler` rule (approval from the panel); an unapproved kit is only a draft; without tune-up-studio there is no kit, so the skill asks for tone and colours and marks them as a draft. Producing the pieces is started by the owner from the tune-up panel (Studio tab); the skills never invoke `post`, `video` or `anuncio` themselves.
- Before ANY call that spends money or credits, the skill estimates the total for the task in the service's own unit and asks when the service bills in money, the free balance does not renew, or the estimate in credits is above `credit_ask_above` (in `config.json`, default 2000; set with `contas.py config --credit-ask-above N`). Unsure of the price: it asks.
- `preflight`: all 9 items block (a fail or "not checked" = NO-GO); the GO holds only for the ad as checked, and it never fires real events.
- Raw data and backups are saved under `.tune-up/mkt/bruto/` with personal data and tokens removed; do not commit it (add it to `.gitignore`).

## What costs money

The module itself never spends. What can cost money are the services it connects to:

- Higgsfield: needs a paid subscription and every generation spends credits, with no hard cap.
- ElevenLabs: generating speech spends credits.
- Ad spend on Meta and Google Ads, charged by those platforms.
- OpenSEO: free plan with a one-time US$0.50 credit that does not renew; then paid plans, and a keyword lookup is about US$0.05.
- Composio: Hobby plan US$0 (100k tool calls per month); Pro is US$29/month.

Prices come from `servicos.json` (`custo_aviso`) and can change; check each provider's pricing page.

## Guard

A `PreToolUse` hook (`tune-up-mkt/scripts/guarda_mkt.py`, registered in the core plugin's `hooks/hooks.json`) checks shell commands (Bash, PowerShell, Monitor), every MCP tool call and writes to the loosening file. Defaults:

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

- It runs through Python and fails open (the action goes through) when the hook times out or hits an internal error. With no Python 3.9+ found, the launcher (`scripts/py`) prints a message and exits 127 for this script: Claude Code shows a hook error and the tool call goes through.
- Covered shapes include dedicated MCP servers by name (`meta-ads`, `fb-ads`, `facebook`, `instagram`, `google-ads`, also with a suffix such as `meta-ads-mcp`, ...), remote bash/workbench tools of any server, `composio.cmd`/`.exe`/quoted/path forms, and Graph API writes through PowerShell `-Method Post`/`-Body`, `requests.post`, `fetch`, `curl --json`, `wget --post-data` and httpie.
- Bash heredoc bodies are skipped (an unterminated marker means the whole command is read); PowerShell commands are read whole.
- Not covered: `sh -c`/`eval` indirection, a heredoc fed to an interpreter, Python/Node files on disk, a globbed name like `mk?.json`. A server that hides tool slugs inside code is only caught by keywords. A write to an existing ad addressed only by its numeric id is treated as another Graph path (ask, not block).
- The core `tune-up` plugin only asks (it does not deny) on writes under `~/.config/tune-up/`.

## Limits

- The guard is best effort and fails open without Python 3.9+ (see Guard).
- The panel never connects an account: OAuth needs an interactive session, so connecting happens in the `connect` skill.
- The output formats of `claude mcp list`, `claude plugin list --json` and `composio connections list` are undocumented; output the checks do not recognize is recorded as `nao_sei`.
- claude-ads is a development candidate, qualified only for Linux x86_64.
- Meta Ads in Composio has no managed app (bring your own Meta app); Google Ads needs a developer token.
- No automatic posting or scheduling by the module; scheduling counts as publishing and happens only on the owner's request in the current turn.

## License

MIT, see [LICENSE](LICENSE).
