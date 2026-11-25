"""Tests: trust bound to the config CONTENT and trust by indirection in Bash (security review
H2b, 21/10). Run: python3 -m unittest discover -s tests -q"""
import json
import os
import shutil
import unittest
from base import SCRIPT, PromptBase, mkdtemp, rmtree, sh_path, symlink

SCRIPT_ = SCRIPT


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
        scripts = os.path.dirname(SCRIPT_)
        g = os.path.join(self.cwd, "g")
        symlink(SCRIPT_, g)  # symlink without .py
        u = os.path.join(self.tmp, ".config", "tune-up", "user.json")
        cfg = os.path.join(self.cwd, ".tune-up", "config.json")
        SCRIPT, scripts, u, cfg = sh_path(SCRIPT_), sh_path(scripts), sh_path(u), sh_path(cfg)
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
        SCRIPT = sh_path(SCRIPT_)  # Claude passes C:/x; a backslash is refused
        for cmd in ['python3 "%s" info' % SCRIPT, "python3 %s info" % SCRIPT, "python %s info" % SCRIPT]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))
        g = os.path.join(self.cwd, "g.py")
        symlink(SCRIPT_, g)
        g = sh_path(g)
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


class TestRotaSoLeitura(PromptBase):
    """`guarda.py rota` is read-only: the Bash guard lets the exact form through and nothing else."""
    def test_rota_exata_passa_resto_pergunta(self):
        g = sh_path(SCRIPT)
        for ok in ("python3 %s rota --files migrations/001.sql src/Button.tsx" % g,
                   "python3 %s rota --files a.md --diff-file d.patch --failed sonnet" % g,
                   "python3 %s rota --failed opus --files 'a b.md'" % g, "python3 %s rota" % g,
                   "python3 %s rota --files a.md --diff-file d.patch --text-file item.rota.txt" % g,
                   "python3 %s rota --text-file '/tmp/my item.rota.txt' --failed opus" % g,
                   "python3 %s rota --text-file %s" % (g, sh_path(os.path.join(self.tmp, "x.rota.txt"))),
                   "python3 %s info" % g):
            self.assertIsNone(self.bash(ok), ok)
        for ruim in ("python3 %s rota --files a.md; touch x" % g, "python3 %s rota --files a > o" % g,
                     "python3 %s rota --files $(id)" % g, "python3 %s rota --failed haiku" % g,
                     "python3 %s rota --x" % g, "python3 %s rota --diff-file" % g,
                     "python3 %s info --files a" % g, "python3 %s trust c.json" % g,
                     "python3 %s/../scripts/guarda.py rota" % g.rsplit("/", 2)[0],
                     "python3 -c x %s rota" % g, "FOO=1 python3 %s rota" % g,
                     "python3 %s rota --text-file" % g, "python3 %s rota --text-file --files a" % g,
                     "python3 %s rota --text-file a.txt --text-file b.txt" % g,
                     "python3 %s rota --text-file $HOME/x" % g) + tuple(
                         "python3 %s rota --text-file %s" % (g, t) for t in (
                             ".env", "notes.txt", "~/x.rota.txt", "../x.rota.txt", ".ssh/x.rota.txt",
                             "{a,b}.rota.txt", "*.rota.txt", "/a/.ssh/x.rota.txt", ".rota.txt",
                             "x.rota.txt.bak", "x.rota.tx?", "[x].rota.txt")):
            self.assertIsNotNone(self.bash(ruim), ruim)


