"""Estúdio no Windows com a distro pronta (WSL): abas, Preparar e selo do vídeo. Tudo com sonda, runner e Popen falsos."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(STUDIO), "painel"))
import wsl  # noqa: E402

PLUGIN = "/home/tuneup/.claude/plugins/cache/tune-up/tune-up/2.26.0"
MARCA = {"versao": 1, "plugin": "2.26.0", "usuario": "tuneup", "plugin_dir": PLUGIN}
PRONTA = {"pronta": True, "motivo": "pronta", "marcador": MARCA}


def carregar(nome):
    caminho = os.path.join(STUDIO, "painel", "modulos", "estudio", nome)
    sys.path.insert(0, os.path.dirname(caminho))
    try:
        spec = importlib.util.spec_from_file_location("estudio_wsl_teste_" + nome[:-3], caminho)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(os.path.dirname(caminho))
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mod = carregar("modulo.py")
        p = mock.patch.object(self.mod, "_windows", return_value=True)
        p.start()
        self.addCleanup(p.stop)
        self.chamadas = []

    def rodar(self, cmd, tempo, env=None):
        self.chamadas.append((cmd, tempo))
        return self.saida

    def ctx(self, sonda=PRONTA):
        return {"dados": os.path.join(self.tmp, "dados"), "raiz": "C:\\proj", "sonda": lambda: sonda,
                "wsl": wsl, "wsl_rodar": self.rodar}


class TestPreparar(Base):
    def ctx(self, sonda=PRONTA):
        c = super().ctx(sonda)
        c["dados_dir"] = "C:\\Users\\v\\dados"
        return c

    def agir(self, ctx):
        with mock.patch.object(self.mod.subprocess, "Popen") as popen, \
                mock.patch.object(self.mod.os, "makedirs"), mock.patch("builtins.open", mock.mock_open()):
            r = self.mod.agir(ctx, "preparar", {"confirmar": True})
        return r, popen

    def test_popen_uma_vez_com_o_argv_exato(self):
        r, popen = self.agir(self.ctx())
        self.assertTrue(r["feito"])
        popen.assert_called_once()
        cmd, kw = popen.call_args[0][0], popen.call_args[1]
        self.assertEqual(cmd, wsl.argv("/mnt/c/Users/v/dados", [
            "/usr/bin/python3", "-I", PLUGIN + "/tune-up-studio/scripts/preparar_estudio.py",
            "--dados", "/mnt/c/Users/v/dados", "--projeto", "/mnt/c/proj", "--sim"]))
        i = cmd.index("--exec")
        self.assertEqual(cmd[i + 1:i + 4], [wsl.PORTAO, "/usr/bin/python3", "-I"])
        self.assertNotIn("--", cmd)
        self.assertNotIn("pass_fds", kw)
        self.assertNotIn("shell", kw)
        self.assertIs(kw["stdin"], self.mod.subprocess.DEVNULL)

    def test_plugin_dir_invalido_recusa_sem_popen(self):
        for ruim in ("/etc/passwd", PLUGIN + "/../x", None):
            sonda = dict(PRONTA, marcador=dict(MARCA, plugin_dir=ruim))
            r, popen = self.agir(self.ctx(sonda))
            self.assertFalse(r["feito"])
            popen.assert_not_called()

    def test_sem_confirmar_e_sem_sonda_pronta_recusam(self):
        with mock.patch.object(self.mod.subprocess, "Popen") as popen:
            r = self.mod.agir(self.ctx(), "preparar", {})
            self.assertFalse(r["feito"])
            r = self.mod.agir(self.ctx({"pronta": False, "motivo": "falta a marca."}), "preparar", {"confirmar": True})
        popen.assert_not_called()
        self.assertIn("instalar.ps1", r["mensagem"])
        self.assertIn("falta a marca", r["mensagem"])


class TestMontar(Base):
    def test_pronta_mostra_as_abas_normais(self):
        self.saida = (0, "", "")
        r = self.mod.montar(self.ctx())
        abas = {a["id"]: a["blocos"] for a in r["abas"]}
        self.assertTrue([b for b in abas["ambiente"] if b.get("acao") == "preparar"])
        self.assertFalse(any("instalar.ps1" in str(b) for b in r["abas"]))
        self.assertFalse(any("instalar.ps1" in a["texto"] for a in r["alertas"]))

    def test_pronto_vem_do_hf_pronto_da_distro(self):
        self.saida = (0, "", "")
        with mock.patch.object(wsl, "hf_pronto", return_value=True) as hf:
            r = self.mod.montar(self.ctx())
        hf.assert_called_once()
        self.assertEqual(hf.call_args[0][0], self.rodar)
        self.assertTrue(any("ir_para" in b for a in r["abas"] if a["id"] == "ambiente" for b in a["blocos"]))

    def textos(self, pronto, amb):
        os.makedirs(os.path.join(self.tmp, "dados"), exist_ok=True)
        with open(os.path.join(self.tmp, "dados", "ambiente.json"), "w", encoding="utf-8") as f:
            json.dump(amb, f)
        with mock.patch.object(wsl, "hf_pronto", return_value=pronto):
            r = self.mod.montar(self.ctx())
        aba = next(a for a in r["abas"] if a["id"] == "ambiente")["blocos"][0]
        return aba, [a["texto"] for a in r["alertas"]]

    def test_texto_de_pronto_vem_do_hf_pronto_nao_do_ambiente_json(self):
        """ambiente.json (Windows side) says the opposite of the distro: the tab and the top follow hf_pronto."""
        for amb in ({"pronto": False, "erro": "ffmpeg falhou"}, {}):
            with self.subTest(amb=amb):
                aba, alertas = self.textos(True, amb)
                self.assertIn("pronto (no WSL)", aba["texto"])
                self.assertIn("ir_para", aba)
                self.assertFalse([t for t in alertas + [aba["texto"]] if "não está pronto" in t or "Preparar" in t])
        for amb in ({"pronto": True, "chave": "x"}, {"pronto": True}, {}):
            with self.subTest(amb=amb):
                aba, alertas = self.textos(False, amb)
                self.assertIn("Clique em Preparar", aba["texto"])
                self.assertNotIn("ir_para", aba)
                self.assertFalse([t for t in alertas + [aba["texto"]] if "pronto." in t or "pronto (no WSL)" in t])
                self.assertEqual(alertas, [aba["texto"]])

    def test_preparando_mostra_o_andamento(self):
        aba, alertas = self.textos(False, {"estado": "preparando"})
        self.assertIn("Preparando o estúdio", aba["texto"])
        self.assertEqual(alertas, [aba["texto"]])

    def test_nao_pronta_recusa_com_o_motivo(self):
        r = self.mod.montar(self.ctx({"pronta": False, "motivo": "conferindo o WSL..."}))
        self.assertTrue(any("instalar.ps1" in a["texto"] and "conferindo" in a["texto"] for a in r["alertas"]))
        self.assertFalse(self.chamadas)


class TestSelo(Base):
    def setUp(self):
        super().setUp()
        self.selo = carregar("selo.py")
        self.pasta = os.path.join(self.tmp, "peca")
        os.makedirs(os.path.join(self.pasta, "fonte"))
        with open(os.path.join(self.pasta, "fonte", "index.html"), "w") as f:
            f.write("<html><body>oi</body></html>")
        with open(os.path.join(self.pasta, "video.mp4"), "wb") as f:  # ftyp, moov, mdat (faststart)
            for k in (b"ftyp", b"moov", b"mdat"):
                f.write((8).to_bytes(4, "big") + k)
        with open(os.path.join(self.pasta, "qa.json"), "w") as f:
            json.dump({"ok": True, "linha": "PRONTO: tudo"}, f)
        os.utime(os.path.join(self.pasta, "fonte", "index.html"), (1, 1))
        qi, _ = self.selo._scripts()
        self.params = {"duracao": 10}
        self.dado = {"streams": [{"codec_type": "video", "width": 1080, "height": 1920, "r_frame_rate": "30/1",
                                  "nb_read_frames": "300", "codec_name": "h264", "pix_fmt": "yuv420p"}],
                     "format": {"duration": "10.0"}}
        self.pasta_w = "C:\\x\\peca"
        self.run = mock.Mock()

    def selar(self, saida):
        self.run.return_value = saida
        fake = lambda video, pasta, tempo: self.run(video, pasta, tempo)  # noqa: E731
        self.selo.esquecer()
        return self.selo.calcular(self.pasta, "estudio.video-motion", self.params, fake)

    def test_ffprobe_do_wsl_com_20s_e_selo_verde(self):
        s = self.selar((0, json.dumps(self.dado), ""))
        self.run.assert_called_once_with(os.path.join(self.pasta, "video.mp4"), self.pasta, 20)
        self.assertTrue(s["ok"], s["linha"])

    def test_gate_97_vira_cheque_vermelho_com_motivo(self):
        s = self.selar((97, "", "recusado"))
        self.assertFalse(s["ok"])
        self.assertIn("ffprobe", s["falhas"])

    def test_timeout_e_json_ruim_ficam_vermelhos(self):
        for saida in ((124, "", ""), (0, "nao e json", ""), (0, "[]", "")):
            s = self.selar(saida)
            self.assertIn("ffprobe", s["falhas"], saida)

    def test_argv_do_ffprobe_no_modulo(self):
        self.saida = (0, "{}", "")
        f = self.mod._ffprobe_wsl(self.ctx())
        f("C:\\x\\peca\\video.mp4", "C:\\x\\peca", 20)
        cmd, tempo = self.chamadas[0]
        self.assertEqual(tempo, 20)
        self.assertEqual(cmd, wsl.argv("/mnt/c/x/peca", ["/usr/local/bin/ffprobe", "-v", "error", "-print_format",
                                                         "json", "-count_frames", "-show_streams", "-show_format",
                                                         "/mnt/c/x/peca/video.mp4"]))
        self.assertNotIn("--", cmd)

    def test_skills_aceitam_o_caminho_do_wsl(self):
        for n in ("post", "video", "anuncio"):
            with open(os.path.join(STUDIO, "skills", n, "SKILL.md"), encoding="utf-8") as f:
                self.assertIn(".local/share/tune-up/estudio-node", f.read())


if __name__ == "__main__":
    unittest.main()
