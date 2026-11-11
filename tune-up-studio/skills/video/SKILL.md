---
name: video
description: "Makes a silent vertical reel (9:16, 1080x1920 MP4, 10 or 15 s) from a briefing, using only the owner-approved brand: script in scenes, CSS-only motion, render or slide reserve, and the studio QA. Runs unattended from the panel actions estudio.video and estudio.video-motion. Use on: vídeo, reel, reels, story em vídeo."
allowed-tools: Read, Bash(${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_video.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/reserva_slides.py *), Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fontes.py *)
---

# Reel (9:16 video)

This runs in the background. Nobody answers questions: never ask anything, never wait for a reply, never run `ls` or any command outside the list below. When a step fails twice, write it down and finish. Piece copy is in Brazilian Portuguese; your final answer is one short line in Brazilian Portuguese.

The prompt gives: the working folder (`{trabalho}`, your current folder), `Motor` (`hyperframes` or `reserva`), `Duracao` (`10` or `15` seconds, called `D` below) and the briefing file. Write only inside the working folder. Use relative paths made of letters, digits, `_`, `.` and `/` only (no `-`, no `..`).

`Motor: reserva` means this project did not turn on the local render (`estudio.video_rede_local` in `painel.json`): never run `render`, it cannot open its local port here. The video is made from still slides of the same composition (step 6b).

## 1. Inputs

1. Read the briefing file named in the prompt.
2. Size from `${CLAUDE_PLUGIN_ROOT}/formatos.json`, entry `instagram-reels-tamanho` (1080x1920). Safe zone from `instagram-reels-zona-segura`: top margin = the larger of `margem_topo_px` and `margem_topo_pct`% of 1920, bottom margin the same with `margem_base_*` (today 269 px top, 384 px bottom). Sides: 90 px. No text outside that box at any moment.
3. Text limits: headline up to 40 characters, any other line up to 60. Count characters; cut and rewrite until they fit.

## 2. Brand (read-only, as the `marca-ler` skill)

The project root is the working folder path cut right before `/.tune-up/`. Read `<root>/.tune-up/estudio/marca/marca.json`. The panel only starts this action when the owner approved that file; do not look for approval yourself and never write there.

- Use `campos` values only: `cores.*` (hex) and `fontes.*`. Never invent a color or a font. Missing field: use the neutral one from `MARCA.md` next to it.
- Fonts come from a script: run `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/fontes.py --trabalho <working folder>` (absolute path) once and paste every printed line as is at the top of the `<style>`; never write an `@font-face` yourself. For each `generica` line, write in `resultado.md` that the brand font of that field is generic and the video uses the local stack.
- Logo: if `logo` points to an `.svg` in `<root>/.tune-up/estudio/marca/assets/`, Read it and Write the same text to `fonte/assets/logo.svg`. Any other logo type: leave it out and say so in `resultado.md`.

## 3. Script in scenes

Write `roteiro.md`, one row per scene: start, length, text, motion. `D` = 10: 4 scenes of 2.5 s. `D` = 15: 5 scenes of 3 s.
- Scene 1 is the hook and it is on screen in the very first frame (the first frame is the thumbnail): a question or a strong claim from the briefing.
- One idea per scene: a headline and at most one short line. Never repeat a fact already shown.
- The last scene is the call to action from the briefing, readable for at least 2 s.
- Never invent a fact, price, date or promise. A short briefing gets simpler scenes, not made-up ones.

## 4. Composition: `fonte/index.html`, CSS only

Measured with HyperFrames 0.9.6; follow it exactly or the check fails:
- Root: `<div id="root" data-composition-id="video" data-start="0" data-duration="D" data-width="1080" data-height="1920" data-fps="30" data-no-timeline>`, `#root` 1080x1920, `position: relative; overflow: hidden`, background and colors only through `--` variables set from the brand.
- Every visible element is a direct child of `#root` with `class="clip"`, a unique `id`, `data-start` and `data-duration` (seconds), `position: absolute`. A clip holds plain text or is an `<img src="assets/logo.svg">` or an empty shape: no child elements inside a clip (no `<span>`, `<em>`, `<br>`).
- Scene N = the clips with that scene's `data-start` and `data-duration`. A decor shape or the logo that stays all video: `data-start="0" data-duration="D"`.
- A clip's animation clock starts at its own `data-start`. Give each clip exactly one animation: `animation: <name> <its data-duration>s <easing> 0s 1 both`, no delay, with keyframe percentages for entry, hold and exit (exit in the last 10 to 15%).
- Hook clips: their `0%` keyframe is fully visible and inside the safe box (settle from `scale(1.06)`, `letter-spacing`, a color change), never `opacity: 0` at 0%.
- The last line must stay fully visible for at least 2 s: start its entry in the first 15% of the last scene and give it no exit.

