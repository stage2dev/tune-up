---
name: video
description: "Makes a hook-first, business-oriented silent vertical reel (9:16, 1080x1920 MP4, 10 or 15 s) from a briefing, using only the owner-approved brand: strategy, the reel composition of the studio kit filled with the script and a hero drawn for this briefing, motion by the studio JavaScript engine (seek-safe, no network), render or slide reserve, and the studio QA. Runs unattended from the panel actions estudio.video and estudio.video-motion. Use on: vídeo, reel, reels, story em vídeo."
allowed-tools: Read, Bash(${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_video.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/reserva_slides.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/montar.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fotos.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py *)
---

# Reel (9:16 video)

This runs in the background. Nobody answers questions: never ask anything, never wait for a reply, never run `ls` or any command outside the list below. When a step fails twice, write it down and finish. Piece copy is in Brazilian Portuguese; your final answer is one short line in Brazilian Portuguese.

The prompt gives: the working folder (`{trabalho}`, your current folder), `Motor` (`hyperframes` or `reserva`), `Duracao` (`10` or `15` seconds, called `D` below), `Objetivo`, `Estilo` and the briefing file. `Objetivo` or `Estilo` empty (`Objetivo: .`) or missing means `a IA escolhe`. Write only inside the working folder. Use relative paths made of letters, digits, `_`, `.` and `/` only (no `-`, no `..`).

`Motor: reserva` means this project did not turn on the local render (`estudio.video_rede_local` in `painel.json`): never run `render`, it cannot open its local port here. The video is made from still slides of the same composition (step 7b): each slide is the scene near its end, none of the motion between. So with `reserva`, every scene must work as a still photo and scenes must differ in arrangement, not only in motion.

## 1. Inputs

1. Read the briefing file named in the prompt. The QA reads the facts only from `entrada.md` in the working folder (the panel writes the briefing there): if the prompt names another file, Write its exact text to `entrada.md` before step 3. Without it every fact check fails.
2. Read once, and only these: `${CLAUDE_PLUGIN_ROOT}/referencias/ritmo.md`, then `ganchos.md`, `checklist-atencao.md`, `kit-video.md`, `heroi.md` from the same folder (and `legenda.md` at step 8). They hold the hook families, arcs, regulated-niche rules, the scenes of the kit and their slots, the styles, the way to draw the hero, the director score and the self-check; this file does not repeat them. Their pt-BR lines are molds from invented businesses: never reuse one word for word (QA `molde`).
3. The style: the `Estilo` of the prompt, or, for `a IA escolhe`, the one the Styles table of kit-video.md gives for this briefing. Then Read its file in `${CLAUDE_PLUGIN_ROOT}/referencias/estilos-video/` (the file name of that table), that one only: never open or list the other style files.
4. Size from `${CLAUDE_PLUGIN_ROOT}/formatos.json`, entry `instagram-reels-tamanho` (1080x1920); the kit keeps every text inside the safe zone of `instagram-reels-zona-segura` (today 269 px top, 384 px bottom, 90 px sides) and puts only brand-color shapes outside it.
5. Text limits: the hook up to 40 characters, any other line up to 60. Words per scene, all text of the scene together (the brand name aside): at most the larger of 6 and 3 x the scene length in seconds (kit-video.md gives the number per scene). The kit refuses a scene that goes over; cut and rewrite until it fits.

## 2. Brand (read-only, as the `marca-ler` skill)

The project root is the working folder path cut right before `/.tune-up/`. Read `<root>/.tune-up/estudio/marca/marca.json` for `campos.nome`, `campos.descricao` and the top-level `tom.valor` (voice). The panel only starts this action when the owner approved that file; do not look for approval yourself and never write there.

- Colors, contrast, fonts and logo are placed by the kit from that file: it measures every text pair as `qa_imagem.py --pares` does, writes the `@font-face` lines `fontes.py` prints and copies an SVG logo to `fonte/assets/`. Never invent a color or a font and never work out a ratio yourself. For each brand font that is a generic family (`system-ui`, `sans-serif`), write in `resultado.md` that the video uses the local stack; no logo in the brand: say so there.
- Photos: when `marca.json` has a non-empty `fotos` list, the main one may be the hero. Never pick, read or copy an image file yourself: run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fotos.py --trabalho <working folder> --para fonte --logo --quantas 1` (absolute working folder) before `montar.py`. It copies the photo as `assets/foto1.<ext>` (and a PNG/JPEG/WebP logo as `assets/logo.<ext>`) and prints one line per copied file. Nothing printed: no photo, never a substitute. Never use an image made by AI, drawn to look like a photo, or from anywhere else.
- Contact: only the channel or handle the briefing or the brand kit writes (`pelo WhatsApp`, the phone, the `@`, the site), with or without `link na bio`; nothing else. Never invent a number, handle or address.

## 3. Strategy

Before the script, write `estrategia.md`, one key per line, `key: value`, exactly these keys:

```
objetivo: <Objetivo of the prompt; for "a IA escolhe" the one ganchos.md infers, plus " (inferido)">
publico: <one segment in one situation, from the briefing and campos.descricao>
estagio: frio | morno | quente
promessa: <one sentence the video keeps, only briefing facts; never a promise of results>
prova: <briefing facts used as proof> | nenhuma
arquetipo: <an arc of ritmo.md>
estilo: <the style's file name, without .md> | <asked in the prompt, or why this briefing asks for it>
gancho 1: [family] <text> | nota <0-5> | <one-line critique>
gancho 2: ...
gancho 3: ...
escolhido: <1|2|3> | <why>
cta: <text> | leve|média|forte
faltou: <what the owner could send next time> | nada
```

The 3 hooks come from 3 different families of ganchos.md (at least 2 from its row for the objective), scored with its rubric. When the briefing names an audience or a situation, one candidate speaks to it (`reader's situation`) and the offer moves to the offer scene and the call; a headline that only states the offer loses. The call to action matches the stage's temperature.

## 4. The script, as slots of the kit

Write `peca.json` with `"estilo"` (the same file name as in `estrategia.md`) and the slots of kit-video.md: `gancho` (the chosen hook: title + its key words as `destaque`; 6 words and 40 characters together), scene 2 as the style file gives its slots (it continues the hook with the mechanism or the proof; every slot filled, the beats are what moves), the 15 s scene, `oferta` (the offer as the briefing names it + its price or offer word + one fact not shown yet) and `final` (verb + a gain not said yet, the briefing's condition and deadline, the contact as written, its channel).
- The arc of `arquetipo` (ritmo.md) decides what each scene says; the kit decides how it looks and moves. One idea per scene; a fact appears once in the whole reel; the caption takes what does not fit.
- When the briefing has an offer word (`grátis`, `gratuita`, a `%`, `desconto`...), it is in a scene title, `oferta.nome`, `oferta.valor` or `final.titulo` (QA `oferta_destaque`); a price is `oferta.valor`, alone (QA `preco_destaque`). A hook that is the proof itself sets `"numero": true` in `gancho`.
- Set `heroi_anda`, `chao` and `variante` by kit-video.md; never copy the mold's values. No AI tics from checklist-atencao.md and no `!` on screen.
- Never invent a fact, price, date, number or promise; a short briefing gets a shorter text in each slot, never a scene that describes the business (name, city, "atendimento individual").

## 5. The hero and the composition

1. Draw `heroi.svg` by heroi.md: the reader's object in its moment, one detail only this briefing has, and its change: `h_antes` (the problem state) and 3 or more `h_depois` or `h_traco` parts (what the offer adds). That change is the reel's payoff: the kit plays it in the offer scene. With a main photo printed by `fotos.py`, write `"heroi": "foto"` in `peca.json` and draw nothing.
2. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/montar.py --tipo video --peca peca.json --heroi heroi.svg --out fonte --duracao D`. It writes `fonte/index.html` (layout in CSS, motion by the studio engine in one inline script, seek-safe, no network) and prints one line per scene; exit 1 names the one thing to fix in `peca.json` or `heroi.svg`.

Never edit `fonte/index.html`: a change is a change of `peca.json` or `heroi.svg`, then `montar.py` again. What the kit keeps for you (and the QA checks): every scene whole at its cut and a new beat about every 0.6 s, cuts off the 0.25 s grid, no text through a mask, one hero reframed at every cut and 45% wide or more on the end card, the value 220 px or more on the accent band, a cursor pressing the contact on the end card, at least 2 kinds of transition, nothing still for 0.5 s but the last second.
- Forbidden in anything you write: a `<script>` of your own, any URL (`http`, `//`), web fonts, `gsap` or any animation library, `style` or a color value inside `heroi.svg`, images other than the files `fotos.py` printed. The kit and the QA refuse them (`script_seguro`, `network_lint`, `no_gsap`).

## 6. Loop: lint, check, look (QA rounds and visual rounds)

`HF` = `${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes` (absolute path, no `npx`). Run each as a single command, no `cd`, no `;`, no `>`, no `|`.

1. `HF lint fonte`
2. `HF check fonte --json --strict`. Do not read or copy its long output: HyperFrames saves the report under `fonte/.hyperframes/` and the QA reads it from there. Then run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --achados fonte`: it prints only the `warning`/`error` findings of that report, one per line (exit 1 = fix them).
3. `HF snapshot fonte --at <T> --no-end -o snap`, with the look `--at` list of kit-video.md for `D` and the style. Read every `snap/contact-sheet*.jpg`: score `checklist-atencao.md` (12 items) and then its director score (0-10), as the stranger who will judge it. Look hardest at the hero: does it read as this business's object or as an icon, is the briefing's detail big, is the change in the offer scene visible from across the room?

At most 2 fix rounds for QA findings (static check or the QA of step 7a) and at most 3 visual rounds for the director score, 5 rounds in all: a round changes `peca.json` or `heroi.svg` by the last table of kit-video.md and redoes step 5.2 and 1 to 3; a visual round fixes the weakest criterion of the director score while it is below 9, with a change the eye sees (the drawing, the variant, a shorter line), not only a word. Never silence a finding. Never write inside `.hyperframes/`.

## 7a. `Motor: hyperframes`: render and QA

1. `HF render fonte -o video.mp4 --fps 30 --quality delivery --experimental-fast-capture=false --workers=1 --quiet` (screenshot capture in one browser: two renders give the same MP4, byte for byte; several workers do not). It still prints progress lines (`[initSession...]`): the command list accepts no `>`, so ignore them and never run it again just to read them; only its exit code matters.
2. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_video.py --source fonte --video video.mp4 --duration D --atencao --out qa.json --sheet folha.png`
3. Read `folha.png` (one frame every 0.5 s of the MP4) and `folha_cortes.png` (0.35 s before and after each cut) and score item 12 and the director score again from them: 2 equal frames in a row before the last second, a word cut in half, an empty frame or a transition leftover is a 0. If the QA is red, an item is 0 or the director score is below 9 and rounds are left, fix, then redo step 5.2, step 6 and 7a steps 1 to 3 (render again: never keep an MP4 older than the fix).

If the render fails twice, make the video by 7b and say in `resultado.md` that the render failed and the reserve was used.

## 7b. `Motor: reserva`: slides and QA

1. `HF snapshot fonte --at <T> --no-end -o slides` with the slides `--at` list of kit-video.md for `D` and the style (each scene near its end, every beat landed; each slide lasts its scene (`--tempos`)).
2. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/reserva_slides.py --slides slides --out video.mp4 --duration D --tempos <the --tempos list of kit-video.md for D and the style>`
3. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_video.py --engine reserve --source fonte --video video.mp4 --duration D --atencao --out qa.json --sheet folha.png`, then Read `folha.png`.

The QA also fails when the MP4 is older than `fonte/` or than the last check (render again after a fix) and when the newest snapshot recorded a warning. A `brand_font` check with `Fonts failed` means the brand font is not on this machine: do not swap it for another font and do not spend fix rounds on it; the video stays `precisa do seu olho`.

## 8. Finish

1. Write `resultado.md`: motor and why (`reserva`: "o projeto não ligou estudio.video_rede_local no painel.json; o vídeo saiu da reserva em slides, sem movimento dentro das cenas"), length and size; the strategy in 3 lines (objective, chosen hook, arc); the style and why; the variant `montar.py` printed; one line per scene with its texts (with `reserva`, never describe motion as if it were in the video: its motion is `não aparece na reserva`); the hero in one line (object, the briefing's detail, its change); `video.mp4` and `folha.png`; the `linha` of `qa.json` and its failed checks (a failed font by name); `autoavaliacao: <score>/12 | pior: <item> | corrigido: sim|não`; `nota_diretor: <n>/10 | pior: <criterion>`; `Legenda sugerida:` a caption written by legenda.md in the brand voice; the photo used (or `sem fotos`); anything left out (logo, missing brand field); each generic brand font; and, from `faltou`, `Para a próxima peça, mande: ...` (skip it when `faltou: nada`).
2. Answer with the `linha` of `qa.json`, exactly (`PRONTO: ...` or `PRECISA DO SEU OLHO: ...`); but if checklist item 1, 5 or 9 still scores 0, answer `PRECISA DO SEU OLHO: autoavaliação item <n>`, and if the director score is below 9, `PRECISA DO SEU OLHO: nota do diretor <n>/10`. Do not list or re-check files after that.
