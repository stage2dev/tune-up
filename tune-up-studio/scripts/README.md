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
| `png_size` | PNG is not `--width` x `--height` (default 1080x1350) |
| `layout_allow_count` | any `data-layout-allow-*` in the source |
| `no_gsap` | the word `gsap` anywhere in the source |
| `network_lint` | `http(s)://`, `//host` in src/href/url(), `url(http`, `fetch(`, `XMLHttpRequest`, `WebSocket`, `EventSource`, `sendBeacon`, `import(` |
| `hyperframes_check` | check not strict, browser skipped, `ok` false, or any error/warning finding |

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
