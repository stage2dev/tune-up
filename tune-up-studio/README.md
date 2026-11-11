# tune-up-studio

Status: work in progress. A plugin of the `tune-up` marketplace that depends on
`tune-up` (it adds a module to its panel):

```
/plugin install tune-up-studio --marketplace stage2dev/tune-up
```

Platforms: the studio runs on macOS, Linux and WSL2 only. Native Windows is not
supported (the Claude Code sandbox it relies on does not run there); the
`tune-up` panel itself still runs on Windows.

## What it is

A studio module for the `tune-up` panel that turns a project's brand source of
truth into finished pieces: a still post (4:5, 1080x1350 PNG) and a silent
vertical reel (9:16, 1080x1920, 10 s MP4). Compositions are HTML written from
scratch (CSS `@keyframes` only, no GSAP, no network), rendered locally with a
pinned [HyperFrames](node/README.md) 0.9.6, then judged by deterministic QA
scripts. If HyperFrames is missing or fails, the reel is built from slide PNGs
with FFmpeg (`scripts/video_ou_reserva.py`).

The proof project is a fictional bakery in `exemplos/forno-miudo/`. Piece
text in the example is Brazilian Portuguese; code and docs are English.

## Requirements

Measured on macOS (10 cores, 16 GB):
Node v26.5.0, FFmpeg 8.1.2 (with `ffprobe`), Python 3.9+ (standard library
only), headless Chrome in `~/.cache/hyperframes/chrome`. Linux and WSL2 are
planned; they are not verified here. On Linux the sandbox also needs `bwrap`
and `socat`.

Check a machine (report in Brazilian Portuguese, exit 1 if something is
missing or blocks):

```sh
python3 -I tune-up-studio/scripts/verificar_ambiente.py --projeto <project folder>
```

It checks the OS, Node >= 22, the pinned HyperFrames install, the
chrome-headless-shell version HyperFrames 0.9.6 pins in its cache, ffmpeg and
ffprobe with every filter and the encoder the scripts use, `bwrap`/`socat` on
Linux, and the sandbox lists in the user, project and managed settings that
merge into the studio's: `excludedCommands` and `network.allowedDomains` block,
`filesystem.allowWrite` warns.

## Safe install

```sh
cd tune-up-studio/node
npm ci --ignore-scripts        # lockfile pinned, integrity hashes, no install script
```

Run every HyperFrames call with:

```sh
export HYPERFRAMES_NO_TELEMETRY=1 DO_NOT_TRACK=1 HYPERFRAMES_NO_UPDATE_CHECK=1 \
  HYPERFRAMES_NO_AUTO_INSTALL=1 HYPERFRAMES_SKIP_SKILLS=1
npx --no-install hyperframes <command>
```

Never run: `cloud`, `lambda`, `tts`, `transcribe`, `skills`, `upgrade`, `add`,
`browser`, `snapshot --describe`, `render --docker`, or `init` with a template
(templates load GSAP from a CDN). See `node/README.md` for the pin and the
known `undici` audit finding. `regras/bash-estudio.json` is the hook
positive list that enforces this for studio actions.

## Commands

| step | command (from `tune-up-studio/node`) |
| --- | --- |
| still | `hyperframes snapshot <fonte> --at 0 --no-end -o <OUT>` |
| strict check | `hyperframes check <fonte> --json --strict > check.json` |
| render reel | `hyperframes render <fonte> -o <OUT>/video.mp4 --fps 30 --quality delivery` |
| QA still | `python3 -I scripts/qa_imagem.py --source <fonte> --png <png> --check-json check.json --out qa.json` |
| QA reel | `python3 -I scripts/qa_video.py --source <fonte> --video <mp4> --check-json check.json --out qa.json` |
| reserve reel | `python3 -I scripts/video_ou_reserva.py --source <fonte> --slides <png dir> --out <mp4>` |

