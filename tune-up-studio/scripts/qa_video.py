#!/usr/bin/env python3
"""QA for a short silent video (9:16 reel) rendered by HyperFrames.

Standard library plus ffprobe/ffmpeg. It does not run Chrome: it probes the
MP4, runs ffmpeg blackdetect and freezedetect, scans the composition source
folder and reads the JSON of `hyperframes check <dir> --json --strict`.

Exit code: 0 all green, 1 at least one check failed, 2 bad usage.
"""
import argparse
import json
import os
import re
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from qa_imagem import (  # noqa: E402
    GSAP_RE, LAYOUT_ALLOW_RE, NETWORK_PATTERNS, check_strict_json, result, scan)

BLACK_FILTER = "blackdetect=d=0.5:pix_th=0.10"
FREEZE_FILTER = "freezedetect=n=-60dB:d=2"
BLACK_RE = re.compile(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)\s+black_duration:\s*([\d.]+)")
FREEZE_RE = re.compile(r"lavfi\.freezedetect\.freeze_(start|duration|end):\s*([\d.]+)")


def run_tool(cmd, timeout=300):
    """Return (exit code, stdout, stderr); a missing tool is exit 127."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError:
        return 127, "", "%s not found" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "", "%s timed out" % cmd[0]
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def probe(video, ffprobe):
    code, out, err = run_tool([ffprobe, "-v", "error", "-print_format", "json",
                               "-show_streams", "-show_format", video])
    if code != 0:
        raise ValueError("ffprobe failed (%d): %s" % (code, err.strip()[:300]))
    data = json.loads(out)
    if not isinstance(data, dict):
        raise ValueError("ffprobe output is not an object")
    return data


def top_level_atoms(path):
    """Names of the top-level MP4 boxes, in file order."""
    names = []
    with open(path, "rb") as f:
        size_total = os.fstat(f.fileno()).st_size
        pos = 0
        while pos + 8 <= size_total:
            f.seek(pos)
            size, kind = struct.unpack(">I4s", f.read(8))
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
            elif size == 0:
                size = size_total - pos
            if size < 8:
                break
            names.append(kind.decode("latin-1"))
            pos += size
    return names


def fps_of(stream):
    num, _, den = str(stream.get("r_frame_rate") or "0/1").partition("/")
    try:
        return float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0


def stream_checks(data, video, width, height, duration, fps):
    streams = data.get("streams") or []
    vids = [s for s in streams if s.get("codec_type") == "video"]
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    checks = [result("no_audio", not audio, ["audio streams=%d" % len(audio)])]
    if len(vids) != 1:
        checks.append(result("video_stream", False, ["video streams=%d (expected 1)" % len(vids)]))
        return checks
    v = vids[0]
    size = (v.get("width"), v.get("height"))
    checks.append(result("video_size", size == (width, height),
                         ["%sx%s (expected %dx%d)" % (size[0], size[1], width, height)]))
    try:
        got = float((data.get("format") or {}).get("duration"))
    except (TypeError, ValueError):
        got = -1.0
    checks.append(result("duration", abs(got - duration) <= 0.2,
                         ["%.3f s (expected %.1f +-0.2)" % (got, duration)]))
    rate = fps_of(v)
    checks.append(result("fps", abs(rate - fps) < 0.01,
                         ["r_frame_rate=%s (expected %g)" % (v.get("r_frame_rate"), fps)]))
    checks.append(result("codec", v.get("codec_name") == "h264" and v.get("pix_fmt") == "yuv420p",
                         ["%s %s (expected h264 yuv420p)" % (v.get("codec_name"), v.get("pix_fmt"))]))
    try:
        atoms = top_level_atoms(video)
    except (OSError, struct.error) as exc:
        atoms, err = [], str(exc)
    else:
        err = ""
    ok = "moov" in atoms and "mdat" in atoms and atoms.index("moov") < atoms.index("mdat")
    checks.append(result("faststart", ok, [err or "atoms: %s" % " ".join(atoms[:8])]))
    return checks


def detect(video, ffmpeg, flt):
    """Run one ffmpeg detection filter; return (ok_to_parse, stderr)."""
    code, _, err = run_tool([ffmpeg, "-hide_banner", "-nostats", "-i", video, "-an",
                             "-vf", flt, "-f", "null", "-"])
    return code == 0, err


def check_black(video, ffmpeg):
    ran, err = detect(video, ffmpeg, BLACK_FILTER)
    if not ran:
        return result("blackdetect", False, ["ffmpeg failed: %s" % err.strip()[-300:]])
    spans = ["black %s-%s s (%s s)" % m for m in BLACK_RE.findall(err)]
    return result("blackdetect", not spans, spans or ["no black span >= 0.5 s"])


def check_freeze(video, ffmpeg):
    ran, err = detect(video, ffmpeg, FREEZE_FILTER)
    if not ran:
        return result("freezedetect", False, ["ffmpeg failed: %s" % err.strip()[-300:]])
    found = ["freeze_%s=%s" % m for m in FREEZE_RE.findall(err)]
    return result("freezedetect", not found, found or ["no still span >= 2 s"])


def run(source, video, check_json, width, height, duration, fps, ffmpeg, ffprobe):
    try:
        checks = stream_checks(probe(video, ffprobe), video, width, height, duration, fps)
    except (ValueError, OSError) as exc:
        checks = [result("probe", False, [str(exc)])]
    else:
        checks += [check_black(video, ffmpeg), check_freeze(video, ffmpeg)]
    if not os.path.isdir(source):
        checks.append(result("source", False, ["not a folder: %s" % source]))
    else:
        allow = scan(source, [("layout allow", LAYOUT_ALLOW_RE)])
        checks.append(result("layout_allow_count", not allow, ["count=%d" % len(allow)] + allow))
        gsap = scan(source, [("gsap", GSAP_RE)])
        checks.append(result("no_gsap", not gsap, gsap or ["ok"]))
        net = scan(source, NETWORK_PATTERNS, strip_xmlns=True)
        checks.append(result("network_lint", not net, net or ["ok"]))
    checks.append(check_strict_json(check_json))
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", required=True, help="composition folder (fonte/)")
    p.add_argument("--video", required=True, help="rendered MP4")
    p.add_argument("--check-json", required=True, help="output of check --json --strict")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--ffmpeg", default=shutil.which("ffmpeg") or "ffmpeg")
    p.add_argument("--ffprobe", default=shutil.which("ffprobe") or "ffprobe")
    p.add_argument("--out", help="also write the report to this file")
    args = p.parse_args(argv)
    report = run(args.source, args.video, args.check_json, args.width, args.height,
                 args.duration, args.fps, args.ffmpeg, args.ffprobe)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
