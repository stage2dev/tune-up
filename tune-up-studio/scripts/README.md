# Studio scripts

Standard library only (Python 3.9+). Tests: `python3 -m unittest discover -s tests`
from `tune-up-studio/` (no Chrome, no network).

## qa_imagem.py: still post (4:5, 1080x1350)

Run from `tune-up-studio/node` with the env of `node/README.md`
(`HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_NO_UPDATE_CHECK=1
HYPERFRAMES_NO_AUTO_INSTALL=1 HYPERFRAMES_SKIP_SKILLS=1`). Measured with
HyperFrames 0.9.6 on macOS.

```sh
# 1. one PNG, exactly 1 frame (also writes contact-sheet.jpg in OUT)
npx --no-install hyperframes snapshot <fonte> --at 0 --no-end -o <OUT>
#    -> <OUT>/frame-00-at-0s.png, 1080x1350 (size comes from data-width/height)

# 2. strict check as JSON (exit 1 on any error or warning)
npx --no-install hyperframes check <fonte> --json --strict > check.json

# 3. QA report (exit 0 green, 1 failed)
python3 scripts/qa_imagem.py --source <fonte> --png <OUT>/frame-00-at-0s.png \
  --check-json check.json --out qa.json
```

`render --format png-sequence` also works but writes duration x fps frames
(24 for 1 s at 24 fps); its first frame is byte-identical to the snapshot.
Use `snapshot` for a still.

Both commands write `<fonte>/.hyperframes/` (git-ignored).

Checks in `qa.json`:

| name | fails when |
| --- | --- |
| `png_size` | not a whole PNG (every chunk up to `IEND`, CRCs, IDAT inflates to exactly what IHDR needs) or not `--width` x `--height` (default 1080x1350) |
| `layout_allow_count` | anything that can silence the layout audit: `data-layout-allow\|ignore\|bleed\|boundary\|check*` (also on an ancestor), `layoutAllow`-style dataset names, `dataset`, `setAttribute` |
| `no_script` | any `<script` in the post source (the post is CSS only; post QA only) |
| `no_gsap` | the word `gsap` anywhere in the source |
| `network_lint` | `http(s)://`, `//host` in src/href/url(), `url(http`, `fetch(`, `XMLHttpRequest`, `WebSocket`, `EventSource`, `sendBeacon`, `import(` |
| `hyperframes_check` | check not strict, browser skipped, `ok` false, any error/warning finding, `saved.report` not under `--source` (check of another piece), check JSON older than a source file (source edited after the check); for video also `layout.duration` not `--duration` |

How the check reports problems: text that leaves its box gives a layout
`text_box_overflow` error; text past the canvas edge gives a
`canvas_overflow` warning. `data-layout-allow-overflow` on the text silences
both (check exits 0), so `layout_allow_count` is what catches it.

## qa_atencao.py: attention checks (`--atencao`)

Imported by `qa_imagem.py` and `qa_video.py`, never run on its own (standard
library plus `cores.py`; the CSS parser is in `qa_css.py`, the reel checks in
`qa_cenas.py`, the motion-script checks in `qa_script.py`). The checks run only
with `--atencao`: without the flag both QA scripts return exactly what they
returned before. Everything is judged from the HTML and the job's text files,
with no browser. Thresholds are constants at the top of the file, to be tuned
after measuring real pieces.

```sh
python3 -I scripts/qa_imagem.py --source <q1/fonte> --png <png> --atencao --out qa.json
python3 -I scripts/qa_imagem.py --final <work folder> --atencao --out final.json
python3 -I scripts/qa_video.py --source <fonte> --video <mp4> --duration 10 --atencao --out qa.json
```

The parser does not resolve the cascade, so pieces follow one contract: the
post `<h1>` takes its `font-size` from its own `style=""` or from a rule whose
last compound names `h1`; a reel clip takes `font-size` and `animation` from
its own `style=""` or a rule whose selector is exactly `#<clip id>`; `#root`
declares a `font-size` in px at or above the floor.