Details, the check list and the measured behavior of CSS-only animation are in
`scripts/README.md`. Tests (no Chrome, no network): `python3 -m unittest
discover -s tests` from `tune-up-studio/`.

## Cost table (PROVISIONAL)

How measured: on 2026-11-10, by the Part 2 executor, on the example project,
one machine, not by the real studio action. Wall time and peak RAM come from
`/usr/bin/time -l` (macOS). "Peak RAM" is `maximum resident set size`, which
for a wrapped command is the largest single process in the tree that was
waited on, not the sum of the tree; the real total is higher. Render runs
used `--fps 30 --quality delivery`, warm Chrome cache.

| step | wall time | peak RAM (max RSS) | runs | notes |
| --- | --- | --- | --- | --- |
| `snapshot` (post PNG) | 1.07 s | 210 MB | 1 | 1080x1350 |
| `check --strict` (post) | 1.40 s | 185 MB | 1 | |
| `render` 10 s reel, 1080x1920, 30 fps | 5.15 s, 4.56 s | 459 MB, 460 MB | 2 | HyperFrames reports 4.5 s: capture 3.4 s, encode 0.1 s; MP4 1.1 MB |
| `qa_video.py` (ffprobe, blackdetect, freezedetect) | 0.54 s | 110 MB | 1 | green |
| `qa_imagem.py` | 0.06 s | 19 MB | 1 | green |
| reserve reel (3 slides, FFmpeg) | 1.70 s | 878 MB | 1 | MP4 0.7 MB; `zoompan` on a 2x upscale is the RAM cost |

Model usage:

| quantity | value | how |
| --- | --- | --- |
| one `claude --bg` session, 3 assistant turns, 22 s wall | input 6, cache creation 57,861, cache read 111,001, output 574 (169,442 total) | summed from the session `.jsonl` by `painel/tests_reais/prova_video_bg.py`. This session ended in a failed render (see below), so it is not a cost per piece. |
| tokens per finished piece | not measured | no run of the real action produced a piece |
| correction rounds per piece | not measured | no real action run |
| wall clock of a full action (brief to QA green) | not measured | only the render and QA steps were timed |
| RAM of the `claude` session itself | not measured | |
| render time on Linux, WSL2, other hardware | not measured | |
| `max_minutos` hit rate | not measured | |

Known blocker for the real action, observed once: inside the `claude --bg`
sandbox the fixture settings make `hyperframes render` fail with `listen EPERM:
operation not permitted 127.0.0.1` (render serves the composition on
loopback). The numbers above were taken outside the sandbox. Until a render
works in a sandboxed session, render time in a real action is not measured. The
reserve reel was not run inside the sandbox either (not measured).

## Proposed caps per action (PROVISIONAL, to be revised in Parts 5 and 6)

These are proposals set from the table, not enforced yet. The time cap is the
only one the panel can enforce (`max_minutos`, plan item 1.6); the others
must be stated in the action prompt and checked by the QA scripts or the
hook.

| cap | proposal | basis |
| --- | --- | --- |
| pieces per request | 6 (for example 4 posts + 2 reels) | Rendering is not the limit: 6 reels would take about 30 s of render. The limit is model tokens, which are not measured, so this number is a guess that keeps one session small. |
| correction rounds per piece | 2 | Plan rule. A third round is a stop, the piece is reported as failed with the QA findings. |
| `max_minutos` | 15 | Render plus QA for 6 pieces is under 1 minute on the measured machine; the rest is model time, not measured. 15 leaves room for 2 rounds on 6 pieces. Raise only with a measured run. |
| `max_bloqueado_min` | 5 | Guess: a session waiting on a permission prompt should not hold a slot. Not measured. |
| concurrent studio actions | 1 | Peak RAM of one reel render is about 0.5 GB for its largest process and the reserve path reached 0.9 GB. |

Parts 5 and 6 measure again with the real action and replace this section.
