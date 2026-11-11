---
name: post
description: "Makes a still post or a carousel (PNG per frame) from a briefing, using only the owner-approved brand, and checks every frame with the studio QA. Runs unattended from the panel action estudio.post. Use on: post, carrossel, carousel, peça estática, post do Instagram."
allowed-tools: Read, Bash(${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fontes.py *)
---

# Post and carousel

This runs in the background. Nobody answers questions: never ask anything, never wait for a reply, never run `ls` or any command outside the list below. When a step fails twice, write it down and finish. Piece copy is in Brazilian Portuguese; your final answer is one short line in Brazilian Portuguese.

The prompt gives: the working folder (`{trabalho}`, your current folder), `Formato` (`post 4:5`, `post 1:1`, `carrossel 4:5`, `carrossel 1:1`), `Quadros` and the briefing file. Write only inside the working folder. Use relative paths made of letters, digits, `_`, `.` and `/` only (no `-`, no `..`).

## 1. Inputs

1. Read the briefing file named in the prompt.
2. Frames: `post` = 1 frame. `carrossel` = `Quadros` frames, at least 2 (if 1, make 2). One aspect ratio for all frames.
3. Size from `${CLAUDE_PLUGIN_ROOT}/formatos.json`: 4:5 = `instagram-feed-organico-tamanho` (1080x1350), 1:1 = `instagram-feed-quadrado-tamanho` (1080x1080). `<R>` below is the ratio of `Formato` (`4:5` or `1:1`); the QA checks every PNG against that size.
4. Text limits from the same file, entry `instagram-feed-anuncio-texto`: headline on the image up to `titulo` characters, caption up to `texto_principal` characters. Any other line on the image: up to 90 characters. Count characters; cut and rewrite until they fit.

## 2. Brand (read-only, as the `marca-ler` skill)

The project root is the working folder path cut right before `/.tune-up/`. Read `<root>/.tune-up/estudio/marca/marca.json`. The panel only starts this action when the owner approved that file; do not look for approval yourself and never write there.

- Use `campos` values only: `cores.*` (hex) and `fontes.*`. Never invent a color or a font. Missing field: use the neutral one from `MARCA.md` next to it.
- Fonts come from a script, not from you: run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fontes.py --trabalho <working folder>` (absolute path) once. It prints the two `@font-face` lines for `fontes.heading` and `fontes.body` (a generic family like `system-ui` or `sans-serif` becomes a fixed stack of local fonts) and one `/* fonte da marca ...: ... generica ... */` line per field that names a generic family. Paste every printed line as is at the top of each frame's `<style>`; never write or edit an `@font-face` yourself. For each `generica` line, write in `resultado.md` that the brand font of that field is generic and the frame uses the local stack.
- Logo: if `logo` points to an `.svg` in `<root>/.tune-up/estudio/marca/assets/`, Read it and Write the same text to `q<N>/fonte/assets/logo.svg`. Any other logo type: leave the logo out and say so in `resultado.md`.

## 3. Copy

Write `copy.md`: for each frame, headline and at most 2 short lines; then the caption and the call to action from the briefing. A carousel tells one story:
- Frame 1 is only the hook: it raises the question and does not give the answer; it ends with a swipe cue (`arraste ->`).
- Every middle frame brings one point the other frames do not say. Never repeat a fact already shown.
- The last frame has the call to action.
- If the briefing has fewer distinct points than `Quadros` asks, make fewer frames (at least 2) and write in `resultado.md`: `quadros: <made> de <asked>, briefing curto`. Never invent a fact, price, date or promise to fill a frame.
- Vary the layout between frames (big number, short list, quote), same brand and size.

## 4. One HTML per frame

For frame N write `q<N>/fonte/index.html` (N = 1, 2, ...). Copy the shape of this skeleton:

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <style>
    <the lines printed by fontes.py, unchanged>
    :root { --bg: #...; --surface: #...; --primary: #...; --text: #...; --accent: #...; }
    html, body { margin: 0; background: var(--bg); }
    #root { position: relative; width: 1080px; height: 1350px; overflow: hidden; box-sizing: border-box;
            padding: 96px; background: var(--bg); color: var(--text); font-family: "Brand Body", sans-serif; }
  </style>
</head>
<body>
  <div id="root" data-composition-id="post" data-start="0" data-duration="5"
       data-width="1080" data-height="1350" data-no-timeline>
    <!-- content -->
  </div>
</body>
</html>
```

Rules:
- `data-width`/`data-height` and `#root` width/height are the frame size. Every frame of a carousel has the same size.
- CSS only, colors only through the `--` variables, fonts only through the two `@font-face` names `Brand Heading` and `Brand Body` printed by `fontes.py` (never a bare generic family as the only font: the renderer would download a web font).
- Safe container: all text inside `#root` with at least 80 px padding; give text boxes a `max-width` and let them wrap. No absolute positioning of text near the edges.
- Forbidden: `<script>`, any URL (`http`, `//`), web fonts, `gsap`, `data-layout-*` attributes, images other than `assets/logo.svg`. The QA fails on any of these.

## 5. Snapshot, check, QA (per frame)

`HF` = `${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes` (absolute path, no `npx`). Run each as a single command, no `cd`, no `;`, no `>`, no `|`.

1. `HF snapshot q<N>/fonte --at 0 --no-end -o q<N>/snap` -> `q<N>/snap/frame-00-at-0s.png`.
2. `HF check q<N>/fonte --json --strict`. Do not copy its output anywhere: HyperFrames saves the report under `q<N>/fonte/.hyperframes/` and the QA reads it from there. Exit 1 means findings.
3. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --source q<N>/fonte --png <working folder>/q<N>/snap/frame-00-at-0s.png --formato=<R> --out q<N>/qa.json`. Exit 0 = green. Give `--png` with the absolute working-folder path: the file name has `-`, which the command list only accepts after that path.

Fix rounds: if the QA is not green, read the failed checks in `q<N>/qa.json`, edit `q<N>/fonte/index.html` (shorter text, smaller font, more room) and redo steps 1 to 3 (snapshot and check must be newer than the last edit). At most 2 fix rounds per frame. Never silence a check. A `snapshot` check with `Fonts failed` means the brand font is not on this machine: do not swap it for another font and do not spend fix rounds on it; that frame stays `precisa do seu olho`. Never write inside `.hyperframes/`.

## 6. Finish

1. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --final <working folder> --formato=<R> --out final.json`. It re-checks every `q<N>/` frame (size of the format, saved check report, snapshot record) and writes the final line in `linha`: `PRONTO: <n> de <n> quadros verdes` only when every frame is green, otherwise `PRECISA DO SEU OLHO: <k> de <n> verdes, <frames and checks>`.
2. Write `resultado.md`: format, size, one line per frame from `final.json` (`q<N>/snap/frame-00-at-0s.png`, green or `precisa do seu olho` with the failed checks; a failed font by name), the caption, anything left out (logo, missing brand field, fewer frames than asked) and each generic brand font reported by `fontes.py`.
3. Answer with the `linha` of `final.json`, exactly. Do not list or re-check files after that.
