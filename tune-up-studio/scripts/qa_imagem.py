#!/usr/bin/env python3
"""QA for a still image (post) rendered by HyperFrames.

Standard library only. It does not run Chrome: it reads the PNG, the
composition source folder and the JSON written by
`hyperframes check <dir> --json --strict`, and prints one JSON report.

Exit code: 0 all green, 1 at least one check failed, 2 bad usage.
"""
import argparse
import json
import os
import re
import struct
import sys
import zlib

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
PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
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
        rel = os.path.relpath(path, folder)
        for number, line in enumerate(read_text(path).splitlines(), 1):
            if strip_xmlns:
                line = XMLNS_RE.sub("", line)
            for label, rx in patterns:
                for m in rx.finditer(line):
                    hits.append("%s:%d: %s: %s" % (rel, number, label, m.group(0)))
    return hits


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


def check_binding(data, path, source, duration):
    """Problems tying this check JSON to the source folder (and the video length)."""
    problems = []
    if source is not None:
        root = os.path.realpath(source)
        report = (data.get("saved") or {}).get("report") if isinstance(data.get("saved"), dict) else None
        if not isinstance(report, str) or not os.path.realpath(report).startswith(root + os.sep):
            problems.append("check was not run on this source: saved.report=%r, source=%s" % (report, root))
        elif os.path.getmtime(path) < newest_mtime(source):
            problems.append("source changed after the check; run check again")
    if duration is not None:
        got = (data.get("layout") or {}).get("duration") if isinstance(data.get("layout"), dict) else None
        if not isinstance(got, (int, float)) or abs(got - duration) > 0.2:
            problems.append("check layout.duration=%r (expected %g)" % (got, duration))
    return problems


def check_strict_json(path, source=None, duration=None):
    """Green only if the strict check ran in a browser on `source` and found nothing above info."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as exc:
        return result("hyperframes_check", False, ["cannot read %s: %s" % (path, exc)])
    if not isinstance(data, dict):
        return result("hyperframes_check", False, ["check output is not a JSON object"])
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


def run(source, png, check_json, width, height):
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
    checks.append(check_strict_json(check_json, source))
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", required=True, help="composition folder (fonte/)")
    p.add_argument("--png", required=True, help="rendered still")
    p.add_argument("--check-json", required=True, help="output of check --json --strict")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1350)
    p.add_argument("--out", help="also write the report to this file")
    args = p.parse_args(argv)
    report = run(args.source, args.png, args.check_json, args.width, args.height)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
