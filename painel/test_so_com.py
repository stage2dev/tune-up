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

    def test_rede_local_sem_so_com_recusada(self):
        sem = dict(PRESA)
        sem.pop("so_com")
        with self.assertRaises(ValueError) as ctx:
            catalogo.validar_acao(sem)
        self.assertIn("so_com", str(ctx.exception))
        self.assertTrue(catalogo.validar_acao(dict(sem, sandbox=True))["sandbox"])  # sandbox sem rede_local segue

    def test_pacote_nao_tira_so_com_nem_liga_rede_local_de_plugin(self):
        # o pacote carrega antes dos plugins: a mesma id sem so_com, com outro so_com ou com rede_local perde o lugar
        sem_so_com = dict(PRESA, sandbox=True)
        sem_so_com.pop("so_com")
        outro_so_com = dict(PRESA, so_com="meu.sempre")
        com_rede = dict(LIVRE, so_com="meu.sempre", sandbox={"rede_local": True})
        plugin_livre = dict(LIVRE, sandbox=True)
        for pacote, plugin in ((sem_so_com, PRESA), (outro_so_com, PRESA), (com_rede, plugin_livre)):
            with self.subTest(pacote=pacote):
                pastas = [os.path.join(self.tmp, n) for n in ("nucleo", "pacote", "plugin")]
                for pasta, acoes in zip(pastas[1:], ([dict(pacote, titulo="Falsa")], [plugin])):
                    os.makedirs(pasta, exist_ok=True)
                    with open(os.path.join(pasta, "a.json"), "w", encoding="utf-8") as f:
                        json.dump({"acoes": acoes}, f)
                acoes, avisos = catalogo.carregar_catalogo(pastas)
                self.assertEqual([a["titulo"] for a in acoes], [plugin["id"]], avisos)
                self.assertEqual(len(avisos), 1, avisos)
        for pasta, acao in (("pacote", dict(PRESA, titulo="Minha")), ("plugin", PRESA)):
            with open(os.path.join(self.tmp, pasta, "a.json"), "w", encoding="utf-8") as f:
                json.dump({"acoes": [acao]}, f)  # mesmas travas: o pacote segue ocupando a id
        acoes, _ = catalogo.carregar_catalogo(pastas)
        self.assertEqual([a["titulo"] for a in acoes], ["Minha"])


if __name__ == "__main__":
    unittest.main()
