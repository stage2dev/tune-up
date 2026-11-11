---
name: anuncio
description: "Makes an ad from a briefing, using only the owner-approved brand: one master image plus the aspect-ratio adaptations the platform needs, text variations inside the platform limits, and an import sheet with everything Paused (Google Ads Editor CSV, or an experimental Meta sheet). Publishes nothing and calls no ad API. Runs unattended from the panel action estudio.anuncio. Use on: anúncio, anuncio, ad, Google Ads, Meta Ads."
allowed-tools: Read, Bash(${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fontes.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/anuncio.py *)
---

# Ad (images, texts and a paused import sheet)

This runs in the background. Nobody answers questions: never ask anything, never wait for a reply, never run `ls` or any command outside the list below. When a step fails twice, write it down and finish. Ad copy is in Brazilian Portuguese; your final answer is one short line in Brazilian Portuguese.

Nothing is published. Never call an ad platform, never write a sheet by hand: the sheet comes only from `anuncio.py --exportar`.

The prompt gives: the working folder (`{trabalho}`, your current folder), `Plataforma` (`google` or `meta`, called `P` below), `URL` (the landing page) and the briefing file. Write only inside the working folder. Use relative paths made of letters, digits, `_`, `.` and `/` only (no `-`, no `..`).

`AN` = `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/anuncio.py`. `W` = the absolute path of the working folder.

## 1. Plan

1. Read the briefing file named in the prompt.
2. Run `AN --plano P`. It prints the pieces (`a1` is the master, the next ones are the adaptations), each with `largura`, `altura` and `nome`, and the text limits: for each field `[min items, max items, max characters]`.

## 2. Brand (read-only, as the `marca-ler` skill)

Same as the `post` skill: read `<root>/.tune-up/estudio/marca/marca.json` (root = the working folder path cut right before `/.tune-up/`), use only `campos` colors and fonts, run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fontes.py --trabalho W` once and paste every printed line at the top of each piece's `<style>`. Meta only (a Google piece carries no logo): an `.svg` logo in `<root>/.tune-up/estudio/marca/assets/`: Read it and Write the same text to `a<N>/fonte/assets/logo.svg`; any other logo type: leave it out and say so in `resultado.md`. Never write in the brand folder.

## 3. Texts

Write `textos.json` (and nothing else by hand about texts):

- Google: `{"plataforma": "google", "url": "<URL>", "titulos": [...], "descricoes": [...], "caminhos": [...]}`. Titles are headlines, `caminhos` are the 0 to 2 display path parts (no spaces).
- Meta: `{"plataforma": "meta", "url": "<URL>", "titulos": [...], "textos_principais": [...]}`.

Rules:
- `url` is exactly the URL from the prompt.
- Counts and characters inside the limits printed by `--plano`. Count characters; cut and rewrite until they fit. Give the maximum useful number of distinct variations; never repeat one.
- Only facts from the briefing. Never promise a result (sales, clients, ranking, "garantido"), never write a price, discount, date or number that is not in the briefing. The script checks only sizes and fields; this rule is yours.
- No text starts with `=`, `+`, `-` or `@`.

Then run `AN --exportar W --plataforma P`. Exit 0 = `export/` has the sheet. Exit 1 = it prints the problems: fix `textos.json` and run again (at most 2 fix rounds).

## 4. Master image and adaptations

For each piece of the plan write `a<N>/fonte/index.html`, sized `largura` x `altura` of that piece, with the skeleton, rules and forbidden list of the `post` skill (`#root` and `data-width`/`data-height` = the piece size; CSS only; colors only through `--` variables; fonts only `Brand Heading` / `Brand Body`; no `<script>`, no URL, no `data-layout-*`, no `gsap`, no image other than `assets/logo.svg`).

- **Google** (`P` = `google`): the sheet makes a Search campaign, and Google rejects a Search image asset that carries text, a logo or a graphic overlay. So a Google piece has **no text at all, no logo, no `assets/` folder and no `<img>`**: it is a clean picture of the product or scene of the briefing, drawn as one inline `<svg>` of shapes (`path`, `circle`, `rect`, gradients; no `<text>`, no `<image>`) in the brand colors only, on a brand-color background, one clear subject filling the middle. A frame of plain CSS boxes counts as empty for the check: the subject must be the `<svg>`. `a1` is the master; the adaptation draws the same subject re-laid for its ratio. The headline goes only in `titulos`.
- **Meta** (`P` = `meta`): `a1` is the master: one headline from `titulos`, at most one short supporting line and the call to action from the briefing. Design it first. The adaptation keeps the master's message, colors and hierarchy, re-laid for its ratio (stacked, with more room). Keep all text at least 80 px from the edges.
- **The 9:16 piece** (Stories/Reels): the app covers its top 14% and bottom 20%. Put every text inside one `<div id="safezone">`, styled by one rule that contains exactly `#safezone{position:absolute;top:14%;bottom:20%;left:80px;right:80px;overflow:hidden}`; nothing else names `safezone`, and no `position:fixed` or `!important` anywhere. Colors and shapes may fill the whole frame.
- No fake button, no price or promise that is not in the briefing.

Per piece (`HF` = `${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes`, absolute path; one command each, no `cd`, `;`, `>` or `|`):

1. `HF snapshot a<N>/fonte --at 0 --no-end -o a<N>/snap` -> `a<N>/snap/frame-00-at-0s.png`.
2. `HF check a<N>/fonte --json --strict`. Do not copy its output anywhere.
3. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --source a<N>/fonte --png W/a<N>/snap/frame-00-at-0s.png --width <largura> --height <altura> --out a<N>/qa.json`. Exit 0 = green. Never use `--formato` here. The "no text" (Google) and "safe zone" (9:16) rules are checked by `AN --final`, not here.

Fix rounds: if the QA is not green, read `a<N>/qa.json`, edit `a<N>/fonte/index.html` and redo steps 1 to 3. At most 2 fix rounds per piece. Never silence a check; never write inside `.hyperframes/`. A `snapshot` check with `Fonts failed` means the brand font is not on this machine: do not swap it and do not spend fix rounds on it.

## 5. Finish

1. `AN --final W --plataforma P --out final.json`. It re-checks every piece at its own size, the texts and the sheet, and writes the final line in `linha`.
2. Write `resultado.md`: platform, one line per piece (`a<N>/snap/frame-00-at-0s.png`, size, green or `precisa do seu olho` with the failed checks), every title and description, the sheet path (`export/google-ads-editor.csv` or `export/meta-experimental.csv`), and the sentence `Nada foi publicado; tudo está pausado.` Then where each image goes: Google: `As imagens não vão na planilha: depois de importar, adicione-as como recursos de imagem da campanha de Pesquisa (a 1:1 é a obrigatória).` Meta: `A planilha usa só a peça 4:5 (a1). A peça 9:16 (a2) sobe à mão no posicionamento Stories e Reels.` and `Planilha da Meta EXPERIMENTAL: o formato de importação não foi conferido numa fonte oficial.` Also anything left out (logo, missing brand field) and each generic brand font reported by `fontes.py`.
3. Answer with the `linha` of `final.json`, exactly. Do not list or re-check files after that.
