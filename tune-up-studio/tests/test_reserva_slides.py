"""Unit tests for scripts/reserva_slides.py and scripts/video_ou_reserva.py. No Chrome, no network.

The render cases make slide PNGs with ffmpeg (lavfi testsrc2, so every slide has detail)
and are skipped when ffmpeg/ffprobe or libx264 are missing.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))
sys.path.insert(0, HERE)

import qa_video  # noqa: E402
import reserva_slides  # noqa: E402
import video_ou_reserva  # noqa: E402
from test_qa_imagem import SAVED, bound, clean_check, record_snapshot  # noqa: E402

SLIDES_SOURCE = os.path.join(STUDIO, "exemplos", "forno-miudo", "reserva-9x16", "fonte")
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")


def has_x264():
    if not FFMPEG:
        return False
    out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return b"libx264" in out.stdout


class Graph(unittest.TestCase):
    def test_segments_add_up_to_duration(self):
        seg = reserva_slides.segment_seconds(3, 10.0, 0.5)
        self.assertAlmostEqual(3 * seg - 2 * 0.5, 10.0)

    def test_graph_chains_every_slide(self):
        g = reserva_slides.build_graph(3, 1080, 1920, 30, 10.0, 0.5, 0.06)
        for label in ("[0:v]", "[1:v]", "[2:v]", "[x2]trim=duration=10", "zoompan", "xfade"):
            self.assertIn(label, g)
        self.assertNotIn("drawtext", g)

    def test_cuts_and_moves_vary_and_never_dissolve(self):
        # A plain dissolve shows two texts on top of each other; one zoom on every slide reads as a template.
        g = reserva_slides.build_graph(5, 1080, 1920, 30, 15.0, 0.5, 0.06)
        cuts = [line.split("transition=")[1].split(":")[0] for line in g.splitlines() if "xfade" in line]
        self.assertEqual(len(cuts), 4)
        self.assertEqual(len(set(cuts)), 4)
        self.assertNotIn("fade", cuts)
        moves = [line.split("zoompan=")[1].split(":d=")[0] for line in g.splitlines() if "zoompan" in line]
        self.assertTrue(all(moves[i] != moves[i - 1] for i in range(1, len(moves))), moves)

    def test_single_slide_has_no_crossfade(self):
        self.assertNotIn("xfade", reserva_slides.build_graph(1, 1080, 1920, 30, 10.0, 0.5, 0.06))

    def test_crossfade_longer_than_slide_is_refused(self):
        with self.assertRaises(ValueError):
            reserva_slides.build_graph(2, 1080, 1920, 30, 1.0, 1.5, 0.06)

    def test_command_whitelists_each_input_and_keeps_graph_in_file(self):
        cmd = reserva_slides.ffmpeg_command("ffmpeg", ["a.png", "b.png"], "g.txt", "o.mp4", 30, 10.0)
        self.assertEqual(cmd.count("-i"), 2)
        for i, tok in enumerate(cmd):
            if tok == "-i":
                self.assertEqual(cmd[i - 2:i], ["-protocol_whitelist", "file,pipe"])
        self.assertNotIn(";", " ".join(cmd))
        self.assertIn("comment=" + reserva_slides.MARK, cmd)

    def test_slide_folder_checks(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                reserva_slides.list_slides(d)
            with open(os.path.join(d, "a.png"), "wb") as f:
                f.write(b"not a png")
            with self.assertRaises(ValueError):
                reserva_slides.list_slides(d)


@unittest.skipUnless(FFPROBE and has_x264(), "needs ffmpeg with libx264 and ffprobe")
class Fallback(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="reserva-")
        cls.slides = os.path.join(cls.tmp, "slides")
        os.mkdir(cls.slides)
        for i in range(3):
            subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                            "testsrc2=s=540x960:r=1", "-vf", "hue=h=%d" % (i * 120), "-frames:v", "1",
                            os.path.join(cls.slides, "s%d.png" % i)], check=True)
        bound(clean_check(layout={"ok": True, "findings": [], "duration": 10}), SLIDES_SOURCE)
        cls.state = os.path.join(SLIDES_SOURCE, ".hyperframes", "video-state.json")
        cls.had_state = os.path.exists(cls.state)
        if not cls.had_state:  # the slides were snapshots of this source, with no warning
            record_snapshot(SLIDES_SOURCE, os.path.join(cls.slides, "s0.png"))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)
        if not cls.had_state and os.path.exists(cls.state):
            os.remove(cls.state)

    def qa(self, video, engine="reserve"):
        return qa_video.run(SLIDES_SOURCE, video, None, 1080, 1920, 10.0, 30, FFMPEG, FFPROBE, engine)

    def test_missing_hyperframes_falls_back_and_passes_qa(self):
        out = os.path.join(self.tmp, "v.mp4")
        rec = video_ou_reserva.run("fonte", self.slides, out, "/nonexistent/hyperframes", ffmpeg=FFMPEG)
        self.assertEqual(rec["engine"], "reserve")
        with open(out + ".engine.json", encoding="utf-8") as f:
            self.assertEqual(json.load(f)["engine"], "reserve")
        report = self.qa(out)
        self.assertTrue(report["ok"], [c for c in report["checks"] if not c["ok"]])

    def test_failing_hyperframes_falls_back(self):
        out = os.path.join(self.tmp, "f.mp4")
        with open(out, "wb") as f:
            f.write(b"stale")  # must not survive as the render
        rec = video_ou_reserva.run("fonte", self.slides, out, shutil.which("false") or "/usr/bin/false",
                                   ffmpeg=FFMPEG)
        self.assertEqual(rec["engine"], "reserve")
        self.assertIn("failed", rec["reason"])

    def test_untagged_video_fails_reserve_qa(self):
        out = os.path.join(self.tmp, "plain.mp4")
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                        "testsrc2=s=1080x1920:r=30:d=10", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-movflags", "+faststart", out], check=True)
        failed = [c["name"] for c in self.qa(out)["checks"] if not c["ok"]]
        self.assertEqual(failed, ["engine_reserve"])

    def test_reserve_video_cannot_pass_as_render(self):
        out = os.path.join(self.tmp, "as-render.mp4")
        video_ou_reserva.run("fonte", self.slides, out, "/nonexistent/hyperframes", ffmpeg=FFMPEG)
        failed = [c["name"] for c in self.qa(out, engine="hyperframes")["checks"] if not c["ok"]]
        self.assertEqual(failed, ["engine_hyperframes"])

    def test_reserve_still_needs_the_composition_check(self):
        out = os.path.join(self.tmp, "r.mp4")
        video_ou_reserva.run("fonte", self.slides, out, "/nonexistent/hyperframes", ffmpeg=FFMPEG)
        mine = os.path.join(os.path.realpath(SLIDES_SOURCE), "")
        saved = [r for r in SAVED if r.startswith(mine) and os.path.exists(r)]
        for report in saved:
            os.rename(report, report + ".off")
        try:
            failed = [c["name"] for c in self.qa(out)["checks"] if not c["ok"]]
        finally:
            for report in saved:
                os.rename(report + ".off", report)
        self.assertEqual(failed, ["hyperframes_check"])

    def test_both_engines_failing_reports_none(self):
        with tempfile.TemporaryDirectory() as empty:
            rec = video_ou_reserva.run("fonte", empty, os.path.join(self.tmp, "n.mp4"), "/nonexistent", ffmpeg=FFMPEG)
        self.assertIsNone(rec["engine"])
        self.assertIsNone(rec["video"])



class ToolOptions(unittest.TestCase):
    def test_tool_paths_are_not_options(self):
        # A session could point these at python3 or a file it wrote; tools come from PATH / ../node.
        cases = [(reserva_slides.main, ["--slides", "s", "--out", "v.mp4", "--ffmpeg", "python3"]),
                 (video_ou_reserva.main, ["--source", "f", "--slides", "s", "--out", "v.mp4", "--ffmpeg", "x"]),
                 (video_ou_reserva.main, ["--source", "f", "--slides", "s", "--out", "v.mp4", "--hyperframes", "x"])]
        for main, argv in cases:
            with self.subTest(argv=argv[-2]), open(os.devnull, "w") as devnull:
                err, sys.stderr = sys.stderr, devnull
                try:
                    with self.assertRaises(SystemExit) as ctx:
                        main(argv)
                finally:
                    sys.stderr = err
                self.assertEqual(ctx.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
