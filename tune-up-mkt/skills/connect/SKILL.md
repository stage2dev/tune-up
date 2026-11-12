---
name: connect
description: "Guides the owner through connecting their own marketing accounts one service at a time, checks each connection read-only and records the result. Use on: connect my marketing accounts, set up marketing, what is missing; conectar contas de marketing, cadastro, o que falta."
disable-model-invocation: true
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py *)
---

# Connect marketing accounts

Reply in the `language` of `~/.config/tune-up/user.json` (English if missing) and call the user `owner`. The catalog is `${CLAUDE_PLUGIN_ROOT}/servicos.json`: take every text from it (use its `pt` text when the language is Portuguese). Never invent a price, a limit or a URL that is not in the catalog.

Commands below are all `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py <command>`.

Hard rules for the whole skill:
- The OWNER creates accounts and authorizes in the browser. You never create an account, never type credentials, and never ask the owner to paste a key, token, password or callback URL into the chat. If a service needs a key, the owner sets it through the provider's own login flow or in their own shell or env, outside the chat. Never write a secret to a file.
- Before anything that costs money or credits (paid plan, credits purchase, a tool call that spends credits) stop and get an explicit yes. Checks use only zero-cost reads.
- Never record `ligado` on a guess.

## Step 0 - Status

1. Tell the owner the check takes about half a minute, then run `status`.
2. Show a short table: service, what it is for (one short phrase), state. States: ligado, falta_autenticar, nao_instalado, desligado, falhou, nao_sei, conferir_de_novo (a manual mark older than 7 days).
3. If this session is non-interactive (headless, no way to answer questions or run `/mcp`): attempt no login and no install. Run `falta`, list what is missing with its next step, and stop.

## Step 1 - Channels and site

1. Ask which channels the business uses: Meta ads, Google Ads, Instagram, Facebook, SEO/site, video/voice. Ask for the site URL.
2. Save: `config --site <url> --canais <comma list of the chosen channels>`.
3. Offer by `nivel`: `base` always; `por_canal` only for the chosen channels; `opcional` only if the owner asks for them. For Composio, only the chosen `canais` (metaads, googleads, instagram, facebook).

## Step 2 - One service at a time

Go in catalog order. Skip services already `ligado` (unless `conferir_de_novo`). For each one tell the owner, briefly:

1. What it is for (one sentence, `para_que`).
2. What it costs (`custo_aviso`). For each item of `incerto` that affects this service, say plainly that the catalog marks it as not confirmed.
3. Prerequisites (`pre_requisitos`) and the sign-up link (`cadastro_url`).
4. The exact commands of `instalar`, and how to authorize (`autenticar`). Ask the owner to run them or to confirm the plugin install prompt; you do not enter credentials.
5. Ask for an explicit yes before any paid plan or credits.

Special cases:
- Composio / Meta Ads: say before starting that Composio has no managed app for Meta Ads (the owner brings their own Meta app credentials), and that writes to ad objects stay blocked by this module's guard by default: changes are made in Ads Manager in the browser.
- Composio / Google Ads: a developer token is needed; see the channel prerequisites.
- OAuth: when a server shows "Needs authentication", tell the owner to run `/mcp` (or `claude mcp login <name>`) in an interactive session.
- IndexNow: the key is public by design. Generate or choose it with the owner, save it with `config --indexnow-key <key>`, and tell them to publish the key file at the site root (`https://<site>/<key>.txt`). Do not submit any URL in this skill.

## Step 3 - Verify each service

Use the `conferir` entries of the catalog, zero-cost reads only.

1. `plugin`, `mcp` or `cli` checks: re-run `status` and read the new state.
2. `ferramenta` check: call the zero-cost read tool named in the catalog (for example the account or identity read tool of the SEO server, or the list-voices tool); never a tool that spends credits. For Composio channels run `composio connections list --toolkit <canal>`. If it proves the connection, record: `marcar <id> ligado --prova whoami_ok|connections_ok --via mcp|cli` (for a channel, `<id>` is `composio:<canal>`).
3. `manual` check (for example the browser extension): ask the owner to confirm what they see (the `alvo` text) and record `marcar <id> ligado --prova manual`.
4. If the check shows the install exists but not the login, record `marcar <id> falta_autenticar ...`; if nothing is installed, `nao_instalado`. If the check cannot tell, say "could not verify", leave the state as is, and go on.

## Step 4 - Close

1. Run `falta` and show what is connected and what is still missing, with the next step for each.
2. Remind that manual marks expire after 7 days (state `conferir_de_novo`): run this skill again to renew them.
3. Do not commit anything. `.tune-up/mkt/contas.json` and `config.json` hold no secrets.
