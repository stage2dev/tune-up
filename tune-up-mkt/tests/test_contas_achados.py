"""contas.py review round 1 (H1, H2, M1-M5, S1-S4, L1-L4): each test was red on the first version."""
import contextlib
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

from tests.test_contas import C, R, T0, SCRIPT, PLUGIN, MCP, COMPOSIO, fx, which_tudo

CAT = C.ler_catalogo()


def rodador(plugin, mcp, composio, cwds=None, durante=None):
    respostas = {PLUGIN: plugin, MCP: mcp, COMPOSIO: composio}

    def rodar(args, timeout, cwd=None):
        chave = (os.path.basename(args[0]),) + tuple(args[1:])
        if cwds is not None:
            cwds.append(cwd)
        if durante and chave == MCP:
            durante()
        return 0, respostas[chave]
    return rodar


def servicos(plugin, mcp, composio, which=which_tudo):
    auto = C.conferir_tudo(CAT, rodar=rodador(plugin, mcp, composio), which=which, agora=T0, raiz="/x")
    return R.montar(CAT, auto, {}, T0)["servicos"]


def plugins(*ids):
    return json.dumps([{"id": i, "enabled": True} for i in ids])


class Decide(unittest.TestCase):  # H2, M1, M4
    def test_openseo_so_pelo_mcp_e_ligado(self):
        s = servicos(fx("plugin_list_ausente.json"), fx("mcp_list_ligado.txt"), "{}")
        self.assertEqual(s["openseo"]["estado"], "ligado")
        papel = {c["tipo"]: c["papel"] for c in s["openseo"]["checagens"] if c["tipo"] in R.AUTOMATICOS}
        self.assertEqual(papel, {"plugin": "informa", "mcp": "decide"})

    def test_composio_so_pela_cli_e_ligado(self):
        s = servicos(fx("plugin_list_ausente.json"), fx("mcp_list_ausente.txt"), fx("composio_connections_ligado.json"))
        c = s["composio"]
        self.assertEqual((c["estado"], c["cli"], c["mcp"]), ("ligado", "ligado", "nao_instalado"))

    def test_marketing_conectores_so_informam(self):
        for pid in ("marketing@knowledge-work-plugins", "marketing@synced"):
            s = servicos(plugins(pid), fx("mcp_list_falta_autenticar.txt"), "{}")
            self.assertEqual(s["anthropic_marketing"]["estado"], "ligado", pid)

    def test_plugin_de_outro_marketplace_nao_conta(self):
        s = servicos(plugins("marketing@some-other-marketplace", "openseo@elsewhere"), fx("mcp_list_ausente.txt"), "{}")
        self.assertEqual(s["anthropic_marketing"]["estado"], "nao_instalado")

    def test_mcp_casa_pelo_nome_nao_pela_url(self):
        linha = "my-docs: https://docs.example.com/openseo-guide/mcp - ✔ Connected\n"
        self.assertEqual(R.classificar_mcp(linha, "openseo")[0], "nao_instalado")
        self.assertEqual(R.classificar_mcp("openseoish: https://x.test/mcp - ✔ Connected\n", "openseo")[0],
                         "nao_instalado")
        self.assertEqual(R.classificar_mcp("seo: https://app.openseo.so/mcp (HTTP) - ✔ Connected\n", "openseo",
                                           host="app.openseo.so")[0], "ligado")
        self.assertEqual(R.classificar_mcp("seo: https://app.openseo.so.evil.test/mcp - ✔ Connected\n", "openseo",
                                           host="app.openseo.so")[0], "nao_instalado")
        cmd = "x-openseo: node -e x - Connected - ! Needs authentication\n"
        self.assertEqual(R.classificar_mcp(cmd, "openseo")[0], "falta_autenticar")