| name | piece | fails when |
| --- | --- | --- |
| `titulo` | post frame | not exactly one `<h1>`, headline over 40 characters, or its `font-size` under 88 px or under 1.8x the largest other text |
| `fonte_minima` | post, reel | a `font-size` not in px, a `font:` shorthand, `#root` without a px size, post text under 28 px, reel `_titulo`/`_destaque` under 96 px or other text under 44 px |
| `palavras` | post frame | more than 20 visible words on the cover (`q1`), 30 on other frames |
| `cores_marca` | post, reel | a CSS color (or `fill`/`stroke`/`stop-color`) outside the brand colors (missing ones fall back to the neutral palette), a color name, `rgba`/`hsla` or 8-digit hex with alpha, `color-mix(`, or no `marca.json` |
| `tiques` | post, reel | a phrase of the closed AI-tic list (whole words, no case or accents) or `!` in the art |
| `numeros` | post, reel | a 2+ digit number in visible text that is not a whole number of `entrada.md` or of the brand's text values (a number written in pieces, `R$ 12<small>,90</small>` or a phone with other separators, passes when its digits are a known number), or `entrada.md` missing or empty (said out loud, never a silent green) |
| `recurso_visual` | post frame, Meta ad piece (`anuncio.py --final`), reel scenes 1, payoff and last | no visual device: a business photo, an inline `<svg>` or an empty shape with a background covering 2-85% of the frame (a band of 90% width or height only when rotated, round or cut by `clip-path`), a text of 200 px or more, or a highlighter `<span>` in the `<h1>`; the logo never counts |
| `legibilidade` | post frame, reel | a text of 3+ words without `text-wrap: balance`/`pretty` (on `#root`, `html`, `body` or its own rule), a text with `clip-path`/`overflow: hidden` without room (line-height under 1.2 and padding under .1em top / .15em bottom), or a headline (post `<h1>`, reel `_titulo`/`_destaque`) with two sentences on one line (no `<br>`) or a 1-2 letter word before a breakable space (glue it with `&nbsp;`) |
| `ocupacao` | post frame (on its PNG), reel (on the MP4 at 70% of each scene) | a rectangle of plain background (the frame's most common color, tolerance 8) bigger than 15% of the post's safe area (80 px margin) or 18% of the reel's safe box (`scripts/qa_vazio.py`, pure-Python PNG reading; a PNG it cannot read is reported `não medido`, never red) |
| `marca` | post (`--final`, any frame), reel (last scene) | `campos.nome` of `marca.json` is not written on the art (the `marca` clip of the reel is not counted in `palavras_cena`) |
| `layout_post` | post frame | `#root` without exactly one `l-*` arrangement |
| `estrategia` | post (`--final`), reel | `estrategia.md` missing or without `objetivo`, `publico`, `promessa`, `arquetipo`, `gancho 1-3`, `escolhido`, `cta` |
| `cta` | post (`--final`) | `#cta` with text missing on the last frame, present on another one, or with `border-radius`; or a deadline of `entrada.md` ("só esta semana", "até 15/12", "até sábado", "últimos dias") missing from the art |
| `sequencia_layout` | post (`--final`), reel | the same `l-*` twice in a row; a reel with fewer than 2 (10 s) or 3 (15 s) arrangements |
| `arraste` | post (`--final`) | a carousel whose cover does not say `arraste` |
| `legenda` | post (`--final`) | `copy.md` without `## Legenda`, first line over 125 characters, caption over 1000, more than 5 hashtags, or a tic |
| `cenas` | reel | not 4-5 scenes (10 s) or 5-6 (15 s), scene 1 over 2 s, last under 2.5 s, any under 1.5 s, gaps, a sum off `D` by more than 0.05 s, or a text clip outside `s<N>_<role>` |
| `gancho` | reel | scene 1 title + accent word over 40 characters, a scene 1 text hidden at 0% (opacity, closed `clip-path`, `visibility`, `display`), or the logo or brand name on screen at 0 s |
| `palavras_cena` | reel | a scene with more than max(6, 3 x its seconds) words, all text layers together |
| `cta_final` | reel | the last scene without `_titulo` and `_contato` text, either of them with `border-radius` or `background`, a contact naming a word, handle or phone digits that are not in `entrada.md` or the brand kit (`link na bio` and connectors like `pelo`, `no` are free), a deadline of `entrada.md` missing from the video, or no `entrada.md` |
| `transicoes` | reel, render engine only | fewer than 2 kinds among `tr<N>`, the same kind twice in a row, one not 0.4-0.8 s long and centred on a cut, or a frame-sized one that covers the whole frame for more than 0.15 s |

In `--final`, the whole-post checks come as one `peca` item: it does not count
in `k de n` but turns the line red (`PRECISA DO SEU OLHO: 3 de 3 verdes, peca:
cta, legenda`). `anuncio.py --exportar` (and `--final`) also refuses AI tics
and numbers that are in neither `entrada.md` nor the brand kit.

### `--achados`: the check findings, short

`python3 -I scripts/qa_imagem.py --achados <fonte>` prints only the `warning` and `error` findings of the newest
report `hyperframes check` saved under `<fonte>/.hyperframes/` (at most 20 lines), or `nenhum achado acima de
info`. Exit 0 when clean, 1 otherwise (also when no check ran or the source changed after it). The check's own
JSON is long; sessions read this instead.

### `--pares`: the contrast table

`python3 -I scripts/qa_imagem.py --pares <work folder>` reads the approved
`marca.json` of the project that holds the work folder and prints every
text-on-background pair of brand colors at 3:1 or more, best first, one per line
(`texto cores.text #3B2417 sobre cores.bg #FFF8EC: 13.71:1 normal`). `normal`
(4.5:1 or more) works for any text; `so_titulo` (3 to 4.49:1) only for a headline
of 88 px or more. Exit 0, or 2 when the brand kit is not found. Sessions pick
pairs from this table and never work a ratio out themselves.

## Network: the lint is not the guarantee

Measured with `tests/fixtures/defect-external-fetch` (URL built as
`"ht" + "tp://"` at runtime):

- HyperFrames does not block page requests. With a listener on the LAN
  address, `snapshot` and `check` both reached it.
- `check` sometimes reports a runtime `request_failed` error, but not
  always (silent under an OS network block). Do not rely on it.
- The lint catches `fetch(`, not the hidden URL.
- What stops the request is the OS sandbox around the browser. Under a
  macOS Seatbelt profile that denies outbound network except loopback,
  the page saw the fetch fail immediately. HyperFrames itself needs
  loopback: it serves the composition on `127.0.0.1`.
- Fonts: when a composition names a generic family (for example
  `Georgia, serif`), the HyperFrames compiler swaps in a Google font
  (EB Garamond here) and downloads it on first use into
  `~/.cache/hyperframes/fonts` (log: "Fetched ... from Google Fonts").
  Later runs read the cache. Declare fonts
  with `@font-face { src: local(...) }` under your own family name, as the
  example post does.

## qa_video.py: silent reel (9:16, 1080x1920, 10 s)

```sh
# 1. strict check (HyperFrames saves the report under <fonte>/.hyperframes/)
npx --no-install hyperframes check <fonte> --json --strict

# 2. render (about 10 s of wall time for the example on macOS)
npx --no-install hyperframes render <fonte> -o <OUT>/video.mp4 --fps 30 --quality delivery --experimental-fast-capture=false

# 3. QA report (exit 0 green, 1 failed); needs ffmpeg and ffprobe on PATH
python3 scripts/qa_video.py --source <fonte> --video <OUT>/video.mp4 \
  --out qa.json --sheet <OUT>/folha.png
```

The check verdict comes from the newest report HyperFrames saved under
`<fonte>/.hyperframes/artifacts/checks/` (or the one `--check-json` names in
`saved.report`), never from a copy the session wrote. `--sheet` writes a contact
sheet of the MP4 (frame 0, then one every 0.5 s from 0.25 s, 5 per row) and adds the `contact_sheet`
check; with `--atencao` also `<sheet>_cortes.png`, 0.35 s before and after each cut (just outside the
transition), where a half-gone line or a transition leftover shows. The report ends with `linha`: `PRONTO: video verde (<engine>)` or
`PRECISA DO SEU OLHO: <failed checks>`.

Checks in `qa.json` (plus `layout_allow_count`, `no_gsap`, `network_lint` and
`hyperframes_check`, shared with `qa_imagem.py`):

| name | fails when |
| --- | --- |
| `video_size` | not `--width` x `--height` (default 1080x1920) |
| `duration` | more than 0.2 s away from `--duration` (default 10) |
| `fps` | `r_frame_rate` is not `--fps` (default 30) |
| `frames` | frames decoded by `ffprobe -count_frames` not `--duration` x `--fps` (a cut MP4 keeps its header duration) |
| `codec` | not h264 yuv420p |
| `faststart` | `moov` box is not before `mdat` |
| `no_audio` | any audio stream |
| `blackdetect` | a black span of 0.5 s or more (`blackdetect=d=0.5:pix_th=0.10`), or ffmpeg reports `partial file` / `Invalid data` |
| `freezedetect` | a still span of 1.2 s or more (`freezedetect=n=-70dB:d=1.2`; -70 dB so a small pulse counts as motion, measured on the example), or the same damage lines |

Tool paths are not options: `qa_video.py` and `reserva_slides.py` take
`ffmpeg`/`ffprobe` from `PATH`, `video_ou_reserva.py` takes HyperFrames from
`STUDIO_HYPERFRAMES_BIN` or `../node`. An option would let a session point
it at `python3` and a file it wrote.

`hyperframes check --strict` does not catch a black second: the fixture
`tests/fixtures/defect-black-second` passes the check and fails only
`blackdetect` ("black 4-5 s").

## Animation without GSAP (measured with 0.9.6)

- CSS `@keyframes` are seeked frame by frame. Frames of the MP4 at 0.2, 1, 3.5,
  5, 7 and 9.8 s all differ and match `snapshot --at` of the same times.
- A composition with no `window.__timelines` must carry `data-no-timeline` on
  its root, even when it moves; without it `check` fails with
  `missing_timeline_registry`.
- Give each animation `animation-fill-mode: both` and a finite count. With
  delays of 3.3 s, 3.7 s and 6.6 s, a seek before the delay showed the end
  state, while delays up to 0.8 s held the start state. Late entrances in the
  example run over the whole 10 s with no delay and use keyframe percentages.
- A clip's CSS animation clock starts at its own `data-start` (measured on
  2026-11-11: an entry of 1 s on clips starting at 0, 3 and 6 s was half done
  at 0.5, 3.5 and 6.6 s). The video skill gives every element its own clip
  and one animation as long as the clip, with no delay.
