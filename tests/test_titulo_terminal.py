"""Tests for titulo_terminal.py: terminal tab in VS Code-family editors.
Run: python3 -m unittest discover -s tests -q"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from base import mkdtemp, rmtree  # noqa: E402

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "titulo_terminal.py")
CHAVE = "terminal.integrated.tabs.title"
VALOR = "${sequence}${separator}${process}"

sys.path.insert(0, os.path.dirname(SCRIPT))
from titulo_terminal import ler  # noqa: E402


class TestTituloTerminal(unittest.TestCase):
    def setUp(self):
        self.tmp = mkdtemp("tuneup-titulo-")
        self.addCleanup(rmtree, self.tmp)
        self.env = {k: v for k, v in os.environ.items() if k not in ("XDG_CONFIG_HOME", "APPDATA")}
        self.env.update({"HOME": self.tmp, "USERPROFILE": self.tmp})
        if sys.platform == "darwin":
            self.base = os.path.join(self.tmp, "Library", "Application Support")
        elif sys.platform == "win32":
            self.base = os.path.join(self.tmp, "AppData", "Roaming")
        else:
            self.base = os.path.join(self.tmp, ".config")

    def editor(self, nome, texto=None):
        user = os.path.join(self.base, nome, "User")
        os.makedirs(os.path.join(user, "globalStorage"))
        arq = os.path.join(user, "settings.json")
        if texto is not None:
            with open(arq, "w") as f:
                f.write(texto)
        return arq

    def rodar(self, *args):
        r = subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True,
                           env=self.env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def conteudo(self, arq):
        with open(arq) as f:
            return f.read()

    def test_listar_nao_escreve(self):
        arq = self.editor("Code", '{\n    "editor.fontSize": 12\n}\n')
        s = self.rodar()
        self.assertEqual([(e["editor"], e["antes"]) for e in s["editores"]], [("Code", "falta")])
        self.assertEqual(self.conteudo(arq), '{\n    "editor.fontSize": 12\n}\n')
        self.assertFalse(os.path.exists(arq + ".bak-tune-up"))

    def test_aplica_mantendo_comentario_e_virgula_sobrando(self):
        texto = '{\n  // fonte\n  "editor.fontSize": 12, /* x */\n  "a": "http://b" // fim\n}\n'
        arq = self.editor("Cursor", texto)
        s = self.rodar("aplicar")
        self.assertEqual(s["editores"][0]["depois"], "aplicado")
        novo = self.conteudo(arq)
        self.assertIn("// fonte", novo)
        self.assertIn('  "%s": "%s"\n}' % (CHAVE, VALOR), novo)
        self.assertEqual(ler(novo), {"editor.fontSize": 12, "a": "http://b", CHAVE: VALOR})
        self.assertEqual(self.conteudo(arq + ".bak-tune-up"), texto)
        texto2 = '{\n    "a": 1,\n}'
        arq2 = self.editor("Windsurf", texto2)
        self.rodar("aplicar")
        self.assertEqual(ler(self.conteudo(arq2)), {"a": 1, CHAVE: VALOR})

    def test_sem_arquivo_e_objeto_vazio(self):
        arq = self.editor("Antigravity IDE")
        arq2 = self.editor("VSCodium", "{}")
        self.rodar("aplicar")
        self.assertEqual(ler(self.conteudo(arq)), {CHAVE: VALOR})
        self.assertEqual(ler(self.conteudo(arq2)), {CHAVE: VALOR})

    def test_valor_do_dono_fica(self):
        arq = self.editor("Code", '{"%s": "${process}"}' % CHAVE)
        s = self.rodar("aplicar")
        self.assertEqual(s["editores"][0]["antes"], "valor_do_dono")
        self.assertEqual(self.conteudo(arq), '{"%s": "${process}"}' % CHAVE)

    def test_ilegivel_nao_mexe(self):
        arq = self.editor("Code", '{"a": 1')
        s = self.rodar("aplicar")
        self.assertEqual(s["editores"][0]["antes"], "ilegivel")
        self.assertEqual(self.conteudo(arq), '{"a": 1')

    def test_ignora_pasta_que_nao_e_editor(self):
        os.makedirs(os.path.join(self.base, "OutroApp", "User"))
        self.assertEqual(self.rodar()["editores"], [])

    def test_perfil_do_editor_tambem(self):
        self.editor("Code", "{}")
        perfil = os.path.join(self.base, "Code", "User", "profiles", "abc")
        os.makedirs(perfil)
        with open(os.path.join(perfil, "settings.json"), "w") as f:
            f.write('{"a": 1}')
        s = self.rodar("aplicar")
        self.assertEqual([e["depois"] for e in s["editores"]], ["aplicado", "aplicado"])
        self.assertEqual(ler(self.conteudo(os.path.join(perfil, "settings.json"))), {"a": 1, CHAVE: VALOR})

    def test_desfazer_volta_ao_original(self):
        casos = ['{\n    "a": 1\n}\n', '{\n    "a": 1,\n    "b": [1, 2]\n}\n', "{}"]
        arqs = [self.editor("E%d" % i, t) for i, t in enumerate(casos)]
        self.rodar("aplicar")
        s = self.rodar("desfazer")
        self.assertEqual({e["depois"] for e in s["editores"]}, {"falta"})
        for arq, t in zip(arqs, casos):
            self.assertEqual(ler(self.conteudo(arq)), ler(t))
        primeiro = self.editor("F", '{\n    "%s": "%s",\n    "a": 1\n}' % (CHAVE, VALOR))
        self.rodar("desfazer")
        self.assertEqual(ler(self.conteudo(primeiro)), {"a": 1})

    def test_desfazer_nao_tira_valor_do_dono(self):
        arq = self.editor("Code", '{"%s": "${cwdFolder}"}' % CHAVE)
        self.rodar("desfazer")
        self.assertEqual(self.conteudo(arq), '{"%s": "${cwdFolder}"}' % CHAVE)


if __name__ == "__main__":
    unittest.main()
