"""Testes do chat: níveis (grupo chat), escolha de modelo pela licença e resposta na mesma sessão.

Nada chama o claude de verdade: o CLI é falso.
"""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

import catalogo  # noqa: E402
import lancador  # noqa: E402
import modelos  # noqa: E402
import transcricao  # noqa: E402
from test_lancador import CLIFalso, cfg_teste  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
PEDIDO = [{"nome": "pedido", "rotulo": "Pedido", "tipo": "texto", "obrigatorio": True, "max": 6000, "linhas": True}]
NIVEL = {"id": "chat.x", "grupo": "chat", "titulo": "Nível", "risco": "leitura", "prompt": "PEDIDO:\n{pedido}\n\nfaça",
         "nome_sessao": "Chat: {pedido}", "modelos": ["fable", "opus"], "esforco": "xhigh", "equipe": "2 agentes",
         "params": PEDIDO}
SONDA_SIM = json.dumps({"is_error": False, "result": "ok", "modelUsage": {"claude-fable-9": {}}})
SONDA_NAO = ('[claude-code:unrecognized_model] {"model":"fable"}\n' + json.dumps(
    {"is_error": True, "api_error_status": 404,
     "result": "There's an issue with the selected model (fable). It may not exist or you may not have access to it."}))
SONDA_TROCOU = json.dumps({"is_error": False, "result": "ok", "modelUsage": {"claude-opus-9": {}}})
SONDA_CAIU = json.dumps({"is_error": True, "api_error_status": 529, "result": "Overloaded"})


class CLIChat(CLIFalso):
    """CLIFalso + sonda de modelo (`-p`), `--bg --resume` e `rm`."""

    def __init__(self, sonda=SONDA_SIM):
        CLIFalso.__init__(self)
        self.sonda, self.copiar, self.demora_sair = sonda, 0, 0

    def __call__(self, cmd, cwd, timeout):
        if cmd[1:2] == ["-p"]:
            self.chamadas.append((list(cmd), cwd))
            return 0, self.sonda, ""
        if cmd[1:3] == ["--bg", "--resume"]:
            self.chamadas.append((list(cmd), cwd))
            alvo = [a for a in self.agentes if a["sessionId"] == cmd[3]]
            if not alvo:
                return 1, "", "No conversation found"
            if alvo[0].get("status") and self.demora_sair:  # o processo antigo ainda não saiu
                self.copiar += 1
            if self.copiar > 0 or alvo[0]["state"] == "working":
                self.copiar -= 1
                self.agentes.append({"id": "c0c0c0c0", "sessionId": "c0c0c0c0-1111-2222-3333-444455556666",
                                     "name": "copia", "cwd": cwd, "kind": "background", "state": "working"})
                return 0, "note: started a copy as c0c0c0c0\nbackgrounded · c0c0c0c0\n", ""
            alvo[0]["state"] = "working"
            return 0, "note: woke session %s with its saved options\nbackgrounded · %s · x\n" % (
                alvo[0]["id"], alvo[0]["id"]), ""
        if cmd[1:2] == ["rm"]:
            self.chamadas.append((list(cmd), cwd))
            self.agentes = [a for a in self.agentes if a["id"] != cmd[2]]
            return 0, "removed", ""
        if cmd[1:2] == ["agents"] and self.demora_sair:  # cada olhada na lista deixa o processo mais perto de sair
            self.demora_sair -= 1
            if not self.demora_sair:
                for a in self.agentes:
                    if a.get("parando"):
                        a.pop("status", None)
        if cmd[1:2] == ["stop"]:
            for a in self.agentes:
                if a["id"] == cmd[2]:
                    a["parando"] = True
                    if not self.demora_sair:
                        a.pop("status", None)
        return CLIFalso.__call__(self, cmd, cwd, timeout)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        os.makedirs(os.path.join(self.tmp, "acoes"))
        self.gravar_acoes([NIVEL])
        self.t = [1000.0]
        self.cli = CLIChat()

    def gravar_acoes(self, acoes, pasta="acoes"):
        os.makedirs(os.path.join(self.tmp, pasta), exist_ok=True)
        with open(os.path.join(self.tmp, pasta, "chat.json"), "w", encoding="utf-8") as f:
            json.dump({"acoes": acoes}, f)

    def lanc(self, **extra):
        lc = lancador.Lancador(cfg_teste(self.tmp, **extra), lambda: {}, rodar=self.cli, relogio=lambda: self.t[0])
        self.sonos = []
        lc.dormir = self.sonos.append
        return lc

    def bg(self):
        return [c[0] for c in self.cli.chamadas if c[0][1:2] == ["--bg"]]


