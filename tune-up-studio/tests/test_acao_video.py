"""The real actions estudio.video (slide reserve) and estudio.video-motion (render, local network).

Loads them the way the panel does (catalogo.validar_acao). No session, no network.
"""
import json
import os
import re
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


OBJETIVOS = ["a IA escolhe", "vender", "receber mensagens", "encher a agenda", "lançar novidade",
             "ensinar e ganhar seguidores"]
ESTILOS = ["a IA escolhe", "produto em destaque", "tipografia cinética", "conversa de WhatsApp",
           "lista que se marca sozinha", "contador e gráfico", "antes e depois", "tela com cursor clicando",
           "cartaz que se monta", "passo a passo", "mito ou verdade"]
REFS = ("ganchos.md", "arquetipos-post.md", "padroes-cena.md", "ritmo.md", "legenda.md", "checklist-atencao.md",
        "recursos-visuais.md", "motion-js.md", "kit-post.md", "kit-video.md", "heroi.md")


def skill_rules(test, text, max_lines=130):
    """Shared by the three skills: short, gsap only in the Forbidden list, references by their exact names."""
    test.assertLessEqual(len(text.splitlines()), max_lines)
    test.assertNotIn("gsap.", text.lower())
    linhas = [ln for ln in text.splitlines() if "gsap" in ln.lower()]
    test.assertEqual(len(linhas), 1)
    test.assertIn("forbidden", linhas[0].lower())  # the Forbidden list is a lock: it stays
    for nome in re.findall(r"referencias/([a-z-]+\.md)", text):  # the names P1 creates, exactly
        test.assertIn(nome, REFS)
    for marca in ("zapscaler", "autoagendai"):
        test.assertNotIn(marca, text.lower())


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
                for marker in ("{trabalho}", "{briefing}", "{duracao}", "{objetivo}", "{estilo}"):
                    self.assertIn(marker, a["_prompt"])
                self.assertIn("Objetivo: {objetivo}. Estilo: {estilo}. Briefing no arquivo {briefing}", a["_prompt"])
                params = {p["nome"]: p for p in a["params"]}
                self.assertEqual(set(params), {"briefing", "duracao", "objetivo", "estilo"})
                self.assertEqual(params["estilo"]["rotulo"], "Estilo do vídeo")
                self.assertEqual(params["estilo"]["tipo"], "escolha")
                self.assertIs(params["estilo"]["obrigatorio"], False)
                self.assertEqual(params["estilo"]["opcoes"], ESTILOS)
                self.assertEqual(params["briefing"]["tipo"], "texto_longo")
                self.assertIn("prova real", params["briefing"]["ajuda"])
                self.assertEqual(params["duracao"]["opcoes"], ["10", "15"])
                self.assertEqual(params["objetivo"]["tipo"], "escolha")
                self.assertIs(params["objetivo"]["obrigatorio"], False)
                self.assertEqual(params["objetivo"]["opcoes"], OBJETIVOS)

    def test_objective_may_be_missing(self):
        for k, a in self.acao.items():
            with self.subTest(k):
                sem = catalogo.validar_params(a, {"briefing": "Pao", "duracao": "10"}, {})
                self.assertEqual(sem["objetivo"], "")
                com = catalogo.validar_params(a, {"briefing": "Pao", "duracao": "15", "objetivo": "encher a agenda"}, {})
                self.assertEqual(com["objetivo"], "encher a agenda")
                with self.assertRaises(catalogo.ErroAcao):
                    catalogo.validar_params(a, {"briefing": "Pao", "duracao": "10", "objetivo": "outro"}, {})

    def test_style_may_be_missing_and_is_never_free_text(self):
        for k, a in self.acao.items():
            with self.subTest(k):
                sem = catalogo.validar_params(a, {"briefing": "Pao", "duracao": "10"}, {})
                self.assertEqual(sem["estilo"], "")
                self.assertIn("Estilo: . Briefing", catalogo.montar(a["_prompt"], sem))
                com = catalogo.validar_params(a, {"briefing": "Pao", "duracao": "15", "estilo": "conversa de WhatsApp"}, {})
                self.assertIn("Estilo: conversa de WhatsApp. Briefing", catalogo.montar(a["_prompt"], com))
                with self.assertRaises(catalogo.ErroAcao):
                    catalogo.validar_params(a, {"briefing": "Pao", "duracao": "10", "estilo": "estilo livre"}, {})

    def test_skill_reads_the_saved_report_and_never_lists(self):
        with open(SKILL, encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("---\nname: video\n"))
        self.assertIn("never run `ls`", text)
        self.assertIn("At most 2 fix rounds", text)
        self.assertNotIn("--check-json", text)  # the QA reads what HyperFrames saved, never a copy
        self.assertNotIn("gsap.", text.lower())
        for step in ("--experimental-fast-capture=false", "--workers=1", "HF lint fonte", "--sheet folha.png", "reserva_slides.py --slides slides", "fontes.py"):
            self.assertIn(step, text)
        # round 6: the layout comes from the kit (kit-video.md, heroi.md, montar.py), no longer from padroes-cena.md
        for frase in ("--tempos", "--atencao", "--pares", "estrategia.md", "referencias/ritmo.md",
                      "kit-video.md", "heroi.md", "montar.py --tipo video", "checklist-atencao.md", "ganchos.md",
                      "Objetivo", "Estilo", "a IA escolhe", "each slide lasts its scene"):
            self.assertIn(frase, text)
        self.assertNotIn("same length", text)  # the reserve follows the scene lengths now
        frontmatter = text.split("---", 2)[1]
        allowed = [ln for ln in frontmatter.splitlines() if ln.startswith("allowed-tools:")][0]
        self.assertIn("Bash(python3 -I ${CLAUDE_PLUGIN_ROOT}/scripts/qa_imagem.py *)", allowed)
        # numbers of the motion recipes live only in referencias/padroes-cena.md
        for antigo in ("scale(.3)", "rotate(-10deg)", "scale(1.07)", "circle(80%"):
            self.assertNotIn(antigo, text)
        skill_rules(self, text)


if __name__ == "__main__":
    unittest.main()
