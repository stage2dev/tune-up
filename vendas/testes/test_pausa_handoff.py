"""C4i: pausa e handoff pelo caminho real (webhook -> recebimento -> atendente -> cérebro na OpenAI FALSA -> portão).
Dono no celular = pausa 15 min (estende; eco nunca pausa); pedir_humano / erro / rodadas = IA desligada com motivo até
'Devolver para a IA'; pausada ou desligada = o modelo nem é chamado e as mensagens chegam normalmente."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import conversas  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from testes.openai_falsa import resposta_ferramenta, resposta_texto  # noqa: E402
from testes.test_atendente import Base, corpo  # noqa: E402
from testes.test_aba_conversas import Conversas  # noqa: E402

UTC = datetime.timezone.utc


def corpo_dono(ident, texto):
    c = corpo(ident, texto)
    c["data"]["key"]["fromMe"] = True
    return c


class TestePausa(Base):
    def dono_fala(self, ident, texto="Oi, é o dono"):
        from servico import recebimento
        recebimento.executar_depois(self.con, self.c, recebimento.gravar(self.con, evolution.traduzir(
            corpo_dono(ident, texto))))

    def pausada_ate(self):
        return datetime.datetime.fromisoformat(self.conversa()["pausada_ate"])

    def test_dono_no_celular_pausa_e_o_modelo_nao_e_chamado(self):
        self.chegar("m0", "oi")
        self.falsa.fila = [resposta_texto("Olá!")]
        self.assertTrue(self.esperar(lambda: len(self.c.entregues) == 1))
        n = len(self.falsa.chamadas_chat())
        self.dono_fala("D1")
        self.assertGreater(self.pausada_ate(), datetime.datetime.now(UTC) + datetime.timedelta(minutes=14))
        self.chegar("m1", "e o preço?")
        time.sleep(self.ESPERA * 3)
        self.assertEqual(len(self.falsa.chamadas_chat()), n)   # nenhuma chamada nova
        self.assertEqual(len(self.c.entregues), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM mensagens WHERE direcao = 'entrada'").fetchone()[0], 2)

    def test_eco_do_nosso_envio_nao_pausa(self):
        self.chegar("m0", "oi")
        self.falsa.fila = [resposta_texto("Olá!")]
        self.assertTrue(self.esperar(lambda: len(self.c.entregues) == 1))
        ident = self.con.execute("SELECT id_externo FROM envios").fetchone()["id_externo"]
        self.dono_fala(ident, "Olá!")
        self.assertIsNone(self.conversa()["pausada_ate"])

    def test_nova_fala_do_dono_estende_e_a_mais_velha_nao_encurta(self):
        self.chegar("m0", "oi")
        self.con.execute("UPDATE conversas SET pausada_ate = ?",
                         ((datetime.datetime.now(UTC) + datetime.timedelta(minutes=5)).isoformat(),))
        self.dono_fala("D1")
        primeira = self.pausada_ate()
        self.assertGreater(primeira, datetime.datetime.now(UTC) + datetime.timedelta(minutes=14))
        self.con.execute("UPDATE conversas SET pausada_ate = ?", ((primeira + datetime.timedelta(minutes=30)).isoformat(),))
        self.dono_fala("D2")   # pausa já vale por mais tempo: não encurta
        self.assertEqual(self.pausada_ate(), primeira + datetime.timedelta(minutes=30))

    def test_pausa_acabou_a_proxima_mensagem_do_lead_e_respondida_nao_as_velhas(self):
        self.chegar("m0", "oi")
        self.dono_fala("D1")
        self.chegar("m1", "mensagem durante a pausa")
        time.sleep(self.ESPERA * 3)
        self.assertEqual(self.falsa.chamadas_chat(), [])
        self.con.execute("UPDATE conversas SET pausada_ate = ?",
                         ((datetime.datetime.now(UTC) - datetime.timedelta(seconds=1)).isoformat(),))
        time.sleep(self.ESPERA * 3)
        self.assertEqual(self.falsa.chamadas_chat(), [])   # expirar sozinho não responde o passado
        self.falsa.fila = [resposta_texto("Agora sim!")]
        self.chegar("m2", "e então?")
        self.assertTrue(self.esperar(lambda: len(self.c.entregues) == 1))
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)
        envio = self.con.execute("SELECT chave_dedupe FROM envios").fetchone()
        self.assertIn(":m2:", envio["chave_dedupe"])


class TesteDesligada(Base):
    def test_pedir_humano_desliga_guarda_o_motivo_e_nao_envia(self):
        self.falsa.fila = [resposta_ferramenta("pedir_humano", {"motivo": "pediu desconto"}),
                           resposta_texto("não deveria sair")]
        self.chegar("m0", "quero falar com alguém")
        self.assertTrue(self.esperar(lambda: self.conversa()["modo"] == "humano"))
        c = self.conversa()
        self.assertEqual((c["modo"], c["precisa_de_voce"], c["motivo_humano"]), ("humano", 1, "pedir_humano"))
        time.sleep(self.ESPERA * 2)
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)   # nem uma segunda chamada
        self.assertEqual(self.textos_enviados(), [])

    def test_desligada_nao_chama_o_modelo_e_mensagens_chegam(self):
        self.falsa.fila = [resposta_ferramenta("pedir_humano", {"motivo": "x"})]
        self.chegar("m0", "oi")
        self.assertTrue(self.esperar(lambda: self.conversa()["modo"] == "humano"))
        n = len(self.falsa.chamadas_chat())
        self.chegar("m1", "alguém aí?")
        time.sleep(self.ESPERA * 3)
        self.assertEqual(len(self.falsa.chamadas_chat()), n)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM mensagens WHERE direcao = 'entrada'").fetchone()[0], 2)

    def test_rodadas_desliga_a_ia(self):
        self.falsa.fila = [resposta_ferramenta("qualificar", {"nivel": "morno"}, ident="c%d" % i) for i in range(10)]
        self.chegar("m0", "oi")
        self.assertTrue(self.esperar(lambda: self.conversa()["modo"] == "humano"))
        self.assertEqual(self.conversa()["motivo_humano"], "rodadas")

    def test_anti_loop_tres_respostas_parecidas_desliga_a_ia(self):
        repetida = "Posso te ajudar com os planos. O que você procura?"
        for n in range(2):
            self.falsa.fila = [resposta_texto(repetida)]
            self.chegar("m%d" % n, "oi %d" % n)
            self.assertTrue(self.esperar(lambda: len(self.c.entregues) == n + 1))
        self.falsa.fila = [resposta_texto(repetida)]
        self.chegar("m2", "oi 2")
        self.assertTrue(self.esperar(lambda: self.conversa()["modo"] == "humano"))
        c = self.conversa()
        self.assertEqual((c["modo"], c["precisa_de_voce"], c["motivo_humano"]), ("humano", 1, "anti_loop"))
        self.assertEqual(len(self.c.entregues), 2)   # a 3ª parecida não saiu
        n = len(self.falsa.chamadas_chat())
        self.falsa.fila = [resposta_texto("não deveria sair")]
        self.chegar("m3", "alguém aí?")
        time.sleep(self.ESPERA * 3)
        self.assertEqual(len(self.falsa.chamadas_chat()), n)   # desligada: o modelo nem é chamado
        self.assertEqual(len(self.c.entregues), 2)

    def test_devolver_para_a_ia_limpa_tudo_e_a_ia_volta_a_responder(self):
        self.falsa.fila = [resposta_ferramenta("pedir_humano", {"motivo": "x"})]
        self.chegar("m0", "oi")
        self.assertTrue(self.esperar(lambda: self.conversa()["modo"] == "humano"))
        self.assertTrue(conversas.definir_modo(self.con, self.conversa()["id"], "ia"))
        c = self.conversa()
        self.assertEqual((c["modo"], c["precisa_de_voce"], c["motivo_humano"], c["pausada_ate"]), ("ia", 0, None, None))
        self.falsa.fila = [resposta_texto("De volta!")]
        self.chegar("m1", "oi de novo")
        self.assertTrue(self.esperar(lambda: len(self.c.entregues) == 1))


class TesteAba(Conversas):
    def test_motivo_aparece_nos_blocos_e_devolver_para_a_ia_limpa(self):
        from servico import cerebro
        cerebro.marcar_precisa_de_voce(self.con, self.maria, "pedir_humano", True)
        blocos = self.aba()
        item = [i for i in self.tipos(blocos, "lista")[0]["itens"] if i["titulo"].startswith("Maria")][0]
        self.assertEqual(item["selo"]["texto"], "precisa de você")
        self.assertIn("pediu para você assumir", item["detalhe"])
        self.agir("abrir_conversa", conversa_id=str(self.maria))
        bloco = self.tipos(self.aba(), "conversa")[0]
        self.assertIn("IA desligada: A IA pediu para você assumir", bloco["titulo"])
        self.assertEqual(bloco["botoes"][0]["rotulo"], "Devolver para a IA")
        self.assertTrue(self.agir("devolver_ia", conversa_id=self.maria)["ok"])
        bloco = self.tipos(self.aba(), "conversa")[0]
        self.assertNotIn("desligada", bloco["titulo"])
        self.assertNotIn("precisa de você", bloco["titulo"])
        self.assertEqual(bloco["botoes"][0]["rotulo"], "Assumir a conversa")

    def test_motivo_anti_loop_aparece_em_pt_nos_blocos(self):
        from servico import cerebro
        cerebro.marcar_precisa_de_voce(self.con, self.maria, "anti_loop", True)
        self.agir("abrir_conversa", conversa_id=str(self.maria))
        titulo = self.tipos(self.aba(), "conversa")[0]["titulo"]
        self.assertIn("IA desligada: A IA repetiu", titulo)
        self.assertNotIn("anti_loop", titulo)


if __name__ == "__main__":
    unittest.main()
