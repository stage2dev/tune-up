"""Aviso de Git Bash no painel: função injetável e entrada em cfg["avisos"] (tela e stderr)."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import aviso_sh  # noqa: E402
import config  # noqa: E402


def sem(which=None, env=None, files=(), nt=True):
    return aviso_sh.sem_git_bash(nt=nt, which=(which or {}).get, env=env or {}, isfile=lambda p: p in files)


class TestAvisoSh(unittest.TestCase):
    def test_funcao(self):
        self.assertFalse(sem(nt=False))
        self.assertTrue(sem())
        self.assertTrue(sem({"bash": "C:\\Windows\\System32\\bash.exe"}))
        self.assertFalse(sem({"sh": "C:\\Git\\usr\\bin\\sh.exe"}))
        env = {"CLAUDE_CODE_GIT_BASH_PATH": "D:\\b.exe"}
        self.assertTrue(sem(env=env))
        self.assertFalse(sem(env=env, files={"D:\\b.exe"}))

    def test_carregar_poe_o_aviso_no_topo(self):
        raiz = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, raiz, True)
        with mock.patch.object(aviso_sh, "sem_git_bash", return_value=True):
            cfg = config.carregar(raiz=raiz)
        self.assertEqual(cfg["avisos"][0], aviso_sh.AVISO)
        self.assertIn("Git Bash não encontrado", cfg["avisos"][0])
        with mock.patch.object(aviso_sh, "sem_git_bash", return_value=False):
            cfg = config.carregar(raiz=raiz)
        self.assertNotIn(aviso_sh.AVISO, cfg["avisos"])


if __name__ == "__main__":
    unittest.main()
