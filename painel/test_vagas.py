"""Testes do teto contando as sessões abertas fora do painel (vagas.py). Nada chama o claude de verdade."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

import config  # noqa: E402
import lancador  # noqa: E402
import vagas  # noqa: E402
from test_chat import Base as BaseChat, CLIChat  # noqa: E402

SID = "dddddddd-1111-4222-8333-%012d"


class CLIFora(CLIChat):
    """CLIChat + linhas abertas fora do painel (`fora`) e a lista crua que o CLI devolve (`crua`)."""

    def __init__(self):
        CLIChat.__init__(self)
        self.fora, self.crua = [], None

    def __call__(self, cmd, cwd, timeout):
        if cmd[1:2] == ["agents"]:
            CLIChat.__call__(self, cmd, cwd, timeout)
            return self.crua or (0, json.dumps(self.agentes + self.fora), "")
        return CLIChat.__call__(self, cmd, cwd, timeout)


class Base(BaseChat):
    def setUp(self):
        super().setUp()
        self.cli = CLIFora()

    def lanc(self, **extra):
        return super().lanc(**dict({"max_execucoes": 2}, **extra))

    def linha(self, n=1, **extra):
        """Linha interativa como o CLI devolve: sem `id` e sem `state`."""
        return dict({"sessionId": SID % n, "status": "busy", "pid": 10 + n, "cwd": self.tmp, "kind": "interactive"}, **extra)

    def iniciar(self, lc, pedido="um"):
        return lc.iniciar("chat.x", {"pedido": pedido})["id"]

    def recusa(self, lc, pedido="novo"):
        antes = len(self.bg())
        with self.assertRaises(lancador.ErroAcao) as e:
            self.iniciar(lc, pedido)
        self.assertEqual((e.exception.codigo, e.exception.execucao_id), (409, None))
        self.assertEqual(len(self.bg()), antes)
        self.assertEqual([c for c, _ in self.cli.chamadas if c[1:2] == ["stop"]], [])  # nada é parado
        return e.exception.mensagem

    def terminada(self, lc):
        i = self.iniciar(lc)
        lc.execucoes(forcar=True)  # aprende o sessionId
        self.cli.agentes[0].update(state="done")
        self.t[0] += lancador.GRACA + 1
        lc.esquecer_agentes()
        return i


class TesteConta(Base):
    def test_padrao_2(self):
        os.makedirs(os.path.join(self.tmp, ".git"))
        self.assertEqual(config.carregar(self.tmp)["max_execucoes"], 2)

    def test_so_de_fora_enche_o_teto(self):
        lc = self.lanc()
        self.cli.fora = [self.linha(1), self.linha(2, cwd=os.path.join(self.tmp, "sub"))]
        self.assertEqual(self.recusa(lc), "Já tem 2 rodando ao mesmo tempo (2 abertas fora do painel). "
                                          "O limite é 2. Espere uma acabar ou pare uma.")
        self.cli.fora.pop()
        self.iniciar(lc)  # com uma vaga, entra

    def test_mistura_diz_quantas_de_fora(self):
        lc = self.lanc()
        self.iniciar(lc)
        self.cli.fora = [self.linha()]
        self.assertIn("Já tem 2 rodando ao mesmo tempo (1 aberta fora do painel). O limite é 2.", self.recusa(lc))

    def test_so_do_painel_nao_fala_de_fora(self):
        lc = self.lanc(max_execucoes=1)
        self.iniciar(lc)
        self.assertEqual(self.recusa(lc), "Já tem 1 rodando ao mesmo tempo. O limite é 1. Espere uma acabar ou pare uma.")

    def test_acao_igual_continua_com_o_id(self):
        lc = self.lanc()
        i = self.iniciar(lc)
        self.cli.fora = [self.linha()]
        with self.assertRaises(lancador.ErroAcao) as e:
            self.iniciar(lc)
        self.assertEqual(e.exception.execucao_id, i)

    def test_uma_busca_so_por_disparo(self):
        lc = self.lanc()
        self.cli.fora = [self.linha()]
        self.iniciar(lc)
        self.assertEqual(len([c for c, _ in self.cli.chamadas if c[1:2] == ["agents"]]), 1)

    def test_de_fora_parada_nao_conta(self):
        casos = [dict(status="idle"), dict(status="waiting"), dict(status=None), dict(status="novidade"),
                 dict(status=None, state="done"), dict(status=None, state="stopped"), dict(status=None, state="blocked"),
                 dict(status="waiting", state="blocked"), dict(status="idle", state="working")]
        for c in casos:
            self.assertEqual(vagas.externas([self.linha(1, **c)], self.tmp, [], []), 0, c)
        lc = self.lanc(max_execucoes=1)
        self.cli.fora = [self.linha(n, **c) for n, c in enumerate(casos)]
        self.iniciar(lc)

    def test_segundo_plano_de_fora_sem_status_conta_pelo_state(self):
        for st in ("working", "running", "busy", "active"):
            linha = self.linha(1, id="99999999", kind="background", state=st, status=None)
            self.assertEqual(vagas.externas([linha], self.tmp, [], []), 1, st)

    def test_pasta_de_outro_projeto_nao_conta(self):
        raiz = os.path.join(self.tmp, "proj")
        for cwd in (self.tmp, raiz + "-x", os.path.join(raiz, "..", "proj-x"), "", ".", None, 3, "/a\x00b", "/\ud800"):
            self.assertEqual(vagas.externas([self.linha(cwd=cwd)], raiz, [], []), 0, repr(cwd))
        for cwd in (raiz, os.path.join(raiz, "a", "b")):
            self.assertEqual(vagas.externas([self.linha(cwd=cwd)], raiz, [], []), 1, cwd)

    @unittest.skipIf(os.name == "nt", "atalho pede privilégio no Windows")
    def test_atalho_para_a_raiz_conta(self):
        raiz, atalho = os.path.join(self.tmp, "proj"), os.path.join(self.tmp, "atalho")
        os.makedirs(raiz)
        os.symlink(raiz, atalho)
        self.assertEqual(vagas.externas([self.linha(cwd=atalho)], raiz, [], []), 1)
        self.assertEqual(vagas.externas([self.linha(cwd=raiz)], atalho, [], []), 1)


class TesteSemDobrar(Base):
    def test_sessao_do_painel_nao_dobra_pelo_id(self):
        lc = self.lanc()
        self.iniciar(lc)
        self.cli.agentes[0]["status"] = "busy"
        self.iniciar(lc, "dois")
        self.assertIn("Já tem 2 rodando ao mesmo tempo. ", self.recusa(lc))

    def test_interativa_que_retoma_uma_ativa_nao_dobra(self):
        lc = self.lanc()
        self.iniciar(lc)  # o registro ainda não aprendeu o sessionId: vale o da linha do CLI
        self.cli.fora = [self.linha(sessionId=self.cli.agentes[0]["sessionId"])]
        self.iniciar(lc, "dois")
        self.assertIn("Já tem 2 rodando ao mesmo tempo. ", self.recusa(lc))

    def test_mesma_sessao_de_fora_em_duas_linhas_conta_uma(self):
        linhas = [self.linha(), self.linha(id="99999999", state="working")]
        self.assertEqual(vagas.externas(linhas, self.tmp, [], []), 1)

    def test_interativa_que_retoma_uma_terminada_conta(self):
        lc = self.lanc(max_execucoes=1)
        self.terminada(lc)
        self.cli.fora = [self.linha(sessionId=self.cli.agentes[0]["sessionId"])]
        self.assertIn("1 aberta fora do painel", self.recusa(lc))

    def test_terminada_com_a_linha_ocupada_e_o_registro_que_decide(self):
        ex = {"id": "aaaaaaaa", "sessao_id": SID % 1}
        self.assertEqual(vagas.externas([self.linha(id="aaaaaaaa")], self.tmp, [ex], []), 0)

    def test_esperando_do_painel_ainda_conta(self):
        lc = self.lanc()
        self.iniciar(lc)
        self.cli.agentes[0].update(state="blocked", status="waiting")
        self.cli.fora = [self.linha()]
        self.assertIn("Já tem 2 rodando", self.recusa(lc))


class TesteFalha(Base):
    def test_lista_com_falha_conta_so_o_registro(self):
        for crua in ((1, "", "x"), (0, "{quebrado", ""), (0, "{}", ""), (124, "", "demorou demais")):
            shutil.rmtree(os.path.join(self.tmp, "dados"), ignore_errors=True)
            self.cli = CLIFora()
            self.cli.fora = [self.linha(1), self.linha(2)]
            self.cli.crua = crua
            lc = self.lanc()
            self.iniciar(lc, "um")
            self.iniciar(lc, "dois")  # as de fora não são vistas, então não bloqueiam
            self.assertIn("Já tem 2 rodando ao mesmo tempo. ", self.recusa(lc))  # registro cheio recusa

    def test_falha_depois_de_lista_boa_nao_usa_a_velha(self):
        lc = self.lanc(max_execucoes=1)
        self.cli.fora = [self.linha()]
        self.recusa(lc)
        self.cli.crua = (1, "", "x")
        self.iniciar(lc)

    def test_linhas_tortas_nao_derrubam(self):
        tortas = [None, 3, "x", [], {}, self.linha(cwd=None), self.linha(cwd=["a"]), self.linha(status=["busy"]),
                  self.linha(status=None, state={"a": 1}), self.linha(sessionId=["x"], id={"a": 1}, status="idle")]
        self.assertEqual(vagas.externas(tortas, self.tmp, [], []), 0)
        sem_sid = [self.linha(), self.linha(), self.linha(), self.linha()]
        for s in sem_sid:
            del s["sessionId"]
        self.assertEqual(vagas.externas(tortas + sem_sid[:2], self.tmp, [], []), 2)  # sem sessionId: uma por linha
        lc = self.lanc(max_execucoes=1)
        self.cli.fora = tortas
        self.cli.agentes = []
        self.iniciar(lc)

    def test_erro_ao_contar_vira_zero_de_fora(self):
        lc = self.lanc()
        original = vagas.externas
        self.addCleanup(setattr, vagas, "externas", original)

        def quebra(*_a):
            raise RuntimeError("x")
        vagas.externas = quebra
        self.iniciar(lc)
        self.iniciar(lc, "dois")
        self.assertIn("Já tem 2 rodando ao mesmo tempo. ", self.recusa(lc))


class TesteResponder(Base):
    def test_de_fora_enche_e_recusa_sem_mexer_na_sessao(self):
        lc = self.lanc(max_execucoes=1)
        i = self.terminada(lc)
        self.cli.fora = [self.linha()]
        with self.assertRaises(lancador.ErroAcao) as e:
            lc.responder(i, "oi")
        self.assertEqual((e.exception.codigo, e.exception.execucao_id), (409, None))
        self.assertIn("1 aberta fora do painel", e.exception.mensagem)
        self.assertEqual([c for c, _ in self.cli.chamadas if c[1:2] == ["stop"] or "--resume" in c], [])
        self.cli.fora = []
        self.assertEqual(lc.responder(i, "oi")["id"], i)

    def test_a_propria_nao_conta_contra_ela(self):
        lc = self.lanc(max_execucoes=1)
        i = self.terminada(lc)
        # a mesma sessão aberta à mão no terminal (linha sem id)
        self.cli.fora = [self.linha(sessionId=self.cli.agentes[0]["sessionId"])]
        self.assertEqual(lc.responder(i, "oi")["id"], i)

    def test_ativa_ja_ocupa_a_vaga_dela(self):
        lc = self.lanc(max_execucoes=1)
        i = self.iniciar(lc)
        self.cli.fora = [self.linha(1), self.linha(2)]
        lc.esquecer_agentes()
        self.assertEqual(lc.responder(i, "muda", interromper=True)["id"], i)


if __name__ == "__main__":
    unittest.main()
