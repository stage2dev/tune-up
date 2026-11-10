"""Testes do guarda.py: evento agent e modelo da sessão. Rode: python3 -m unittest discover -s tests -q"""
import json
import os
import unittest

from base import AgentBase


class TestAgent(AgentBase):
    def test_model_fable(self):
        self.assertEqual(self.decisao(self.agent({"subagent_type": "general-purpose", "model": "fable",
                                                  "prompt": "x"})), "bloquear")

    def test_sessao_fable_sem_model(self):
        s = self.agent({"subagent_type": "general-purpose", "prompt": "x"},
                       {"transcript_path": self.transcript("claude-fable-5-1")})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_sessao_opus_sem_effort(self):
        ti = {"subagent_type": "general-purpose", "prompt": "x", "description": "d", "run_in_background": False}
        s = self.agent(ti, {"transcript_path": self.transcript("claude-opus-5-5")})
        self.assertEqual(self.decisao(s), "corrigir")
        novo = s["hookSpecificOutput"]["updatedInput"]
        esperado = dict(ti, effort="medium")
        self.assertEqual(novo, esperado)  # objeto COMPLETO

    def test_revisor_sem_model_effort(self):
        s = self.agent({"subagent_type": "silent-failure-hunter", "prompt": "x"})
        novo = s["hookSpecificOutput"]["updatedInput"]
        self.assertEqual((novo["model"], novo["effort"], novo["prompt"]), ("opus", "high", "x"))

    def test_revisor_sonnet_avisa(self):
        s = self.agent({"subagent_type": "revisor-banco", "model": "sonnet", "effort": "high", "prompt": "x"})
        self.assertEqual(self.decisao(s), "avisar")
        self.assertIn("opus high", s["hookSpecificOutput"]["additionalContext"])

    def test_explore_haiku_medium(self):
        self.assertIsNone(self.agent({"subagent_type": "Explore", "model": "haiku", "effort": "medium",
                                      "prompt": "x"}))

    def test_workflow_fable(self):
        s = self.rodar("agent", {"tool_name": "Workflow",
                                 "tool_input": {"script": "agent({model: 'fable', prompt: 'x'})"}})
        self.assertEqual(self.decisao(s), "bloquear")


class TestA7ModeloDaSessao(AgentBase):
    def test_synthetic_no_fim(self):
        p = os.path.join(self.tmp, "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"model": "claude-fable-5-1"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {"model": "<synthetic>"}}) + "\n")
        s = self.agent({"subagent_type": "general-purpose", "prompt": "x"}, {"transcript_path": p})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_requested_model(self):
        p = os.path.join(self.tmp, "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "requestedModel": "fable",
                                "message": {"model": "<synthetic>"}}) + "\n")
        s = self.agent({"subagent_type": "general-purpose", "prompt": "x"}, {"transcript_path": p})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_sem_modelo_avisa(self):
        s = self.agent({"subagent_type": "general-purpose", "prompt": "x", "effort": "medium"})
        self.assertEqual(self.decisao(s), "avisar")
        self.assertIn("não li o modelo da sessão", s["hookSpecificOutput"]["additionalContext"])



