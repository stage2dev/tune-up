"""Rascunho durante o envio (servico/rascunhos.py): editar depois de uma tentativa que falhou não manda o texto velho
como se fosse o novo; aprovar trava o rascunho ('aprovando') antes do portão, então descartar ou um rascunho novo da
IA no meio do envio não passam por cima; uma falha devolve o rascunho a pendente; o banco do esquema 8 migra."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, rascunhos  # noqa: E402
from testes.test_rascunhos import BaseRascunho  # noqa: E402


class TesteCorrida(BaseRascunho):
    def no_meio_do_envio(self, acao):
        """Troca o enviar_texto do conector falso: roda acao(con2) numa conexão própria enquanto 'está na rede'."""
        original, vistos = self.c.enviar_texto, []

        def lento(instancia, numero, texto):
            con2 = banco.abrir(self.pasta)
            try:
                vistos.append(acao(con2))
            finally:
                con2.close()
            return original(instancia, numero, texto)
        self.c.enviar_texto = lento
        return vistos

    def test_editar_depois_de_falhou_nao_manda_o_texto_velho(self):
        d = self.rascunho(resposta="Custa R$ 999 por mes.")
        self.c.modo_envio = "recusar"
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"])[1]["estado"], "falhou")
        self.assertEqual(self.estado(d["id"]), "pendente")
        self.c.modo_envio = "ok"
        codigo, r = rascunhos.aprovar(self.app, self.con, d["id"], "Custa R$ 99 por mes.")
        self.assertEqual(codigo, 409)
        self.assertIn("descarte", r["erro"])
        self.assertEqual(self.c.entregues, [])   # nada saiu com o texto velho no lugar do editado
        self.assertEqual(self.estado(d["id"]), "pendente")
        self.assertEqual(self.pendente()["texto"], "Custa R$ 999 por mes.")   # o texto guardado não mente
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"])[1]["estado"], "enviado")   # sem editar: sai
        self.assertEqual([e["conteudo"] for e in self.c.entregues], ["Custa R$ 999 por mes."])
        self.assertEqual(self.estado(d["id"]), "aprovado")

    def test_editar_igual_ao_texto_que_falhou_reenvia(self):
        d = self.rascunho(resposta="Texto certo.")
        self.c.modo_envio = "recusar"
        rascunhos.aprovar(self.app, self.con, d["id"])
        self.c.modo_envio = "ok"
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"], "Texto certo.")[1]["estado"], "enviado")
        self.assertEqual([e["conteudo"] for e in self.c.entregues], ["Texto certo."])

    def test_descartar_durante_o_envio_e_recusado(self):
        d = self.rascunho()
        vistos = self.no_meio_do_envio(lambda con2: rascunhos.descartar(con2, d["id"]))
        codigo, r = rascunhos.aprovar(self.app, self.con, d["id"])
        self.assertEqual((codigo, r["estado"]), (200, "enviado"))
        self.assertEqual(vistos[0][0], 409)   # a tela não diz "nada foi enviado"
        self.assertIn("sendo enviado", vistos[0][1]["erro"])
        self.assertEqual(self.c.envios(), 1)
        self.assertEqual(self.estado(d["id"]), "aprovado")

    def test_rascunho_novo_durante_o_envio_nao_vira_segunda_resposta(self):
        d = self.rascunho("m1", "Resposta 1")
        cid = self.conversa()["id"]

        def nova_mensagem(con2):
            mid = banco.registrar_mensagem(con2, cid, "entrada", "e o prazo?")
            return rascunhos.guardar(con2, cid, mid, "Resposta 2")
        vistos = self.no_meio_do_envio(nova_mensagem)
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"])[1]["estado"], "enviado")
        self.assertEqual((vistos[0]["estado"], vistos[0]["motivo"]), ("barrado", "rascunho_em_aprovacao"))
        self.assertEqual(self.estado(d["id"]), "aprovado")
        self.assertIsNone(self.pendente())   # nenhum segundo rascunho às cegas
        self.assertEqual(self.conversa()["precisa_de_voce"], 1)   # o dono vê a mensagem nova
        self.assertEqual([e["conteudo"] for e in self.c.entregues], ["Resposta 1"])

    def test_aprovar_durante_o_envio_e_recusado(self):
        d = self.rascunho()
        vistos = self.no_meio_do_envio(lambda con2: rascunhos.aprovar(self.app, con2, d["id"], "Outro texto."))
        rascunhos.aprovar(self.app, self.con, d["id"])
        self.assertEqual(vistos[0][0], 409)
        self.assertEqual([e["conteudo"] for e in self.c.entregues], ["Oi! Posso ajudar com o plano."])

    def test_erro_no_meio_devolve_o_rascunho_a_pendente(self):
        d = self.rascunho()
        with mock.patch.object(rascunhos.portao, "enviar_rascunho_aprovado", side_effect=RuntimeError("teste")):
            with self.assertRaises(RuntimeError):
                rascunhos.aprovar(self.app, self.con, d["id"])
        self.assertEqual(self.estado(d["id"]), "pendente")   # não fica preso em 'aprovando'
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"])[1]["estado"], "enviado")


class TesteMigracao9(unittest.TestCase):
    def test_banco_do_esquema_8_migra_e_guarda_os_rascunhos(self):
        con = banco.sqlite3.connect(":memory:", isolation_level=None)
        con.row_factory = banco.sqlite3.Row
        for comandos in banco.MIGRACOES[:8]:
            for comando in comandos:
                con.execute(comando)
        con.execute("PRAGMA user_version = 8")
        con.execute("INSERT INTO contatos (telefone, criado_em) VALUES ('5511900000001', 'x')")
        con.execute("INSERT INTO conversas (contato_id, criado_em, modo_ia) VALUES (1, 'x', 'automatico')")
        con.execute("INSERT INTO mensagens (conversa_id, direcao, texto, criado_em) VALUES (1, 'entrada', 'oi', 'x')")
        con.execute("INSERT INTO mensagens (conversa_id, direcao, texto, criado_em) VALUES (1, 'entrada', 'e', 'x')")
        con.execute("INSERT INTO rascunhos (conversa_id, mensagem_id, texto, estado, criado_em, decidido_em) "
                    "VALUES (1, 1, 'velho', 'aprovado', 'x', 'y')")
        con.execute("INSERT INTO rascunhos (conversa_id, mensagem_id, texto, criado_em) VALUES (1, 2, 'novo', 'x')")
        self.assertEqual(banco.migrar(con), banco.VERSAO)
        self.assertEqual(banco.migrar(con), banco.VERSAO)   # de novo: nada muda
        linhas = [tuple(r) for r in con.execute("SELECT id, mensagem_id, texto, estado, decidido_em FROM rascunhos "
                                                "ORDER BY id")]
        self.assertEqual(linhas, [(1, 1, "velho", "aprovado", "y"), (2, 2, "novo", "pendente", None)])
        con.execute("UPDATE rascunhos SET estado = 'aprovando' WHERE id = 2")   # o estado novo cabe no CHECK
        con.execute("INSERT INTO mensagens (conversa_id, direcao, texto, criado_em) VALUES (1, 'entrada', 'f', 'x')")
        with self.assertRaises(banco.sqlite3.IntegrityError):   # nada de pendente ao lado de um aprovando
            con.execute("INSERT INTO rascunhos (conversa_id, mensagem_id, texto, criado_em) VALUES (1, 3, 'b', 'x')")
        self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()
