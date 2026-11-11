"""Unit tests for scripts/qa_video.py. No Chrome, no network.

The video cases synthesize small clips with ffmpeg (lavfi sources) and are
skipped when ffmpeg/ffprobe or libx264 are missing.
"""
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))
sys.path.insert(0, HERE)

import qa_video  # noqa: E402
from test_qa_imagem import bound, clean_check, record_snapshot  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
VIDEO_SOURCE = os.path.join(STUDIO, "exemplos", "forno-miudo", "video-9x16", "fonte")
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
W, H = 180, 320


def has_x264():
    if not FFMPEG:
        return False
    out = subprocess.run([FFMPEG, "-hide_banner", "-encoders"], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL).stdout
    return b"libx264" in out


@unittest.skipUnless(FFPROBE and has_x264(), "ffmpeg/ffprobe with libx264 not available")
class VideoChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # A copy of the example source with the snapshot record HyperFrames would write.
        self.source = os.path.join(self.tmp, "fonte")
        shutil.copytree(VIDEO_SOURCE, self.source, ignore=shutil.ignore_patterns(".hyperframes"))
        record_snapshot(self.source, os.path.join(self.tmp, "snap.png"))
        self.check = os.path.join(self.tmp, "check.json")
        with open(self.check, "w", encoding="utf-8") as f:
            json.dump(bound(clean_check(layout={"ok": True, "findings": [], "duration": 3}), self.source), f)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def make(self, name, inputs, extra=(), faststart=True):
        out = os.path.join(self.tmp, name)
        cmd = [FFMPEG, "-v", "error", "-y"] + inputs + list(extra) + [
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30"]
        cmd += (["-movflags", "+faststart"] if faststart else []) + [out]
        subprocess.run(cmd, check=True)
        return out

    def moving(self, seconds=3):
        return ["-f", "lavfi", "-i", "testsrc2=size=%dx%d:rate=30:duration=%d" % (W, H, seconds)]

    def report(self, video, duration=3.0, source=None):
        return qa_video.run(source or self.source, video, self.check, W, H, duration, 30.0, FFMPEG, FFPROBE)

    def failed(self, rep):
        return sorted(c["name"] for c in rep["checks"] if not c["ok"])

    def test_clean_clip_is_green(self):
        rep = self.report(self.make("ok.mp4", self.moving()))
        self.assertTrue(rep["ok"], rep)

    def test_one_second_of_black_is_caught(self):
        video = self.make("black.mp4", self.moving(1) + [
            "-f", "lavfi", "-i", "color=black:size=%dx%d:rate=30:duration=1" % (W, H)] + self.moving(1),
            ["-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0"])
        rep = self.report(video)
        self.assertEqual(self.failed(rep), ["blackdetect"])

    def test_still_frame_is_caught(self):
        video = self.make("still.mp4", ["-f", "lavfi", "-i", "color=0xF4E4C8:size=%dx%d:rate=30:duration=3" % (W, H)])
        self.assertEqual(self.failed(self.report(video)), ["freezedetect"])

    def test_audio_track_is_caught(self):
        video = self.make("audio.mp4", self.moving() + ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono"],
                          ["-shortest", "-c:a", "aac"])
        self.assertIn("no_audio", self.failed(self.report(video)))

    def test_missing_faststart_is_caught(self):
        video = self.make("slow.mp4", self.moving(), faststart=False)
        self.assertEqual(self.failed(self.report(video)), ["faststart"])

    def test_wrong_duration_size_and_fps(self):
        video = self.make("ok.mp4", self.moving())
        rep = qa_video.run(self.source, video, self.check, 1080, 1920, 10.0, 24.0, FFMPEG, FFPROBE)
        self.assertEqual(self.failed(rep), ["duration", "fps", "frames", "hyperframes_check", "video_size"])

    def test_source_defects_still_counted(self):
        video = self.make("ok.mp4", self.moving())
        rep = self.report(video, source=os.path.join(FIXTURES, "defect-allow-overflow"))
        self.assertIn("layout_allow_count", self.failed(rep))
        rep = self.report(video, source=os.path.join(FIXTURES, "defect-external-fetch"))
        self.assertIn("network_lint", self.failed(rep))

    def test_truncated_clip_is_caught(self):
        # Observed by review: faststart keeps moov (and the duration) up front, so a cut
        # file probes fine and ffmpeg exits 0 after decoding only part of the frames.
        video = self.make("ok.mp4", self.moving())
        cut = os.path.join(self.tmp, "cut.mp4")
        with open(video, "rb") as f, open(cut, "wb") as g:
            g.write(f.read()[:int(os.path.getsize(video) * 0.4)])
        rep = self.report(cut)
        self.assertFalse(rep["ok"])
        self.assertIn("frames", self.failed(rep))

    def test_check_of_another_piece_fails(self):
        video = self.make("ok.mp4", self.moving())
        post = os.path.join(STUDIO, "exemplos", "forno-miudo", "post-4x5", "fonte")
        with open(self.check, "w", encoding="utf-8") as f:
            json.dump(bound(clean_check(layout={"ok": True, "findings": [], "duration": 5}), post), f)
        self.assertEqual(self.failed(self.report(video)), ["hyperframes_check"])

    def test_tool_paths_are_not_options(self):
        # A session could point --ffprobe at python3 and run a file it wrote.
        for opt in ("--ffprobe", "--ffmpeg"):
            with self.subTest(opt), self.assertRaises(SystemExit) as ctx:
                with open(os.devnull, "w") as devnull:
                    err, sys.stderr = sys.stderr, devnull
                    try:
                        qa_video.main(["--source", VIDEO_SOURCE, "--video", "v.mp4",
                                       "--check-json", self.check, opt, "python3"])
                    finally:
                        sys.stderr = err
                self.assertEqual(ctx.exception.code, 2)

    def test_main_exit_codes(self):
        video = self.make("ok.mp4", self.moving())
        base = ["--source", self.source, "--video", video, "--check-json", self.check,
                "--width", str(W), "--height", str(H), "--duration", "3", "--out",
                os.path.join(self.tmp, "qa.json")]
        self.assertEqual(qa_video.main(base), 0)
        self.assertEqual(qa_video.main(base[:-4] + ["--duration", "10"]), 1)

    def test_main_reads_saved_report_writes_sheet_and_line(self):
        # The session never passes a copy of the check: the newest saved report is read.
        video = self.make("ok.mp4", self.moving())
        sheet, out = os.path.join(self.tmp, "folha.png"), os.path.join(self.tmp, "qa.json")
        base = ["--source", self.source, "--video", video, "--width", str(W), "--height", str(H),
                "--out", out, "--sheet", sheet]
        with open(os.devnull, "w") as devnull:
            old, sys.stdout = sys.stdout, devnull
            try:
                good = qa_video.main(base + ["--duration", "3"])
                bad = qa_video.main(base + ["--duration", "10"])
            finally:
                sys.stdout = old
        self.assertEqual((good, bad), (0, 1))
        with open(out, encoding="utf-8") as f:
            rep = json.load(f)
        self.assertTrue(rep["linha"].startswith("PRECISA DO SEU OLHO: duration"))
        self.assertIn("contact_sheet", [c["name"] for c in rep["checks"] if c["ok"]])
        with open(sheet, "rb") as f:
            self.assertEqual(f.read(8), b"\x89PNG\r\n\x1a\n")
        self.assertEqual(qa_video.final_line({"ok": True, "checks": []}, "reserve"), "PRONTO: video verde (reserve)")

    def test_mp4_older_than_source_or_check_fails(self):
        video = self.make("ok.mp4", self.moving())
        old = os.path.getmtime(video) - 60
        os.utime(video, (old, old))
        self.assertEqual(self.failed(self.report(video)), ["video_fresh"])  # the check report is newer
        index = os.path.join(self.source, "index.html")
        os.utime(index, None)
        record_snapshot(self.source, os.path.join(self.tmp, "snap.png"))
        rep = self.report(video)
        self.assertIn("source changed after the MP4; render again", [d for c in rep["checks"]
                                                                     if c["name"] == "video_fresh" for d in c["details"]])

    def test_brand_font_that_failed_is_caught(self):
        video = self.make("ok.mp4", self.moving())
        record_snapshot(self.source, os.path.join(self.tmp, "snap.png"), ["Fonts failed: Brand Heading (400 normal)"])
        rep = self.report(video)
        self.assertEqual(self.failed(rep), ["brand_font"])
        font = next(c for c in rep["checks"] if c["name"] == "brand_font")
        self.assertIn("Fonts failed", font["details"][0])
        os.remove(os.path.join(self.source, ".hyperframes", "video-state.json"))
        self.assertEqual(self.failed(self.report(video)), ["brand_font"])

    def test_sheet_frames_at_given_times(self):
        video = self.make("ok.mp4", self.moving())
        sheet = os.path.join(self.tmp, "folha.png")
        base = ["--source", self.source, "--video", video, "--width", str(W), "--height", str(H),
                "--duration", "3", "--sheet", sheet]
        with open(os.devnull, "w") as devnull:
            old, sys.stdout = sys.stdout, devnull
            try:
                self.assertEqual(qa_video.main(base + ["--at", "0,0.75,1.5,2.9"]), 0)
            finally:
                sys.stdout = old
        with open(sheet, "rb") as f:
            head = f.read(24)
        self.assertEqual(struct.unpack(">II", head[16:24]), (4 * 216, 384))  # 4 frames in one row
        with open(os.devnull, "w") as devnull, self.assertRaises(SystemExit) as ctx:
            err, sys.stderr = sys.stderr, devnull
            try:
                qa_video.main(base + ["--at", "0,3"])  # 3 s is past the last frame of a 3 s video
            finally:
                sys.stderr = err
        self.assertEqual(ctx.exception.code, 2)


class Pure(unittest.TestCase):
    def test_atoms_order(self):
        with tempfile.NamedTemporaryFile(delete=False) as f:
            for kind in (b"ftyp", b"mdat", b"moov"):
                f.write(struct.pack(">I4s", 16, kind) + b"\0" * 8)
        try:
            self.assertEqual(qa_video.top_level_atoms(f.name), ["ftyp", "mdat", "moov"])
        finally:
            os.remove(f.name)

    def test_fps_parsing(self):
        self.assertEqual(qa_video.fps_of({"r_frame_rate": "30/1"}), 30.0)
        self.assertEqual(qa_video.fps_of({"r_frame_rate": "0/0"}), 0.0)
        self.assertEqual(qa_video.fps_of({}), 0.0)

    def test_missing_video_fails_cleanly(self):
        rep = qa_video.run(VIDEO_SOURCE, "/nonexistent.mp4", "/nonexistent.json",
                           1080, 1920, 10.0, 30.0, FFMPEG or "ffmpeg", FFPROBE or "ffprobe")
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["checks"][0]["name"], "probe")

    def test_real_source_is_clean(self):
        for rx in ([("gsap", qa_video.GSAP_RE)], qa_video.NETWORK_PATTERNS,
                   [("allow", qa_video.LAYOUT_ALLOW_RE)]):
            self.assertEqual(qa_video.scan(VIDEO_SOURCE, rx, strip_xmlns=True), [])


if __name__ == "__main__":
    unittest.main()
