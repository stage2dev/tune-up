---
name: post
description: "Makes a still post or a carousel (PNG per frame) from a briefing, using only the owner-approved brand, and checks every frame with the studio QA. Runs unattended from the panel action estudio.post. Use on: post, carrossel, carousel, peça estática, post do Instagram."
allowed-tools: Read, Bash(${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py *)
---

# Post and carousel

This runs in the background. Nobody answers questions: never ask anything, never wait for a reply, never run `ls` or any command outside the list below. When a step fails twice, write it down and finish. Piece copy is in Brazilian Portuguese; your final answer is one short line in Brazilian Portuguese.

The prompt gives: the working folder (`{trabalho}`, your current folder), `Formato` (`post 4:5`, `post 1:1`, `carrossel 4:5`, `carrossel 1:1`), `Quadros` and the briefing file. Write only inside the working folder. Use relative paths made of letters, digits, `_`, `.` and `/` only (no `-`, no `..`).

## 1. Inputs

1. Read the briefing file named in the prompt.
2. Frames: `post` = 1 frame. `carrossel` = `Quadros` frames, at least 2 (if 1, make 2). One aspect ratio for all frames.
3. Size from `${CLAUDE_PLUGIN_ROOT}/formatos.json`: 4:5 = `instagram-feed-organico-tamanho` (1080x1350), 1:1 = `instagram-feed-quadrado-tamanho` (1080x1080).
4. Text limits from the same file, entry `instagram-feed-anuncio-texto`: headline on the image up to `titulo` characters, caption up to `texto_principal` characters. Any other line on the image: up to 90 characters. Count characters; cut and rewrite until they fit.

## 2. Brand (read-only, as the `marca-ler` skill)

The project root is the working folder path cut right before `/.tune-up/`. Read `<root>/.tune-up/estudio/marca/marca.json`. The panel only starts this action when the owner approved that file; do not look for approval yourself and never write there.

- Use `campos` values only: `cores.*` (hex) and `fontes.*`. Never invent a color or a font. Missing field: use the neutral one from `MARCA.md` next to it.
- Logo: if `logo` points to an `.svg` in `<root>/.tune-up/estudio/marca/assets/`, Read it and Write the same text to `q<N>/fonte/assets/logo.svg`. Any other logo type: leave the logo out and say so in `resultado.md`.

## 3. Copy

Write `copy.md`: for each frame, headline and at most 2 short lines; then the caption and the call to action from the briefing. A carousel tells one story: frame 1 hooks, the last frame has the call to action.

## 4. One HTML per frame

For frame N write `q<N>/fonte/index.html` (N = 1, 2, ...). Copy the shape of this skeleton:

```html
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <style>
    @font-face { font-family: "Brand Heading"; src: local("<first family of fontes.heading>"); }
    @font-face { font-family: "Brand Body"; src: local("<first family of fontes.body>"); }
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
- CSS only, colors only through the `--` variables, fonts only through the two `@font-face` names (never a bare generic family as the only font: the renderer would download a web font). In `src`, one `local("...")` per family of the brand field, comma-separated (`src: local("Helvetica Neue"), local("Arial");`); skip generic names like `sans-serif` or `system-ui` there.
- Safe container: all text inside `#root` with at least 80 px padding; give text boxes a `max-width` and let them wrap. No absolute positioning of text near the edges.
- Forbidden: `<script>`, any URL (`http`, `//`), web fonts, `gsap`, `data-layout-*` attributes, images other than `assets/logo.svg`. The QA fails on any of these.

## 5. Snapshot, check, QA (per frame)

`HF` = `${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes` (absolute path, no `npx`). Run each as a single command, no `cd`, no `;`, no `>`, no `|`.

1. `HF snapshot q<N>/fonte --at 0 --no-end -o q<N>/snap` -> `q<N>/snap/frame-00-at-0s.png`.
2. `HF check q<N>/fonte --json --strict`. Write its JSON output, unchanged, to `q<N>/check.json` (Write tool). Exit 1 means findings: keep the JSON anyway.
3. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py --source q<N>/fonte --png <working folder>/q<N>/snap/frame-00-at-0s.png --check-json q<N>/check.json --width <W> --height <H> --out q<N>/qa.json`. Exit 0 = green. Give `--png` with the absolute working-folder path: the file name has `-`, which the command list only accepts after that path.

Fix rounds: if the QA is not green, read the failed checks in `q<N>/qa.json`, edit `q<N>/fonte/index.html` (shorter text, smaller font, more room) and redo steps 1 to 3 (the check must be newer than the last edit). At most 2 fix rounds per frame. Never silence a check.

## 6. Finish

Write `resultado.md`: format, size, one line per frame (`q<N>/snap/frame-00-at-0s.png`, green or `precisa do seu olho` with the failed checks), the caption, and anything left out (logo, missing brand field). Then answer one line: `PRONTO: <k> de <n> quadros verdes` or `PRECISA DO SEU OLHO: <reason>`. Do not list or re-check files after that.