- An inline `<svg>` clip renders still: its CSS animation is ignored in the
  snapshot and in the MP4 (measured 2026-11-11: a translate, an opacity and a
  scale on `<svg>` clips never moved). Motion goes to text clips and empty
  `div` shapes cut by `clip-path`.
- A clip with child elements gives the `nested_structure_needs_subcomposition`
  lint warning (fails `--strict`); `check` also warns `first_frame_empty` when
  frame 0 shows only the background and `line_unread` when the last line is
  on screen under 2 s.
- Lines that replace each other (captions) are clips: `class="clip"`,
  `data-start`, `data-duration` and an `id`. Caption lines stacked in one box
  with opacity-only fades failed `check` with `content_overlap`; without an
  `id` a clip gives the `studio_missing_editable_id` warning.

## Inside the Claude Code sandbox (`claude --bg`, CLI 2.1.322)

Proof script: `painel/tests_reais/prova_video_bg.py`. With plain
`"sandbox": true`, `hyperframes render` fails with `listen EPERM: operation
not permitted 127.0.0.1`: render serves the composition on loopback and the
sandbox network block forbids the bind. `Skill(hyperframes)` in `deny` blocks
the skill ("Skill execution blocked by permission rules").

The fixture now uses `"sandbox": {"rede_local": true}`, which adds
`sandbox.network.allowLocalBinding` (macOS only; no effect on Linux). Measured
on macOS with haiku: the example reel renders in the session (21 s wall time
for the whole session) and passes `qa_video.py`. The price, from a page
snapshotted in the sandbox: requests to `192.0.2.1` and `example.com` fail at
once (`TypeError`), but requests to another listener on `127.0.0.1` and on this
machine's own LAN address both arrive. Any local service without
authentication is reachable from a composition.

