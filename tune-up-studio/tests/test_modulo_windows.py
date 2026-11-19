"""Windows nativo: o módulo do estúdio no painel mostra uma linha (use o WSL2) e não quebra. Tudo por mock."""
import importlib.util
import os
import shutil
import tempfile
import unittest
from unittest import mock

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def carregar_modulo():
    caminho = os.path.join(STUDIO, "painel", "modulos", "estudio", "modulo.py")
    spec = importlib.util.spec_from_file_location("estudio_modulo_windows_teste", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestModuloWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dados = os.path.join(self.tmp, "dados")
        self.mod = carregar_modulo()

    def windows(self, sim):
        p = mock.patch.object(self.mod, "_windows", return_value=sim)
        p.start()
        self.addCleanup(p.stop)

    def test_preparar_no_windows_devolve_a_frase_e_nao_grava_nada(self):
        self.windows(True)
        with mock.patch.object(self.mod.subprocess, "Popen", side_effect=AssertionError("Popen no Windows")) as popen:
            r = self.mod.agir({"dados": self.dados, "raiz": self.tmp}, "preparar", {"confirmar": True})
        popen.assert_not_called()
        self.assertFalse(r["feito"])
        self.assertIn("WSL2", r["mensagem"])
        self.assertIn("instalar.ps1", r["mensagem"])
        for nome in ("ambiente.lock", "ambiente.log"):
            self.assertFalse(os.path.exists(os.path.join(self.dados, nome)))
        self.assertFalse(os.path.exists(self.dados))  # nem a pasta é criada

    def test_montar_no_windows_mostra_a_frase_sem_preparar_nem_pedir_peca(self):
        self.windows(True)
        r = self.mod.montar({"dados": self.dados})
        self.assertTrue(any(a["nivel"] == "atencao" and "WSL2" in a["texto"] and "instalar.ps1" in a["texto"]
                            for a in r["alertas"]))
        abas = {a["id"]: a["blocos"] for a in r["abas"]}
        todos = [b for blocos in abas.values() for b in blocos]
        self.assertFalse([b for b in todos if b.get("acao") == "preparar"])
        self.assertFalse([b for b in abas["novo"] if "catalogo" in b])
        for aba in ("ambiente", "novo"):
            self.assertTrue(any("WSL2" in b.get("texto", "") for b in abas[aba]))
        textos = " ".join(str(b.get("texto", "")) for b in todos) + " ".join(a["texto"] for a in r["alertas"])
        self.assertNotIn("Estúdio pronto", textos)
        self.assertNotIn("Clique em Preparar", textos)

    def test_fora_do_windows_preparar_segue_para_o_popen_com_pass_fds(self):
        self.windows(False)
        with mock.patch.object(self.mod.subprocess, "Popen") as popen:
            r = self.mod.agir({"dados": self.dados, "raiz": self.tmp}, "preparar", {"confirmar": True})
        self.assertTrue(r["feito"])
        self.assertIn("pass_fds", popen.call_args[1])


if __name__ == "__main__":
    unittest.main()
