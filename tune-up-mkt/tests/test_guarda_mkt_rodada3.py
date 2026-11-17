"""guarda_mkt.py: third review round (server names with a suffix, deep/huge inputs within the hook timeout,
Graph write next to a GET in another command segment). Big strings are built at runtime."""
import time
import unittest

from .apoio_mkt import Base

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
        # same depth with no deny: no decision and no erros.log line (the walkers do not recurse)
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


if __name__ == "__main__":
    unittest.main()
