#!/usr/bin/env python3
"""QA for a still image (post) rendered by HyperFrames.

Standard library only. It does not run Chrome: it reads the PNG, the
composition source folder and what HyperFrames itself saved under
`<source>/.hyperframes/` (the newest `check --strict` report and the snapshot
record, whose warnings list a brand font that failed to load), and prints one
JSON report. `--formato 4:5|1:1` takes the size from formatos.json.
`--final <working folder>` re-checks every `q<N>/` frame and gives the final line.

Exit code: 0 all green, 1 at least one check failed, 2 bad usage.
"""
import argparse
import json
import os
import re
import struct
import sys
import zlib

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE_IDS = {"4:5": "instagram-feed-organico-tamanho", "1:1": "instagram-feed-quadrado-tamanho"}
STILL = "frame-00-at-0s.png"
FRAME_RE = re.compile(r"q([1-9]\d*)\Z")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SKIP_DIRS = {".hyperframes", "node_modules", ".git"}
MAX_DETAILS = 20

# SVG/XML namespace URIs are identifiers, never fetched. Only these exact
# attribute forms are removed before the network lint.
XMLNS_RE = re.compile(r"""xmlns(?::[\w-]+)?\s*=\s*["']http://www\.w3\.org/[^"']*["']""")

# Static lint. It can be dodged (string building, eval, encodings); the real
# guarantee is a browser without network. This only catches the plain cases.
NETWORK_PATTERNS = [
    ("absolute URL", re.compile(r"https?://", re.I)),
    ("protocol-relative URL", re.compile(r"""(?:src|href)\s*=\s*["']//|url\(\s*["']?//""", re.I)),
    ("url(http", re.compile(r"""url\(\s*["']?\s*http""", re.I)),
    ("fetch(", re.compile(r"\bfetch\s*\(")),
    ("XMLHttpRequest", re.compile(r"XMLHttpRequest")),
    ("WebSocket", re.compile(r"WebSocket")),
    ("EventSource", re.compile(r"EventSource")),
    ("sendBeacon", re.compile(r"sendBeacon")),
    ("dynamic import(", re.compile(r"\bimport\s*\(")),
]
GSAP_RE = re.compile(r"gsap", re.I)
# Every way seen to silence the layout audit: the data-layout-* attributes (on the
# element or any ancestor) and setting them from script (dataset / setAttribute).
LAYOUT_ALLOW_RE = re.compile(
    r"data-layout-(?:allow|ignore|bleed|boundary|check)[\w-]*|"
    r"\blayout(?:Allow|Ignore|Bleed|Boundary|Check)\w*|\bdataset\b|setAttribute", re.I)
SCRIPT_RE = re.compile(r"<script\b", re.I)
# Images: only files directly in <source>/assets/, PNG/JPEG/WebP checked by their first bytes (plus the
# text logo.svg). Every image reference in the text files must name one of them.
RASTER = {".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
          ".webp": (b"RIFF",)}
IMAGE_EXT = set(RASTER) | {".svg", ".gif", ".avif", ".bmp", ".ico", ".tif", ".tiff", ".heic", ".apng", ".jxl"}
ASSET_RE = re.compile(r"(?:\./)?assets/([\w.]+)\Z")
IMAGE_REF_RE = re.compile(
    r"""\b(?:src|srcset|poster|data|xlink:href)\s*=\s*["']([^"']*)["']|"""
    r"""<(?:image|feImage|use)\b[^>]*?\bhref\s*=\s*["']([^"']*)["']|"""
    r"""(?:url|image-set)\(\s*["']?([^"')\s]*)|"""
    r"""["'(\s]([^"'()\s<>]+\.(?:png|jpe?g|webp|svg|gif|avif|bmp|ico|tiff?|heic|apng|jxl))(?=["')\s,])""", re.I)
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
MAX_RAW = 1080 * 1920 * 8 + 1920 * 8  # biggest format (1080x1920) at 16-bit RGBA, plus filter bytes
ADAM7 = ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2))


