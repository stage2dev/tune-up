"""Tests: Bash write verbs and safety net, remote psql, and talk mode denials (security review
H2b, 21/10). Run: python3 -m unittest discover -s tests -q"""
import json
import os
import subprocess
import unittest
from base import SCRIPT, PromptBase


class TestSegVerbosDeEscrita(PromptBase):
    def test_gravam_no_perfil_perguntam(self):
        u = "~/.config/tune-up/user.json"
        absu = os.path.join(self.tmp, ".config", "tune-up", "user.json")
        for cmd in ["install -m 600 a.json " + u, "dd if=a.json of=" + u, "rsync a.json " + u,
                    "ditto a.json " + u, "perl -pi -e 's/a/b/' " + u, "curl -o %s https://e.x" % u,
                    "curl --output=%s https://e.x" % u, "curl -sSo %s https://e.x" % u,
                    "truncate -s0 " + u, "touch " + u, "cp -t ~/.config/tune-up a.json",
                    "mv -t ~/.config/tune-up a.json", "D=~/.config/tune-up; cp a.json $D/user.json",
                    "python3 -c \"open('%s','w').write('{}')\"" % absu,
                    "sed -i '' 's/a/b/' " + u, "echo x >> $HOME/.config/tune-up/user.json"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_comum_passa(self):
        for cmd in ["touch a.txt", "curl -o x.json https://e.x", "dd if=a of=b", "rsync -a src/ dst/",
                    "install -m 644 a b", "cat ~/.config/tune-up/user.json 2>/dev/null",
                    "perl -ne 'print' a.txt", "echo '{}' > u.json"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))


class TestSegPsqlRemoto(PromptBase):
    def test_perguntam(self):
        for cmd in ['psql "host=db.abc.supabase.co user=postgres dbname=postgres" -c "delete from t"',
                    'PGHOST=db.abc.supabase.co psql -c "delete from t"',
                    'export PGHOST=db.abc.supabase.co; psql -c "delete from t"',
                    'DATABASE_URL=postgres://x psql -c "delete from t"',
                    'psql service=prod -c "delete from t"',
                    'PSQL=psql; $PSQL -h db.abc.supabase.co -c "delete from t"',
                    '${PSQL} -h db.abc.supabase.co -c "delete from t"']:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_local_passa(self):
        for cmd in ['psql -h localhost -c "delete from t"', 'psql "host=localhost dbname=x" -c "select 1"',
                    'psql -c "select 1"', '$EDITOR a.txt']:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))


class TestSegConversa(PromptBase):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", self.cwd], check=True)
        os.makedirs(os.path.join(self.cwd, "docs"))
        self.sessao(modo_conversa=True, modo_pesquisa=True)

    def test_nega_no_projeto(self):
        for cmd in ["git apply x.diff", "git am x.patch", "git checkout -- src/a.py", "git restore src/a.py",
                    "patch -p1 < x.diff", "perl -i -pe 's/a/b/' x", "python3 -c 'print(1)'", "node -e 1",
                    "ruby -e 1", "python3 - < x.py", "install a /tmp/b", "dd if=a of=/tmp/b", "touch x",
                    "rsync a /tmp/b", "npm install", "pnpm add x", "yarn init", "npm init -y"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "bloquear")

    def test_passa(self):
        for cmd in ["sed -i '' 's/a/b/' docs/a.md", "sed -i -e 's/a/b/' docs/a.md", "git restore --staged x",
                    "git apply --check x.diff", "npm test", "python3 x.py"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))
        alvo = os.path.join(self.cwd, ".planning", "x.json")
        s = self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": alvo}})
        self.assertIsNone(s)

    def test_pergunta_com_frase_do_talk(self):
        for cmd in ["git commit -m x", "git push", "gh pr create --base main", "rm /x/a.md", "mv /x/a /x/b"]:
            with self.subTest(cmd=cmd):
                s = self.rodar("bash", {"tool_name": "Bash", "tool_input": {"command": cmd}})
                self.assertEqual(self.decisao(s), "perguntar")
                self.assertIn("modo conversa ativo", s["hookSpecificOutput"]["permissionDecisionReason"])

    def test_repo_dentro_de_pasta_externa(self):
        w = os.path.join(self.tmp, "w")
        r = os.path.join(w, "R")
        subprocess.run(["git", "init", "-q", r], check=True)
        for alvo, esperado in (("R/.planning/phases/1/GOAL.md", None), ("R/docs/PRD.md", None),
                               ("R/src/a.py", "bloquear")):
            with self.subTest(alvo=alvo):
                s = self.rodar("escrita", {"tool_name": "Write", "cwd": w,
                                           "tool_input": {"file_path": os.path.join(w, alvo)}})
                self.assertEqual(self.decisao(s), esperado)


