"""guarda_mkt.py: per-project loosening (mkt.json), its protection, messages by language, any MCP server."""
import json
import os

from .apoio_mkt import Base

ESCRITA_META = "composio execute METAADS_UPDATE_AD"


class Config(Base):
    def setUp(self):
        super().setUp()
        self.raiz = os.path.join(self.tmp, "projeto")
        self.outra = os.path.join(self.tmp, "outra")
        os.makedirs(self.raiz)
        os.makedirs(self.outra)

    def mkt(self, conteudo):
        """Writes mkt.json, returns env with CLAUDE_PROJECT_DIR = real root."""
        arq = self.gravar("mkt.json", conteudo)
        return {"TUNEUP_MKT_JSON": arq, "CLAUDE_PROJECT_DIR": self.raiz}

    def meta(self, env, cwd=None):
        e = {"tool_name": "Bash", "tool_input": {"command": ESCRITA_META}}
        if cwd:
            e["cwd"] = cwd
        return self.saida(e, env=env)

    # C5 (1)
    def test_meta_ask_afrouxa_e_explica(self):
        env = self.mkt({"projetos": {self.raiz: {"meta_ads_write": "ask"}}})
        self.shell(ESCRITA_META, "perguntar", env=env)
        self.assertEqual(self.multi("METAADS_UPDATE_AD", env=env), "perguntar")
        s = self.meta(env)
        self.assertIn("The default is to block", s["permissionDecisionReason"])
        self.assertIn(env["TUNEUP_MKT_JSON"], s["permissionDecisionReason"])

    def test_caminho_normalizado(self):
        chave = os.path.join(self.raiz, "sub", "..") + os.sep
        env = self.mkt({"projetos": {chave: {"meta_ads_write": "ask"}}})
        env["CLAUDE_PROJECT_DIR"] = self.raiz + os.sep
        self.assertEqual(self.meta(env)["permissionDecision"], "ask")

    def test_endurecer_ask_para_deny(self):
        env = self.mkt({"projetos": {self.raiz: {"google_ads_write": "deny", "organic_publish": "deny"}}})
        self.assertEqual(self.multi("GOOGLEADS_MUTATE_CAMPAIGNS", env=env), "bloquear")
        self.assertEqual(self.multi("INSTAGRAM_CREATE_MEDIA_CONTAINER", env=env), "bloquear")
        self.assertIsNone(self.multi("GOOGLEADS_SEARCH", env=env))

    def test_afrouxar_meta_nao_esconde_outro_deny(self):
        env = self.mkt({"projetos": {self.raiz: {"meta_ads_write": "ask", "organic_publish": "deny"}}})
        self.assertEqual(self.rodar({"tool_name": "mcp__composio__COMPOSIO_MULTI_EXECUTE_TOOL", "tool_input": {
            "tools": [{"tool_slug": "METAADS_UPDATE_AD"}, {"tool_slug": "INSTAGRAM_CREATE_MEDIA_CONTAINER"}]}},
            env=env), "bloquear")

    # C5 (2)
    def test_valores_invalidos_ficam_no_padrao(self):
        for valor in ("allow", "ASK", "pass", 1, None, ["ask"]):
            with self.subTest(valor=valor):
                env = self.mkt({"projetos": {self.raiz: {"meta_ads_write": valor}}})
                self.assertEqual(self.meta(env)["permissionDecision"], "deny")

    def test_arquivo_ilegivel_ou_invalido(self):
        pasta = os.path.join(self.tmp, "e-pasta.json")
        os.makedirs(pasta)
        for arq in (pasta, self.gravar("ruim.json", "{nao e json"), self.gravar("lista.json", "[1]"),
                    self.gravar("sem-projetos.json", {"meta_ads_write": "ask"})):
            with self.subTest(arq=os.path.basename(arq)):
                env = {"TUNEUP_MKT_JSON": arq, "CLAUDE_PROJECT_DIR": self.raiz}
                self.assertEqual(self.meta(env)["permissionDecision"], "deny")

    def test_chave_com_byte_nulo_nao_desliga_a_guarda(self):
        env = self.mkt({"projetos": {"x\u0000y": {"meta_ads_write": "ask"}, self.raiz: {"google_ads_write": "deny"}}})
        self.assertEqual(self.meta(env)["permissionDecision"], "deny")
        self.assertEqual(self.multi("GOOGLEADS_MUTATE_CAMPAIGNS", env=env), "bloquear")

    def test_projeto_ausente(self):
        env = self.mkt({"projetos": {self.outra: {"meta_ads_write": "ask"}}})
        self.assertEqual(self.meta(env)["permissionDecision"], "deny")

    # C5 (4): the hook cwd never selects the project
    def test_cwd_plantado_nao_muda(self):
        env = self.mkt({"projetos": {self.outra: {"meta_ads_write": "ask"}}})
        with open(os.path.join(self.outra, "mkt.json"), "w", encoding="utf-8") as f:
            json.dump({"projetos": {self.outra: {"meta_ads_write": "ask"}}}, f)
        s = self.meta(env, cwd=self.outra)
        self.assertEqual(s["permissionDecision"], "deny")
        self.assertNotIn("loosened", s["permissionDecisionReason"])

    # C5 (5)
    def test_sem_claude_project_dir(self):
        env = self.mkt({"projetos": {self.raiz: {"meta_ads_write": "ask"}}})
        del env["CLAUDE_PROJECT_DIR"]
        self.assertEqual(self.meta(env, cwd=self.raiz)["permissionDecision"], "deny")

    # C5 (3): protection of the loosening file
    def test_shell_que_cita_mkt_json(self):
        for cmd in ("cd ~/.config/tune-up && echo x > mkt.json", 'echo x > "$D/mkt.json"',
                    "Set-Content C:\\Users\\x\\.config\\tune-up\\mkt.json x", "cp a MKT.JSON"):
            with self.subTest(cmd=cmd):
                self.shell(cmd, "perguntar")
        s = self.saida({"tool_name": "Bash", "tool_input": {"command": "echo x > mkt.json"}})
        self.assertIn("loosens the marketing guard", s["permissionDecisionReason"])

    def test_shell_parecido_nao_cita(self):
        for cmd in ("cat xmkt.jsonl", "cat mkt.jsonl", "ls my-mkt.json"):
            with self.subTest(cmd=cmd):
                self.shell(cmd, None)

    def test_escrita_no_mkt_json(self):
        alvo = os.path.join(self.tmp, ".config", "tune-up", "mkt.json")
        for nome, ti in (("Write", {"file_path": alvo, "content": "{}"}),
                         ("Edit", {"file_path": alvo, "old_string": "a", "new_string": "b"}),
                         ("MultiEdit", {"file_path": "C:\\x\\tune-up\\mkt.json", "edits": []}),
                         ("NotebookEdit", {"notebook_path": "/x/mkt.json", "new_source": ""})):
            with self.subTest(ferramenta=nome):
                self.assertEqual(self.rodar({"tool_name": nome, "tool_input": ti}), "perguntar")

    def test_escrita_outro_arquivo_passa(self):
        # Only the target path counts, not the content (docs that mention the file must stay editable).
        for ti in ({"file_path": "/x/xmkt.jsonl", "content": ""},
                   {"file_path": "/x/README.md", "content": "see ~/.config/tune-up/mkt.json"},
                   {"file_path": "/x/a.sh", "content": "curl -X POST https://graph.facebook.com/v20/act_1/ads"}):
            with self.subTest(ti=ti["file_path"]):
                self.assertIsNone(self.rodar({"tool_name": "Write", "tool_input": ti}))


