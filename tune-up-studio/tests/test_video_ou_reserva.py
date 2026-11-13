"""scripts/video_ou_reserva.py: which file runs as HyperFrames (Windows .cmd shim, current-folder plant)."""
import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import video_ou_reserva as vr  # noqa: E402


class Done:
    returncode, stderr = 1, b"stop"


class Resolve(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin = os.path.join(self.tmp.name, ".bin")
        os.makedirs(self.bin)
        self.binary = os.path.join(self.bin, "hyperframes")

    def shim(self, nome="hyperframes.cmd", pasta=None):
        caminho = os.path.join(pasta or self.bin, nome)
        open(caminho, "w").close()
        return caminho

    def test_windows_cmd_shim_is_what_runs(self):
        self.shim("hyperframes")  # npm's sh shim, no extension: WinError 193 if run
        cmd = self.shim()
        self.shim("hyperframes.ps1")
        with mock.patch.dict(os.environ, {"PATHEXT": ".PS1;.JS;.COM;.EXE;.BAT;.CMD"}):  # PATHEXT does not decide
            self.assertEqual(vr.resolve(self.binary, nt=True), cmd)
            with mock.patch.object(vr.os, "name", "nt"), \
                    mock.patch.object(vr.subprocess, "run", return_value=Done()) as run:
                ok, reason = vr.try_hyperframes(self.binary, "fonte", os.path.join(self.tmp.name, "v.mp4"), 30, 5)
        self.assertEqual(run.call_args[0][0][0], cmd)
        self.assertIn("render failed", reason)

    def test_windows_binary_that_already_has_an_extension(self):
        cmd = self.shim()
        self.assertEqual(vr.resolve(cmd, nt=True), cmd)
        self.assertIsNone(vr.resolve(os.path.join(self.bin, "outro.cmd"), nt=True))
        self.shim("hf.js")  # not startable by CreateProcess: only hf.js.cmd and friends would do
        self.assertIsNone(vr.resolve(os.path.join(self.bin, "hf.js"), nt=True))

    def test_cmd_planted_in_the_current_folder_is_never_picked(self):
        trabalho = os.path.join(self.tmp.name, "trabalho")
        os.makedirs(trabalho)
        self.shim(pasta=trabalho)
        antes = os.getcwd()
        os.chdir(trabalho)
        self.addCleanup(os.chdir, antes)
        with mock.patch.object(vr.subprocess, "run") as run:
            self.assertIsNone(vr.resolve(self.binary, nt=True))  # nothing in .bin: the plant is not a fallback
            with mock.patch.object(vr.os, "name", "nt"):
                ok, reason = vr.try_hyperframes(self.binary, "fonte", "v.mp4", 30, 5)
        run.assert_not_called()
        self.assertEqual(reason, "hyperframes not available: %s" % self.binary)
        cmd = self.shim()  # with the real shim present, the plant does not hide it either
        self.assertEqual(vr.resolve(self.binary, nt=True), cmd)

    def test_windows_folder_with_a_separator_in_its_name(self):
        pasta = os.path.join(self.tmp.name, "a;b" if os.name == "nt" else "a;b:c")  # ":" cannot be in a Windows name
        os.makedirs(pasta)
        cmd = self.shim(pasta=pasta)
        self.assertEqual(vr.resolve(os.path.join(pasta, "hyperframes"), nt=True), cmd)

    def test_posix_is_the_old_check(self):
        self.assertIsNone(vr.resolve(self.binary, nt=False))
        with open(self.binary, "w") as f:
            f.write("#!/bin/sh\n")
        if os.name != "nt":
            self.assertIsNone(vr.resolve(self.binary, nt=False))  # not executable yet
        os.chmod(self.binary, os.stat(self.binary).st_mode | stat.S_IXUSR)
        self.assertEqual(vr.resolve(self.binary, nt=False), self.binary)
        self.shim()  # a .cmd next to it changes nothing off Windows
        self.assertEqual(vr.resolve(self.binary, nt=False), self.binary)

    @unittest.skipIf(os.name == "nt", "symlink needs a privilege on Windows")
    def test_posix_npm_symlink_and_odd_folder_names(self):
        pasta = os.path.join(self.tmp.name, "a:b")
        os.makedirs(pasta)
        alvo = os.path.join(self.tmp.name, "cli.js")
        with open(alvo, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(alvo, 0o755)
        link = os.path.join(pasta, "hyperframes")  # npm links .bin/hyperframes to the package's cli
        os.symlink(alvo, link)
        self.assertEqual(vr.resolve(link), link)
        os.remove(alvo)
        self.assertIsNone(vr.resolve(link))  # broken link

    @unittest.skipUnless(os.name == "nt", "real PATHEXT lookup, Windows only")
    def test_real_windows_picks_the_cmd(self):
        self.shim("hyperframes")
        cmd = self.shim()
        self.assertEqual(os.path.normcase(vr.resolve(self.binary)), os.path.normcase(cmd))


if __name__ == "__main__":
    unittest.main()
