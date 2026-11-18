"""Tests: user.json fable_agents unlocks a forbidden model only for a listed agent, only through
Agent/Task with an explicit model (C3). Run: python3 -m unittest discover -s tests -q"""
import json
import os
import unittest

from base import AgentBase

VIS = "tune-up:visual"


class TestFableAgents(AgentBase):
    def listar(self, valor=None, **extra):
        d = {"language": "pt-BR", "fable_agents": [VIS] if valor is None else valor}
        d.update(extra)
        self.user_json(d)

    def explicito(self, tipo=VIS, modelo="fable", tool="Agent", extra=None):
        e = {"tool_name": tool, "tool_input": {"subagent_type": tipo, "model": modelo, "prompt": "x"}}
        e.update(extra or {"transcript_path": self.transcript("claude-opus-5-5")})
        return self.rodar("agent", e)

    def test_padrao_continua_bloqueando(self):
        self.assertEqual(self.decisao(self.explicito()), "bloquear")

    def test_listado_com_model_explicito_passa(self):
        self.listar()
        for tool in ("Agent", "Task"):
            for m in ("fable", "claude-fable-5-1"):
                with self.subTest(tool=tool, m=m):
                    s = self.explicito(modelo=m, tool=tool)
                    self.assertNotEqual(self.decisao(s), "bloquear")
                    novo = (s or {}).get("hookSpecificOutput", {}).get("updatedInput")
                    if novo:
                        self.assertEqual(novo["model"], m)

    def test_so_igualdade_exata(self):
        self.listar()
        for t in ["tune-up:visual ", " tune-up:visual", "Tune-Up:Visual", "TUNE-UP:VISUAL", "visual",
                  "tune-up:visual-x", "tune-up:vis", "tune-up:vіsual", "tune-up:visual\n",
                  [VIS], {"x": VIS}, None]:
            with self.subTest(t=t):
                self.assertEqual(self.decisao(self.explicito(tipo=t)), "bloquear")

    def test_outro_agente_nao_listado_bloqueia(self):
        self.listar()
        self.assertEqual(self.decisao(self.explicito(tipo="general-purpose")), "bloquear")

    def test_workflow_continua_bloqueando(self):
        self.listar()
        for sc in ["agent({agentType: 'tune-up:visual', model: 'fable', prompt: 'x'})",
                   "agent({subagent_type: 'tune-up:visual', model: 'fable', prompt: 'x'})"]:
            with self.subTest(sc=sc):
                s = self.rodar("agent", {"tool_name": "Workflow", "tool_input": {"script": sc},
                                         "transcript_path": self.transcript("claude-opus-5-5")})
                self.assertEqual(self.decisao(s), "bloquear")
        s = self.rodar("agent", {"tool_name": "Workflow",
                                 "tool_input": {"script": "agent({agentType: 'tune-up:visual', prompt: 'x'})"},
                                 "transcript_path": self.transcript("claude-fable-5")})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_sessao_proibida_sem_model_continua_bloqueando(self):
        self.listar(["meu-agente", VIS])
        for ti in [{"subagent_type": "meu-agente", "prompt": "x"},
                   {"subagent_type": "meu-agente", "model": "inherit", "prompt": "x"}]:
            with self.subTest(ti=ti):
                s = self.agent(ti, {"transcript_path": self.transcript("claude-fable-5-1")})
                self.assertEqual(self.decisao(s), "bloquear")
        # listed plugin agent: its frontmatter (opus) replaces the session model, never keeps fable
        s = self.agent({"subagent_type": VIS, "prompt": "x"}, {"transcript_path": self.transcript("claude-fable-5-1")})
        self.assertEqual(s["hookSpecificOutput"]["updatedInput"]["model"], "opus")

    def test_modelo_do_papel_ou_frontmatter_nao_destrava(self):
        self.listar(["meu-agente", VIS], models={"visual": {"model": "fable"}, "meu-agente": {"model": "fable"}})
        s = self.agent({"subagent_type": VIS, "prompt": "x"}, {"transcript_path": self.transcript("claude-opus-5-5")})
        self.assertNotIn("fable", json.dumps(s or {}).lower())
        s = self.agent({"subagent_type": "meu-agente", "prompt": "x"},
                       {"transcript_path": self.transcript("claude-fable-5-1")})
        self.assertEqual(self.decisao(s), "bloquear")
        d = os.path.join(self.cwd, ".claude", "agents")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "meu-agente.md"), "w", encoding="utf-8") as f:
            f.write("---\nname: meu-agente\nmodel: fable\n---\nx\n")
        s = self.agent({"subagent_type": "meu-agente", "prompt": "x"},
                       {"transcript_path": self.transcript("claude-fable-5-1")})
        self.assertEqual(self.decisao(s), "bloquear")

    def test_config_do_projeto_nao_destrava(self):
        self.user_json({"language": "pt-BR"})
        d = os.path.join(self.cwd, ".tune-up")
        os.makedirs(d, exist_ok=True)
        c = os.path.join(d, "config.json")
        with open(c, "w", encoding="utf-8") as f:
            json.dump({"fable_agents": [VIS]}, f)
        os.chmod(c, 0o600)
        self.assertEqual(self.decisao(self.explicito()), "bloquear")
        self.confiar(c)
        self.assertEqual(self.decisao(self.explicito()), "bloquear")

    def test_lista_invalida_nao_destrava_nada(self):
        for v in [VIS, ["*"], [""], [VIS, ""], [VIS, 3], [VIS, "a/b"], [VIS, "x" * 81], {"a": VIS}, True]:
            with self.subTest(v=v):
                self.listar(v)
                self.assertEqual(self.decisao(self.explicito()), "bloquear")


if __name__ == "__main__":
    unittest.main()