class TesteCatalogoChat(Base):
    def test_chat_json_real(self):
        acoes, avisos = catalogo.carregar_catalogo(os.path.join(AQUI, "acoes"))
        self.assertEqual([x for x in avisos if x.startswith("chat.json")], [])
        niveis = [a for a in acoes if a["grupo"] == "chat"]
        self.assertEqual([a["id"] for a in niveis],
                         ["chat.pergunta", "chat.simples", "chat.moderado", "chat.completo", "chat.marketing"])
        por_id = {a["id"]: a for a in niveis}
        self.assertEqual(por_id["chat.completo"]["modelos"], ["fable", "opus"])
        self.assertEqual(por_id["chat.simples"]["modelos"], ["opus"])
        self.assertTrue(por_id["chat.simples"]["confirmar"] and por_id["chat.moderado"]["confirmar"])
        self.assertEqual(por_id["chat.completo"]["risco"], "rascunho")  # só plano: não mexe em código
        for a in niveis:
            self.assertEqual([p["nome"] for p in a["params"]], ["pedido"])
            self.assertTrue(a["params"][0]["linhas"])
            self.assertIn(a["esforco"], catalogo.ESFORCOS)
            self.assertTrue(a["equipe"])
            publica = catalogo.publica(a)
            self.assertEqual(sorted(k for k in publica if k.startswith("_")), [])
            self.assertIn("modelos", publica)
        self.assertIn("Write", por_id["chat.pergunta"]["_travas"]["negar"])

    def test_campos_novos_validados(self):
        ok = catalogo.validar_acao(dict(NIVEL, modelos="opus"))
        self.assertEqual((ok["modelos"], ok["esforco"], ok["equipe"]), (["opus"], "xhigh", "2 agentes"))
        sem = catalogo.validar_acao({"id": "a.b", "grupo": "dev", "risco": "leitura", "prompt": "/x"})
        self.assertEqual((sem["modelos"], sem["esforco"], sem["equipe"]), ([], None, ""))
        for ruim in ({"modelos": []}, {"modelos": ["opus", "opus"]}, {"modelos": ["--flag"]}, {"modelos": 3},
                     {"modelos": ["a", "b", "c", "d", "e"]}, {"esforco": "turbo"}, {"equipe": "a\nb"}):
            with self.assertRaises(ValueError, msg=str(ruim)):
                catalogo.validar_acao(dict(NIVEL, **ruim))

    def test_nivel_do_chat_exige_um_pedido(self):
        for params in ([], PEDIDO + [{"nome": "x", "tipo": "texto"}], [dict(PEDIDO[0], nome="ideia")],
                       [dict(PEDIDO[0], obrigatorio=False)]):
            with self.assertRaises(ValueError):
                catalogo.validar_acao(dict(NIVEL, params=params, prompt="/x", nome_sessao=None))

    def test_texto_com_linhas(self):
        acao = catalogo.validar_acao(NIVEL)
        v = catalogo.validar_params(acao, {"pedido": " um\r\ndois\n\n\n\n- três\t! "}, {})
        self.assertEqual(v["pedido"], "um\ndois\n\n- três !")
        self.assertEqual(catalogo.montar(acao["_prompt"], v), "PEDIDO:\num\ndois\n\n- três !\n\nfaça")
        self.assertEqual(catalogo.nome_da_sessao(acao, v), "Chat: um dois - três !")
        for ruim in ("-rf", "a\x00b", "a\x1b[0m", "x" * 6001):
            with self.assertRaises(catalogo.ErroAcao, msg=repr(ruim[:10])):
                catalogo.validar_params(acao, {"pedido": ruim}, {})
        sem_linhas = catalogo.validar_acao({"id": "a.b", "grupo": "dev", "risco": "leitura", "prompt": "/x {t}",
                                           "params": [{"nome": "t", "tipo": "texto", "max": 6000}]})
        self.assertEqual(sem_linhas["params"][0]["max"], catalogo.TEXTO_PADRAO)  # teto maior só com linhas
        with self.assertRaises(catalogo.ErroAcao):
            catalogo.validar_params(sem_linhas, {"t": "a\nb"}, {})

    def test_pacote_troca_nivel_so_com_substitui(self):
        self.gravar_acoes([dict(NIVEL, titulo="Do pacote", substitui=True),
                           dict(NIVEL, id="chat.novo", titulo="Novo")], pasta="pacote/acoes")
        pastas = [os.path.join(self.tmp, "acoes"), os.path.join(self.tmp, "pacote", "acoes")]
        acoes, avisos = catalogo.carregar_catalogo(pastas)
        self.assertEqual([(a["id"], a["titulo"]) for a in acoes], [("chat.x", "Do pacote"), ("chat.novo", "Novo")])
        self.assertEqual(avisos, [])
        self.gravar_acoes([dict(NIVEL, titulo="Do pacote")], pasta="pacote/acoes")  # sem substitui: ignora e avisa
        acoes, avisos = catalogo.carregar_catalogo(pastas)
        self.assertEqual([(a["id"], a["titulo"]) for a in acoes], [("chat.x", "Nível")])
        self.assertEqual(len(avisos), 1)
        # o núcleo não troca a si mesmo
        self.gravar_acoes([NIVEL, dict(NIVEL, titulo="Outro", substitui=True)])
        acoes, avisos = catalogo.carregar_catalogo(pastas[:1])
        self.assertEqual([a["titulo"] for a in acoes], ["Nível"])