def png_raw_size(width, height, depth, ctype, interlace):
    """Bytes the inflated IDAT must hold (filter byte + packed pixels per row)."""
    if ctype not in PNG_CHANNELS or depth not in (1, 2, 4, 8, 16):
        raise ValueError("unsupported PNG color type %d / depth %d" % (ctype, depth))
    bits = depth * PNG_CHANNELS[ctype]

    def rows(w, h):
        return h * (1 + (w * bits + 7) // 8) if w and h else 0
    if not interlace:
        return rows(width, height)
    return sum(rows((width - x + dx - 1) // dx if width > x else 0,
                    (height - y + dy - 1) // dy if height > y else 0) for x, y, dx, dy in ADAM7)


def png_size(path):
    """Return (width, height) of a whole PNG, or raise ValueError.

    Walks every chunk up to IEND checking the CRCs, then inflates the IDAT data
    and requires exactly the size IHDR promises, so a cut or damaged file fails.
    """
    with open(path, "rb") as f:
        data = f.read()
    if data[:8] != PNG_SIGNATURE or data[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    pos, ihdr, idat = 8, None, []
    while True:
        if pos + 12 > len(data):
            raise ValueError("truncated PNG: no IEND chunk")
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        end = pos + 12 + length
        if end > len(data):
            raise ValueError("truncated PNG: %s chunk cut" % kind.decode("latin-1"))
        body = data[pos + 4:pos + 8 + length]
        if zlib.crc32(body) != struct.unpack(">I", data[end - 4:end])[0]:
            raise ValueError("bad CRC in %s chunk" % kind.decode("latin-1"))
        if kind == b"IHDR" and length == 13:
            ihdr = struct.unpack(">IIBBBBB", body[4:])
        elif kind == b"IDAT":
            idat.append(body[4:])
        elif kind == b"IEND":
            break
        pos = end
    if ihdr is None:
        raise ValueError("bad IHDR chunk")
    width, height, depth, ctype, _, _, interlace = ihdr
    want = png_raw_size(width, height, depth, ctype, interlace)
    if want > MAX_RAW:  # the header is free text: never inflate past the biggest real format
        raise ValueError("PNG too large: IHDR says %dx%d" % (width, height))
    inflater = zlib.decompressobj()
    try:
        raw = inflater.decompress(b"".join(idat), want + 1)
    except zlib.error as exc:
        raise ValueError("bad IDAT data: %s" % exc)
    if len(raw) != want or not inflater.eof:
        raise ValueError("IDAT holds %d bytes, IHDR needs %d" % (len(raw), want))
    return width, height


def source_files(folder):
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            yield os.path.join(root, name)


def read_text(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


def scan(folder, patterns, strip_xmlns=False):
    """Return ["file:line: label: match", ...] for every pattern hit."""
    hits = []
    for path in source_files(folder):
        if os.path.splitext(path)[1].lower() in RASTER:  # binary: checked by check_images, not as text
            continue
        rel = os.path.relpath(path, folder)
        for number, line in enumerate(read_text(path).splitlines(), 1):
            if strip_xmlns:
                line = XMLNS_RE.sub("", line)
            for label, rx in patterns:
                for m in rx.finditer(line):
                    hits.append("%s:%d: %s: %s" % (rel, number, label, m.group(0)))
    return hits


def image_file_problem(path, rel):
    """Why an image file in the source is not allowed, or None (assets/<name>, real type, no link)."""
    parts, ext = rel.replace(os.sep, "/").split("/"), os.path.splitext(rel)[1].lower()
    if os.path.islink(path):
        return "%s: a link" % rel
    if len(parts) != 2 or parts[0] != "assets":
        return "%s: images only directly in assets/" % rel
    if ext == ".svg":
        return None if parts[1] == "logo.svg" else "%s: the only SVG allowed is assets/logo.svg" % rel
    if ext not in RASTER:
        return "%s: type not allowed (png, jpg, webp)" % rel
    with open(path, "rb") as f:
        head = f.read(12)
    if not head.startswith(RASTER[ext]) or (ext == ".webp" and head[8:12] != b"WEBP"):
        return "%s: the bytes are not %s" % (rel, ext[1:])
    return None


def check_images(source):
    """Images come only from <source>/assets/ (png, jpg, webp, logo.svg); every reference names one of them."""
    problems, names = [], set()
    for path in source_files(source):
        rel = os.path.relpath(path, source)
        if os.path.splitext(path)[1].lower() in IMAGE_EXT or os.path.islink(path):
            bad = image_file_problem(path, rel)
            if bad:
                problems.append(bad)
            else:
                names.add(os.path.basename(path))
    for path in source_files(source):
        if os.path.splitext(path)[1].lower() in IMAGE_EXT - {".svg"}:
            continue
        rel = os.path.relpath(path, source)
        for number, line in enumerate(read_text(path).splitlines(), 1):
            for m in IMAGE_REF_RE.finditer(line):
                value = next(g for g in m.groups() if g is not None)
                for ref in [r.strip().split(" ")[0] for r in value.split(",")] if "srcset" in m.group(0).lower() \
                        else [value.strip()]:
                    a = ASSET_RE.match(ref)
                    if ref and not ref.startswith("#") and not (a and a.group(1) in names):
                        problems.append("%s:%d: image not in assets/: %s" % (rel, number, ref[:80]))
    return result("images", not problems, problems or ["ok"])


def result(name, ok, details):
    return {"name": name, "ok": ok, "details": details[:MAX_DETAILS]}


def check_png(png, width, height):
    try:
        w, h = png_size(png)
    except (OSError, ValueError, struct.error) as exc:
        return result("png_size", False, ["%s: %s" % (png, exc)])
    ok = (w, h) == (width, height)
    return result("png_size", ok, ["%dx%d (expected %dx%d)" % (w, h, width, height)])


def newest_mtime(folder):
    return max([os.path.getmtime(p) for p in source_files(folder)] or [0.0])


def format_size(formato, path=None):
    """(width, height) of a post format ("post 4:5", "4:5", "1x1") read from formatos.json."""
    m = re.search(r"(\d+)[:x](\d+)", formato or "")
    key = "%s:%s" % m.groups() if m else None
    if key not in SIZE_IDS:
        raise ValueError("unknown format %r (use 4:5 or 1:1)" % formato)
    with open(path or os.path.join(STUDIO, "formatos.json"), encoding="utf-8") as f:
        entries = json.load(f)["formatos"]
    values = next(e["valores"] for e in entries if e.get("id") == SIZE_IDS[key])
    return int(values["largura"]), int(values["altura"])


def newest_report(source):
    """The newest report HyperFrames saved under `<source>/.hyperframes/artifacts/checks/`."""
    checks = os.path.join(os.path.realpath(source), ".hyperframes", "artifacts", "checks")
    try:
        paths = [os.path.join(checks, n) for n in os.listdir(checks) if n.endswith(".json")]
    except OSError:
        return None
    paths = [p for p in paths if os.path.isfile(p) and not os.path.islink(p)]
    return max(paths, key=os.path.getmtime) if paths else None


def saved_report(data, source):
    """Path of the report HyperFrames itself wrote for this check, if it sits under the source."""
    checks = os.path.join(os.path.realpath(source), ".hyperframes", "artifacts", "checks")
    report = (data.get("saved") or {}).get("report") if isinstance(data.get("saved"), dict) else None
    if isinstance(report, str) and os.path.realpath(report).startswith(checks + os.sep):
        return os.path.realpath(report)
    return None


def check_binding(data, path, source, duration):
    """Problems tying this check report to the source folder (and the video length)."""
    problems = []
    if source is not None and os.path.getmtime(path) < newest_mtime(source):
        problems.append("source changed after the check; run check again")
    if duration is not None:
        got = (data.get("layout") or {}).get("duration") if isinstance(data.get("layout"), dict) else None
        if not isinstance(got, (int, float)) or abs(got - duration) > 0.2:
            problems.append("check layout.duration=%r (expected %g)" % (got, duration))
    return problems


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError, RecursionError) as exc:
        return None, "cannot read %s: %s" % (path, exc)
    if not isinstance(data, dict):
        return None, "%s is not a JSON object" % path
    return data, None


def check_strict_json(path, source=None, duration=None):
    """Green only if the strict check ran in a browser on `source` and found nothing above info.

    With `source` the verdict is read from the report HyperFrames saved under
    `<source>/.hyperframes/artifacts/checks/`, never from a copy the session wrote: the one
    `path` names in `saved.report`, or the newest one when `path` is None.
    """
    data = None
    if path is not None:
        data, err = load_json(path)
        if err:
            return result("hyperframes_check", False, [err])
    if source is not None:
        report = saved_report(data, source) if data is not None else newest_report(source)
        if report is None:
            return result("hyperframes_check", False, ["no check report HyperFrames saved for this source "
                                                       "(run check --json --strict on it): %s"
                                                       % os.path.realpath(source)])
        path = report
        data, err = load_json(path)
        if err:
            return result("hyperframes_check", False, [err])
    if data is None:
        return result("hyperframes_check", False, ["no check output"])
    problems = []
    if data.get("strict") is not True:
        problems.append("check was not run with --strict")
    if data.get("browserSkipped") is not False:
        problems.append("browser checks were skipped")
    for section, body in data.items():
        if not isinstance(body, dict):
            continue
        for finding in body.get("findings") or []:
            if finding.get("severity") in ("error", "warning"):
                problems.append("%s: %s %s at %s: %s" % (
                    section, finding.get("severity"), finding.get("code"),
                    finding.get("selector"), finding.get("message")))
    if data.get("ok") is not True:
        problems.append("check reported ok=false")
    problems += check_binding(data, path, source, duration)
    return result("hyperframes_check", not problems, problems or ["ok"])


def snapshot_records(node):
    """Every snapshot record (a dict with an "image" path) inside video-state.json."""
    if isinstance(node, dict):
        if isinstance(node.get("image"), str):
            yield node
        for value in node.values():
            yield from snapshot_records(value)
    elif isinstance(node, list):
        for value in node:
            yield from snapshot_records(value)


def check_snapshot(png, source):
    """Green only if HyperFrames recorded `png` as a snapshot of `source`, after the last edit,
    with no warning. A brand font that did not load is one ("Fonts failed: ...")."""
    data, err = load_json(os.path.join(source, ".hyperframes", "video-state.json"))
    if err:
        return result("snapshot", False, [err])
    want = os.path.realpath(png)
    found = [r for r in snapshot_records(data.get("snapshots")) if os.path.realpath(r["image"]) == want]
    if not found:
        return result("snapshot", False, ["%s was not recorded by hyperframes snapshot of %s" % (png, source)])
    last = max(found, key=lambda r: r.get("createdAt") if isinstance(r.get("createdAt"), (int, float)) else 0)
    warnings = (last.get("metadata") or {}).get("warnings") if isinstance(last.get("metadata"), dict) else None
    problems = ["snapshot warning: %s" % w for w in warnings] if isinstance(warnings, list) \
        else ["snapshot record has no warnings list"]
    created = last.get("createdAt")
    if not isinstance(created, (int, float)) or created / 1000.0 < newest_mtime(source):
        problems.append("source changed after the snapshot; run snapshot again")
    return result("snapshot", not problems, problems or ["ok"])


def run(source, png, check_json, width, height, snapshot=False):
    checks = [check_png(png, width, height)]
    if not os.path.isdir(source):
        checks.append(result("source", False, ["not a folder: %s" % source]))
    else:
        allow = scan(source, [("layout allow", LAYOUT_ALLOW_RE)])
        checks.append(result("layout_allow_count", not allow,
                             ["count=%d" % len(allow)] + allow))
        gsap = scan(source, [("gsap", GSAP_RE)])
        checks.append(result("no_gsap", not gsap, gsap or ["ok"]))
        net = scan(source, NETWORK_PATTERNS, strip_xmlns=True)
        checks.append(result("network_lint", not net, net or ["ok"]))
        script = scan(source, [("script", SCRIPT_RE)])  # the post is CSS only
        checks.append(result("no_script", not script, script or ["ok"]))
        checks.append(check_images(source))
        if snapshot:
            checks.append(check_snapshot(png, source))
    checks.append(check_strict_json(check_json, source))
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def run_final(folder, width, height):
    """Re-check every `q<N>/` frame (fonte/ + snap/) at the format size; PRONTO only if all are green."""
    try:
        names = os.listdir(folder)
    except OSError:
        names = []
    frames = sorted((int(m.group(1)), n) for n in names for m in [FRAME_RE.match(n)] if m)
    out = []
    for _, name in frames:
        base = os.path.join(folder, name)
        rep = run(os.path.join(base, "fonte"), os.path.join(base, "snap", STILL), None, width, height, snapshot=True)
        out.append({"frame": name, "ok": rep["ok"], "failed": [c["name"] for c in rep["checks"] if not c["ok"]],
                    "checks": rep["checks"]})
    n, green = len(out), sum(1 for f in out if f["ok"])
    ok = n > 0 and green == n
    if ok:
        line = "PRONTO: %d de %d quadros verdes" % (n, n)
    else:
        why = "; ".join("%s: %s" % (f["frame"], ", ".join(f["failed"])) for f in out if not f["ok"])
        line = "PRECISA DO SEU OLHO: %d de %d verdes, %s" % (green, n, why or "nenhum quadro q<N> achado")
    return {"ok": ok, "linha": line, "size": "%dx%d" % (width, height), "frames": out}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", help="composition folder (fonte/)")
    p.add_argument("--png", help="rendered still")
    p.add_argument("--check-json", help="optional: output of check --json --strict; only its saved.report "
                                         "path is used (default: newest report HyperFrames saved)")
    p.add_argument("--formato", help="4:5 or 1:1: size from formatos.json (overrides --width/--height)")
    p.add_argument("--final", metavar="FOLDER", help="re-check every q<N>/ frame in FOLDER (needs --formato)")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1350)
    p.add_argument("--out", help="also write the report to this file")
    args = p.parse_args(argv)
    if args.formato:
        try:
            args.width, args.height = format_size(args.formato)
        except (OSError, ValueError, KeyError, StopIteration) as exc:
            p.error("--formato: %s" % (exc or "not in formatos.json"))
    if args.final:
        if not args.formato:
            p.error("--final needs --formato")
        report = run_final(args.final, args.width, args.height)
    elif not (args.source and args.png):
        p.error("--source and --png are required")
    else:
        report = run(args.source, args.png, args.check_json, args.width, args.height, snapshot=True)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
