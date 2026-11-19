"""More preparar.sh cases (A4b): plugin version, --versao-plugin, fixados key, PATH pin, profile warning."""
import json
import os
import subprocess
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_wsl_preparar import PASSWD_TUNEUP, Preparar  # noqa: E402


class Usuario2(Preparar):
    def setUp(self):
        super().setUp()
        self.env.update(TUNE_UP_UID_TESTE="1000", FAKE_PASSWD=PASSWD_TUNEUP)
        os.makedirs(self.p("home", "tuneup"))
        self.instalados = self.p("home", "tuneup", ".claude", "plugins", "installed_plugins.json")

    def usuario(self, **env):
        return self.rodar("--usuario", "--sem-login", "--plugin", self.plugin, **env)

    def instalado(self, versao):
        with open(self.instalados, "w") as f:
            json.dump({"version": 2, "plugins": {"tune-up@tune-up": [{"scope": "user", "version": versao}]}}, f)

    def plugin_chamadas(self):
        return [c for c in self.chamadas("claude") if c.startswith("claude plugin")]

    def test_mesma_versao_nao_chama_claude_plugin(self):
        self.assertEqual(self.usuario().returncode, 0)
        os.remove(self.log)
        r = self.usuario()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.plugin_chamadas(), [])
        self.assertIn("Plugin tune-up 2.19.0 já instalado.", r.stdout)

    def test_versao_diferente_atualiza_em_ordem_e_reconfere(self):
        self.assertEqual(self.usuario().returncode, 0)
        self.instalado("2.18.0")
        os.remove(self.log)
        r = self.usuario()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.plugin_chamadas(), ["claude plugin marketplace update tune-up",
                                                  "claude plugin update tune-up@tune-up --scope user"])
        self.assertIn("Plugin tune-up 2.19.0 instalado.", r.stdout)

    def test_continua_diferente_depois_sai_com_1(self):
        self.assertEqual(self.usuario().returncode, 0)
        self.instalado("2.18.0")
        os.remove(self.log)
        r = self.usuario(FAKE_PLUGIN_V="2.18.0")  # the fake update leaves the old version
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("esperado 2.19.0", r.stderr)
        self.assertEqual(self.chamadas("preparar_estudio.py"), [])

    def test_manifesto_sem_versao_sai_com_1(self):
        with open(os.path.join(self.plugin, ".claude-plugin", "plugin.json"), "w") as f:
            f.write('{"name": "tune-up"}')
        r = self.usuario()
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertEqual(self.plugin_chamadas(), [])

    def test_versao_plugin(self):
        r = self.rodar("--versao-plugin")
        self.assertEqual((r.returncode, r.stdout), (1, ""), r.stderr)
        os.makedirs(os.path.dirname(self.instalados))
        self.instalado("2.19.0")
        r = self.rodar("--versao-plugin")
        self.assertEqual((r.returncode, r.stdout), (0, "2.19.0\n"), r.stderr)
        with open(self.instalados, "w") as f:
            f.write("{quebrado")
        r = self.rodar("--versao-plugin")
        self.assertEqual((r.returncode, r.stdout), (1, ""), r.stderr)
        r = self.rodar("--versao-plugin", TUNE_UP_UID_TESTE="0")
        self.assertEqual((r.returncode, r.stdout), (3, ""), r.stderr)
        self.assertEqual(self.rodar("--versao-plugin", "--plugin", self.plugin).returncode, 2)

    def test_perfil_alterado_pelo_claude_install_vira_aviso(self):
        r = self.usuario(FAKE_PERFIL="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Aviso: a instalação do Claude Code alterou ~/.profile ou ~/.bashrc; nada foi desfeito.",
                      r.stdout.splitlines())
        with open(self.p("home", "tuneup", ".bashrc")) as f:
            self.assertEqual(f.read(), "x\n")  # nothing restored

    def test_perfil_intacto_sem_aviso(self):
        r = self.usuario()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Aviso:", r.stdout)


class Geral2(Preparar):
    def test_chave_com_espaco_sai_com_4(self):
        base = "".join("%s=%s\n" % kv for kv in self.fix.items())
        self.escrever_fixados(base.replace("NODE_SHA256=", "NODE_URL NODE_SHA256="))
        r = self.rodar("--raiz")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn("chave inválida", r.stderr)
        self.assertEqual(self.chamadas("curl"), [])

    def test_path_fixado_antes_do_primeiro_comando_externo(self):
        for nome in ("id", "dirname"):
            p = os.path.join(self.bin, nome)
            with open(p, "w") as f:
                f.write('#!/bin/sh\necho "%s $*" >> "$FAKE_LOG"\nexec /usr/bin/%s "$@"\n' % (nome, nome))
            os.chmod(p, 0o755)
        env = dict(self.env)
        del env["TUNE_UP_RAIZ_TESTE"]  # a real run: the fake bin dir must never be searched
        r = subprocess.run(["bash", os.path.join(self.lib, "preparar.sh"), "--fechar"], env=env,
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(self.chamadas("id") + self.chamadas("dirname"), [])


if __name__ == "__main__":
    unittest.main()