class TesteModelos(Base):
    def test_ler_resposta(self):
        self.assertIs(modelos.ler_resposta(0, SONDA_SIM), True)
        self.assertIs(modelos.ler_resposta(0, SONDA_NAO), False)
        self.assertIs(modelos.ler_resposta(0, SONDA_CAIU), None)
        self.assertIs(modelos.ler_resposta(124, ""), None)
        self.assertIs(modelos.ler_resposta(1, "lixo"), None)
        self.assertIs(modelos.ler_resposta(1, SONDA_SIM), None)
        self.assertFalse(modelos.atendeu_com(SONDA_TROCOU, "fable"))
        self.assertTrue(modelos.atendeu_com(SONDA_SIM, "fable"))
        self.assertTrue(modelos.atendeu_com(SONDA_TROCOU, "claude-nome-inteiro"))

    def test_licenca_com_o_preferido(self):
        ex = self.lanc().iniciar("chat.x", {"pedido": "oi"})
        cmd = self.bg()[0]
        self.assertEqual(cmd[cmd.index("--model") + 1], "fable")
        self.assertEqual(cmd[cmd.index("--effort") + 1], "xhigh")
        self.assertEqual(cmd[-1], "PEDIDO:\noi\n\nfaça")
        self.assertEqual((ex["modelo"], ex["esforco"]), ("fable", "xhigh"))
        sonda = [c[0] for c in self.cli.chamadas if c[0][1:2] == ["-p"]]
        self.assertEqual(len(sonda), 1)
        self.assertEqual(sonda[0][sonda[0].index("--tools") + 1], "")
        self.assertIn("--safe-mode", sonda[0])
        self.assertIn("--no-session-persistence", sonda[0])

    def test_licenca_sem_o_preferido_cai_na_reserva(self):
        self.cli.sonda = SONDA_NAO
        lc = self.lanc()
        ex = lc.iniciar("chat.x", {"pedido": "oi"})
        self.assertEqual(ex["modelo"], "opus")
        self.assertEqual(lc.status_modelos(), {"fable": "nao"})
        # a reserva nunca é sondada e a resposta fica guardada: uma sonda só
        lc.iniciar("chat.x", {"pedido": "outro"})
        self.assertEqual(len([c for c in self.cli.chamadas if c[0][1:2] == ["-p"]]), 1)
        self.t[0] += modelos.VALE_NAO + 1  # venceu: pergunta de novo
        self.cli.sonda = SONDA_SIM
        self.assertEqual(lc.modelos.escolher(["fable", "opus"]), ("fable", []))

    def test_troca_calada_de_modelo_conta_como_nao_ter(self):
        self.cli.sonda = SONDA_TROCOU
        self.assertEqual(self.lanc().modelos.escolher(["fable", "opus"]), ("opus", ["fable"]))

    def test_sonda_que_falha_nao_fica_guardada(self):
        self.cli.sonda = SONDA_CAIU
        lc = self.lanc()
        self.assertEqual(lc.modelos.escolher(["fable", "opus"]), ("opus", ["fable"]))
        self.assertFalse(os.path.exists(lc.modelos.arquivo))
        self.cli.sonda = SONDA_SIM
        self.assertEqual(lc.modelos.escolher(["fable", "opus"])[0], "opus")  # não insiste antes de 10 min
        self.t[0] += modelos.VALE_NAO_SEI + 1
        self.assertEqual(lc.modelos.escolher(["fable", "opus"])[0], "fable")
        if os.name != "nt":  # Windows não tem modo 0600
            self.assertEqual(oct(os.stat(lc.modelos.arquivo).st_mode & 0o777), "0o600")

    def test_painel_json_vence_a_sonda(self):
        lc = self.lanc(modelos_disponiveis={"fable": False})
        self.assertEqual(lc.modelos.escolher(["fable", "opus"]), ("opus", ["fable"]))
        self.assertEqual([c for c in self.cli.chamadas if c[0][1:2] == ["-p"]], [])
        self.assertEqual(lc.status_modelos(), {"fable": "nao"})

    def test_acao_sem_modelo_nao_passa_opcao(self):
        self.gravar_acoes([{k: v for k, v in NIVEL.items() if k not in ("modelos", "esforco")}])
        ex = self.lanc().iniciar("chat.x", {"pedido": "oi"})
        self.assertNotIn("--model", self.bg()[0])
        self.assertNotIn("--effort", self.bg()[0])
        self.assertEqual((ex["modelo"], ex["esforco"]), ("", ""))


