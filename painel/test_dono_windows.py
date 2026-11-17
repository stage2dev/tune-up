"""dono.py no Windows: BOM do Bloco de Notas, troca de nome com o arquivo aberto por outro e caminho aprovado
que sai da raiz (barra invertida, letra de unidade, fluxo ':' e atalho). Roda em todo sistema."""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import dono  # noqa: E402
import registro  # noqa: E402

CONTEUDO = b"marca aprovada"
SHA = hashlib.sha256(CONTEUDO).hexdigest()


class TesteDonoWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.raiz = os.path.join(self.tmp, "ws")
        self.cfg = {"dados_dir": os.path.join(self.tmp, "dados"), "raiz": self.raiz}
        os.makedirs(self.cfg["dados_dir"])
        os.makedirs(self.raiz)
        self.arq = os.path.join(self.cfg["dados_dir"], "estudio-dono.json")

    def _aprovar(self, rel, prefixo=b""):
        with open(self.arq, "wb") as f:
            f.write(prefixo + json.dumps({"marca": {"aprovado": True, "sha256": SHA, "arquivo": rel}}).encode())

    def _criar(self, *partes):
        caminho = os.path.join(*partes)
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "wb") as f:
            f.write(CONTEUDO)

    def test_json_com_bom_e_lido(self):
        self._criar(self.raiz, "marca.json")
        self._aprovar("marca.json", prefixo=b"\xef\xbb\xbf")
        self.assertEqual(dono.ler(self.cfg, "estudio")["marca"]["aprovado"], True)
        self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), [])

    def test_troca_de_nome_insiste_em_permission_error(self):
        real = os.replace
        vezes = []

        def ocupado(a, b):
            vezes.append(1)
            if len(vezes) == 1:
                raise PermissionError(13, "em uso por outro processo")
            return real(a, b)

        with mock.patch.object(registro, "PRAZO_OCUPADO", 2), mock.patch("os.replace", ocupado):
            v = dono.gravar(self.cfg, "estudio", "marca", {"aprovado": True})
        self.assertEqual((v["aprovado"], len(vezes)), (True, 2))
        self.assertIs(dono.ler(self.cfg, "estudio")["marca"]["aprovado"], True)

    def test_caminho_valido_continua_aprovado(self):
        self._criar(self.raiz, ".tune-up", "estudio", "marca.json")
        self._aprovar(".tune-up/estudio/marca.json")
        self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), [])

    def test_barra_invertida_e_unidade_nao_aprovam(self):
        # no Mac estes nomes são arquivos comuns dentro da raiz; no Windows saem dela. Fecha nos dois.
        casos = {"..\\x": (self.raiz, "..\\x"), "D:/x": (self.raiz, "D:", "x"), "C:x": (self.raiz, "C:x"),
                 "sub\\x": (self.raiz, "sub\\x")}
        for rel, partes in casos.items():
            if os.name != "nt":  # no Windows o nome nem é criável (ou cai fora da raiz): basta não aprovar
                self._criar(*partes)
            self._aprovar(rel)
            self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), ["estudio.marca"], rel)
        for rel in ("/x", "//servidor/x", "a/../x", "x\x00"):
            self.assertIsNone(dono._caminho_aprovado(self.raiz, rel), rel)

    def test_dois_pontos_no_windows_e_fluxo(self):
        self._criar(self.raiz, "marca.json")
        self.assertIsNone(dono._caminho_aprovado(self.raiz, "marca.json::$DATA", nt=True))
        self.assertIsNone(dono._caminho_aprovado(self.raiz, "marca.json:oculto", nt=True))
        self.assertIsNotNone(dono._caminho_aprovado(self.raiz, "marca.json", nt=True))

    def test_atalho_no_meio_que_sai_da_raiz_nao_aprova(self):
        fora = os.path.join(self.tmp, "fora")
        self._criar(fora, "x")
        try:
            os.symlink(fora, os.path.join(self.raiz, "sub"), target_is_directory=True)
        except (OSError, NotImplementedError) as e:
            self.skipTest("sem permissão de atalho: %s" % e)
        self._aprovar("sub/x")
        self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), ["estudio.marca"])


if __name__ == "__main__":
    unittest.main()
