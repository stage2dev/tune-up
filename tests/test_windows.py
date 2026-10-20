"""Windows support: path normaliser, launcher scripts/py, PowerShell tool, the injected info call
and Windows path spellings. Monkeypatched tests run everywhere; real Windows checks only on nt."""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from base import SCRIPT, Base, rmtree

RAIZ = os.path.dirname(os.path.dirname(SCRIPT))
LANCADOR = os.path.join(RAIZ, "scripts", "py")
sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import bash_guarda, caminhos, config, escrita  # noqa: E402
from tuneup.bash_parse import comando_simples  # noqa: E402
from tuneup.powershell import como_bash, instrucoes, leitura  # noqa: E402

NT = os.name == "nt"
SH = shutil.which("sh")


class TestNativo(unittest.TestCase):
    """caminhos.nativo with NT forced on (pure string work: runs on any OS)."""

    def n(self, p):
        with mock.patch.object(caminhos, "NT", True), \
                mock.patch.object(caminhos, "temporarios", lambda: ["C:\\Users\\x\\AppData\\Local\\Temp"]):
            return caminhos.nativo(p)

    def test_git_bash(self):
        self.assertEqual(self.n("/c/Users/x/.claude/settings.json"), "C:/Users/x/.claude/settings.json")
        self.assertEqual(self.n("/d"), "D:/")
        self.assertEqual(self.n("/tmp/a/b"), "C:/Users/x/AppData/Local/Temp/a/b")
        self.assertEqual(self.n("/tmp"), "C:/Users/x/AppData/Local/Temp")
        self.assertEqual(self.n("/usr/bin/x"), "/usr/bin/x")  # not a drive: unchanged
        self.assertEqual(self.n("/tmpx/a"), "/tmpx/a")

    def test_prefixos_e_unc(self):
        self.assertEqual(self.n("\\\\?\\C:\\Users\\x\\settings.json"), "C:/Users/x/settings.json")
        self.assertEqual(self.n("\\\\.\\C:\\Users\\x"), "C:/Users/x")
        self.assertEqual(self.n("\\\\?\\UNC\\srv\\share\\x"), "//srv/share/x")
        self.assertEqual(self.n("\\\\localhost\\c$\\Users\\x").casefold(), "c:/users/x")
        self.assertEqual(self.n("\\\\127.0.0.1\\C$\\Users\\x"), "C:/Users/x")
        self.assertEqual(self.n("\\\\srv\\share\\x"), "//srv/share/x")  # another machine stays UNC

    def test_pontos_espacos_stream(self):
        self.assertEqual(self.n("C:\\Users\\x\\settings.json."), "C:/Users/x/settings.json")
        self.assertEqual(self.n("C:/Users/x/settings.json. . "), "C:/Users/x/settings.json")
        self.assertEqual(self.n("C:/Users/x/settings.json:evil:$DATA"), "C:/Users/x/settings.json")
        self.assertEqual(self.n("C:/Users/x/.claude./settings.json"), "C:/Users/x/.claude/settings.json")
        self.assertEqual(self.n("C:/a/../b/./c"), "C:/a/../b/./c")  # . and .. kept for normpath
        self.assertEqual(self.n("C:foo/x."), "C:foo/x")  # drive-relative stays (junta_dir resolves)
        self.assertEqual(self.n("rel/x."), "rel/x")

    def test_fora_do_windows_nada_muda(self):
        with mock.patch.object(caminhos, "NT", False):
            for p in ("/c/x", "/tmp/a", "a.", "x:y"):
                self.assertEqual(caminhos.nativo(p), p)

    def test_absoluto(self):
        with mock.patch.object(caminhos, "NT", True):
            for x in ("C:\\x", "c:/x", "\\\\srv\\s", "/x", "~/x"):
                self.assertTrue(caminhos.absoluto(x), x)
            for x in ("x/y", "C:x", ".tune-up"):
                self.assertFalse(caminhos.absoluto(x), x)
        with mock.patch.object(caminhos, "NT", False):
            self.assertFalse(caminhos.absoluto("C:\\x"))

    def test_texto_nt(self):
        with mock.patch.object(bash_guarda, "NT", True):
            nt = bash_guarda._nt
            self.assertEqual(nt("echo x > /c/users/x/.claude/settings.json."), "echo x > c:/users/x/.claude/settings.json")
            self.assertEqual(nt("d=/c/users/x/"), "d=c:/users/x/")
            self.assertEqual(nt("c:\\users\\x\\.claude\\settings.json"), "c:/users/x/.claude/settings.json")
            self.assertEqual(nt("cd .. && ls ./x"), "cd .. && ls ./x")
            self.assertEqual(nt("c:/users/x/y"), "c:/users/x/y")  # one-letter folder is not a drive


