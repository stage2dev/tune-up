---
name: content
description: "Writes and reviews marketing copy and content pieces (posts, captions, ad text, emails, landing text) with a QA checklist. Use on: write a post, write ad copy, caption, review this copy, content plan; escrever post, legenda, texto de anúncio, revisar texto, calendário de conteúdo."
allowed-tools: Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py falta), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py falta *), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py status), Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py status *)
---

# Content

Reply in the `language` of `~/.config/tune-up/user.json` (English if missing) and call the user `owner`. Commands are `sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py <command>`. State lives in `.tune-up/mkt/contas.json` and `.tune-up/mkt/config.json` (`site`, `canais`, `indexnow_key`, `credit_ask_above`, default 2000). Service ids are in `${CLAUDE_PLUGIN_ROOT}/servicos.json`.

## Step 0 - Check what is connected

No service is required to write or review copy. Run `falta --json` only to know the channels: publishing needs `composio:instagram` or `composio:facebook` `ligado`; if it is not, say so and point to the `connect` skill, but still write the piece. Read `.tune-up/estudio/marca/` (brand, colours, tone) when it exists and follow it.

## Hard rules

- Copy states, it does not ask. Do not address the personal attributes of the reader (health, finances, family, and similar) in ad copy.
- No invented social proof, scarcity, urgency, authority or price. Check price and offer against the current product. Without a real testimonial, write a clearly marked placeholder.
- Publishing happens only on the owner's explicit request IN THE CURRENT TURN; an old "yes" does not count. Public posts ask the owner first, and the owner presses the final publish.
- Everything is created as a draft or scheduled-not-live, and a paid use goes through `preflight` first.
- Competitors: never copy their art or text.
- Music in ad media only under a recorded licence.
- Separate [signal] (a number, a real quote) from [guess]. Never fill in a number you do not have.
- Save raw research to disk under `.tune-up/mkt/` (or the project's marketing folder) and check there first; do not repeat research.
- Defect outside this task: one line "recorded in <file>".
- The owner decides what was not approved; never reopen a refused decision.

## Flow

1. Ask the goal, audience, offer and channel. Confirm the offer against the current product.
2. Write 2 or 3 options in the brand tone. Keep each short.
3. Piece QA with a checked list: offer and price correct; claims true and sourced; copy states; legible on a phone (390 px); captions present (watch without sound); call to action clear; brand kit followed. Close with one line: "What I did NOT check".
4. Art, image, video or post layout: if the `tune-up-studio` plugin is installed, use its `post`, `anuncio`, `video` or `marca` skills; otherwise give a brief the owner can hand to a designer.
5. Publish or schedule only on the owner's request in this turn.
