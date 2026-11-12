---
name: anuncio
description: "Makes a hook-first, business-oriented ad from a briefing, using only the owner-approved brand: one master image plus the aspect-ratio adaptations the platform needs, text variations inside the platform limits, and an import sheet with everything Paused (Google Ads Editor CSV, or an experimental Meta sheet). Publishes nothing and calls no ad API. Runs unattended from the panel action estudio.anuncio. Use on: anúncio, anuncio, ad, Google Ads, Meta Ads."
allowed-tools: Read, Bash(${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fontes.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fotos.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/anuncio.py *)
---

# Ad (images, texts and a paused import sheet)

This runs in the background. Nobody answers questions: never ask anything, never wait for a reply, never run `ls` or any command outside the list below. When a step fails twice, write it down and finish. Ad copy is in Brazilian Portuguese; your final answer is one short line in Brazilian Portuguese.

Nothing is published. Never call an ad platform, never write a sheet by hand: the sheet comes only from `anuncio.py --exportar`.

The prompt gives: the working folder (`{trabalho}`, your current folder), `Plataforma` (`google` or `meta`, called `P` below), `URL` (the landing page) and the briefing file. Write only inside the working folder. Use relative paths made of letters, digits, `_`, `.` and `/` only (no `-`, no `..`).

`AN` = `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/anuncio.py`. `W` = the absolute path of the working folder.

## 1. Plan

1. Read the briefing file named in the prompt. The scripts read the facts only from `entrada.md` in the working folder (the panel writes the briefing there): if the prompt names another file, Write its exact text to `entrada.md` first. Without it `AN --exportar` and `AN --final` fail.
2. Run `AN --plano P`. It prints the pieces (`a1` is the master, the next ones are the adaptations), each with `largura`, `altura` and `nome`, and the text limits: for each field `[min items, max items, max characters]`.
3. Read once: `${CLAUDE_PLUGIN_ROOT}/referencias/ganchos.md` and `checklist-atencao.md` (same folder); for Meta pieces also the *Arrangements* section of `arquetipos-post.md` and `recursos-visuais.md`. They hold the hook families, the regulated-niche rules, the self-check and the visual devices; this file does not repeat them.

Ad angles (each variation takes one; pt-BR molds from invented businesses):

| angle | what it says | mold |
|---|---|---|
| situation or pain | the reader's situation or pain | `Carro fazendo barulho ao frear?` |
| outcome | the result, with time | `Inglês para reunião em [N] meses` |
| proof | number, rating or customer quote | `Nota [nota] em [N] avaliações` |
| curiosity | the hidden detail | `O passo que evita [problema]` |
| comparison | old way vs this one | `Sem planilha: o contador manda o DAS pronto` |
| real urgency | a written limit | `Agenda de [mês] abre dia [dia]` |
| identity | who it is for | `Para quem abriu o MEI este ano` |
| objection | the doubt answered | `Atende sábado? Sim, das 8h às 13h.` |

Google RSA mix: 3-4 headlines with benefit or keyword, 2-3 proof (only with proof in the briefing), 2-3 CTA, 1-2 differential, 1 brand; each makes sense alone, in any order. Meta: every primary text a different angle, the hook inside its first 125 characters. "Agende já" and "Marque agora" are one variation.

## 2. Brand (read-only, as the `marca-ler` skill)

Same as the `post` skill: read `<root>/.tune-up/estudio/marca/marca.json` (root = the working folder path cut right before `/.tune-up/`), use only `campos` colors and fonts, run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fontes.py --trabalho W` once and paste every printed line at the top of each piece's `<style>`. Also read `campos.nome`, `campos.descricao` and the top-level `tom.valor` (voice). Contrast comes from a script, never from you: run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --pares W` once and use only the color pairs it prints (text 4.5:1 or more; a headline of 88 px or more may use a pair of 3:1 or more). Meta only (a Google piece carries no logo): an `.svg` logo in `<root>/.tune-up/estudio/marca/assets/`: Read it and Write the same text to `a<N>/fonte/assets/logo.svg`; a PNG, JPEG or WebP logo comes only from `fotos.py --logo`; no logo file: leave it out and say so in `resultado.md`. Never write in the brand folder.

Photos: when `marca.json` has a non-empty `fotos` list, images come only from `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fotos.py --trabalho W --para a<N>/fonte` (Meta: add `--logo`, up to 2 photos; Google: add `--quantas 1`, never `--logo`). It copies them as `assets/foto1.<ext>` (the main photo), `assets/foto2.<ext>` and prints one line per file: use exactly those names. Never pick, read or copy an image yourself, and never use an image made by AI, drawn to look like a photo, or from anywhere else.

## 3. Strategy

Before any text, write `estrategia.md`, one key per line, `key: value`, exactly these keys:

```
objetivo: vender | receber mensagens | encher a agenda | lançar novidade | ensinar e ganhar seguidores (inferred from the briefing as ganchos.md says, plus " (inferido)")
publico: <one segment in one situation, from the briefing and campos.descricao>
estagio: frio | morno | quente
promessa: <one sentence the ad keeps, only briefing facts; never a promise of results>
prova: <briefing facts used as proof> | nenhuma
arquetipo: <an archetype of arquetipos-post.md (Meta) or the main angle (Google)>
gancho 1: [family] <text> | nota <0-5> | <one-line critique>
gancho 2: ...
gancho 3: ...
escolhido: <1|2|3> | <why>
cta: <text> | leve|média|forte
angulos: <the angles used in the variations, at least 3 from the table above>
faltou: <what the owner could send next time> | nada
```

The 3 hooks come from 3 different families, scored with the rubric of ganchos.md; when the briefing names an audience or a situation, one speaks to it and the offer goes to the support line. For Meta they are the candidates for the headline of `a1` and each fits the `titulos` limit printed by `--plano`. Use an angle only if the briefing has what it needs (no proof angle without proof).

## 4. Texts

Write `textos.json` (and nothing else by hand about texts):

- Google: `{"plataforma": "google", "url": "<URL>", "titulos": [...], "descricoes": [...], "caminhos": [...]}`. Titles are headlines, `caminhos` are the 0 to 2 display path parts (no spaces).
- Meta: `{"plataforma": "meta", "url": "<URL>", "titulos": [...], "textos_principais": [...]}`.

Rules:
- `url` is exactly the URL from the prompt.
- Counts and characters inside the limits printed by `--plano`. Count characters; cut and rewrite until they fit. Give the maximum useful number of distinct variations; never repeat one.
- Every variation comes from one angle of `angulos`: write in `estrategia.md` which index is which angle (`titulos 1: dor`, ...). Variations differ in angle, not in synonyms. Google follows the mix above. Meta: each `textos_principais` item is a different angle with its hook at the start.
- No AI tics from checklist-atencao.md.
- Only facts from the briefing. Never promise a result (sales, clients, ranking, "garantido"), never write a price, discount, date or number that is not in the briefing. The script checks sizes and fields; `AN --exportar` also refuses AI tics and numbers that are not in the briefing (`entrada.md`) or the brand kit.
- No text starts with `=`, `+`, `-` or `@`.

Then run `AN --exportar W --plataforma P`. Exit 0 = `export/` has the sheet. Exit 1 = it prints the problems: fix `textos.json` and run again (at most 2 fix rounds).

## 5. Master image and adaptations

For each piece of the plan write `a<N>/fonte/index.html`, sized `largura` x `altura` of that piece, with the skeleton, rules and forbidden list of the `post` skill (`#root` and `data-width`/`data-height` = the piece size; CSS only; colors only through `--` variables; fonts only `Brand Heading` / `Brand Body`; no `<script>`, no URL, no `data-layout-*`, no `gsap`, no image other than `assets/logo.svg` and the files `fotos.py` printed).

- **Google** (`P` = `google`): the sheet makes a Search campaign, and Google rejects a Search image asset that carries text, a logo or a graphic overlay. So a Google piece has **no text at all and no logo**. With a main photo, the piece is that photo and nothing else: one `<img src="assets/foto1.<ext>">` filling `#root` (`width:100%; height:100%; object-fit:cover`), no other element, the same photo in every ratio. Without photos, no `assets/` folder and no `<img>`: it is a clean picture of the product or scene of the briefing, drawn as one inline `<svg>` of shapes (`path`, `circle`, `rect`, gradients; no `<text>`, no `<image>`) in the brand colors only, on a brand-color background, one clear subject filling the middle. A frame of plain CSS boxes counts as empty for the check: the subject must be the `<svg>`. `a1` is the master; the adaptation draws the same subject re-laid for its ratio. The headline goes only in `titulos`.
- **Meta** (`P` = `meta`): `a1` is the master: the chosen hook as its `<h1>` (one headline from `titulos`), at most one short supporting line with the proof or the offer, `id="cta"` with the action and what the person gets on the *CTA band* with the channel icon (the briefing's condition and deadline on it, never cut), the brand name written next to the logo, and one visual device from recursos-visuais.md that shows the product or the situation (the photo when there is one; `AN --final` fails a Meta piece that is only text). Headline sentences break by `<br>`, and every 1-2 letter word is glued with `&nbsp;`. `#root` carries one `l-*` arrangement of arquetipos-post.md; its type scale times 1.33 (the piece is 1440 wide). Design it first. A photo goes in a fixed box with `object-fit: cover`; text never sits directly on it: always on a solid brand-color band or block with a pair printed by `--pares` (write the pair and its ratio in `resultado.md`). The adaptation keeps the master's message, colors and hierarchy, re-laid for its ratio (stacked, with more room). Keep all text at least 80 px from the edges.
- **The 9:16 piece** (Stories/Reels): the app covers its top 14% and bottom 20%. Put every text inside one `<div id="safezone">`, styled by one rule that contains exactly `#safezone{position:absolute;top:14%;bottom:20%;left:80px;right:80px;overflow:hidden}`; nothing else names `safezone`, and no `position:fixed` or `!important` anywhere. Colors and shapes may fill the whole frame.
- No fake button, no price or promise that is not in the briefing.

Before the QA of each Meta piece, Read its snapshot and score `checklist-atencao.md` (one image: 9 items, items 3, 6 and 12 skipped): any item at 0, fix the worst (it counts as a fix round). The per-piece QA runs without `--atencao`.

Per piece (`HF` = `${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes`, absolute path; one command each, no `cd`, `;`, `>` or `|`):

1. `HF snapshot a<N>/fonte --at 0 --no-end -o a<N>/snap` -> `a<N>/snap/frame-00-at-0s.png`.
2. `HF check a<N>/fonte --json --strict`. Do not copy its output anywhere.
3. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --source a<N>/fonte --png W/a<N>/snap/frame-00-at-0s.png --width <largura> --height <altura> --out a<N>/qa.json`. Exit 0 = green. Never use `--formato` here. The "no text" (Google) and "safe zone" (9:16) rules are checked by `AN --final`, not here.

Fix rounds: if the QA is not green, read `a<N>/qa.json`, edit `a<N>/fonte/index.html` and redo steps 1 to 3. At most 2 fix rounds per piece. Never silence a check; never write inside `.hyperframes/`. A `snapshot` check with `Fonts failed` means the brand font is not on this machine: do not swap it and do not spend fix rounds on it.

## 6. Finish

1. `AN --final W --plataforma P --out final.json`. It re-checks every piece at its own size, the texts and the sheet, and writes the final line in `linha`.
2. Write `resultado.md`: platform, one line per piece (`a<N>/snap/frame-00-at-0s.png`, size, green or `precisa do seu olho` with the failed checks), every title and description, the sheet path (`export/google-ads-editor.csv` or `export/meta-experimental.csv`), and the sentence `Nada foi publicado; tudo está pausado.` Then where each image goes: Google: `As imagens não vão na planilha: depois de importar, adicione-as como recursos de imagem da campanha de Pesquisa (a 1:1 é a obrigatória).` Meta: `A planilha usa só a peça 4:5 (a1). A peça 9:16 (a2) sobe à mão no posicionamento Stories e Reels.` and `Planilha da Meta EXPERIMENTAL: o formato de importação não foi conferido numa fonte oficial.` Also `autoavaliacao: <score>/9 | pior: <item> | corrigido: sim|não` (Meta), the photos used (or `sem fotos`), anything left out (logo, missing brand field), each generic brand font reported by `fontes.py` and, from `faltou`, `Para a próxima peça, mande: ...` (skip it when `faltou: nada`).
3. Answer with the `linha` of `final.json`, exactly. Do not list or re-check files after that.
