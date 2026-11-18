"""scripts/saida_utf8.py: studio scripts print UTF-8 even when stdout is cp1252 (Windows)."""
import ast
import glob
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
sys.path.insert(0, SCRIPTS)

import saida_utf8  # noqa: E402

# runs a script the way `python3 -I script.py` does, but with stdout/stderr in cp1252 like a Windows pipe
CP1252 = ("import io, runpy, sys; script = sys.argv[1]; sys.argv = sys.argv[1:]; "
          "sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='cp1252'); "
          "sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='cp1252'); "
          "runpy.run_path(script, run_name='__main__')")


def cp1252():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="\n")  # no Windows o padrão grava \r\n


class Helper(unittest.TestCase):
    def test_cp1252_streams_become_utf8(self):
        out, err = cp1252(), cp1252()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            saida_utf8.utf8()
            print("ação ✓ 日本")
            print("erro ✓", file=sys.stderr)
        out.flush()
        err.flush()
        self.assertEqual(out.buffer.getvalue(), "ação ✓ 日本\n".encode("utf-8"))
        self.assertEqual(err.buffer.getvalue(), "erro ✓\n".encode("utf-8"))
        self.assertEqual(err.errors, "backslashreplace")

    def test_utf8_stream_and_stringio_are_left_alone(self):
        out = io.TextIOWrapper(io.BytesIO(), encoding="UTF8", errors="strict")
        err = io.StringIO()
        with mock.patch.object(sys, "stdout", out), mock.patch.object(sys, "stderr", err):
            saida_utf8.utf8()
        self.assertEqual((out.encoding, out.errors), ("UTF8", "strict"))


class EveryScript(unittest.TestCase):
    def test_every_main_calls_the_helper_first(self):
        achados = 0
        for caminho in sorted(glob.glob(os.path.join(SCRIPTS, "*.py"))):
            with open(caminho, encoding="utf-8") as f:
                arvore = ast.parse(f.read())
            for no in arvore.body:
                if isinstance(no, ast.FunctionDef) and no.name == "main":
                    achados += 1
                    primeiro = ast.dump(no.body[0])
                    self.assertIn("attr='utf8'", primeiro, os.path.basename(caminho))
                    self.assertIn("id='saida_utf8'", primeiro, os.path.basename(caminho))
        self.assertGreaterEqual(achados, 11)


class EndToEnd(unittest.TestCase):
    def test_fontes_prints_a_cjk_brand_font_under_cp1252(self):
        with tempfile.TemporaryDirectory() as raiz:
            marca = os.path.join(raiz, ".tune-up", "estudio", "marca")
            trab = os.path.join(raiz, ".tune-up", "painel", "dados", "trabalhos", "abc")
            os.makedirs(marca)
            os.makedirs(trab)
            with open(os.path.join(marca, "marca.json"), "w", encoding="utf-8") as f:
                json.dump({"versao": 1, "campos": {"fontes.heading": {"valor": "Noto 日本"}}}, f)
            r = subprocess.run([sys.executable, "-I", "-c", CP1252, os.path.join(SCRIPTS, "fontes.py"),
                                "--trabalho", trab], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace")[-300:])
        self.assertIn('local("Noto 日本")'.encode("utf-8"), r.stdout)


if __name__ == "__main__":
    unittest.main()
