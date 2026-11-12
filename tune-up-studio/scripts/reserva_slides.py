#!/usr/bin/env python3
"""Fallback renderer: a silent slide video from PNGs whose text is already drawn.

Standard library plus ffmpeg (no drawtext, no fonts). Each slide gets a slow
move (zoompan on a 2x upscale, so the motion stays smooth): zoom in, zoom out
and a sideways pan in turn. Cuts rotate through TRANSITIONS; never a plain
dissolve, which shows two slides' text on top of each other. The filter graph is written to a file and passed
with -filter_complex_script, so the command line never carries ';'. Every
input carries -protocol_whitelist file,pipe. The MP4 is tagged with
comment=MARK so qa_video.py --engine reserve can tell it apart.

--tempos T1,T2,... gives each slide the length of its scene (a short hook, a long
call to action). Each cut is centred on the scene boundary, as in the composition:
the first slide lasts T1 + xfade/2, a middle one Ti + xfade, the last Tn + xfade/2.
Without it every slide gets the same length.

Exit code: 0 rendered, 1 ffmpeg failed, 2 bad usage.
"""
import argparse
import math
import os
import shutil
import subprocess
import sys

MARK = "tune-up-studio reserve"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
MAX_SLIDES = 12
TRANSITIONS = ("wipeleft", "slideup", "wipedown", "slideleft")  # hard edges only: soft ones blend two texts


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


def parse_tempos(text):
    """'1.5,2.5,3.5' -> [1.5, 2.5, 3.5]; ValueError on anything that is not a positive number."""
    out = []
    for part in (text or "").split(","):
        try:
            value = float(part)
        except ValueError:
            raise ValueError("--tempos: %r is not a number of seconds" % part)
        if not math.isfinite(value) or value <= 0:
            raise ValueError("--tempos: %r is not a positive number of seconds" % part)
        out.append(value)
    return out


def check_tempos(tempos, count, duration, xfade):
    """ValueError with the reason when the scene lengths cannot cut `count` slides into `duration`."""
    if len(tempos) != count:
        raise ValueError("--tempos has %d lengths for %d slides" % (len(tempos), count))
    if abs(sum(tempos) - duration) > 0.05:
        raise ValueError("--tempos adds up to %g s, not --duration %g s" % (sum(tempos), duration))
    if count == 1:
        return
    for i, t in enumerate(tempos):
        edge = i in (0, count - 1)
        floor = xfade / 2 if edge else xfade
        if t <= floor:
            raise ValueError("slide %d lasts %g s, not more than the %g s its cut%s takes"
                             % (i + 1, t, floor, "" if edge else "s"))


def timeline(count, duration, xfade, tempos=None):
    """(seconds of each slide, offset of each xfade). Equal slides without tempos, as before."""
    if not tempos:
        seg = segment_seconds(count, duration, xfade)
        return [seg] * count, [round(i * (seg - xfade), 4) for i in range(1, count)]
    check_tempos(tempos, count, duration, xfade)
    if count == 1:
        return [max(tempos[0], duration)], []
    cuts = [sum(tempos[:k]) for k in range(1, count)]
    offsets = [round(c - xfade / 2, 4) for c in cuts]
    lengths = [tempos[0] + xfade / 2] + [tempos[i] + xfade for i in range(1, count - 1)]
    lengths.append(max(tempos[-1] + xfade / 2, duration - offsets[-1]))  # sum short by <= 0.05 s: last slide fills it
    return lengths, offsets


def move(i, zoom, frames):
    """zoompan z/x/y for slide i: zoom in, zoom out, pan left to right, in turn."""
    centre = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    kind = i % 3
    if kind == 0:
        return "z='1+%g*on/%d':%s" % (zoom, frames, centre)
    if kind == 1:
        return "z='1+%g-%g*on/%d':%s" % (zoom, zoom, frames, centre)
    return "z='1+%g':x='(iw-iw/zoom)*on/%d':y='ih/2-(ih/zoom/2)'" % (zoom, frames)


def build_graph(count, width, height, fps, duration, xfade, zoom, tempos=None):
    """Filter graph text: one zoompan chain per input, a varied xfade between them, trimmed to duration.

    tempos: one scene length per slide (seconds); None gives every slide the same length.
    """
    if not tempos:
        seg = segment_seconds(count, duration, xfade)
        if count > 1 and seg <= xfade:
            raise ValueError("crossfade %.2f s is too long for %d slides in %.1f s" % (xfade, count, duration))
    lengths, offsets = timeline(count, duration, xfade, tempos)
    if tempos:  # never a frame short: a slide that ends before its cut does would shorten the video
        frames = [int(math.ceil(n * fps - 1e-6)) for n in lengths]
    else:
        frames = [int(round(n * fps)) for n in lengths]
    lines = []
    for i in range(count):
        lines.append(
            "[%d:v]scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,"
            "zoompan=%s:d=%d:s=%dx%d:fps=%d,"
            "setsar=1,format=yuv420p[s%d]" % (i, width * 2, height * 2, width * 2, height * 2,
                                              move(i, zoom, frames[i]), frames[i], width, height, fps, i))
    last = "s0"
    for i in range(1, count):
        out = "x%d" % i
        lines.append("[%s][s%d]xfade=transition=%s:duration=%g:offset=%g[%s]"
                     % (last, i, TRANSITIONS[(i - 1) % len(TRANSITIONS)], xfade, offsets[i - 1], out))
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
           ffmpeg="ffmpeg", graph_file=None, timeout=600, tempos=None):
    """Render the slides to `out`. Return (ok, message). The graph is kept next to the MP4.

    tempos: one scene length per slide; ValueError before ffmpeg runs if they do not fit.
    """
    slides = list_slides(slides_dir)
    graph = build_graph(len(slides), width, height, fps, duration, xfade, zoom, tempos)
    graph_file = graph_file or out + ".graph.txt"
    with open(graph_file, "w", encoding="utf-8") as f:
        f.write(graph)
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
    p.add_argument("--xfade", type=float, default=0.5, help="transition seconds")
    p.add_argument("--zoom", type=float, default=0.06, help="zoom or pan per slide (0.06 = 6%%)")
    p.add_argument("--tempos", help="seconds of each slide's scene, comma separated (1.5,2.5,2.5,3.5); "
                                    "one per slide, adding up to --duration")
    args = p.parse_args(argv)  # no tool-path option: a session could point it at its own file
    try:
        tempos = parse_tempos(args.tempos) if args.tempos is not None else None
        ok, msg = render(args.slides, args.out, args.width, args.height, args.duration, args.fps,
                         args.xfade, args.zoom, shutil.which("ffmpeg") or "ffmpeg", tempos=tempos)
    except (OSError, ValueError) as exc:
        print("reserva_slides: %s" % exc, file=sys.stderr)
        return 2
    print(msg, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
