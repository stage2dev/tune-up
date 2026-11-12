---
name: post
description: "Makes a hook-first, business-oriented still post or carousel (PNG per frame) from a briefing, using only the owner-approved brand: strategy first, one chosen hook, a composition of the studio kit with a hero drawn for this briefing, one call to action, and every frame checked by the studio QA. Runs unattended from the panel action estudio.post. Use on: post, carrossel, carousel, peça estática, post do Instagram."
allowed-tools: Read, Bash(${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/montar.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fotos.py *)
---

# Post and carousel

This runs in the background. Nobody answers questions: never ask anything, never wait for a reply, never run `ls` or any command outside the list below. When a step fails twice, write it down and finish. Piece copy is in Brazilian Portuguese; your final answer is one short line in Brazilian Portuguese.

The prompt gives: the working folder (`{trabalho}`, your current folder), `Formato` (`post 4:5`, `post 1:1`, `carrossel 4:5`, `carrossel 1:1`), `Quadros`, `Objetivo` and the briefing file. `Objetivo` empty (`Objetivo: .`) or missing means `a IA escolhe`. Write only inside the working folder. Use relative paths made of letters, digits, `_`, `.` and `/` only (no `-`, no `..`).

## 1. Inputs

1. Read the briefing file named in the prompt. The QA reads the facts only from `entrada.md` in the working folder (the panel writes the briefing there): if the prompt names another file, Write its exact text to `entrada.md` before step 3. Without it every fact check fails.
2. Read once, and only these: `${CLAUDE_PLUGIN_ROOT}/referencias/ganchos.md`, `arquetipos-post.md` (its *Archetypes* and *Carousel arcs*; measures and type are the kit's), `kit-post.md`, `heroi.md`, `legenda.md`, `checklist-atencao.md` (same folder). They hold the hook families, the compositions of the kit and their slots, the way to draw the hero, caption rules, regulated-niche rules, the self-check and the director score; this file does not repeat them. Their pt-BR lines are molds from invented businesses: never reuse one word for word (QA `molde`).
3. Frames: `post` = 1 frame. `carrossel` = `Quadros` frames, at least 2 (if 1, make 2). One aspect ratio for all frames.
4. Size from `${CLAUDE_PLUGIN_ROOT}/formatos.json`: 4:5 = `instagram-feed-organico-tamanho` (1080x1350), 1:1 = `instagram-feed-quadrado-tamanho` (1080x1080). `<R>` below is the ratio of `Formato` (`4:5` or `1:1`); the QA checks every PNG against that size.
5. Text limits from the same file, entry `instagram-feed-anuncio-texto`: headline on the image up to `titulo` characters; caption: first line up to `texto_principal` characters (what shows before "mais"), whole caption up to 1000 characters, at most 5 hashtags at the end. Words on the image: a single post and any frame after the first at most 30, a carousel cover at most 20; the brand name beside the logo is not counted. The kit refuses a slot that is too long.

## 2. Brand (read-only, as the `marca-ler` skill)

The project root is the working folder path cut right before `/.tune-up/`. Read `<root>/.tune-up/estudio/marca/marca.json` for `campos.nome`, `campos.descricao` and the top-level `tom.valor` (voice; see legenda.md). The panel only starts this action when the owner approved that file; do not look for approval yourself and never write there.

- Colors, contrast, fonts and logo are placed by the kit from that file: it measures every text pair as `qa_imagem.py --pares` does (4.5:1, or 3:1 for big type), writes the `@font-face` lines `fontes.py` prints and copies an SVG logo to `q<N>/fonte/assets/`. Never invent a color or a font, never work out a ratio yourself, never edit those lines. When `montar.py` prints nothing about the logo and the brand has none, say so in `resultado.md`; for each brand font that is a generic family (`system-ui`, `sans-serif`), write that the frame uses the local stack.
- Photos: when `marca.json` has a non-empty `fotos` list, the piece may use the main one as the hero. Never pick, read or copy an image file yourself: run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fotos.py --trabalho <working folder> --para q<N>/fonte --logo --quantas 1` (absolute working folder) before `montar.py`. It copies the photo as `assets/foto1.<ext>` (and a PNG/JPEG/WebP logo as `assets/logo.<ext>`) and prints one line per copied file. Nothing printed: no photo, never a substitute. Never use an image made by AI, drawn to look like a photo, or from anywhere else.

## 3. Strategy

Before any copy, write `estrategia.md`, one key per line, `key: value`, exactly these keys:

```
objetivo: <Objetivo of the prompt; for "a IA escolhe" the one ganchos.md infers, plus " (inferido)">
publico: <one segment in one situation, from the briefing and campos.descricao>
estagio: frio | morno | quente
promessa: <one sentence the piece keeps, only briefing facts; never a promise of results>
prova: <briefing facts used as proof> | nenhuma
arquetipo: <a name from arquetipos-post.md>
gancho 1: [family] <text> | nota <0-5> | <one-line critique>
gancho 2: ...
gancho 3: ...
escolhido: <1|2|3> | <why>
cta: <text> | leve|média|forte
faltou: <what the owner could send next time> | nada
```

The 3 hooks come from 3 different families of ganchos.md (at least 2 from its row for the objective), scored with its rubric. When the briefing names an audience or a situation, one candidate speaks to it (`reader's situation`) and the offer goes to the offer stack and the call; a headline that only states the offer loses. Pick the archetype only if the briefing has the proof it needs; a short briefing (3 facts or fewer) follows the *Short briefing* path of ganchos.md. The call to action matches the stage's temperature.

## 4. Copy, as slots of the kit

Write `copy.md`: one `## q<N>` block per frame with `layout:` (the `l-*` of the chosen composition, kit-post.md), `recurso:` (the hero and what it carries), `titulo:` and `apoio:`; then `## Legenda` with the caption written by legenda.md, in the brand voice. Then write one `q<N>/peca.json` per frame with the slots of kit-post.md.
- Frame 1 is the chosen hook. Choose the composition by the table of kit-post.md (the hero's shape, price or no price, proof as hook) and set `variante` only when you have a reason; never copy the mold's values.
- The offer is written as the briefing names it (`oferta.nome`: the service or package, never only its price), its price or offer word in `oferta.valor`, one fact not said in the title in `oferta.prova`.
- Single post: the title, the proof and the call never repeat a noun; `cta.chamada` is verb + where or a gain not said yet; the briefing's real contact, condition and deadline ("só esta semana", "até 15/12") go in `cta.condicao` (QA `cta`): cut the proof before cutting the deadline. The kit writes the brand name beside the logo (QA `marca`).
- Carousel: follow an arc of arquetipos-post.md with the `--quadro` kinds of kit-post.md. The cover only raises the question and carries the swipe cue (`arraste`); frame 2 continues the hook; the second to last pays the promise with a fact the hook did not show; the last has the offer and the call. Every middle frame brings one point the others do not say; `layout:` never repeats the frame before.
- If the briefing has fewer distinct points than `Quadros` asks, make fewer frames (at least 2) and write in `resultado.md`: `quadros: <made> de <asked>, briefing curto`. Never invent a fact, price, date, number or promise to fill a frame. A contact names only the channel or handle written in the briefing or the brand kit (`pelo WhatsApp`, the phone, the `@`), with or without `link na bio`.
- No AI tics from checklist-atencao.md and no `!` on the image.

## 5. The hero and the frames

1. Draw `heroi.svg` once, in the working folder, by heroi.md: the reader's object in its moment, with one detail only this briefing has and its before and after. With a main photo printed by `fotos.py`, write `"heroi": "foto"` in `peca.json` and draw nothing. No photo of the product: write `sem foto do produto: precisa do seu olho` in `resultado.md` and ask for photos in `faltou`.
2. For frame N run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/montar.py --tipo post --peca q<N>/peca.json --heroi heroi.svg --out q<N>/fonte --formato=<R>` (a carousel adds `--quadro capa`, `ponto` or `fecho`). It writes `q<N>/fonte/index.html` and prints the sizes it chose; exit 1 names the one thing to fix in `peca.json` or `heroi.svg`.

What the kit writes, so you know what the QA sees: one `<h1>`, at most 3 type levels, `id="oferta"` for the value (up to 1.7 times the h1), `id="cta"` only in the last frame, one `l-*` class on `#root`, the one margin (`#root` has `padding: 80px;`), shapes that run to the real edge, brand colors through `--` variables only. Never edit `index.html`: a change is a change of `peca.json` or `heroi.svg`, then `montar.py` again.
- Forbidden in anything you write: `<script>`, any URL (`http`, `//`), web fonts, `gsap`, `style` or a color value inside `heroi.svg`, images other than the files `fotos.py` printed. The kit and the QA refuse them.

## 6. Snapshot, look, check, QA (per frame)

`HF` = `${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes` (absolute path, no `npx`). Run each as a single command, no `cd`, no `;`, no `>`, no `|`.

1. `HF snapshot q<N>/fonte --at 0 --no-end -o q<N>/snap` -> `q<N>/snap/frame-00-at-0s.png`.
2. Read that PNG and score `checklist-atencao.md` (a single post: 9 items; a carousel: items 1 to 11), then its director score (0-10), as the stranger who will judge it. Any item at 0: fix the worst now (it counts as a fix round) and redo from step 5.2; a director score below 9: fix its weakest criterion (a visual round) by the last table of kit-post.md, most often the hero's drawing, and redo from step 5.2.
3. `HF check q<N>/fonte --json --strict`. Do not read or copy its long output: HyperFrames saves the report under `q<N>/fonte/.hyperframes/`, the QA reads it from there and lists its findings in `q<N>/qa.json`. Exit 1 means findings.
4. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --source q<N>/fonte --png <working folder>/q<N>/snap/frame-00-at-0s.png --formato=<R> --atencao --out q<N>/qa.json`. Exit 0 = green. Give `--png` with the absolute working-folder path: the file name has `-`, which the command list only accepts after that path.

Fix rounds: if the QA is not green, read the failed checks in `q<N>/qa.json`, change the slot or the drawing the last table of kit-post.md names and redo steps 5.2, 1, 3 and 4 (snapshot and check must be newer than the last change). At most 2 fix rounds per frame for QA findings, plus at most 3 visual rounds for the director score (5 in all): each visual round changes the hero, the composition or the variant, not only a word. Never silence a check. A `snapshot` check with `Fonts failed` means the brand font is not on this machine: do not swap it for another font and do not spend fix rounds on it; that frame stays `precisa do seu olho`. Never write inside `.hyperframes/`.

## 7. Finish

1. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --final <working folder> --formato=<R> --atencao --out final.json`. It re-checks every `q<N>/` frame (size of the format, saved check report, snapshot record) and the whole piece (`estrategia.md`, call to action, arrangement sequence, swipe cue, caption in `copy.md`), and writes the final line in `linha`: `PRONTO: <n> de <n> quadros verdes` only when everything is green, otherwise `PRECISA DO SEU OLHO: <k> de <n> verdes, <frames and checks>`.
2. Write `resultado.md`: format, size; the strategy in 3 lines (objective, chosen hook, archetype); the composition and variant of each frame; one line per frame from `final.json` (`q<N>/snap/frame-00-at-0s.png`, green or `precisa do seu olho` with the failed checks; a failed font by name); `autoavaliacao: <score>/<9 or 11> | pior: <item> | corrigido: sim|não`; `nota_diretor: <n>/10 | pior: <criterion>`; the caption; the photo used (or `sem fotos`); anything left out (logo, missing brand field, fewer frames than asked); each generic brand font; and, from `faltou`, `Para a próxima peça, mande: ...` (skip it when `faltou: nada`).
3. Answer with the `linha` of `final.json`, exactly; but if checklist item 1, 5 or 9 still scores 0, answer `PRECISA DO SEU OLHO: autoavaliação item <n>`, and if the director score is below 9, `PRECISA DO SEU OLHO: nota do diretor <n>/10`. Do not list or re-check files after that.
