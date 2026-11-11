"""Recebimento (C4): mesmo id 2 vezes = 1 linha; grupo e fromMe não acionam a IA; SAIR grava opt-out, manda 1
confirmação e a IA não responde; opt-out por variante do 9º dígito; áudio/imagem/documento gravam o tipo e marcam
"precisa de você"; mensagem com mais de 30 min não aciona a IA; @lid com remoteJidAlt -> contato certo (e mapa
aprendido), sem alternativa -> linha em eventos; opt-out só com a mensagem INTEIRA igual à palavra."""
import sys

sys.dont_write_bytecode = True

import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import banco, pasta, portao, recebimento  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402

INST = "loja"
LEAD = "5511900000001"
LEAD9 = "5511960000001"     # celular com variante sem o 9º dígito (551160000001)
LID = "123456789012345@lid"


def jid(numero):
    return numero + "@s.whatsapp.net"


def corpo(ident, texto="oi", de=LEAD, from_me=False, mensagem=None, ts=None, chave_extra=None, evento="messages.upsert"):
    chave = dict({"remoteJid": de if "@" in de else jid(de), "fromMe": from_me, "id": ident}, **(chave_extra or {}))
    return {"event": evento, "instance": INST, "data": {
        "key": chave, "message": mensagem if mensagem is not None else {"conversation": texto},
        "messageTimestamp": int(time.time()) if ts is None else ts}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "projeto"))
        self.pasta = pasta.pasta_de_dados(os.path.join(self.tmp, "projeto"), base=os.path.join(self.tmp, "dados"))
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        banco.gravar_config(self.con, "instancia", INST)
        self.c = ConectorFalso()
        self.rec = recebimento.Recebimento(lambda: self.c)
        self.ia = []
        recebimento.registrar_gancho(lambda conversa, mensagem: self.ia.append((conversa, mensagem)))
        self.addCleanup(recebimento.registrar_gancho, None)

    def receber(self, c, con=None):
        """Como a rota do webhook com segredo válido: despacha dentro da transação, commit, depois o 'depois'."""
        con = con or self.con
        con.execute("BEGIN IMMEDIATE")
        try:
            depois = self.rec(con, INST, c, True)
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise
        if depois:
            depois(con)

    def um(self, sql, *args):
        return self.con.execute(sql, args).fetchone()

    def contar(self, tabela, onde="1=1", *args):
        return self.um("SELECT COUNT(*) FROM %s WHERE %s" % (tabela, onde), *args)[0]

    def conversa(self, numero=LEAD):
        return self.um("SELECT cv.* FROM conversas cv JOIN contatos ct ON ct.id = cv.contato_id "
                       "WHERE ct.telefone = ?", numero)

    def confirmacoes(self):
        return self.contar("envios", "origem = 'confirmacao_sair' AND estado = 'enviado'")


class TesteBasico(Base):
    def test_mesmo_id_duas_vezes_uma_linha(self):
        self.receber(corpo("M1"))
        self.receber(corpo("M1"))
        self.receber(corpo("M1", evento="send.message"))
        self.assertEqual(self.contar("mensagens"), 1)
        self.assertEqual(len(self.ia), 1)
        m = self.um("SELECT * FROM mensagens")
        self.assertEqual((m["direcao"], m["tipo"], m["texto"]), ("entrada", "texto", "oi"))
        self.assertEqual(self.ia, [(self.conversa()["id"], m["id"])])

    def test_grupo_nao_grava_nem_aciona_ia(self):
        self.receber(corpo("G1", de="120363000000000001@g.us", chave_extra={"participant": jid(LEAD)}))
        self.assertEqual((self.contar("mensagens"), self.contar("contatos"), self.ia), (0, 0, []))

    def test_from_me_nao_aciona_ia(self):
        self.receber(corpo("F1", "respondo eu", from_me=True))
        self.assertEqual(self.ia, [])
        self.assertEqual(self.um("SELECT direcao FROM mensagens")[0], "saida")

    def test_gancho_padrao_nao_faz_nada(self):
        recebimento.registrar_gancho(None)
        self.receber(corpo("M1"))
        self.assertEqual(self.contar("mensagens"), 1)

    def test_falha_do_gancho_nao_vaza_dado_pessoal_no_log(self):
        def quebrar(*_):
            raise RuntimeError("texto %s" % LEAD)
        recebimento.registrar_gancho(quebrar)
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            self.receber(corpo("M1", "meu segredo"))
        self.assertIn("RuntimeError", err.getvalue())
        self.assertNotIn(LEAD, err.getvalue())
        self.assertNotIn("segredo", err.getvalue())
        self.assertEqual(self.contar("mensagens"), 1)   # gravou antes; a falha do gancho não desfaz

    def test_instancia_de_outro_nome_nao_grava(self):
        self.con.execute("BEGIN IMMEDIATE")
        self.rec(self.con, "outra", corpo("M1"), True)
        self.con.execute("COMMIT")
        self.assertEqual(self.contar("mensagens"), 0)
        self.assertEqual(self.contar("eventos", "tipo = 'webhook_outra_instancia'"), 1)