## reserva_slides.py and video_ou_reserva.py: FFmpeg fallback

When HyperFrames is missing or its render fails, the reel is built from slide
PNGs whose text is already drawn (the local ffmpeg 8.1 build has no
`drawtext`). Each slide gets a slow zoom (`zoompan` on a 2x upscale) and a
`xfade` crossfade; the graph goes to `<out>.graph.txt` and is passed with
`-filter_complex_script`, so the command line has no `;`. Every `-i` is
preceded by `-protocol_whitelist file,pipe`. The MP4 carries
`comment=tune-up-studio reserve`. Filters used, all listed by
`ffmpeg -filters` here: `scale`, `crop`, `zoompan`, `setsar`, `format`,
`xfade`, `trim`.

`--tempos T1,T2,...` gives each slide the length of its scene, so a short hook
and a long call to action reach the MP4 (without it every slide lasts the same).
One length per slide, adding up to `--duration` within 0.05 s, or exit 2 with the
reason. Each cut is centred on the scene boundary, as in the composition: the
first slide lasts `T1 + xfade/2`, a middle one `Ti + xfade`, the last
`Tn + xfade/2`; the xfade before slide k starts at the sum of the lengths before
it minus `xfade/2` (`1.5,2.5,2.5,3.5` with the default 0.5 s gives cuts at 1.25,
3.75 and 6.25 s). A middle scene of `xfade` or less, or a first/last one of
`xfade/2` or less, is refused. Slide frames are rounded up, so no slide ends
before its cut. `video_ou_reserva.py` does not pass `--tempos`.

