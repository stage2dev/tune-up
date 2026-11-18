"""Windows Part 3, shell parsing: cmd/powershell run from the Bash tool, `~\\` and
$env:HOMEDRIVE$env:HOMEPATH as home, PowerShell common parameters, pipes into write cmdlets,
redirections to $null/NUL and the new read-only cmdlets, wsl/setx. Runs on any OS."""
import json
import os
import sys
import time
import unittest
from unittest import mock

from base import SCRIPT, Base

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import bash_guarda  # noqa: E402
from tuneup.bash_parse import comandos  # noqa: E402
from tuneup.powershell import abre, comando_cmd, comando_ps, como_bash, instrucoes, le, leitura, previo, traduz  # noqa: E402

SETTINGS = "~/.claude/settings.json"


class TestParse(unittest.TestCase):
    def test_17_verbos_do_cmd(self):
        self.assertEqual(comando_cmd(["/c", "del /f /q %USERPROFILE%\\.claude\\settings.json 2>nul"]).strip(),
                         "rm -r -- '$USERPROFILE/.claude/settings.json'")
        self.assertEqual(comando_cmd(["//c", "RD /S /Q x && copy /y a b"]).split(), "rm -r -- x && cp -r -- a b".split())
        self.assertEqual(comando_cmd(["/c", "ren d/a.txt b.txt & move c e"]).split(), "mv -- d/a.txt d/b.txt & mv -- c e".split())
        self.assertEqual(comando_cmd(["/c", "dir /b & echo del x"]), "dir /b & echo del x")  # no verb: unchanged
        self.assertEqual(comando_cmd(["/c", "del build.log >nul 2>&1"]).split(), "rm -r -- build.log".split())
        self.assertEqual(comando_cmd(["/c", "@if exist a rd/s/q b"]).split(), "rm -r -- b".split())
        self.assertEqual(comando_cmd(["/c", "cd /d %USERPROFILE%\\x & cd"]).split(), "cd ~/x & true".split())

    def test_17_cmd_e_powershell_no_bash(self):
        def exes(c):
            return [t[0] for _, t in comandos(c) if t]
        self.assertIn("rm", exes('cmd /c "del C:/Users/u/.claude/settings.json"'))
        self.assertIn("rm", exes("cmd.exe //C 'erase x'"))
        self.assertIn("rm", exes('powershell.exe -Command "Remove-Item x"'))
        self.assertIn("rm", exes("pwsh -c 'gci ~/.claude | Remove-Item'"))
        self.assertIn("tee", exes('pwsh -NoProfile "Set-Content y z"'))

    def test_18_til_barra_invertida(self):
        h = os.path.expanduser("~")
        with mock.patch.object(bash_guarda, "NT", True):
            t = bash_guarda.expandido("x ~\\.claude\\settings.json")
        self.assertIn(bash_guarda._nt(h.casefold()) + "/.claude/settings.json", t.replace("//", "/"))
        with mock.patch.object(bash_guarda, "NT", False):  # elsewhere `~\` is no home
            self.assertIn("~\\.claude", bash_guarda.expandido("x ~\\.claude"))

    def test_18_homedrive_homepath(self):
        for c in ("Set-Content $env:HOMEDRIVE$env:HOMEPATH/.claude/settings.json x",
                  "Set-Content ${env:HOMEDRIVE}${env:HOMEPATH}/.claude/settings.json x"):
            self.assertEqual(como_bash(instrucoes(c)[0]), "tee " + SETTINGS, c)
        self.assertEqual(como_bash(instrucoes("Set-Content $env:HOMEDRIVE/x y")[0]), "tee '$HOMEDRIVE/x'")

    def test_19_parametros_comuns(self):
        for p in ("-ErrorAction Stop", "-ea Stop", "-EA:Stop", "-ErrorVariable e", "-ev e", "-WarningAction 0",
                  "-OutVariable o", "-ov o", "-PipelineVariable p", "-ob 1", "-InformationAction Ignore"):
            c = "Copy-Item x %s %s" % (SETTINGS, p)
            self.assertEqual(como_bash(instrucoes(c)[0]), "cp -r -- x " + SETTINGS, c)
        self.assertEqual(como_bash(instrucoes("Copy-Item -ea Stop x -Destination d")[0]), "cp -r -- x d")

    def test_21_nulo_e_leitura(self):
        for c in ("git status 2>$null", "git status *>$null", "ls > $null", "ls >NUL", "ls 2>/dev/null",
                  "git log | Out-Null", "Get-ChildItem | Select-Object -First 3", "ls | Sort-Object Name | Format-Table",
                  "gci | ? { $_.Length -gt 1 } | measure", "ls | where Name -like x | fl", "dir | select Name | ft"):
            st = instrucoes(c)
            self.assertTrue(all(leitura(s) for s in st), c)
            self.assertNotIn("tee", " ".join(map(como_bash, st)), c)
            self.assertNotIn(">", " ".join(map(como_bash, st)), c)
        for c in ("ls > out.txt", "Select-Object -First 3 > o.txt", "gci -OutVariable v", "gci -ov v",
                  "gci | % { Remove-Item $_ }", "ls | ? { Remove-Item x }", "git status 2>$nullx",
                  "Remove-Item -in x", "gci | ? { $_.Delete() -gt 1 }", "gci | ? { $_ -eq (Remove-Item x) }"):
            self.assertFalse(all(leitura(s) for s in instrucoes(c)), c)

    def test_23_wsl_setx(self):
        for c in ("wsl tuneup trust", "wsl.exe -e confiar", "C:/Windows/System32/wsl.exe x", "setx A b"):
            with mock.patch.object(bash_guarda, "NT", True):
                self.assertTrue(bash_guarda.executor(c.casefold()), c)
            with mock.patch.object(bash_guarda, "NT", False):
                self.assertFalse(bash_guarda.executor(c.casefold()), c)


