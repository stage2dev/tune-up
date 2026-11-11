#!/usr/bin/env python3
"""QA for a short silent video (9:16 reel) rendered by HyperFrames.

Standard library plus ffprobe/ffmpeg. It does not run Chrome: it probes the
MP4, runs ffmpeg blackdetect and freezedetect, scans the composition source
folder and reads the `check --strict` report HyperFrames saved under
`<source>/.hyperframes/` (never a copy the session wrote). The report carries a
final line in `linha` (PRONTO / PRECISA DO SEU OLHO) and, with --sheet, a
contact sheet PNG of the MP4 (one frame per second, 5 per row).

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
from reserva_slides import MARK  # noqa: E402

BLACK_FILTER = "blackdetect=d=0.5:pix_th=0.10"
FREEZE_FILTER = "freezedetect=n=-60dB:d=2"
BLACK_RE = re.compile(r"black_start:\s*([\d.]+)\s+black_end:\s*([\d.]+)\s+black_duration:\s*([\d.]+)")
FREEZE_RE = re.compile(r"lavfi\.freezedetect\.freeze_(start|duration|end):\s*([\d.]+)")
# ffmpeg exits 0 on a cut MP4 after decoding part of it; these lines give it away.
DAMAGE_RE = re.compile(r"partial file|Invalid data", re.I)


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
    code, out, err = run_tool([ffprobe, "-v", "error", "-print_format", "json", "-count_frames",
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
    try:
        frames = int(v.get("nb_read_frames"))
    except (TypeError, ValueError):
        frames = -1
    want = int(round(duration * fps))
    checks.append(result("frames", abs(frames - want) <= max(1, int(fps * 0.2)),
                         ["%d frames decoded (expected %d)" % (frames, want)]))
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
    """Run one ffmpeg detection filter; return (ok_to_parse, stderr). A damaged file is not ok."""
    code, _, err = run_tool([ffmpeg, "-hide_banner", "-nostats", "-i", video, "-an",
                             "-vf", flt, "-f", "null", "-"])
    return code == 0 and not DAMAGE_RE.search(err), err


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


def check_reserve_tag(data):
    """Reserve videos have no HyperFrames composition to check; they must carry the reserve tag."""
    tag = ((data.get("format") or {}).get("tags") or {}).get("comment")
    return result("engine_reserve", tag == MARK, ["comment=%r (expected %r)" % (tag, MARK)])


def contact_sheet(video, out, duration, ffmpeg):
    """One frame per second of the MP4 in a 5-column grid PNG. Return the check result."""
    count = max(1, int(round(duration)))
    rows = (count + 4) // 5
    code, _, err = run_tool([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-an",
                             "-vf", "fps=1,scale=216:384,tile=5x%d" % rows, "-frames:v", "1", out])
    ok = code == 0 and os.path.isfile(out)
    return result("contact_sheet", ok, [out if ok else "ffmpeg failed: %s" % err.strip()[-300:]])


def final_line(report, engine):
    if report["ok"]:
        return "PRONTO: video verde (%s)" % engine
    return "PRECISA DO SEU OLHO: %s" % ", ".join(c["name"] for c in report["checks"] if not c["ok"])


def run(source, video, check_json, width, height, duration, fps, ffmpeg, ffprobe, engine="hyperframes"):
    data = {}
    try:
        data = probe(video, ffprobe)
        checks = stream_checks(data, video, width, height, duration, fps)
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
    if engine == "reserve":  # the slides are snapshots of the same composition: it is checked too
        checks.append(check_reserve_tag(data))
    elif check_reserve_tag(data)["ok"]:  # a reserve MP4 is never reported as a render
        checks.append(result("engine_hyperframes", False, ["the MP4 carries the reserve tag; use --engine reserve"]))
    checks.append(check_strict_json(check_json, source, duration))
    return {"ok": all(c["ok"] for c in checks), "checks": checks}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", required=True, help="composition folder (fonte/)")
    p.add_argument("--video", required=True, help="rendered MP4")
    p.add_argument("--check-json", help="optional: output of check --json --strict; only its saved.report "
                                         "path is used (default: newest report HyperFrames saved)")
    p.add_argument("--engine", choices=("hyperframes", "reserve"), default="hyperframes",
                   help="reserve: slide video from reserva_slides.py, also checked for the reserve tag")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--fps", type=float, default=30.0)
    p.add_argument("--out", help="also write the report to this file")
    p.add_argument("--sheet", help="also write a contact sheet PNG of the MP4 here")
    args = p.parse_args(argv)
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    report = run(args.source, args.video, args.check_json, args.width, args.height,
                 args.duration, args.fps, ffmpeg, shutil.which("ffprobe") or "ffprobe", args.engine)
    if args.sheet:
        report["checks"].append(contact_sheet(args.video, args.sheet, args.duration, ffmpeg))
        report["ok"] = all(c["ok"] for c in report["checks"])
    report["linha"] = final_line(report, args.engine)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
