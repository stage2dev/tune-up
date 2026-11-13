---
name: seo
description: "Keyword research, site audit, rank tracking and search-engine submission through OpenSEO, Search Console and IndexNow. Use on: keyword research, SEO audit, rank tracking, index my pages, search traffic; pesquisa de palavras-chave, auditoria de SEO, posição no Google, indexar páginas."
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py falta), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py falta *), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py status), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py status *)
---

# SEO

Reply in the `language` of `~/.config/tune-up/user.json` (English if missing) and call the user `owner`. Commands are `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py <command>`. State lives in `.tune-up/mkt/contas.json` and `.tune-up/mkt/config.json` (`site`, `canais`, `indexnow_key`, `credit_ask_above`, default 2000). Service ids are in `${CLAUDE_PLUGIN_ROOT}/servicos.json`.

## Step 0 - Check what is connected

Run `falta --json`. Needed: `openseo` `ligado`; for real queries and traffic also `search_console_analytics` `ligado`; for submission `indexnow` `ligado` and `indexnow_key` in `config.json`. If one is missing, say which and send the owner to the `connect` skill; still give advice that needs no data. Read `.tune-up/estudio/marca/` for tone when it exists.

## Hard rules

- Estimate the cost before any paid OpenSEO call (a keyword lookup costs credits). Ask the owner above `credit_ask_above` from `config.json` (default 2000). Zero-cost reads (projects, saved keywords, Search Console) need no ask.
- Save raw data to disk under `.tune-up/mkt/` before summarizing. Check the disk first and do not repeat research already done.
- Separate [signal] (volume, position, clicks as returned) from [guess] (interpretation). Say what the collection did NOT bring; never fill in a number.
- IndexNow submission only on the owner's explicit request IN THE CURRENT TURN, with the key from `config.json`. Never submit a URL outside `site`. Never put any other key in that field.
- No invented claims in titles, descriptions or page text (authority, awards, prices). Check price and offer against the current product.
- Competitors: study their public pages, never copy their text and never contact them.
- Backup of the current titles and descriptions and how to undo, before proposing changes to a live page. Changes to the site itself are the owner's; this skill proposes text.
- Defect outside this task: one line "recorded in <file>".
- The owner decides what was not approved; never reopen a refused decision.

## Flow

1. Research: seed terms from the business, then keywords with intent, volume and difficulty; group by page. Save raw.
2. Audit: crawl results for titles, descriptions, headings, speed, mobile (390 px), broken links, indexing.
3. Rank tracking: save the tracked keywords and positions with dates; compare to the last saved run.
4. Report [signal] and [guess] apart and end in 1 to 3 marketing actions (a page to write, a title to change, a page to submit), not code.
5. Submit: list the exact URLs (all under `site`), wait for the owner's request in this turn, then submit and report the response.
