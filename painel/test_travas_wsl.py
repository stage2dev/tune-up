"""Travas of a session launched into the WSL distro: --settings and hook conf valid inside Linux (B3a).

Run: python3 -B -m unittest test_travas_wsl  (from painel/)
"""
import json
import os
import posixpath
import re
import shlex
import subprocess
import sys
import threading
import unittest
from unittest import mock

import catalogo
import embutidos
import sandbox
import test_sandbox
import trabalho
import travas
import travas_sessao
import wsl
from erros import ErroAcao

WS = "C:\\Users\\Ana\\Projetos\\loja"
PACOTE = WS + "\\.tune-up\\painel"
DADOS = PACOTE + "\\dados"
PLUGIN_WIN = "C:\\Users\\Ana\\.claude\\plugins\\cache\\mkt\\tune-up\\1.0.0"
CFG = {"workspace": WS, "pacote_dir": PACOTE, "dados_dir": DADOS, "painel_dir": PLUGIN_WIN + "\\painel",
       "arquivo": WS + "\\.tune-up\\painel.json"}
PLUGIN_DIR = "/home/tuneup/.claude/plugins/cache/mkt/tune-up/1.0.0"
CHAVE = "0123456789ab"
W = {"plugin_dir": PLUGIN_DIR, "chave": CHAVE, "este_arquivo": PLUGIN_WIN + "\\painel\\travas.py",
     "codigo": [PLUGIN_WIN + "\\tune-up-studio", PLUGIN_WIN + "\\vendas"]}
WS_W = "/mnt/c/Users/Ana/Projetos/loja"
DADOS_W = WS_W + "/.tune-up/painel/dados"
PASTA_W = DADOS_W + "/trabalhos/abc"
HF = wsl.caminho_hf(CHAVE)
PY = PLUGIN_DIR + "/tune-up-studio/scripts/"


def acao_wsl(acao=None):
    acao = acao or test_sandbox.fixture()
    return trabalho.resolver_travas(acao, PASTA_W, {"hf": HF, "py": None})


def texto_wsl(acao=None, cfg=CFG, w=W):
    return travas.argv_travas(acao_wsl(acao), cfg, wsl=w)[1]