class TestRevisaoDaParte(PromptBase):
    """The part and ship skills' own guarda.py calls pass the Bash guard; anything around them asks."""
    def test_forma_exata_passa_resto_pergunta(self):
        r = sh_path(os.path.dirname(os.path.dirname(SCRIPT)))
        g = 'sh "%s/scripts/py" scripts/guarda.py ' % r
        s = sh_path(self.tmp)
        salva = g + "review-save --dir '%s' --lens failures --chunk item-B1 --round 1" % s
        pend = g + "review-pending --file '%s/my PROGRESS.md' --part B" % s
        rota = g + "rota --part --files src/A.tsx 'src/b c.tsx' --diff-file %s/d.patch" % s
        oks = [salva, salva + " --answer-file '%s/a.md'" % s, pend, g + "review-pending --file x.md", rota,
               g + "rota --files src/A.tsx --part --diff-file d.patch", "python3 %s review-pending --file x.md" % sh_path(SCRIPT)]
        copia, py = os.path.join(self.tmp, "g.py"), 'sh "%s/scripts/py" ' % r
        shutil.copy(SCRIPT, copia)
        for modo in ({}, {"modo_pesquisa": True}, {"modo_conversa": True}):
            self.sessao(**modo)
            for ok in oks:
                self.assertIsNone(self.bash(ok), (modo, ok))
        self.sessao()
        ruins = [c + x for c in (salva, pend, rota) for x in (
            "; rm x", " && rm x", " | tee x", " & rm x", " > x", " >> x", " < x", " $(id)", " `id`", "\nrm x", " trust",
            " confiar", " --trust", " <<'END'\nx\nEND")]
        ruins += [g + "trust c.json", g + "confiar c.json", g + "trust review-save", g + "review-save trust c.json",
                  g + "review-pending confiar", g + "review-pending --file trust", g + "review-save --dir /x --lens trust",
                  g + "rota --part --files trust", g + "rota --part trust", g + "rota --part --x", g + "rota --part --part=1",
                  g + "review-save --dir /x --dir /y", g + "review-save --out /x", g + "review-save --dir", g + "review-pendin",
                  g + "review-pending --file --part", g + "review-save --dir $HOME/x", g + "review-save --dir ~/x",
                  salva.replace(s, r), salva.replace(s, r + "/scripts"), "FOO=1 " + salva, "cd /tmp && " + salva,
                  py + "%s review-save --dir %s" % (sh_path(copia), s), "python3 %s trust c.json" % sh_path(copia),
                  py + "./scripts/guarda.py review-pending --file x", 'sh "%s/../%s/scripts/py" scripts/guarda.py '
                  "review-pending --file x" % (r, os.path.basename(r))]
        for ruim in ruins:
            self.assertIsNotNone(self.bash(ruim), ruim)


class TestContasMkt(PromptBase):
    """The marketing skills' `contas.py` call cites the plugin root but is not a guard write (F1)."""
    def test_comando_das_skills_passa_imitacao_pergunta(self):
        r = sh_path(os.path.dirname(os.path.dirname(SCRIPT)))
        c = 'sh "%s/scripts/py" tune-up-mkt/scripts/contas.py ' % r
        oks = [c + "status", c + "falta --json", c + "marcar composio:instagram ok --prova sessao",
               c + "config --site https://a.b --canais instagram"]
        for ok in oks:
            self.assertIsNone(self.bash(ok), ok)
        for ruim in (c + "status; rm x", c + "status && rm x", c + "falta $(id)", c + "status `id`",
                     c + "status > %s/scripts/x" % r, c + "rodar", c + "status --raiz /tmp",
                     c + "status --raiz=/tmp", c + "status {--raiz,/tmp}", c + "status --rai?=/tmp",
                     c + "status --[r]aiz=/tmp", c + "status --raiz=~", 'sh "%s/scripts/py" tune-up-mkt/scripts/outro.py status' % r,
                     'sh "%s/../%s/scripts/py" tune-up-mkt/scripts/contas.py status' % (r, os.path.basename(r)),
                     "sh /tmp/py tune-up-mkt/scripts/contas.py status %s" % r,
                     "python3 %s/tune-up-mkt/scripts/contas.py status" % r):
            self.assertIsNotNone(self.bash(ruim), ruim)
        for modo in ({"modo_pesquisa": True}, {"modo_conversa": True}):  # like any other script run
            self.sessao(**modo)
            for ok in oks:
                self.assertIsNone(self.bash(ok), (modo, ok))


if __name__ == "__main__":
    unittest.main()