@unittest.skipUnless(SH, "no sh on PATH")
class TestLancador(unittest.TestCase):
    """scripts/py with fake interpreters on PATH (sh scripts)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tuneup-py-")
        self.addCleanup(rmtree, self.tmp)
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.bin)
        self.dados = os.path.join(self.tmp, "dados")
        self.cache = os.path.join(self.dados, "python")
        self.so_bin = self.bin  # PATH with the fakes and the few tools the launcher calls, no Python
        for t in ("mkdir", "mv", "rm", "tr"):
            origem = shutil.which(t)
            if origem:
                try:
                    os.symlink(origem, os.path.join(self.bin, t))
                except (OSError, NotImplementedError):
                    shutil.copy(origem, os.path.join(self.bin, t))

    def fake(self, nome, corpo):
        p = os.path.join(self.bin, nome)
        with open(p, "w", newline="\n") as f:
            f.write("#!/bin/sh\necho %s >> '%s/chamadas'\n%s\n" % (nome, self.tmp, corpo))
        os.chmod(p, 0o755)

    def real(self, nome):  # a working interpreter that is this Python
        self.fake(nome, 'exec "%s" "$@"' % sys.executable.replace("\\", "/"))

    def chamadas(self):
        try:
            with open(os.path.join(self.tmp, "chamadas")) as f:
                return f.read().split()
        except OSError:
            return []

    def roda(self, *args, entrada="", path=None):
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_DATA"}
        env.update(CLAUDE_PLUGIN_DATA=self.dados, PATH=path or (self.bin + os.pathsep + "/usr/bin" + os.pathsep + "/bin"))
        return subprocess.run([SH, LANCADOR] + list(args), input=entrada, capture_output=True, text=True,
                              env=env, timeout=30)

    def test_alias_falso_da_store_e_pulado(self):
        self.fake("python3", "exit 9009")  # the Windows Store alias: not Python
        self.real("python")
        r = self.roda("-c", "import sys; print(sys.stdin.read().strip()); sys.exit(5)", entrada="oi")
        self.assertEqual((r.returncode, r.stdout.strip()), (5, "oi"), r.stderr)
        with open(self.cache) as f:
            self.assertEqual(f.read(), "python\n")
        self.assertEqual(self.chamadas(), ["python3", "python", "python"])
        r = self.roda("-c", "print(1)")  # cached: no probe of python3 again
        self.assertEqual(r.stdout.strip(), "1")
        self.assertEqual(self.chamadas(), ["python3", "python", "python", "python"])

    def test_py_3_e_versao_velha(self):
        self.fake("python3", "exit 1")  # too old: the probe fails
        self.fake("python", "exit 1")
        self.fake("py", '[ "$1" = -3 ] || exit 2\nshift\nexec "%s" "$@"' % sys.executable.replace("\\", "/"))
        r = self.roda("-c", "print('via py')")
        self.assertEqual(r.stdout.strip(), "via py", r.stderr)
        with open(self.cache) as f:
            self.assertEqual(f.read(), "py -3\n")

    def test_cache_invalido_ou_sumido(self):
        self.real("python")
        os.makedirs(self.dados)
        for lixo in ("rm -rf /", "/usr/bin/evil", "python3"):  # python3 is not on this PATH
            with open(self.cache, "w") as f:
                f.write(lixo + "\n")
            r = self.roda("-c", "print(2)", path=self.so_bin)
            self.assertEqual(r.stdout.strip(), "2", (lixo, r.stderr))
            with open(self.cache) as f:
                self.assertEqual(f.read(), "python\n", lixo)

    def test_sem_python(self):
        self.fake("python3", "exit 9009")
        r = self.roda("scripts/guarda.py", "inicio", path=self.so_bin)
        self.assertEqual(r.returncode, 0)
        self.assertIn("Python 3.9", r.stderr)
        self.assertIn("hooks off", json.loads(r.stdout)["systemMessage"])
        r = self.roda("scripts/guarda.py", "bash", entrada="{}", path=self.so_bin)
        self.assertEqual((r.returncode, r.stdout), (0, ""))  # fail-open, no decision
        r = self.roda("scripts/titulo_terminal.py", path=self.so_bin)
        self.assertEqual(r.returncode, 127)
        self.assertFalse(os.path.exists(self.cache))

    def test_utf8_no_stdin_e_stdout(self):  # Claude sends UTF-8; Windows Python would use the ANSI page
        self.real("python3")
        env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PLUGIN_DATA", "PYTHONUTF8")}
        env.update(CLAUDE_PLUGIN_DATA=self.dados, PATH=self.bin + os.pathsep + "/usr/bin" + os.pathsep + "/bin")
        r = subprocess.run([SH, LANCADOR, "-c", "import sys; sys.stdout.write(sys.stdin.read()[::-1])"],
                           input="não → ok".encode("utf-8"), capture_output=True, env=env, timeout=30)
        self.assertEqual(r.stdout.decode("utf-8"), "ko → oãn", r.stderr)

    def test_caminho_relativo_a_raiz(self):
        self.real("python3")
        r = self.roda("scripts/guarda.py", "info")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("language", json.loads(r.stdout))
        r = self.roda(os.path.join(RAIZ, "scripts", "guarda.py").replace("\\", "/"), "info")
        self.assertIn("language", json.loads(r.stdout))


class TestArquivos(unittest.TestCase):
    def test_lancador_lf_e_executavel(self):
        with open(LANCADOR, "rb") as f:
            self.assertNotIn(b"\r", f.read())
        if not NT:
            self.assertTrue(os.stat(LANCADOR).st_mode & stat.S_IXUSR)
        with open(os.path.join(RAIZ, "scripts", ".gitattributes")) as f:
            self.assertIn("py text eol=lf", f.read())

    def test_hooks_usam_o_lancador(self):
        with open(os.path.join(RAIZ, "hooks", "hooks.json")) as f:
            h = json.load(f)
        for ev, grupos in h["hooks"].items():
            for g in grupos:
                for x in g["hooks"]:
                    self.assertTrue(x["command"].startswith('sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py '),
                                    x["command"])
                    if " bash" in x["command"] or "pos_bash" in x["command"]:
                        self.assertEqual(g["matcher"], "Bash|PowerShell")

    def test_skills_sem_python3_do_plugin(self):
        import glob
        for p in glob.glob(os.path.join(RAIZ, "skills", "*", "SKILL.md")) + glob.glob(os.path.join(RAIZ, "agents", "*.md")):
            with open(p, encoding="utf-8") as f:
                self.assertNotIn('python3 "${CLAUDE_PLUGIN_ROOT}', f.read(), p)


class TestParse(unittest.TestCase):
    def test_lancador_vira_python(self):
        self.assertEqual(comando_simples(["sh", "/r/scripts/py", "scripts/guarda.py", "trust", "x"]),
                         ["python", "scripts/guarda.py", "trust", "x"])
        self.assertEqual(comando_simples(["/r/scripts/py", "-c", "x"]), ["python", "-c", "x"])
        self.assertEqual(comando_simples(["py", "-3.12", "-c", "x"]), ["python", "-c", "x"])
        self.assertEqual(comando_simples(["GIT.EXE", "push"]), ["git", "push"])


class TestChamadaInfo(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp(prefix="tuneup-info-")
        self.addCleanup(rmtree, self.t)
        for p in ("dev/tune-up/scripts/guarda.py", "dev/tune-up/scripts/py", "evil/tune-up/scripts/py"):
            os.makedirs(os.path.dirname(os.path.join(self.t, p)), exist_ok=True)
            open(os.path.join(self.t, p), "w").close()
        self.r = os.path.join(self.t, "dev", "tune-up")

    def ok(self, cmd):
        with mock.patch.object(bash_guarda, "RAIZ_PLUGIN", self.r):
            return bash_guarda.chamada_info(cmd)

    def test_forma_nova(self):
        L = os.path.join(self.r, "scripts", "py")
        g = os.path.join(self.r, "scripts", "guarda.py")
        self.assertTrue(self.ok('sh "%s" scripts/guarda.py info' % L))
        self.assertTrue(self.ok("sh %s %s info" % (L, g)))
        self.assertTrue(self.ok("python3 %s info" % g))  # the older form still passes
        for ruim in ('sh "%s" scripts/guarda.py info x' % L, 'sh "%s" scripts/guarda.py trust' % L,
                     'bash "%s" scripts/guarda.py info' % L, '"%s" scripts/guarda.py info' % L,
                     'sh "%s" scripts/../scripts/guarda.py info' % L, 'sh "%s" ./scripts/guarda.py info' % L,
                     'sh "%s" scripts/other.py info' % L, 'sh "%s" scripts/guarda.py info; ls' % L,
                     'sh "%s/dev/x/../tune-up/scripts/py" scripts/guarda.py info' % self.t,
                     'sh "%s/evil/tune-up/scripts/py" scripts/guarda.py info' % self.t,
                     'sh "%s" %s/evil/tune-up/scripts/guarda.py info' % (L, self.t)):
            self.assertFalse(self.ok(ruim), ruim)

    @unittest.skipUnless(NT, "Windows spellings")
    def test_grafias_windows(self):
        L = os.path.join(self.r, "scripts", "py")
        self.assertTrue(self.ok('sh "%s" scripts/guarda.py info' % L.replace("\\", "/")))
        self.assertTrue(self.ok('sh "%s" scripts/guarda.py info' % L.replace("\\", "/").upper()))


class TestArquivoSeguroWindows(unittest.TestCase):
    def test_sem_uid_dentro_do_perfil(self):
        t = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-seg-"))
        self.addCleanup(rmtree, t)
        fora = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-fora-"))
        self.addCleanup(rmtree, fora)
        for d in (t, fora):
            open(os.path.join(d, "x"), "w").close()
        with mock.patch.object(config, "home_real", lambda: t), mock.patch.object(config.os, "name", "nt"), \
                mock.patch.object(config.os, "getuid", side_effect=AssertionError("getuid on Windows"), create=True):
            self.assertTrue(config.arquivo_seguro(os.path.join(t, "x")))
            self.assertTrue(config.arquivo_seguro(t))
            self.assertFalse(config.arquivo_seguro(os.path.join(fora, "x")))

    def test_chmod_sem_getuid(self):
        t = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-chmod-"))
        self.addCleanup(rmtree, t)
        f = os.path.join(t, "a.txt")
        open(f, "w").close()
        os.chmod(f, stat.S_IREAD)
        with mock.patch.object(escrita, "NT", True), \
                mock.patch.object(escrita.os, "getuid", side_effect=AssertionError("getuid on Windows"), create=True):
            escrita.liberar_escrita(f, t)
        self.assertTrue(os.stat(f).st_mode & stat.S_IWUSR)


class TestTituloWindows(unittest.TestCase):
    def test_pastas_do_windows(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("titulo_terminal", os.path.join(RAIZ, "scripts", "titulo_terminal.py"))
        tt = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tt)
        ap = tempfile.mkdtemp(prefix="tuneup-appdata-")
        self.addCleanup(rmtree, ap)
        nomes = ["Code", "Code - Insiders", "Cursor", "Windsurf", "VSCodium"]
        for n in nomes:
            os.makedirs(os.path.join(ap, n, "User", "globalStorage"))
        with mock.patch.object(tt.sys, "platform", "win32"), mock.patch.object(tt.os, "name", "nt"), \
                mock.patch.dict(os.environ, {"APPDATA": ap}):
            self.assertEqual(tt.bases(), [ap])
            achados = dict(tt.editores())
        self.assertEqual(sorted(achados), sorted(nomes))
        self.assertEqual(achados["Code"], os.path.join(ap, "Code", "User", "settings.json"))


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
        self.assertEqual(b("Copy-Item a -Destination b"), ["tee b"])
        self.assertEqual(b("Set-Location ~/p"), ["cd ~/p"])
        self.assertEqual(b("echo hi > out.txt 2>&1"), ["echo hi > out.txt"])
        self.assertIn("~/.claude/settings.json", b("New-Item -Path ~/.claude -Name settings.json")[0])
        self.assertIn("~/.claude/settings.json", b("Rename-Item ~/.claude/x.json -NewName settings.json")[0])
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


class TestBashLancador(Base):
    USER_JSON = {"language": "en"}

    def test_info_injetado_passa_e_trust_pergunta(self):
        L = LANCADOR.replace("\\", "/")
        self.assertIsNone(self.bash('sh "%s" scripts/guarda.py info' % L))
        self.assertEqual(self.bash('sh "%s" scripts/guarda.py info extra' % L), "perguntar")
        self.assertEqual(self.bash('sh "%s" scripts/guarda.py trust /x/config.json' % L), "perguntar")
        self.assertEqual(self.bash("py -3 guarda.py trust /x/config.json"), "perguntar")


@unittest.skipUnless(NT, "real Windows path spellings")
class TestGrafiasWindowsReais(Base):
    USER_JSON = {"language": "en"}

    def setUp(self):
        super().setUp()
        self.claude = os.path.join(self.tmp, ".claude")
        os.makedirs(self.claude)
        self.settings = os.path.join(self.claude, "settings.json")
        with open(self.settings, "w") as f:
            f.write("{}")

    def escrita(self, alvo):
        return self.decisao(self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": alvo}}))

    def test_grafias_de_settings(self):
        s = self.settings
        drive = s[0]
        gitbash = "/" + drive.lower() + s[2:].replace("\\", "/")
        for alvo in (s, s + ".", s + " ", s + ". .", s + ":evil", s + "::$DATA", "\\\\?\\" + s,
                     "\\\\localhost\\%s$%s" % (drive, s[2:]), s.replace("\\", "/"), s.upper(), gitbash,
                     os.path.join(self.claude + ".", "settings.json")):
            with self.subTest(alvo=alvo):
                self.assertEqual(self.escrita(alvo), "perguntar")
        self.assertEqual(self.bash("echo x > '%s'" % gitbash), "perguntar")
        self.assertEqual(self.bash("echo x > '%s.'" % s.replace("\\", "/")), "perguntar")

    def test_nome_curto_8_3(self):
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if not ctypes.windll.kernel32.GetShortPathNameW(self.claude, buf, 1024) or \
                os.path.basename(buf.value).lower() == ".claude":
            self.skipTest("8.3 names are off on this volume")
        self.assertEqual(self.escrita(os.path.join(buf.value, "settings.json")), "perguntar")
        self.assertEqual(self.escrita(os.path.join(buf.value, "settings.local.json")), "perguntar")  # does not exist

    def test_relativo_ao_drive(self):
        rel = self.cwd[:2] + "..\\.claude\\settings.json"  # C:..\.claude: from the cwd on that drive
        self.assertEqual(self.escrita(rel), "perguntar")

    def test_tmp_livre_em_pesquisa(self):
        self.sessao(modo_pesquisa=True)
        self.assertIsNone(self.bash("echo x > /tmp/tuneup-%s.txt" % os.getpid()))
        self.assertEqual(self.bash("echo x > '%s'" % os.path.join(self.cwd, "a.txt")), "perguntar")

    def test_chmod_tira_somente_leitura(self):
        f = os.path.join(self.tmp, "ro.txt")
        open(f, "w").close()
        os.chmod(f, stat.S_IREAD)
        escrita.liberar_escrita(f, self.tmp)
        self.assertTrue(os.access(f, os.W_OK))


if __name__ == "__main__":
    unittest.main()
