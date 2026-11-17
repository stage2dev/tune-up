"""contas.py end to end (C8, C11): subprocess with HOME/USERPROFILE and PATH pointing to a temp dir."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "scripts", "contas.py")
SEGREDOS = ("oseo_abcdefgh", "sk-abcdefgh", "Bearer abcdefgh", "deadbeef" * 5, "Zm9vYmFyYmF6cXV4" * 2 + "Zm9v",
            "fulano@exemplo.com")
HEX32 = "deadbeef" * 4


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-contas-cli-"))
        self.env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_DATA")}
        # nothing installed: PATH holds only an empty temp dir; ~ resolves to tmp on POSIX and Windows
        self.env.update({"HOME": self.tmp, "USERPROFILE": self.tmp, "PATH": self.tmp})
        self.mkt = os.path.join(self.tmp, ".tune-up", "mkt")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_(self, *args):
        r = subprocess.run([sys.executable, SCRIPT] + list(args) + ["--raiz", self.tmp], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", env=self.env, timeout=30)
        return r.returncode, r.stdout, r.stderr

    def ler(self, nome):
        with open(os.path.join(self.mkt, nome), encoding="utf-8") as f:
            return f.read()


class NadaInstalado(Base):
    def test_status_tudo_nao_instalado_ou_nao_sei(self):
        rc, out, err = self.run_("status")
        self.assertEqual(rc, 0, err)
        for linha in out.splitlines()[1:]:
            self.assertIn(linha.split()[2], ("nao_instalado", "nao_sei"), linha)
        dados = json.loads(self.ler("contas.json"))
        self.assertEqual(len(dados["servicos"]), 9)
        for sid, item in dados["servicos"].items():
            self.assertIn(item["estado"], ("nao_instalado", "nao_sei"), sid)
            for canal in item.get("canais", {}).values():
                self.assertEqual(canal["estado"], "nao_instalado")
        if os.name != "nt":
            self.assertEqual(os.stat(os.path.join(self.mkt, "contas.json")).st_mode & 0o777, 0o600)

    def test_status_json(self):
        rc, out, _ = self.run_("status", "--json")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["servicos"]["composio"]["cli"], "nao_instalado")

    def test_falta_lista_tudo(self):
        self.assertEqual(self.run_("falta", "--json")[0], 1)  # no status yet
        self.run_("status")
        rc, out, _ = self.run_("falta", "--json")
        self.assertEqual(rc, 0)
        ids = {i["id"] for i in json.loads(out)["itens"]}
        self.assertEqual(len(ids), 13)  # 9 services + 4 Composio channels
        self.assertIn("composio:metaads", ids)


class Segredos(Base):
    def assert_recusado(self, args, valor):
        rc, out, err = self.run_(*args)
        self.assertEqual(rc, 2, args)
        self.assertNotIn(valor, out + err)
        return out + err

    def test_segredos_e_email_recusados_sem_eco_nem_escrita(self):
        for v in SEGREDOS:
            for args in (["config", "--site", v], ["config", "--canais", "instagram," + v],
                         ["config", "--site=" + v], ["marcar", v, "ligado", "--prova", "manual"],
                         ["marcar", "chrome", "ligado", "--prova", v], ["status", "--json", v]):
                with self.subTest(args=args):
                    self.assert_recusado(args, v)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".tune-up")))

    def test_arquivos_nao_tem_valor_recusado(self):
        self.assertEqual(self.run_("config", "--site", "https://example.com", "--canais", "instagram")[0], 0)
        self.assertEqual(self.run_("marcar", "chrome", "ligado", "--prova", "manual")[0], 0)
        antes = (self.ler("config.json"), self.ler("contas.json"))
        for v in SEGREDOS:
            self.assert_recusado(["config", "--site", "https://example.com/" + v], v)
            self.assert_recusado(["marcar", "chrome", "ligado", "--prova", "manual", "--via", v], v)
        depois = (self.ler("config.json"), self.ler("contas.json"))
        self.assertEqual(antes, depois)
        for v in SEGREDOS:
            for texto in depois:
                self.assertNotIn(v, texto)

    def test_site_com_credencial_ou_chave_na_query(self):
        for url in ("https://u:p@example.com", "https://example.com/?token=abc", "https://example.com/?api_key=x",
                    "ftp://example.com", "example.com", "https://example.com/?secret=1"):
            with self.subTest(url=url):
                rc, out, err = self.run_("config", "--site", url)
                self.assertEqual(rc, 2)
                self.assertNotIn(url, out + err)
        self.assertFalse(os.path.exists(os.path.join(self.mkt, "config.json")))

    def test_indexnow_aceita_chave_no_proprio_campo(self):
        rc, _, err = self.run_("config", "--indexnow-key", HEX32, "--site", "https://example.com")
        self.assertEqual(rc, 0, err)
        cfg = json.loads(self.ler("config.json"))
        self.assertEqual(cfg, {"credit_ask_above": 2000, "site": "https://example.com", "indexnow_key": HEX32})
        self.assertEqual(self.run_("config", "--indexnow-key=" + HEX32)[0], 0)
        for ruim in ("short", "a" * 129, "has space here", "bad_char_x"):
            self.assertEqual(self.run_("config", "--indexnow-key", ruim)[0], 2, ruim)
        self.assertEqual(self.run_("config", "--site", HEX32)[0], 2)  # only its own field is exempt
        rc, out, _ = self.run_("config")
        self.assertEqual(json.loads(out)["indexnow_key"], HEX32)
        self.assertIn("PUBLIC", subprocess.run([sys.executable, SCRIPT, "config", "--help"], capture_output=True,
                                               text=True, env=self.env).stdout)

    def test_prova_so_tres_valores(self):
        for prova in ("whoami_ok", "connections_ok", "manual"):
            self.assertEqual(self.run_("marcar", "chrome", "ligado", "--prova", prova)[0], 0, prova)
        for prova in ("I checked it", "ok", "WHOAMI_OK", ""):
            self.assertEqual(self.run_("marcar", "chrome", "ligado", "--prova", prova)[0], 2, prova)
        self.assertEqual(json.loads(self.ler("contas.json"))["servicos"]["chrome"]["marca"]["prova"], "manual")

    def test_credit_ask_above(self):
        self.assertEqual(self.run_("config", "--credit-ask-above", "500")[0], 0)
        self.assertEqual(json.loads(self.ler("config.json"))["credit_ask_above"], 500)
        self.assertEqual(self.run_("config", "--credit-ask-above", "-1")[0], 2)


@unittest.skipIf(shutil.which("sh") is None, "no sh on this machine")
class Lancador(unittest.TestCase):
    def test_import_irmao_pelo_scripts_py(self):
        tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-contas-py-"))
        try:
            env = {k: v for k, v in os.environ.items() if k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_DATA")}
            env.update({"HOME": tmp, "USERPROFILE": tmp})
            r = subprocess.run(["sh", "scripts/py", "scripts/contas.py", "config", "--site", "https://example.com",
                                "--raiz", tmp], cwd=RAIZ, capture_output=True, text=True, env=env, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            with open(os.path.join(tmp, ".tune-up", "mkt", "config.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["site"], "https://example.com")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
