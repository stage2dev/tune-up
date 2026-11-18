"""Dry mode of the router eval (no network, no key). Rode: python3 -m unittest discover -s tests -q"""
import os
import subprocess
import sys
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RODAR = os.path.join(RAIZ, "evals", "rota", "rodar.py")
sys.path.insert(0, os.path.join(RAIZ, "evals", "rota"))
import rodar  # noqa: E402


class TestEvalRota(unittest.TestCase):
    def test_modo_seco_sai_0(self):
        env = {k: v for k, v in os.environ.items() if k != "TYPESAFE_API_KEY"}
        p = subprocess.run([sys.executable, RODAR, "--seco"], capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("dry run", p.stdout)

    def test_arquivo_de_casos(self):
        casos = rodar.carregar()
        self.assertGreaterEqual(len(casos), 30)
        self.assertGreaterEqual(sum(1 for c in casos if c["risk"]), 12)
        ids = [c["id"] for c in casos]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(rodar.validar(casos), [])

    def test_arquivo_quebrado_nao_passa(self):
        casos = rodar.carregar()
        self.assertTrue(rodar.validar(casos[:5]))
        self.assertTrue(rodar.validar(casos + [dict(casos[0])]))
        self.assertTrue(rodar.validar([dict(casos[0], expect="haiku")] + casos[1:]))
        self.assertTrue(rodar.validar([dict(casos[0], risk=1)] + casos[1:]))
        self.assertTrue(rodar.validar([{"id": "x"}] + casos[1:]))
        self.assertTrue(rodar.validar({}))


if __name__ == "__main__":
    unittest.main()
