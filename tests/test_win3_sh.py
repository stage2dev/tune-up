"""Git Bash warning (gitbash.sem_git_bash, SessionStart line, docs) and gravar_sessao retry on PermissionError."""
import ast
import importlib.util
import os
import sys
import tempfile
import unittest
from unittest import mock

from base import SCRIPT, rmtree

RAIZ = os.path.dirname(os.path.dirname(SCRIPT))
sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import sessao, usuario  # noqa: E402
from tuneup.gitbash import sem_git_bash  # noqa: E402


def sem(which=None, env=None, files=(), nt=True):
    which = which or {}
    return sem_git_bash(nt=nt, which=which.get, env=env or {}, isfile=lambda p: p in files)


class TestGitBash(unittest.TestCase):
    def test_nao_windows_nunca_avisa(self):
        self.assertFalse(sem(nt=False))

    def test_windows_sem_nada_avisa(self):
        self.assertTrue(sem())

    def test_sh_no_path_ok(self):
        self.assertFalse(sem({"sh": "C:\\Program Files\\Git\\usr\\bin\\sh.exe"}))

    def test_bash_do_wsl_nao_conta(self):
        self.assertTrue(sem({"bash": "C:\\Windows\\System32\\bash.exe"}))
        self.assertTrue(sem({"bash": "C:\\Users\\x\\AppData\\Local\\Microsoft\\WindowsApps\\bash.exe"}))

    def test_variavel_precisa_apontar_para_arquivo(self):
        env = {"CLAUDE_CODE_GIT_BASH_PATH": "D:\\Git\\bin\\bash.exe"}
        self.assertTrue(sem(env=env))
        self.assertFalse(sem(env=env, files={"D:\\Git\\bin\\bash.exe"}))

    def test_local_padrao(self):
        env = {"ProgramFiles": "C:\\Program Files"}
        self.assertFalse(sem(env=env, files={"C:\\Program Files\\Git\\bin\\bash.exe"}))


# (name, which, env, files, expected "sem git bash")
CASOS = [
    ("nada", {}, {}, (), True),
    ("git_cmd_no_path", {"git": "C:\\Program Files (x86)\\Git\\cmd\\git.exe"}, {},
     ("C:\\Program Files (x86)\\Git\\bin\\bash.exe",), False),
    ("git_em_D", {"git": "D:\\Tools\\Git\\cmd\\git.exe"}, {}, ("D:\\Tools\\Git\\bin\\bash.exe",), False),
    ("git_portatil_barras", {"git": "E:/PortableGit/cmd/git.exe"}, {}, ("E:\\PortableGit\\usr\\bin\\bash.exe",), False),
    ("scoop", {"git": "C:\\Users\\x\\scoop\\apps\\git\\current\\cmd\\git.exe"}, {},
     ("C:\\Users\\x\\scoop\\apps\\git\\current\\bin\\bash.exe",), False),
    ("git_sem_bash", {"git": "D:\\Tools\\Git\\cmd\\git.exe"}, {}, (), True),
    ("programfiles", {}, {"ProgramFiles": "C:\\Program Files"}, ("C:\\Program Files\\Git\\bin\\bash.exe",), False),
    ("programw6432", {}, {"ProgramW6432": "C:\\Program Files"}, ("C:\\Program Files\\Git\\usr\\bin\\sh.exe",), False),
    ("programfiles_x86", {}, {"ProgramFiles(x86)": "C:\\Program Files (x86)"},
     ("C:\\Program Files (x86)\\Git\\bin\\bash.exe",), False),
    ("localappdata", {}, {"LocalAppData": "C:\\Users\\x\\AppData\\Local"},
     ("C:\\Users\\x\\AppData\\Local\\Programs\\Git\\bin\\bash.exe",), False),
    ("sh_do_wsl", {"bash": "C:\\Windows\\System32\\bash.exe"}, {}, (), True),
    ("bash_windowsapps", {"bash": "C:\\Users\\x\\AppData\\Local\\Microsoft\\WindowsApps\\bash.exe"}, {}, (), True),
    ("git_relativo", {"git": "git.exe"}, {}, ("bin\\bash.exe",), True),  # no root from a relative git
    ("git_relativo_ponto", {"git": ".\\git.exe"}, {}, ("bin\\bash.exe", ".\\bin\\bash.exe"), True),
]


