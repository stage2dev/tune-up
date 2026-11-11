#!/usr/bin/env python3
"""Render a video with HyperFrames; when it is missing or fails, fall back to the FFmpeg slide reserve.

The HyperFrames binary comes from STUDIO_HYPERFRAMES_BIN, else the pinned install in
../node (no command-line option: a session could point it at a file it wrote). Writes the MP4 and <out>.engine.json with
{"engine": "hyperframes" | "reserve", "reason": ...}. The reserve MP4 also carries the
reserve tag (see reserva_slides.MARK), so qa_video.py --engine reserve can check it.

Exit code: 0 an MP4 was written (by either engine), 1 both failed, 2 bad usage.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reserva_slides  # noqa: E402

DEFAULT_BIN = os.path.join(os.path.dirname(HERE), "node", "node_modules", ".bin", "hyperframes")
QUIET_ENV = {"HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1",
             "HYPERFRAMES_NO_AUTO_INSTALL": "1", "HYPERFRAMES_SKIP_SKILLS": "1"}


def try_hyperframes(binary, source, out, fps, timeout):
    """(ok, reason). ok only if the binary ran, exited 0 and the MP4 exists."""
    if not (os.path.isfile(binary) and os.access(binary, os.X_OK)):
        return False, "hyperframes not available: %s" % binary
    if os.path.exists(out):
        os.remove(out)  # a stale MP4 must not pass as this render
    env = dict(os.environ, **QUIET_ENV)
    try:
        p = subprocess.run([binary, "render", source, "-o", out, "--fps", str(fps), "--quiet"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env)
    except OSError as exc:
        return False, "hyperframes did not start: %s" % exc
    except subprocess.TimeoutExpired:
        return False, "hyperframes timed out after %d s" % timeout
    if p.returncode != 0 or not os.path.isfile(out):
        tail = p.stderr.decode("utf-8", "replace").strip()[-300:]
        return False, "hyperframes render failed (%d): %s" % (p.returncode, tail)
    return True, "rendered by hyperframes"


def run(source, slides, out, binary, duration=10.0, fps=30, ffmpeg="ffmpeg", timeout=600):
    """Return the engine record written to <out>.engine.json; engine is None if both failed."""
    ok, reason = try_hyperframes(binary, source, out, fps, timeout)
    record = {"engine": "hyperframes", "reason": reason, "video": out}
    if not ok:
        if os.path.exists(out):
            os.remove(out)
        try:
            ok2, msg = reserva_slides.render(slides, out, duration=duration, fps=fps, ffmpeg=ffmpeg,
                                             timeout=timeout)
        except (OSError, ValueError) as exc:
            ok2, msg = False, str(exc)
        record = {"engine": "reserve" if ok2 else None, "reason": reason,
                  "reserve": msg, "video": out if ok2 else None}
    with open(out + ".engine.json", "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return record


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", required=True, help="HyperFrames composition folder (fonte/)")
    p.add_argument("--slides", required=True, help="folder with slide PNGs for the reserve")
    p.add_argument("--out", required=True, help="MP4 to write")
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--fps", type=int, default=30)
    args = p.parse_args(argv)
    binary = os.environ.get("STUDIO_HYPERFRAMES_BIN") or DEFAULT_BIN
    record = run(args.source, args.slides, args.out, binary, args.duration, args.fps,
                 shutil.which("ffmpeg") or "ffmpeg")
    print(json.dumps(record, ensure_ascii=False))
    return 0 if record["engine"] else 1


if __name__ == "__main__":
    sys.exit(main())