class Pasta(unittest.TestCase):  # H1, S2
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-pasta-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_comandos_rodam_na_raiz(self):
        cwds = []
        rodar = rodador(fx("plugin_list_ligado.json"), fx("mcp_list_ligado.txt"), "{}", cwds)
        C.conferir_tudo(CAT, rodar=rodar, which=which_tudo, agora=T0, raiz=self.tmp)
        self.assertEqual(len(cwds), 3)
        self.assertEqual(set(cwds), {self.tmp})

    def exe(self, pasta):
        os.makedirs(pasta, exist_ok=True)
        p = os.path.join(pasta, "claude" + (".bat" if os.name == "nt" else ""))
        with open(p, "w") as f:
            f.write("#!/bin/sh\n")
        os.chmod(p, 0o755)
        return p

    def test_which_ignora_cwd_e_raiz(self):
        raiz, cwd, bin_ = (os.path.join(self.tmp, n) for n in ("raiz", "cwd", "bin"))
        self.exe(raiz), self.exe(cwd)
        bom = self.exe(bin_)
        path = os.pathsep.join([raiz, cwd, ".", "", "relativo", bin_])
        achado = C.A.achar("claude", raiz, path=path, cwd=cwd)
        self.assertIsNotNone(achado)
        # PATHEXT supplies the extension casing (.BAT vs .bat); same file on Windows
        self.assertEqual(os.path.normcase(achado), os.path.normcase(bom))
        self.assertIsNone(C.A.achar("claude", raiz, path=os.pathsep.join([raiz, cwd]), cwd=cwd))

    @unittest.skipIf(os.name == "nt", "fake executable is a POSIX shell script")
    def test_status_de_outra_pasta(self):
        bin_, a, b = (os.path.join(self.tmp, n) for n in ("bin", "projA", "projB"))
        for p in (bin_, a, b):
            os.makedirs(p)
        open(os.path.join(a, "tem-openseo"), "w").close()
        with open(os.path.join(bin_, "claude"), "w") as f:
            f.write("#!/bin/sh\nif [ \"$1\" = plugin ]; then echo '[]'; exit 0; fi\n"
                    "if [ -f ./tem-openseo ]; then echo 'plugin:openseo:openseo: https://app.openseo.so/mcp (HTTP)"
                    " - ✔ Connected'; else echo 'other: https://example.test/mcp (HTTP) - ✔ Connected'; fi\n")
        os.chmod(os.path.join(bin_, "claude"), 0o755)
        env = dict(os.environ, HOME=self.tmp, PATH=bin_)
        env.pop("CLAUDE_PROJECT_DIR", None)
        for cwd, raiz, esperado in ((a, b, "nao_instalado"), (b, a, "ligado")):
            r = subprocess.run([sys.executable, SCRIPT, "status", "--json", "--raiz", raiz], cwd=cwd, env=env,
                               capture_output=True, text=True, encoding="utf-8", timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["servicos"]["openseo"]["estado"], esperado, raiz)


