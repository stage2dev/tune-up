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
# FFmpeg 8.0.1 on Windows: three flag columns, a ..C legend line and no ------ separator
FILTERS_801 = """Filters:
  T.. = Timeline support
  .S. = Slice threading
  ..C = Command support
  A = Audio input/output
  V = Video input/output
  N = Dynamic number and/or type of input/output
  | = Source or sink filter
 ... blackdetect       V->V       Detect video intervals that are (almost) black.
 ..C crop              V->V       Crop the input video.
 ... format            V->V       Convert the input video to one of the specified pixel formats.
 ... freezedetect      V->V       Detects frozen video input.
 TSC scale             V->V       Scale the input video size and/or convert the image format.
 ... setpts            V->V       Set PTS for the output video frame.
 ... setsar            V->V       Set the pixel sample aspect ratio.
 ... trim              V->V       Pick one continuous section from the input, drop the rest.
 .S. xfade             VV->V      Cross fade one video with another video.
 ... zoompan           V->V       Apply Zoom & Pan effect.
 ... color             |->V       Provide an uniformly colored input.
 ... amix              N->A       Audio mixing.
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

    def test_ffmpeg_801_without_separator(self):
        self.assertEqual(va.nomes_de_filtros(FILTERS_801), set(va.FILTROS) | {"color", "amix"})
        self.assertEqual(levels(va.ffmpeg(fake_which({"ffmpeg", "ffprobe"}), fake_run(filters=FILTERS_801))),
                         [va.OK] * 3)

    def test_old_format_names_exactly_the_filters(self):
        self.assertEqual(va.nomes_de_filtros(FILTERS_OUT), set(va.FILTROS))


class Wsl(unittest.TestCase):
    WSL1 = "4.4.0-19041-Microsoft"
    WSL2 = "6.6.87.2-microsoft-standard-WSL2"

    def test_wsl1_is_refused(self):
        itens = va.sistema("linux", self.WSL1)
        self.assertEqual(levels(itens), [va.ERRO])
        self.assertIn("WSL1", itens[0][1])
        self.assertIn("[falta]", va.relatorio(itens))

    def test_wsl2_and_plain_linux_are_ok(self):
        self.assertEqual(levels(va.sistema("linux", self.WSL2)), [va.OK])
        self.assertIn("WSL2", va.sistema("linux", self.WSL2)[0][1])
        self.assertEqual(levels(va.sistema("linux", "6.8.0-45-generic")), [va.OK])
        self.assertEqual(va.wsl("linux", self.WSL1), 1)
        self.assertEqual(va.wsl("linux", self.WSL2), 2)
        self.assertIsNone(va.wsl("linux", "6.8.0-45-generic"))
        self.assertIsNone(va.wsl("darwin", self.WSL2))

    def test_kernel_string_heuristics(self):
        for texto in ("4.19.104-microsoft-standard", "5.10.16.3-Microsoft-Standard-WSL2", "5.15.0-microsoft-WSL2-foo"):
            self.assertEqual(va.wsl("linux", texto), 2, texto)
        self.assertEqual(va.wsl("linux", "4.4.0-19041-Microsoft"), 1)

    def test_node_dir_option(self):
        vistos = []
        orig = va.verificar
        va.verificar = lambda projeto=None, node_dir=va.NODE_DIR, selo=False: vistos.append((node_dir, selo)) or []
        try:
            self.assertEqual(va.main(["--node-dir", "/abs/node"]), 0)
            self.assertEqual(vistos, [("/abs/node", True)])
            for ruim in ("rel/node", "/a/../b", "/a/..", ".."):
                self.assertEqual(va.main(["--node-dir", ruim]), 2, ruim)
            self.assertEqual(va.main([]), 0)
            self.assertEqual(vistos[-1], (va.NODE_DIR, False))
        finally:
            va.verificar = orig

    def test_unreadable_osrelease_is_plain_linux(self):
        def falha():
            raise OSError("sem /proc")
        self.assertEqual(va.osrelease(falha), "")
        self.assertEqual(va.osrelease(lambda: self.WSL2), self.WSL2)
        self.assertEqual(levels(va.sistema("linux", "")), [va.OK])

    def test_darwin_and_windows_unchanged(self):
        self.assertEqual(va.sistema("darwin", self.WSL1), [(va.OK, "sistema: macOS")])
        self.assertEqual(levels(va.sistema("win32", self.WSL2)), [va.ERRO])


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

    def test_hyperframes_signature_stamp_only_when_asked(self):
        self.write("node/package.json", {"dependencies": {"hyperframes": "0.9.6"}})
        self.write("node/node_modules/hyperframes/package.json", {"version": "0.9.6"})
        node_dir = os.path.join(self.d, "node")
        self.assertEqual(levels(va.hyperframes(node_dir)), [va.OK])  # panel flow: no stamp needed
        res = va.hyperframes(node_dir, selo=True)
        self.assertEqual(res, [(va.ERRO, "hyperframes: instalação sem conferência de assinatura; "
                                         "rode o instalador de novo")])
        self.write("node/" + va.SELO, "abc\n")
        self.assertEqual(levels(va.hyperframes(node_dir, selo=True)), [va.OK])

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
