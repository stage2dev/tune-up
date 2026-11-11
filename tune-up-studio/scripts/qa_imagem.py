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
LAYOUT_ALLOW_RE = re.compile(r"data-layout-allow-[a-z-]+", re.I)


def png_size(path):
    """Return (width, height) from the IHDR chunk, or raise ValueError."""
    with open(path, "rb") as f:
        head = f.read(24)
    if len(head) < 24 or head[:8] != PNG_SIGNATURE or head[12:16] != b"IHDR":
        raise ValueError("not a PNG file")
    return struct.unpack(">II", head[16:24])


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
    except (OSError, ValueError) as exc:
        return result("png_size", False, ["%s: %s" % (png, exc)])
    ok = (w, h) == (width, height)
    return result("png_size", ok, ["%dx%d (expected %dx%d)" % (w, h, width, height)])


def check_strict_json(path):
    """Green only if the strict check ran in a browser and found nothing above info."""
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
    checks.append(check_strict_json(check_json))
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
