"""Recebimento, parte 2: eco do fromMe (pelo id devolvido, por texto em até 5 s, corrida do eco antes do id; eco nunca
pausa; fromMe que não casa = dono no celular, pausa 15 min), busca na subida do que chegou com o serviço parado
(SAIR -> optout_em; > 30 min sem IA), /chat/findMessages da Evolution contra servidor falso e a rota do webhook
plugada no recebimento."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import http.client  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import banco, portao, recebimento, rotas  # noqa: E402
from servico import servico as servico_mod  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.test_conector_evolution import EvolutionFalsa  # noqa: E402
from testes.test_recebimento import INST, LEAD, Base, corpo, jid  # noqa: E402

UTC = datetime.timezone.utc


class TesteEco(Base):
    def enviar_ia(self, texto="Temos sim!", gatilho="G1"):
        return portao.enviar_ia(self.con, self.c, INST, LEAD, texto, 1, gatilho, 1)

    def saida(self):
        return self.con.execute("SELECT * FROM mensagens WHERE direcao = 'saida'").fetchall()

    def test_eco_pelo_id_devolvido_nao_pausa(self):
        r = self.enviar_ia()
        self.receber(corpo(r["id_externo"], "Temos sim!", from_me=True))
        self.receber(corpo(r["id_externo"], "Temos sim!", from_me=True, evento="send.message"))  # repetido
        linhas = self.saida()
        self.assertEqual([(m["envio_id"], m["id_externo"]) for m in linhas], [(r["envio_id"], r["id_externo"])])
        self.assertIsNone(self.conversa()["pausada_ate"])
        self.assertEqual(self.ia, [])

    def test_eco_por_texto_igual_em_ate_5s(self):
        r = self.enviar_ia()
        self.receber(corpo("OUTRO-ID", "Temos sim!", from_me=True))
        self.assertEqual(self.saida()[0]["envio_id"], r["envio_id"])
        self.assertIsNone(self.conversa()["pausada_ate"])

    def test_mesmo_texto_depois_de_5s_e_o_dono(self):
        self.enviar_ia()
        self.receber(corpo("DONO-1", "Temos sim!", from_me=True, ts=int(time.time()) + 8))
        self.assertIsNone(self.saida()[0]["envio_id"])
        self.assertIsNotNone(self.conversa()["pausada_ate"])

    def test_dois_envios_iguais_cada_eco_casa_um(self):
        a, b = self.enviar_ia("ok", "G1"), self.enviar_ia("ok", "G2")
        self.receber(corpo("X1", "ok", from_me=True))
        self.receber(corpo("X2", "ok", from_me=True))
        self.assertEqual(sorted(m["envio_id"] for m in self.saida()), sorted([a["envio_id"], b["envio_id"]]))
        self.assertIsNone(self.conversa()["pausada_ate"])

    def test_dono_no_celular_grava_e_pausa_15_min(self):
        self.receber(corpo("M1", "oi"))
        antes = datetime.datetime.now(UTC)
        self.receber(corpo("DONO-1", "Oi, aqui é o dono", from_me=True))
        ate = datetime.datetime.fromisoformat(self.conversa()["pausada_ate"])
        self.assertTrue(datetime.timedelta(minutes=14) < ate - antes <= datetime.timedelta(minutes=15, seconds=2))
        self.assertEqual(self.saida()[0]["texto"], "Oi, aqui é o dono")
        self.assertEqual(portao.pode_enviar(self.con, "ia", LEAD), (False, "pausa_humana"))
        self.assertEqual(len(self.ia), 1)   # só a mensagem do lead

    def test_corrida_eco_chega_antes_do_id(self):
        teste = self
        con2 = banco.abrir(self.pasta)
        self.addCleanup(con2.close)

        class EcoAntes(ConectorFalso):
            def enviar_texto(self, instancia, telefone, texto):
                teste.receber(corpo("falso-1", texto, from_me=True), con=con2)  # eco antes de devolver o id
                return super().enviar_texto(instancia, telefone, texto)

        self.c = EcoAntes()
        r = self.enviar_ia()
        self.assertEqual((r["estado"], r["id_externo"]), ("enviado", "falso-1"))
        self.receber(corpo("falso-1", "Temos sim!", from_me=True))   # o mesmo eco de novo, já com o id
        linhas = self.saida()
        self.assertEqual([(m["envio_id"], m["id_externo"]) for m in linhas], [(r["envio_id"], "falso-1")])
        self.assertIsNone(self.conversa()["pausada_ate"])

    def test_eco_da_confirmacao_de_sair_nao_pausa(self):
        self.receber(corpo("S1", "sair"))
        ident = self.c.entregues[0]["id_externo"]
        self.receber(corpo(ident, self.c.entregues[0]["conteudo"], from_me=True))
        self.assertIsNone(self.conversa()["pausada_ate"])


class TesteSubida(Base):
    def test_o_que_chegou_parado(self):
        agora = datetime.datetime.now(UTC)
        ts = int(agora.timestamp())
        self.c.perdidos = [corpo("P1", "SAIR", de="5511900000001", ts=ts - 3600),
                           corpo("P2", "ainda tem?", de="5511900000002", ts=ts - 40 * 60),
                           corpo("P3", "oi", de="5511900000003", ts=ts - 5 * 60),
                           corpo("P4", "muito antigo", de="5511900000004", ts=ts - 5 * 3600)]
        n = self.rec.recuperar(self.con, agora - datetime.timedelta(hours=2), agora)
        self.assertEqual(n, 3)   # P4 é de antes da última vida do serviço
        self.assertIsNotNone(self.um("SELECT optout_em FROM contatos WHERE telefone = ?", "5511900000001")[0])
        self.assertEqual(self.confirmacoes(), 1)
        self.assertEqual(self.conversa("5511900000002")["precisa_de_voce"], 1)
        self.assertEqual([m for _, m in self.ia],
                         [self.um("SELECT id FROM mensagens WHERE id_externo = 'P3'")[0]])
        self.assertIsNone(self.conversa("5511900000004"))
        self.rec.recuperar(self.con, agora - datetime.timedelta(hours=2), agora)   # de novo: dedupe
        self.assertEqual((self.contar("mensagens"), self.confirmacoes(), len(self.ia)), (3, 1, 1))

    def test_sem_ultima_vida_nao_busca(self):
        self.assertEqual(self.rec.recuperar(self.con, None), 0)
        self.assertEqual([n for n, _ in self.c.chamadas], [])

    def test_ultima_vida_batimento_ou_parado_em(self):
        self.assertIsNone(recebimento.ultima_vida(self.con))
        banco.gravar_config(self.con, "parado_em", "2026-11-10T12:00:00+00:00")
        self.assertEqual(recebimento.ultima_vida(self.con), datetime.datetime(2026, 11, 10, 12, tzinfo=UTC))
        self.con.execute("INSERT INTO batimento (id, pid, em) VALUES (1, 1, '2026-11-10T13:00:00+00:00')")
        self.assertEqual(recebimento.ultima_vida(self.con).hour, 13)   # queda: vale o batimento que ficou

    def test_subida_do_servico_grava_optout_do_sair_recebido_parado(self):
        app = rotas.App(self.pasta, 0, "http://127.0.0.1:18787", "t" * 43, "s" * 43)
        app.despachar = recebimento.Recebimento(lambda: app.conector)
        app.conector = self.c
        agora = datetime.datetime.now(UTC)
        self.c.perdidos = [corpo("P1", "Sair", ts=int(agora.timestamp()) - 600)]
        servico_mod.recuperar(app, agora - datetime.timedelta(minutes=20))
        self.assertIsNotNone(self.um("SELECT optout_em FROM contatos")[0])
        self.assertEqual(self.confirmacoes(), 1)

    def test_falha_na_busca_vira_evento_sem_derrubar(self):
        class Quebrado(ConectorFalso):
            def mensagens_desde(self, *a):
                raise evolution.NaoEnviado("fora do ar")
        app = rotas.App(self.pasta, 0, "http://127.0.0.1:18787", "t" * 43, "s" * 43)
        app.despachar = recebimento.Recebimento(lambda: app.conector)
        app.conector = Quebrado()
        servico_mod.recuperar(app, datetime.datetime.now(UTC))
        self.assertEqual(self.contar("eventos", "tipo = 'recuperacao_falhou'"), 1)


class TesteFindMessages(unittest.TestCase):
    def test_busca_paginada_e_traduz(self):
        falsa = EvolutionFalsa()
        self.addCleanup(falsa.fechar)
        registro = {"key": {"remoteJid": jid(LEAD), "fromMe": False, "id": "R1"}, "messageType": "conversation",
                    "message": {"conversation": "sair"}, "messageTimestamp": 1700000000}
        caminho = "/chat/findMessages/" + INST
        falsa.srv.respostas[("POST", caminho)] = (200, {"messages": {"total": 2, "pages": 2, "currentPage": 1,
                                                                     "records": [registro]}})
        con = evolution.Evolution(falsa.url, "k", "http://x", "s", tempo_limite=2)
        desde = datetime.datetime(2026, 11, 10, 12, 0, tzinfo=UTC)
        eventos = con.mensagens_desde(INST, desde, desde + datetime.timedelta(hours=1))
        self.assertEqual([(e["id_externo"], e["remetente"], e["texto"], e["fromMe"]) for e in eventos],
                         [("R1", LEAD, "sair", False)] * 2)
        pedidos = falsa.srv.pedidos
        self.assertEqual([p["corpo"]["page"] for p in pedidos], [1, 2])
        self.assertEqual(pedidos[0]["corpo"]["where"], {"messageTimestamp": {
            "gte": "2026-11-10T12:00:00Z", "lte": "2026-11-10T13:00:00Z"}})
        self.assertEqual(pedidos[0]["headers"]["apikey"], "k")


class TesteRota(Base):
    def test_webhook_http_grava_e_confirma_sair_depois_do_commit(self):
        app = rotas.App(self.pasta, 0, "http://127.0.0.1:18787", "t" * 43, "s" * 43)
        app.despachar = self.rec
        servidor = rotas.criar_servidor(app, 0)
        threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        for segredo, ident in (("s" * 43, "W1"), ("errado", "W2")):   # válido e (modo registra) inválido
            h = http.client.HTTPConnection("127.0.0.1", app.porta, timeout=5)
            h.request("POST", "/webhook/" + INST, body=json.dumps(corpo(ident, "Sair", de="55119000000%02d" % len(
                ident + segredo))).encode(), headers={"Content-Type": "application/json", rotas.CAB_SEGREDO: segredo,
                                                      "Host": "127.0.0.1:%d" % app.porta})
            r = h.getresponse()
            r.read()
            h.close()
            self.assertEqual(r.status, 200)
        self.assertEqual(self.contar("contatos", "optout_em IS NOT NULL"), 2)
        self.assertEqual((self.c.envios(), self.confirmacoes()), (2, 2))
        self.assertEqual(banco.ler_config(self.con, "webhook_validos"), "1")


if __name__ == "__main__":
    unittest.main()
