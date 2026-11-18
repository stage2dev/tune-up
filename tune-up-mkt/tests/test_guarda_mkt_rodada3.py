"""guarda_mkt.py: third review round (server names with a suffix, deep/huge inputs within the hook timeout,
Graph write next to a GET in another command segment). Big strings are built at runtime."""
import importlib.util
import json
import os
import stat
import subprocess
import sys
import time
import unittest
from unittest import mock

from .apoio_mkt import SCRIPT, Base

MULTI = "mcp__composio__COMPOSIO_MULTI_EXECUTE_TOOL"
GRAPH = "https://graph.facebook.com/v20.0/"


class ServidorComSufixo(Base):
    # F1
    def mcp(self, nome, ti=None):
        return self.rodar({"tool_name": nome, "tool_input": ti or {"id": "1"}})

    def test_servidor_de_anuncios_com_sufixo_bloqueia(self):
        for nome in ("mcp__meta-ads-mcp__update_campaign", "mcp__fb-ads-mcp-server__update_adset",
                     "mcp__facebook-ads-mcp-server__update_adset", "mcp__metaads-mcp__create_ad"):
            with self.subTest(nome=nome):
                self.assertEqual(self.mcp(nome), "bloquear")

    def test_google_ads_com_sufixo_pergunta(self):
        self.assertEqual(self.mcp("mcp__google-ads-mcp__mutate"), "perguntar")

    def test_leitura_e_servidores_parecidos_passam(self):
        for nome in ("mcp__meta-ads-mcp__get_insights", "mcp__metadata__update_record", "mcp__metabase__create_card"):
            with self.subTest(nome=nome):
                self.assertIsNone(self.mcp(nome))
        self.assertIsNone(self.mcp("mcp__seo__get_page_audit", {"field": "meta description"}))


class EntradaPesada(Base):
    def cronometrado(self, entrada=None, bruto=None):
        t = time.monotonic()
        r = self.rodar(entrada, bruto)
        self.assertLess(time.monotonic() - t, 3.0)
        return r

    def multi_args(self, args):
        return self.cronometrado({"tool_name": MULTI, "tool_input": {"tools": [
            {"tool_slug": "METAADS_UPDATE_CAMPAIGN", "arguments": args}]}})

    # F2
    def test_string_com_colchetes_nao_perde_o_bloqueio(self):
        for nota in ("[" * 100000, "[" * 3000 + "]" * 3000):
            with self.subTest(tamanho=len(nota)):
                self.assertEqual(self.multi_args({"note": nota}), "bloquear")

    def test_tool_input_muito_fundo_bloqueia_sem_log(self):
        # written by hand: json.dumps of 2000 levels hits the test runner's own recursion limit
        fundo = '{"a": ' * 2000 + "{}" + "}" * 2000
        bruto = '{"tool_name": "mcp__x__y", "tool_input": {"tool_slug": "METAADS_UPDATE_AD", "n": %s}}' % fundo
        self.assertEqual(self.cronometrado(bruto=bruto), "bloquear")
        # same depth with no deny: no decision and no erros-mkt.log line (the walkers do not recurse)
        self.assertIsNone(self.cronometrado(bruto=bruto.replace("UPDATE", "GET")))

    # F3
    def test_composio_repetido_no_argumento_mcp(self):
        self.assertEqual(self.multi_args({"text": "composio " * 12000}), "bloquear")

    def test_execute_depois_de_continuacao_de_linha(self):
        for cmd in ("composio \\\n  execute METAADS_UPDATE_AD", "composio --json \\\n  execute METAADS_UPDATE_AD",
                    "composio `\n execute METAADS_UPDATE_AD", "composio\nexecute METAADS_UPDATE_AD"):
            with self.subTest(cmd=cmd):
                self.shell(cmd, "bloquear")

    def test_composio_repetido_no_shell(self):
        cmd = "curl -X POST %sact_1/campaigns; echo " % GRAPH + "composio " * 12000
        self.assertEqual(self.cronometrado({"tool_name": "Bash", "tool_input": {"command": cmd}}), "bloquear")


class GraphPorSegmento(Base):
    # F4
    def test_get_em_outro_segmento_nao_mascara_escrita(self):
        for cmd in ("curl.exe -d status=PAUSED %sact_1/ads; Invoke-RestMethod -Method Get -Uri %sme" % (GRAPH, GRAPH),
                    "curl -F status=PAUSED %sact_1/ads && curl -X GET %sact_1/ads" % (GRAPH, GRAPH)):
            with self.subTest(cmd=cmd):
                self.shell(cmd, "bloquear")

    def test_get_no_mesmo_segmento_passa(self):
        for cmd in ("curl -G -d fields=name %sact_1/insights" % GRAPH, "curl -X GET -d x %sact_1/ads" % GRAPH):
            with self.subTest(cmd=cmd):
                self.shell(cmd, None)


class PacoteUnico(Base):
    def test_log_sem_plugin_data_e_privado(self):  # F5: same 0700/0600 the core keeps in ~/.cache/tune-up
        spec = importlib.util.spec_from_file_location("guarda_mkt_teste", SCRIPT)
        g = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(g)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_DATA"}
        env.update(HOME=self.tmp, USERPROFILE=self.tmp)
        with mock.patch.dict(os.environ, env, clear=True):
            g.log_erro("x")
        d = os.path.join(self.tmp, ".cache", "tune-up")
        with open(os.path.join(d, "erros-mkt.log"), encoding="utf-8") as f:
            self.assertTrue(f.read().endswith(" x\n"))
        if sys.platform != "win32":
            self.assertEqual(stat.S_IMODE(os.stat(d).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(d, "erros-mkt.log")).st_mode), 0o600)

    def test_comando_real_do_hooks_json_do_nucleo_bloqueia(self):
        nucleo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        nucleo = os.path.dirname(nucleo)
        with open(os.path.join(nucleo, "hooks", "hooks.json"), encoding="utf-8") as f:
            grupos = json.load(f)["hooks"]["PreToolUse"]
        cmds = [h["command"] for g in grupos for h in g["hooks"] if "guarda_mkt.py" in h["command"]]
        self.assertEqual(len(cmds), 1)
        cmd = cmds[0].replace("${CLAUDE_PLUGIN_ROOT}", nucleo.replace("\\", "/"))
        entrada = json.dumps({"tool_name": "mcp__meta-ads-mcp__update_campaign", "tool_input": {"id": "1"}})
        r = subprocess.run(cmd, shell=True, input=entrada, capture_output=True, text=True, env=self.env,
                           timeout=30, cwd=self.tmp)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")


if __name__ == "__main__":
    unittest.main()
