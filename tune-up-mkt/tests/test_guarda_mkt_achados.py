"""guarda_mkt.py: second review round (dedicated ads MCP servers, remote tools of any server, Graph writes
without -X/-d, composio invocation forms, heredoc edge cases, JSON-in-string slugs, internal exception)."""
import contextlib
import importlib.util
import io
import json
import os
import unittest
from unittest import mock

from .apoio_mkt import SCRIPT, Base

GRAPH = "https://graph.facebook.com/v20.0/act_1/"


class ServidorDedicado(Base):
    # H1
    def mcp(self, nome, ti=None):
        return self.rodar({"tool_name": nome, "tool_input": ti or {}})

    def test_servidor_de_anuncios_escrita_bloqueia(self):
        for nome in ("mcp__meta-ads__update_campaign", "mcp__meta-ads__create_campaign", "mcp__meta-ads__pause_campaign",
                     "mcp__meta_ads__update_adset", "mcp__metaads__create_ad", "mcp__fb-ads__update_adset",
                     "mcp__claude_ai_Meta_Ads__update_campaign", "mcp__MetaAds__updateCampaign",
                     "mcp__plugin_x_meta-ads__update_campaign"):
            with self.subTest(nome=nome):
                self.assertEqual(self.mcp(nome, {"id": "1"}), "bloquear")

    def test_servidor_social_publicacao_pergunta(self):
        for nome in ("mcp__facebook__create_post", "mcp__facebook__publish_post", "mcp__instagram__publish_media"):
            with self.subTest(nome=nome):
                self.assertEqual(self.mcp(nome, {"message": "oi"}), "perguntar")

    def test_servidor_google_ads_mutacao_pergunta(self):
        for nome in ("mcp__google-ads__mutate", "mcp__google_ads__mutate_campaigns"):
            with self.subTest(nome=nome):
                self.assertEqual(self.mcp(nome), "perguntar")

    def test_servidor_dedicado_leitura_passa(self):
        for nome in ("mcp__meta-ads__get_insights", "mcp__meta-ads__list_campaigns", "mcp__google-ads__search",
                     "mcp__facebook__get_page_posts"):
            with self.subTest(nome=nome):
                self.assertIsNone(self.mcp(nome, {"q": "x"}))

    def test_seo_meta_description_continua_passando(self):
        self.assertIsNone(self.mcp("mcp__seo__get_page_audit", {"field": "meta description"}))
        self.assertIsNone(self.mcp("mcp__metabase__update_card", {"id": 1}))

    # H2
    def test_remoto_de_outro_servidor(self):
        self.assertEqual(self.mcp("mcp__rube__RUBE_REMOTE_BASH_TOOL",
                                  {"command": "composio execute METAADS_UPDATE_AD"}), "bloquear")
        self.assertEqual(self.mcp("mcp__rube__RUBE_REMOTE_WORKBENCH",
                                  {"code": 'run_composio_tool("METAADS_UPDATE_AD", {})'}), "bloquear")
        self.assertIsNone(self.mcp("mcp__rube__RUBE_REMOTE_WORKBENCH", {"code": "print(1)"}))

    def test_execute_em_qualquer_string_mcp(self):
        self.assertEqual(self.mcp("mcp__hub__run", {"cmd": "npx composio execute METAADS_UPDATE_AD"}), "bloquear")

    # M7
    def test_prefixo_fb(self):
        self.assertEqual(self.mcp("mcp__x__exec", {"tool_slug": "FB_UPDATE_CAMPAIGN"}), "bloquear")
        self.assertIsNone(self.mcp("mcp__x__exec", {"q": "fbx_update_campaign"}))
        self.assertIsNone(self.mcp("mcp__x__exec", {"q": "fbx"}))

    # M8
    def test_slug_em_json_dentro_de_string(self):
        self.assertEqual(self.mcp("mcp__x__y", {"tools": '[{"tool_slug":"METAADS_UPDATE_AD"}]'}), "bloquear")
        self.assertIsNone(self.mcp("mcp__x__y", {"tools": '[{"tool_slug":"METAADS_GET_INSIGHTS"}]'}))

    def test_chaves_tool_name_e_toolslug(self):
        self.assertEqual(self.mcp("mcp__x__y", {"tool_name": "METAADS_UPDATE_AD"}), "bloquear")
        self.assertEqual(self.mcp("mcp__x__y", {"toolSlug": "METAADS_UPDATE_AD"}), "bloquear")


