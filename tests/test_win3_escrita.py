"""Windows Part 3, group B: null-device redirections, BOM'd user.json, `git add .\\*` and
raw-string `open(r'...', 'w')`. Monkeypatched NT runs everywhere."""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from base import IS_WIN, SCRIPT, Base, rmtree

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import escrita  # noqa: E402
from tuneup.bash_parse import comandos  # noqa: E402


def alvos(cmd, nt=False):
    with mock.patch.object(escrita, "NT", nt):
        seg, toks = comandos(cmd)[0]
        return escrita.alvos_de_escrita(seg, toks, "/proj")


class TestNulo(unittest.TestCase):
    def test_dev_null_nao_e_escrita(self):
        for cmd in ("git status 2>/dev/null", "git log >/dev/null", "ls &>/dev/null", "ls >> /dev/null"):
            with self.subTest(cmd=cmd):
                self.assertEqual(alvos(cmd), [])

    def test_null_do_bash_e_arquivo(self):  # Bash: `$null` is a variable that may be bound (fix round 1)
        for cmd in ("git status 2>$null", "git status > '$null'", 'ls &> "$null"'):
            with self.subTest(cmd=cmd):
                self.assertEqual(len(alvos(cmd)), 1)

    def test_nul_so_no_windows(self):
        for cmd in ("dir >NUL", "dir > nul", "dir 2>NUL:"):
            with self.subTest(cmd=cmd):
                self.assertEqual(alvos(cmd, nt=True), [])
                self.assertEqual(len(alvos(cmd, nt=False)), 1)  # macOS/Linux: a real file named NUL

    def test_escritas_reais_continuam(self):
        for cmd in ("echo x > /dev/nullx", "echo x > /dev/null/../x", "echo x > $nullo",
                    "echo x > $null/x", "echo x > NULx", "echo x > app.py"):
            with self.subTest(cmd=cmd):
                self.assertEqual(len(alvos(cmd, nt=True)), 1)

    def test_null_ligado_ou_no_ambiente_escreve(self):
        self.assertEqual(len(alvos("echo x > $null")), 1)
        with mock.patch.dict(os.environ, {"null": "/x"}):
            self.assertEqual(len(alvos("echo x > $null")), 1)


class TestNuloEmConversa(Base):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", self.cwd], check=True)
        self.sessao(modo_conversa=True)

    def test_leitura_com_saida_nula_fica_livre(self):
        cmds = ["git status 2>/dev/null"]
        if IS_WIN:
            cmds.append("git status >NUL")
        for cmd in cmds:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))

    def test_escrita_real_continua_bloqueada(self):
        cmds = ["echo x > app.py", "echo x > $nullo", "echo x > $null/x",
                "null=app.py; echo x > $null", "read null; echo x > $null", "echo x > ${null}",
                "git status 2>$null", "git log > '$null'", "echo hack > $null",  # fix round 1: as at the base
                "declare nu{ll,}=app.py; echo hack > $null", 'export nu""ll=app.py; echo hack > $null',
                "printf -v nu''ll %s ~/.claude/settings.json; echo '{}' > $null", ". ./vars.sh; cat x > $null"]
        if not IS_WIN:
            cmds.append("echo x > NUL")  # a real file outside Windows
        for cmd in cmds:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "bloquear")


class TestNuloNoPowerShell(Base):
    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", self.cwd], check=True)
        self.sessao(modo_conversa=True)

    def ps(self, cmd):
        return self.decisao(self.rodar("bash", {"tool_name": "PowerShell", "tool_input": {"command": cmd}}))

    def test_null_sem_aspas_e_nulo(self):
        for cmd in ("git status 2>$null", "git status *>$null", "ls > $null"):
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.ps(cmd))

    def test_null_entre_aspas_e_arquivo(self):  # a quoted name is a literal file in PowerShell
        for cmd in ("ls > '$null'", 'ls > "nul"', 'ls 2> "$null"', "ls > `$null"):
            with self.subTest(cmd=cmd):
                self.assertIn(self.ps(cmd), ("perguntar", "bloquear"))


class TestUserJsonComBom(unittest.TestCase):
    def test_protected_paths_com_bom(self):
        import tempfile
        d = tempfile.mkdtemp(prefix="tuneup-bom-")
        self.addCleanup(rmtree, d)
        p = os.path.join(d, "user.json")
        with open(p, "w", encoding="utf-8-sig") as f:  # what PowerShell 5.1 `-Encoding UTF8` writes
            json.dump({"protected_paths": ["/seg/redo"]}, f)
        with mock.patch.dict(os.environ, {"TUNEUP_USER_JSON": p}):
            self.assertEqual(escrita.caminhos_protegidos(), (["/seg/redo"], []))


class TestGitAddAmplo(Base):
    def test_barra_invertida(self):
        for cmd in ["git add '.\\*'", 'git add ".\\*"', "git add .\\*", "git add '.\\'", "git add .\\",
                    "git add ./*", "git add .*", "git add ."]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "bloquear")

    def test_arquivo_nomeado_continua_livre(self):
        for cmd in ["git add src/a.py", "git add '.\\src\\a.py'", "git add .gitignore"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))


class TestOpenRaw(unittest.TestCase):
    def py(self, codigo):
        return escrita.python_c_escreve(["python3", "-c", codigo])

    def test_prefixos(self):
        for codigo, alvo in [("open(r'C:\\x\\a.json', 'w')", "C:\\x\\a.json"), ('open(R"C:\\y", "a")', "C:\\y"),
                             ("open(rb'z', 'wb')", "z"), ("open(BR'z', 'wb')", "z"),
                             ("open(f'o', 'w')", "o"), ("open(fr'o', mode='w')", "o"),
                             ("open('x', 'w')", "x")]:
            with self.subTest(codigo=codigo):
                self.assertEqual(self.py(codigo), [alvo])

    def test_leitura_e_prefixo_invalido(self):
        for codigo in ("open(r'C:\\x')", "open(r'C:\\x', 'r')", "open(rr'x', 'w')", "open(q'x', 'w')"):
            with self.subTest(codigo=codigo):
                self.assertEqual(self.py(codigo), [])


if __name__ == "__main__":
    unittest.main()