def gancho(cfg):
    partes = shlex.split(cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
    return partes, travas._decodificar(partes[4])


def linux(conf, ferramenta, entrada, cwd=PASTA_W):
    """decidir as the hook runs it inside the distro: posix, sys.platform linux (case-sensitive by default)."""
    with mock.patch.object(travas.sys, "platform", "linux"):
        return travas.decidir(conf, ferramenta, entrada, cwd, nt=False)


class TesteSettingsWsl(unittest.TestCase):
    def setUp(self):
        self.texto = texto_wsl()
        self.cfg = json.loads(self.texto)
        self.partes, self.conf = gancho(self.cfg)

    def test_sem_caminho_do_windows(self):
        self.assertNotIn("\\", self.texto)
        self.assertIsNone(re.search(r"(?<![\w])[A-Za-z]:[\\/]", self.texto))
        for p in self.conf["prot"] + self.conf["lib"] + self.conf["exe"] + [self.conf["py"]]:
            self.assertTrue(p.startswith(("/mnt/c/", "/home/tuneup/")), p)
            self.assertNotIn("\\", p)

    def test_comando_do_gancho(self):
        cmd = self.cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertTrue(cmd.startswith("/usr/bin/python3 -I -BXutf8 /mnt/c/"), cmd)
        self.assertEqual(self.partes[3], "/mnt/c/Users/Ana/.claude/plugins/cache/mkt/tune-up/1.0.0/painel/travas.py")
        self.assertTrue(cmd.endswith(" || exit 2"))

    def test_sandbox_dono_e_segredos(self):
        fs = self.cfg["sandbox"]["filesystem"]
        self.assertEqual(fs["denyWrite"], [DADOS_W + "/" + x for x in sandbox.DONO])
        for x in (".claude", ".ssh", "AppData", ".aws", ".config", ".gnupg"):
            self.assertIn("/mnt/c/Users/*/" + x, fs["denyRead"])
            self.assertIn("Read(//mnt/c/Users/*/%s/**)" % x, self.cfg["permissions"]["deny"])
        self.assertIn(WS_W + "/.env*", fs["denyRead"])
        self.assertIn("Read(/" + WS_W + "/**/.env*)", self.cfg["permissions"]["deny"])

    def test_segredos_na_unidade_do_workspace_e_na_c(self):
        cfg = dict(CFG, workspace="D:\\obras\\loja")
        lido = json.loads(texto_wsl(cfg=cfg))["sandbox"]["filesystem"]["denyRead"]
        self.assertIn("/mnt/d/Users/*/.ssh", lido)
        self.assertIn("/mnt/c/Users/*/.ssh", lido)

    def test_conf_do_gancho(self):
        self.assertIs(self.conf["wsl"], True)
        self.assertEqual(self.conf["py"], PY)
        self.assertEqual(self.conf["exe"], [HF])
        self.assertIn(DADOS_W + "/estudio-dono.json", self.conf["prot"])
        self.assertIn(WS_W + "/.tune-up/painel/dados", self.conf["lib"])

    def test_ler_env_nega_sem_caixa(self):
        """Host: the hook leaves .env to the Read rule. WSL (/mnt has no case): the hook denies .env, .Env, .ENV."""
        host = test_sandbox.gancho(test_sandbox.settings(test_sandbox.fixture()))
        self.assertIsNone(travas.decidir(host, "Read", {"file_path": "/proj [1]/.env"}))
        for nome in (".env", ".Env", ".ENV", ".Env.local", "x.PEM"):
            self.assertEqual(linux(self.conf, "Read", {"file_path": WS_W + "/" + nome})[0], "deny", nome)

    def test_sandbox_variantes_de_caixa(self):
        ler = self.cfg["sandbox"]["filesystem"]["denyRead"]
        for x in (".ENV*", ".Env*", "*.PEM", "*.Key"):
            self.assertIn(WS_W + "/" + x, ler)
            self.assertIn(WS_W + "/**/" + x, ler)
        host = test_sandbox.settings(test_sandbox.fixture())["sandbox"]["filesystem"]["denyRead"]
        self.assertFalse([x for x in host if ".ENV" in x or ".Env" in x])

    def test_permissions_deny_variantes_de_caixa(self):
        negar = self.cfg["permissions"]["deny"]
        for x in (".ENV*", ".Env*", "*.PEM", "*.Pem", "*.KEY", "*.Key"):
            self.assertIn("Read(/%s/**/%s)" % (WS_W, x), negar)
        hnegar = test_sandbox.settings(test_sandbox.fixture())["permissions"]["deny"]
        self.assertFalse([x for x in hnegar if ".ENV" in x or ".Env" in x or "PEM" in x])


class TesteDecidirWsl(unittest.TestCase):
    def setUp(self):
        self.conf = gancho(json.loads(texto_wsl()))[1]

    def test_libera_o_estudio(self):
        qa = "python3 -I %sqa_video.py %s/video.mp4" % (PY, PASTA_W)
        self.assertIsNone(linux(self.conf, "Bash", {"command": qa}))
        self.assertIsNone(linux(self.conf, "Bash", {"command": "%s render %s/comp" % (HF, PASTA_W)}))
        self.assertIsNone(linux(self.conf, "Write", {"file_path": PASTA_W + "/roteiro.md"}))

    def test_nega_caixa_e_nome_curto(self):
        painel = "/mnt/c/Users/Ana/.claude/plugins/cache/mkt/tune-up/1.0.0/PAINEL/travas.py"
        casos = [painel, DADOS_W + "/ESTUDI~1.JSO", DADOS_W + "/HYPERF~1/x", DADOS_W + "/ESTUDIO-DONO.JSON",
                 DADOS_W + "/Aprovados/x", DADOS_W + "/extensoes.JSON", WS_W + "/.TUNE-UP/PAINEL/dados/aprovados/x"]
        for c in casos:
            for ferr, ent in (("Write", {"file_path": c}), ("Edit", {"file_path": c}),
                              ("Bash", {"command": "echo x > " + c})):
                with self.subTest(c=c, ferr=ferr):
                    self.assertEqual(linux(self.conf, ferr, ent)[0], "deny")

    def test_flag_wsl_faz_a_diferenca(self):
        """Without "wsl" (Linux, case-sensitive) the upper-case and 8.3 names passed: the flag is what denies them."""
        conf = gancho(json.loads(texto_wsl(cfg=dict(CFG, painel_dir="C:\\tune-up\\painel"))))[1]
        sem = {k: v for k, v in conf.items() if k != "wsl"}
        self.assertEqual(linux(sem, "Write", {"file_path": "/mnt/c/tune-up/painel/travas.py"})[0], "deny")
        for c in ("/mnt/c/tune-up/PAINEL/travas.py", "/mnt/c/tune-up/Painel/x.py", DADOS_W + "/ESTUDI~1.JSO", DADOS_W + "/HYPERF~1/x"):
            self.assertIsNone(linux(sem, "Write", {"file_path": c}), c)
            self.assertEqual(linux(conf, "Write", {"file_path": c})[0], "deny")
        nucleo = dict(sem, n=[], p=[])  # the Studio's own regex rules aside: the core alone let cmd.exe through
        self.assertIsNone(linux(nucleo, "Bash", {"command": "/mnt/c/Windows/System32/cmd.exe /c echo x"}))
        self.assertEqual(linux(dict(nucleo, wsl=True), "Bash", {"command": "/mnt/c/Windows/System32/cmd.exe /c x"})[0],
                         "deny")

    def test_nega_programa_do_windows(self):
        cmds = ["cmd.exe /c echo x", "/mnt/c/Windows/System32/cmd.exe /c echo x", "cmd /c dir", "powershell -c ls",
                "pwsh -c ls", "wsl ls", "notepad.EXE", "./x.BAT", "run.cmd", "x.ps1", "/mnt/c/Tools/a.Com",
                "ls /mnt/c/windows/system32", "ls /mnt/c/Users/Ana/../../Windows/System32", "ffmpeg -i a.mp4 b.exe",
                "c\"md\".exe /c x", "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"]
        for c in cmds:
            with self.subTest(c=c):
                self.assertEqual(linux(self.conf, "Bash", {"command": c})[0], "deny")

    def test_nega_segredo_do_windows(self):
        casos = [("Read", {"file_path": "/mnt/c/Users/Ana/.CLAUDE/.credentials.json"}),
                 ("Read", {"file_path": "/mnt/c/Users/Ana/APPDAT~1/x"}),
                 ("Grep", {"pattern": "x", "path": "/mnt/c/Users/Ana/.ssh"}),
                 ("Bash", {"command": "cat /mnt/c/Users/Ana/.aws/credentials"}),
                 ("Bash", {"command": "cat ../../../../../../../.gnupg/x"})]
        for ferr, ent in casos:
            with self.subTest(ent=ent):
                cwd = "/mnt/c/Users/Ana/a/b/c/d/e/f" if ".gnupg" in json.dumps(ent) else PASTA_W
                self.assertEqual(linux(self.conf, ferr, ent, cwd)[0], "deny")

    def test_gancho_de_verdade(self):
        """The real hook process (python -I, stdin JSON) with the WSL conf: allows the Studio, denies cmd.exe."""
        cmd = gancho(json.loads(texto_wsl()))[0]

        def rodar(comando):
            entrada = json.dumps({"tool_name": "Bash", "tool_input": {"command": comando}, "cwd": PASTA_W})
            r = subprocess.run([sys.executable, "-I", "-BXutf8", travas.__file__, cmd[4]], input=entrada,
                               capture_output=True, text=True, timeout=20)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] if r.stdout else None
        self.assertIsNone(rodar("python3 -I %sqa_video.py %s/video.mp4" % (PY, PASTA_W)))
        self.assertEqual(rodar("/mnt/c/Windows/System32/cmd.exe /c echo x"), "deny")
        self.assertEqual(rodar("echo x > %s/ESTUDI~1.JSO" % DADOS_W), "deny")

    def test_insistir_do_windows(self):
        with mock.patch.object(travas.time, "sleep") as dormir:
            vezes = []

            def falha():
                vezes.append(1)
                if len(vezes) < 3:
                    raise PermissionError()
                return "ok"
            self.assertEqual(travas._insistir(falha, True), "ok")
            self.assertEqual(len(vezes), 3)
            self.assertEqual(dormir.call_count, 2)
            vezes.clear()
            with self.assertRaises(PermissionError):
                travas._insistir(falha, False)


