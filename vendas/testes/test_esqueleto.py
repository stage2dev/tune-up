"""Esqueleto do plugin tune-up-vendas: manifesto, marketplace, módulo pelo carregador real do painel."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
RAIZ = os.path.dirname(VENDAS)
sys.path.insert(0, os.path.join(RAIZ, "painel"))

import config  # noqa: E402
import modulos  # noqa: E402

CHAVE = "tune-up-vendas@mkt-teste"
TIPOS = {"kpis", "tabela", "lista", "serie", "texto", "acoes", "formulario", "conversa", "imagem"}


class TesteEsqueleto(unittest.TestCase):
    def test_plugin_json(self):
        with open(os.path.join(VENDAS, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            p = json.load(f)
        self.assertEqual(p["name"], "tune-up-vendas")
        self.assertEqual(p["version"], "0.1.0")
        self.assertEqual(p["license"], "MIT")
        self.assertTrue(p["description"].isascii() and p["description"])

    def test_marketplace_lista_os_dois(self):
        with open(os.path.join(RAIZ, ".claude-plugin", "marketplace.json"), encoding="utf-8") as f:
            m = json.load(f)
        fontes = {p["name"]: p["source"] for p in m["plugins"]}
        self.assertEqual(fontes, {"tune-up": "./", "tune-up-vendas": "./vendas"})

    def test_modulo_carrega_pelo_painel_real(self):
        tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        os.makedirs(os.path.join(tmp, ".claude", "plugins"))
        os.makedirs(os.path.join(tmp, ".tune-up"))
        with open(os.path.join(tmp, ".claude", "plugins", "installed_plugins.json"), "w") as f:
            json.dump({"version": 2, "plugins": {CHAVE: [{"installPath": os.path.realpath(VENDAS)}]}}, f)
        with open(os.path.join(tmp, ".tune-up", "painel.json"), "w") as f:
            json.dump({"modulos_de_plugins": [CHAVE + ":vendas"]}, f)
        cfg = config.carregar(tmp, home=tmp)
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)
        codigo, dado = modulos.montar(cfg, "vendas")
        self.assertEqual(codigo, 200)
        self.assertEqual(dado["id"], "vendas")
        self.assertEqual(dado["avisos"], [])
        aba = dado["abas"][0]
        self.assertEqual(aba["titulo"], "Conexão")
        self.assertEqual([a["titulo"] for a in dado["abas"]], ["Conexão", "Conversas", "IA", "Leads", "Disparos"])
        for b in aba["blocos"]:
            self.assertIn(b["tipo"], TIPOS)
        self.assertIn("está parado", aba["blocos"][0]["texto"])
        regras = modulos.regras_de_negar(cfg)
        self.assertIn("Bash(*security find-generic-password*)", regras)
        self.assertIn("Bash(*/api/modulos/*/acao*)", regras)

    def test_sem_nomes_do_projeto_original(self):
        # partido em pedaços para o próprio teste não casar com o grep do plano
        rx = re.compile("|".join(["zap" + "scaler", "autoagend" + "ai", "vaap" + "ty", "41" + "05"]), re.I)
        achados = []
        for pasta, _, arqs in os.walk(VENDAS):
            for a in arqs:
                if a.endswith(".pyc"):
                    continue
                caminho = os.path.join(pasta, a)
                with open(caminho, encoding="utf-8", errors="replace") as f:
                    if rx.search(f.read()) or rx.search(a):
                        achados.append(caminho)
        self.assertEqual(achados, [])


if __name__ == "__main__":
    unittest.main()