class EmProcesso(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-proc-"))
        self.env = mock.patch.dict(os.environ, {"HOME": self.tmp, "USERPROFILE": self.tmp})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def main(self, *args, agora=T0, rodar=None):
        rodar = rodar or rodador(fx("plugin_list_ligado.json"), fx("mcp_list_ligado.txt"),
                                 fx("composio_connections_ligado.json"))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = C.main(list(args) + ["--raiz", self.tmp], agora=agora, rodar=rodar, which=which_tudo)
        return rc, out.getvalue(), err.getvalue()

    def contas(self):
        with open(os.path.join(self.tmp, ".tune-up", "mkt", "contas.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_marcar_durante_status_nao_se_perde(self):  # M2
        def marcar():
            C.main(["marcar", "chrome", "ligado", "--prova", "manual", "--raiz", self.tmp], agora=T0)
        rodar = rodador(fx("plugin_list_ligado.json"), fx("mcp_list_ligado.txt"), "{}", durante=marcar)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(C.main(["status", "--raiz", self.tmp], agora=T0, rodar=rodar, which=which_tudo), 0)
        self.assertEqual(self.contas()["servicos"]["chrome"]["marca"]["prova"], "manual")
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".tune-up", "mkt", "contas.json.lock")))

    def test_conta_separada_do_estado(self):  # M3
        self.main("status")
        s = self.contas()["servicos"]
        self.assertEqual((s["openseo"]["estado"], s["openseo"]["conta"]), ("ligado", "nao_conferida"))
        self.assertEqual(s["claude_ads"]["conta"], "nao_se_aplica")
        self.assertEqual((s["chrome"]["estado"], s["chrome"]["conta"]), ("nao_sei", "nao_conferida"))
        rc, out, _ = self.main("falta", "--json")
        itens = json.loads(out)["itens"]
        ids = [i["id"] for i in itens]
        self.assertIn("openseo", ids)
        self.assertEqual(itens[ids.index("openseo")]["conta"], "nao_conferida")
        self.assertGreater(ids.index("openseo"), ids.index("chrome"))  # softer items come after
        self.main("marcar", "openseo", "ligado", "--prova", "whoami_ok")
        self.main("marcar", "chrome", "ligado", "--prova", "manual")
        s = self.contas()["servicos"]
        self.assertEqual(s["openseo"]["conta"], "conferida")
        self.assertEqual((s["chrome"]["estado"], s["chrome"]["conta"]), ("ligado", "confirmada_pelo_dono"))
        self.main("status", agora=T0 + timedelta(days=8))
        s = self.contas()["servicos"]
        self.assertEqual((s["openseo"]["estado"], s["openseo"]["conta"]), ("ligado", "conferir_de_novo"))
        self.assertEqual((s["chrome"]["estado"], s["chrome"]["conta"]), ("conferir_de_novo", "conferir_de_novo"))

    def test_falta_reconstroi_e_exige_status_recente(self):  # L4
        rc, _, err = self.main("falta")
        self.assertEqual(rc, 1)
        self.assertIn("status", err)
        self.main("status", rodar=rodador(fx("plugin_list_ausente.json"), fx("mcp_list_ausente.txt"), "{}"))
        dados = self.contas()
        dados["servicos"]["openseo"]["estado"] = "ligado"  # tampered: the checks still say nao_instalado
        with open(os.path.join(self.tmp, ".tune-up", "mkt", "contas.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f)
        rc, out, _ = self.main("falta", "--json", agora=T0 + timedelta(minutes=30))
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["minutos"], 30)
        self.assertIn("openseo", [i["id"] for i in json.loads(out)["itens"]])
        rc, out, _ = self.main("falta", agora=T0 + timedelta(minutes=30))
        self.assertIn("30", out.splitlines()[0])
        self.assertEqual(self.main("falta", agora=T0 + timedelta(hours=25))[0], 1)

    def test_aviso_no_json_quando_substituido(self):  # L3
        os.makedirs(os.path.join(self.tmp, ".tune-up", "mkt"))
        with open(os.path.join(self.tmp, ".tune-up", "mkt", "contas.json"), "w") as f:
            f.write("{bad")
        rc, out, _ = self.main("status", "--json")
        self.assertEqual(rc, 0)
        self.assertIn("aviso", json.loads(out))


class Cli(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-cli2-"))
        self.env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_DATA")}
        self.env.update({"HOME": self.tmp, "USERPROFILE": self.tmp, "PATH": self.tmp})
        self.raiz = os.path.join(self.tmp, "p")
        os.makedirs(self.raiz)

    def tearDown(self):
        for pasta, dirs, _ in os.walk(self.tmp):
            for d in dirs:
                os.chmod(os.path.join(pasta, d), 0o700)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_(self, *args, raiz=None):
        r = subprocess.run([sys.executable, SCRIPT] + list(args) + ["--raiz", raiz or self.raiz], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=self.env, timeout=30)
        return r.returncode, r.stdout, r.stderr

    def cfg(self):
        with open(os.path.join(self.raiz, ".tune-up", "mkt", "config.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_caminhos_longos_comuns(self):  # M5
        longa = os.path.join(self.raiz, "home", "user", "projects", "mycompany", "website")
        os.makedirs(longa)
        self.assertEqual(self.run_("config", "--site", "https://example.com", raiz=longa)[0], 0)
        url = "https://example.com/" + "/".join(["blog", "marketing", "digital", "novembro2026"])
        rc, _, err = self.run_("config", "--site", url)
        self.assertEqual(rc, 0, err)
        self.assertEqual(self.cfg()["site"], url)

    @unittest.skipIf(os.name == "nt", "symlinks need extra rights on Windows")
    def test_symlink_recusado(self):  # S1
        fora = os.path.join(self.tmp, "fora.json")
        with open(fora, "w") as f:
            f.write('{"site": "https://example.com", "x": "FOREIGN-CONTENT"}')
        mkt = os.path.join(self.raiz, ".tune-up", "mkt")
        os.makedirs(mkt)
        os.symlink(fora, os.path.join(mkt, "config.json"))
        os.symlink(fora, os.path.join(mkt, "contas.json"))
        for args in (("config", "--site", "https://example.test"), ("config",), ("status",), ("falta",),
                     ("marcar", "chrome", "ligado", "--prova", "manual")):
            rc, out, err = self.run_(*args)
            self.assertEqual(rc, 2, args)
            self.assertNotIn("FOREIGN", out + err, args)
        with open(fora) as f:
            self.assertIn("FOREIGN", f.read())
        outro = os.path.join(self.tmp, "q")
        os.makedirs(os.path.join(self.tmp, "alvo"))
        os.makedirs(outro)
        os.symlink(os.path.join(self.tmp, "alvo"), os.path.join(outro, ".tune-up"))
        self.assertEqual(self.run_("config", "--site", "https://example.test", raiz=outro)[0], 2)
        self.assertEqual(os.listdir(os.path.join(self.tmp, "alvo")), [])

    def test_config_so_chaves_conhecidas(self):  # S1
        mkt = os.path.join(self.raiz, ".tune-up", "mkt")
        os.makedirs(mkt)
        with open(os.path.join(mkt, "config.json"), "w") as f:
            json.dump({"site": "https://example.com", "x": "UNKNOWN-KEY"}, f)
        rc, out, _ = self.run_("config")
        self.assertEqual((rc, json.loads(out)), (0, {"site": "https://example.com"}))
        self.run_("config", "--credit-ask-above", "10")
        self.assertNotIn("x", self.cfg())

    def test_site_e_canais_estritos(self):  # S3
        token = "tok" + "_" + "a1" * 20
        for url in ("https://example.com/#access_" + "token=abc", "https://example.com/cb?code=abc&state=xyz",
                    "https://example.com/" + token, "https://example.com/a b", "https://example.com/?",
                    "https://example.com/x!y"):
            rc, out, err = self.run_("config", "--site", url)
            self.assertEqual(rc, 2, url)
            self.assertNotIn(url, out + err)
        rc, out, err = self.run_("config", "--canais", "instagram,meu canal livre")
        self.assertEqual(rc, 2)
        self.assertNotIn("livre", out + err)
        self.assertEqual(self.run_("config", "--canais", "metaads,googleads,instagram,facebook,seo,video,voz")[0], 0)
        self.assertEqual(self.cfg()["canais"], ["metaads", "googleads", "instagram", "facebook", "seo", "video", "voz"])

    def test_indexnow_gerada_e_prefixos_recusados(self):  # S4
        rc, out, err = self.run_("config", "--gerar-indexnow")
        self.assertEqual(rc, 0, err)
        chave = self.cfg()["indexnow_key"]
        self.assertRegex(chave, r"^[0-9a-f]{32}$")
        self.assertIn(chave, out)
        self.run_("config", "--gerar-indexnow")
        self.assertEqual(self.cfg()["indexnow_key"], chave)  # an existing key is kept
        for v in ("sk" + "-abcdefgh12", "AKIA" + "ABCDEFGH1234", "xox" + "b-12345678", "ghp" + "_abcdefgh12",
                  "oseo" + "_abcdefgh"):
            rc, out, err = self.run_("config", "--indexnow-key", v)
            self.assertEqual(rc, 2, v)
            self.assertNotIn(v, out + err)
        self.assertEqual(self.cfg()["indexnow_key"], chave)

    def test_erro_de_argumento_sem_eco(self):  # L1
        for args in (("status", "--bogus", "VALOR-ECOADO"), ("marcar", "chrome", "ligado", "--prova", "VALOR-ECOADO"),
                     ("status", "--indexnow-key", "deadbeef" * 4)):
            rc, out, err = self.run_(*args)
            self.assertEqual(rc, 2, args)
            self.assertNotIn(args[-1], out + err, args)

    def test_prova_e_via_coerentes(self):  # L2
        self.assertEqual(self.run_("marcar", "openseo", "ligado", "--prova", "whoami_ok", "--via", "cli")[0], 2)
        self.assertEqual(self.run_("marcar", "chrome", "ligado", "--prova", "manual", "--via", "mcp")[0], 2)
        self.assertEqual(self.run_("marcar", "composio:metaads", "ligado", "--prova", "connections_ok")[0], 0)
        with open(os.path.join(self.raiz, ".tune-up", "mkt", "contas.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["servicos"]["composio"]["canais"]["metaads"]["marca"]["via"], "cli")

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "needs POSIX non-root")
    def test_falha_de_escrita_sem_traceback(self):  # L3
        mkt = os.path.join(self.raiz, ".tune-up", "mkt")
        os.makedirs(mkt)
        os.chmod(mkt, stat.S_IRUSR | stat.S_IXUSR)
        rc, _, err = self.run_("marcar", "chrome", "ligado", "--prova", "manual")
        self.assertEqual(rc, 1)
        self.assertNotIn("Traceback", err)
        self.assertEqual(len(err.strip().splitlines()), 1)



class Skill(unittest.TestCase):  # L5
    def test_frontmatter(self):
        caminho = os.path.join(os.path.dirname(os.path.dirname(SCRIPT)), "skills", "connect", "SKILL.md")
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
        topo = texto.split("---")[1]
        self.assertNotIn("disable-model-invocation", topo)
        linha = [x for x in topo.splitlines() if x.startswith("allowed-tools:")][0]
        regras = [r.strip() for r in linha.split(":", 1)[1].split("),") if r.strip()]
        prefixo = 'Bash(sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/contas.py '
        for r in regras:
            self.assertTrue(r.startswith(prefixo), r)
            self.assertIn(r[len(prefixo):].rstrip(")").split()[0], ("status", "marcar", "falta", "config"), r)
        for termo in ("--gerar-indexnow", "`conta`", "metaads", "googleads", "`voz`", "curl ... | sh"):
            self.assertIn(termo, texto)
        self.assertNotIn("--via mcp|cli", texto)


if __name__ == "__main__":
    unittest.main()
