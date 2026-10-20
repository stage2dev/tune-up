"""Testes do guarda.py: leitura do shell no Bash (shell aninhado, chmod, heredoc, guarda no Bash, descritores). Rode: python3 -m unittest discover -s tests -q"""
import json
import os
import stat
import unittest

from base import Base, PromptBase, symlink


class TestD1Shell(Base):
    def test_compostos_e_prefixos(self):
        for cmd in ["for b in x; do git stash -u; done", "if true; then gh pr merge 1; fi",
                    "timeout 60 git stash -u", "nohup git push -f origin main",
                    'bash -c "git stash -u"', "xargs git add -A", "nice -n 5 git stash -u",
                    "while true; do git stash -u; done", "{ git stash -u; }", "! git stash -u",
                    "exec git stash -u", 'eval "git stash -u"', "sh -c 'gh pr merge 3'",
                    "timeout -s KILL 60 git stash -u"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "bloquear")

    def test_leitura_continua_livre(self):
        for cmd in ['bash -c "git status"', "timeout 5 git log", "for f in a; do echo $f; done"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))


class TestD2ChmodSeguro(Base):
    def preparar(self, **extra):
        self.raiz = os.path.join(self.tmp, "sync")
        os.makedirs(self.raiz)
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)
        cfg = {"raizes_sincronizadas": [self.raiz]}
        cfg.update(extra)
        with open(os.path.join(perfil, "config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        self.confiar(os.path.join(perfil, "config.json"))

    def arq(self, caminho):
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        open(caminho, "w", encoding="utf-8").close()
        os.chmod(caminho, 0o444)
        return caminho

    def gravavel(self, p):
        return bool(os.stat(p).st_mode & stat.S_IWUSR)

    def test_symlink_para_fora(self):
        self.preparar()
        alvo = self.arq(os.path.join(self.tmp, "fora", "alvo.txt"))
        link = os.path.join(self.raiz, "link.txt")
        symlink(alvo, link)
        self.rodar("escrita", {"tool_name": "Edit", "tool_input": {"file_path": link}})
        self.assertFalse(self.gravavel(alvo))

    def test_dir_symlink_para_fora(self):
        self.preparar()
        alvo = self.arq(os.path.join(self.tmp, "fora", "alvo.txt"))
        symlink(os.path.dirname(alvo), os.path.join(self.raiz, "d"), True)
        self.rodar("escrita", {"tool_name": "Edit",
                               "tool_input": {"file_path": os.path.join(self.raiz, "d", "alvo.txt")}})
        self.assertFalse(self.gravavel(alvo))

    def test_git_nao_muda(self):
        self.preparar()
        a = self.arq(os.path.join(self.raiz, ".git", "config"))
        self.rodar("escrita", {"tool_name": "Edit", "tool_input": {"file_path": a}})
        self.assertFalse(self.gravavel(a))

    def test_sem_chmod_quando_pergunta(self):
        self.preparar()
        self.sessao(modo_pesquisa=True)
        a = self.arq(os.path.join(self.raiz, "x.txt"))
        s = self.rodar("escrita", {"tool_name": "Edit", "tool_input": {"file_path": a}})
        self.assertEqual(self.decisao(s), "perguntar")
        self.assertFalse(self.gravavel(a))

    def test_normal_continua_liberando(self):
        self.preparar()
        a = self.arq(os.path.join(self.raiz, "x.txt"))
        self.assertIsNone(self.rodar("escrita", {"tool_name": "Edit", "tool_input": {"file_path": a}}))
        self.assertTrue(self.gravavel(a))


class TestD7HeredocFalsoGit(Base):
    def test_heredoc_entre_aspas(self):
        self.assertEqual(self.bash('git commit -m "a <<X"\ngit stash -u'), "bloquear")
        self.assertEqual(self.bash("echo $((1 <<X))\ngit stash -u"), "bloquear")
        self.assertEqual(self.bash("echo 'a <<X'\ngit stash -u"), "bloquear")

    def test_heredoc_de_verdade_continua(self):
        self.assertIsNone(self.bash("cat <<EOF\ngit stash -u\nEOF"))

    def test_git_destrutivo(self):
        for cmd in ["git stash drop", "git stash clear", "git stash drop stash@{1}",
                    "git checkout -- src/a.py", "git switch -f main", "git switch --discard-changes x"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")
        for cmd in ["git checkout feat/x", "git switch -c nova origin/main", "git stash list"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))


class TestD9GuardaNoBash(PromptBase):
    def test_pergunta(self):
        g = os.path.join(self.tmp, ".claude", "plugins", "tune-up", "scripts", "guarda.py")
        conf = os.path.join(self.dados, "perfis_confiaveis.txt")
        cfg = os.path.join(self.cwd, ".tune-up", "config.json")
        for cmd in ["python3 %s confiar x" % g, "echo x >> %s" % conf, "echo {} > %s" % cfg,
                    "tee -a %s < x" % conf, "sed -i '' s/a/b/ %s" % cfg, "cp x %s" % conf,
                    "mv %s y" % cfg, "rm -f %s" % conf, "chmod 666 %s" % conf, "ln -sf x %s" % cfg,
                    "echo x > ~/.claude/plugins/tune-up/x", "cd .tune-up && rm config.json",
                    "echo {} > ~/.claude/settings.json"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_leitura_passa(self):
        conf = os.path.join(self.dados, "perfis_confiaveis.txt")
        for cmd in ["cat %s" % conf, "grep x %s" % conf, "git -C ~/.claude/plugins log",
                    "git -C ~/.claude/plugins status"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))
        # B3 (22/10): reading the trust list into another file is not a write to it
        self.assertIsNone(self.bash("cp %s /tmp/copia" % conf))

    def test_frase_do_turno_libera(self):
        self.prompt("/tune-up:profile")
        g = os.path.join(self.tmp, ".claude", "plugins", "tune-up", "scripts", "guarda.py")
        self.assertIsNone(self.bash("python3 %s confiar x" % g))
        self.assertEqual(self.bash("echo {} > ~/.claude/settings.local.json"), "perguntar")


class TestE4DuplicacaoDeDescritor(Base):
    def test_nada(self):
        for c in ["cd ~/.claude/plugins/tune-up && python3 -m unittest discover -s tests -q 2>&1 | tail -5",
                  "git status 2>&1", "ls >&2"]:
            with self.subTest(c=c):
                self.assertIsNone(self.bash(c))

    def test_arquivo_pergunta(self):
        self.assertEqual(self.bash("echo x &> ~/.claude/plugins/a.txt"), "perguntar")


class TestH2bDonoComPorcento(Base):
    def test_owner_com_porcento_nao_derruba_decisao(self):
        for dono in ["Ana 100%", "x%sy", "a%(b)s%d"]:
            with self.subTest(dono=dono):
                self.user_json({"language": "pt-BR", "owner": dono})
                self.assertEqual(self.bash("git push --force origin main"), "bloquear")
                s = self.rodar("bash", {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}})
                self.assertEqual(self.decisao(s), "bloquear")
                self.assertIn(dono, s["hookSpecificOutput"]["permissionDecisionReason"])
                s = self.rodar("bash", {"tool_name": "Bash", "tool_input": {"command": "git merge feat/y"}},
                               {"TUNEUP_FAKE_BRANCH": "main"})
                self.assertEqual(self.decisao(s), "perguntar")
                self.assertIn(dono, s["hookSpecificOutput"]["permissionDecisionReason"])


class TestH2bCatalogo(unittest.TestCase):
    """Every msg("key", ...) in scripts/tuneup/*.py: key exists in en AND pt-BR, same %-count as args."""
    def setUp(self):
        import sys
        self.scripts = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
        if self.scripts not in sys.path:
            sys.path.insert(0, self.scripts)

    def test_chaves_e_argumentos(self):
        import ast
        import glob
        import re
        from tuneup.mensagens import CATALOG
        conta = lambda t: len(re.findall(r"%[sdr]", t.replace("%%", "")))
        vistos = 0
        for arq in sorted(glob.glob(os.path.join(self.scripts, "tuneup", "*.py"))):
            for no in ast.walk(ast.parse(open(arq, encoding="utf-8").read())):
                if not (isinstance(no, ast.Call) and isinstance(no.func, ast.Name) and no.func.id == "msg"):
                    continue
                self.assertTrue(no.args and isinstance(no.args[0], ast.Constant), "%s:%d" % (arq, no.lineno))
                chave, n = no.args[0].value, len(no.args) - 1
                vistos += 1
                for lang in ("en", "pt-BR"):
                    with self.subTest(arq=os.path.basename(arq), chave=chave, lang=lang):
                        self.assertIn(chave, CATALOG[lang])
                        self.assertEqual(conta(CATALOG[lang][chave]), n)
        self.assertGreater(vistos, 40)

    def test_chave_inexistente_devolve_a_chave(self):
        import tempfile
        from tuneup.mensagens import msg
        antes = os.environ.get("CLAUDE_PLUGIN_DATA")
        os.environ["CLAUDE_PLUGIN_DATA"] = tempfile.mkdtemp()
        try:
            self.assertEqual(msg("nao_existe_xyz", 1), "nao_existe_xyz")
        finally:
            if antes is None:
                os.environ.pop("CLAUDE_PLUGIN_DATA")
            else:
                os.environ["CLAUDE_PLUGIN_DATA"] = antes


class TestH2bConfiarNaoLiteral(Base):
    def test_perguntam(self):
        g = os.path.join(self.tmp, "x", "guarda.py")
        copia = os.path.join(self.tmp, "g2.py")
        with open(copia, "w", encoding="utf-8") as f:
            f.write("import tuneup\n# confiar|trust\n")
        for cmd in ["S=trust; python3 %s $S x" % g, "python3 %s $(printf trust) x" % g,
                    "python3 %s `printf trust` x" % g, 'python3 %s "$S" x' % g,
                    "python3 %s trust x" % copia, "python3 %s $S x" % copia]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_passam(self):
        g = os.path.join(self.tmp, "x", "guarda.py")
        outro = os.path.join(self.tmp, "outro.py")
        with open(outro, "w", encoding="utf-8") as f:
            f.write("print(1)\n")
        for cmd in ["cat %s $HOME" % g, "python3 %s $S" % outro]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))
        # spec 21/10 (indirect trust): python + guarda.py/trust in the text always asks
        for cmd in ["python3 %s info" % g, "python3 %s trust $S" % outro]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")


class TestB5EntradaMalformada(Base):
    def test_tool_input_ou_cwd_invalido_pergunta(self):
        for entrada in ({"tool_name": "Bash", "tool_input": ["git", "status"]},
                        {"tool_name": "Bash", "tool_input": "git status"},
                        {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": 7},
                        {"tool_name": "Bash", "tool_input": {"command": "ls"}, "cwd": ["/x"]}):
            with self.subTest(entrada=entrada):
                self.assertEqual(self.decisao(self.rodar("bash", entrada)), "perguntar")
        with open(os.path.join(self.dados, "erros.log"), encoding="utf-8") as f:
            self.assertIn("malformed input", f.read())


if __name__ == "__main__":
    unittest.main()
