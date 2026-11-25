"""Automatic preparation (tuneup/preparar.py) with fake `claude`, `git` and `node` (preparar_fake.py)."""
import json
import os
import re
import subprocess
import sys
import time
import unittest
from unittest import mock

from base import Base, IS_WIN, SCRIPT
from preparar_fake import PINS, PrepararBase, preparar
from tuneup import preparar_execucao
from tuneup.config import carregar_config

NOMES = [f["nome"] for f in preparar.FONTES]


@unittest.skipIf(IS_WIN, "sh-script fakes are not found on PATH on Windows")
class TestExecucao(PrepararBase):
    def test_caminho_feliz(self):
        res = self.preparar()
        self.assertEqual((res["ok"], res["failed"], res["skipped"]), (True, [], {}))
        m = self.mundo()
        self.assertEqual({n: m["plugins"]["%s@%s" % (n, n)]["enabled"] for n in NOMES},
                         {"ecc": False, "ponytail": True, "caveman": True})
        self.assertEqual(m["limites"], {"ecc": True, "ponytail": True, "caveman": True})  # limits before installs
        calls = self.mexeu()
        self.assertEqual(calls[:3], ["plugin marketplace add affaan-m/ecc#v2.2.3 --scope user --json",
                                     "plugin install ecc@ecc --scope user --config hooks_enabled=false --json",
                                     "plugin disable ecc@ecc --scope user --json"])
        self.assertIn("plugin install ponytail@ponytail --scope user --config ledger=false --json", calls)
        self.assertEqual(self.settings()["env"], {"PONYTAIL_SUBAGENT_MATCHER": "^tune-up:executor"})
        with open(os.path.join(self.tmp, "xdg", "caveman", "config.json")) as f:
            self.assertEqual(f.read(), '{"defaultMode":"off"}')
        self.assertTrue(os.path.isfile(os.path.join(self.conf, "skills-catalog.md")))
        self.assertEqual(self.ler("pronto.json")["version"], preparar.versao())
        # second run with the same version: nothing is called
        antes = len(self.chamadas("claude"))
        self.preparar("t2")
        self.assertEqual(len(self.chamadas("claude")), antes)
        self.assertEqual(self.ler("preparo.resultado.json")["run"], "t1")
        # new plugin version: checked, nothing installed, nothing to say
        self.grava("pronto.json", {"version": "0.0.1"})
        self.preparar("t3")
        self.assertEqual(self.mexeu(), calls)
        self.assertEqual(self.ler("pronto.json")["version"], preparar.versao())
        self.assertEqual(self.ler("preparo.resultado.json")["run"], "t1")

    def test_removido_pelo_usuario_nao_volta(self):
        self.preparar()
        m = self.mundo()
        del m["plugins"]["ponytail@ponytail"]
        self.mundo(plugins=m["plugins"])
        self.settings({"enabledPlugins": {"ecc@ecc": False, "caveman@caveman": True}})  # as uninstall leaves it
        self.grava("pronto.json", {"version": "0.0.1"})
        antes = self.mexeu()
        self.preparar("t2")
        self.assertEqual(self.mexeu(), antes)
        self.assertEqual(self.ler("pronto.json")["skipped"], {"ponytail": "removed"})

    def test_o_que_o_usuario_tem_fica_como_esta(self):
        tem = {"ponytail@ponytail": {"enabled": False}, "caveman@outro": {"enabled": True},
               "ecc@ecc": {"enabled": True}}
        self.mundo(plugins=dict(tem))
        res = self.preparar()
        self.assertEqual(self.mundo()["plugins"], tem)
        self.assertEqual(self.mexeu(), [])
        self.assertEqual(res["skipped"], {n: "present" for n in NOMES})
        self.assertIsNone(self.settings())  # no limit on a plugin that is not ours
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "xdg")))

    def test_ligado_no_settings_sem_estar_instalado(self):
        self.settings({"enabledPlugins": {"caveman@caveman": False}})
        self.assertEqual(self.preparar()["skipped"], {"caveman": "present"})
        self.assertNotIn("caveman@caveman", self.mundo()["plugins"])

    def test_marketplace_de_outra_fonte(self):
        outro = {"repo": "someone/ponytail", "installLocation": "/nowhere"}
        sem_ref = {"repo": "affaan-m/ecc", "installLocation": "/nowhere"}
        self.mundo(mkts={"ponytail": outro, "ecc": sem_ref})
        self.settings({"extraKnownMarketplaces": {"caveman": {"source": {"source": "github", "repo": "x/y"}}}})
        res = self.preparar()
        self.assertEqual(res["skipped"], {n: "marketplace" for n in NOMES})
        self.assertEqual(self.mexeu(), [])
        self.assertEqual(self.mundo()["mkts"], {"ponytail": outro, "ecc": sem_ref})
        linha = self.inicio()
        self.assertIn("ready", linha)
        self.assertIn("another source: ecc, ponytail, caveman", linha)
        self.assertEqual(self.inicio(), "")  # once

    def test_marketplace_ja_no_pin_instala_sem_adicionar(self):
        loc = os.path.join(self.tmp, "clone")
        os.makedirs(os.path.join(loc, ".git"))
        with open(os.path.join(loc, ".git", "HEAD"), "w") as f:
            f.write(PINS["caveman"])
        self.mundo(mkts={"caveman": {"repo": "JuliusBrussee/caveman", "ref": "v4.2.0", "installLocation": loc}})
        self.assertTrue(self.preparar()["ok"])
        self.assertIn("caveman@caveman", self.mundo()["plugins"])
        self.assertFalse([c for c in self.mexeu() if "add JuliusBrussee" in c])

    def test_commit_diferente(self):
        self.mundo(commits=dict(PINS, ponytail="e" * 40))
        res = self.preparar()
        self.assertEqual(res["failed"], [["ponytail", "commit"]])
        calls = self.mexeu()
        self.assertFalse([c for c in calls if "install ponytail" in c])
        self.assertIn("plugin marketplace remove ponytail --json", calls)
        self.assertIsNone(self.ler("pronto.json"))
        self.assertNotIn("env", self.settings())  # the limit is not written for what is not installed

    def test_commit_muda_durante_o_install(self):
        self.mundo(move=True)
        res = self.preparar()
        self.assertEqual(res["failed"], [[n, "commit"] for n in NOMES])
        self.assertEqual((self.mundo()["plugins"], self.mundo()["mkts"]), ({}, {}))

    def test_disable_falha_desinstala(self):
        self.mundo(quebra=["disable"])
        res = self.preparar()
        self.assertEqual(res["failed"], [["ecc", "disable"]])
        self.assertNotIn("ecc@ecc", self.mundo()["plugins"])
        self.assertIsNone(self.ler("pronto.json"))
        self.assertNotIn("ecc", self.ler("preparo.json")["installed"])
        self.mundo(quebra=[])
        self.assertTrue(self.preparar("t2")["ok"])  # retried
        self.assertFalse(self.mundo()["plugins"]["ecc@ecc"]["enabled"])

    def test_disable_e_uninstall_falham_e_a_proxima_desfaz(self):
        self.mundo(quebra=["disable", "uninstall"])
        self.assertEqual(self.preparar()["failed"], [["ecc", "left"]])
        self.assertEqual(self.ler("preparo.json")["installed"]["ecc"], "installing")
        self.mundo(quebra=[])
        self.assertTrue(self.preparar("t2")["ok"])
        self.assertFalse(self.mundo()["plugins"]["ecc@ecc"]["enabled"])

    def test_sem_rede(self):
        self.mundo(quebra=["marketplace add"])
        res = self.preparar()
        self.assertEqual(res["failed"], [[n, "add"] for n in NOMES])
        self.assertIsNone(self.ler("pronto.json"))
        self.assertFalse([c for c in self.mexeu() if c.startswith("plugin install")])
        self.assertIn("no network", self.inicio())

    def test_falta_programa(self):
        for nome in ("git", "node"):
            os.remove(os.path.join(self.tmp, "bin", nome))
        self.assertEqual(self.preparar()["failed"], [["git", "missing"], ["node", "missing"]])
        self.assertEqual(self.chamadas("claude"), [])
        self.assertIsNone(self.ler("pronto.json"))

    def test_limite_que_nao_grava_barra_o_install(self):
        os.makedirs(os.path.join(self.tmp, "xdg"))
        open(os.path.join(self.tmp, "xdg", "caveman"), "w").close()  # a file where the folder goes
        with open(os.path.join(self.cfg, "settings.json"), "w") as f:
            f.write("{broken")
        res = self.preparar()
        self.assertEqual(res["failed"], [[n, "limit"] for n in NOMES])
        self.assertEqual(self.mundo()["plugins"], {})
        self.settings({})
        self.assertEqual(self.preparar("t2")["failed"], [["caveman", "limit"]])
        self.assertNotIn("caveman@caveman", self.mundo()["plugins"])

    def test_limite_que_ja_existe_fica(self):
        self.settings({"env": {"PONYTAIL_SUBAGENT_MATCHER": "mine", "OTHER": "1"}, "x": 1})
        os.makedirs(os.path.join(self.tmp, "xdg", "caveman"))
        cave = os.path.join(self.tmp, "xdg", "caveman", "config.json")
        with open(cave, "w") as f:
            f.write('{"defaultMode":"review"}')
        self.assertTrue(self.preparar()["ok"])
        self.assertEqual(self.settings(), {"env": {"PONYTAIL_SUBAGENT_MATCHER": "mine", "OTHER": "1"}, "x": 1,
                                           "enabledPlugins": {"ecc@ecc": False, "ponytail@ponytail": True,
                                                              "caveman@caveman": True}})
        with open(cave) as f:
            self.assertEqual(f.read(), '{"defaultMode":"review"}')

    def test_registro_ilegivel_nao_instala(self):
        with open(os.path.join(self.conf, "preparo.json"), "w") as f:
            f.write("{broken")
        self.assertEqual(self.preparar()["failed"], [["tune-up", "state"]])
        self.assertEqual(self.mexeu(), [])
        self.assertIsNone(self.ler("pronto.json"))

    def test_catalogo_que_existe_fica(self):
        with open(os.path.join(self.conf, "skills-catalog.md"), "w") as f:
            f.write("mine")
        self.preparar()
        with open(os.path.join(self.conf, "skills-catalog.md")) as f:
            self.assertEqual(f.read(), "mine")
        self.assertFalse(os.path.exists(os.path.join(self.conf, "ecc-skills")))

    def test_tranca_de_outro_nao_roda(self):
        with open(os.path.join(self.conf, "preparo.lock"), "w") as f:
            f.write("other")
        r = subprocess.run(preparar.argv_filho("mine"), env=self.env, capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.chamadas("claude"), [])
        self.assertTrue(os.path.exists(os.path.join(self.conf, "preparo.lock")))

    def test_perder_a_tranca_no_meio_para(self):
        self.fake("claude", 'printf other > "%s/preparo.lock"\necho "[]"' % self.conf)
        self.env["PATH"] = os.path.join(self.tmp, "bin")
        with open(os.path.join(self.conf, "preparo.lock"), "w") as f:
            f.write("t1")
        subprocess.run(preparar.argv_filho("t1"), env=self.env, capture_output=True, timeout=60)
        self.assertEqual(len(self.chamadas("claude")), 1)
        self.assertIsNone(self.ler("preparo.resultado.json"))
        with open(os.path.join(self.conf, "preparo.lock")) as f:
            self.assertEqual(f.read(), "other")

    def test_timeout_mata_o_processo(self):
        self.fake("claude", "/bin/sleep 60")
        self.grava("preparo.lock", 0)
        ambiente = dict(self.env, PATH=os.path.join(self.tmp, "bin"))
        with mock.patch.dict(os.environ, ambiente, clear=True), mock.patch.object(preparar_execucao, "PRAZO_CMD", 0.3), \
                mock.patch.object(preparar_execucao, "tranca_e_minha", return_value=True):
            t = time.time()
            rc, _ = preparar_execucao.Preparo("x").claude("list")
        self.assertIsNone(rc)
        self.assertLess(time.time() - t, 10)