class GraphSemMetodo(Base):
    # H3: every pattern through Bash, PowerShell and Monitor
    def test_escrita_em_objeto_de_anuncio_bloqueia(self):
        for cmd in ("Invoke-RestMethod -Method Post -Uri '%scampaigns' -Body @{name='x'}" % GRAPH,
                    "irm %sadsets -Method Post -Body @{name='x'}" % GRAPH,
                    "Invoke-WebRequest -Method Post -Uri %scampaigns" % GRAPH,
                    "Invoke-RestMethod -Uri %sads -Body @{a=1}" % GRAPH,
                    "python3 -c 'import requests; requests.post(\"%scampaigns\", data={})'" % GRAPH,
                    "curl --json '{}' %sads" % GRAPH,
                    "wget --post-data x %scampaigns" % GRAPH,
                    "http POST %scampaigns" % GRAPH,
                    "node -e \"fetch('%scampaigns',{method:'POST'})\"" % GRAPH):
            with self.subTest(cmd=cmd):
                self.shell(cmd, "bloquear")

    def test_escrita_em_outro_caminho_pergunta(self):
        self.shell("http POST https://graph.facebook.com/v20.0/1/feed message=x", "perguntar")
        self.shell("Invoke-RestMethod -Method Post -Uri https://graph.facebook.com/v20.0/1/photos", "perguntar")

    def test_get_continua_passando(self):
        for cmd in ("curl %sinsights" % GRAPH, "Invoke-RestMethod -Uri %sinsights" % GRAPH,
                    "Invoke-RestMethod -Method Get -Uri %sinsights -Body @{fields='spend'}" % GRAPH,
                    "python3 -c 'import requests; requests.get(\"%sinsights\")'" % GRAPH):
            with self.subTest(cmd=cmd):
                self.shell(cmd, None)


class FormasDoComposio(Base):
    # M1
    def test_formas_de_invocar(self):
        for cmd in ("composio.cmd execute METAADS_UPDATE_AD", "composio.exe execute METAADS_UPDATE_AD",
                    "& 'composio' execute METAADS_UPDATE_AD", '"composio" execute METAADS_UPDATE_AD',
                    "node_modules\\.bin\\composio execute METAADS_UPDATE_AD"):
            with self.subTest(cmd=cmd):
                self.shell(cmd, "bloquear")

    def test_slug_ilegivel_pergunta(self):
        for cmd in ("composio execute $S", "cat lista | xargs composio execute"):
            with self.subTest(cmd=cmd):
                self.shell(cmd, "perguntar")
        s = self.saida({"tool_name": "Bash", "tool_input": {"command": "composio execute $S"}})
        self.assertIn("cannot read", s["permissionDecisionReason"])

    def test_slug_legivel_neutro_passa(self):
        self.shell("composio execute GMAIL_LIST_THREADS", None)

    # M6
    def test_heredoc_falso(self):
        for cmd in ("grep -c x <<<hello\ncomposio execute METAADS_UPDATE_AD",
                    "echo $((1<<2))\ncomposio execute METAADS_UPDATE_AD",
                    "cat <<EOF\ntexto\ncomposio execute METAADS_UPDATE_AD"):
            with self.subTest(cmd=cmd):
                self.shell(cmd, "bloquear")


class ExcecaoInterna(Base):
    # M3: no test-only switch in the script; the exception path is exercised in-process
    def test_sem_chaves_de_teste_no_script(self):
        with open(SCRIPT, encoding="utf-8") as f:
            fonte = f.read()
        for chave in ("TUNEUP_TESTE", "TUNEUP_FAKE_EXCECAO", "TUNEUP_MKT_JSON", "TUNEUP_USER_JSON"):
            self.assertNotIn(chave, fonte)

    def test_excecao_interna_sem_decisao_e_uma_linha_de_log(self):
        spec = importlib.util.spec_from_file_location("guarda_mkt_em_processo", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        entrada = json.dumps({"tool_name": "Bash", "tool_input": {"command": "composio execute METAADS_UPDATE_AD"}})
        saida = io.StringIO()
        with mock.patch.object(mod, "achados_da_chamada", side_effect=RuntimeError("simulated exception")), \
                mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self.dados}), \
                mock.patch("sys.stdin", io.StringIO(entrada)), contextlib.redirect_stdout(saida):
            mod.main()
        self.assertEqual(saida.getvalue(), "")
        with open(os.path.join(self.dados, "erros.log"), encoding="utf-8") as f:
            linhas = f.read().splitlines()
        self.assertEqual(len(linhas), 1)
        self.assertIn("simulated exception", linhas[0])


if __name__ == "__main__":
    unittest.main()
