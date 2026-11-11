"""Unit tests for scripts/verificar_ambiente.py. No Chrome, no network, no real ffmpeg needed."""
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))

import qa_video  # noqa: E402
import reserva_slides  # noqa: E402
import verificar_ambiente as va  # noqa: E402

FILTERS_OUT = """Filters:
  T.. = Timeline support
  ------
 .S blackdetect       V->V       Detect video intervals that are (almost) black.
 .. crop              V->V       Crop the input video.
 .. format            V->V       Convert the input video.
 .. freezedetect      V->V       Detects frozen video input.
 .. scale             V->V       Scale the input video.
 .. setpts            V->V       Set PTS.
 .. setsar            V->V       Set the pixel sample aspect ratio.
 .. trim              V->V       Pick one continuous section.
 .S xfade             VV->V      Cross fade.
 .. zoompan           V->V       Apply Zoom & Pan effect.
"""
ENCODERS_OUT = " V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC\n"


def levels(items):
    return [n for n, _ in items]


def fake_which(present):
    return lambda name: ("/bin/" + name) if name in present else None


def fake_run(filters=FILTERS_OUT, encoders=ENCODERS_OUT, node="v22.1.0\n"):
    def run(cmd, timeout=20):
        if cmd[-1] == "-filters":
            return 0, filters
        if cmd[-1] == "-encoders":
            return 0, encoders
        return 0, node
    return run


class FiltersInSync(unittest.TestCase):
    def test_every_filter_the_scripts_use_is_checked(self):
        graph = reserva_slides.build_graph(3, 1080, 1920, 30, 10.0, 0.5, 0.06)
        used = set(re.findall(r"\]([a-z_]+)=|,([a-z_]+)=", graph))
        used = {a or b for a, b in used}
        used |= {qa_video.BLACK_FILTER.split("=")[0], qa_video.FREEZE_FILTER.split("=")[0]}
        self.assertEqual(used, set(va.FILTROS))


class Ffmpeg(unittest.TestCase):
    def test_all_present(self):
        self.assertEqual(levels(va.ffmpeg(fake_which({"ffmpeg", "ffprobe"}), fake_run())), [va.OK] * 3)

    def test_missing_ffmpeg_says_what_is_missing(self):
        items = va.ffmpeg(fake_which(set()), fake_run())
        self.assertEqual(levels(items), [va.ERRO])
        self.assertIn("ffmpeg: não encontrado", items[0][1])

    def test_missing_filter_and_encoder_are_named(self):
        filters = FILTERS_OUT.replace(" .. zoompan ", " .. zoomxxx ")
        items = va.ffmpeg(fake_which({"ffmpeg"}), fake_run(filters=filters, encoders=""))
        self.assertEqual(levels(items), [va.ERRO, va.ERRO, va.ERRO])
        self.assertIn("zoompan", items[1][1])
        self.assertIn("libx264", items[2][1])

    def test_header_lines_are_not_filters(self):
        self.assertNotIn("=", va.nomes_de_filtros(FILTERS_OUT))
        self.assertIn("xfade", va.nomes_de_filtros(FILTERS_OUT))


class SystemAndNode(unittest.TestCase):
    def test_windows_is_refused(self):
        self.assertEqual(levels(va.sistema("win32")), [va.ERRO])
        self.assertEqual(levels(va.sistema("linux")), [va.OK])

    def test_linux_needs_bwrap_and_socat(self):
        items = va.sandbox_linux("linux", fake_which({"socat"}))
        self.assertEqual(levels(items), [va.ERRO, va.OK])
        self.assertEqual(va.sandbox_linux("darwin", fake_which(set())), [])

    def test_old_node_fails(self):
        self.assertEqual(levels(va.node(fake_which({"node"}), fake_run(node="v20.9.0\n"))), [va.ERRO])
        self.assertEqual(levels(va.node(fake_which({"node"}), fake_run())), [va.OK])
        self.assertEqual(levels(va.node(fake_which(set()), fake_run())), [va.ERRO])


class Files(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.saved, va.GERENCIADOS = va.GERENCIADOS, ()

    def tearDown(self):
        va.GERENCIADOS = self.saved
        self.tmp.cleanup()

    def write(self, rel, data):
        path = os.path.join(self.d, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        return path

    def test_hyperframes_install(self):
        self.write("node/package.json", {"dependencies": {"hyperframes": "0.9.6"}})
        node_dir = os.path.join(self.d, "node")
        self.assertEqual(levels(va.hyperframes(node_dir)), [va.ERRO])
        self.write("node/node_modules/hyperframes/package.json", {"version": "0.9.5"})
        self.assertEqual(levels(va.hyperframes(node_dir)), [va.ERRO])
        self.write("node/node_modules/hyperframes/package.json", {"version": "0.9.6"})
        self.assertEqual(levels(va.hyperframes(node_dir)), [va.OK])

    def test_chrome_cache(self):
        env = {"HYPERFRAMES_CACHE_DIR": os.path.join(self.d, "hf")}
        self.assertEqual(levels(va.chrome(env)), [va.ERRO])
        self.assertIn("hyperframes browser ensure", va.chrome(env)[0][1])  # o Preparar não baixa o Chrome
        old = self.write("hf/chrome/chrome-headless-shell/mac_arm-1.0.0.0/x/chrome-headless-shell", "")
        items = va.chrome(env)
        self.assertEqual(levels(items), [va.ERRO])
        self.assertIn("mac_arm-1.0.0.0", items[0][1])
        exe = self.write("hf/chrome/chrome-headless-shell/linux-%s/chrome-headless-shell-linux64/"
                         "chrome-headless-shell" % va.CHROME_VERSION, "")
        os.chmod(exe, 0o755)
        self.assertEqual(levels(va.chrome(env)), [va.OK])
        self.assertEqual(levels(va.chrome({"HYPERFRAMES_BROWSER_PATH": old})), [va.AVISO])
        self.assertEqual(levels(va.chrome({"HYPERFRAMES_BROWSER_PATH": old + "-no"})), [va.ERRO])

    def test_user_sandbox_keys(self):
        home, proj = os.path.join(self.d, "home"), os.path.join(self.d, "proj")
        os.makedirs(home)
        self.assertEqual(levels(va.sandbox_do_usuario(proj, home)), [va.OK])
        self.write("home/.claude/settings.json", {"sandbox": {"excludedCommands": ["docker"],
                                                              "filesystem": {"allowWrite": ["~/x"]}}})
        self.write("proj/.claude/settings.local.json", {"sandbox": {"network": {"allowedDomains": ["a.example"]}}})
        self.write("proj/.claude/settings.json", "{not json")
        items = va.sandbox_do_usuario(proj, home)
        self.assertEqual(levels(items), [va.ERRO, va.AVISO, va.AVISO, va.ERRO])
        self.assertIn("docker", items[0][1])
        self.assertIn("a.example", items[3][1])

    def test_report_and_exit_code(self):
        text = va.relatorio([(va.OK, "a"), (va.ERRO, "b")])
        self.assertIn("[falta] b", text)
        self.assertIn("Não está pronto: 1", text)
        self.assertIn("Pronto para o estúdio.", va.relatorio([(va.AVISO, "c")]))


if __name__ == "__main__":
    unittest.main()