class TesteResponder(Base):
    def comecar(self):
        lc = self.lanc()
        ex = lc.iniciar("chat.x", {"pedido": "oi"})
        lc.execucoes(forcar=True)  # aprende o sessionId
        return lc, ex["id"]

    def terminar(self, exec_id):
        for a in self.cli.agentes:
            if a["id"] == exec_id:
                a.update(state="done", status="idle")

    def test_so_responde_quando_terminou(self):
        lc, i = self.comecar()
        self.assertFalse(lc.execucao(i)["pode_responder"])
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder(i, "e agora?")
        self.assertEqual(e.exception.codigo, 409)
        self.cli.agentes[0].update(state="blocked", status="waiting")
        lc.esquecer_agentes()
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder(i, "e agora?")
        self.assertEqual(e.exception.codigo, 409)
        self.assertIn("terminal", e.exception.mensagem)
        self.assertEqual([c for c in self.bg() if "--resume" in c], [])

    def test_responde_na_mesma_sessao_sem_opcao_nenhuma(self):
        lc, i = self.comecar()
        self.terminar(i)
        lc.esquecer_agentes()
        self.assertTrue(lc.execucao(i)["pode_responder"])
        self.t[0] += 500
        ex = lc.responder(i, "muda para\nazul")
        self.assertEqual((ex["id"], ex["estado"], ex["pode_responder"]), (i, "rodando", False))
        chamadas = [c[0] for c in self.cli.chamadas]
        retomada = [c for c in chamadas if c[1:3] == ["--bg", "--resume"]]
        self.assertEqual(retomada, [["claude", "--bg", "--resume", i + "-1111-2222-3333-444455556666",
                                     "muda para\nazul"]])
        # para o processo antigo ANTES de acordar (senão o CLI abre uma cópia)
        self.assertLess(chamadas.index(["claude", "stop", i]), chamadas.index(retomada[0]))
        reg = lc.achar(i)
        self.assertEqual((reg["terminou_em"], reg["parada_pelo_painel"]), ("", False))
        self.assertEqual(lc.execucao(i)["estado"], "rodando")
        # o CLI ainda mostrando a linha velha por alguns segundos não vira "terminou"
        self.terminar(i)
        lc.esquecer_agentes()
        self.assertEqual(lc.execucao(i)["estado"], "rodando")
        self.t[0] += lancador.GRACA + 1
        lc.esquecer_agentes()
        self.assertEqual(lc.execucao(i)["estado"], "terminou")

    def test_copia_e_parada_e_apagada(self):
        lc, i = self.comecar()
        self.terminar(i)
        lc.esquecer_agentes()
        self.cli.copiar = 2  # o CLI insiste em abrir cópia nas duas tentativas
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder(i, "oi")
        self.assertEqual(e.exception.codigo, 500)
        chamadas = [c[0] for c in self.cli.chamadas]
        self.assertEqual(chamadas.count(["claude", "stop", "c0c0c0c0"]), 2)
        self.assertEqual(chamadas.count(["claude", "rm", "c0c0c0c0"]), 2)
        self.assertEqual([a["id"] for a in self.cli.agentes], [i])
        self.assertFalse(lc.achar(i).get("respondida_ts"))

    def test_copia_que_nao_para_fica_no_registro(self):
        lc, i = self.comecar()
        self.terminar(i)
        lc.esquecer_agentes()
        self.cli.copiar = 1
        normal = self.cli.__call__

        def cli(cmd, cwd, timeout):
            if cmd[1:] == ["stop", "c0c0c0c0"]:
                self.cli.chamadas.append((list(cmd), cwd))
                return 1, "", "falhou"
            if cmd[1:] == ["rm", "c0c0c0c0"]:
                return 1, "", "ainda rodando"
            return normal(cmd, cwd, timeout)
        lc.rodar = cli
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder(i, "oi")
        self.assertEqual((e.exception.codigo, e.exception.execucao_id), (500, "c0c0c0c0"))
        self.assertEqual(len([c for c in self.bg() if "--resume" in c]), 1)  # não tenta de novo com cópia solta
        orfa = lc.execucao("c0c0c0c0")
        self.assertEqual((orfa["estado"], orfa["titulo"]), ("rodando", "Cópia que não parou"))

    def test_niveis_que_so_leem_tem_trava_de_verdade(self):
        import travas
        acoes = {a["id"]: a for a in catalogo.carregar_catalogo(os.path.join(AQUI, "acoes"))[0]}

        def decide(nivel, comando):
            r = travas.decidir(travas.config_gancho(acoes[nivel]), "Bash", {"command": comando})
            return r[0] if r else None
        for cmd in ("git commit -m x", "git -C /repo push origin main", "gh pr create --fill", "gh pr merge 3"):
            self.assertEqual(decide("chat.pergunta", cmd), "deny", cmd)
            self.assertEqual(decide("chat.completo", cmd), "deny", cmd)
        for cmd in ("sed -i '' s/a/b/ x.py", "echo oi > x.txt", "echo oi >> x.txt", "rm x", "git add x", "tee x",
                    "curl -X POST https://x.test -d a=1", "curl https://x.test --data-binary @f", "mkdir a"):
            self.assertEqual(decide("chat.pergunta", cmd), "deny", cmd)
        for cmd in ("git status", "git log --oneline -5", "git diff main", "grep -rn foo . 2>/dev/null", "ls -la 2>&1",
                    "cat x | head", "curl -s https://x.test/doc", "gh pr list", "git fetch"):
            self.assertIsNone(decide("chat.pergunta", cmd), cmd)
        for cmd in ("git fetch", "git worktree add --detach /tmp/wt origin/main", "mkdir -p plans/phases/001-x",
                    "ls plans/phases | sort > /tmp/x"):
            self.assertIsNone(decide("chat.completo", cmd), cmd)  # o plano precisa disso

    def test_interromper_manda_na_mesma_sessao(self):
        lc = self.lanc(max_execucoes=1)
        i = lc.iniciar("chat.x", {"pedido": "um"})["id"]
        ex = lc.execucao(i)  # rodando, com sessionId já aprendido
        self.assertEqual((ex["estado"], ex["pode_responder"], ex["pode_interromper"]), ("rodando", False, True))
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder(i, "espera")
        self.assertEqual(e.exception.codigo, 409)
        # CLI falso: stop numa sessão trabalhando deixa state=stopped; a retomada acorda a mesma
        ex = lc.responder(i, "muda de ideia", interromper=True)  # não esbarra no teto: a vaga já é dela
        self.assertEqual((ex["id"], ex["estado"]), (i, "rodando"))
        chamadas = [c[0] for c in self.cli.chamadas]
        self.assertIn(["claude", "stop", i], chamadas)
        self.assertEqual([c for c in chamadas if c[1:3] == ["--bg", "--resume"]][0][-1], "muda de ideia")
        # esperando no terminal também aceita
        self.cli.agentes[0].update(state="blocked", status="waiting")
        self.t[0] += lancador.GRACA + 1
        lc.esquecer_agentes()
        self.assertTrue(lc.execucao(i)["pode_interromper"])
        self.cli.agentes[0].pop("status")
        self.cli.agentes[0]["state"] = "stopped"
        self.assertEqual(lc.responder(i, "Azul", interromper=True)["id"], i)

    def test_pergunta_vai_para_o_chat(self):
        import io
        import travas
        lc, i = self.comecar()
        sid = i + "-1111-2222-3333-444455556666"
        cmd = self.bg()[0]
        conf = json.loads(cmd[cmd.index("--settings") + 1])
        gancho = conf["hooks"]["PreToolUse"][0]["hooks"][0]["command"].split()[-1]
        entrada = {"tool_name": "AskUserQuestion", "session_id": sid, "tool_input": {"questions": [
            {"question": "Qual cor?", "header": "Cor", "multiSelect": False,
             "options": [{"label": "Azul", "description": "cor azul"}, {"label": "Verde"}, {"label": ""}, "lixo"]},
            {"question": ""}, "lixo"]}}
        saida = io.StringIO()
        travas.principal(["travas.py", gancho], io.StringIO(json.dumps(entrada)), saida)
        resp = json.loads(saida.getvalue())["hookSpecificOutput"]
        self.assertEqual(resp["permissionDecision"], "deny")
        self.assertIn("chat", resp["permissionDecisionReason"])
        arq = os.path.join(self.tmp, "dados", "perguntas", sid + ".json")
        self.assertEqual(oct(os.stat(arq).st_mode & 0o777), "0o600")
        self.assertNotIn("pergunta", lc.execucao(i))  # ainda rodando: a pergunta só aparece quando dá para responder
        self.cli.agentes[0].update(state="blocked", status="waiting", waitingFor="input needed")
        lc.esquecer_agentes()  # preso no terminal (permissão): não é resposta de texto comum
        self.assertEqual((lc.execucao(i)["estado"], lc.execucao(i)["pode_responder"]), ("precisa_de_voce", False))
        self.cli.agentes[0].pop("waitingFor")
        self.cli.agentes[0].update(state="blocked", status="idle")  # a vez acabou com a pergunta escrita
        lc.esquecer_agentes()
        self.assertEqual((lc.execucao(i)["estado"], lc.execucao(i)["pode_responder"]), ("precisa_de_voce", True))
        self.assertEqual(lc.execucao(i)["pergunta"], {"perguntas": [
            {"pergunta": "Qual cor?", "cabecalho": "Cor", "multipla": False,
             "opcoes": [{"rotulo": "Azul", "descricao": "cor azul"}, {"rotulo": "Verde", "descricao": ""}]}]})
        lc.responder(i, "Azul")
        self.assertFalse(os.path.exists(arq))
        # sessionId fora do formato não vira nome de arquivo; ação fora do chat não barra a pergunta
        ruim = dict(entrada, session_id="../../fuga")
        travas.principal(["travas.py", gancho], io.StringIO(json.dumps(ruim)), io.StringIO())
        self.assertEqual(os.listdir(os.path.join(self.tmp, "dados", "perguntas")), [])
        fora = catalogo.validar_acao({"id": "a.b", "grupo": "dev", "risco": "leitura", "prompt": "/x"})
        self.assertNotIn("perg", travas.config_gancho(fora, perguntas_dir="/tmp/x"))
        self.assertIsNone(travas.decidir(travas.config_gancho(fora), "AskUserQuestion", entrada["tool_input"]))

    def _com_pergunta(self, conteudo=None, bruto=None):
        """Sessão que terminou a vez com pergunta; devolve (lançador, id, caminho do arquivo)."""
        lc, i = self.comecar()
        sid = i + "-1111-2222-3333-444455556666"
        pasta = os.path.join(self.tmp, "dados", "perguntas")
        os.makedirs(pasta, exist_ok=True)
        arq = os.path.join(pasta, sid + ".json")
        if bruto is not None or conteudo is not None:
            with open(arq, "w", encoding="utf-8") as f:
                f.write(bruto if bruto is not None else json.dumps(conteudo))
        self.cli.agentes[0].update(state="blocked", status="idle")
        lc.esquecer_agentes()
        return lc, i, arq

    def test_pergunta_sai_mascarada(self):
        lc, i, _arq = self._com_pergunta({"perguntas": [{"pergunta": "Mando para joao.silva@cliente.com.br?",
                                                         "opcoes": [{"rotulo": "Ligar 11 98765-4321",
                                                                     "descricao": "chave sk-abcdefghijklmnopqrstu"}]}]})
        texto = json.dumps(lc.execucao(i)["pergunta"], ensure_ascii=False)
        for cru in ("joao.silva", "98765", "abcdefghijklmnop"):
            self.assertNotIn(cru, texto)

    def test_arquivo_de_pergunta_ruim_nunca_derruba_a_lista(self):
        lc, i, arq = self._com_pergunta()
        for bruto in ('{"perguntas": 5}', '{"perguntas": [{"pergunta": "x", "opcoes": 7}]}', "[1]", "{quebrado",
                      '{"perguntas": [5, {"pergunta": "", "opcoes": [{"rotulo": "A"}]}]}', "x" * 70000):
            with open(arq, "w", encoding="utf-8") as f:
                f.write(bruto)
            ex = lc.execucao(i)  # não levanta
            self.assertTrue(ex["pode_responder"], bruto[:20])
            if "opcoes\": 7" not in bruto:
                self.assertNotIn("pergunta", ex, bruto[:20])
            os.unlink(arq)
        if hasattr(os, "mkfifo"):  # um FIFO no lugar do arquivo não pode prender o painel
            os.mkfifo(arq)
            import threading
            feito = []
            t = threading.Thread(target=lambda: feito.append(lc.execucao(i)), daemon=True)
            t.start()
            t.join(5)
            self.assertTrue(feito, "ficou preso lendo o FIFO")
            self.assertNotIn("pergunta", feito[0])
            os.unlink(arq)
        if hasattr(os, "symlink"):
            alvo = os.path.join(self.tmp, "fora.json")
            with open(alvo, "w") as f:
                json.dump({"perguntas": [{"pergunta": "de fora", "opcoes": [{"rotulo": "A"}]}]}, f)
            os.symlink(alvo, arq)
            self.assertNotIn("pergunta", lc.execucao(i))

    def test_pergunta_velha_nao_volta(self):
        import io
        import travas
        boa = {"perguntas": [{"pergunta": "Qual?", "opcoes": [{"rotulo": "A"}]}]}
        # 1) gravada antes do começo desta vez (antes da última resposta)
        lc, i, arq = self._com_pergunta(boa)
        self.assertIn("pergunta", lc.execucao(i))
        lc.registro.atualizar(i, respondida_ts=os.path.getmtime(arq) + 60)
        self.assertNotIn("pergunta", lc.execucao(i))
        lc.registro.atualizar(i, respondida_ts=0)
        # 2) a conversa seguiu muito depois da pergunta
        sid = i + "-1111-2222-3333-444455556666"
        pasta = os.path.join(self.tmp, "proj", transcricao.pasta_do_projeto(self.tmp))
        os.makedirs(pasta, exist_ok=True)
        conversa = os.path.join(pasta, sid + ".jsonl")
        open(conversa, "w").close()
        os.utime(conversa, (os.path.getmtime(arq) + 5, os.path.getmtime(arq) + 5))
        self.assertIn("pergunta", lc.execucao(i))  # perguntou e parou logo depois: vale
        os.utime(conversa, (os.path.getmtime(arq) + lancador.PERGUNTA_VALE + 5,) * 2)
        self.assertNotIn("pergunta", lc.execucao(i))
        # 3) o gancho apaga a pergunta quando a sessão usa outra ferramenta
        cmd = self.bg()[-1]
        gancho = json.loads(cmd[cmd.index("--settings") + 1])["hooks"]["PreToolUse"][0]["hooks"][0]["command"].split()[-1]
        travas.principal(["travas.py", gancho], io.StringIO(json.dumps(
            {"tool_name": "Read", "session_id": sid, "tool_input": {"file_path": "/tmp/x"}})), io.StringIO())
        self.assertFalse(os.path.exists(arq))

    def test_pedido_preso_no_terminal_e_avisado(self):
        lc, i = self.comecar()
        self.cli.agentes[0].update(state="blocked", status="waiting", waitingFor="permission")
        lc.esquecer_agentes()
        ex = lc.execucao(i)
        self.assertEqual((ex["estado"], ex["pode_responder"], ex["pode_interromper"], ex["espera_terminal"]),
                         ("precisa_de_voce", False, True, True))
        self.cli.agentes[0].pop("waitingFor")
        self.cli.agentes[0].update(state="blocked", status="idle")
        lc.esquecer_agentes()
        ex = lc.execucao(i)
        self.assertEqual((ex["pode_responder"], ex["espera_terminal"]), (True, False))
        # respondida: a linha velha "blocked" sem processo não volta a aparecer como espera
        self.t[0] += 500
        lc.responder(i, "Azul")
        self.cli.agentes[0].pop("status", None)
        self.cli.agentes[0]["state"] = "blocked"
        lc.esquecer_agentes()
        self.assertEqual(lc.execucao(i)["estado"], "rodando")

    def test_fala_automatica_de_interrupcao_some(self):
        linha = {"type": "assistant", "message": {"content": [{"type": "text", "text": "No response requested."},
                                                              {"type": "text", "text": "Azul"}]}}
        self.assertEqual([e[1] for e in transcricao.eventos_da_linha(linha)], ["Azul"])

    def test_copia_na_primeira_tentativa_e_refeita(self):
        lc, i = self.comecar()
        self.terminar(i)
        lc.esquecer_agentes()
        self.cli.copiar = 1
        ex = lc.responder(i, "oi")
        self.assertEqual((ex["id"], ex["estado"]), (i, "rodando"))
        self.assertEqual([a["id"] for a in self.cli.agentes], [i])  # a cópia foi apagada

    def test_espera_o_processo_antigo_sair(self):
        lc, i = self.comecar()
        self.terminar(i)
        lc.esquecer_agentes()
        lc.execucao(i)
        self.cli.demora_sair = 4  # o `stop` volta, mas o processo só some depois de algumas olhadas
        ex = lc.responder(i, "oi")
        self.assertEqual(ex["id"], i)
        self.assertEqual(len([c for c in self.bg() if "--resume" in c]), 1)  # acordou de primeira, sem cópia
        self.assertTrue(self.sonos)

    def test_sessao_apagada_nao_responde(self):
        lc, i = self.comecar()
        self.terminar(i)
        lc.esquecer_agentes()
        lc.execucoes(forcar=True)  # grava terminou_em
        self.cli.agentes = []
        lc.esquecer_agentes()
        ex = lc.execucao(i)
        self.assertEqual((ex["estado"], ex["pode_responder"]), ("terminou", False))
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder(i, "oi")
        self.assertEqual(e.exception.codigo, 409)

    def test_texto_ruim_e_execucao_inexistente(self):
        lc, i = self.comecar()
        self.terminar(i)
        lc.esquecer_agentes()
        for ruim in ("", "   ", "-p", None, 3, "a\x00b", "x" * 6001):
            with self.assertRaises(lancador.ErroAcao, msg=repr(ruim)[:12]) as e:
                lc.responder(i, ruim)
            self.assertEqual(e.exception.codigo, 400)
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder("deadbeef", "oi")
        self.assertEqual(e.exception.codigo, 404)
        self.assertEqual([c for c in self.bg() if "--resume" in c], [])

    def test_respeita_o_teto(self):
        lc = self.lanc(max_execucoes=1)
        i = lc.iniciar("chat.x", {"pedido": "um"})["id"]
        lc.execucoes(forcar=True)
        self.terminar(i)
        lc.esquecer_agentes()
        lc.iniciar("chat.x", {"pedido": "dois"})
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder(i, "oi")
        self.assertEqual(e.exception.codigo, 409)


