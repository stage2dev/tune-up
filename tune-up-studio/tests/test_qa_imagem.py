"""Unit tests for scripts/qa_imagem.py. No Chrome, no network."""
import atexit
import contextlib
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import time
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))
sys.path.insert(0, HERE)

import qa_imagem  # noqa: E402
from test_qa_atencao import COPY, escrever, post_html, projeto  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
POST_SOURCE = os.path.join(STUDIO, "exemplos", "forno-miudo", "post-4x5", "fonte")


def write_png(path, width, height, cheio=False):
    """A white PNG; `cheio` stripes it every third pixel, so no part of it is empty (qa_vazio)."""
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = (b"\xff" * 6 + b"\x00" * 3) * (width // 3 + 1) if cheio else b"\xff" * (3 * width)
    pixels = pixels[:3 * width]
    rows = (b"\0" + pixels) * height
    with open(path, "wb") as f:
        f.write(qa_imagem.PNG_SIGNATURE + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


SAVED = []  # reports written under sources kept in the repo; removed at exit


def bound(data, source):
    """The check JSON names its saved report under the source it ran on; HyperFrames wrote it there."""
    checks = os.path.join(os.path.realpath(source), ".hyperframes", "artifacts", "checks")
    os.makedirs(checks, exist_ok=True)
    report = os.path.join(checks, "unittest-%d.json" % os.getpid())
    with open(report, "w", encoding="utf-8") as f:
        json.dump(data, f)
    if report not in SAVED:
        SAVED.append(report)
    return dict(data, saved={"report": report})


def record_snapshot(source, png, warnings=(), created=None):
    """What `hyperframes snapshot` records in <source>/.hyperframes/video-state.json (shape observed)."""
    state = os.path.join(source, ".hyperframes", "video-state.json")
    os.makedirs(os.path.dirname(state), exist_ok=True)
    entry = {"scope": "full", "image": os.path.realpath(png), "time": 0,
             "createdAt": time.time() * 1000 + 1000 if created is None else created,
             "metadata": {"width": 1080, "height": 1350, "warnings": list(warnings),
                          "partial": bool(warnings)}}
    with open(state, "w", encoding="utf-8") as f:
        json.dump({"version": 1, "checks": {}, "snapshots": {"latest": [entry], "unversioned": [entry]}}, f)


@atexit.register
def _remove_saved():
    for report in SAVED:
        if os.path.exists(report):
            os.remove(report)


def clean_check(**overrides):
    data = {"ok": True, "strict": True, "browserSkipped": False,
            "lint": {"ok": True, "findings": []},
            "layout": {"ok": True, "findings": []},
            "audio": {"ok": True, "findings": [
                {"code": "audio_none", "severity": "info", "message": "no sound"}]}}
    data.update(overrides)
    return data


# Shape observed from `check --json --strict` on fixtures/defect-text-overflow.
OVERFLOW_CHECK = clean_check(ok=False, layout={"ok": False, "findings": [
    {"code": "text_box_overflow", "severity": "error", "selector": "div.caixa > h1",
     "message": "Text extends outside its nearest visual/container box."},
    {"code": "canvas_overflow", "severity": "warning", "selector": "div.caixa > h1",
     "message": "Text extends outside the composition canvas."}]})


class QaImagemTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.png = os.path.join(self.tmp, "post.png")
        write_png(self.png, 1080, 1350)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def check_file(self, data, source=None):
        path = os.path.join(self.tmp, "check.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(bound(data, source) if source else data, f)
        return path

    def source(self, html, extra=None):
        folder = os.path.join(self.tmp, "fonte")
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        for name, text in (extra or {}).items():
            with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
                f.write(text)
        return folder

    def failed(self, report):
        return sorted(c["name"] for c in report["checks"] if not c["ok"])

    def named(self, report, name):
        return next(c for c in report["checks"] if c["name"] == name)

    def test_real_post_source_passes_static_checks(self):
        report = qa_imagem.run(POST_SOURCE, self.png, self.check_file(clean_check(), POST_SOURCE), 1080, 1350)
        self.assertEqual(self.failed(report), [])
        self.assertTrue(report["ok"])

    def test_svg_namespace_is_not_a_network_hit(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"/>'
        folder = self.source("<p>ok</p>", {"logo.svg": svg})
        self.assertEqual(qa_imagem.scan(folder, qa_imagem.NETWORK_PATTERNS, strip_xmlns=True), [])

    def test_other_w3_url_is_still_a_hit(self):
        folder = self.source('<img src="http://www.w3.org/x.png">')
        self.assertTrue(qa_imagem.scan(folder, qa_imagem.NETWORK_PATTERNS, strip_xmlns=True))

    def test_wrong_png_size_fails(self):
        write_png(self.png, 1080, 1080)
        report = qa_imagem.run(POST_SOURCE, self.png, self.check_file(clean_check(), POST_SOURCE), 1080, 1350)
        self.assertEqual(self.failed(report), ["png_size"])

    def test_huge_declared_size_is_refused_before_inflating(self):
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
        with open(self.png, "wb") as f:  # IHDR says 100000x100000 (~30 GB raw): a decompression bomb
            f.write(qa_imagem.PNG_SIGNATURE + chunk(b"IHDR", struct.pack(">IIBBBBB", 100000, 100000, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(b"\0" * 100000)) + chunk(b"IEND", b""))
        real = qa_imagem.zlib.decompressobj
        qa_imagem.zlib.decompressobj = lambda *a: self.fail("inflated a PNG bigger than any format")
        try:
            report = qa_imagem.check_png(self.png, 1080, 1350)
        finally:
            qa_imagem.zlib.decompressobj = real
        self.assertFalse(report["ok"])
        self.assertIn("too large", report["details"][0])

    def test_not_a_png_fails(self):
        with open(self.png, "wb") as f:
            f.write(b"GIF89a")
        self.assertFalse(qa_imagem.check_png(self.png, 1080, 1350)["ok"])

    def test_defect_text_overflow_fails_on_check(self):
        source = os.path.join(FIXTURES, "defect-text-overflow")
        report = qa_imagem.run(source, self.png, self.check_file(OVERFLOW_CHECK, source), 1080, 1350)
        self.assertEqual(self.failed(report), ["hyperframes_check"])
        details = " ".join(self.named(report, "hyperframes_check")["details"])
        self.assertIn("text_box_overflow", details)

    def test_defect_allow_overflow_fails_even_when_check_is_green(self):
        # Observed: the attribute silences the check (ok=true), so only the count catches it.
        source = os.path.join(FIXTURES, "defect-allow-overflow")
        report = qa_imagem.run(source, self.png, self.check_file(clean_check(), source), 1080, 1350)
        self.assertEqual(self.failed(report), ["layout_allow_count"])
        self.assertIn("count=1", self.named(report, "layout_allow_count")["details"][0])

    def test_defect_external_fetch_caught_by_lint(self):
        source = os.path.join(FIXTURES, "defect-external-fetch")
        report = qa_imagem.run(source, self.png, self.check_file(clean_check(), source), 1080, 1350)
        self.assertEqual(self.failed(report), ["network_lint", "no_script"])
        net = " ".join(self.named(report, "network_lint")["details"])
        self.assertIn("fetch(", net)
        # The URL is built as "ht" + "tp://": the plain URL pattern cannot see it.
        self.assertNotIn("absolute URL", net)

    def test_network_patterns(self):
        cases = ['<link href="https://cdn.example/x.css">', "a{background:url( 'http://x/y.png')}",
                 '<script src="//cdn.example/a.js"></script>', "new XMLHttpRequest()",
                 "new WebSocket(u)", "import('./x.js')", "navigator.sendBeacon(u)",
                 "new EventSource(u)"]
        for text in cases:
            with self.subTest(text=text):
                folder = self.source(text)
                self.assertTrue(qa_imagem.scan(folder, qa_imagem.NETWORK_PATTERNS, strip_xmlns=True))

    def test_gsap_fails(self):
        folder = self.source("<script>window.GSAP = 1;</script>")
        report = qa_imagem.run(folder, self.png, self.check_file(clean_check(), folder), 1080, 1350)
        self.assertEqual(self.failed(report), ["no_gsap", "no_script"])

    def test_hyperframes_artifacts_are_skipped(self):
        folder = self.source("<p>ok</p>")
        os.makedirs(os.path.join(folder, ".hyperframes"))
        with open(os.path.join(folder, ".hyperframes", "x.json"), "w") as f:
            f.write('{"u": "https://x", "gsap": 1}')
        report = qa_imagem.run(folder, self.png, self.check_file(clean_check(), folder), 1080, 1350)
        self.assertTrue(report["ok"], report)

    def test_check_json_guards(self):
        cases = {"not strict": clean_check(strict=False),
                 "browser skipped": clean_check(browserSkipped=True),
                 "ok false": clean_check(ok=False),
                 "warning only": clean_check(layout={"findings": [
                     {"severity": "warning", "code": "canvas_overflow"}]})}
        for label, data in cases.items():
            with self.subTest(label):
                self.assertFalse(qa_imagem.check_strict_json(self.check_file(data))["ok"])
        self.assertFalse(qa_imagem.check_strict_json(os.path.join(self.tmp, "missing.json"))["ok"])
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w") as f:
            f.write("[1, 2]")
        self.assertFalse(qa_imagem.check_strict_json(bad)["ok"])

    def test_other_layout_silencers_are_counted(self):
        # Observed by review: each of these makes `check --strict` exit 0 on an overflowing h1.
        for name in ("defect-ignore-parent", "defect-bleed", "defect-dataset-script"):
            with self.subTest(name):
                source = os.path.join(FIXTURES, name)
                report = qa_imagem.run(source, self.png, self.check_file(clean_check(), source), 1080, 1350)
                self.assertIn("layout_allow_count", self.failed(report))
                self.assertFalse(report["ok"])
        for text in ('el.setAttribute("data-layout-ignore", "")', "el.dataset.layoutIgnore = 1",
                     '<p data-layout-boundary>x</p>', "x.dataset['layoutCheck'] = 'ignore'"):
            with self.subTest(text=text):
                self.assertTrue(qa_imagem.scan(self.source(text), [("allow", qa_imagem.LAYOUT_ALLOW_RE)]))

    def test_script_in_post_fails(self):
        folder = self.source("<p>ok</p><script>var a = 1;</script>")
        report = qa_imagem.run(folder, self.png, self.check_file(clean_check(), folder), 1080, 1350)
        self.assertEqual(self.failed(report), ["no_script"])

    def test_truncated_png_fails(self):
        with open(self.png, "rb") as f:
            whole = f.read()
        for label, data in (("100 bytes", whole[:100]), ("no IEND", whole[:-12]),
                            ("bad CRC", whole[:40] + bytes([whole[40] ^ 1]) + whole[41:])):
            with self.subTest(label):
                with open(self.png, "wb") as f:
                    f.write(data)
                self.assertFalse(qa_imagem.check_png(self.png, 1080, 1350)["ok"])
        short = os.path.join(self.tmp, "short.png")
        write_png(short, 1080, 1350)
        with open(short, "rb") as f:  # IDAT holds fewer rows than IHDR promises
            body = f.read()
        write_png(short, 1080, 1349)
        with open(short, "rb") as f:
            fewer = f.read()
        ihdr_end = 8 + 25
        with open(short, "wb") as f:
            f.write(body[:ihdr_end] + fewer[ihdr_end:])
        self.assertFalse(qa_imagem.check_png(short, 1080, 1350)["ok"])
        write_png(self.png, 1080, 1350)
        self.assertTrue(qa_imagem.check_png(self.png, 1080, 1350)["ok"])

    def test_check_json_is_bound_to_its_source(self):
        clean_post = self.check_file(clean_check(), POST_SOURCE)
        overflow = os.path.join(FIXTURES, "defect-text-overflow")
        report = qa_imagem.run(overflow, self.png, clean_post, 1080, 1350)
        self.assertEqual(self.failed(report), ["hyperframes_check"])
        self.assertFalse(qa_imagem.check_strict_json(self.check_file(clean_check()), POST_SOURCE)["ok"])
        folder = self.source("<p>ok</p>")
        path = self.check_file(clean_check(), folder)
        self.assertTrue(qa_imagem.check_strict_json(path, folder)["ok"])
        with open(path, encoding="utf-8") as f:
            os.utime(json.load(f)["saved"]["report"], (1, 1))  # the source was edited after the check
        self.assertFalse(qa_imagem.check_strict_json(path, folder)["ok"])
        path = self.check_file(clean_check(layout={"ok": True, "findings": [], "duration": 5}), folder)
        self.assertTrue(qa_imagem.check_strict_json(path, folder, duration=5.0)["ok"])
        self.assertFalse(qa_imagem.check_strict_json(path, folder, duration=10.0)["ok"])

    def test_verdict_comes_from_the_saved_report_not_the_transcript(self):
        # Observed in review: the session copies check output by hand; a copy that drops the
        # findings must not turn a red check green. The report HyperFrames wrote decides.
        folder = self.source("<p>ok</p>")
        path = self.check_file(clean_check(), folder)
        with open(path, encoding="utf-8") as f:
            report = json.load(f)["saved"]["report"]
        with open(report, "w", encoding="utf-8") as f:
            json.dump(OVERFLOW_CHECK, f)
        result = qa_imagem.check_strict_json(path, folder)
        self.assertFalse(result["ok"], result)
        os.remove(report)  # the transcript names a report that is not on disk
        self.assertFalse(qa_imagem.check_strict_json(path, folder)["ok"])

    def main_quiet(self, args):
        with open(os.devnull, "w") as devnull:
            stdout, sys.stdout = sys.stdout, devnull
            try:
                return qa_imagem.main(args)
            finally:
                sys.stdout = stdout

    def test_main_exit_codes_and_out_file(self):
        out = os.path.join(self.tmp, "qa.json")
        folder = self.source("<p>ok</p>")
        bound(clean_check(), folder)
        record_snapshot(folder, self.png)
        args = ["--source", folder, "--png", self.png, "--formato=4:5", "--out", out]
        self.assertEqual(self.main_quiet(args), 0)  # no --check-json: the saved report decides
        self.assertEqual(self.main_quiet(args[:4] + ["--check-json", self.check_file(clean_check(), folder)]), 0)
        self.assertEqual(self.main_quiet(args[:4] + ["--formato=1:1"]), 1)  # 1080x1350 is not 1:1
        write_png(self.png, 10, 10)
        self.assertEqual(self.main_quiet(args), 1)
        with open(out, encoding="utf-8") as f:
            self.assertFalse(json.load(f)["ok"])

    def test_newest_saved_report_decides_without_check_json(self):
        folder = self.source("<p>ok</p>")
        self.assertFalse(qa_imagem.check_strict_json(None, folder)["ok"])  # check never ran
        bound(clean_check(), folder)
        self.assertTrue(qa_imagem.check_strict_json(None, folder)["ok"])
        newer = os.path.join(folder, ".hyperframes", "artifacts", "checks", "z-newer.json")
        with open(newer, "w", encoding="utf-8") as f:
            json.dump(OVERFLOW_CHECK, f)
        os.utime(newer, (time.time() + 5, time.time() + 5))
        self.assertFalse(qa_imagem.check_strict_json(None, folder)["ok"])

    def test_achados_lists_only_the_findings_of_the_saved_report(self):
        folder = self.source("<p>ok</p>")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(qa_imagem.main(["--achados", folder]), 1)  # check never ran: said, not hidden
        self.assertIn("no check report", buf.getvalue())
        bound(clean_check(), folder)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(qa_imagem.main(["--achados", folder]), 0)
        self.assertEqual(buf.getvalue().strip(), "nenhum achado acima de info")
        newer = os.path.join(folder, ".hyperframes", "artifacts", "checks", "z-newer.json")
        with open(newer, "w", encoding="utf-8") as f:
            json.dump(OVERFLOW_CHECK, f)
        os.utime(newer, (time.time() + 5, time.time() + 5))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(qa_imagem.main(["--achados", folder]), 1)
        self.assertIn("error", buf.getvalue())
        self.assertLess(len(buf.getvalue().splitlines()), 21)  # short: never the whole JSON

    def test_format_size_comes_from_formatos_json(self):
        self.assertEqual(qa_imagem.format_size("post 4:5"), (1080, 1350))
        self.assertEqual(qa_imagem.format_size("carrossel 1:1"), (1080, 1080))
        self.assertEqual(qa_imagem.format_size("4x5"), (1080, 1350))
        with self.assertRaises(ValueError):
            qa_imagem.format_size("9:16")

    def test_snapshot_record_guards(self):
        folder = self.source("<p>ok</p>")
        self.assertFalse(qa_imagem.check_snapshot(self.png, folder)["ok"])  # nothing recorded
        record_snapshot(folder, self.png)
        self.assertTrue(qa_imagem.check_snapshot(self.png, folder)["ok"])
        other = os.path.join(self.tmp, "other.png")
        write_png(other, 1080, 1350)
        self.assertFalse(qa_imagem.check_snapshot(other, folder)["ok"])  # a PNG HyperFrames did not take
        record_snapshot(folder, self.png, created=1000)  # the source was edited after the snapshot
        self.assertFalse(qa_imagem.check_snapshot(self.png, folder)["ok"])
        # Shape seen in the snapshot source: a brand font that does not load is a warning.
        record_snapshot(folder, self.png, ["Fonts failed: Brand Heading (400 normal)"])
        result = qa_imagem.check_snapshot(self.png, folder)
        self.assertFalse(result["ok"])
        self.assertIn("Fonts failed", result["details"][0])

    def frame(self, work, n, size=(1080, 1350), warnings=(), html=None):
        source = os.path.join(work, "q%d" % n, "fonte")
        os.makedirs(source)
        with open(os.path.join(source, "index.html"), "w", encoding="utf-8") as f:
            f.write(html or "<p>quadro %d</p>" % n)
        png = os.path.join(work, "q%d" % n, "snap", qa_imagem.STILL)
        os.makedirs(os.path.dirname(png))
        write_png(png, *size, cheio=True)
        bound(clean_check(), source)
        record_snapshot(source, png, warnings)
        return png

    def test_final_carousel_needs_every_frame_green_at_the_format_size(self):
        work = os.path.join(self.tmp, "trabalho")
        self.assertIn("nenhum quadro", qa_imagem.run_final(work, 1080, 1350)["linha"])
        self.frame(work, 1)
        middle = self.frame(work, 2, size=(1080, 1080))  # a 1:1 frame in a 4:5 carousel
        self.frame(work, 3, warnings=["Fonts failed: Brand Body (400 normal)"])
        rep = qa_imagem.run_final(work, *qa_imagem.format_size("carrossel 4:5"))
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["linha"], "PRECISA DO SEU OLHO: 1 de 3 verdes, q2: png_size; q3: snapshot")
        write_png(middle, 1080, 1350)
        record_snapshot(os.path.join(work, "q3", "fonte"), os.path.join(work, "q3", "snap", qa_imagem.STILL))
        rep = qa_imagem.run_final(work, 1080, 1350)
        self.assertTrue(rep["ok"], rep["linha"])
        self.assertEqual(rep["linha"], "PRONTO: 3 de 3 quadros verdes")
        out = os.path.join(self.tmp, "final.json")
        self.assertEqual(self.main_quiet(["--final", work, "--formato=4:5", "--out", out]), 0)
        self.assertEqual(self.main_quiet(["--final", work, "--formato=1:1", "--out", out]), 1)
        with open(out, encoding="utf-8") as f:
            self.assertTrue(json.load(f)["linha"].startswith("PRECISA DO SEU OLHO: 0 de 3"))


    def test_atencao_is_opt_in(self):
        folder = self.source("<p>quadro 1</p>")
        check = self.check_file(clean_check(), folder)
        self.assertEqual(self.failed(qa_imagem.run(folder, self.png, check, 1080, 1350)), [])
        self.assertIn("titulo", self.failed(qa_imagem.run(folder, self.png, check, 1080, 1350, atencao=True)))

    def test_final_atencao_adds_the_piece_outside_k_of_n(self):
        work = projeto(self.tmp)
        self.frame(work, 1, html=post_html())
        self.frame(work, 2, html=post_html(h1="Reserve o&nbsp;seu", layout="l-cheia", corpo='<p id="cta">Peça já</p>'))
        self.assertEqual(qa_imagem.run_final(work, 1080, 1350)["linha"], "PRONTO: 2 de 2 quadros verdes")
        rep = qa_imagem.run_final(work, 1080, 1350, atencao=True)  # no copy.md
        self.assertFalse(rep["ok"])
        self.assertEqual(rep["linha"], "PRECISA DO SEU OLHO: 2 de 2 verdes, peca: legenda")
        self.assertEqual([f["frame"] for f in rep["frames"]], ["q1", "q2", "peca"])
        escrever(os.path.join(work, "copy.md"), COPY)
        out = os.path.join(self.tmp, "final.json")
        self.assertEqual(self.main_quiet(["--final", work, "--formato=4:5", "--atencao", "--out", out]), 0)
        with open(out, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["linha"], "PRONTO: 2 de 2 quadros verdes")

    def test_pares_prints_and_exits(self):
        work = projeto(self.tmp)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(qa_imagem.main(["--pares", work]), 0)
        self.assertIn("texto cores.text #3B2417 sobre cores.bg #FFF8EC: ", buf.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(qa_imagem.main(["--pares", os.path.join(self.tmp, "fora")]), 2)


if __name__ == "__main__":
    unittest.main()
