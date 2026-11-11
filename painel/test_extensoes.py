"""Testes de extensoes.py: ações de plugin instalado e a trava de versão/sha256. Nada chama o claude."""
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
import extensoes  # noqa: E402
import modulos  # noqa: E402
import painel  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ACAO = {"id": "estudio.post", "grupo": "estudio", "risco": "rascunho", "prompt": "Faça um post"}
CHAT = {"id": "chat.simples", "grupo": "chat", "risco": "leitura", "substitui": True, "prompt": "x {pedido}",
        "params": [{"nome": "pedido", "tipo": "texto"}]}
MODULO = "INFO = {\"titulo\": \"Estudio\"}\ndef montar(ctx):\n    return {}\n"


def escrever(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


class TesteExtensoes(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.inst = os.path.join(self.tmp, "cache", "meumarket", "estudio", "1.0.0")
        escrever(os.path.join(self.inst, "painel", "acoes", "estudio.json"), json.dumps({"acoes": [ACAO, CHAT]}))
        escrever(os.path.join(self.inst, "painel", "modulos", "estudio", "modulo.py"), MODULO)
        escrever(os.path.join(self.inst, "scripts", "qa.py"), "print(1)\n")
        self.registro({"estudio@meumarket": [{"installPath": self.inst, "version": "1.0.0"}],
                       "estudio@outromarket": [{"installPath": self.inst, "version": "1.0.0"}]})
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)

    def registro(self, plugins):
        escrever(os.path.join(self.tmp, ".claude", "plugins", "installed_plugins.json"),
                 json.dumps({"version": 2, "plugins": plugins}))

    def cfg(self, **chaves):
        escrever(os.path.join(self.tmp, ".tune-up", "painel.json"), json.dumps(dict({"nome": "L"}, **chaves)))
        c = config.carregar(self.tmp, home=self.tmp)
        c["acoes_dir"] = os.path.join(AQUI, "acoes")
        return c

    def ids(self, cfg):
        acoes, avisos = catalogo.catalogo_do_projeto(cfg)
        return [a["id"] for a in acoes], avisos

    def aceitas(self, cfg):
        with open(os.path.join(cfg["dados_dir"], "extensoes.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_plugin_listado_e_instalado_carrega_e_grava_versao_e_sha(self):
        cfg = self.cfg(acoes_de_plugins=["estudio@meumarket"])
        ids, avisos = self.ids(cfg)
        self.assertIn("estudio.post", ids)
        self.assertEqual([a for a in avisos if "estudio" in a and "repetida" not in a], [])
        gravado = self.aceitas(cfg)["estudio@meumarket"]
        self.assertEqual(gravado["versao"], "1.0.0")
        self.assertEqual(gravado["sha256"], extensoes.soma(self.inst))
        self.assertRegex(gravado["sha256"], r"^[0-9a-f]{64}$")

    def test_sem_a_chave_nada_de_plugin(self):
        for chaves in ({}, {"acoes_de_plugins": []}):
            ids, avisos = self.ids(self.cfg(**chaves))
            self.assertNotIn("estudio.post", ids)
            self.assertFalse(os.path.exists(os.path.join(self.tmp, ".tune-up", "painel-projeto", "dados",
                                                         "extensoes.json")))

    def test_plugin_nao_instalado_nao_carrega(self):
        ids, avisos = self.ids(self.cfg(acoes_de_plugins=["outro@meumarket"]))
        self.assertNotIn("estudio.post", ids)
        self.assertTrue(any("outro@meumarket não está instalado" in a for a in avisos), avisos)

    def test_mesmo_nome_em_outro_marketplace_nao_carrega(self):
        self.registro({"estudio@outromarket": [{"installPath": self.inst, "version": "1.0.0"}]})
        ids, avisos = self.ids(self.cfg(acoes_de_plugins=["estudio@meumarket"]))
        self.assertNotIn("estudio.post", ids)
        self.assertTrue(any("estudio@meumarket não está instalado" in a for a in avisos), avisos)
        ids, avisos = self.ids(self.cfg(acoes_de_plugins=["estudio"]))  # sem @marketplace
        self.assertNotIn("estudio.post", ids)
        self.assertTrue(any("use plugin@marketplace" in a for a in avisos), avisos)

    def test_conteudo_mudou_recusa_acoes_e_modulo_ate_aceitar(self):
        cfg = self.cfg(acoes_de_plugins=["estudio@meumarket"], modulos_de_plugins=["estudio@meumarket:estudio"])
        self.assertIn("estudio.post", self.ids(cfg)[0])
        self.assertEqual(modulos.montar(cfg, "estudio", usar_cache=False)[0], 200)
        escrever(os.path.join(self.inst, "scripts", "qa.py"), "print('trocado por outro')\n")
        ids, avisos = self.ids(cfg)
        self.assertNotIn("estudio.post", ids)
        self.assertTrue(any("conteúdo diferente" in a and "--aceitar-extensao estudio@meumarket" in a
                            for a in avisos), avisos)
        self.assertEqual(modulos.montar(cfg, "estudio", usar_cache=False)[0], 404)
        self.assertIn("aceito estudio@meumarket", extensoes.aceitar(cfg, "estudio@meumarket"))
        self.assertIn("estudio.post", self.ids(cfg)[0])
        self.assertEqual(modulos.montar(cfg, "estudio", usar_cache=False)[0], 200)

    def test_versao_mudou_recusa(self):
        cfg = self.cfg(acoes_de_plugins=["estudio@meumarket"])
        self.assertIn("estudio.post", self.ids(cfg)[0])
        self.registro({"estudio@meumarket": [{"installPath": self.inst, "version": "1.0.1"}]})
        ids, avisos = self.ids(cfg)
        self.assertNotIn("estudio.post", ids)
        self.assertTrue(any("1.0.0 -> 1.0.1" in a for a in avisos), avisos)

    def test_node_modules_nao_entra_na_soma(self):
        antes = extensoes.soma(self.inst)
        escrever(os.path.join(self.inst, "node", "node_modules", "x", "index.js"), "1")
        self.assertEqual(extensoes.soma(self.inst), antes)
        escrever(os.path.join(self.inst, "node", "package.json"), "{}")
        self.assertNotEqual(extensoes.soma(self.inst), antes)

    def test_acao_de_plugin_nao_substitui_a_do_nucleo(self):
        lista, avisos = catalogo.catalogo_do_projeto(self.cfg(acoes_de_plugins=["estudio@meumarket"]))
        acoes = {a["id"]: a for a in lista}
        self.assertNotEqual(acoes["chat.simples"]["_prompt"], "x {pedido}")
        self.assertTrue(any("chat.simples repetida" in a for a in avisos), avisos)

    def test_registro_ilegivel_recusa_tudo_e_aceitar_pede_para_apagar(self):
        cfg = self.cfg(acoes_de_plugins=["estudio@meumarket"])
        escrever(os.path.join(cfg["dados_dir"], "extensoes.json"), "{quebrado")
        ids, avisos = self.ids(cfg)
        self.assertNotIn("estudio.post", ids)
        self.assertTrue(any("ilegível" in a for a in avisos), avisos)
        with self.assertRaises(ValueError):
            extensoes.aceitar(cfg, "estudio@meumarket")
        with open(os.path.join(cfg["dados_dir"], "extensoes.json"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "{quebrado")

    def test_linha_de_comando_aceita_e_recusa(self):
        cfg = self.cfg(acoes_de_plugins=["estudio@meumarket"])
        with mock.patch.object(config, "carregar", return_value=cfg), mock.patch("builtins.print") as p:
            painel.main(["--projeto", self.tmp, "--aceitar-extensao", "estudio@meumarket"])
        self.assertIn("aceito estudio@meumarket", p.call_args[0][0])
        self.assertEqual(self.aceitas(cfg)["estudio@meumarket"]["versao"], "1.0.0")
        with mock.patch.object(config, "carregar", return_value=cfg), self.assertRaises(SystemExit) as fim:
            painel.main(["--projeto", self.tmp, "--aceitar-extensao", "nada@meumarket"])
        self.assertIn("não está instalado", str(fim.exception.code))


if __name__ == "__main__":
    unittest.main()