class TesteFalaInteira(unittest.TestCase):
    def test_corte_so_muda_nas_falas(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        arq = os.path.join(tmp, "s.jsonl")
        longo = "palavra " * 400  # 3200 letras
        linhas = [{"type": "user", "message": {"content": longo}},
                  {"type": "assistant", "message": {"content": [
                      {"type": "text", "text": longo},
                      {"type": "tool_use", "name": "Bash", "input": {"command": "echo " + longo}}]}}]
        with open(arq, "w", encoding="utf-8") as f:
            for linha in linhas:
                f.write(json.dumps(linha) + "\n")
        curto = transcricao.ler(arq, 0)["eventos"]
        inteiro = transcricao.ler(arq, 0, corte_fala=transcricao.CORTE_INTEIRO)["eventos"]
        self.assertEqual([e["tipo"] for e in inteiro], ["usuario", "assistente", "ferramenta"])
        self.assertTrue(all(len(e["texto"]) <= transcricao.CORTE for e in curto))
        self.assertEqual([len(e["texto"]) for e in inteiro[:2]], [len(longo.strip())] * 2)
        self.assertLessEqual(len(inteiro[2]["texto"]), transcricao.CORTE_ALVO)


class TesteRotasDoChat(Base):
    def setUp(self):
        Base.setUp(self)
        import http.client
        import threading
        import painel
        self.http = http.client
        os.makedirs(os.path.join(self.tmp, "plans", "phases"))
        cfg = cfg_teste(self.tmp)
        self.lc = lancador.Lancador(cfg, lambda: {}, rodar=self.cli, relogio=lambda: self.t[0])
        self.app = painel.App(cfg, os.path.join(self.tmp, "plans"), lancador=self.lc, rodar_externos=False)
        self.app.log = False
        self.srv = painel.criar_servidor(self.app, 0)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def pedir(self, metodo, caminho, corpo=None):
        cab = {}
        if metodo == "POST":
            cab = {"Origin": "http://127.0.0.1:%d" % self.app.porta, "Content-Type": "application/json",
                   "X-Painel-Token": self.app.token}
            corpo = json.dumps(corpo).encode("utf-8")
        c = self.http.HTTPConnection("127.0.0.1", self.app.porta, timeout=10)
        try:
            c.request(metodo, caminho, body=corpo, headers=cab)
            r = c.getresponse()
            return r.status, json.loads(r.read().decode("utf-8"))
        finally:
            c.close()

    def test_conversa_inteira_pela_api(self):
        st, d = self.pedir("GET", "/api/acoes")
        nivel = [a for a in d["acoes"] if a["grupo"] == "chat"][0]
        self.assertEqual((nivel["modelos"], nivel["esforco"], nivel["equipe"]), (["fable", "opus"], "xhigh", "2 agentes"))
        self.assertTrue(nivel["params"][0]["linhas"])
        self.assertNotIn("prompt", nivel)
        st, d = self.pedir("GET", "/api/modelos")
        self.assertEqual(st, 200)
        self.assertIn(d["modelos"]["fable"], ("verificando", "sim"))

        st, d = self.pedir("POST", "/api/execucoes", {"acao": "chat.x", "params": {"pedido": "linha 1\nlinha 2"}})
        self.assertEqual(st, 201)
        i = d["execucao"]["id"]
        self.assertEqual((d["execucao"]["modelo"], d["execucao"]["pode_responder"]), ("fable", False))
        self.assertEqual(self.pedir("GET", "/api/modelos")[1], {"modelos": {"fable": "sim"}})

        st, d = self.pedir("POST", "/api/execucoes/%s/responder" % i, {"texto": "e agora?"})
        self.assertEqual((st, d.get("execucao_id")), (409, i))
        self.lc.execucoes(forcar=True)
        self.cli.agentes[0].update(state="done", status="idle")
        self.lc.esquecer_agentes()
        st, d = self.pedir("GET", "/api/execucoes")
        self.assertTrue(d["execucoes"][0]["pode_responder"])
        self.assertEqual(self.pedir("POST", "/api/execucoes/%s/responder" % i, {"texto": ""})[0], 400)
        self.assertEqual(self.pedir("POST", "/api/execucoes/%s/responder" % i, {})[0], 400)
        self.assertEqual(self.pedir("POST", "/api/execucoes/deadbeef/responder", {"texto": "oi"})[0], 404)
        st, d = self.pedir("POST", "/api/execucoes/%s/responder" % i, {"texto": "e agora?"})
        self.assertEqual((st, d["execucao"]["id"], d["execucao"]["estado"]), (200, i, "rodando"))
        self.assertEqual(self.pedir("GET", "/api/execucoes/%s/responder" % i)[0], 405)

    def test_eventos_inteiro(self):
        st, d = self.pedir("POST", "/api/execucoes", {"acao": "chat.x", "params": {"pedido": "oi"}})
        i = d["execucao"]["id"]
        self.lc.execucoes(forcar=True)
        pasta = os.path.join(self.tmp, "proj", transcricao.pasta_do_projeto(self.tmp))
        os.makedirs(pasta)
        with open(os.path.join(pasta, i + "-1111-2222-3333-444455556666.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "resposta " * 300}]}}) + "\n")
        curto = self.pedir("GET", "/api/execucoes/%s/eventos?desde=0" % i)[1]["eventos"][0]["texto"]
        inteiro = self.pedir("GET", "/api/execucoes/%s/eventos?desde=0&inteiro=1" % i)[1]["eventos"][0]["texto"]
        self.assertEqual((len(curto), len(inteiro)), (transcricao.CORTE, len(("resposta " * 300).strip())))


if __name__ == "__main__":
    unittest.main()
