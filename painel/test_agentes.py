"""Testes do leitor de agentes com pastas temporárias que imitam ~/.claude/projects."""
import json
import os
import shutil
import tempfile
import time
import unittest

import agentes
import agentes_disco as disco

SID = "11111111-2222-4333-8444-555555555555"
SID2 = "66666666-7777-4888-9999-aaaaaaaaaaaa"
SEGREDO = "TEXTO-DO-PROMPT-NAO-PODE-VAZAR"


def linha_assistente(modelo="claude-opus-5-5", effort="high", ferramenta=None, entrada=None, tid="toolu_x", ts="2026-11-10T12:00:00.000Z"):
    content = [{"type": "text", "text": SEGREDO}]
    if ferramenta:
        content.append({"type": "tool_use", "id": tid, "name": ferramenta, "input": entrada or {}})
    obj = {"parentUuid": "p", "type": "assistant", "timestamp": ts, "effort": effort,
           "message": {"model": modelo, "role": "assistant", "content": content}}
    return json.dumps(obj) + "\n"


def linha_usuario(ts="2026-11-10T11:59:00.000Z"):
    return json.dumps({"parentUuid": None, "type": "user", "timestamp": ts,
                       "message": {"role": "user", "content": SEGREDO}}) + "\n"


def blob():
    # linha de api-request-blob traz tool_use antigos dentro: não pode contar
    return json.dumps({"type": "api-request-blob", "message": {"content": [
        {"type": "assistant", "content": [{"type": "tool_use", "name": "Bash", "id": "t9"}]}]}}) + "\n"


class Base(unittest.TestCase):
    def setUp(self):
        agentes.esquecer()
        self.tmp = tempfile.mkdtemp()
        self.raiz = os.path.realpath(os.path.join(self.tmp, "proj"))
        os.makedirs(self.raiz)
        self.projects = os.path.join(self.tmp, "projects")
        self.pasta = os.path.join(self.projects, "-proj")
        os.makedirs(self.pasta)
        self.agora = time.time()
        self.cli = [{"id": SID[:8], "sessionId": SID, "cwd": self.raiz, "kind": "background",
                     "name": "Minha sessão", "state": "working", "status": "busy", "startedAt": 1794272518847}]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rodar(self, cmd, cwd, timeout):
        self.assertEqual(cmd[1:], ["agents", "--json", "--all"])
        return 0, json.dumps(self.cli), ""

    def cfg(self):
        return {"workspace": self.raiz, "projects_dir": self.projects, "claude_bin": "claude-falso"}

    def montar(self, **kw):
        return agentes.montar(self.cfg(), rodar=self.rodar, agora=self.agora, **kw)

    def escrever(self, caminho, texto, idade=0):
        os.makedirs(os.path.dirname(caminho), exist_ok=True)
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)
        t = self.agora - idade
        os.utime(caminho, (t, t))

    def conversa(self, sid=SID, idade=0):
        self.escrever(os.path.join(self.pasta, sid + ".jsonl"),
                      linha_usuario() + linha_assistente(modelo="claude-sonnet-5-5", effort="xhigh"), idade)

    def agente(self, aid, meta, linhas, idade=0, wf=None, sid=SID):
        base = os.path.join(self.pasta, sid, "subagents")
        if wf:
            base = os.path.join(base, "workflows", wf)
        self.escrever(os.path.join(base, "agent-%s.jsonl" % aid), linhas, idade)
        if meta is not None:
            self.escrever(os.path.join(base, "agent-%s.meta.json" % aid),
                          meta if isinstance(meta, str) else json.dumps(meta), idade)

    def todos_agentes(self, r):
        return [a for s in r["sessoes"] for g in s["grupos"] for a in g["agentes"]]