class TesteSair(Base):
    def test_sair_grava_optout_uma_confirmacao_e_ia_nao_responde(self):
        self.receber(corpo("S1", "SAIR"))
        contato = self.um("SELECT * FROM contatos")
        self.assertIsNotNone(contato["optout_em"])
        self.assertEqual((self.c.envios(), self.confirmacoes(), self.ia), (1, 1, []))
        self.assertEqual(self.c.entregues[0]["telefone"], LEAD)
        self.receber(corpo("S2", "sair"))      # de novo: nada de 2ª confirmação
        self.receber(corpo("S3", "oi?"))       # depois do opt-out, a IA não é chamada
        self.assertEqual((self.c.envios(), self.ia), (1, []))
        self.assertEqual(portao.pode_enviar(self.con, "ia", LEAD), (False, "optout"))

    def test_todas_as_palavras_com_acento_pontuacao_e_caixa(self):
        for i, texto in enumerate(("Sair!", "  PARAR. ", "stop", "Cancelar...", "descadastrar?", "pàrar")):
            numero = "55119000001%02d" % i
            with self.subTest(texto=texto):
                self.receber(corpo("S%d" % i, texto, de=numero))
                self.assertIsNotNone(self.um("SELECT optout_em FROM contatos WHERE telefone = ?", numero)[0])
        self.assertEqual((self.c.envios(), self.ia), (6, []))

    def test_frase_com_a_palavra_nao_e_optout_e_marca_precisa_de_voce(self):
        for i, texto in enumerate(("quero cancelar o pedido", "não quero pagar isso", "Não quero")):
            numero = "55119000002%02d" % i
            with self.subTest(texto=texto):
                self.receber(corpo("P%d" % i, texto, de=numero))
                self.assertIsNone(self.um("SELECT optout_em FROM contatos WHERE telefone = ?", numero)[0])
                self.assertEqual(self.conversa(numero)["precisa_de_voce"], 1)
        self.assertEqual(self.c.envios(), 0)

    def test_frase_comum_nao_marca_precisa_de_voce(self):
        self.receber(corpo("M1", "quanto custa?"))
        self.assertEqual(self.conversa()["precisa_de_voce"], 0)

    def test_optout_casa_por_variante_do_9o_digito(self):
        contato_id = banco.salvar_contato(self.con, LEAD9)
        self.receber(corpo("S1", "sair", de="551160000001"))     # chega sem o 9º dígito
        self.assertEqual(self.contar("contatos"), 1)
        self.assertIsNotNone(self.um("SELECT optout_em FROM contatos WHERE id = ?", contato_id)[0])
        self.assertTrue(banco.em_optout(self.con, "+55 11 96000-0001"))
        self.assertEqual(portao.pode_enviar(self.con, "campanha", LEAD9)[1], "optout")
        self.assertEqual(self.confirmacoes(), 1)

    def test_sem_conector_grava_optout_e_registra_evento(self):
        self.c = None
        self.receber(corpo("S1", "parar"))
        self.assertIsNotNone(self.um("SELECT optout_em FROM contatos")[0])
        self.assertEqual(self.contar("eventos", "tipo = 'confirmacao_sair_sem_conector'"), 1)

    def test_from_me_com_a_palavra_nao_e_optout(self):
        self.receber(corpo("F1", "sair", from_me=True))
        self.assertIsNone(self.um("SELECT optout_em FROM contatos")[0])
        self.assertEqual(self.c.envios(), 0)


