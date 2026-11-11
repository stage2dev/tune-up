"""Endurecimento da revisão da Parte E: usage sem inteiros cobra o pior caso, resposta cortada (finish_reason length)
não sai, erro interno guarda só o tipo, reescrita que quebra barra, campanha pausada entre a escolha e a reserva não
sai, frio/novo é por instância, CSV malformado vira recusa limpa (rota e comando), os.replace do segredo tenta de
novo no Windows. Nada de rede: OpenAI falsa e conector falso em 127.0.0.1."""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import datetime  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import banco, campanha, cerebro, portao, precos, saida, travas  # noqa: E402
from testes import test_campanha  # noqa: E402
from testes.openai_falsa import resposta_texto  # noqa: E402
from testes.test_cerebro import Base as BaseCerebro  # noqa: E402
from testes.test_leads import Importa  # noqa: E402
from testes import test_leads_aba, test_saida  # noqa: E402

GRANDE = "nome,telefone\nAna,+55 11 90000-0001\n\"%s\",+55 11 90000-0002\n" % ("x" * 200000)


class TesteCerebro(BaseCerebro):
    def test_usage_vazia_ou_sem_inteiros_cobra_o_pior_caso(self):
        par = [0.15, 0.60]
        for usage in ({}, {"prompt_tokens": 10}, {"prompt_tokens": "10", "completion_tokens": 5},
                      {"prompt_tokens": 1.5, "completion_tokens": 5}, {"prompt_tokens": True, "completion_tokens": 5}):
            self.assertIsNone(precos.custo_usd(par, usage), usage)
        self.assertAlmostEqual(precos.custo_usd(par, {"prompt_tokens": 1000000, "completion_tokens": 0}), 0.15)
        self.falsa.fila = [(200, {"choices": [{"message": {"content": "Oi"}}], "usage": {}})]
        r = self.responder()
        self.assertEqual((r["texto"], r["motivo"]), (None, "resposta_invalida"))
        self.assertGreater(precos.gasto_hoje(self.con), cerebro.SAIDA_MAX * 0.60 / 1e6)   # a reserva ficou

    def test_resposta_cortada_por_length_nao_sai_e_marca(self):
        st, corpo = resposta_texto("Custa R$ 10 e o melhor da oferta é")
        corpo["choices"][0]["finish_reason"] = "length"
        self.falsa.fila = [(st, corpo)]
        r = self.responder()
        self.assertEqual((r["texto"], r["motivo"], r["precisa_de_voce"]), (None, "resposta_cortada", True))
        self.assertEqual(self.precisa(), 1)

    def test_erro_interno_guarda_so_o_tipo_no_evento_e_no_stderr(self):
        segredo = "telefone +55 11 90000-0009 e chave"

        def explode(*_a, **_k):
            raise KeyError(segredo)
        erro = io.StringIO()
        with mock.patch.object(cerebro.openai_cliente, "pedir", explode), contextlib.redirect_stderr(erro):
            r = self.responder()
        self.assertEqual(r["motivo"], "erro_interno")
        dados = json.loads(self.con.execute("SELECT dados FROM eventos WHERE tipo = 'ia_precisa_de_voce' "
                                            "ORDER BY id DESC").fetchone()[0])
        self.assertEqual(dados["erro"], "KeyError")
        self.assertIn("KeyError", erro.getvalue())
        self.assertNotIn("90000", json.dumps(dados) + erro.getvalue())

    def test_reescrita_que_quebra_barra_e_marca(self):
        def quebra(_t, _p):
            raise RuntimeError("inesperado")
        erro = io.StringIO()
        with contextlib.redirect_stderr(erro):
            r = saida.entregar(self.con, object(), "loja", "+55 11 90000-0001", self.conversa, "gat1",
                               'enviar_link({"nome": "x"})', reescrever=quebra)
        self.assertEqual((r["estado"], r["motivo"]), ("barrado", "reescrita_falhou"))
        self.assertEqual(self.precisa(), 1)
        self.assertIn("RuntimeError", erro.getvalue())


