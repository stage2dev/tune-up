"""Windows support, PowerShell tool: tokenizer, Bash rewrite, read-only list and the guard's
verdicts (including review round 1 spellings). Runs on any OS."""
import os
import sys
import unittest

from base import SCRIPT, Base

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup.powershell import como_bash, instrucoes, leitura  # noqa: E402


class TestPowerShellParse(unittest.TestCase):
    def test_instrucoes(self):
        self.assertEqual(instrucoes("ls | Remove-Item -Recurse a,b"), [["ls"], ["Remove-Item", "-Recurse", "a", "b"]])
        self.assertEqual(instrucoes('& { git commit -m "a b" }'), [["git", "commit", "-m", "a b"]])
        self.assertEqual(instrucoes("g`it push"), [["git", "push"]])
        self.assertEqual(instrucoes("${env:USERPROFILE}/x # c"), [["${env:USERPROFILE}/x"]])
        self.assertEqual(instrucoes("Get-Content \"$(Remove-Item x)\""), [["Get-Content", "$(Remove-Item x)"]])
        for ruim in ('echo "abc', "x < y", "git --% push", "a <# b", "@'\nx"):
            with self.assertRaises(ValueError, msg=ruim):
                instrucoes(ruim)

    def test_como_bash(self):
        b = lambda c: [como_bash(s) for s in instrucoes(c)]  # noqa: E731
        self.assertEqual(b("Set-Content -Path $HOME/.claude/settings.json -Value x"), ["tee ~/.claude/settings.json"])
        self.assertEqual(b("Copy-Item a -Destination b"), ["cp -r -- a b"])
        self.assertEqual(b("Rename-Item d/a.txt b.txt"), ["mv -- d/a.txt d/b.txt"])
        self.assertEqual(b("Remove-Item -Recurse a,b"), ["rm -r -- a b"])
        self.assertEqual(b("Set-Location ~/p"), ["cd ~/p"])
        self.assertEqual(b("echo hi > out.txt 2>&1"), ["echo hi > out.txt"])
        self.assertIn("~/.claude/settings.json", b("New-Item -Path ~/.claude -Name settings.json")[0])
        self.assertTrue(b("iwr http://x -OutFile y")[0].endswith("; tee y"))

    def test_leitura(self):
        for c in ("Get-ChildItem -Recurse", "dir", "type a.txt", "Select-String x a.txt", "git status",
                  "git log -3", "Test-Path a", "pwd"):
            self.assertTrue(all(leitura(s) for s in instrucoes(c)), c)
        for c in ("ls > a.txt", "git -c core.fsmonitor=x status", "git diff --output=a", "Remove-Item a",
                  "git push", "ls | Remove-Item", "$x = 1"):
            self.assertFalse(all(leitura(s) for s in instrucoes(c)), c)


class TestPowerShellGuarda(Base):
    USER_JSON = {"language": "en"}

    def ps(self, cmd, env=None):
        return self.decisao(self.rodar("bash", {"tool_name": "PowerShell", "tool_input": {"command": cmd}}, env))

    def test_git_gh_e_banco(self):
        self.assertEqual(self.ps("git push origin main"), "bloquear")
        self.assertEqual(self.ps("gh pr merge 12"), "bloquear")
        self.assertEqual(self.ps("git commit -m x", {"TUNEUP_FAKE_BRANCH": "main"}), "bloquear")
        self.assertEqual(self.ps('Set-Location sub; git.exe push origin main'), "bloquear")
        self.assertEqual(self.ps('psql -h db.example.com -c "drop table x"'), "perguntar")
        self.assertIsNone(self.ps("git status; Get-ChildItem"))
        self.assertEqual(self.ps('iex "git push origin main"'), "bloquear")  # opened like eval
        self.assertEqual(self.ps('pwsh -NoProfile -Command "gh pr merge 1"'), "bloquear")
        self.assertEqual(self.ps("powershell -e ZQBjAGgAbwA="), "perguntar")  # -EncodedCommand: unreadable

    def test_arquivos_protegidos(self):
        for c in ("Set-Content -Path $HOME/.claude/settings.json -Value '{}'",
                  "Remove-Item ~/.config/tune-up/user.json",
                  "'x' | Out-File -FilePath $env:USERPROFILE/.claude/settings.local.json",
                  '[IO.File]::WriteAllText("$HOME/.claude/settings.json", "x")',
                  "echo x > ~/.claude/settings.json"):
            self.assertEqual(self.ps(c, {"USERPROFILE": self.tmp}), "perguntar", c)
        self.assertIsNone(self.ps("Get-Content ~/.claude/settings.json"))

    def test_ilegivel_pergunta(self):
        self.assertEqual(self.ps('echo "abc'), "perguntar")

    def test_conversa_e_pesquisa(self):
        for campos in ({"modo_conversa": True}, {"modo_pesquisa": True}):
            self.sessao(**campos)
            for c in ("Get-Content README.md", "git status", "ls | Select-String x", "Test-Path a"):
                self.assertIsNone(self.ps(c), (campos, c))
            for c in ("Remove-Item x.txt", "ls | Remove-Item", 'Get-Content "$(Remove-Item x)"',
                      "git -c core.fsmonitor=x status", "ls > out.txt", "npm test", "$c = 'rm'; & $c x"):
                self.assertIn(self.ps(c), ("perguntar", "bloquear"), (campos, c))

    def test_pos_bash_powershell(self):
        s = self.rodar("pos_bash", {"tool_name": "PowerShell", "tool_input": {"command": "gh pr create --fill"},
                                    "tool_response": {"stdout": "https://github.com/a/b/pull/7\n"}})
        self.assertIn("additionalContext", s["hookSpecificOutput"])


