import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import atalho


def sem_privilegio():
    e = OSError("A required privilege is not held by the client")
    e.winerror = 1314
    return e


class AtalhoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tuneup-atalho-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pasta = os.path.join(self.tmp, "pasta")
        os.makedirs(self.pasta)
        self.arq = os.path.join(self.pasta, "f.txt")
        with open(self.arq, "w") as f:
            f.write("oi")

    def ler(self, *partes):
        with open(os.path.join(self.tmp, *partes)) as f:
            return f.read()

    def test_sem_privilegio_no_windows_vira_skip(self):
        with mock.patch("os.symlink", side_effect=sem_privilegio()), mock.patch("os.name", "nt"):
            for dir_ in (False, True):
                with self.assertRaises(unittest.SkipTest):
                    atalho.symlink("a", "b", dir_=dir_)
        with mock.patch("os.symlink", side_effect=NotImplementedError()):
            with self.assertRaises(unittest.SkipTest):
                atalho.symlink("a", "b")

    def sobe(self, tipo, f, *a, **k):
        """f must raise `tipo`. A SkipTest would escape assertRaises and report the test as skipped, so it fails here."""
        try:
            f(*a, **k)
        except unittest.SkipTest as e:
            self.fail("became a skip: %s" % e)
        except tipo as e:
            return e
        self.fail("did not raise %s" % tipo.__name__)

    def test_outro_erro_sobe_em_qualquer_sistema(self):
        # a missing parent or an existing link is a broken test, never a skip (bare os.symlink errored too)
        for nome in ("nt", "posix"):
            for erro in (FileNotFoundError(2, "x"), FileExistsError(17, "x"), PermissionError(13, "x")):
                with mock.patch("os.symlink", side_effect=erro), mock.patch("os.name", nome), \
                        mock.patch("subprocess.run") as run:
                    self.sobe(type(erro), atalho.symlink, "a", "b")
                    self.sobe(type(erro), atalho.symlink, "a", "b", dir_=True)
                    self.sobe(type(erro), atalho.link_dir, "a", "b")
                run.assert_not_called()
        with mock.patch("os.symlink", side_effect=sem_privilegio()), mock.patch("os.name", "posix"), \
                mock.patch("subprocess.run") as run:  # winerror means nothing off Windows
            self.sobe(OSError, atalho.symlink, "a", "b")
            self.sobe(OSError, atalho.link_dir, "a", "b")
        run.assert_not_called()

    def test_link_dir_no_windows_usa_junction(self):
        ok = subprocess.CompletedProcess([], 0)
        with mock.patch("os.symlink", side_effect=sem_privilegio()), mock.patch("os.name", "nt"), \
                mock.patch.dict(os.environ, {"COMSPEC": "C:\\Windows\\system32\\cmd.exe"}), \
                mock.patch("subprocess.run", return_value=ok) as run:
            atalho.link_dir(self.pasta, os.path.join(self.tmp, "j"))  # não pula
        self.assertEqual(run.call_args[0][0], ["C:\\Windows\\system32\\cmd.exe", "/c", "mklink", "/J",
                                               os.path.join(self.tmp, "j"), self.pasta])
        self.assertFalse(run.call_args[1].get("shell"))

    def test_mklink_que_falha_da_erro_nao_skip(self):
        ruim = subprocess.CompletedProcess([], 1, b"", b"denied")
        with mock.patch("os.symlink", side_effect=sem_privilegio()), mock.patch("os.name", "nt"), \
                mock.patch("subprocess.run", return_value=ruim):
            self.assertIn("mklink", str(self.sobe(OSError, atalho.link_dir, "a", "b")))

    def test_link_de_pasta_real_funciona_aqui(self):
        atalho.link_dir(self.pasta, os.path.join(self.tmp, "ld"))
        self.assertEqual(self.ler("ld", "f.txt"), "oi")

    def test_link_de_arquivo_real_funciona_aqui(self):
        atalho.symlink(self.arq, os.path.join(self.tmp, "ls.txt"))
        self.assertEqual(self.ler("ls.txt"), "oi")

    @unittest.skipUnless(os.name == "nt", "junctions exist only on Windows")
    def test_junction_de_verdade_no_windows(self):
        link = os.path.join(self.tmp, "j")
        with mock.patch("os.symlink", side_effect=sem_privilegio()):  # even where the runner may symlink
            atalho.link_dir(self.pasta, link)
        self.assertEqual(self.ler("j", "f.txt"), "oi")
        self.assertEqual(os.path.realpath(link), os.path.realpath(self.pasta))
        self.assertFalse(os.path.islink(link))
        shutil.rmtree(self.tmp)
        self.assertFalse(os.path.exists(link))


if __name__ == "__main__":
    unittest.main()
