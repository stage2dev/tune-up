"""Docs do painel: sem 'macOS and Linux only' e com o launcher scripts/py em vez de python3 literal."""
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOVO = 'sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" -B "${CLAUDE_PLUGIN_ROOT}/painel/painel.py"'


def ler(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        return f.read()


class TestDocsPainel(unittest.TestCase):
    def test_skill_sem_so_mac_linux(self):
        for texto in (ler("skills", "panel", "SKILL.md"), ler("README.md")):
            self.assertNotRegex(texto, r"macOS and Linux(?! and)")
        self.assertIn("Windows", ler("skills", "panel", "SKILL.md"))

    def test_skill_usa_scripts_py_no_allowed_tools_e_no_comando(self):
        s = ler("skills", "panel", "SKILL.md")
        self.assertIn("allowed-tools: Bash(" + NOVO + " *)", s)
        self.assertIn("`" + NOVO + " --projeto", s)
        self.assertNotIn("python3 -B", s)

    def test_readme_do_painel_sem_python3_literal_nos_comandos(self):
        r = ler("painel", "README.md")
        self.assertIsNone(re.search(r"^python3 .*painel\.py", r, re.M))
        self.assertNotIn("`python3 painel.py", r)


if __name__ == "__main__":
    unittest.main()