class TestAgentes(Base):
    def test_sessao_sem_subagents(self):
        self.conversa()
        r = self.montar()
        self.assertEqual(r["avisos"], [])
        s = r["sessoes"][0]
        self.assertEqual((s["id"], s["sessao_id"], s["tipo"], s["estado"]), (SID[:8], SID, "segundo_plano", "rodando"))
        self.assertEqual((s["modelo"], s["esforco"]), ("sonnet", "xhigh"))
        self.assertEqual((s["grupos"], s["agentes_total"], s["agentes_ativos"]), ([], 0, 0))
        self.assertIsNone(s["execucao_id"])

    def test_meta_com_effort_e_finished(self):
        self.conversa()
        self.agente("a1", {"agentType": "Explore", "description": "Mapear", "model": "haiku", "effort": "low",
                           "spawnDepth": 1, "finished": True, "toolUseId": "toolu_1"},
                    linha_usuario() + linha_assistente("claude-haiku-5-5", "high", "Read",
                                                       {"file_path": "/x/y/segredo/painel.py"}) + blob(), idade=60)
        a = self.todos_agentes(self.montar())[0]
        self.assertEqual((a["estado"], a["esforco"], a["modelo"], a["modelo_id"]), ("terminou", "low", "haiku", "claude-haiku-5-5"))
        self.assertEqual((a["ferramentas"], a["ultima_acao"], a["profundidade"], a["pai_id"]), (1, "Read painel.py", 1, None))
        self.assertEqual(a["tipo_agente"], "Explore")
        self.assertIsNotNone(a["iniciado_em"])

    def test_descricao_e_nome_da_sessao_mascarados(self):
        self.cli[0]["name"] = "Sessao FAL_KEY=abc123def456"
        self.conversa()
        self.agente("a1", {"agentType": "Explore", "description": "usar ana@exemplo.com e API_KEY=zzz999",
                           "model": "haiku"}, linha_usuario() + blob())
        r = self.montar()
        d = self.todos_agentes(r)[0]["descricao"]
        self.assertNotIn("ana@", d)
        self.assertNotIn("zzz999", d)
        self.assertNotIn("abc123def456", r["sessoes"][0]["nome"])

    def test_meta_sem_effort_nem_finished(self):
        self.conversa()
        self.agente("a2", {"agentType": "x", "description": "d", "spawnDepth": 1},
                    linha_assistente("claude-opus-5-5", "medium", "Bash", {"command": SEGREDO}), idade=5)
        self.agente("a3", {"agentType": "x", "description": "d", "spawnDepth": 1},
                    linha_assistente("claude-opus-5-5", "max"), idade=600)
        self.agente("a4", {"agentType": "x", "description": "velho", "spawnDepth": 1},
                    linha_assistente(), idade=3600)
        r = self.montar()
        por = {a["id"]: a for a in self.todos_agentes(r)}
        self.assertEqual(set(por), {"a2", "a3"})  # a4 terminou há mais de 30 min
        self.assertEqual((por["a2"]["estado"], por["a2"]["esforco"], por["a2"]["ultima_acao"]), ("rodando", "medium", "Bash"))
        self.assertEqual((por["a3"]["estado"], por["a3"]["esforco"]), ("terminou", "max"))
        self.assertEqual(r["sessoes"][0]["agentes_total"], 3)
        self.assertEqual(r["sessoes"][0]["agentes_ativos"], 1)
        self.assertEqual(len(self.todos_agentes(self.montar(todos=True))), 3)
        self.assertNotIn(SEGREDO, json.dumps(r))

    def test_workflow_com_journal(self):
        self.conversa()
        wf = "wf_abc12345-def"
        jornal = [{"type": "launched"},
                  {"type": "started", "agentId": "w1", "label": "L1", "phase": "Executar"},
                  {"type": "started", "agentId": "w2", "label": "L2", "phase": "Revisar"},
                  {"type": "result", "agentId": "w1", "result": SEGREDO}]
        self.escrever(os.path.join(self.pasta, SID, "subagents", "workflows", wf, "journal.jsonl"),
                      "".join(json.dumps(j) + "\n" for j in jornal))
        self.escrever(os.path.join(self.pasta, SID, "workflows", "scripts", "meu-fluxo-%s.js" % wf),
                      "export const meta = {\n  name: 'meu-fluxo',\n  phases: []}\n")
        meta = {"agentType": "workflow-subagent", "description": "L1", "spawnDepth": 1, "model": "opus",
                "workflowPhase": "Executar"}
        self.agente("w1", meta, linha_assistente(effort="high"), idade=200, wf=wf)
        self.agente("w2", dict(meta, description="L2", workflowPhase="Revisar"), linha_assistente(effort="low"),
                    idade=1, wf=wf)
        g = self.montar()["sessoes"][0]["grupos"]
        self.assertEqual(len(g), 1)
        self.assertEqual((g[0]["tipo"], g[0]["id"], g[0]["nome"], g[0]["fases"]), ("workflow", wf, "meu-fluxo", ["Executar", "Revisar"]))
        por = {a["id"]: a for a in g[0]["agentes"]}
        self.assertEqual((por["w1"]["estado"], por["w1"]["fase"], por["w1"]["esforco"]), ("terminou", "Executar", "high"))
        self.assertEqual((por["w2"]["estado"], por["w2"]["fase"]), ("rodando", "Revisar"))

    def test_workflow_sem_script_usa_id(self):
        self.conversa()
        self.agente("w9", {"agentType": "workflow-subagent", "spawnDepth": 1}, linha_assistente(), wf="wf_zz")
        g = self.montar()["sessoes"][0]["grupos"][0]
        self.assertEqual(g["nome"], "wf_zz")

    def test_arquivo_corrompido(self):
        self.conversa()
        self.agente("c1", "{nao e json", "lixo\n{\"type\":\"assistant\", quebrado\n\x00\x01\n")
        self.agente("c2", None, linha_assistente())  # sem meta
        r = self.montar()
        por = {a["id"]: a for a in self.todos_agentes(r)}
        self.assertEqual(set(por), {"c1", "c2"})
        self.assertEqual((por["c1"]["ferramentas"], por["c1"]["modelo"], por["c1"]["tipo_agente"]), (0, None, "sub-agente"))
        self.assertEqual(por["c2"]["modelo"], "opus")

    def symlink(self, alvo, caminho):
        try:
            os.symlink(alvo, caminho)
        except (OSError, NotImplementedError):  # Windows sem permissão de symlink
            self.skipTest("symlink não permitido neste sistema")

    def test_symlink_para_fora_e_ignorado(self):
        self.conversa()
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(fora)
        alvo = os.path.join(fora, "agent-s1.jsonl")
        self.escrever(alvo, linha_assistente())
        sub = os.path.join(self.pasta, SID, "subagents")
        os.makedirs(sub)
        self.symlink(alvo, os.path.join(sub, "agent-s1.jsonl"))
        self.symlink(fora, os.path.join(sub, "workflows"))
        self.assertEqual(self.todos_agentes(self.montar()), [])
        # conversa inteira apontando para fora: sem modelo, sem sub-agentes
        os.unlink(os.path.join(self.pasta, SID + ".jsonl"))
        self.symlink(alvo, os.path.join(self.pasta, SID + ".jsonl"))
        agentes.esquecer()
        s = self.montar()["sessoes"][0]
        self.assertIsNone(s["modelo"])

    def test_pasta_subagents_symlink(self):
        self.conversa()
        fora = os.path.join(self.tmp, "fora2")
        self.escrever(os.path.join(fora, "agent-z.jsonl"), linha_assistente())
        os.makedirs(os.path.join(self.pasta, SID))
        self.symlink(fora, os.path.join(self.pasta, SID, "subagents"))
        self.assertEqual(self.todos_agentes(self.montar()), [])

    def test_corte_de_200(self):
        self.conversa()
        for i in range(205):
            self.agente("b%03d" % i, {"spawnDepth": 1, "finished": True}, linha_assistente(), idade=10 + i)
        r = self.montar()
        self.assertEqual(len(self.todos_agentes(r)), 200)
        self.assertTrue(any("200 de 205" in a for a in r["avisos"]))
        self.assertEqual(r["sessoes"][0]["agentes_total"], 205)

    def test_pai_por_parent_agent_id_e_por_tool_use(self):
        self.conversa()
        self.agente("p1", {"spawnDepth": 1}, linha_assistente(ferramenta="Agent",
                                                              entrada={"subagent_type": "Explore", "prompt": SEGREDO},
                                                              tid="toolu_filho2"))
        self.agente("f1", {"spawnDepth": 2, "parentAgentId": "p1", "toolUseId": "toolu_filho1"}, linha_assistente())
        self.agente("f2", {"spawnDepth": 2, "toolUseId": "toolu_filho2"}, linha_assistente())
        self.agente("f3", {"spawnDepth": 2, "parentAgentId": "naoexiste"}, linha_assistente())
        por = {a["id"]: a for a in self.todos_agentes(self.montar())}
        self.assertEqual((por["f1"]["pai_id"], por["f1"]["profundidade"]), ("p1", 2))
        self.assertEqual(por["f2"]["pai_id"], "p1")
        self.assertIsNone(por["f3"]["pai_id"])
        self.assertEqual(por["p1"]["ultima_acao"], "Agent Explore")

    def test_so_sessoes_do_projeto_e_estados(self):
        self.conversa()
        self.conversa(SID2)
        self.cli.append({"sessionId": SID2, "cwd": os.path.join(self.raiz, "sub"), "kind": "interactive",
                         "status": "idle", "name": "int"})
        self.cli.append({"sessionId": "77777777-7777-4777-8777-777777777777", "cwd": self.tmp, "kind": "interactive"})
        self.cli.append({"sessionId": "../../etc", "cwd": self.raiz})
        r = self.montar()
        estados = {s["sessao_id"]: (s["tipo"], s["estado"]) for s in r["sessoes"]}
        self.assertEqual(estados, {SID: ("segundo_plano", "rodando"), SID2: ("interativa", "ocioso")})
        self.assertEqual([s["sessao_id"] for s in self.montar(sessao=SID2)["sessoes"]], [SID2])
        self.assertEqual([s["sessao_id"] for s in self.montar(sessao=SID[:8])["sessoes"]], [SID])
        r = self.montar(sessao="../x")
        self.assertEqual((r["sessoes"], r["avisos"]), ([], ["Sessão inválida."]))

    def test_segundo_plano_parado_ha_180s_terminou(self):
        self.conversa(idade=400)
        self.cli[0].update(state="working", status="idle")
        self.assertEqual(self.montar()["sessoes"][0]["estado"], "terminou")
        self.cli[0].update(state="blocked", status="waiting")
        self.assertEqual(self.montar()["sessoes"][0]["estado"], "precisa_de_voce")

    def test_execucao_do_painel(self):
        self.conversa()
        dados = os.path.join(self.tmp, "dados")
        os.makedirs(dados)
        with open(os.path.join(dados, "execucoes.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump([{"id": SID[:8], "nome": "x", "iniciada_em": "2026-11-10T00:00:00"}], f)
        cfg = dict(self.cfg(), dados_dir=dados)
        r = agentes.montar(cfg, rodar=self.rodar, agora=self.agora)
        self.assertEqual(r["sessoes"][0]["execucao_id"], SID[:8])

    def test_cli_falhou(self):
        r = agentes.montar(self.cfg(), rodar=lambda *a: (1, "", "erro"), agora=self.agora)
        self.assertEqual(r["sessoes"], [])
        self.assertEqual(len(r["avisos"]), 1)

    def test_cfg_none_e_objeto(self):
        r = agentes.montar(None, rodar=lambda *a: (0, "[]", ""), agora=self.agora)
        self.assertEqual(set(r), {"gerado_em", "sessoes", "avisos"})

    def test_cache_de_2s(self):
        self.conversa()
        chamadas = []

        def rodar(cmd, cwd, t):
            chamadas.append(1)
            return self.rodar(cmd, cwd, t)
        orig = agentes._rodar_padrao
        agentes._rodar_padrao = rodar
        try:
            agentes.montar(self.cfg())
            agentes.montar(self.cfg())
        finally:
            agentes._rodar_padrao = orig
        self.assertEqual(len(chamadas), 1)


class TestDisco(unittest.TestCase):
    def setUp(self):
        disco.esquecer_tudo()
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_modelo_curto(self):
        casos = {"claude-opus-5-5": "opus", "claude-sonnet-4-5-20250929": "sonnet", "claude-3-5-haiku-20241022": "haiku",
                 "opus": "opus", "claude-opus-4-6[1m]": "opus", "us.anthropic.claude-sonnet-4-5-v1:0": "sonnet",
                 "claude-fable-5-2": "fable", "": None, None: None, "<synthetic>": None}
        for entrada, esperado in casos.items():
            self.assertEqual(disco.modelo_curto(entrada), esperado, entrada)

    def test_contagem_incremental(self):
        p = os.path.join(self.tmp, "a.jsonl")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(linha_assistente(ferramenta="Edit", tid="t1") + blob())
        self.assertEqual(disco.contar(p, os.path.getsize(p))[0], 1)
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(linha_assistente(ferramenta="Agent", tid="t2") + '{"type":"assistant","message":{"content":[{"type":"tool_')
        n, spawns = disco.contar(p, os.path.getsize(p))
        self.assertEqual((n, spawns), (2, ["t2"]))
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write('use","name":"Read","id":"t3"}]}}\n')
        self.assertEqual(disco.contar(p, os.path.getsize(p))[0], 3)

    def test_cauda_le_so_o_fim(self):
        p = os.path.join(self.tmp, "b.jsonl")
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(linha_assistente("claude-haiku-5-5", "low"))
            f.write(json.dumps({"type": "user", "pad": "x" * (disco.CAUDA * 2)}) + "\n")
            f.write(linha_assistente("claude-opus-5-5", "high", "Write", {"file_path": "C:/a/b/c.txt"}))
        fim = disco.cauda(p, os.path.getsize(p))
        self.assertEqual(fim, {"modelo_id": "claude-opus-5-5", "esforco": "high", "ultima_acao": "Write c.txt"})

    def test_ultima_acao_limite(self):
        texto = disco.descrever_ferramenta({"name": "Edit", "input": {"file_path": "/a/" + "x" * 300}})
        self.assertLessEqual(len(texto), 120)


if __name__ == "__main__":
    unittest.main()