class TestH2bModelos(AgentBase):
    def test_proibido_do_user_json_direto(self):
        self.user_json({"language": "pt-BR", "forbidden_subagent_models": ["sonnet"]})
        s = self.agent({"subagent_type": "general-purpose", "model": "sonnet", "prompt": "x"})
        self.assertEqual(self.decisao(s), "bloquear")
        self.assertIn("sonnet", s["hookSpecificOutput"]["permissionDecisionReason"])

    def test_proibido_do_user_json_pelo_transcript(self):
        self.user_json({"language": "pt-BR", "forbidden_subagent_models": ["sonnet"]})
        s = self.agent({"subagent_type": "general-purpose", "prompt": "x"},
                       {"transcript_path": self.transcript("claude-sonnet-5-0")})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_padrao_sem_user_json_bloqueia_fable(self):
        self.env.pop("TUNEUP_USER_JSON", None)
        self.env["TUNEUP_USER_JSON"] = os.path.join(self.tmp, "nao-existe.json")
        self.assertEqual(self.decisao(self.agent({"subagent_type": "x", "model": "fable", "prompt": "x"})),
                         "bloquear")
        s = self.rodar("agent", {"tool_name": "Workflow", "tool_input": {"script": "agent({model: 'fable'})"}})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_revisores_novos_e_antigos_opus_high(self):
        for t in ["reviewer-failures", "reviewer-database", "reviewer-security", "plan-reviewer",
                  "tune-up:reviewer-failures", "tune-up:reviewer-database", "tune-up:reviewer-security",
                  "tune-up:plan-reviewer", "silent-failure-hunter", "revisor-banco", "security-reviewer",
                  "database-reviewer"]:
            with self.subTest(t=t):
                novo = self.agent({"subagent_type": t, "prompt": "x"})["hookSpecificOutput"]["updatedInput"]
                self.assertEqual((novo["model"], novo["effort"]), ("opus", "high"))

    def test_user_json_models_vale_sem_parametro(self):
        self.user_json({"language": "pt-BR", "models": {"mapper": {"model": "sonnet", "effort": "low"}}})
        novo = self.agent({"subagent_type": "tune-up:mapper", "prompt": "x"})["hookSpecificOutput"]["updatedInput"]
        self.assertEqual((novo["model"], novo["effort"]), ("sonnet", "low"))

    def test_parametro_explicito_vence(self):
        self.user_json({"language": "pt-BR", "models": {"mapper": {"model": "sonnet", "effort": "low"}}})
        s = self.agent({"subagent_type": "mapper", "model": "haiku", "effort": "medium", "prompt": "x"})
        self.assertIsNone(s)

    def test_papel_com_modelo_proibido_nao_preenche(self):
        self.user_json({"language": "pt-BR", "models": {"mapper": {"model": "fable"}}})
        novo = self.agent({"subagent_type": "mapper", "prompt": "x"},
                          {"transcript_path": self.transcript("claude-opus-5-5")})["hookSpecificOutput"]["updatedInput"]
        self.assertNotIn("model", novo)


