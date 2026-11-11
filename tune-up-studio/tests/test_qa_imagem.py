"""Unit tests for scripts/qa_imagem.py. No Chrome, no network."""
import json
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))

import qa_imagem  # noqa: E402

FIXTURES = os.path.join(HERE, "fixtures")
POST_SOURCE = os.path.join(STUDIO, "exemplos", "forno-miudo", "post-4x5", "fonte")


def write_png(path, width, height):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = (b"\0" + b"\xff" * (3 * width)) * height
    with open(path, "wb") as f:
        f.write(qa_imagem.PNG_SIGNATURE + chunk(b"IHDR", ihdr)
                + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b""))


def bound(data, source):
    """The check JSON names its saved report under the source it ran on."""
    report = os.path.join(os.path.realpath(source), ".hyperframes", "artifacts", "checks", "t.json")
    return dict(data, saved={"report": report})


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
        os.utime(path, (1, 1))  # the source was edited after the check
        self.assertFalse(qa_imagem.check_strict_json(path, folder)["ok"])
        path = self.check_file(clean_check(layout={"ok": True, "findings": [], "duration": 5}), folder)
        self.assertTrue(qa_imagem.check_strict_json(path, folder, duration=5.0)["ok"])
        self.assertFalse(qa_imagem.check_strict_json(path, folder, duration=10.0)["ok"])

    def test_main_exit_codes_and_out_file(self):
        out = os.path.join(self.tmp, "qa.json")
        args = ["--source", POST_SOURCE, "--png", self.png,
                "--check-json", self.check_file(clean_check(), POST_SOURCE), "--out", out]
        with open(os.devnull, "w") as devnull:
            stdout, sys.stdout = sys.stdout, devnull
            try:
                self.assertEqual(qa_imagem.main(args), 0)
                write_png(self.png, 10, 10)
                self.assertEqual(qa_imagem.main(args), 1)
            finally:
                sys.stdout = stdout
        with open(out, encoding="utf-8") as f:
            self.assertFalse(json.load(f)["ok"])


if __name__ == "__main__":
    unittest.main()
