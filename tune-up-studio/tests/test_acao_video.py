"""The real actions estudio.video (slide reserve) and estudio.video-motion (render, local network).

Loads them the way the panel does (catalogo.validar_acao). No session, no network.
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
SKILL = os.path.join(STUDIO, "skills", "video", "SKILL.md")


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class VideoActions(unittest.TestCase):
    def setUp(self):
        raw = {a["id"]: a for a in load(ACTIONS)["acoes"]}
        self.raw = {k: raw[k] for k in ("estudio.video", "estudio.video-motion")}
        self.acao = {k: catalogo.validar_acao(v) for k, v in self.raw.items()}

    def test_bash_list_env_and_skills_match_the_fixture(self):
        fixture = load(FIXTURE)["acoes"][0]
        for k, raw in self.raw.items():
            with self.subTest(k):
                bash = [r for r in raw["negar"] if isinstance(r, dict)]
                self.assertEqual(bash, load(RULES)["negar"])
                self.assertEqual(bash, fixture["negar"])
                self.assertEqual(raw["env"], fixture["env"])
                self.assertEqual(raw["permitir"], fixture["permitir"])
                self.assertIn("Skill(hyperframes)", raw["negar"])
                self.assertIn("Skill(hyperframes-cli)", raw["negar"])

    def test_reserve_has_no_local_network_and_motion_needs_the_project_key(self):
        reserva, motion = self.acao["estudio.video"], self.acao["estudio.video-motion"]
        self.assertIs(reserva["sandbox"], True)
        self.assertNotIn("_rede_local", reserva)
        self.assertIsNone(reserva["_so_com"])
        self.assertIn("Motor: reserva.", reserva["_prompt"])
        self.assertEqual(self.raw["estudio.video-motion"]["sandbox"], load(FIXTURE)["acoes"][0]["sandbox"])
        self.assertIs(motion["_rede_local"], True)
        self.assertEqual(motion["_so_com"], "estudio.video_rede_local")
        self.assertIn("Motor: hyperframes.", motion["_prompt"])

    def test_model_brand_and_params(self):
        for k, a in self.acao.items():
            with self.subTest(k):
                self.assertEqual(a["_requer"], ["estudio.marca"])
                self.assertEqual((a["modelos"], a["esforco"]), (["opus"], "medium"))
                self.assertTrue(a["_prompt"].startswith("/tune-up-studio:video "))
                for marker in ("{trabalho}", "{briefing}", "{duracao}"):
                    self.assertIn(marker, a["_prompt"])
                params = {p["nome"]: p for p in a["params"]}
                self.assertEqual(params["briefing"]["tipo"], "texto_longo")
                self.assertEqual(params["duracao"]["opcoes"], ["10", "15"])

    def test_skill_reads_the_saved_report_and_never_lists(self):
        with open(SKILL, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("---\nname: video\n"))
        self.assertIn("never run `ls`", text)
        self.assertIn("At most 2 fix rounds", text)
        self.assertNotIn("--check-json", text)  # the QA reads what HyperFrames saved, never a copy
        self.assertNotIn("gsap.", text.lower())
        for step in ("HF lint fonte", "--sheet folha.png", "reserva_slides.py --slides slides", "fontes.py"):
            self.assertIn(step, text)


if __name__ == "__main__":
    unittest.main()
