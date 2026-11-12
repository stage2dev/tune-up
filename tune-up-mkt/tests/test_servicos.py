"""Schema test for servicos.json and presence of the B1 fixtures."""
import datetime
import json
import os
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(RAIZ, "tests", "fixtures")
IDS = ["chrome", "composio", "openseo", "search_console_analytics",
       "indexnow", "claude_ads", "anthropic_marketing", "higgsfield",
       "elevenlabs"]
NIVEL = {"chrome": "base", "composio": "base", "openseo": "base",
         "search_console_analytics": "por_canal", "indexnow": "por_canal",
         "claude_ads": "opcional", "anthropic_marketing": "opcional",
         "higgsfield": "opcional", "elevenlabs": "opcional"}
TIPOS = {"plugin", "mcp", "cli", "ferramenta", "manual"}
FIXTURES_ESPERADAS = [
    "plugin_list_ligado.json", "plugin_list_ausente.json",
    "plugin_list_desligado.json", "mcp_list_ligado.txt",
    "mcp_list_falta_autenticar.txt", "mcp_list_ausente.txt",
    "mcp_list_estados.txt", "composio_connections_ligado.json",
    "composio_connections_expirado.json", "composio_connections_vazio.json",
    "composio_connections_metaads.json", "mcp_list_formato_desconhecido.txt",
    "composio_connections_formato_desconhecido.json", "README.md",
]


def carregar():
    with open(os.path.join(RAIZ, "servicos.json"), encoding="utf-8") as f:
        return json.load(f)


class Servicos(unittest.TestCase):
    def setUp(self):
        self.dados = carregar()
        self.por_id = {s["id"]: s for s in self.dados["servicos"]}

    def bilingue(self, v, onde):
        self.assertIsInstance(v, dict, onde)
        for k in ("en", "pt"):
            self.assertIsInstance(v.get(k), str, onde)
            self.assertTrue(v[k].strip(), onde)

    def checar_conferir(self, lista, onde):
        self.assertIsInstance(lista, list, onde)
        self.assertTrue(lista, onde)
        for c in lista:
            self.assertIn(c.get("tipo"), TIPOS, onde)
            if c["tipo"] == "cli":
                self.assertIsInstance(c["alvo"], list, onde)
                self.assertTrue(all(isinstance(a, str) for a in c["alvo"]))
                self.assertIn(c["alvo"][0], ("claude", "composio"), onde)
            else:
                self.assertIsInstance(c["alvo"], str, onde)
                self.assertTrue(c["alvo"].strip(), onde)
            if "nota" in c:
                self.assertIsInstance(c["nota"], str, onde)

    def test_ids_e_ordem(self):
        self.assertEqual(self.dados["versao"], 1)
        self.assertEqual([s["id"] for s in self.dados["servicos"]], IDS)

    def test_campos_e_tipos(self):
        for s in self.dados["servicos"]:
            i = s["id"]
            self.assertEqual(s["nivel"], NIVEL[i], i)
            self.assertTrue(s["nome"].strip(), i)
            for k in ("para_que", "autenticar", "custo_aviso"):
                self.bilingue(s[k], i + "." + k)
            for k in ("cadastro_url", "doc_url"):
                self.assertTrue(s[k].startswith("https://"), i + "." + k)
            self.assertIsInstance(s["instalar"], list, i)
            self.assertTrue(s["instalar"], i)
            self.assertTrue(all(isinstance(x, str) and x for x in s["instalar"]))
            self.assertIsInstance(s["pre_requisitos"], list, i)
            for p in s["pre_requisitos"]:
                self.bilingue(p, i + ".pre_requisitos")
            self.checar_conferir(s["conferir"], i)
            datetime.date.fromisoformat(s["conferido_em"])
            self.assertIsInstance(s["incerto"], list, i)
            self.assertTrue(all(isinstance(x, str) and x for x in s["incerto"]))

    def test_canais_do_composio(self):
        canais = self.por_id["composio"]["canais"]
        self.assertEqual([c["id"] for c in canais],
                         ["metaads", "googleads", "instagram", "facebook"])
        for c in canais:
            self.assertTrue(c["nome"].strip())
            self.bilingue(c["para_que"], c["id"])
            for p in c["pre_requisitos"]:
                self.bilingue(p, c["id"])
            self.checar_conferir(c["conferir"], c["id"])
            self.assertEqual(c["conferir"][0]["alvo"][-2:],
                             ["--toolkit", c["id"]])
        self.assertNotIn("canais", self.por_id["openseo"])

    def test_fixtures_existem_e_json_valido(self):
        for n in FIXTURES_ESPERADAS:
            caminho = os.path.join(FIXTURES, n)
            self.assertTrue(os.path.isfile(caminho), n)
            if n.endswith(".json"):
                with open(caminho, encoding="utf-8") as f:
                    json.load(f)


if __name__ == "__main__":
    unittest.main()
