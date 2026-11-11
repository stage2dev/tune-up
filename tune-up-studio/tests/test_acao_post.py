"""The real action estudio.post (painel/acoes/estudio.json) against the studio fixture and the Bash list.

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
SKILL = os.path.join(STUDIO, "skills", "post", "SKILL.md")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class PostAction(unittest.TestCase):
    def setUp(self):
        self.raw = [a for a in load(ACTIONS)["acoes"] if a["id"] == "estudio.post"][0]
        self.acao = catalogo.validar_acao(self.raw)

    def test_bash_list_and_env_match_the_fixture(self):
        bash = [r for r in self.raw["negar"] if isinstance(r, dict)]
        self.assertEqual(bash, load(RULES)["negar"])
        fixture = load(FIXTURE)["acoes"][0]
        self.assertEqual(bash, fixture["negar"])
        self.assertEqual(self.raw["env"], fixture["env"])
        self.assertEqual(self.raw["permitir"], fixture["permitir"])

    def test_hyperframes_skills_denied(self):
        self.assertIn("Skill(hyperframes)", self.raw["negar"])
        self.assertIn("Skill(hyperframes-cli)", self.raw["negar"])

    def test_sandbox_on_without_local_network_and_brand_required(self):
        self.assertIs(self.acao["sandbox"], True)
        self.assertNotIn("_rede_local", self.acao)  # post uses snapshot: no local port
        self.assertEqual(self.acao["_requer"], ["estudio.marca"])
        self.assertEqual((self.acao["modelos"], self.acao["esforco"]), (["opus"], "medium"))

    def test_prompt_calls_the_skill_with_work_folder_and_briefing_file(self):
        self.assertTrue(self.acao["_prompt"].startswith("/tune-up-studio:post "))
        for marker in ("{trabalho}", "{briefing}", "{formato}", "{quadros}"):
            self.assertIn(marker, self.acao["_prompt"])
        tipos = {p["nome"]: p["tipo"] for p in self.acao["params"]}
        self.assertEqual(tipos, {"briefing": "texto_longo", "formato": "escolha", "quadros": "escolha"})

    def test_skill_exists_and_never_lists(self):
        with open(SKILL, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("---\nname: post\n"))
        self.assertIn("never run `ls`", text)
        self.assertIn("At most 2 fix rounds", text)


if __name__ == "__main__":
    unittest.main()
