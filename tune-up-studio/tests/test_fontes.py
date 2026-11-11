"""Unit tests for scripts/fontes.py (brand font fields -> the two @font-face lines)."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "scripts", "fontes.py")
sys.path.insert(0, os.path.dirname(SCRIPT))

import fontes  # noqa: E402

SANS = 'local("Helvetica Neue"), local("Arial"), local("Liberation Sans"), local("DejaVu Sans")'


class TestePilha(unittest.TestCase):
    def test_so_generica_vira_pilha_sans(self):
        out = fontes.linhas("system-ui, sans-serif", "system-ui")
        self.assertEqual(out[0], '@font-face { font-family: "Brand Heading"; src: %s; }' % SANS)
        self.assertEqual(out[1], '@font-face { font-family: "Brand Body"; src: %s; }' % SANS)
        self.assertIn("body: so generica (system-ui)", out[3])

    def test_nomeadas_primeiro_e_sem_repetir(self):
        out = fontes.linhas("Georgia, 'Times New Roman', serif", "system-ui, -apple-system, 'Segoe UI', sans-serif")
        self.assertEqual(out[0], '@font-face { font-family: "Brand Heading"; src: local("Georgia"), '
                         'local("Times New Roman"), local("Liberation Serif"), local("DejaVu Serif"); }')
        self.assertTrue(out[1].startswith('@font-face { font-family: "Brand Body"; src: local("Segoe UI"), '
                                          'local("Helvetica Neue")'))
        self.assertIn("heading: com generica (serif)", out[2])

    def test_so_nomeada_nao_ganha_pilha(self):
        out = fontes.linhas("Inter", "Inter, Roboto")
        self.assertEqual(out, ['@font-face { font-family: "Brand Heading"; src: local("Inter"); }',
                               '@font-face { font-family: "Brand Body"; src: local("Inter"), local("Roboto"); }'])

    def test_mono_serif_e_campo_vazio(self):
        out = fontes.linhas("ui-serif", None)
        self.assertIn('local("Georgia")', out[0])
        self.assertIn(SANS, out[1])  # missing field = neutral system-ui, sans-serif
        self.assertIn('local("Menlo")', fontes.linhas("monospace", "x")[0])

    def test_nome_estranho_cai_fora(self):
        out = fontes.linhas('Evil"); } body { x: url(a', "a<b>, sans-serif")
        self.assertNotIn("url", out[0])
        self.assertIn(SANS, out[0])  # nothing usable: same as missing
        self.assertIn('src: %s;' % SANS, out[1])


class TesteComando(unittest.TestCase):
    def rodar(self, campos, *args, cwd=None):
        with tempfile.TemporaryDirectory() as raiz:
            marca = os.path.join(raiz, ".tune-up", "estudio", "marca")
            trab = os.path.join(raiz, ".tune-up", "painel", "dados", "trabalhos", "abc")
            os.makedirs(marca)
            os.makedirs(trab)
            if campos is not None:
                with open(os.path.join(marca, "marca.json"), "w", encoding="utf-8") as f:
                    json.dump({"versao": 1, "campos": campos}, f)
            return subprocess.run([sys.executable, "-I", SCRIPT, *args], cwd=cwd or trab,
                                  capture_output=True, text=True)

    def test_le_a_marca_da_pasta_de_trabalho(self):
        r = self.rodar({"fontes.heading": {"valor": "Georgia, serif"}, "fontes.body": {"valor": "system-ui"}})
        self.assertEqual(r.returncode, 0, r.stderr)
        linhas = r.stdout.splitlines()
        self.assertTrue(linhas[0].startswith('@font-face { font-family: "Brand Heading"; src: local("Georgia")'))
        self.assertIn(SANS, linhas[1])

    def test_sem_marca_sai_2(self):
        r = self.rodar(None)
        self.assertEqual(r.returncode, 2)
        self.assertIn("marca.json", r.stderr)
        self.assertEqual(r.stdout, "")

    def test_fora_de_tune_up_sai_2(self):
        with tempfile.TemporaryDirectory() as d:
            r = subprocess.run([sys.executable, "-I", SCRIPT, "--trabalho", d], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_argumento_desconhecido_sai_2(self):
        self.assertEqual(self.rodar({}, "system-ui").returncode, 2)


if __name__ == "__main__":
    unittest.main()
