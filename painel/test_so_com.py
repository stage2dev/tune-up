"""Campo `so_com` da ação: ela só entra no catálogo do projeto que liga a chave no painel.json. Nada chama o claude."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

import catalogo  # noqa: E402
import config  # noqa: E402
import lancador  # noqa: E402

LIVRE = {"id": "x.livre", "grupo": "x", "risco": "rascunho", "prompt": "a"}
PRESA = {"id": "x.presa", "grupo": "x", "risco": "rascunho", "prompt": "b", "so_com": "estudio.video_rede_local",
         "sandbox": {"rede_local": True}}


class TesteSoCom(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.acoes = os.path.join(self.tmp, "acoes")
        os.makedirs(self.acoes)
        with open(os.path.join(self.acoes, "x.json"), "w", encoding="utf-8") as f:
            json.dump({"acoes": [LIVRE, PRESA]}, f)

    def cfg(self, bruto):
        os.makedirs(os.path.join(self.tmp, ".tune-up"), exist_ok=True)
        with open(os.path.join(self.tmp, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump(bruto, f)
        c = config.carregar(self.tmp, home=self.tmp)
        c.update(acoes_dir=self.acoes, acoes_pacote_dir=None)
        return c

    def ids(self, bruto):
        return [a["id"] for a in catalogo.catalogo_do_projeto(self.cfg(bruto))[0]]

    def test_desligada_por_padrao(self):
        for bruto in ({}, {"estudio": {"video_rede_local": False}}, {"estudio": {"video_rede_local": "true"}},
                      {"estudio.video_rede_local": 1}, {"estudio": True}):
            with self.subTest(bruto):
                self.assertEqual(self.ids(bruto), ["x.livre"])

    def test_ligada_aninhada_ou_plana(self):
        for bruto in ({"estudio": {"video_rede_local": True}}, {"estudio.video_rede_local": True}):
            with self.subTest(bruto):
                self.assertEqual(self.ids(bruto), ["x.livre", "x.presa"])

    def test_lancador_recusa_quando_desligada(self):
        lc = lancador.Lancador(self.cfg({}), lambda: {})
        with self.assertRaises(catalogo.ErroAcao) as ctx:
            lc.iniciar("x.presa", {})
        self.assertIn("não existe", str(getattr(ctx.exception, "mensagem", ctx.exception)))

    def test_valor_invalido_recusado(self):
        for ruim in ("", "Estudio", "a..b", "a.b.c.d.e", 3, ["a"], "a/b"):
            with self.subTest(ruim), self.assertRaises(ValueError):
                catalogo.validar_acao(dict(LIVRE, so_com=ruim))
        self.assertNotIn("so_com", catalogo.publica(catalogo.validar_acao(PRESA)))


if __name__ == "__main__":
    unittest.main()
