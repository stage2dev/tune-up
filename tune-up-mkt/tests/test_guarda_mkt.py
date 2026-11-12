"""Ported cases of guarda_mkt.py (no config file). Run from tune-up-mkt/: python3 -m unittest discover -s tests -t . -q

Every shell case runs through Bash, PowerShell and Monitor (Base.shell).
"""
import json
import os
import re
import unittest

from .apoio_mkt import RAIZ, Base


class TestMkt(Base):
    def test_meta_update_ad_set(self):
        self.assertEqual(self.multi("METAADS_UPDATE_AD_SET_STATUS", {"status": "PAUSED"}), "bloquear")

    def test_facebook_create_campaign(self):
        self.assertEqual(self.multi("FACEBOOK_CREATE_CAMPAIGN"), "bloquear")

    def test_proxy_post_graph(self):
        self.assertEqual(self.rodar({"tool_name": "mcp__composio__COMPOSIO_PROXY_EXECUTE",
                                     "tool_input": {"endpoint": "https://graph.facebook.com/v21.0/123/adsets",
                                                    "method": "POST", "toolkit": "metaads"}}), "bloquear")

    def test_proxy_get_graph(self):
        self.assertIsNone(self.rodar({"tool_name": "mcp__composio__COMPOSIO_PROXY_EXECUTE",
                                      "tool_input": {"endpoint": "https://graph.facebook.com/v21.0/post-1",
                                                     "method": "GET"}}))

    def test_meta_insights(self):
        self.assertIsNone(self.multi("METAADS_GET_INSIGHTS"))

    def test_meta_listar_ad_sets(self):
        self.assertIsNone(self.multi("METAADS_GET_AD_SETS"))

    def test_instagram_create_media(self):
        self.assertEqual(self.multi("INSTAGRAM_CREATE_MEDIA_CONTAINER"), "perguntar")

    def test_googleads_mutate(self):
        self.assertEqual(self.multi("GOOGLEADS_MUTATE_CAMPAIGNS"), "perguntar")

    def test_googleads_search(self):
        self.assertIsNone(self.multi("GOOGLEADS_SEARCH"))

    def test_slug_direto_no_nome(self):
        self.assertEqual(self.rodar({"tool_name": "mcp__composio__FACEBOOK_CREATE_CAMPAIGN",
                                     "tool_input": {"name": "x"}}), "bloquear")

    def test_bash_composio(self):
        self.shell("composio execute METAADS_UPDATE_AD_SET_STATUS --status PAUSED", "bloquear")

    def test_bash_texto_nao_composio(self):
        self.shell("echo METAADS_UPDATE_AD_SET_STATUS && cat <<'EOF'\ncomposio execute FACEBOOK_CREATE_CAMPAIGN\nEOF",
                   None)

    # B1: organic, by slug parts
    def test_facebook_create_photo_post(self):
        self.assertEqual(self.multi("FACEBOOK_CREATE_PHOTO_POST"), "perguntar")

    def test_facebook_upload_photo(self):
        self.assertEqual(self.multi("FACEBOOK_UPLOAD_PHOTO"), "perguntar")

    def test_facebook_get_post_comments(self):
        self.assertIsNone(self.multi("FACEBOOK_GET_POST_COMMENTS"))

    # B2: Graph API outside the proxy, lowercase slug, npx
    def test_bash_curl_post_graph_anuncio(self):
        self.shell("curl -X POST https://graph.facebook.com/v20/act_1/campaigns", "bloquear")

    def test_slug_minusculo(self):
        self.assertEqual(self.multi("metaads_update_ad"), "bloquear")

    def test_bash_npx_composio(self):
        self.shell("npx composio execute METAADS_UPDATE_AD", "bloquear")

    def test_bash_curl_get_graph(self):
        self.shell("curl https://graph.facebook.com/v20/me", None)

    # whole shell command analysed when it mentions composio/graph
    def test_bash_for_loop_proxy(self):
        self.shell('for id in 1 2; do composio proxy "https://graph.facebook.com/v20/act_1/ads" -X POST -d x; done',
                   "bloquear")

    def test_bash_url_em_variavel(self):
        self.shell('U=https://graph.facebook.com/v20/act_1/ads; composio proxy "$U" -X POST', "bloquear")

    def test_bash_instagram_graph_organico(self):
        self.shell("composio proxy https://graph.instagram.com/v20/1/media_publish -X POST", "perguntar")

    def test_bash_composio_run_meta(self):
        self.shell("composio run -f x.ts  # instagram", "perguntar")

    def test_bash_composio_run_sem_meta_pergunta(self):
        # Conscious change (was test_bash_composio_run_neutro, expected pass): `composio run` executes a
        # file the guard cannot read, so a command with no Meta word is no evidence of safety. Now asks.
        self.shell("composio run -f x.ts", "perguntar")
        self.shell("composio run x.ts", "perguntar")

    # decoded values; workbench/remote bash
    def remoto(self, ferramenta, **ti):
        return self.rodar({"tool_name": "mcp__composio__" + ferramenta, "tool_input": ti})

    def test_workbench_proxy_execute_post(self):
        self.assertEqual(self.remoto("COMPOSIO_REMOTE_WORKBENCH", code='proxy_execute(method="POST", endpoint="https://graph.facebook.com/v20/act_1/ads")'), "bloquear")

    def test_workbench_slug_em_pedacos(self):
        self.assertEqual(self.remoto("COMPOSIO_REMOTE_WORKBENCH", code='s = "FACE" + "BOOK_CREATE" + "_POST"  # facebook'), "perguntar")

    def test_workbench_slug_anuncio(self):
        self.assertEqual(self.remoto("COMPOSIO_REMOTE_WORKBENCH", code='run_composio_tool("metaads_update_ad", {})'), "bloquear")

    def test_remote_bash_instagram(self):
        self.assertEqual(self.remoto("COMPOSIO_REMOTE_BASH_TOOL", command="python3 -c 'import requests; requests.post(u)'  # instagram"), "perguntar")

    def test_workbench_neutro(self):
        self.assertIsNone(self.remoto("COMPOSIO_REMOTE_WORKBENCH", code="print(1)"))

    # an ad object only passes with a read verb
    def test_meta_copy_ad(self):
        self.assertEqual(self.multi("METAADS_COPY_AD"), "bloquear")

    def test_meta_enable_campaign(self):
        self.assertEqual(self.multi("METAADS_ENABLE_CAMPAIGN"), "bloquear")

    def test_toolkit_metaads_leitura(self):
        self.assertIsNone(self.rodar({"tool_name": "mcp__composio__COMPOSIO_PROXY_EXECUTE",
                                      "tool_input": {"endpoint": "https://graph.facebook.com/v21.0/act_1/insights",
                                                     "method": "GET", "toolkit": "metaads"}}))

    # other Composio MCP prefix
    def test_mcp_composio_outro_prefixo(self):
        self.assertEqual(self.rodar({"tool_name": "mcp__claude_ai_Composio__COMPOSIO_MULTI_EXECUTE_TOOL",
                                     "tool_input": {"tools": [{"tool_slug": "METAADS_UPDATE_AD"}]}}), "bloquear")

    def test_hooks_matcher(self):
        # Claude Code tests a non-literal matcher as an unanchored JavaScript regex (RegExp.test) = re.search.
        with open(os.path.join(RAIZ, "hooks", "hooks.json")) as f:
            pre = json.load(f)["hooks"]["PreToolUse"][0]
        m = pre["matcher"]
        for nome in ("Bash", "PowerShell", "Monitor", "Write", "Edit", "MultiEdit", "NotebookEdit",
                     "mcp__composio__X", "mcp__claude_ai_Composio__X", "mcp__hub__MULTI_EXECUTE"):
            self.assertTrue(re.search(m, nome), nome)
        self.assertIsNone(re.search(m, "Read"))
        self.assertEqual(pre["hooks"][0]["command"], 'sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda_mkt.py')

    # False positive: slug only where it is a tool name
    def test_argumento_livre_com_cara_de_slug(self):
        self.assertIsNone(self.multi("METAADS_GET_INSIGHTS", {"name": "fb_ads_campaign_oct"}))

    def test_bash_echo_slug_com_composio_list(self):
        self.shell("echo METAADS_UPDATE_AD; composio list", None)

    def test_bash_execute_continua(self):
        self.shell("composio execute METAADS_UPDATE_AD", "bloquear")

    def test_multi_tool_slug_ad_set(self):
        self.assertEqual(self.multi("METAADS_UPDATE_AD_SET"), "bloquear")

    def test_workbench_metadata(self):
        self.assertIsNone(self.remoto("COMPOSIO_REMOTE_WORKBENCH", code="metadata = {}"))

    def test_json_invalido(self):
        self.assertIsNone(self.rodar(bruto="nao e json"))

    def test_excecao_interna(self):
        self.assertIsNone(self.rodar({"tool_name": "Bash", "tool_input": {"command": "ls"}},
                                     env={"TUNEUP_FAKE_EXCECAO": "1"}))
        with open(os.path.join(self.tmp, "erros.log"), encoding="utf-8") as f:
            self.assertIn("simulated exception", f.read())

    # flag before the slug in composio execute
    def test_composio_execute_flag_p_antes(self):
        self.shell("composio execute -p METAADS_UPDATE_AD -d '{\"a\":1}' METAADS_UPDATE_AD -d '{\"a\":1}'",
                   "bloquear")

    def test_composio_execute_skip_checks(self):
        self.shell("composio execute --skip-checks METAADS_UPDATE_AD -d '{}'", "bloquear")

    def test_composio_execute_skip_tool_params(self):
        self.shell("composio execute --skip-tool-params-check METAADS_UPDATE_AD_SET", "bloquear")

    def test_composio_execute_flag_leitura(self):
        self.shell("composio execute -p METAADS_GET_INSIGHTS -d '{}'", None)

    # curl -G -d is a GET
    def test_curl_G_d_insights(self):
        self.shell("curl -G -d fields=spend https://graph.facebook.com/v20/act_1/insights", None)

    def test_curl_get_longo_d_insights(self):
        self.shell("curl --get --data fields=spend https://graph.facebook.com/v20/act_1/insights", None)


if __name__ == "__main__":
    unittest.main()