class TestSegExecutoresEVerbos(PromptBase):
    """A2/A1/B3 (22/10): more executors, more write verbs, globs, and no false positive on reads."""
    def setUp(self):
        super().setUp()
        for p in (".config/tune-up/user.json", ".claude/plugins/data/t/perfis_confiaveis.txt"):
            os.makedirs(os.path.dirname(os.path.join(self.tmp, p)), exist_ok=True)
            open(os.path.join(self.tmp, p), "w").close()

    def test_executores_perguntam(self):
        for cmd in ["node -e \"require('fs').appendFileSync(process.env.CLAUDE_PLUGIN_DATA+'/perfis_confiaveis.txt','x')\"",
                    "perl -e 'open F,\">>$ENV{CLAUDE_PLUGIN_DATA}/perfis_confiaveis.txt\"; print F 1'",
                    "ruby -e 'File.write(ENV[\"CLAUDE_PLUGIN_DATA\"]+\"/perfis_confiaveis.txt\", \"x\")'"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_verbos_e_globs_perguntam(self):
        raiz = os.path.dirname(os.path.dirname(SCRIPT))
        for cmd in ["patch %s x.diff" % SCRIPT, "patch -d %s -p1 < x.diff" % raiz, "git -C %s apply x.diff" % raiz,
                    "tar -xf t.tar -C %s/scripts" % raiz, "unzip -o x.zip -d %s" % raiz,
                    "cat ~/l.txt >> ~/.cl*/plu*/data/*/p*.txt", "cp x ~/.conf?g/tune-up/user.json",
                    "cp x ~/.config/tune-*/novo.json"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_leitura_citando_raiz_passa(self):
        for cmd in ["cat ~/.config/tune-up/user.json > ~/backup.json", "ls ~/.claude/plugins > plugins.txt",
                    "grep -rn trust src | xargs sed -n 1p",
                    "curl https://api.example.com/trust/v1 | python3 -m json.tool", "python3 scripts/trust.py",
                    "patch -p1 < x.diff", "git apply x.diff", "tar -xf t.tar -C out", "unzip x.zip -d out"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))

    def test_seis_mil_alvos_sem_demora(self):
        import time
        cmd = "touch " + " ".join("/var/tmp/f%d" % i for i in range(6000)) + "; cp a ~/.config/tune-up/user.json"
        t = time.time()
        self.assertEqual(self.bash(cmd), "perguntar")
        self.assertLess(time.time() - t, 1.5)  # was ~3 s (B2); measured ~0.33 s


class TestSegConversaArvore(PromptBase):
    """M6/M2 (22/10): talk denies git and tools that rewrite the tree, without one git per target."""
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", self.cwd], check=True)
        self.sessao(modo_conversa=True, modo_pesquisa=True)

    def test_nega(self):
        for cmd in ["python3 -Ic 'x'", "node --eval=1", "node --eval 1", "perl -ne 1 x", "git pull",
                    "git merge x", "git stash pop", "git stash apply", "git checkout dev", "git switch dev",
                    "git cherry-pick a", "git revert a", "git mv a b", "git rm a", "git reset",
                    "npx prettier --write .", "npx eslint --fix src", "uv run ruff check --fix",
                    "tar -xzf p.tgz", "unzip -o p.zip", "tar -xf p.tar -C src"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "bloquear")

    def test_passa(self):
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(fora)
        for cmd in ["git status", "git checkout -b nova", "git stash list", "unzip -l p.zip", "tar -tf p.tgz",
                    "tar -xf p.tar -C %s" % fora, "git log --oneline"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))

    def test_muitos_alvos_fora_sem_git_por_alvo(self):
        b = os.path.join(self.tmp, "bin")
        os.makedirs(b)
        log = os.path.join(self.tmp, "git.chamadas")
        real = subprocess.run(["sh", "-c", "command -v git"], capture_output=True, text=True).stdout.strip()
        with open(os.path.join(b, "git"), "w") as f:
            f.write('#!/bin/sh\necho "$@" >> %s\nexec %s "$@"\n' % (log, real))
        os.chmod(os.path.join(b, "git"), 0o755)
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(fora)
        cmd = "touch " + " ".join("%s/f%d" % (fora, i) for i in range(300)) + " src/app.py"
        self.assertEqual(self.bash(cmd, {"PATH": b + os.pathsep + self.env["PATH"]}), "bloquear")
        with open(log) as f:
            self.assertLess(len(f.read().splitlines()), 10)  # was one git per target (M2)


class TestSegHooksTask(unittest.TestCase):
    def test_matcher_do_agent_pega_task(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(SCRIPT)), "hooks", "hooks.json")) as f:
            h = json.load(f)
        matchers = [m["matcher"] for ms in h["hooks"].values() for m in ms if "agent" in json.dumps(m)]
        self.assertTrue(any("Task" in m.split("|") and "Agent" in m.split("|") for m in matchers), matchers)


if __name__ == "__main__":
    unittest.main()