@unittest.skipIf(IS_WIN, "sh-script fakes are not found on PATH on Windows")
class TestInicio(PrepararBase):
    def test_anuncia_solta_e_volta_logo(self):
        self.fake("claude", '[ -f "%s/dormiu" ] || { : > "%s/dormiu"; /bin/sleep 5; }\nexec "%s" "%s/fake.py" "$@"'
                  % (self.tmp, self.tmp, sys.executable, self.tmp))
        self.env["PATH"] = os.path.join(self.tmp, "bin")
        t = time.time()
        linha = self.inicio("resume")
        self.assertLess(time.time() - t, 4)  # the first fake call alone takes 5 s: it did not wait
        for parte in ("affaan-m/ecc#v2.2.3", "DietrichGebert/ponytail#v5.3.3", "JuliusBrussee/caveman#v4.2.0",
                      "background", "auto_prepare", os.path.join(self.conf, "user.json")):
            self.assertIn(parte, linha)
        self.assertEqual(self.inicio(), "")  # still running: no second run, no second line
        self.assertIsNotNone(self.espera("pronto.json"))
        self.assertEqual(len([c for c in self.chamadas("claude") if "install ecc" in c]), 1)
        self.assertIn("tune-up ready", self.inicio())
        self.assertEqual(self.inicio(), "")
        self.assertEqual(len([c for c in self.chamadas("claude") if "install ecc" in c]), 1)

    def test_falha_mostra_uma_vez_e_tenta_de_novo(self):
        self.mundo(quebra=["marketplace add"])
        self.assertIn("background", self.inicio())
        self.espera("preparo.resultado.json")
        self.mundo(quebra=[])
        linha = self.inicio()
        self.assertIn("incomplete", linha)
        self.assertNotIn("background,", linha)  # announced only once
        self.assertIsNotNone(self.espera("pronto.json"))

    def test_desligado_nao_solta(self):
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)

        def projeto(v):
            with open(os.path.join(perfil, "config.json"), "w") as f:
                f.write(v if isinstance(v, str) else json.dumps(v))
        casos = [("user off", {"auto_prepare": False}, {}, {}),
                 ("user not a bool", {"auto_prepare": "false"}, {}, {}),
                 ("untrusted project off", {}, {"auto_prepare": False}, {}),
                 ("untrusted project cannot turn on", {"auto_prepare": False}, {"auto_prepare": True}, {}),
                 ("project not a bool", {}, {"auto_prepare": "false"}, {}),
                 ("project broken", {}, "{broken", {}),
                 ("test", {}, {}, {"TUNEUP_TESTE": "1"}),
                 ("ci", {}, {}, {"CI": "true"}),
                 ("recursion", {}, {}, {preparar.RECURSAO: "1"})]
        for nome, usuario, proj, env in casos:
            with self.subTest(nome):
                self.usuario(usuario)
                projeto(proj)
                self.rodar("inicio", {"source": "startup"}, env)
                self.assertFalse(os.path.exists(os.path.join(self.conf, "preparo.lock")))
                self.assertIsNone(self.ler("preparo.visto.json"))
        projeto({"auto_prepare": True})
        with open(os.path.join(self.conf, "user.json"), "w") as f:
            f.write("{broken")
        self.inicio()
        self.assertFalse(os.path.exists(os.path.join(self.conf, "preparo.lock")))
        time.sleep(0.3)
        self.assertEqual(self.chamadas("claude"), [])

    def test_trusted_project_does_not_override_user_off(self):
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)
        with open(os.path.join(perfil, "config.json"), "w") as f:
            json.dump({"auto_prepare": True}, f)
        self.confiar(os.path.join(perfil, "config.json"))
        self.usuario({"auto_prepare": False})
        self.inicio()
        self.assertFalse(os.path.exists(os.path.join(self.conf, "preparo.lock")))

    def test_so_startup_e_resume(self):
        for source in ("clear", "compact", None):
            self.inicio(source)
        self.assertFalse(os.path.exists(os.path.join(self.conf, "preparo.lock")))

    def test_erro_no_preparo_nao_muda_a_sessao(self):
        os.remove(os.path.join(self.conf, "user.json"))
        os.rmdir(self.conf)
        open(self.conf, "w").close()  # the folder cannot be created
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("/tune-up:setup", s["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.chamadas("claude"), [])

    def test_vinte_sessoes_uma_execucao(self):
        entrada = json.dumps({"session_id": "s", "cwd": self.cwd, "source": "startup"})
        ps = [subprocess.Popen([sys.executable, SCRIPT, "inicio"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               env=self.env, text=True) for _ in range(20)]
        saidas = [p.communicate(entrada, timeout=60)[0] for p in ps]
        self.assertEqual(sum("background" in s for s in saidas), 1)
        self.assertIsNotNone(self.espera("pronto.json"))
        self.assertEqual(len([c for c in self.chamadas("claude") if "install ecc" in c]), 1)


class TestTranca(Base):
    def setUp(self):
        super().setUp()
        ambiente = {"HOME": self.tmp, "USERPROFILE": self.tmp, "CLAUDE_PLUGIN_DATA": self.dados}
        p = mock.patch.dict(os.environ, ambiente)
        p.start()
        self.addCleanup(p.stop)

    def test_tranca_velha_e_nova(self):
        t1 = preparar.trancar()
        self.assertTrue(preparar.tranca_e_minha(t1))
        self.assertIsNone(preparar.trancar())
        arq = os.path.join(self.tmp, ".config", "tune-up", "preparo.lock")
        velho = time.time() - preparar.TRANCA_VELHA - 5
        os.utime(arq, (velho, velho))
        t2 = preparar.trancar()
        self.assertTrue(t2 and t2 != t1)
        preparar.soltar(t1)  # not its lock any more
        self.assertTrue(preparar.tranca_e_minha(t2))
        preparar.soltar(t2)
        self.assertFalse(os.path.exists(arq))

    def test_lancar_que_falha_solta_a_tranca(self):
        cfg = dict(carregar_config(self.cwd), auto_prepare=True)
        with mock.patch.object(preparar, "permitido", return_value=True), \
                mock.patch.object(preparar, "lancar", side_effect=OSError("no process")):
            with self.assertRaises(OSError):
                preparar.ao_iniciar({"source": "startup"}, cfg)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".config", "tune-up", "preparo.lock")))

    def test_cada_motivo_tem_texto(self):
        with open(preparar_execucao.__file__, encoding="utf-8") as f:
            fonte = f.read()
        usados = set(re.findall(r'(?:Falha\(|desfazer\(f, )"(\w+)"\)', fonte)) | {"missing", "state", "error"}
        self.assertEqual(usados, set(preparar.MOTIVOS))
        for m, texto in preparar.MOTIVOS.items():
            self.assertNotIn("prep_m_", texto(), m)
        linha = preparar.linha_resultado({"ok": False, "failed": [["ecc", "add"], ["x", "junk"]],
                                          "skipped": {"caveman": "marketplace"}})
        self.assertIn("ecc: download failed", linha)
        self.assertIn("another source: caveman", linha)


if __name__ == "__main__":
    unittest.main()