More movement than a sequence of fades. Required:
- Every scene enters with a different motion from the scene before. Use at least 4 of: wipe (`clip-path: inset(0 100% 0 0)` to `inset(0)`), mask rise (`clip-path: inset(100% 0 0 0)` plus `translateY(80px)` to none), scale pop with overshoot (`cubic-bezier(.3,1.4,.5,1)` from `scale(.3)`), slide from the side (`translateX(-200px)`), a big number that zooms and turns (`scale(.3) rotate(-10deg)`), letter-spacing settle.
- Inside a scene, vary rhythm: the headline enters at 0%, the second line later (25 to 40%).
- Between scenes, a transition clip: a full-frame brand-color panel of 0.6 s centered on the cut (`data-start` = cut - 0.3), keyframes `translateX(-100%)` -> `0` (45-55%) -> `100%`, placed last in the HTML so it covers the cut.
- One background shape that lives the whole video and drifts or scales slowly; the logo may turn a few degrees.
- The call to action pulses once or twice (`scale(1.07)` and back) after it lands.

Forbidden: `<script>`, any URL (`http`, `//`), web fonts, `gsap`, `data-layout-*` attributes, images other than `assets/logo.svg`, a bare generic family as the only font. The QA fails on any of these.

## 5. Loop: lint, check, look (at most 2 fix rounds)

`HF` = `${CLAUDE_PLUGIN_ROOT}/node/node_modules/.bin/hyperframes` (absolute path, no `npx`). Run each as a single command, no `cd`, no `;`, no `>`, no `|`.

1. `HF lint fonte`
2. `HF check fonte --json --strict`. Do not copy its output anywhere: HyperFrames saves the report under `fonte/.hyperframes/` and the QA reads it from there. Exit 1 or any `warning`/`error` finding means fix. The findings are in the output it prints: read them there (no `grep`, no `cat`; those commands are refused).
3. `HF snapshot fonte --at <T> --no-end -o snap`, where `<T>` is a comma list with one time per scene at 60% of the scene (10 s: `1.5,4,6.5,9`; 15 s: `1.8,4.8,7.8,10.8,13.8`) plus `0`. Then Read `snap/contact-sheet.jpg` and look: text cut or outside the safe box, two texts on top of each other, empty frame, wrong brand color.

Fix round = edit `fonte/index.html` and redo 1 to 3. At most 2 fix rounds for the whole piece; never silence a finding. Never write inside `.hyperframes/`.

## 6a. `Motor: hyperframes`: render and QA

1. `HF render fonte -o video.mp4 --fps 30 --quality delivery --quiet`
2. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_video.py --source fonte --video video.mp4 --duration D --out qa.json --sheet folha.png`
3. Read `folha.png` (one frame per second of the MP4). If the QA is red and fix rounds are left, fix, redo step 5 and this step.

If the render fails twice, make the video by 6b and say in `resultado.md` that the render failed and the reserve was used.

## 6b. `Motor: reserva`: slides and QA

1. `HF snapshot fonte --at <T> --no-end -o slides` with the scene times of step 5 without the `0`.
2. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/reserva_slides.py --slides slides --out video.mp4 --duration D`
3. `python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_video.py --engine reserve --source fonte --video video.mp4 --duration D --out qa.json --sheet folha.png`, then Read `folha.png`.

## 7. Finish

1. Write `resultado.md`: motor and why (`reserva`: "o projeto não ligou estudio.video_rede_local no painel.json; o vídeo saiu da reserva em slides, sem movimento dentro das cenas"), length and size, one line per scene from `roteiro.md`, `video.mp4` and `folha.png`, the `linha` of `qa.json` and its failed checks, anything left out (logo, missing brand field) and each generic brand font.
2. Answer with the `linha` of `qa.json`, exactly (`PRONTO: ...` or `PRECISA DO SEU OLHO: ...`). Do not list or re-check files after that.
