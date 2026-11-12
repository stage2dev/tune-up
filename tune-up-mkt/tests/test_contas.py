"""contas.py in-process (C7): classification of the real fixtures with an injected command runner and clock."""
import contextlib
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "scripts", "contas.py")
FIX = os.path.join(RAIZ, "tests", "fixtures")
T0 = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)
PLUGIN = ("claude", "plugin", "list", "--json")
MCP = ("claude", "mcp", "list")
COMPOSIO = ("composio", "connections", "list")


def carregar():
    spec = importlib.util.spec_from_file_location("contas_em_processo", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = carregar()
R = C.R


def fx(nome):
    with open(os.path.join(FIX, nome), encoding="utf-8") as f:
        return f.read()


def falso(plugin, mcp, composio):
    """Fake rodar: fixture text (rc 0), a (rc, text) tuple, or an exception to raise. Records the calls."""
    respostas = {PLUGIN: plugin, MCP: mcp, COMPOSIO: composio}
    chamadas = []

    def rodar(args, timeout, cwd=None):
        chave = (os.path.basename(args[0]),) + tuple(args[1:])
        chamadas.append((chave, timeout))
        r = respostas[chave]
        if isinstance(r, BaseException):
            raise r
        return r if isinstance(r, tuple) else (0, r)
    return rodar, chamadas


def which_tudo(nome):
    return "/fake/bin/" + nome


def which_sem_composio(nome):
    return None if nome == "composio" else "/fake/bin/" + nome


def conferir(plugin, mcp, composio, which=which_tudo):
    rodar, _ = falso(plugin, mcp, composio)
    cat = C.ler_catalogo()
    return R.montar(cat, C.conferir_tudo(cat, rodar=rodar, which=which, agora=T0), {}, T0)["servicos"]


def todos_detalhes(servicos):
    for item in servicos.values():
        for c in item["checagens"]:
            yield c["detalhe"]
        for canal in item.get("canais", {}).values():
            for c in canal["checagens"]:
                yield c["detalhe"]


class Cenarios(unittest.TestCase):
    def test_ligado(self):
        s = conferir(fx("plugin_list_ligado.json"), fx("mcp_list_ligado.txt"), fx("composio_connections_ligado.json"))
        for sid in ("composio", "openseo", "claude_ads", "higgsfield", "elevenlabs"):
            self.assertEqual(s[sid]["estado"], "ligado", sid)
        for canal in ("metaads", "googleads", "instagram", "facebook"):
            self.assertEqual(s["composio"]["canais"][canal]["estado"], "ligado", canal)
        # the capture's marketing plugin comes from an anonymized marketplace: only the exact id counts
        self.assertEqual(s["anthropic_marketing"]["estado"], "nao_instalado")
        for sid in ("chrome", "search_console_analytics", "indexnow"):  # manual only, no mark
            self.assertEqual(s[sid]["estado"], "nao_sei", sid)

    def test_falta_autenticar(self):
        s = conferir(fx("plugin_list_ligado.json"), fx("mcp_list_falta_autenticar.txt"),
                     fx("composio_connections_expirado.json"))
        self.assertEqual(s["openseo"]["estado"], "falta_autenticar")
        self.assertEqual(s["composio"]["estado"], "falta_autenticar")
        meta = s["composio"]["canais"]["metaads"]["checagens"][0]
        self.assertEqual((meta["estado"], meta["detalhe"]), ("falta_autenticar", R.D_INATIVA))
        google = s["composio"]["canais"]["googleads"]["checagens"][0]
        self.assertEqual((google["estado"], google["detalhe"]), ("falta_autenticar", R.D_SEM_LINK))

    def test_composio_vazio_falta_autenticar(self):
        s = conferir(fx("plugin_list_ligado.json"), fx("mcp_list_ligado.txt"), fx("composio_connections_vazio.json"))
        self.assertEqual(s["composio"]["cli"], "falta_autenticar")
        self.assertEqual(s["composio"]["canais"]["instagram"]["estado"], "falta_autenticar")

    def test_ausente(self):
        s = conferir(fx("plugin_list_ausente.json"), fx("mcp_list_ausente.txt"), "{}", which=which_sem_composio)
        for sid in ("openseo", "composio", "claude_ads", "anthropic_marketing"):
            self.assertEqual(s[sid]["estado"], "nao_instalado", sid)
        self.assertEqual(s["composio"]["cli"], "nao_instalado")
        self.assertEqual(s["composio"]["mcp"], "nao_instalado")
        for canal in s["composio"]["canais"].values():
            self.assertEqual((canal["estado"], canal["checagens"][0]["detalhe"]), ("nao_instalado", R.D_SEM_COMANDO))

    def test_desligado(self):
        s = conferir(fx("plugin_list_desligado.json"), fx("mcp_list_ligado.txt"), fx("composio_connections_ligado.json"))
        plugin = [c for c in s["openseo"]["checagens"] if c["tipo"] == "plugin"][0]
        self.assertEqual((plugin["estado"], plugin["detalhe"], plugin["papel"]),
                         ("desligado", R.D_DESABILITADO, "informa"))
        self.assertEqual(s["openseo"]["estado"], "ligado")  # the MCP server decides for openseo
        s = conferir(fx("plugin_list_desligado.json").replace('"enabled": true', '"enabled": false'),
                     fx("mcp_list_ligado.txt"), "{}")
        self.assertEqual(s["claude_ads"]["estado"], "desligado")

    def test_seis_estados_mcp(self):
        texto = fx("mcp_list_estados.txt")
        esperado = {"srv-connected": "ligado", "srv-needs-auth": "falta_autenticar",
                    "srv-not-configured": "falta_autenticar", "srv-failed": "falhou",
                    "srv-pending": "desligado", "srv-disabled": "desligado"}
        for alvo, estado in esperado.items():
            with self.subTest(alvo=alvo):
                self.assertEqual(R.classificar_mcp(texto, alvo)[0], estado)
        self.assertEqual(len(R.ESTADOS_MCP), 6)
        self.assertEqual(R.classificar_mcp(texto, "srv-absent"), ("nao_instalado", R.D_SEM_SERVIDOR))

    def test_mcp_texto_desconhecido_numa_linha_achada(self):
        linha = "srv-x: https://example.test/mcp (HTTP) - ? Warming up\n"
        self.assertEqual(R.classificar_mcp(linha, "srv-x")[0], "nao_sei")
        falha = "srv-y: https://example.test/mcp (HTTP) - ✘ Failed to connect: Connected? no - reset\n"
        self.assertEqual(R.classificar_mcp(falha, "srv-y")[0], "falhou")

    def test_formatos_desconhecidos_nao_sei(self):
        s = conferir(fx("plugin_list_ligado.json"), fx("mcp_list_formato_desconhecido.txt"),
                     fx("composio_connections_formato_desconhecido.json"))
        for sid in ("openseo", "composio", "higgsfield", "elevenlabs"):
            mcp = [c for c in s[sid]["checagens"] if c["tipo"] == "mcp"][0]
            self.assertEqual((mcp["estado"], mcp["detalhe"]), ("nao_sei", R.D_FORMATO), sid)
            self.assertNotEqual(s[sid]["estado"], "ligado", sid)
        self.assertEqual(s["composio"]["cli"], "nao_sei")
        for canal in s["composio"]["canais"].values():
            self.assertEqual(canal["estado"], "nao_sei")
        for ruim in ('{"plugins": []}', "not json", '[{"name": "openseo@openseo", "enabled": true}]'):
            self.assertEqual(R.classificar_plugin(ruim, "openseo@")[0], "nao_sei", ruim)
        for ruim in ('{"metaads": [{"state": "ACTIVE"}]}', '{"metaads": "ACTIVE"}', "x"):
            self.assertEqual(R.classificar_composio(ruim, "metaads")[0], "nao_sei", ruim)

    def test_timeout_e_saida_nao_zero_nao_sei(self):
        rodar, chamadas = falso(fx("plugin_list_ligado.json"), subprocess.TimeoutExpired("claude", 60),
                                (1, fx("composio_connections_ligado.json")))
        cat = C.ler_catalogo()
        auto = C.conferir_tudo(cat, rodar=rodar, which=which_tudo, agora=T0)
        s = R.montar(cat, auto, {}, T0)["servicos"]
        mcp = [c for c in s["openseo"]["checagens"] if c["tipo"] == "mcp"][0]
        self.assertEqual((mcp["estado"], mcp["detalhe"]), ("nao_sei", R.D_TEMPO))
        self.assertEqual(s["composio"]["canais"]["metaads"]["checagens"][0]["detalhe"], R.D_SAIDA)
        self.assertEqual(s["composio"]["cli"], "nao_sei")
        self.assertEqual(s["openseo"]["estado"], "nao_sei")
        # each distinct command runs once, with its own timeout
        self.assertEqual(sorted(chamadas), sorted([(PLUGIN, 20), (MCP, 60), (COMPOSIO, 20)]))

    def test_composio_cli_e_mcp_separados(self):
        s = conferir(fx("plugin_list_ligado.json"), fx("mcp_list_falta_autenticar.txt"),
                     fx("composio_connections_ligado.json"))
        self.assertEqual((s["composio"]["cli"], s["composio"]["mcp"]), ("ligado", "falta_autenticar"))
        self.assertEqual(s["composio"]["estado"], "ligado")  # modo qualquer: either path is enough

    def test_detalhe_so_vocabulario_fixo(self):
        for args in ((fx("plugin_list_ligado.json"), fx("mcp_list_ligado.txt"), fx("composio_connections_ligado.json")),
                     ("garbage", "garbage", "garbage")):
            for d in todos_detalhes(conferir(*args)):
                self.assertIn(d, R.DETALHES)


class Marcas(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-contas-"))
        self.env = mock.patch.dict(os.environ, {"HOME": self.tmp, "USERPROFILE": self.tmp})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rodar(self, *args, agora=T0, plugin="plugin_list_ligado.json", mcp="mcp_list_ligado.txt"):
        rodar, _ = falso(fx(plugin), fx(mcp), fx("composio_connections_ligado.json"))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = C.main(list(args) + ["--raiz", self.tmp], agora=agora, rodar=rodar, which=which_tudo)
        return rc, out.getvalue(), err.getvalue()

    def contas(self):
        with open(os.path.join(self.tmp, ".tune-up", "mkt", "contas.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_marca_guarda_data_e_via_e_vence_em_7_dias(self):
        self.assertEqual(self.rodar("marcar", "chrome", "ligado", "--prova", "manual")[0], 0)
        chrome = self.contas()["servicos"]["chrome"]
        self.assertEqual(chrome["marca"], {"estado": "ligado", "prova": "manual", "via": "manual",
                                           "conferido_em": "2026-11-12T12:00:00Z"})
        self.assertEqual(chrome["estado"], "ligado")
        self.rodar("status", agora=T0 + timedelta(days=6, hours=23))
        self.assertEqual(self.contas()["servicos"]["chrome"]["estado"], "ligado")
        self.rodar("status", agora=T0 + timedelta(days=7, seconds=1))
        chrome = self.contas()["servicos"]["chrome"]
        self.assertEqual(chrome["estado"], "conferir_de_novo")
        self.assertEqual(chrome["checagens"][0]["detalhe"], R.D_VENCIDA)

    def test_marca_de_canal_e_via_mcp(self):
        self.rodar("status")
        self.assertEqual(self.rodar("marcar", "composio:metaads", "falta_autenticar", "--prova", "connections_ok",
                                    "--via", "cli")[0], 0)
        meta = self.contas()["servicos"]["composio"]["canais"]["metaads"]
        self.assertEqual(meta["marca"]["via"], "cli")
        self.assertEqual(meta["estado"], "falta_autenticar")  # a mark may lower, never raise

    def test_marca_nao_promove_checagem_automatica(self):
        self.rodar("status", plugin="plugin_list_ausente.json", mcp="mcp_list_ausente.txt")
        self.rodar("marcar", "openseo", "ligado", "--prova", "whoami_ok", "--via", "mcp")
        item = self.contas()["servicos"]["openseo"]
        self.assertEqual(item["estado"], "nao_instalado")
        self.assertEqual(item["marca"]["prova"], "whoami_ok")

    def test_marca_antes_do_status_nao_promove(self):
        self.rodar("marcar", "openseo", "ligado", "--prova", "whoami_ok")
        self.assertEqual(self.contas()["servicos"]["openseo"]["estado"], "nao_sei")

    def test_marca_sobrevive_ao_status(self):
        self.rodar("marcar", "indexnow", "ligado", "--prova", "manual")
        self.rodar("status", agora=T0 + timedelta(days=1))
        self.assertEqual(self.contas()["servicos"]["indexnow"]["marca"]["conferido_em"], "2026-11-12T12:00:00Z")

    def test_id_desconhecido_exit_2(self):
        rc, _, err = self.rodar("marcar", "nao-existe", "ligado", "--prova", "manual")
        self.assertEqual(rc, 2)
        self.assertNotIn("nao-existe", err)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".tune-up")))

    def test_contas_json_invalido_e_substituido(self):
        caminho = os.path.join(self.tmp, ".tune-up", "mkt", "contas.json")
        os.makedirs(os.path.dirname(caminho))
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("{not json")
        rc, _, err = self.rodar("status")
        self.assertEqual(rc, 0)
        self.assertIn("replaced", err)
        self.assertEqual(self.contas()["versao"], 1)

    def test_nada_da_saida_dos_comandos_e_gravado(self):
        self.rodar("status")
        with open(os.path.join(self.tmp, ".tune-up", "mkt", "contas.json"), encoding="utf-8") as f:
            texto = f.read()
        for bruto in ("example.test", "alpha-one", "word_id", "https://", "installPath", "/home/user"):
            self.assertNotIn(bruto, texto)

    def test_falta_em_portugues(self):
        os.makedirs(os.path.join(self.tmp, ".config", "tune-up"))
        with open(os.path.join(self.tmp, ".config", "tune-up", "user.json"), "w", encoding="utf-8") as f:
            json.dump({"language": "pt-BR"}, f)
        self.rodar("status", mcp="mcp_list_falta_autenticar.txt")
        rc, out, _ = self.rodar("falta", "--json")
        self.assertEqual(rc, 0)
        lista = {i["id"]: i for i in json.loads(out)["itens"]}
        cat = {s["id"]: s for s in C.ler_catalogo()["servicos"]}
        self.assertEqual(lista["openseo"]["passos"], [cat["openseo"]["autenticar"]["pt"]])
        self.assertIn(cat["chrome"]["cadastro_url"], lista["chrome"]["passos"])
        self.assertNotIn("claude_ads", lista)
        self.assertNotIn("composio:metaads", lista)


if __name__ == "__main__":
    unittest.main()