class TesteCampanha(test_campanha.Base):
    def test_pausada_entre_a_escolha_e_a_reserva_nao_sai(self):
        self.campanha(1)
        linha = campanha.proximo(self.con, portao._iso(self.agora))
        self.assertTrue(campanha.pausar(self.con, linha["campanha_id"]))   # o dono pausa no meio
        r = portao.enviar_campanha(self.con, self.c, test_campanha.INST, linha["telefone"], "Oi", linha["campanha_id"],
                                   linha["passo"], agora=self.agora)
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "campanha_parada"))
        self.assertEqual(self.c.entregues, [])
        self.assertEqual(self.ag.passo(), 5.0)   # o agendador também não manda nada
        self.assertEqual(self.c.entregues, [])

    def test_contato_fora_de_pendente_ou_concluida_nao_sai(self):
        cid = self.campanha(1)
        linha = campanha.proximo(self.con, portao._iso(self.agora))
        self.con.execute("UPDATE campanha_contatos SET estado = 'respondeu' WHERE campanha_id = ?", (cid,))
        r = portao.enviar_campanha(self.con, self.c, test_campanha.INST, linha["telefone"], "Oi", cid, linha["passo"],
                                   agora=self.agora)
        self.assertEqual(r["motivo"], "campanha_parada")
        self.assertEqual(self.c.entregues, [])

    def test_reenvio_do_agendador_com_campanha_pausada_nao_sai(self):
        cid = self.campanha(1)
        linha = campanha.proximo(self.con, portao._iso(self.agora))
        envio = banco.registrar_envio(self.con, "campanha:%d:%d:%s" % (cid, linha["contato_id"], linha["passo"]),
                                      "campanha", estado="falhou", contato_id=linha["contato_id"],
                                      telefone=linha["telefone"], tipo="texto", conteudo="Oi",
                                      instancia=test_campanha.INST)
        self.assertTrue(campanha.pausar(self.con, cid))
        r = portao.reenviar(self.con, self.c, test_campanha.INST, envio, agora=self.agora, so_se_campanha_ativa=True)
        self.assertEqual(r["motivo"], "campanha_parada")
        self.assertEqual(self.c.entregues, [])

    def test_agendador_reenvia_falha_so_com_a_campanha_ativa(self):
        self.campanha(1)
        self.c.modo_envio = "recusar"
        self.rodar(1)
        self.c.modo_envio = "ok"
        with mock.patch.object(portao, "reenviar", wraps=portao.reenviar) as espiao:
            self.rodar(20, passo_s=600)
        self.assertTrue(espiao.called)
        self.assertTrue(all(c.kwargs.get("so_se_campanha_ativa") for c in espiao.call_args_list))
        self.assertEqual(len(self.c.entregues), 1)

    def test_dono_reenvia_o_incerto_de_campanha_concluida(self):
        cid = self.campanha(1)
        self.c.modo_envio = "timeout"
        self.rodar(3)
        self.assertEqual(self.estados(cid), ["incerto"])
        self.assertEqual(self.con.execute("SELECT estado FROM campanhas WHERE id = ?", (cid,)).fetchone()[0],
                         "concluida")
        envio = self.con.execute("SELECT id FROM envios WHERE estado = 'incerto'").fetchone()[0]
        self.c.modo_envio = "ok"
        r = portao.reenviar(self.con, self.c, test_campanha.INST, envio, agora=self.agora)   # o "Reenviar" do dono
        self.assertEqual((r["estado"], r["motivo"]), ("enviado", None))
        self.assertEqual(len(self.c.entregues), 1)   # o timeout não entregou; o reenvio do dono entregou

    def _ja_recebeu_de_outra_instancia(self, contato_id):
        banco.registrar_envio(self.con, "manual:x%d" % contato_id, "manual", estado="enviado", contato_id=contato_id,
                              telefone="+5511900000000", tipo="texto", conteudo="Oi", instancia="outra",
                              quando=portao._iso(self.agora - datetime.timedelta(days=3)))

    def test_trava_de_descartavel_olha_a_instancia_atual(self):
        banco.gravar_config(self.con, "numero_descartavel", "0")
        contato = banco.salvar_contato(self.con, test_campanha.numero(900), "Ana", "feira", "consentimento")
        self._ja_recebeu_de_outra_instancia(contato)
        self.assertTrue(campanha.fria(self.con, contato))   # outro número não esquenta para este
        self.assertFalse(campanha.fria(self.con, contato, "outra"))
        cid = campanha.criar(self.con, "teste", test_campanha.MODELO, [contato])
        self.assertEqual(campanha.ativar_com_regras(self.con, cid)[0], 403)

    def test_aquecimento_conta_como_novo_quem_so_recebeu_de_outra_instancia(self):
        hoje = portao._iso(self.agora - datetime.timedelta(hours=2))
        for i in range(portao.CURVA_NOVOS[0]):   # o teto de novos do dia 1 já foi usado nesta instância
            c = banco.salvar_contato(self.con, test_campanha.numero(800 + i))
            banco.registrar_envio(self.con, "manual:n%d" % i, "manual", estado="enviado", contato_id=c,
                                  telefone="+5511900000000", tipo="texto", conteudo="Oi",
                                  instancia=test_campanha.INST, quando=hoje)
        contato = banco.salvar_contato(self.con, test_campanha.numero(900), "Ana", "feira", "consentimento")
        self._ja_recebeu_de_outra_instancia(contato)
        self.assertEqual(portao.pode_enviar(self.con, "campanha", test_campanha.numero(900), agora=self.agora),
                         (False, "teto_contatos_novos_dia"))
        self.assertEqual(portao.pode_enviar(self.con, "campanha", test_campanha.numero(900), agora=self.agora,
                                            instancia="outra"), (True, None))


