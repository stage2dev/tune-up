---
name: connect
description: "Guides the owner through connecting their own marketing accounts one service at a time, checks each connection read-only and records the result. Use on: connect my marketing accounts, set up marketing, what is missing; conectar contas de marketing, cadastro, o que falta."
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py status), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py status *), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py marcar), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py marcar *), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py falta), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py falta *), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py config), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py config *)
---

# Connect marketing accounts

Reply in the `language` of `~/.config/tune-up/user.json` (English if missing) and call the user `owner`. The catalog is `${CLAUDE_PLUGIN_ROOT}/servicos.json`: take every text from it (use its `pt` text when the language is Portuguese). Never invent a price, a limit or a URL that is not in the catalog.

Commands below are all `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py <command>` (only these are pre-approved; anything else goes through the normal permission prompt).

Hard rules for the whole skill:
- The OWNER creates accounts and authorizes in the browser. You never create an account, never type credentials, and never ask the owner to paste a key, token, password or callback URL into the chat. If a service needs a key, the owner sets it through the provider's own login flow or in their own shell or env, outside the chat. Never write a secret to a file.
- Before anything that costs money or credits (paid plan, credits purchase, a tool call that spends credits) stop and get an explicit yes. Checks use only zero-cost reads.
- Never record `ligado` on a guess.
- Install commands (`instalar`) are run BY THE OWNER in their own terminal, or by you only after an explicit yes for that exact command. Never run a piped remote script (`curl ... | sh`) yourself: show it with the service's `doc_url` and let the owner run it. Say it when a command changes the owner's user-level (global) Claude or system configuration: `claude mcp add --scope user`, `claude plugin marketplace add`, `claude plugin install`, `/plugin install`, `npm i -g`.

## Step 0 - Status

1. Tell the owner the check takes about half a minute, then run `status`.
2. Show a short table: service, what it is for (one short phrase), `estado`, `conta`. `estado` is the connection: ligado, falta_autenticar, nao_instalado, desligado, falhou, nao_sei, conferir_de_novo (a mark older than 7 days, for services checked only by the session). `conta` is whether the account itself was checked: conferida (by a free read), confirmada_pelo_dono, conferir_de_novo (older than 7 days), nao_conferida, nao_se_aplica.
3. If this session is non-interactive (headless, no way to answer questions or run `/mcp`): attempt no login and no install. Run `falta`, list what is missing with its next step, and stop. (`falta` needs a `status` from the last 24 hours; if it says so, run `status` first.)

## Step 1 - Channels and site

1. Ask which channels the business uses: Meta ads, Google Ads, Instagram, Facebook, SEO/site, video, voice. Ask for the site URL (just `https://site` or `https://site/path`, with no `?` or `#` part).
2. Save: `config --site <url> --canais <comma list>`. Only these channel ids are accepted: `metaads`, `googleads`, `instagram`, `facebook`, `seo`, `video`, `voz`.
3. Offer by `nivel`: `base` always; `por_canal` only for the chosen channels; `opcional` only if the owner asks for them. For Composio, only the chosen `canais` (metaads, googleads, instagram, facebook).

## Step 2 - One service at a time

Go in catalog order. Skip services already `ligado` whose `conta` is `conferida`, `confirmada_pelo_dono` or `nao_se_aplica`; for `ligado` with `conta` `nao_conferida` or `conferir_de_novo` only do Step 3. For each one tell the owner, briefly:

1. What it is for (one sentence, `para_que`).
2. What it costs (`custo_aviso`). For each item of `incerto` that affects this service, say plainly that the catalog marks it as not confirmed.
3. Prerequisites (`pre_requisitos`) and the sign-up link (`cadastro_url`).
4. The exact commands of `instalar`, and how to authorize (`autenticar`). The owner runs them (see the hard rules); you do not enter credentials.
5. Ask for an explicit yes before any paid plan or credits.

Special cases:
- Composio / Meta Ads: say before starting that Composio has no managed app for Meta Ads (the owner brings their own Meta app credentials), and that writes to ad objects stay blocked by this module's guard by default: changes are made in Ads Manager in the browser.
- Composio / Google Ads: a developer token is needed; see the channel prerequisites.
- OAuth: when a server shows "Needs authentication", tell the owner to run `/mcp` (or `claude mcp login <name>`) in an interactive session.
- IndexNow: the key is public by design. Create it with `config --gerar-indexnow` (it prints the key; an existing one is kept), or save one the owner already publishes with `config --indexnow-key <key>`. Never put any other key in this field. Tell the owner to publish the key file at the site root (`https://<site>/<key>.txt`). Do not submit any URL in this skill.

## Step 3 - Verify each service

Use the `conferir` entries of the catalog, zero-cost reads only.

1. `plugin`, `mcp` or `cli` checks: re-run `status` and read the new state.
2. `ferramenta` check: call the zero-cost read tool named in the catalog (for example the account or identity read tool of the SEO server, or the list-voices tool); never a tool that spends credits. For Composio channels run `composio connections list --toolkit <canal>`. If it proves the connection, record `marcar <id> ligado --prova whoami_ok` (a tool read through MCP) or `marcar <id> ligado --prova connections_ok` (the Composio CLI); `--via` follows `--prova` and can be left out. For a channel, `<id>` is `composio:<canal>`.
3. `manual` check (for example the browser extension): ask the owner to confirm what they see (the `alvo` text) and record `marcar <id> ligado --prova manual`.
4. If the check shows the install exists but not the login, record `marcar <id> falta_autenticar ...`; if nothing is installed, `nao_instalado`. If the check cannot tell, say "could not verify", leave the state as is, and go on.

## Step 4 - Close

1. Run `falta` and show what is connected and what is still missing, with the next step for each.
2. Remind that marks expire after 7 days (`conferir_de_novo`): run this skill again to renew them.
3. Do not commit anything. `.tune-up/mkt/contas.json` and `config.json` hold no secrets.