CURINGA_NEGA = [("Bash", {"command": "cat /mnt/c/proj/.ENV"}), ("Read", {"file_path": WS_W + "/.Env"}),
                ("Bash", {"command": "cat %s/.en?" % WS_W}), ("Bash", {"command": "cat %s/.e*" % WS_W}),
                ("Bash", {"command": "/mnt/c/Win*/System32/cmd.ex? /c echo x"}), ("Bash", {"command": "cmd.ex?"}),
                ("Bash", {"command": "{cmd,x}.exe"}), ("Grep", {"pattern": "x", "glob": ".e*", "path": WS_W}),
                ("Bash", {"command": "ls /mnt/c/Users/*/.s?h"}), ("Bash", {"command": "cat '%s/.E'nv.local" % WS_W}),
                ("Bash", {"command": "cat ~/../../mnt/c/U*/x"}), ("Bash", {"command": "cat /m*/c/x"}),
                ("Bash", {"command": "ls {/mnt/c/Users/Ana/.ssh,x}"}), ("Bash", {"command": "cat %s/x{/../../..,}/.ssh/id" % WS_W}),
                ("Glob", {"pattern": "/mnt/c/Users/*/.aws/*"}), ("Bash", {"command": "echo " + "{a,b}" * 30}),
                # a leading wildcard reaches a dot name through find, grep --include, rg -g, dotglob and the Grep tool
                ("Bash", {"command": "grep -r --include='*nv' x %s" % WS_W}), ("Bash", {"command": "rg --hidden -g '*nv' x %s" % WS_W}),
                ("Bash", {"command": "rg --hidden -g '*.ENV' x"}), ("Bash", {"command": "find %s -name '*nv'" % WS_W}),
                ("Grep", {"pattern": "x", "glob": "*nv", "path": WS_W}), ("Grep", {"pattern": "x", "glob": "*.env", "path": WS_W}),
                ("Glob", {"pattern": "**/*nv"}), ("Bash", {"command": "shopt -s dotglob; cat *nv"}),
                ("Bash", {"command": "GLOBIGNORE=x; cat *nv"}), ("Bash", {"command": "cat %s/*.env.local" % WS_W})]