class TesteTipos(Base):
    def test_audio_imagem_documento_gravam_tipo_e_marcam_precisa_de_voce(self):
        casos = (("audio", {"audioMessage": {"seconds": 3, "ptt": True}}),
                 ("imagem", {"imageMessage": {"caption": "foto do produto"}}),
                 ("documento", {"documentMessage": {"fileName": "a.pdf"}}))
        for i, (tipo, mensagem) in enumerate(casos):
            numero = "55119000003%02d" % i
            with self.subTest(tipo=tipo):
                self.receber(corpo("D%d" % i, de=numero, mensagem=mensagem))
                self.assertEqual(self.um("SELECT tipo FROM mensagens WHERE id_externo = ?", "D%d" % i)[0], tipo)
                self.assertEqual(self.conversa(numero)["precisa_de_voce"], 1)
        self.assertEqual(self.ia, [])

    def test_mais_de_30_min_nao_aciona_ia_e_marca_precisa_de_voce(self):
        agora = int(time.time())
        self.receber(corpo("V1", "oi", ts=agora - 31 * 60))
        self.assertEqual((self.ia, self.conversa()["precisa_de_voce"]), ([], 1))
        self.receber(corpo("V2", "oi de novo", de="5511900000002", ts=agora - 29 * 60))
        self.assertEqual(len(self.ia), 1)
        self.assertEqual(self.conversa("5511900000002")["precisa_de_voce"], 0)

    def test_sair_velho_tambem_grava_optout(self):
        self.receber(corpo("S1", "sair", ts=int(time.time()) - 3 * 3600))
        self.assertIsNotNone(self.um("SELECT optout_em FROM contatos")[0])


class TesteLid(Base):
    def test_lid_com_remote_jid_alt_vai_para_o_contato_certo_e_aprende_o_mapa(self):
        banco.salvar_contato(self.con, LEAD)
        self.receber(corpo("L1", de=LID, chave_extra={"remoteJidAlt": jid(LEAD)}))
        self.assertEqual(self.contar("contatos"), 1)
        self.assertEqual(self.um("SELECT ct.telefone FROM mensagens m JOIN conversas cv ON cv.id = m.conversa_id "
                                 "JOIN contatos ct ON ct.id = cv.contato_id")[0], LEAD)
        self.receber(corpo("L2", "sair", de=LID))   # sem alternativa: o mapa aprendido resolve
        self.assertIsNotNone(self.um("SELECT optout_em FROM contatos")[0])

    def test_lid_com_sender_pn(self):
        self.receber(corpo("L1", de=LID, chave_extra={"senderPn": jid(LEAD)}))
        self.assertIsNotNone(self.conversa())

    def test_lid_sem_alternativa_vira_linha_em_eventos(self):
        self.receber(corpo("L1", de=LID))
        self.assertEqual((self.contar("mensagens"), self.contar("contatos"), self.ia), (0, 0, []))
        dados = json.loads(self.um("SELECT dados FROM eventos WHERE tipo = 'mensagem_descartada'")[0])
        self.assertEqual(dados, {"motivo": "lid_sem_alternativa", "id_externo": "L1"})


class TesteNormalizar(unittest.TestCase):
    def test_normalizar(self):
        self.assertEqual(recebimento.normalizar_texto("  Não,  QUERO!! "), "nao quero")
        self.assertTrue(recebimento.e_saida("Descadastrar."))
        self.assertFalse(recebimento.e_saida("sair agora"))
        self.assertFalse(recebimento.e_saida("não quero"))
        self.assertFalse(recebimento.tem_sinal("parabens"))   # "parar" não casa dentro de outra palavra


if __name__ == "__main__":
    unittest.main()
