#!/usr/bin/env python3
"""Fallback renderer: a silent slide video from PNGs whose text is already drawn.

Standard library plus ffmpeg (no drawtext, no fonts). Each slide gets a slow
zoom (zoompan on a 2x upscale, so the motion stays smooth) and a crossfade
(xfade) into the next one. The filter graph is written to a file and passed
with -filter_complex_script, so the command line never carries ';'. Every
input carries -protocol_whitelist file,pipe. The MP4 is tagged with
comment=MARK so qa_video.py --engine reserve can tell it apart.

Exit code: 0 rendered, 1 ffmpeg failed, 2 bad usage.
"""
import argparse
import os
import shutil
import subprocess
import sys

MARK = "tune-up-studio reserve"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_SLIDES = 12


def list_slides(folder):
    """Sorted PNG paths in the folder; ValueError if none, too many or not a PNG."""
    names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".png"))
    if not names or len(names) > MAX_SLIDES:
        raise ValueError("expected 1 to %d PNG files in %s, found %d" % (MAX_SLIDES, folder, len(names)))
    paths = [os.path.join(folder, n) for n in names]
    for p in paths:
        with open(p, "rb") as f:
            if f.read(8) != PNG_SIGNATURE:
                raise ValueError("not a PNG: %s" % p)
    return paths


def segment_seconds(count, duration, xfade):
    """Length of each slide so that count slides with (count - 1) crossfades last `duration`."""
    return (duration + (count - 1) * xfade) / count


def build_graph(count, width, height, fps, duration, xfade, zoom):
    """Filter graph text: one zoompan chain per input, xfade between them, trimmed to duration."""
    seg = segment_seconds(count, duration, xfade)
    if count > 1 and seg <= xfade:
        raise ValueError("crossfade %.2f s is too long for %d slides in %.1f s" % (xfade, count, duration))
    frames = int(round(seg * fps))
    lines = []
    for i in range(count):
        lines.append(
            "[%d:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
            "zoompan=z='1+%g*on/%d':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=%d:s=%dx%d:fps=%d,"
            "setsar=1,format=yuv420p[s%d]" % (i, width * 2, height * 2, width * 2, height * 2,
                                              zoom, frames, frames, width, height, fps, i))
    last = "s0"
    for i in range(1, count):
        out = "x%d" % i
        lines.append("[%s][s%d]xfade=transition=fade:duration=%g:offset=%g[%s]"
                     % (last, i, xfade, round(i * (seg - xfade), 4), out))
        last = out
    lines.append("[%s]trim=duration=%g,setpts=PTS-STARTPTS[out]" % (last, duration))
    return ";\n".join(lines) + "\n"


def ffmpeg_command(ffmpeg, slides, graph_file, out, fps, duration):
    cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
    for s in slides:
        cmd += ["-protocol_whitelist", "file,pipe", "-i", s]
    cmd += ["-filter_complex_script", graph_file, "-map", "[out]", "-an",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-frames:v", str(int(round(duration * fps))), "-movflags", "+faststart",
            "-metadata", "comment=" + MARK, out]
    return cmd


def render(slides_dir, out, width=1080, height=1920, duration=10.0, fps=30, xfade=0.5, zoom=0.06,
           ffmpeg="ffmpeg", graph_file=None, timeout=600):
    """Render the slides to `out`. Return (ok, message). The graph is kept next to the MP4."""
    slides = list_slides(slides_dir)
    graph_file = graph_file or out + ".graph.txt"
    with open(graph_file, "w", encoding="utf-8") as f:
        f.write(build_graph(len(slides), width, height, fps, duration, xfade, zoom))
    cmd = ffmpeg_command(ffmpeg, slides, graph_file, out, fps, duration)
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except FileNotFoundError:
        return False, "%s not found" % ffmpeg
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timed out after %d s" % timeout
    if p.returncode != 0 or not os.path.isfile(out):
        return False, "ffmpeg failed (%d): %s" % (p.returncode, p.stderr.decode("utf-8", "replace").strip()[-400:])
    return True, "%d slides -> %s" % (len(slides), out)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--slides", required=True, help="folder with the slide PNGs (sorted by name)")
    p.add_argument("--out", required=True, help="MP4 to write")
    p.add_argument("--width", type=int, default=1080)
    p.add_argument("--height", type=int, default=1920)
    p.add_argument("--duration", type=float, default=10.0)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--xfade", type=float, default=0.5, help="crossfade seconds")
    p.add_argument("--zoom", type=float, default=0.06, help="zoom gained over one slide (0.06 = 6%%)")
    args = p.parse_args(argv)  # no tool-path option: a session could point it at its own file
    try:
        ok, msg = render(args.slides, args.out, args.width, args.height, args.duration, args.fps,
                         args.xfade, args.zoom, shutil.which("ffmpeg") or "ffmpeg")
    except (OSError, ValueError) as exc:
        print("reserva_slides: %s" % exc, file=sys.stderr)
        return 2
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