class TestGuarda(Base):
    USER_JSON = {"language": "en"}

    def setUp(self):
        super().setUp()
        os.makedirs(os.path.join(self.tmp, ".claude"))
        with open(os.path.join(self.tmp, ".claude", "settings.json"), "w") as f:
            f.write("{}")
        os.makedirs(os.path.join(self.cwd, ".tune-up"))

    def ps(self, cmd):
        return self.decisao(self.rodar("bash", {"tool_name": "PowerShell", "tool_input": {"command": cmd}}))

    def todos(self, f, cmds, esperado=("perguntar", "bloquear")):
        for c in cmds:
            with self.subTest(c=c):
                self.assertIn(f(c), esperado)

    def nada(self, f, cmds):
        for c in cmds:
            with self.subTest(c=c):
                self.assertIsNone(f(c))

    def test_17_bash_abre_cmd_e_powershell(self):
        self.todos(self.bash, ['cmd /c "del %s"' % SETTINGS, 'cmd /c "del %USERPROFILE%/.claude/settings.json"',
                               "cmd.exe //c 'ERASE /F %s'" % SETTINGS, 'CMD /C "rd /s /q .tune-up"',
                               'cmd /c "copy x %s"' % SETTINGS, 'cmd /c "move settings.json ~/.claude/"',
                               'cmd /c "ren ~/.claude/settings.json.bak settings.json"',
                               'cmd /c "del %USERPROFILE%\\.claude\\settings.json"',
                               "powershell -Command \"Remove-Item %s\"" % SETTINGS,
                               "powershell.exe -NoProfile -c 'Set-Content -Path %s -Value x'" % SETTINGS,
                               "pwsh -c 'gci ~/.claude | Remove-Item'", "PWSH.EXE Remove-Item -Recurse .tune-up",
                               "pwsh -c '[IO.File]::WriteAllText(\"$HOME/.claude/settings.json\", \"x\")'"])
        self.nada(self.bash, ['cmd /c "dir /b"', 'cmd /c "del build.log"', "pwsh -c 'Get-ChildItem | Select-Object -First 3'",
                              "powershell -c \"Get-Content %s\"" % SETTINGS])
        self.assertEqual(self.bash('cmd /c "del %s"' % SETTINGS),
                         self.ps('cmd /c "del %s"' % SETTINGS))  # same verdict in both tools

    def test_18_homedrive_homepath(self):
        self.todos(self.ps, ["Set-Content $env:HOMEDRIVE$env:HOMEPATH/.claude/settings.json x",
                             "Remove-Item ${env:HOMEDRIVE}${env:HOMEPATH}/.claude/settings.json",
                             '[IO.File]::WriteAllText("$env:HOMEDRIVE$env:HOMEPATH/.claude/settings.json", "x")'])

    def test_19_parametros_comuns(self):
        self.todos(self.ps, ["Copy-Item x %s -ErrorAction Stop" % SETTINGS, "Copy-Item x %s -ea Stop" % SETTINGS,
                             "Move-Item x %s -ErrorVariable e" % SETTINGS, "cp x %s -EA:SilentlyContinue" % SETTINGS,
                             "Copy-Item config.json .tune-up -OutVariable o"])
        self.nada(self.ps, ["Copy-Item a.txt b.txt -ErrorAction Stop", "Copy-Item a.txt b.txt -ev e"])

    def test_20_pipe_para_escrita(self):
        self.todos(self.ps, ["gci ~/.claude -Recurse | Remove-Item", "Get-ChildItem .tune-up | Remove-Item -Recurse -Force",
                             "'%s' | Remove-Item" % SETTINGS, "gci ~/.claude | % { Remove-Item $_.FullName }",
                             "(gci ~/.claude) | ri", "ls ~/.claude | Sort-Object Name | del",
                             "gci ~/.claude -Filter *.json | Set-Content -Value x",
                             "gci ~/.claude | ForEach-Object { Remove-Item -LiteralPath $PSItem }",
                             "Get-Item %s | Move-Item -Destination x" % SETTINGS])
        self.nada(self.ps, ["gci build | Remove-Item", "Get-Content a.txt | Set-Content b.txt",
                            "Get-Content %s | Set-Content b.txt" % SETTINGS])

    def test_21_modos(self):
        for campos in ({"modo_conversa": True}, {"modo_pesquisa": True}):
            self.sessao(**campos)
            self.nada(self.ps, ["git status 2>$null", "git status *>$null", "ls >NUL", "ls > $null", "git log | Out-Null",
                                "Get-ChildItem | Select-Object -First 3", "ls | Sort-Object Name | Format-Table",
                                "gci | ? { $_.Length -gt 1 } | measure"])
            self.todos(self.ps, ["ls > out.txt", "Select-Object -First 3 > o.txt", "gci | % { Remove-Item $_ }",
                                 "ls | Where-Object { Remove-Item x }", "Invoke-WebRequest u -OutFile f | Out-Null"])

    def test_bash_ilegivel_pergunta(self):
        for c in ("powershell -EncodedCommand ZQBjAGgAbwA=", "pwsh -enc ZQBjAGgAbwA=", "pwsh -c 'echo \"abc'",
                  "powershell -c \"@'\nx\"", "pwsh -c 'git --% push'"):
            with self.subTest(c=c):
                s = self.rodar("bash", {"tool_name": "Bash", "tool_input": {"command": c}})
                self.assertEqual(self.decisao(s), "perguntar")
                motivo = s["hookSpecificOutput"]["permissionDecisionReason"]
                self.assertIn("could not read this PowerShell command", motivo)  # ps_ilegivel, as the PowerShell tool

    def test_bash_modos_como_powershell(self):
        for campos in ({"modo_conversa": True}, {"modo_pesquisa": True}):
            self.sessao(**campos)
            self.todos(self.bash, ['pwsh -c "Set-Content notes.txt x"', "powershell -Command 'ls > out.txt'",
                                   "PowerShell.exe New-Item n.txt", 'cmd /c "echo x"', "pwsh -c 'gci | % { $_.Delete() }'"])
            self.nada(self.bash, ['pwsh -c "git status 2>$null"', 'powershell -Command "Get-ChildItem | Select-Object -First 3"',
                                  "pwsh -c 'gci | ? { $_.Length -gt 1 } | measure'", "git status", "ls"])

    def test_23_wsl_setx(self):
        if os.name == "nt":
            self.todos(self.bash, ["wsl tuneup trust", "wsl.exe -e confiar x", "setx TUNEUP trust"])
        self.nada(self.bash, ["wsl ls", "setx PATH x"])
        if os.name != "nt":  # on Windows `wsl` is an executor word, so the text rule asks (same as `node`)
            self.nada(self.bash, ['git commit -m "wsl support for tuneup"'])

    def modo(self, f, cmds, campos=({"modo_conversa": True}, {"modo_pesquisa": True})):
        for c in campos:
            self.sessao(**c)
            self.todos(f, cmds)

    def test_r1_chamada_e_ponto_nao_sao_leitura(self):  # fix 1
        cmds = ["gci deploy.ps1 | ? { & $_ -eq 1 }", "gci *.ps1 | Where-Object { . $_.FullName -like x }",
                '& $env:ComSpec -eq "/c del x"', "$x -eq 1"]
        self.modo(self.ps, cmds)
        self.modo(self.bash, ["pwsh -c '%s'" % c.replace("'", "") for c in cmds[:2]])
        self.sessao(modo_pesquisa=True)
        self.nada(self.ps, ["gci | ? { $_.Length -gt 1 } | measure", "gci | Where-Object -FilterScript { $_.Name -like x }"])

    def test_r1_sort_com_saida(self):  # fix 2
        self.todos(self.ps, ["sort.exe /o %s in.txt" % SETTINGS, "sort.exe /output %s in.txt" % SETTINGS,
                             "C:\\Windows\\System32\\sort.exe /o %s in.txt" % SETTINGS,
                             "Get-Content in.txt | sort.exe /o %s" % SETTINGS,
                             "Get-Content x.txt | sort.exe /o .tune-up/config.json"])
        self.modo(self.ps, ["sort -o app.py x.txt", "sort.exe x.txt", "gci | sort.exe"], ({"modo_pesquisa": True},))
        self.sessao(modo_pesquisa=True)
        self.nada(self.ps, ["ls | Sort-Object Name | Format-Table", "ls | sort Name"])

    def test_r1_nulo_entre_aspas_no_powershell(self):  # fix 3
        self.modo(self.ps, ["ls > '$null'", 'ls > "nul"', "ls > 'NUL:'"], ({"modo_conversa": True},))

    def test_r1_cmd_verbos_e_cd(self):  # fix 4
        h = self.tmp.replace("\\", "/")
        cmds = ['cmd /c "cd /d %s/.claude && del settings.json"' % h, 'cmd /c "pushd %s/.claude & del /q settings.json"' % h,
                'cmd /c "cd /d %USERPROFILE%/.claude && del settings.json"', 'cmd //c "if exist .tune-up rd /s /q .tune-up"',
                'cmd //c "rd/s/q .tune-up"', 'cmd //c "@rd /s /q .tune-up"', 'cmd //c "for /d %d in (.tune-up) do rd /s /q %d"',
                'cmd /c "echo x > %HOMEDRIVE%%HOMEPATH%\\.claude\\settings.json"', 'cmd /c "chdir .tune-up & del config.json"',
                'cmd /c "if not exist x del /q .tune-up\\config.json"', 'cmd /c "if errorlevel 1 erase/q .tune-up\\config.json"',
                'cmd /c "if foo del %s"' % SETTINGS, 'cmd /c "if /i a == b del %s"' % SETTINGS]
        self.todos(self.bash, cmds)
        self.todos(self.ps, cmds)
        self.nada(self.bash, ['cmd /c "del build.log >nul 2>&1"', 'cmd /c "cd /d build && del x.log"'])

    def test_r1_pipe_para_copy(self):  # fix 5
        self.todos(self.ps, ["gci evil -Filter settings.json | Copy-Item -Destination ~/.claude",
                             "'evil/settings.json' | Copy-Item -Destination ~/.claude",
                             "gci evil | cpi -Destination ~/.claude -Recurse"])

    def test_r1_pipe_para_metodo(self):  # fix 6
        self.todos(self.ps, ["gci ~/.claude -Filter settings.json | % Delete",
                             "gci ~/.claude -Filter settings.json | % { $_.Delete() }",
                             "gci ~/.claude -Filter settings.json | ForEach-Object -MemberName Delete"])

    def test_r1_parametros_comuns_novos(self):  # fix 7
        self.todos(self.ps, ["Set-Location ~/.claude; Copy-Item x settings.json -infa 0",
                             "Set-Location ~/.claude; Copy-Item x settings.json -ProgressAction 0",
                             "Set-Location ~/.claude; Copy-Item x settings.json -proga 0"])

    def test_r1_pwsh_working_directory(self):  # fix 8
        cmds = ['pwsh -wd ~/.claude -c "Remove-Item settings.json"',
                'pwsh -WorkingDirectory ~/.claude -Command "Set-Content settings.json x"']
        self.todos(self.bash, cmds)
        self.todos(self.ps, cmds)

    def test_r1_cd_do_wrapper_nao_vaza(self):  # fix 10
        scratch = os.path.join(self.tmp, "scratch")
        os.makedirs(scratch)
        self.sessao(modo_conversa=True)  # `rm app.py` runs in the project: denied, not only asked
        for c in ('pwsh -c "cd %s"; rm app.py', 'cmd /c "cd /d %s"; rm app.py', 'powershell "Set-Location %s"; rm app.py'):
            with self.subTest(c=c):
                s = self.rodar("bash", {"tool_name": "Bash", "scratchpad_dir": scratch,
                                        "tool_input": {"command": c % scratch.replace("\\", "/")}})
                self.assertEqual(self.decisao(s), "bloquear")

    def test_r1_rotulo_sem_controle(self):  # fix 11
        for campos in ({"modo_conversa": True}, {"modo_pesquisa": True}):
            self.sessao(**campos)
            for f, c in ((self.bash, 'cmd /c "dir"'), (self.bash, 'cmd /c "echo x"'), (self.bash, "pwsh -c 'gci | % { $_.Delete() }'"),
                         ("PowerShell", 'cmd /c "dir"'), (self.bash, 'pwsh -c "New-Item %s/x -Value --fix"' % self.tmp)):
                with self.subTest(c=c, campos=campos):
                    s = self.rodar("bash", {"tool_name": f if f == "PowerShell" else "Bash", "tool_input": {"command": c}})
                    motivo = s["hookSpecificOutput"]["permissionDecisionReason"]
                    self.assertNotIn("\x00", motivo)

    def test_r2_prefixo_sem_recursao(self):  # round 2, fix 1
        self.todos(self.ps, [". " * 1100 + "; Remove-Item %s" % SETTINGS, "& " * 1100 + "; Remove-Item %s" % SETTINGS])
        self.todos(self.bash, ["pwsh -c '%s'; rm %s" % (". " * 1100, SETTINGS)])

    def test_r2_pipe_longo_pergunta_rapido(self):  # round 2, fix 2
        longo = "gci ~/.claude" + " | % y" * 1500 + "; Remove-Item %s" % SETTINGS
        self.todos(self.ps, [longo])
        self.todos(self.bash, ["pwsh -c '%s'" % longo])

    def test_r2_metodo_no_filtro(self):  # round 2, fix 3
        cmds = ["gci ~/.claude -Filter settings.json | ? { $_ -eq $_.Delete() }", "Where-Object { $_.Name -eq $_.Delete() }",
                "? -FilterScript { $_.Length -gt $_.Delete() }", "? { $_.Length -gt 1 -or $_.Length -gt $_.Delete() }",
                "gci deploy.ps1 | ? { $_ -eq $_.Encrypt() }", "gci | ? { $_ -eq $(Remove-Item x) }",
                "gci | ? { $_ -eq @(1) }"]
        self.modo(self.ps, cmds)
        self.modo(self.bash, ["pwsh -c 'gci | ? { $_ -eq $_.Delete() }'"])
        self.sessao(modo_pesquisa=True)
        self.nada(self.ps, ["gci | ? { $_.Length -gt 1 } | measure"])

    def test_r2_chaves_do_pwsh(self):  # round 2, fix 4
        b64 = "ZQBjAGgAbwA="
        self.todos(self.bash, ["pwsh --enc " + b64, "pwsh /enc " + b64, "powershell /EncodedCommand " + b64,
                               'pwsh --wd ~/.claude --command "Remove-Item settings.json"',
                               'pwsh /wd ~/.claude /c "Remove-Item settings.json"'])
        self.todos(self.ps, ["pwsh --EncodedCommand " + b64, "powershell.exe /e " + b64,
                             "pwsh --WorkingDirectory ~/.claude --c 'Remove-Item settings.json'"])

    def test_r2_cifrao_aspas_sem_escopo(self):  # round 2, fix 5
        self.todos(self.bash, ["cmd /c $'\\'' ; cd ~/.claude ; echo \\' ; rm settings.json",
                               "pwsh -c $'\\'' ; cd ~/.claude ; echo \\' ; rm settings.json"])

    def test_r2_nul(self):  # round 2, fix 6
        self.todos(self.bash, ["\x00escopo +; cd ~/.claude; \x00escopo -; rm settings.json",
                               "\x00bash; rm %s" % SETTINGS])
        for c in ("\x00bash; Remove-Item %s" % SETTINGS, "ls \x00> x"):
            with self.subTest(c=c):
                s = self.rodar("bash", {"tool_name": "PowerShell", "tool_input": {"command": c}})
                self.assertEqual(self.decisao(s), "perguntar")
                self.assertIn("could not read this PowerShell command", s["hookSpecificOutput"]["permissionDecisionReason"])

    def test_r2_cmd_verbo_escondido(self):  # round 2, fix 7
        h = self.tmp.replace("\\", "/")
        cmds = ['cmd /c "cd %s/.claude & del settings.json \'x"' % h, 'cmd /c "cd %s/.claude & call del settings.json"' % h,
                'cmd /c "cd %s/.claude & start /b del settings.json"' % h,
                'cmd /c "cd %s/.claude & start \\"t\\" del settings.json"' % h,
                'cmd /c "cd %s/.claude & %%COMSPEC%% /c del settings.json"' % h,
                'cmd /c "cd %s/.claude & cmd /c del settings.json"' % h,
                'cmd /c "cd %s & cd.claude & del settings.json"' % h, 'cmd /c "cd %s/.claude/sub & cd.. & del settings.json"' % h,
                'cmd /c "xcopy evil\\settings.json %USERPROFILE%\\.claude"', 'cmd /c "xcopy /y evil\\settings.json %s/.claude"' % h,
                'cmd /c "robocopy evil %USERPROFILE%\\.claude settings.json /mir"', 'cmd /c "robocopy evil %s/.claude"' % h,
                'cmd /c "xcopy /e evil %USERPROFILE%\\.claude"',
                'cmd /c "replace evil\\settings.json %USERPROFILE%\\.claude"']
        if h.startswith("/"):  # `cd/x` is a cd in cmd; `cdC:/x` (a drive letter) is no command at all
            cmds.append('cmd /c "cd%s/.claude & del settings.json"' % h)
        self.todos(self.bash, cmds)
        self.todos(self.ps, cmds)
        self.nada(self.bash, ['cmd /c "echo hi"', "cmd /c dir", "cmd /c ver", 'cmd /c "echo del x"', 'cmd /c "xcopy a b /y"'])

    def test_r2_regressao_no_bash(self):  # round 2: these stay allowed in code mode
        self.nada(self.bash, ['git commit -m "fix sort and cmd call"', "sort -o out.txt in.txt", "echo $'a\\nb'",
                              "cmd /c dir", "ls | sort", "cd a && make"])


    def test_r3_new_item_alias_type(self):  # round 3, group 1: -Type is -ItemType
        self.todos(self.ps, ["New-Item -Type Junction -Path x -Value $HOME/.claude",
                             "ni x -Type SymbolicLink -Value $HOME/.claude", "ni x -ty HardLink -Value " + SETTINGS])
        self.nada(self.ps, ["New-Item -Type File -Path x", "ni -Type Directory build"])

    def test_r3_cmd_chaves_e_variaveis(self):  # round 3, group 2
        cmds = ['cmd /c "del %UserProfile%\\.claude\\settings.json"', 'cmd /r "del %USERPROFILE%/.claude/settings.json"',
                "cmd /cdel %USERPROFILE%/.claude/settings.json", 'cmd /c"del %USERPROFILE%/.claude/settings.json"',
                'cmd /q/c "del %USERPROFILE%/.claude/settings.json"', 'cmd /v:on /c "del %USERPROFILE%/.claude/settings.json"',
                'cmd /c "set X=%USERPROFILE%\\.claude& del %X%\\settings.json"', 'cmd /c "set x=1& echo %X%"',
                'cmd /v:on /c "set X=%USERPROFILE%\\.claude& del !X!\\settings.json"', "cmd foo /c dir",
                'cmd /c "start /b cmd /cdel %USERPROFILE%/.claude/settings.json"']
        self.todos(self.bash, cmds)
        self.todos(self.ps, cmds + ["cmd /cdel %USERPROFILE%\\.claude\\settings.json"])
        self.nada(self.bash, ['cmd /q /c "dir /b"', "cmd /cdir", 'cmd /c "del build.log"', "cmd /q"])

    def test_r3_subexpressao_metodo_foreach(self):  # round 3, group 3
        self.todos(self.ps, ["Set-Content (gci \"$HOME/.claude/settings.json\").FullName '{}'",
                             "(dir $HOME/.claude/settings.json).Delete()", "(gi .tune-up).MoveTo('x')",
                             "Remove-Item (gci .tune-up) -Recurse", "Remove-Item $(gci .tune-up/config.json)",
                             "Copy-Item C:/t/evil.json (dir \"$HOME/.claude/settings.json\")",
                             "gci $HOME/.claude | % Delete", "gci $HOME/.claude -Filter s*.json | % Delete",
                             "gci .tune-up | % { $_.Delete() }", "gci .tune-up | ForEach-Object -MemberName Delete"])
        self.nada(self.ps, ["gci | % Name", "gci .tune-up | % FullName", "gci .tune-up | % { $_.FullName } | sort",
                            "(gci).Count", "(Get-Date).ToString()", "Set-Content x -Value (Get-Date)",
                            "Set-Content x (Get-Date)"])

    def test_r3_alvo_variavel(self):  # round 3, group 4
        cmds = ["$d = \"$HOME/.claude\"; Set-Content \"$d/settings.json\" '{}'", "Remove-Item $x",
                "$f = gci $HOME/.claude -Filter settings.json; Set-Content $f.FullName '{}'",
                "Set-Content \"$([Environment]::GetFolderPath('UserProfile'))/.claude/settings.json\" '{}'",
                "Set-Content ([IO.Path]::Combine($HOME,'.claude','settings.json')) '{}'", "if (1) { Remove-Item $x }",
                "Set-Content -Value (Get-Date) -Path $x", "New-Item -ItemType Junction -Path x -Value $t",
                "$files | Remove-Item"]
        self.todos(self.ps, cmds)
        self.todos(self.bash, ["pwsh -c 'Remove-Item $x'"])
        saida = self.rodar("bash", {"tool_name": "PowerShell", "tool_input": {"command": "Remove-Item $x"}})
        self.assertIn("variable or expression", json.dumps(saida))
        self.nada(self.ps, ["git status 2>$null", "Get-ChildItem | Select-Object -First 3", "$x = 1; Write-Output $x",
                            "Set-Content out.txt x", "Set-Content \"$env:TEMP/x.txt\" x", "Set-Content o.txt $x",
                            "gci *.log | % { Remove-Item $_ }", "Remove-Item $HOME/tmp/x.log", "Remove-Item ${env:TEMP}/x"])

