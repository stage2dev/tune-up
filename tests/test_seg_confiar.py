"""Tests: trust bound to the config CONTENT and trust by indirection in Bash (security review
H2b, 21/10). Run: python3 -m unittest discover -s tests -q"""
import json
import os
import unittest
from base import SCRIPT, PromptBase, mkdtemp, rmtree, symlink


class TestSegConfiancaPeloConteudo(PromptBase):
    def cfg(self, conteudo):
        d = os.path.join(self.cwd, ".tune-up")
        os.makedirs(d, exist_ok=True)
        c = os.path.join(d, "config.json")
        with open(c, "w", encoding="utf-8") as f:
            json.dump(conteudo, f)
        os.chmod(c, 0o600)
        return c

    def test_editar_depois_do_trust_perde_a_confianca(self):
        c = self.cfg({"claude_may_merge": True})
        self.confiar(c)
        self.assertIsNone(self.bash("gh pr merge 12"))
        self.cfg({"claude_may_merge": True, "supabase_guard": False})  # edited after trust
        self.assertEqual(self.bash("gh pr merge 12"), "bloquear")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("mudou desde a confiança; rode trust de novo", s["systemMessage"])
        self.confiar(c)
        self.assertIsNone(self.bash("gh pr merge 12"))
        s = self.rodar("inicio", {"source": "startup"})
        self.assertNotIn("mudou", json.dumps(s, ensure_ascii=False) if s else "")

    def test_linha_antiga_sem_hash_nao_confia_e_avisa_uma_vez(self):
        c = self.cfg({"claude_may_merge": True})
        os.makedirs(self.dados, exist_ok=True)
        conf = os.path.join(self.dados, "perfis_confiaveis.txt")
        with open(conf, "w", encoding="utf-8") as f:
            f.write(os.path.realpath(c) + "\n")
        os.chmod(conf, 0o600)
        self.assertEqual(self.bash("gh pr merge 12"), "bloquear")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("sem hash", s["systemMessage"])
        s = self.rodar("inicio", {"source": "startup"})
        self.assertNotIn("sem hash", json.dumps(s, ensure_ascii=False) if s else "")


class TestSegConfiarIndireto(PromptBase):
    def test_formas_indiretas_perguntam(self):
        scripts = os.path.dirname(SCRIPT)
        g = os.path.join(self.cwd, "g")
        symlink(SCRIPT, g)  # symlink without .py
        u = os.path.join(self.tmp, ".config", "tune-up", "user.json")
        cfg = os.path.join(self.cwd, ".tune-up", "config.json")
        for cmd in ["python3 -m tuneup confiar x",
                    "cd %s && python3 -c 'import tuneup; tuneup.confiar(\"x\")'" % scripts,
                    "python3 -c 'import sys; sys.argv=[\"g\",\"trust\",\"%s\"]; exec(open(\"%s\").read())'"
                    % (cfg, SCRIPT),
                    "printf 'trust\\n' | xargs python3 %s" % SCRIPT,
                    "python3 g trust y", "python3 g x y",
                    "python3 %s TRUST x" % SCRIPT,
                    "cp %s /tmp/g.py; python3 /tmp/g.py trust y" % SCRIPT,
                    "ln -s %s g2" % SCRIPT, "ln %s u.json" % u, "ln -s ~/.config/tune-up/user.json u2",
                    "exec python3 ./g trust y"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_info_exato_das_skills_passa(self):
        for cmd in ['python3 "%s" info' % SCRIPT, "python3 %s info" % SCRIPT, "python %s info" % SCRIPT]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))
        g = os.path.join(self.cwd, "g.py")
        symlink(SCRIPT, g)
        for cmd in ["python3 %s info; echo x > ~/.config/tune-up/user.json" % SCRIPT,
                    "python3 %s info x" % SCRIPT, "python3 %s trust y" % SCRIPT,
                    "python3 -I %s info" % SCRIPT, "python3 %s info > /tmp/x" % SCRIPT,
                    "python3 %s info $(echo x)" % SCRIPT, "python3 %s info" % g]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_comum_passa(self):
        for cmd in ["python3 x.py", "python3 -m unittest discover -s tests -q", "ls -la", "ln -s a b",
                    "grep -r trust docs/", "cat %s" % SCRIPT]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))


class TestB1InfoComPontoPonto(unittest.TestCase):
    def test_ponto_ponto_nao_e_info(self):
        import shutil
        import sys
        import tempfile
        from unittest import mock
        sys.path.insert(0, os.path.dirname(SCRIPT))
        import tuneup.bash_guarda as bg
        t = mkdtemp("tuneup-b1-")
        self.addCleanup(rmtree, t)
        for p in ("dev/tune-up/scripts/guarda.py", "evil/tune-up/scripts/guarda.py"):
            os.makedirs(os.path.dirname(os.path.join(t, p)), exist_ok=True)
            open(os.path.join(t, p), "w", encoding="utf-8").close()
        os.makedirs(os.path.join(t, "evil", "x"))
        symlink(os.path.join(t, "evil", "x"), os.path.join(t, "dev", "L"), True)
        t = t.replace("\\", "/")  # CLAUDE_PLUGIN_ROOT and commands use forward slashes on Windows too
        with mock.patch.object(bg, "RAIZ_PLUGIN", t + "/dev/tune-up"):
            self.assertTrue(bg.chamada_info("python3 %s/dev/tune-up/scripts/guarda.py info" % t))
            self.assertFalse(bg.chamada_info("python3 %s/dev/L/../tune-up/scripts/guarda.py info" % t))
            self.assertFalse(bg.chamada_info("python3 %s/dev/./tune-up/scripts/guarda.py info" % t))


if __name__ == "__main__":
    unittest.main()