CURINGA_PASSA = [("Bash", {"command": "ls %s/*.png" % WS_W}), ("Bash", {"command": "cat %s/src/**/*.html" % WS_W}),
                 ("Glob", {"pattern": "**/*.md"}), ("Glob", {"pattern": "**/*.md", "path": WS_W}),
                 ("Bash", {"command": "ls *.png"}), ("Read", {"file_path": WS_W + "/foto [1].png"}),
                 ("Grep", {"pattern": "x", "glob": "*.{md,txt}", "path": WS_W})]


class TesteCuringaWsl(unittest.TestCase):
    """Bash expands globs and braces before running, and /mnt/<letter>/ has no case: the WSL hook decides on what they can reach."""

    def setUp(self):
        self.conf = dict(gancho(json.loads(texto_wsl()))[1], n=[], p=[])  # the core alone (the Studio's rules deny `ls`)

    def test_nega(self):
        for ferr, ent in CURINGA_NEGA:
            with self.subTest(ent=ent):
                self.assertEqual(linux(self.conf, ferr, ent), ("deny", travas.decidir(self.conf, "Bash", {"command": "cmd.exe"})[1]))

    def test_passa(self):
        for ferr, ent in CURINGA_PASSA:
            with self.subTest(ent=ent):
                self.assertIsNone(linux(self.conf, ferr, ent))

    def test_sem_workspace_conhecido_nega_curinga_em_mnt(self):
        conf = dict(self.conf, prot=[p for p in self.conf["prot"] if not p.endswith("painel.json")])
        self.assertEqual(linux(conf, "Bash", {"command": "ls %s/*.png" % WS_W})[0], "deny")
        self.assertIsNone(linux(conf, "Bash", {"command": "ls %s/a.png" % WS_W}))

    def test_host_nem_chama(self):
        """Without "wsl" the new checks never run: same decision as before, on the Mac/Linux and on Windows."""
        host = {k: v for k, v in self.conf.items() if k != "wsl"}
        with mock.patch.object(travas, "_wsl", side_effect=AssertionError("WSL check on host")):
            for ferr, ent in CURINGA_NEGA + CURINGA_PASSA:
                for nt in (False, True):
                    travas.decidir(host, ferr, ent, PASTA_W, nt=nt, realpath=lambda c: c)


