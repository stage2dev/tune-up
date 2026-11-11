"""The real action estudio.anuncio (painel/acoes/estudio.json) against the studio fixture and the Bash list.

Loads it the way the panel does (catalogo.validar_acao). No session, no network.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
PAINEL = os.path.join(os.path.dirname(STUDIO), "painel")
sys.path.insert(0, PAINEL)

import catalogo  # noqa: E402

ACTIONS = os.path.join(STUDIO, "painel", "acoes", "estudio.json")
RULES = os.path.join(STUDIO, "regras", "bash-estudio.json")
FIXTURE = os.path.join(PAINEL, "tests_reais", "acao_estudio.json")
SKILL = os.path.join(STUDIO, "skills", "anuncio", "SKILL.md")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class AdAction(unittest.TestCase):
    def setUp(self):
        self.raw = [a for a in load(ACTIONS)["acoes"] if a["id"] == "estudio.anuncio"][0]
        self.acao = catalogo.validar_acao(self.raw)

    def test_same_positive_list_env_and_skills_as_the_fixture(self):
        bash = [r for r in self.raw["negar"] if isinstance(r, dict)]
        self.assertEqual(bash, load(RULES)["negar"])
        fixture = load(FIXTURE)["acoes"][0]
        self.assertEqual(bash, fixture["negar"])
        self.assertEqual(self.raw["env"], fixture["env"])
        self.assertEqual(self.raw["permitir"], fixture["permitir"])
        self.assertIn("Skill(hyperframes)", self.raw["negar"])
        self.assertIn("Skill(hyperframes-cli)", self.raw["negar"])

    def test_sandbox_without_local_network_brand_required_opus_medium(self):
        self.assertIs(self.acao["sandbox"], True)
        self.assertNotIn("_rede_local", self.acao)
        self.assertEqual(self.acao["_requer"], ["estudio.marca"])
        self.assertEqual((self.acao["modelos"], self.acao["esforco"]), (["opus"], "medium"))

    def test_prompt_and_params(self):
        self.assertTrue(self.acao["_prompt"].startswith("/tune-up-studio:anuncio "))
        for marker in ("{trabalho}", "{briefing}", "{plataforma}", "{url}"):
            self.assertIn(marker, self.acao["_prompt"])
        p = {x["nome"]: x for x in self.acao["params"]}
        self.assertEqual({k: v["tipo"] for k, v in p.items()},
                         {"briefing": "texto_longo", "plataforma": "escolha", "url": "texto"})
        self.assertEqual(p["plataforma"]["opcoes"], ["google", "meta"])
        self.assertEqual(p["url"]["formato"], "url")

    def test_url_must_be_https_without_space(self):
        base = {"briefing": "Pao", "plataforma": "google"}
        ok = catalogo.validar_params(self.acao, dict(base, url="https://exemplo.test/pao?x=1"), {})
        self.assertEqual(ok["url"], "https://exemplo.test/pao?x=1")
        for ruim in ("http://exemplo.test/", "https://exemplo.test/a b", "https://", "exemplo.test",
                     "https://exemplo.test/\"x", "https://user@exemplo.test/", "javascript:alert(1)"):
            with self.assertRaises(catalogo.ErroAcao, msg=ruim):
                catalogo.validar_params(self.acao, dict(base, url=ruim), {})

    def test_skill_exists_never_lists_and_never_publishes(self):
        with open(SKILL, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("---\nname: anuncio\n"))
        for frase in ("never run `ls`", "Nothing is published", "never write a sheet by hand",
                      "At most 2 fix rounds", "EXPERIMENTAL", "--width <largura> --height <altura>"):
            self.assertIn(frase, text)


if __name__ == "__main__":
    unittest.main()