```sh
python3 scripts/reserva_slides.py --slides <png dir> --out <OUT>/video.mp4 \
  --duration 10 --tempos 1.5,2.5,2.5,3.5
# HyperFrames first; reserve if the binary is missing or the render fails
STUDIO_HYPERFRAMES_BIN=/path/that/does/not/exist \
  python3 scripts/video_ou_reserva.py --source <fonte> --slides <png dir> --out <OUT>/video.mp4
# -> <OUT>/video.mp4 and <OUT>/video.mp4.engine.json {"engine": "reserve", ...}
python3 scripts/qa_video.py --engine reserve --source <composition> --video <OUT>/video.mp4
```

`--engine reserve` adds a check of the reserve tag and still needs the strict
check of the composition the slides were snapshotted from (the video skill makes
the slides with `snapshot --at <one time per scene>` of that composition). The
older example slides are in
`exemplos/forno-miudo/reserva-9x16/fonte/`; they were turned into PNGs with
headless Chrome (`--screenshot --window-size=1080,1920`,
`--host-resolver-rules="MAP * ~NOTFOUND"`). Measured on macOS: 3 slides, 10 s,
1.7 s wall time, QA all green.

## montar.py: the composition kit (post and reel)

```sh
# from the working folder (inside <project>/.tune-up/)
python3 -I scripts/montar.py --tipo post  --peca q1/peca.json --heroi heroi.svg --out q1/fonte --formato=4:5
python3 -I scripts/montar.py --tipo video --peca peca.json --heroi heroi.svg --out fonte --duracao 10
```

