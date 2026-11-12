"""Transcrição e legenda passam pelas MESMAS triagens do texto do lead: SAIR falado ou na legenda = opt-out e
confirmação pelo portão, zero chamadas ao chat; frase com o sinal = "precisa de você" (sinal_de_saida). Imagem que não
cabe (mais de 8 MB, ou a do gatilho além do limite) nunca vai ao modelo como "[imagem]": falha, nada sai. Modo
automático em todos (o pior caso: a resposta sairia). Relógio fixo (portao._agora e o `agora` da rodada)."""
import sys

sys.dont_write_bytecode = True

import base64  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, midia, rascunhos, recebimento  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from testes.openai_falsa import imagens_do_pedido, resposta_texto, resposta_transcricao  # noqa: E402
from testes.test_entender import AGORA, OGG, PNG, Base, corpo  # noqa: E402

JPG = b"\xff\xd8\xff\xe0" + b"\x03" * 40


class Comum(Base):
    def setUp(self):
        super().setUp()
        rascunhos.definir_modo_padrao(self.con, "automatico")

    def com_legenda(self, ident, conteudo, legenda):
        self.c.midias[ident] = (conteudo, "x", None)
        c = corpo(ident, "imagem")
        c["data"]["message"]["imageMessage"]["caption"] = legenda
        for acao in recebimento.gravar(self.con, evolution.traduzir(c), agora=AGORA):
            if acao[0] == "midia":
                midia.baixar(lambda: banco.abrir(self.pasta), self.c, self.pasta, acao[1])
        return self.con.execute("SELECT id FROM mensagens WHERE id_externo = ?", (ident,)).fetchone()["id"]

    def optout(self):
        return self.con.execute("SELECT optout_em FROM contatos").fetchone()[0]

    def envios(self):
        return [tuple(l) for l in self.con.execute("SELECT origem, conteudo FROM envios ORDER BY id")]

    def saiu_so_a_confirmacao(self):
        self.assertEqual(self.optout(), "2026-03-10T13:00:00+00:00")
        self.assertEqual(self.falsa.chamadas_chat(), [])
        self.assertEqual(self.envios(), [("confirmacao_sair", recebimento.CONFIRMACAO_SAIR)])
        self.assertEqual(self.rascunhos(), [])


class TesteSaidaFalada(Comum):
    def falado(self, texto):
        mid, _ = self.chegar("a1", "audio", OGG)
        self.falsa.fila += [resposta_transcricao(texto), resposta_texto("Tudo bem! Posso ajudar?")]
        self.assertIsNone(self.rodar(mid))
        self.assertEqual(len(self.falsa.chamadas_transcricao()), 1)
        self.saiu_so_a_confirmacao()

    def test_audio_parar_vira_optout_sem_chamar_o_chat(self):
        self.falado("Parar.")

    def test_audio_sair_vira_optout_sem_chamar_o_chat(self):
        self.falado("Sair.")

    def test_audio_com_o_sinal_numa_frase_marca_precisa_e_a_ia_responde(self):
        mid, _ = self.chegar("a1", "audio", OGG)
        self.falsa.fila += [resposta_transcricao("nao quero mais isso"), resposta_texto("Entendi, sem problema.")]
        self.rodar(mid)
        self.assertIsNone(self.optout())
        self.assertEqual(self.precisa(), 1)
        self.assertIn("sinal_de_saida", self.motivos())
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)

    def test_legenda_sair_vira_optout_sem_chamar_nada(self):
        mid = self.com_legenda("i1", PNG, "Sair")
        self.falsa.fila.append(resposta_texto("Que foto bonita!"))
        self.assertIsNone(self.rodar(mid))
        self.assertEqual(self.falsa.chamadas_transcricao(), [])
        self.saiu_so_a_confirmacao()

    def test_legenda_com_o_sinal_marca_precisa(self):
        mid = self.com_legenda("i1", PNG, "pode parar de mandar isso")
        self.falsa.fila.append(resposta_texto("Combinado."))
        self.rodar(mid)
        self.assertIsNone(self.optout())
        self.assertIn("sinal_de_saida", self.motivos())


class TesteImagemQueNaoCabe(Comum):
    def test_png_de_9_mb_nao_chama_o_chat_e_nada_sai(self):
        grande = PNG[:8] + b"\x02" * (9 * 1024 * 1024)
        mid, _ = self.chegar("i1", "imagem", grande)
        self.assertEqual(self.con.execute("SELECT estado FROM midias").fetchone()[0], "pronta")
        self.falsa.fila.append(resposta_texto("Que legal! Como posso ajudar?"))
        self.assertIsNone(self.rodar(mid))
        self.assertEqual(self.falsa.chamadas_chat(), [])
        self.assertEqual(self.motivos(), ["imagem_grande"])
        self.assertEqual(self.precisa(), 1)
        self.nada_saiu()

    def test_texto_depois_de_imagem_grande_tambem_nao_responde_sobre_o_que_nao_viu(self):
        self.chegar("i1", "imagem", PNG[:8] + b"\x02" * (9 * 1024 * 1024))
        mid, _ = self.chegar("t1", texto="e aí, gostou?")
        self.falsa.fila.append(resposta_texto("Adorei!"))
        self.assertIsNone(self.rodar(mid))
        self.assertEqual(self.falsa.chamadas_chat(), [])
        self.assertEqual(self.motivos(), ["imagem_grande"])
        self.nada_saiu()

    def test_quinta_imagem_do_gatilho_entra_e_a_mais_velha_fica_de_fora(self):
        mids = [self.chegar("i%d" % n, "imagem", (JPG if n % 2 else PNG) + bytes([n]))[0] for n in range(5)]
        self.falsa.fila.append(resposta_texto("Recebi as fotos."))
        self.rodar(mids[-1])
        partes = imagens_do_pedido(self.falsa.chamadas_chat()[0]["corpo"])
        enviados = [base64.b64decode(p["image_url"]["url"].split(",", 1)[1]) for p in partes]
        self.assertEqual(len(enviados), 4)
        self.assertIn(PNG + bytes([4]), enviados)        # a do gatilho
        self.assertNotIn(PNG + bytes([0]), enviados)     # a mais velha é a que fica de fora
        self.assertIn("imagens_demais", self.motivos())


if __name__ == "__main__":
    unittest.main()