class TesteReescritaCortada(test_saida.Base):
    def test_reescrita_com_length_barra_e_nao_chama_o_conector(self):
        st, corpo = resposta_texto("Custa R$ 10 e o melhor da oferta")
        corpo["choices"][0]["finish_reason"] = "length"
        self.falsa.fila = [(st, corpo)]
        r = self.entregar('enviar_link({"nome": "x"})')
        self.assertEqual((r["estado"], r["motivo"]), ("barrado", "ferramenta_como_texto"))
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)   # a reescrita foi pedida e voltou cortada
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.precisa_de_voce(), 1)


class TesteCsvMalformado(Importa):
    def test_campo_grande_demais_vira_400_em_pt_br_e_nada_entra(self):
        codigo, r = self.csv(GRANDE)
        self.assertEqual(codigo, 400)
        self.assertIn("CSV está malformado", r["erro"])
        self.assertEqual(self.contatos(), [])

    def test_caractere_nulo_nunca_derruba_a_conexao(self):
        codigo, r = self.csv("nome,telefone\nA\x00na,+55 11 90000-0001\n")
        self.assertIn(codigo, (200, 400))   # 3.9 recusa o NUL; 3.11+ aceita: nunca conexão caída
        if codigo == 400:
            self.assertIn("CSV está malformado", r["erro"])


class TesteCsvMalformadoComando(test_leads_aba.Aba):
    escrever, rodar = test_leads_aba.TesteComando.escrever, test_leads_aba.TesteComando.rodar

    def setUp(self):
        super().setUp()
        travas.gravar_segredo(os.path.join(self.pasta, "token_envio"), self.token)
        self.arquivo = os.path.join(self.tmp, "lista.csv")

    def test_comando_recusa_limpo(self):
        self.escrever(GRANDE)
        codigo, saida_, erro = self.rodar(self.arquivo, "--origem", "feira", "--base-legal", "consentimento")
        self.assertEqual(codigo, 1)
        self.assertIn("Erro: O CSV está malformado", erro)
        self.assertNotIn("90000", saida_ + erro)


class TesteSubstituirNoWindows(unittest.TestCase):
    def test_tenta_3_vezes_no_windows_e_nenhuma_fora(self):
        chamadas = []

        def falha_duas(origem, destino):
            chamadas.append(1)
            if len(chamadas) < 3:
                raise PermissionError("em uso")
        with mock.patch.object(travas.os, "replace", falha_duas), mock.patch.object(travas.time, "sleep"), \
                mock.patch.object(travas.os, "name", "nt"):
            travas.substituir("a", "b")
        self.assertEqual(len(chamadas), 3)
        chamadas.clear()

        def sempre(origem, destino):
            chamadas.append(1)
            raise PermissionError("em uso")
        with mock.patch.object(travas.os, "replace", sempre), mock.patch.object(travas.time, "sleep"):
            with mock.patch.object(travas.os, "name", "nt"):
                self.assertRaises(PermissionError, travas.substituir, "a", "b")
            self.assertEqual(len(chamadas), 3)
            chamadas.clear()
            with mock.patch.object(travas.os, "name", "posix"):
                self.assertRaises(PermissionError, travas.substituir, "a", "b")
            self.assertEqual(len(chamadas), 1)


if __name__ == "__main__":
    unittest.main()
