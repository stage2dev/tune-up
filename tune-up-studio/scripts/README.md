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
# 1. strict check as JSON
npx --no-install hyperframes check <fonte> --json --strict > check.json

# 2. render (about 10 s of wall time for the example on macOS)
npx --no-install hyperframes render <fonte> -o <OUT>/video.mp4 --fps 30 --quality delivery

# 3. QA report (exit 0 green, 1 failed); needs ffmpeg and ffprobe on PATH
python3 scripts/qa_video.py --source <fonte> --video <OUT>/video.mp4 \
  --check-json check.json --out qa.json
```

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
| `freezedetect` | a still span of 2 s or more (`freezedetect=n=-60dB:d=2`), or the same damage lines |

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

```sh
# HyperFrames first; reserve if the binary is missing or the render fails
STUDIO_HYPERFRAMES_BIN=/path/that/does/not/exist \
  python3 scripts/video_ou_reserva.py --source <fonte> --slides <png dir> --out <OUT>/video.mp4
# -> <OUT>/video.mp4 and <OUT>/video.mp4.engine.json {"engine": "reserve", ...}
python3 scripts/qa_video.py --engine reserve --source <slide sources> --video <OUT>/video.mp4
```

`--engine reserve` replaces the HyperFrames check JSON (there is no
composition) with a check of the reserve tag. The example slides are in
`exemplos/forno-miudo/reserva-9x16/fonte/`; they were turned into PNGs with
headless Chrome (`--screenshot --window-size=1080,1920`,
`--host-resolver-rules="MAP * ~NOTFOUND"`). Measured on macOS: 3 slides, 10 s,
1.7 s wall time, QA all green.

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
  `qa_video.py`, `qa_imagem.py`, `reserva_slides.py` or `video_ou_reserva.py`.

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
