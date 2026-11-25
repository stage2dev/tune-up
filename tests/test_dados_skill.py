"""Tests: a skill's Bash has no CLAUDE_PLUGIN_DATA; it must still read the folder the hooks use.
Run: python3 -m unittest discover -s tests -q"""
import json
import os
import shutil
import subprocess
import sys
import unittest

from base import SCRIPT, Base

RAIZ = os.path.dirname(os.path.dirname(SCRIPT))


class TestDadosDaSkill(Base):
    USER_JSON = None

    def setUp(self):
        super().setUp()
        plugins = os.path.join(self.tmp, ".claude", "plugins")
        self.inst = os.path.join(plugins, "cache", "loja.x", "tune-up", "9.9.9")
        for d in ("scripts", "templates"):
            shutil.copytree(os.path.join(RAIZ, d), os.path.join(self.inst, d),
                            ignore=shutil.ignore_patterns("__pycache__", "wsl"))
        self.dados = os.path.join(plugins, "data", "tune-up-loja-x")
        os.makedirs(self.dados, mode=0o700)
        d = os.path.join(self.cwd, ".tune-up")
        os.makedirs(d)
        self.cfg = os.path.join(d, "config.json")
        with open(self.cfg, "w", encoding="utf-8") as f:
            json.dump({"front_globs": ["**/web/**"]}, f)
        os.chmod(self.cfg, 0o600)

    def guarda(self, *args, hook):
        env = {k: v for k, v in self.env.items() if k != "CLAUDE_PLUGIN_DATA"}
        if hook:
            env["CLAUDE_PLUGIN_DATA"] = self.dados
        r = subprocess.run([sys.executable, os.path.join(self.inst, "scripts", "guarda.py")] + list(args),
                           cwd=self.cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def front(self, hook):
        return json.loads(self.guarda("info", hook=hook))["front_globs"]

    def test_confianca_vale_com_e_sem_a_variavel(self):
        self.assertEqual(self.front(hook=False), [])  # not trusted yet
        self.guarda("confiar", self.cfg, hook=True)
        self.assertEqual(self.front(hook=True), ["**/web/**"])
        self.assertEqual(self.front(hook=False), ["**/web/**"])
        with open(self.cfg, "a", encoding="utf-8") as f:
            f.write("\n")  # edited after the trust
        self.assertEqual(self.front(hook=False), [])

    def test_sem_pasta_de_dados_cai_no_cache_da_home(self):
        shutil.rmtree(self.dados)
        self.guarda("confiar", self.cfg, hook=False)
        self.assertFalse(os.path.exists(self.dados))
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, ".cache", "tune-up", "perfis_confiaveis.txt")))

    def test_fora_da_instalacao_nao_muda(self):
        self.env.pop("CLAUDE_PLUGIN_DATA")
        self.guarda("confiar", self.cfg, hook=True)
        r = subprocess.run([sys.executable, SCRIPT, "info"], cwd=self.cwd, env=self.env, stdin=subprocess.DEVNULL,
                           capture_output=True, timeout=20)
        self.assertEqual(json.loads(r.stdout)["front_globs"], [])


if __name__ == "__main__":
    unittest.main()