def painel_func():
    spec = importlib.util.spec_from_file_location("aviso_sh_copia", os.path.join(RAIZ, "painel", "aviso_sh.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.sem_git_bash


def corpo(*partes):
    with open(os.path.join(RAIZ, *partes), encoding="utf-8") as f:
        arvore = ast.parse(f.read())
    fns = [n for n in arvore.body if isinstance(n, ast.FunctionDef) and n.name == "sem_git_bash"]
    for n in fns:
        n.body = n.body[1:]  # the docstring is in each file's own language
    fns += [n for n in arvore.body if isinstance(n, ast.Assign) and any(getattr(a, "id", "") == "_WSL" for a in n.targets)]
    return [ast.dump(n) for n in fns]


class TestLocais(unittest.TestCase):
    def test_tabela_nas_duas_copias(self):
        for func in (sem_git_bash, painel_func()):
            for nome, which, env, files, esperado in CASOS:
                r = func(nt=True, which=which.get, env=env, isfile=lambda p: p in files)
                self.assertIs(r, esperado, nome)
            self.assertFalse(func(nt=False, which={}.get, env={}, isfile=lambda p: False))

    def test_copias_nao_divergem(self):
        a, b = corpo("scripts", "tuneup", "gitbash.py"), corpo("painel", "aviso_sh.py")
        self.assertEqual(len(a), 2)  # sem_git_bash and _WSL
        self.assertEqual(a, b)


class TestInicio(unittest.TestCase):
    def test_linha_de_sistema_nos_dois_idiomas(self):
        from tuneup import mensagens
        for lang in ("en", "pt-BR"):
            t = mensagens.CATALOG[lang]["sem_git_bash"]
            self.assertIn("CLAUDE_CODE_GIT_BASH_PATH", t)

    def test_ev_inicio_traz_a_linha(self):
        d = tempfile.mkdtemp()
        self.addCleanup(rmtree, d)
        env = {"CLAUDE_PLUGIN_DATA": d, "HOME": d, "USERPROFILE": d,
               "TUNEUP_USER_JSON": os.path.join(d, "user.json")}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        saved = dict(usuario._CACHE)
        usuario._CACHE.clear()
        self.addCleanup(lambda: (usuario._CACHE.clear(), usuario._CACHE.update(saved)))
        with mock.patch("tuneup.gitbash.sem_git_bash", return_value=True):
            out = sessao.ev_inicio({"source": "resume"}, {})
        self.assertIn("Git Bash", out["systemMessage"])
        with mock.patch("tuneup.gitbash.sem_git_bash", return_value=False):
            out = sessao.ev_inicio({"source": "resume"}, {})
        self.assertFalse(out and "Git Bash" in out.get("systemMessage", ""))


class TestRetry(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(rmtree, self.d)
        p = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self.d})
        p.start()
        self.addCleanup(p.stop)

    def test_permissao_duas_vezes_e_grava(self):
        real, n = os.replace, [0]

        def falha(a, b):
            n[0] += 1
            if n[0] <= 2:
                raise PermissionError(13, "in use")
            return real(a, b)
        with mock.patch.object(sessao.os, "replace", falha):
            sessao.gravar_sessao("s1", {"modo_pesquisa": True})
        self.assertEqual(n[0], 3)
        self.assertTrue(sessao.ler_sessao("s1")["modo_pesquisa"])

    def test_sempre_falha_levanta_como_antes_sem_travar(self):
        n = [0]

        def falha(a, b):
            n[0] += 1
            raise PermissionError(13, "in use")
        with mock.patch.object(sessao.os, "replace", falha):
            with self.assertRaises(PermissionError):
                sessao.gravar_sessao("s2", {})
        self.assertEqual(n[0], 5)

    def test_outro_erro_nao_repete(self):
        n = [0]

        def falha(a, b):
            n[0] += 1
            raise OSError(5, "io")
        with mock.patch.object(sessao.os, "replace", falha):
            with self.assertRaises(OSError):
                sessao.gravar_sessao("s3", {})
        self.assertEqual(n[0], 1)


class TestDocs(unittest.TestCase):
    def ler(self, *p):
        with open(os.path.join(RAIZ, *p), encoding="utf-8") as f:
            return f.read()

    def test_git_bash_obrigatorio_nos_docs(self):
        self.assertIn("Git Bash is REQUIRED", self.ler("README.md"))
        self.assertIn("Git Bash é obrigatório", self.ler("painel", "README.md"))
        s = self.ler("skills", "setup", "SKILL.md")
        self.assertIn("STOP here", s)
        for t in (self.ler("README.md"), self.ler("painel", "README.md"), s):
            self.assertIn("CLAUDE_CODE_GIT_BASH_PATH", t)


if __name__ == "__main__":
    unittest.main()