class TestR2Parse(unittest.TestCase):
    def test_prefixo_em_laco(self):  # fix 1
        self.assertEqual(como_bash(["."] * 1100 + ["x"]), "x")
        self.assertEqual(como_bash(["&"] * 1100), "")

    def test_pipe_longo_rapido(self):  # fix 2
        for n, erro in ((1500, True), (290, False)):
            texto = "gci ~/.claude" + " | % y" * n + "; Remove-Item %s" % SETTINGS
            t0 = time.time()
            try:
                traduz(abre(le(previo(texto))))
                lido = True
            except ValueError:
                lido = False
            self.assertLess(time.time() - t0, 3.0, n)
            self.assertEqual(lido, not erro, n)

    def test_metodo_no_filtro(self):  # fix 3
        for c in ("gci | ? { $_ -eq $_.Delete() }", "gci | ? { $_.Length -gt 1 -or $_.Length -gt $_.Delete() }"):
            self.assertFalse(all(leitura(s) for s in instrucoes(c)), c)
        self.assertTrue(all(leitura(s) for s in instrucoes("gci | ? { $_.Length -gt 1 } | measure")))

    def test_chaves_do_pwsh(self):  # fix 4
        self.assertEqual(comando_ps(["pwsh", "--command", "x"]), "x")
        self.assertEqual(comando_ps(["pwsh", "/c", "x"]), "x")
        self.assertEqual(comando_ps(["pwsh", "/usr/local/x.ps1"]), "/usr/local/x.ps1")  # a path, not a switch
        for s in (["pwsh", "--enc", "x"], ["pwsh", "/e", "x"], ["pwsh", "/bogus", "x"]):
            self.assertRaises(ValueError, comando_ps, s)

    def test_nul_sem_indexerror(self):  # fix 6
        self.assertEqual(como_bash(["\x00bash"]), "")

    def test_cmd_verbos(self):  # fix 7
        self.assertEqual(comando_cmd(["/c", "call del x"]).split(), "rm -r -- x".split())
        self.assertEqual(comando_cmd(["/c", "start /b /wait del x"]).split(), "rm -r -- x".split())
        self.assertEqual(comando_cmd(["/c", "%COMSPEC% /c del x"]).split(), "rm -r -- x".split())
        self.assertEqual(comando_cmd(["/c", "cd..&del x"]).split(), "cd .. & rm -r -- x".split())
        self.assertEqual(comando_cmd(["/c", "robocopy src dst a.txt /mir /mt:8"]).split(), "cp -r -- src/a.txt dst".split())
        self.assertEqual(comando_cmd(["/c", "xcopy /e /i a b >nul"]).split(), "cp -r -- a 'a/*' b".split())
        for x in ("del x 'y", "echo x & cmd/c del x", "cd/d x", "if foo del x", "robocopy src"):
            self.assertRaises(ValueError, comando_cmd, ["/c", x])


class TestExecutorSoNoWindows(unittest.TestCase):  # fix 9
    def nivel(self, cmd):
        seg, toks = comandos(cmd)[0]
        e, links, w = bash_guarda.citacoes(seg, toks, "/proj", [])
        return bash_guarda.nivel_do_texto(e, links, "/proj", w)

    def test_wsl_setx(self):
        with mock.patch.object(bash_guarda, "NT", True):
            for c in ("wsl tuneup trust", "wsl.exe -e confiar x", "C:/Windows/System32/wsl.exe tuneup", "setx TUNEUP trust"):
                self.assertEqual(self.nivel(c), "turno", c)
            self.assertIsNone(self.nivel("wsl ls"))
        with mock.patch.object(bash_guarda, "NT", False):
            for c in ("wsl tuneup trust", 'git commit -m "wsl support for tuneup"', "setx TUNEUP trust"):
                self.assertIsNone(self.nivel(c), c)


if __name__ == "__main__":
    unittest.main()
