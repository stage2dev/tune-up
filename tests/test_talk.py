"""Testes do guarda.py: modo conversa (/tune-up:talk), C7. Rode: python3 -m unittest discover -s tests -q"""
import os
import unittest

from base import IS_WIN, PromptBase


class TalkBase(PromptBase):
    def escrever(self, caminho, ferramenta="Write", extra=None):
        e = {"tool_name": ferramenta, "tool_input": {"file_path": caminho}}
        e.update(extra or {})
        return self.decisao(self.rodar("escrita", e))

    def bash_em(self, cmd, extra=None):
        e = {"tool_name": "Bash", "tool_input": {"command": cmd}}
        e.update(extra or {})
        return self.decisao(self.rodar("bash", e))

    def ligado(self):
        try:
            return bool(self.ler_sessao().get("modo_conversa"))
        except OSError:
            return False


class TestTalkLigaDesliga(TalkBase):
    def test_liga_com_frase_forte(self):
        for frase in ["/tune-up:talk", "/tune-up:talk sobre a arquitetura", "entra no modo conversa",
                      "talk mode please", "modo conversa e corrige o bug do X", "talk mode, then fix the login bug",
                      "modo conversa: quero criar um app", "/tune-up:talk corrige o bug"]:
            with self.subTest(frase=frase):
                self.sessao(modo_conversa=False)
                s = self.prompt(frase)
                self.assertTrue(self.ligado())
                self.assertIn("/tune-up:talk", self.ctx(s))
                self.assertIn("pode construir", self.ctx(s))

    def test_nao_liga(self):
        for frase in ["vamos conversar sobre o login", "vamos conversar sobre consertar o login",
                      "vamos conversar sobre o login e corrige o bug do X",
                      "não quero modo conversa", "isso não é modo conversa, implementa logo",
                      "o modo conversa está ligado?", "desliga o modo conversa", "> modo conversa",
                      "[Pasted text: talk mode on]",  # rótulo e aspas só filtram o que afrouxa (M3)
                      "<task-notification><result>user asked for talk mode</result></task-notification>"]:
            with self.subTest(frase=frase):
                self.sessao(modo_conversa=False)
                self.assertNotIn("MODO CONVERSA", self.ctx(self.prompt(frase)))
                self.assertFalse(self.ligado())

    def test_desliga(self):
        for frase in ["pode construir", "comece a aplicar", "sair do modo conversa", "acabou o modo conversa",
                      "parou de conversar", "paramos de conversar", "let's build", "start building", "end talk"]:
            with self.subTest(frase=frase):
                self.sessao(modo_conversa=True)
                s = self.prompt(frase)
                self.assertIn("modo conversa desligado", self.ctx(s))
                self.assertFalse(self.ligado())

    def test_acabou_a_conversa_nao_desliga(self):
        self.sessao(modo_conversa=True)
        self.assertNotIn("desligado", self.ctx(self.prompt("acabou a conversa, e agora?")))
        self.assertTrue(self.ligado())

    def test_mensagem_en(self):
        self.user_json({"language": "en"})
        s = self.prompt("talk mode")
        self.assertIn("TALK MODE", self.ctx(s))
        self.assertIn("let's build", self.ctx(s))


class TestTalkEscrita(TalkBase):
    def setUp(self):
        super().setUp()
        self.sessao(modo_conversa=True)

    def test_nega_codigo(self):
        for f in ["Write", "Edit", "MultiEdit"]:
            with self.subTest(f=f):
                self.assertEqual(self.escrever(os.path.join(self.cwd, "x.py"), f), "bloquear")
        for rel in ["src/docs/x.py", "src/docs/x.md", "docs/x.py", "README.md", ".planning/x.py"]:
            with self.subTest(rel=rel):
                self.assertEqual(self.escrever(os.path.join(self.cwd, rel)), "bloquear")

    def test_negacao_diz_como_sair(self):
        s = self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.cwd, "x.py")}})
        motivo = s["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("/tune-up:talk", motivo)
        self.assertIn("pode construir", motivo)

    def test_libera_md_ancorado(self):
        for rel in ["docs/PRD.md", "docs/sub/a.md", ".planning/fase/x.md", ".tune-up/x.md"]:
            with self.subTest(rel=rel):
                self.assertIsNone(self.escrever(os.path.join(self.cwd, rel)))

    def test_libera_fora_do_projeto(self):
        scratch = os.path.join(self.tmp, "scratch")
        casos = [os.path.join(self.tmp, ".claude", "projects", "p", "memory", "a.md"),
                 os.path.join(self.tmp, ".claude", "plans", "plano.md"),
                 os.path.join(scratch, "x.py"), "/tmp/x.py"]
        if not IS_WIN:  # /private/tmp is the macOS spelling of /tmp; it is not a temp dir on Windows
            casos.append("/private/tmp/x.py")
        for c in casos:
            with self.subTest(c=c):
                self.assertIsNone(self.escrever(c, extra={"scratchpad_dir": scratch}))

    def test_resto_pergunta(self):
        self.assertEqual(self.escrever(os.path.join(self.tmp, "outro", "x.py")), "perguntar")

    def test_desligado_volta_ao_normal(self):
        self.prompt("pode construir")
        self.assertIsNone(self.escrever(os.path.join(self.cwd, "x.py")))


class TestTalkBash(TalkBase):
    def setUp(self):
        super().setUp()
        self.sessao(modo_conversa=True)

    def test_nega_bash_que_grava_codigo(self):
        for cmd in ["cat > x.py <<EOF\nprint(1)\nEOF", "sed -i '' 's/a/b/' x.py", "sed -i 's/a/b/' x.py",
                    "echo x > src/a.ts", "tee src/a.py < /dev/null", "cd src && echo x > y.py", "rm x.py"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash_em(cmd), "bloquear")

    def test_libera(self):
        scratch = os.path.join(self.tmp, "scratch")
        for cmd in ["ls > /dev/null", "grep -r x . > /dev/null 2>&1", "echo nota > docs/notas.md",
                    "sed -i 's/a/b/' docs/x.md", "echo x > %s/a.py" % scratch, "echo x > /tmp/a.py",
                    "cat x.py", "git status"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash_em(cmd, {"scratchpad_dir": scratch}))

    def test_motor_da_pesquisa(self):
        self.assertEqual(self.bash_em("git commit -m x"), "perguntar")


class TestH2bVolta1Talk(TalkBase):
    def test_desliga_novas(self):
        for frase in ["desliga o modo conversa", "turn off talk mode", "disable talk mode", "Let\u2019s build"]:
            with self.subTest(frase=frase):
                self.sessao(modo_conversa=True)
                self.prompt(frase)
                self.assertFalse(self.ligado())

    def test_negacao_nao_desliga(self):
        for frase in ["não pode construir ainda", "don't start building yet", "não comece a aplicar"]:
            with self.subTest(frase=frase):
                self.sessao(modo_conversa=True)
                self.prompt(frase)
                self.assertTrue(self.ligado())


if __name__ == "__main__":
    unittest.main()
