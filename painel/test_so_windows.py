"""No Windows nativo (win32) a ação com `sandbox` some do catálogo e não dispara; no resto nada muda. Nada chama o claude."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import catalogo  # noqa: E402
import config  # noqa: E402
import lancador  # noqa: E402

LIVRE = {"id": "x.livre", "grupo": "x", "risco": "rascunho", "prompt": "a"}
PRESA = {"id": "x.presa", "grupo": "x", "risco": "rascunho", "prompt": "b", "sandbox": True}
LOCAL = {"id": "x.local", "grupo": "x", "risco": "rascunho", "prompt": "c", "so_com": "estudio.video_rede_local",
         "sandbox": {"rede_local": True}}


class TesteSoWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.acoes = os.path.join(self.tmp, "acoes")
        os.makedirs(self.acoes)
        with open(os.path.join(self.acoes, "x.json"), "w", encoding="utf-8") as f:
            json.dump({"acoes": [LIVRE, PRESA, LOCAL]}, f)

    def cfg(self, bruto=None):
        os.makedirs(os.path.join(self.tmp, ".tune-up"), exist_ok=True)
        with open(os.path.join(self.tmp, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump(bruto or {}, f)
        c = config.carregar(self.tmp, home=self.tmp)
        c.update(acoes_dir=self.acoes, acoes_pacote_dir=None)
        return c

    def cat(self, plataforma, bruto=None):
        acoes, avisos = catalogo.catalogo_do_projeto(self.cfg(bruto), plataforma)
        return [a["id"] for a in acoes], avisos

    def test_win32_esconde_sandbox_e_avisa(self):
        ids, avisos = self.cat("win32")
        self.assertEqual(ids, ["x.livre"])
        self.assertEqual(len([a for a in avisos if "WSL2" in a]), 1, avisos)

    def test_mac_e_linux_ficam_iguais(self):
        for plat in ("darwin", "linux"):
            with self.subTest(plat):
                ids, avisos = self.cat(plat)
                self.assertEqual(ids, ["x.livre", "x.presa"])
                self.assertFalse([a for a in avisos if "WSL2" in a], avisos)

    def test_win32_lancador_recusa(self):
        # se o filtro sumir, o teste falha aqui em vez de abrir uma sessão de verdade
        with mock.patch.object(sys, "platform", "win32"), \
                mock.patch.object(lancador.subprocess, "run", side_effect=AssertionError("chamou o claude")):
            lc = lancador.Lancador(self.cfg(), lambda: {})
            with self.assertRaises(catalogo.ErroAcao) as ctx:
                lc.iniciar("x.presa", {})
        self.assertIn("não existe", str(getattr(ctx.exception, "mensagem", ctx.exception)))

    def test_win32_so_com_ligado_com_sandbox_tambem_some(self):
        bruto = {"estudio": {"video_rede_local": True}}
        self.assertEqual(self.cat("linux", bruto)[0], ["x.livre", "x.presa", "x.local"])
        self.assertEqual(self.cat("win32", bruto)[0], ["x.livre"])


if __name__ == "__main__":
    unittest.main()