Writes `<out>/index.html` from the texts (`peca.json`, slots in
`referencias/kit-post.md` and `kit-video.md`) and one drawing (`heroi.svg`,
method in `referencias/heroi.md`, examples in `kit/herois/`). It prints one note
per line (the sizes it chose, the variant) and exits 1 with the reason when an
input is missing, too long or not allowed. Modules: `kit_base.py` (brand, color
pairs, text fitted to a box, the hero's checks, channel icons), `kit_medida.py`
(advance widths read from the font file `local("Name")` resolves to: `name`,
`cmap`, `hmtx`, `OS/2` with `struct`; unknown face: the average letter),
`kit_post.py` (compositions `oferta`, `palco`, `numero`; frames `unico`, `capa`,
`ponto`, `fecho`), `kit_palco.py` and `kit_video.py` (the reel: scenes `gancho`,
`rampa`, `lista`, `oferta`, `final`; cuts at 1.875, 4.375, 6.875 s) and
`kit_estilos.py` (the style scene, picked by `"estilo"` in `peca.json`: a chat,
a list, a counter, before and after, a screen with a cursor, a poster, steps, a
myth; with a style the cuts are 1.625, 4.375, 6.875 s). Render with
`--workers=1`: several render workers gave MP4s that differ from run to run.

The hero file is data, never code: only `g`, `path`, `rect`, `circle`, `ellipse`,
`line`, `polyline`, `polygon`; a fixed attribute list; colors only by class
(`p a t b s`, `lp la lt lb ls`); ids `h_*`; no `style`, `url(`, event, `use`,
`image` or `text`. `--out` must stay inside the working folder. Measured
2026-11-12 with HyperFrames 0.9.6 on macOS: a kit reel renders in about 5 s,
`check --strict` clean, `qa_video.py --atencao` green with 43 checks, two renders
byte for byte the same.

## fontes.py: brand fonts for a post frame

`python3 -I scripts/fontes.py --trabalho <work folder>` reads `fontes.heading` and
`fontes.body` from the approved `marca.json` of the project that holds the work
folder and prints the two `@font-face` lines (`Brand Heading`, `Brand Body`) the
post skill pastes. Named families stay first; a generic family (`system-ui`,
`sans-serif`, `serif`, `monospace`, `-apple-system`, `ui-*`, ...) cannot go in
`local()`, so it becomes a fixed stack: sans = Helvetica Neue, Arial, Liberation
Sans, DejaVu Sans; serif = Georgia, Times New Roman, Liberation Serif, DejaVu
Serif; mono = Menlo, Courier New, Liberation Mono, DejaVu Sans Mono. It also
prints one `/* fonte da marca <field>: ... generica ... */` line per field with a
generic family. A field with only named fonts gets no stack, so a font missing on
the machine still fails the snapshot. Exit 2 when `marca.json` cannot be read.
Measured 2026-11-11 with HyperFrames on macOS: the Forno Miúdo body
(`system-ui, -apple-system, 'Segoe UI', sans-serif`) as `local("Segoe UI")` alone
gave `Fonts FAILED: Brand Body`; with the printed lines, `Fonts: 2 loaded` and
`qa_imagem.py --final` `PRONTO: 1 de 1 quadros verdes`.

## Bash positive list for studio actions (`regras/bash-estudio.json`)

Six `negar` hook rules (lookahead regexes on `command`) that every studio
action copies; the fixture `painel/tests_reais/acao_estudio.json` carries the
same list (checked by `tests/test_regras_bash.py`). Allowed, nothing else:

- `<abs path>/tune-up-studio[/<version>]/node/node_modules/.bin/hyperframes`
  with `render`, `check`, `lint`, `validate`, `inspect`, `snapshot`, `info`,
  `compositions` (no `--describe`, no `--docker`); the binary must not be
  under `{trabalho}`, so a script the session wrote cannot pass as it. Other
  names of the same folder are refused too: any path with a `/trabalhos/`
  segment (covers `/tmp` vs `/private/tmp` and `/System/Volumes/Data/...`)
  and anything under `/proc/`, `/dev/` or `/System/Volumes/`. This is still a
  text match, not the exact install path; see the limits below.
- `ffmpeg` where every `-i` comes right after `-protocol_whitelist file,pipe`.
- `ffprobe`.
- `python3 -I <abs path>/tune-up-studio[/<version>]/scripts/` with
  `qa_video.py`, `qa_imagem.py`, `reserva_slides.py`, `video_ou_reserva.py`,
  `fontes.py`, `anuncio.py` or `fotos.py`.

Every argument is either an option without `/`, a relative path without `:`,
or a path inside `{trabalho}`. No `..`, `//`, `~`, quotes, `$`, `;`, `&`,
`|`, redirects or newlines. Limits: `npx` and a bare `hyperframes` are refused
(both can resolve a binary planted in `{trabalho}`); an alias of `{trabalho}`
not listed above (a symlinked parent, a bind mount) is not caught, the exact
plugin path would need a marker resolved by the core; the content of the filter
graph file is not inspected (a `movie=` source there is stopped only by the
sandbox network block); an action that puts `Bash` in `permitir` turns on the
core's compound/script lock, which refuses `python3` and absolute-path
binaries, so studio actions must not do that.

## preparar_estudio.py: "Preparar estúdio"

Deterministic, not an AI session, and the only studio step with network:
`npm ci --ignore-scripts` then `npm audit signatures` (no install script runs;
see `node/README.md`). Then it runs `verificar_ambiente.py` and writes
`<dados>/ambiente.json` (`pronto`, `node_dir`, `hyperframes`, each step with
its exit code, the checker items). If signatures fail, `node_modules` is
removed and `pronto` is false.

```sh
python3 -I scripts/preparar_estudio.py --dados <pacote>/dados [--projeto <pasta>]
# asks before downloading; --sim skips the question (the module command passes it)
```

Install folder: `node/` in place, unless the studio is under `~/.claude` (the
plugin cache, protected by the sandbox); then `package.json` and the lockfile
are copied to `<dados>/tune-up-studio/<version>/node` and the install goes
there (`ambiente.json` says where). It does not download Chrome.

From the panel: module `estudio` (`painel/modulos/estudio/modulo.py`), command
`preparar` with `{"confirmar": true}`; without it nothing runs. The command
holds `<dados>/ambiente.lock` and passes it to the background run, so a second
click while it runs is refused. Output goes to `<dados>/ambiente.log`.

## descobrir_marca.py: brand kit discovery

Deterministic, no network, no AI. Reads what the project already declares and
writes `<raiz>/.tune-up/estudio/marca/`: `marca.json`, `MARCA.md` (pt-BR) and
`assets/logo.<ext>` (a copy of the logo, when there is one).

```sh
python3 -I scripts/descobrir_marca.py --projeto <pasta> [--saida <pasta>]
# exit 0 written; 2 refused (missing folder, unreadable marca.json: nothing overwritten)
```

Sources (readers in `marca_leitores.py`): custom properties in `:root` and
`@theme` (also in `<style>` of `index.html`; `.dark` is skipped; one level of
`var(--x)` is followed), `h1`/`body` `font-family` rules, `tailwind.config.*`
(quoted colors, `DEFAULT`, font arrays), `index.html` (`<title>`, meta
description/theme-color/og:site_name, an `<img>` with `logo` in src/class/id,
icon links), web manifest, a file named `logo*`/`brand*`/`marca*`, and the
name/description of `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`,
`composer.json`. Walk: depth 4, at most 4000 entries, skips `node_modules`,
`dist`, `vendor`, `build`, `.git`, `.tune-up` and similar; no symlinks; an
image outside the project, a URL or a `..` path is never taken as the logo.

Fields: `nome`, `descricao`, `cores.bg|surface|primary|text|accent`,
`fontes.heading|body`, `logo`. Each is `{valor, fonte, confianca, travado}`,
with `fonte` as `arquivo:linha` (a logo found only by file name cites the
file). `confianca`: `alta` (declared under a brand name), `media` (inferred),
`baixa` (library default from a partial shadcn/Tailwind list, a package slug,
an icon), `faltando` (`valor` and `fonte` null). A field with `"travado": true`
is kept on the next run. No color, font or logo at `alta`/`media` gives
`"modo": "sem_marca"` and a declared `paleta_neutra`, which fills no field.

`cores.py` turns `#rgb[a]`, `#rrggbb[aa]`, `rgb()`, `hsl()`, a bare HSL trio
(shadcn) and `oklch()` into `#RRGGBB`; anything else is `None`.

The studio's Marca tab also writes `marca.json`: every field the owner changes
gets `"fonte": "dono"` and `"travado": true`, plus three keys that a new
discovery keeps as they are: `fotos` (`[{arquivo: "fotos/<name>", principal}]`,
up to 8, the first is the main one), `tom` (`{valor: ["acolhedor", ...]}`) and
`letras_do_projeto` (the font pair found before the owner picked another one).
Logo and photos the owner uploads land in `marca/assets/` and `marca/fotos/`
through the panel's upload route (file name = 16 hex of the sha256); studio
sessions only read them (their sandbox writes only to the job folder).

## cores_da_logo.py: "Pegar as cores da logo"

Deterministic, no network, no AI, same file = same answer.

```sh
python3 -I scripts/cores_da_logo.py <logo.png|logo.svg>
# exit 0: {"cores": [[hex, weight], ...], "papeis": {"primary", "accent", "text", "bg"}}
# exit 2: refused, with the reason in Portuguese (shown on the screen)
```

- SVG: `fill`, `stroke` and `stop-color` (attributes and CSS) counted by
  occurrence, read by `cores.py`; `var()`, `url()` and color names other than
  white/black are skipped, and a shape with no fill is not counted as black.
- PNG: decoded with `zlib` only (color types 0, 2, 3, 4, 6; bit depth 1 to 16;
  `tRNS` honored; pixels under 50% alpha skipped), counted on a grid of up to
  200 x 200 pixels. Interlaced PNGs and images above 2.5 million pixels are
  refused (pure-Python unfiltering takes about 4 s at that size on a laptop).
- Similar colors (anti-aliasing) merge into the most frequent one. Roles:
  `primary` = most frequent colorful color, `accent` = the next colorful one
  far from it, `text` = the darkest if dark enough, `bg` = the lightest if light
  enough. A role with no fitting color is left as it was; `surface` never changes.
- JPEG and WebP are not read: the standard library has no decoder for them
  (baseline JPEG means a Huffman + IDCT decoder, WebP a VP8/VP8L one), and a
  dependency is out. With a JPEG or WebP logo the Marca tab hides the button;
  the owner picks the colors by hand.
