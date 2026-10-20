"""Tests: message catalog in en and pt-BR, user.json and SessionStart line. Run: python3 -m unittest discover -s tests -q"""
import json
import os
import subprocess
import sys
import unittest

from base import SCRIPT, PromptBase

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from tuneup import mensagens  # noqa: E402


class TestIdioma(PromptBase):
    USER_JSON = None  # each test picks its own profile

    def razao(self, cmd):
        s = self.rodar("bash", {"tool_name": "Bash", "tool_input": {"command": cmd}})
        return s["hookSpecificOutput"]["permissionDecisionReason"]

    def test_sem_user_json_e_ingles(self):
        self.assertIn("add files by name", self.razao("git add -A"))
        self.assertIn("RESEARCH MODE", self.ctx(self.prompt("só pesquisa, sem alterar nada")))
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("run /tune-up:setup", s["hookSpecificOutput"]["additionalContext"])

    def test_en(self):
        self.user_json({"language": "en", "owner": "Ana", "reply_style": "plain"})
        self.assertIn("add files by name", self.razao("git add -A"))
        self.assertIn("RESEARCH MODE", self.ctx(self.prompt("só pesquisa, sem alterar nada")))
        self.assertIn("merging belongs to Ana", self.razao("gh pr merge 12"))
        c = self.rodar("inicio", {"source": "startup"})["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(c, "tune-up: language en, owner Ana, reply style plain.")

    def test_pt_br(self):
        self.user_json({"language": "pt-BR", "owner": "Ana", "reply_style": "summary"})
        self.assertIn("adicione os arquivos pelo nome", self.razao("git add -A"))
        self.assertIn("MODO PESQUISA", self.ctx(self.prompt("só pesquisa, sem alterar nada")))
        self.assertIn("o merge fica com Ana", self.razao("gh pr merge 12"))
        c = self.rodar("inicio", {"source": "startup"})["hookSpecificOutput"]["additionalContext"]
        self.assertEqual(c, "tune-up: idioma pt-BR, dono Ana, estilo de resposta summary.")

    def test_sem_dono_usa_palavra_generica(self):
        self.user_json({"language": "en"})
        self.assertIn("merging belongs to the owner", self.razao("gh pr merge 12"))

    def test_idioma_desconhecido_cai_em_ingles(self):
        self.user_json({"language": "xx"})
        self.assertIn("add files by name", self.razao("git add -A"))

    def test_user_json_quebrado_usa_padrao_e_loga(self):
        p = os.path.join(self.tmp, "user.json")
        with open(p, "w") as f:
            f.write("{quebrado")
        self.env["TUNEUP_USER_JSON"] = p
        self.assertIn("add files by name", self.razao("git add -A"))
        with open(os.path.join(self.dados, "erros.log")) as f:
            self.assertIn("user.json invalid", f.read())

    def test_projeto_confiado_vence_user_json(self):
        self.user_json({"language": "en"})
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)
        c = os.path.join(perfil, "config.json")
        with open(c, "w") as f:
            json.dump({"language": "pt-BR"}, f)
        self.assertIn("add files by name", self.razao("git add -A"))  # not trusted: user.json wins
        self.confiar(c)
        self.assertIn("adicione os arquivos pelo nome", self.razao("git add -A"))

    def test_startup_so_em_startup(self):
        self.user_json({"language": "en"})
        for src in ("compact", "clear", "resume"):
            with self.subTest(src=src):
                s = self.rodar("inicio", {"source": src})
                c = s["hookSpecificOutput"]["additionalContext"] if s else ""
                self.assertNotIn("reply style", c)
                self.assertNotIn("/tune-up:setup", c)

    def test_confiar_fala_no_idioma(self):
        self.user_json({"language": "en"})
        r = subprocess.run([sys.executable, SCRIPT, "trust", os.path.join(self.tmp, "nada.json")],
                           capture_output=True, text=True, env=self.env, timeout=20)
        self.assertIn("does not exist", r.stdout)

    def test_idioma_normalizado_e_precedencia(self):
        self.user_json({"language": "pt-br"})
        self.assertIn("adicione os arquivos pelo nome", self.razao("git add -A"))
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)
        c = os.path.join(perfil, "config.json")
        for lang, esperado in (("fr", "adicione os arquivos pelo nome"), ("EN", "add files by name")):
            with self.subTest(lang=lang):
                with open(c, "w") as f:
                    json.dump({"language": lang}, f)
                self.confiar(c)
                self.assertIn(esperado, self.razao("git add -A"))

    def test_user_json_invalido_avisa_no_startup(self):
        p = os.path.join(self.tmp, "user.json")
        for bruto in ("{quebrado", "[1, 2]"):
            with self.subTest(bruto=bruto):
                with open(p, "w") as f:
                    f.write(bruto)
                self.env["TUNEUP_USER_JSON"] = p
                s = self.rodar("inicio", {"source": "startup"})
                self.assertIn("user.json invalid", s.get("systemMessage", ""))
                self.assertIn("/tune-up:setup", s["hookSpecificOutput"]["additionalContext"])

class TestCatalogo(unittest.TestCase):
    def test_mesmas_chaves(self):
        self.assertEqual(set(mensagens.CATALOG["en"]), set(mensagens.CATALOG["pt-BR"]))

    def test_mesmos_marcadores(self):
        for k, en in mensagens.CATALOG["en"].items():
            with self.subTest(k=k):
                pt = mensagens.CATALOG["pt-BR"][k]
                self.assertEqual(en.count("%"), pt.count("%"))
                self.assertEqual("{owner}" in en, "{owner}" in pt)


if __name__ == "__main__":
    unittest.main()
