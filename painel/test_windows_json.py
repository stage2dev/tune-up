"""Windows: JSON com BOM (PowerShell 5.1), soma sem cache, os.replace com arquivo ocupado e cwd sem caixa.
Roda em todo SO: o ramo do Windows é ligado por parâmetro ou trocando os.name só durante a chamada."""
import sys

sys.dont_write_bytecode = True

import collections  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import catalogo  # noqa: E402
import config  # noqa: E402
import extensoes  # noqa: E402
import habilidades  # noqa: E402
import leitor  # noqa: E402
import modelos  # noqa: E402
import registro  # noqa: E402

BOM = "\ufeff"
ACAO = {"id": "teste.bom", "grupo": "teste", "risco": "leitura", "prompt": "oi"}


def escrever(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)


class TesteJsonComBom(Base):
    def test_painel_json_com_bom_e_lido(self):
        escrever(os.path.join(self.tmp, ".tune-up", "painel.json"), BOM + json.dumps({"nome": "Loja BOM"}))
        cfg = config.carregar(self.tmp, home=self.tmp)
        self.assertFalse([a for a in cfg.get("avisos", []) if "ilegível" in a], cfg.get("avisos"))
        self.assertIn("Loja BOM", json.dumps(cfg, ensure_ascii=False))

    def test_habilidades_json_com_bom_e_lido(self):
        arq = os.path.join(self.tmp, "habilidades.json")
        escrever(arq, BOM + json.dumps({"enabledPlugins": {"a@b": True}}))
        avisos = []
        self.assertEqual(habilidades._ler_json(arq, avisos, "x"), {"enabledPlugins": {"a@b": True}})
        self.assertEqual(avisos, [])

    def test_acoes_json_com_bom_e_lido(self):
        pasta = os.path.join(self.tmp, "acoes")
        escrever(os.path.join(pasta, "teste.json"), BOM + json.dumps({"acoes": [ACAO]}))
        acoes, avisos = catalogo.carregar_catalogo(pasta)
        self.assertEqual([a["id"] for a in acoes], ["teste.bom"], avisos)

    def test_extensoes_json_com_bom_e_lido(self):
        escrever(os.path.join(self.tmp, extensoes.ARQUIVO), BOM + json.dumps({"a@b": {"versao": "1"}}))
        self.assertEqual(extensoes._ler({"dados_dir": self.tmp}), {"a@b": {"versao": "1"}})


Stat = collections.namedtuple("Stat", "st_mode st_size st_mtime_ns st_ctime_ns st_ino")


class TesteSomaNoWindows(Base):
    """No NTFS st_ctime é a criação: trocar o conteúdo e voltar o mtime não muda a assinatura."""

    def setUp(self):
        super().setUp()
        self.inst = os.path.join(self.tmp, "plugin")
        self.qa = os.path.join(self.inst, "qa.py")
        escrever(self.qa, "print(1)\n")
        real = os.lstat
        # assinatura como no Windows: ctime e inode fixos; tamanho e mtime reais
        self.lstat = lambda c: (lambda st: Stat(st.st_mode, st.st_size, st.st_mtime_ns, 0, 0))(real(c))

    def trocar(self, nt):
        k = {} if nt is None else {"nt": nt}
        with mock.patch.object(extensoes.os, "lstat", self.lstat):
            antes = extensoes.soma(self.inst, **k)
            st = os.stat(self.qa)
            escrever(self.qa, "print(2)\n")
            os.utime(self.qa, ns=(st.st_atime_ns, st.st_mtime_ns))
            return antes, extensoes.soma(self.inst, **k)

    def test_nt_conteudo_trocado_com_mesmo_tamanho_e_mtime_muda_a_soma(self):
        with mock.patch.object(extensoes.os, "name", "nt"):
            antes, depois = self.trocar(nt=None)
        self.assertNotEqual(depois, antes)

    def test_nt_por_parametro(self):
        antes, depois = self.trocar(nt=True)
        self.assertNotEqual(depois, antes)

    def test_posix_continua_com_cache(self):
        antes, depois = self.trocar(nt=False)
        self.assertEqual(depois, antes)  # no POSIX o ctime real muda; aqui ele foi fixado de propósito


class TesteReplaceOcupado(Base):
    """No Windows os.replace dá PermissionError enquanto outro processo lê o destino."""

    def ocupado_uma_vez(self):
        real, vezes = os.replace, []

        def falso(a, b):
            if not vezes:
                vezes.append(1)
                raise PermissionError(13, "ocupado")
            return real(a, b)
        return falso

    def test_extensoes_gravar_insiste(self):
        with mock.patch.object(registro, "PRAZO_OCUPADO", 2), \
                mock.patch.object(extensoes.os, "replace", self.ocupado_uma_vez()):
            extensoes._gravar({"dados_dir": self.tmp}, {"a@b": {"versao": "1"}})
        self.assertEqual(extensoes._ler({"dados_dir": self.tmp}), {"a@b": {"versao": "1"}})

    def test_modelos_gravar_insiste(self):
        m = modelos.Modelos({"dados_dir": self.tmp}, rodar=None, relogio=lambda: 5)
        with mock.patch.object(registro, "PRAZO_OCUPADO", 2), \
                mock.patch.object(modelos.os, "replace", self.ocupado_uma_vez()):
            m._gravar("opus", True)
        self.assertEqual(m._ler(), {"opus": {"tem": True, "em": 5}})


class TesteCwdDaRaiz(unittest.TestCase):
    def test_nt_letra_do_disco_e_caixa_diferentes(self):
        raiz = "C:\\Users\\Ana\\Loja"
        self.assertTrue(leitor.da_raiz("c:\\users\\ana\\loja", raiz, nt=True))
        self.assertTrue(leitor.da_raiz("c:\\Users\\Ana\\Loja\\sub", raiz, nt=True))
        self.assertTrue(leitor.da_raiz("C:/Users/Ana/Loja/sub", raiz, nt=True))
        self.assertFalse(leitor.da_raiz("C:\\Users\\Ana\\Loja2", raiz, nt=True))
        self.assertFalse(leitor.da_raiz("D:\\Users\\Ana\\Loja", raiz, nt=True))

    def test_posix_igual_ao_de_antes(self):
        self.assertTrue(leitor.da_raiz("/a/b", "/a/b", nt=False))
        self.assertTrue(leitor.da_raiz("/a/b/c", "/a/b", nt=False))
        self.assertFalse(leitor.da_raiz("/a/bc", "/a/b", nt=False))
        self.assertFalse(leitor.da_raiz("/A/b", "/a/b", nt=False))


if __name__ == "__main__":
    unittest.main()
