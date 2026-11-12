#!/usr/bin/env python3
"""QA for a short silent video (9:16 reel) rendered by HyperFrames.

Standard library plus ffprobe/ffmpeg. It does not run Chrome: it probes the
MP4, runs ffmpeg blackdetect and freezedetect, scans the composition source
folder and reads what HyperFrames saved under `<source>/.hyperframes/` (never a
copy the session wrote): the `check --strict` report and the newest snapshot
record, whose warnings list a brand font that failed to load. The MP4 must be
newer than the source and than that check report. The report carries a final
line in `linha` (PRONTO / PRECISA DO SEU OLHO) and, with --sheet, a contact
sheet PNG of the MP4 (frames at --at seconds, else 0 and every 0.5 s from 0.25; 5 per row);
with --atencao also `<sheet>_cortes.png` (0.35 s before and after each cut) and
the empty area at 70% of each scene (qa_vazio.py).

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
    GSAP_RE, LAYOUT_ALLOW_RE, NETWORK_PATTERNS, check_images, check_strict_json, load_json, newest_mtime,
    newest_report, result, saved_report, scan, snapshot_records)
from reserva_slides import MARK  # noqa: E402
import qa_atencao  # noqa: E402
import qa_cenas  # noqa: E402
import qa_css  # noqa: E402
import qa_quadros  # noqa: E402
import qa_vazio  # noqa: E402

BLACK_FILTER = "blackdetect=d=0.5:pix_th=0.10"
FREEZE_FILTER = "freezedetect=n=-70dB:d=1.0"  # nothing still for 1 s (ritmo.md)
# `movimento`: frames every 0.25 s at 108x192 gray; a mean change under MOVE_MIN levels counts as "almost still"
# (a 24 px settle, a pulse too small to see). Measured on real renders: a slow camera push gives 0.5-1.5, a scene
# the director called still gave 0.00-0.22. MOVE_RUN steps in a row (0.75 s) fail anywhere but the final hold:
# the end card moves too (the judge of round 4 saw 3 s of a still end card), only its last MOVE_HOLD s may rest.
MOVE_FPS, MOVE_W, MOVE_H, MOVE_MIN, MOVE_RUN, MOVE_HOLD = 4, 108, 192, 0.4, 3, 1.0
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


def probe(video, ffprobe, timeout=300):
    code, out, err = run_tool([ffprobe, "-v", "error", "-print_format", "json", "-count_frames",
                               "-show_streams", "-show_format", video], timeout)
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
    return result("freezedetect", not found, found or ["no still span >= 1.0 s"])


def check_movement(video, ffmpeg, scenes):
    """`movimento`: no 0.75 s almost still (mean change under MOVE_MIN per 0.25 s) before the final hold (the
    last MOVE_HOLD s of the video; `scenes` gives its end)."""
    try:
        out = subprocess.run([ffmpeg, "-v", "error", "-i", video, "-vf", "fps=%d,scale=%d:%d" % (MOVE_FPS, MOVE_W, MOVE_H),
                              "-f", "rawvideo", "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, timeout=300).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return result("movimento", False, ["ffmpeg failed: %s" % exc])
    n = MOVE_W * MOVE_H
    frames = [out[i:i + n] for i in range(0, len(out) - n + 1, n)]
    fim = scenes[-1][0] + scenes[-1][1] - MOVE_HOLD if scenes else float("inf")
    problems, run = [], []
    for i in range(len(frames) - 1):
        t = i / float(MOVE_FPS)
        quieto = t + 1.0 / MOVE_FPS <= fim + 1e-6 and \
            sum(abs(a - b) for a, b in zip(frames[i], frames[i + 1])) / float(n) < MOVE_MIN
        if quieto:
            run.append(t)
            continue
        if len(run) >= MOVE_RUN:
            problems.append("quase parado de %.2f s a %.2f s: câmera, stagger ou segunda batida (motion-js.md)"
                            % (run[0], run[-1] + 1.0 / MOVE_FPS))
        run = []
    if len(run) >= MOVE_RUN:
        problems.append("quase parado de %.2f s a %.2f s: câmera, stagger ou segunda batida (motion-js.md)"
                        % (run[0], run[-1] + 1.0 / MOVE_FPS))
    if len(frames) < 2:
        problems.append("ffmpeg gave fewer than 2 frames")
    return result("movimento", not problems, problems or ["ok"])


def check_reserve_tag(data):
    """Reserve videos have no HyperFrames composition to check; they must carry the reserve tag."""
    tag = ((data.get("format") or {}).get("tags") or {}).get("comment")
    return result("engine_reserve", tag == MARK, ["comment=%r (expected %r)" % (tag, MARK)])


def check_fresh(video, source, check_json):
    """The MP4 must be newer than every source file and than the check report the QA reads."""
    report = None
    if check_json is not None:
        data, _ = load_json(check_json)
        report = saved_report(data, source) if data is not None else None
    else:
        report = newest_report(source)
    try:
        made = os.path.getmtime(video)
    except OSError as exc:
        return result("video_fresh", False, [str(exc)])
    problems = []
    if made < newest_mtime(source):
        problems.append("source changed after the MP4; render again")
    if report is not None and made < os.path.getmtime(report):
        problems.append("check report is newer than the MP4; render again")
    return result("video_fresh", not problems, problems or ["ok"])


def check_fonts(source):
    """Green only if the newest snapshot of `source` recorded no warning (a brand font that did not
    load is one: "Fonts failed: ..."), as the post QA does."""
    data, err = load_json(os.path.join(source, ".hyperframes", "video-state.json"))
    if err:
        return result("brand_font", False, [err])
    found = [r for r in snapshot_records(data.get("snapshots"))
             if isinstance(r.get("createdAt"), (int, float))]
    if not found:
        return result("brand_font", False, ["no snapshot recorded for %s; run snapshot" % source])
    newest = max(r["createdAt"] for r in found)
    problems = []
    for r in found:
        meta = r.get("metadata") if isinstance(r.get("metadata"), dict) else {}
        warnings = meta.get("warnings")
        if r["createdAt"] == newest:
            problems += ["snapshot warning: %s" % w for w in warnings] if isinstance(warnings, list) \
                else ["snapshot record has no warnings list"]
    if newest / 1000.0 < newest_mtime(source):
        problems.append("source changed after the snapshot; run snapshot again")
    return result("brand_font", not problems, sorted(set(problems)) or ["ok"])


def parse_times(text, duration):
    """Comma list of seconds in [0, duration); raise ValueError otherwise."""
    times = [float(t) for t in text.split(",") if t.strip()]
    if not times or any(t < 0 or t >= duration for t in times):
        raise ValueError("--at needs seconds from 0 to below %g" % duration)
    return times


def contact_sheet(video, out, duration, ffmpeg, times=None, fps=30.0):
    """Frames of the MP4 at `times` (default: 0, then every 0.5 s from 0.25 s) in a 5-column grid PNG."""
    if not times:  # the cover, then every 0.5 s off the cuts (a cut at a round second is the transition's peak)
        times = [0.0] + [0.25 + i * 0.5 for i in range(int(duration * 2)) if 0.25 + i * 0.5 < duration]
    pick = "+".join("eq(n\\,%d)" % int(round(t * fps)) for t in times)
    count, vf = len(times), "select=%s,scale=216:384" % pick
    rows = (count + 4) // 5
    code, _, err = run_tool([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-an",
                             "-vf", "%s,tile=%dx%d" % (vf, min(count, 5), rows), "-frames:v", "1", out])
    ok = code == 0 and os.path.isfile(out)
    return result("contact_sheet", ok, [out if ok else "ffmpeg failed: %s" % err.strip()[-300:]])


def scenes_of(source, duration):
    """[(start, length)] of the scenes of the composition (qa_cenas.cenas), or [] when it cannot be read."""
    doc = qa_css.ler_fonte(source) if os.path.isdir(source) else None
    if doc is None:
        return []
    found, _ = qa_cenas.cenas([e for e in doc["elementos"] if "clip" in e["classes"]], duration)
    return [found[n][:2] for n in sorted(found)]


def cut_times(scenes, duration):
    """0.35 s before and after each cut, just outside its 0.6 s transition: a half-gone line or a transition
    leftover shows up there."""
    out = []
    for start, _ in scenes[1:]:
        out += [round(t, 2) for t in (start - 0.35, start + 0.35) if 0 <= t < duration]
    return out


def check_occupancy(video, ffmpeg, scenes, width, height):
    """`ocupacao`: the frame at 70% of each scene (entries and the second beat landed) has no void above
    qa_vazio.VIDEO_MAX of the reel safe box."""
    w, h = 216, 384  # the safe box of the reel (x 90-990, y 269-1536 of 1080x1920) at this size
    escala, caixa = w / float(width), (w * 90 / 1080.0, h * 269 / 1920.0, w * 990 / 1080.0, h * 1536 / 1920.0)
    problems = []
    for n, (start, length) in enumerate(scenes, 1):
        try:
            out = subprocess.run([ffmpeg, "-v", "error", "-ss", "%.3f" % (start + length * 0.7), "-i", video,
                                  "-frames:v", "1", "-vf", "scale=%d:%d" % (w, h), "-f", "rawvideo",
                                  "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 timeout=60).stdout
        except (OSError, subprocess.SubprocessError) as exc:
            return result("ocupacao", False, ["ffmpeg failed: %s" % exc])
        if len(out) < w * h * 3:
            return result("ocupacao", False, ["ffmpeg gave no frame at %.2f s" % (start + length * 0.7)])
        frac, ret = qa_vazio.medir(w, h, 3, [out[y * w * 3:(y + 1) * w * 3] for y in range(h)], caixa)
        erro = qa_vazio.problema(frac, ret, qa_vazio.VIDEO_MAX, "cena %d" % n, escala)
        if erro:
            problems.append(erro)
    return result("ocupacao", not problems, problems or ["ok"])


def final_line(report, engine):
    if report["ok"]:
        return "PRONTO: video verde (%s)" % engine
    return "PRECISA DO SEU OLHO: %s" % ", ".join(c["name"] for c in report["checks"] if not c["ok"])


def run(source, video, check_json, width, height, duration, fps, ffmpeg, ffprobe, engine="hyperframes",
        atencao=False):
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
        checks += [check_images(source), check_fresh(video, source, check_json), check_fonts(source)]
    if engine == "reserve":  # the slides are snapshots of the same composition: it is checked too
        checks.append(check_reserve_tag(data))
    elif check_reserve_tag(data)["ok"]:  # a reserve MP4 is never reported as a render
        checks.append(result("engine_hyperframes", False, ["the MP4 carries the reserve tag; use --engine reserve"]))
    checks.append(check_strict_json(check_json, source, duration))
    if atencao and os.path.isdir(source):
        checks += qa_atencao.checar_video(source, duration, engine)
        scenes = scenes_of(source, duration)
        if scenes and data:  # the MP4 was probed
            checks.append(check_occupancy(video, ffmpeg, scenes, width, height))
            checks.append(qa_quadros.check_quadro_de_corte(video, ffmpeg, scenes))
            if engine == "hyperframes":  # the reserve is still slides by design
                checks.append(check_movement(video, ffmpeg, scenes))
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
    p.add_argument("--at", help="sheet frame times in seconds, comma list (default: every 0.5 s)")
    p.add_argument("--atencao", action="store_true", help="also the attention checks (qa_atencao.py)")
    args = p.parse_args(argv)
    try:
        times = parse_times(args.at, args.duration) if args.at else None
    except ValueError as exc:
        p.error(str(exc))
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    report = run(args.source, args.video, args.check_json, args.width, args.height,
                 args.duration, args.fps, ffmpeg, shutil.which("ffprobe") or "ffprobe", args.engine, args.atencao)
    if args.sheet:
        report["checks"].append(contact_sheet(args.video, args.sheet, args.duration, ffmpeg, times, args.fps))
        cuts = cut_times(scenes_of(args.source, args.duration), args.duration) if args.atencao else []
        if cuts:
            stem = os.path.splitext(args.sheet)[0]
            report["checks"].append(dict(contact_sheet(args.video, stem + "_cortes.png", args.duration, ffmpeg,
                                                       cuts, args.fps), name="contact_sheet_cuts"))
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