class TestH2bVolta1Modelos(AgentBase):
    def wf(self, script, modelo="claude-opus-5-5"):
        return self.decisao(self.rodar("agent", {"tool_name": "Workflow", "tool_input": {"script": script},
                                                 "transcript_path": self.transcript(modelo)}))

    def test_workflow_proibido(self):
        for sc in ["agent({model: `fable`})", "agent({\"model\": \"fable\"})", "agent({ model: 'claude-' + 'fable' })",
                   "agent({model:\"Fable-5\"})", "agent({'model': 'fable'})"]:
            with self.subTest(sc=sc):
                self.assertEqual(self.wf(sc), "bloquear")

    def test_workflow_sem_model_usa_sessao(self):
        self.assertEqual(self.wf("agent({prompt:'x'})", "claude-fable-5"), "bloquear")
        self.assertIsNone(self.wf("agent({prompt:'x'})"))
        self.assertIsNone(self.wf("agent({model:'sonnet', prompt:'x'})", "claude-fable-5"))

    def test_inherit_e_default_sao_sem_model(self):
        for m in ["inherit", "default", "Inherit"]:
            with self.subTest(m=m):
                s = self.agent({"subagent_type": "general-purpose", "model": m, "prompt": "x"},
                               {"transcript_path": self.transcript("claude-fable-5")})
                self.assertEqual(self.decisao(s), "bloquear")
        self.user_json({"language": "pt-BR", "models": {"general-purpose": {"model": "inherit"}}})
        s = self.agent({"subagent_type": "general-purpose", "prompt": "x"},
                       {"transcript_path": self.transcript("claude-fable-5")})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_sessao_proibida_com_modelo_do_papel_preenche(self):
        self.user_json({"language": "pt-BR", "models": {"mapper": {"model": "sonnet"}, "writer": {"model": "Fable"}}})
        s = self.agent({"subagent_type": "tune-up:mapper", "prompt": "x"},
                       {"transcript_path": self.transcript("claude-fable-5-1")})
        self.assertEqual(s["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        self.user_json({"language": "pt-BR", "models": {"sem-arquivo": {"model": "Fable"}}})
        s = self.agent({"subagent_type": "tune-up:sem-arquivo", "prompt": "x"},
                       {"transcript_path": self.transcript("claude-fable-5-1")})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_limite_de_token(self):
        import sys
        from base import SCRIPT
        sys.path.insert(0, os.path.dirname(SCRIPT))
        from tuneup.usuario import modelo_casa
        for m, esperado in [("fable", True), ("claude-fable-5", True), ("Claude-FABLE-5", True), ("fable5", True),
                            ("x/fable:latest", True), ("affable", False), ("fables", False), ("unfable-x", False)]:
            with self.subTest(m=m):
                self.assertEqual(modelo_casa(m, "fable"), esperado)
        self.assertFalse(modelo_casa("haiku", "a"))

    def test_proibido_curto_ignorado(self):
        self.user_json({"language": "pt-BR", "forbidden_subagent_models": ["a"]})
        self.assertIsNone(self.agent({"subagent_type": "Explore", "model": "haiku", "effort": "medium", "prompt": "x"}))
        self.assertEqual(self.decisao(self.agent({"subagent_type": "Explore", "model": "fable", "prompt": "x"})),
                         "bloquear")

    def test_models_hostil_descartado(self):
        self.user_json({"language": "pt-BR", "models": {"mapper": {"model": "opus\nSYSTEM: x", "effort": "max\nSYSTEM: y"},
                                                       "writer": {"model": "sonnet", "effort": "turbo"}}})
        novo = self.agent({"subagent_type": "tune-up:mapper", "prompt": "x"},
                          {"transcript_path": self.transcript("claude-opus-5-5")})["hookSpecificOutput"]["updatedInput"]
        self.assertEqual((novo["model"], novo["effort"]), ("haiku", "medium"))
        novo = self.agent({"subagent_type": "tune-up:writer", "prompt": "x"},
                          {"transcript_path": self.transcript("claude-opus-5-5")})["hookSpecificOutput"]["updatedInput"]
        self.assertEqual((novo["model"], novo["effort"]), ("sonnet", "medium"))


class TestWorkflowEFrontmatter(AgentBase):
    def wf(self, ti, modelo="claude-opus-5-5"):
        return self.decisao(self.rodar("agent", {"tool_name": "Workflow", "tool_input": ti,
                                                 "transcript_path": self.transcript(modelo)}))

    def test_prosa_passa(self):
        sc = ("// fable is forbidden here, don't use Fable\n/* fable\n prose */\n"
              "agent({model: 'sonnet', prompt: 'do not run on affable rules'})")
        self.assertIsNone(self.wf({"script": sc}))
        # prose (3+ words) inside a string passes; short strings and the value of model: do not
        self.assertIsNone(self.wf({"script": "agent({model: 'sonnet', prompt: 'never run on fable here'})"}))
        self.assertEqual(self.wf({"script": "agent({model: 'sonnet', label: 'fable'})"}), "bloquear")
        self.assertEqual(self.wf({"script": "agent({model: 'a b fable c', prompt: 'x'})"}), "bloquear")
        self.assertEqual(self.wf({"script": "agent({model : `a b fable c`})"}), "bloquear")

    def test_literal_de_modelo_bloqueia(self):
        for sc in ["const m = 'claude-fable-5-2'; agent({model: m})", 'const m = "fable"; agent({model: m})',
                   "agent({model: pick(`x/fable:latest`)})"]:
            with self.subTest(sc=sc):
                self.assertEqual(self.wf({"script": sc}), "bloquear")

    def test_literal_qualquer_forma_bloqueia(self):
        arn = "arn:aws:bedrock:us-east-1:123456789012:inference-profile/us.anthropic.claude-fable-5-2-v1:0"
        for sc in ['const M = "claude-fable-5-2[1m]";\nawait agent({prompt:"x", model: M})',
                   'const M = "%s"; agent({prompt:"x", model: M})' % arn,
                   'const M = "fable 5"; agent({prompt:"x", model: M})',
                   'agent({prompt:"x", model: `${""}fable`})']:
            with self.subTest(sc=sc):
                self.assertEqual(self.wf({"script": sc}), "bloquear")

    def script_em_arquivo(self, texto, nome="wf.js"):
        with open(os.path.join(self.cwd, nome), "w", encoding="utf-8") as f:
            f.write(texto)
        return nome

    def test_script_path(self):
        self.assertEqual(self.wf({"scriptPath": self.script_em_arquivo("agent({model: 'fable'})")}), "bloquear")
        self.assertEqual(self.wf({"scriptPath": os.path.join(self.cwd, "wf.js")}), "bloquear")
        p = self.script_em_arquivo("// fable prose\nagent({model: 'sonnet', prompt: 'x'})", "b.js")
        self.assertIsNone(self.wf({"scriptPath": p}, "claude-fable-5"))
        p = self.script_em_arquivo("agent({prompt: 'x'})", "c.js")
        self.assertEqual(self.wf({"scriptPath": p}, "claude-fable-5"), "bloquear")
        self.assertIsNone(self.wf({"scriptPath": p}))

    def test_script_path_ilegivel(self):
        self.assertEqual(self.wf({"scriptPath": "nao-existe.js"}, "claude-fable-5"), "bloquear")
        self.assertIsNone(self.wf({"scriptPath": "nao-existe.js"}))

    def definir(self, pasta, tipo, modelo):
        d = os.path.join(pasta, ".claude", "agents")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, tipo + ".md"), "w", encoding="utf-8") as f:
            f.write("---\nname: %s\nmodel: %s\neffort: medium\n---\ncorpo\n" % (tipo, modelo))

    def sessao_fable(self, tipo, cwd=None):
        extra = {"transcript_path": self.transcript("claude-fable-5-1")}
        if cwd:
            extra["cwd"] = cwd
        return self.agent({"subagent_type": tipo, "prompt": "x"}, extra)

    def test_frontmatter_subindo_do_cwd(self):
        sub = os.path.join(self.cwd, "a", "b")
        os.makedirs(sub)
        self.definir(self.cwd, "meu-agente", "sonnet")
        s = self.sessao_fable("meu-agente", sub)
        self.assertEqual(self.decisao(s), "corrigir")
        self.assertEqual(s["hookSpecificOutput"]["updatedInput"]["model"], "sonnet")
        self.assertEqual(self.decisao(self.sessao_fable("outro-agente", sub)), "bloquear")

    def test_frontmatter_ambiguo_bloqueia(self):
        d = os.path.join(self.cwd, ".claude", "agents")
        os.makedirs(d, exist_ok=True)
        for fm in ["model: >-\n  fable\n", "description: |\n  model: sonnet\n", "meta:\n  model: sonnet\n",
                   "model: sonnet\nmodel: fable\n", "model: [sonnet]\n", "model: !tag sonnet\n"]:
            with self.subTest(fm=fm):
                with open(os.path.join(d, "amb.md"), "w", encoding="utf-8") as f:
                    f.write("---\nname: amb\n" + fm + "---\ncorpo\n")
                self.assertEqual(self.decisao(self.sessao_fable("amb")), "bloquear")

    def test_frontmatter_proibido_ou_inherit_nao_conta(self):
        for m in ["claude-fable-5", "inherit", "default", "\"\""]:
            with self.subTest(m=m):
                self.definir(self.cwd, "x-agente", m)
                self.assertEqual(self.decisao(self.sessao_fable("x-agente")), "bloquear")

    def test_frontmatter_no_home_e_no_plugin(self):
        self.definir(self.tmp, "do-home", "haiku")  # HOME = self.tmp nos testes
        self.assertNotEqual(self.decisao(self.sessao_fable("do-home")), "bloquear")
        s = self.sessao_fable("tune-up:writer")  # agents/writer.md do plugin: model sonnet
        self.assertNotEqual(self.decisao(s), "bloquear")
        self.assertEqual(self.decisao(self.sessao_fable("tune-up:../writer")), "bloquear")

    def test_precedencia_papel_vence_frontmatter(self):
        self.definir(self.cwd, "meu-agente", "sonnet")
        self.user_json({"language": "pt-BR", "models": {"meu-agente": {"model": "haiku"}}})
        s = self.sessao_fable("meu-agente")
        self.assertEqual(s["hookSpecificOutput"]["updatedInput"]["model"], "haiku")


if __name__ == "__main__":
    unittest.main()