class TestRevisao1(Base):
    """Review round 1: PowerShell spellings that passed with no question (each must ask or deny)."""
    USER_JSON = {"language": "en"}

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.tmp, ".claude"))
        with open(os.path.join(self.tmp, ".claude", "settings.json"), "w") as f:
            f.write("{}")
        os.makedirs(os.path.join(self.cwd, ".tune-up"))
        os.makedirs(self.dados, exist_ok=True)

    def ps(self, cmd, branch="feat/x"):
        return self.decisao(self.rodar("bash", {"tool_name": "PowerShell", "tool_input": {"command": cmd}},
                                       {"USERPROFILE": self.tmp, "TUNEUP_FAKE_BRANCH": branch}))

    def todos(self, cmds, esperado=("perguntar", "bloquear"), branch="feat/x"):
        for c in cmds:
            with self.subTest(c=c):
                self.assertIn(self.ps(c, branch), esperado)

    def test_a1_copiar_mover_apagar_renomear(self):
        self.todos(["Copy-Item settings.json ~/.claude/", "Move-Item settings.json ~/.claude",
                    "Rename-Item ~/.claude/settings.json.bak settings.json", "Remove-Item -Recurse -Force ~/.claude",
                    "Copy-Item config.json .tune-up", "Rename-Item .tune-up/c.json config.json",
                    "Remove-Item -Recurse .tune-up", "Remove-Item -Recurse '%s'" % self.dados,
                    "Expand-Archive a.zip -DestinationPath ~/.claude", "cp settings.json ~/.claude/",
                    "copy settings.json -Destination ~/.claude", "move settings.json ~/.claude",
                    "ren ~/.claude/settings.json.bak settings.json",
                    "rni -Path ~/.claude/settings.json.bak -NewName settings.json", "rm -r ~/.claude",
                    "del -Recurse .tune-up", "rd ~/.claude -Recurse", "ri .tune-up -r", "erase .tune-up -Recurse",
                    "Copy-Item -Path config.json -Destination .tune-up -Force"])
        self.assertIsNone(self.ps("Copy-Item a.txt b.txt"))
        self.assertIsNone(self.ps("Remove-Item -Recurse build"))

    def test_a2_env_do_powershell(self):
        self.todos(["psql $env:DATABASE_URL -f m.sql", 'psql "$env:DATABASE_URL" -c "drop table x"',
                    '$env:PGHOST="db.abc.supabase.co"; psql -f m.sql', "$env:pghost = 'db.abc.supabase.co'; psql -f m.sql",
                    "Get-Content m.sql | psql $env:DATABASE_URL", "psql ${env:DATABASE_URL} -f m.sql"])
        self.assertIsNone(self.ps("psql -h localhost -c 'select 1'"))

    def test_a3_embrulhos(self):
        self.todos(['cmd /c "git add -A && git commit -m x && git push"', 'powershell "git push origin main"',
                    "powershell -NoProfile git push origin main", '"git push origin main" | bash',
                    '"git push origin main" | sh', '"git push origin main" | Invoke-Expression',
                    '"git push origin main" | iex', 'echo "git push origin main" | pwsh',
                    'cmd /c "psql %DATABASE_URL% -c ""drop table x"""', "cmd /c supabase db push",
                    "cmd.exe /K git push origin main", ". git push origin main"], branch="main")

    def test_a3_cmd_no_bash(self):
        for c in ('cmd //c "git push origin main"', "cmd /c supabase db push", 'cmd.exe /C "psql %DATABASE_URL% -f m.sql"'):
            with self.subTest(c=c):
                self.assertIn(self.bash(c, {"TUNEUP_FAKE_BRANCH": "main"}), ("perguntar", "bloquear"))

    def test_m2_extensoes(self):
        self.todos(["npx.cmd supabase db push", "npm.cmd exec supabase db push", "git.CMD push origin main"],
                   branch="main")
        self.assertEqual(self.bash("npx.cmd supabase db push"), "perguntar")

    def test_m3_join_path_e_subexpressao(self):
        self.todos(['Set-Content (Join-Path $HOME ".claude/settings.json") x',
                    "Set-Content -Path (Join-Path ~ .claude settings.json) x",
                    "Set-Content -Path (Join-Path -Path $env:USERPROFILE -ChildPath .claude\\settings.json) x",
                    'Set-Content "$($env:USERPROFILE)/.claude/settings.json" x'])


if __name__ == "__main__":
    unittest.main()