class TestePlugin(unittest.TestCase):
    def test_plugin_dir_invalido_recusa_antes(self):
        for ruim in ("/home/tuneup/.claude/plugins/cache/../../../tmp/x", "/tmp/tune-up", "", None,
                     "/home/tuneup/.claude/plugins/cachex/x", "/home/tuneup/.claude/plugins/cache/x/"):
            with self.subTest(ruim=ruim), mock.patch.object(travas_sessao, "settings_da_sessao") as s:
                with self.assertRaises(ErroAcao):
                    travas.argv_travas(acao_wsl(), CFG, wsl=dict(W, plugin_dir=ruim))
                s.assert_not_called()

    def test_caminho_relativo_ou_de_rede_recusa(self):
        for ruim in ("\\\\srv\\share\\loja", "loja", "C:\\a\\..\\b"):
            with self.subTest(ruim=ruim), self.assertRaises(ErroAcao):
                texto_wsl(cfg=dict(CFG, workspace=ruim))


class TesteHostIgual(unittest.TestCase):
    def test_sem_wsl_igual(self):
        acao = trabalho.resolver_travas(test_sandbox.fixture(), test_sandbox.DADOS + "/trabalhos/abc", test_sandbox.EST)
        self.assertEqual(travas.argv_travas(acao, test_sandbox.CFG), travas.argv_travas(acao, test_sandbox.CFG, wsl=None))
        self.assertNotIn('"wsl"', json.dumps(test_sandbox.gancho(test_sandbox.settings(test_sandbox.fixture()))))

    def test_travas_os_intacto_e_threads(self):
        antes = travas.os
        acao_h = trabalho.resolver_travas(test_sandbox.fixture(), test_sandbox.DADOS + "/trabalhos/abc", test_sandbox.EST)
        esperado_w, esperado_h = texto_wsl(), travas.argv_travas(acao_h, test_sandbox.CFG)[1]
        self.assertIs(travas.os, antes)
        erros = []

        def wsl_n():
            for _ in range(30):
                if texto_wsl() != esperado_w:
                    erros.append("wsl")

        def host_n():
            for _ in range(30):
                if travas.argv_travas(acao_h, test_sandbox.CFG)[1] != esperado_h:
                    erros.append("host")
        ts = [threading.Thread(target=f) for f in (wsl_n, host_n, wsl_n, host_n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(erros, [])
        self.assertIs(travas.os, antes)
        self.assertNotIn("/mnt/", esperado_h)


class TesteEstudioEPrompt(unittest.TestCase):
    ACAO = {"_prompt": "Use {estudio_hf} em {trabalho}: {texto}", "_travas": {},
            "params": [{"nome": "texto", "tipo": "texto_longo"}]}

    def test_estudio_da_acao_wsl(self):
        vistos = []
        est = embutidos.estudio_da_acao({}, self.ACAO, hf_pronto=lambda c: vistos.append(c) or True)
        studio = os.path.join(os.path.realpath(os.path.dirname(embutidos.config.PAINEL)), "tune-up-studio")
        self.assertEqual(vistos, [embutidos.chave_do_ambiente(studio)])
        self.assertEqual(est["hf"], wsl.caminho_hf(vistos[0]))
        self.assertFalse(os.path.exists(est["hf"]))  # no os.path.isfile: the binary only exists in the distro
        with self.assertRaises(ErroAcao) as e:
            embutidos.estudio_da_acao({}, self.ACAO, hf_pronto=lambda c: False)
        self.assertEqual(e.exception.codigo, 409)
        self.assertIn("instalar.ps1", str(e.exception))

    def test_prompt_com_pasta_traduzida(self):
        texto = trabalho.montar_prompt(self.ACAO, {"texto": "x"}, PASTA_W, {"hf": HF}, caminho=posixpath)
        self.assertIn(PASTA_W + "/entrada.md", texto)
        self.assertIn(shlex.quote(HF), texto)
        self.assertNotIn("\\", texto)


if __name__ == "__main__":
    unittest.main()
