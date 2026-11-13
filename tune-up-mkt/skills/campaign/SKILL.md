---
name: campaign
description: "Analyzes, plans and (only on request) changes paid campaigns on Meta Ads and Google Ads, always ending in a marketing action. Use on: analyze my campaign, plan an ad campaign, ad results, change budget or audience; analisar campanha, planejar anúncio, resultado dos anúncios, mexer em orçamento."
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py falta), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py falta *), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py status), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py status *)
---

# Campaign

Reply in the `language` of `~/.config/tune-up/user.json` (English if missing) and call the user `owner`. Commands are `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py <command>`. State lives in `.tune-up/mkt/contas.json` and `.tune-up/mkt/config.json` (`site`, `canais`, `indexnow_key`, `credit_ask_above`, default 2000). Service ids are in `${CLAUDE_PLUGIN_ROOT}/servicos.json`.

## Step 0 - Check what is connected

Run `falta --json` (run `status` first if it says the last status is older than 24 hours). Needed: `composio:metaads` and/or `composio:googleads` `ligado` for the channels in `config.json`, or `chrome` `ligado`. Any other state (falta_autenticar, nao_instalado, desligado, falhou, nao_sei, conferir_de_novo): say which service, send the owner to the `connect` skill, and still give any advice that needs no account data. Read `.tune-up/estudio/marca/` (brand, colours, tone) when it exists.

## Hard rules

- A campaign analysis ends in a marketing action (keep, pause, change the offer, change the audience, new test), never in code.
- Any write to an ad or a publication happens only on the owner's explicit request IN THE CURRENT TURN. An earlier "yes" does not count. Never click the final "review and publish" button: the owner does.
- The guard blocks Meta ad writes by default: make them in Ads Manager in the browser (Chrome), on the owner's explicit request. Google Ads changes and public posts ask the owner first.
- Everything is created paused, with an explicit budget cap, before it is turned on. Run the `preflight` skill first; a NO-GO means nothing goes live.
- Optimize for qualified results (leads or sales that fit), not for the cost per result the dashboard shows.
- Before changing anything, save a backup of the current state (settings, budgets, audiences) and write how to undo it. After applying, re-read the remote (read only) and compare.
- Separate [signal] (a number the collection returned) from [guess] (your interpretation). Say what the collection did NOT bring; never fill in a number.
- Save raw data to disk under `.tune-up/mkt/` (or the project's own marketing folder) before summarizing. Check the disk first and do not repeat research already done.
- Copy states, does not ask. Never address personal attributes of the viewer in ad copy (platform personal-attribute policies, privacy law).
- No invented social proof, scarcity, urgency, authority or price. Check price and offer against the current product. Without a real testimonial, use a placeholder.
- Competitors: never copy their art or text, never pay them, never message them.
- Ad media with music only under a licence you have recorded.
- Defect outside this task: one line "recorded in <file>", then go on.
- The owner decides what was not approved. Never reopen a refused decision.

## Flow

1. Ask the goal and the cap; read the data with read-only calls and save it raw.
2. Report [signal] and [guess] separately, with what is missing.
3. Propose 1 to 3 marketing actions with expected effect and how to undo. Wait for the owner.
4. Production of image, video or post art: if the `tune-up-studio` plugin is installed, use its `anuncio`, `post` or `video` skills; otherwise give a brief for the owner.
5. Only after the explicit request in this turn and a GO preflight: apply paused, then re-read and report.