class Mensagens(Base):
    def user(self, conteudo):
        return {"TUNEUP_USER_JSON": self.gravar("user.json", conteudo)}

    def razao(self, env, slug="METAADS_UPDATE_AD"):
        s = self.saida({"tool_name": "mcp__composio__COMPOSIO_MULTI_EXECUTE_TOOL",
                        "tool_input": {"tools": [{"tool_slug": slug}]}}, env=env)
        return s["permissionDecisionReason"]

    # C6
    def test_sem_arquivo_ingles_the_owner(self):
        r = self.razao({})
        self.assertTrue(r.startswith("tune-up: Meta ad objects"), r)
        self.assertIn("the owner's explicit request", r)

    def test_pt_br_com_dono(self):
        r = self.razao(self.user({"language": "pt-br", "owner": "Ana"}))
        self.assertIn("Gerenciador de Anúncios", r)
        self.assertIn("pedido explícito de Ana", r)
        self.assertIn("ordem de Ana", self.razao(self.user({"language": "pt-BR", "owner": "Ana"}),
                                                  "INSTAGRAM_CREATE_MEDIA_CONTAINER"))

    def test_pt_br_sem_dono(self):
        self.assertIn("pedido explícito do dono", self.razao(self.user({"language": "pt-BR"})))
        self.assertIn("do dono", self.razao(self.user({"language": "pt-BR", "owner": "../x"})))

    def test_en_com_dono(self):
        r = self.razao(self.user({"language": "en", "owner": "Ana"}))
        self.assertIn("Ana's explicit request", r)
        self.assertIn("Google Ads change", self.razao(self.user({"language": "en"}), "GOOGLEADS_MUTATE_CAMPAIGNS"))

    def test_outro_idioma_ou_arquivo_ruim_ingles(self):
        self.assertIn("Ana's explicit", self.razao(self.user({"language": "fr", "owner": "Ana"})))
        self.assertIn("the owner's", self.razao(self.user("{quebrado")))
        self.assertIn("the owner's", self.razao(self.user({"owner": 7})))

    def test_afrouxado_em_pt_br(self):
        raiz = os.path.join(self.tmp, "p")
        os.makedirs(raiz)
        env = self.user({"language": "pt-BR"})
        env.update({"TUNEUP_MKT_JSON": self.gravar("mkt.json", {"projetos": {raiz: {"meta_ads_write": "ask"}}}),
                    "CLAUDE_PROJECT_DIR": raiz})
        r = self.razao(env)
        self.assertIn("O padrão é bloquear", r)
        self.assertIn(env["TUNEUP_MKT_JSON"], r)


class QualquerMcp(Base):
    # C13
    def test_execute_meta_nos_tres_shells(self):
        self.shell("composio execute METAADS_UPDATE_AD", "bloquear")

    def test_servidor_sem_composio_no_nome(self):
        self.assertEqual(self.rodar({"tool_name": "mcp__hub__MULTI_EXECUTE",
                                     "tool_input": {"tools": [{"tool_slug": "METAADS_UPDATE_AD"}]}}), "bloquear")

    def test_seo_meta_description_passa(self):
        self.assertIsNone(self.rodar({"tool_name": "mcp__seo__get_page_audit",
                                      "tool_input": {"field": "meta description"}}))

    def test_mcp_inofensivo_passa(self):
        self.assertIsNone(self.rodar({"tool_name": "mcp__x__y", "tool_input": {"q": "hello"}}))

    def test_outras_ferramentas_passam(self):
        for nome in ("Read", "TodoWrite", "BashOutput"):
            with self.subTest(ferramenta=nome):
                self.assertIsNone(self.rodar({"tool_name": nome, "tool_input": {
                    "command": ESCRITA_META, "file_path": "/x/mkt.json"}}))
