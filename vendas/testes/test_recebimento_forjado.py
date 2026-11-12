"""Webhook com segredo errado (modo "registra e conta"): grava e conta, marca "precisa de você" e pode gravar optout_em,
mas não tem efeito para fora nem muda estado de roteamento: sem confirmação de SAIR, sem gancho da IA, sem pausa da IA
por fromMe e sem escrever no mapa de @lid."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from testes.test_recebimento import INST, LEAD, LID, Base, corpo, jid  # noqa: E402

OUTRO = "5511900000009"


class TesteForjado(Base):
    def forjar(self, c):
        """Como a rota com segredo errado: o despachante roda fora de transação e o 'depois' roda em seguida."""
        depois = self.rec(self.con, INST, c, False)
        if depois:
            depois(self.con)

    def test_sair_forjado_nao_manda_confirmacao(self):
        for i in range(5):
            self.forjar(corpo("F%d" % i, "sair", de="55119000000%02d" % (10 + i)))
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.contar("envios"), 0)
        self.assertEqual(self.contar("contatos", "optout_em IS NOT NULL"), 5)   # opt-out é conservador: vale
        self.assertEqual(self.contar("conversas", "precisa_de_voce = 1"), 5)

    def test_texto_forjado_nao_chama_a_ia_e_marca_precisa_de_voce(self):
        self.forjar(corpo("F1", "quero comprar"))
        self.assertEqual(self.ia, [])
        self.assertEqual(self.contar("mensagens"), 1)
        self.assertEqual(self.conversa()["precisa_de_voce"], 1)

    def test_from_me_forjado_nao_pausa_a_ia(self):
        self.forjar(corpo("F1", "sou o dono", from_me=True))
        self.assertIsNone(self.conversa()["pausada_ate"])
        self.assertEqual(self.contar("mensagens", "direcao = 'saida' AND envio_id IS NULL"), 1)

    def test_lid_forjado_nao_troca_o_mapa(self):
        self.receber(corpo("L1", de=LID, chave_extra={"remoteJidAlt": jid(LEAD)}))   # válido: aprende
        self.forjar(corpo("F1", de=LID, chave_extra={"remoteJidAlt": jid(OUTRO)}))
        self.assertEqual(self.um("SELECT telefone FROM lids WHERE lid = ?", LID)[0], LEAD)
        self.receber(corpo("L2", "oi de novo", de=LID))   # válido sem alternativa: segue no contato certo
        linha = self.um("SELECT ct.telefone FROM mensagens m JOIN conversas cv ON cv.id = m.conversa_id "
                        "JOIN contatos ct ON ct.id = cv.contato_id WHERE m.id_externo = 'L2'")
        self.assertEqual(linha[0], LEAD)

    def test_lid_forjado_novo_nao_entra_no_mapa(self):
        self.forjar(corpo("F1", de=LID, chave_extra={"remoteJidAlt": jid(OUTRO)}))
        self.assertEqual(self.contar("lids"), 0)

    def test_valido_continua_com_efeitos(self):
        self.receber(corpo("V1", "sair"))
        self.assertEqual(self.confirmacoes(), 1)


if __name__ == "__main__":
    unittest.main()
