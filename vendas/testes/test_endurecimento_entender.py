"""Endurecimento da IA que entende mídia (revisão de M3): transcrição que falhou não é paga de novo a cada mensagem e
o texto seguinte é respondido; só o erro real de "modelo sem visão" vira modelo_sem_visao e a imagem recusada não vai
de novo; SAIR falado vale mesmo com outra mídia do lote falhando e com a conversa pausada; serviço parando não vira
midia_indisponivel; o preço que falta na transcrição é o do modelo de transcrição. Caminho real: webhook traduzido ->
recebimento -> download pelo conector falso -> atendente -> OpenAI FALSA. Relógio fixo."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, entender, midia, recebimento  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from testes.openai_falsa import OpenAIFalsa, erro, imagens_do_pedido, resposta_texto, resposta_transcricao  # noqa: E402
from testes.test_entender import AGORA, OGG, PNG, corpo  # noqa: E402
from testes.test_entender_saida import Comum  # noqa: E402


def abas_motivos():
    import importlib.util
    caminho = os.path.join(os.path.dirname(AQUI), "painel", "modulos", "vendas", "abas", "motivos.py")
    spec = importlib.util.spec_from_file_location("vendas_motivos_teste", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.MOTIVOS


class TesteTranscricaoQueFalhou(Comum):
    def test_tempo_esgotado_nao_paga_de_novo_e_o_texto_seguinte_e_respondido(self):
        self.cerebro.tempo_transcricao = 0.3
        audio, _ = self.chegar("a1", "audio", OGG)
        self.falsa.fila.append(OpenAIFalsa.DORMIR)
        self.assertIsNone(self.rodar(audio))
        self.assertEqual(self.motivos(), ["transcricao_falhou"])
        self.assertEqual(self.con.execute("SELECT falha_ia FROM midias").fetchone()[0], "transcricao_falhou")
        texto, _ = self.chegar("t1", texto="e o preço?")
        self.falsa.fila.append(resposta_texto("Custa R$ 100."))
        self.rodar(texto)
        self.assertEqual(len(self.falsa.chamadas_transcricao()), 1)   # nada pago duas vezes
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)
        self.assertIn(("ia", "Custa R$ 100."), self.envios())
        self.assertEqual(self.motivos(), ["transcricao_falhou", "midia_nao_entendida"])
        self.assertEqual(self.precisa(), 1)   # a conversa continua "precisa de você" pelo áudio
        # o dono pede de novo: a falha some e a próxima rodada transcreve
        mid = self.con.execute("SELECT id FROM midias").fetchone()[0]
        self.assertIsNotNone(midia.entender_de_novo(self.con, mid))
        self.assertIsNone(midia.entender_de_novo(self.con, mid))   # clique repetido
        t2, _ = self.chegar("t2", texto="?")
        self.falsa.fila += [resposta_transcricao("quero comprar"), resposta_texto("Ótimo!")]
        self.rodar(t2)
        self.assertEqual(len(self.falsa.chamadas_transcricao()), 2)

    def test_tentar_de_novo_depois_da_resposta_do_dono_nao_responde(self):
        self.cerebro.tempo_transcricao = 0.3
        audio, _ = self.chegar("a1", "audio", OGG)
        self.falsa.fila.append(OpenAIFalsa.DORMIR)
        self.assertIsNone(self.rodar(audio))
        cid = self.con.execute("SELECT conversa_id FROM mensagens WHERE id = ?", (audio,)).fetchone()[0]
        banco.registrar_mensagem(self.con, cid, "saida", "Não consegui ouvir, pode escrever?", "dono1", "texto")
        mid = self.con.execute("SELECT id FROM midias").fetchone()[0]
        alvo = midia.entender_de_novo(self.con, mid)
        self.assertEqual(tuple(alvo), (cid, None))   # a IA não ganha a vez: o dono já respondeu
        self.assertIsNone(self.con.execute("SELECT falha_ia FROM midias").fetchone()[0])   # a falha foi limpa
        self.falsa.fila += [resposta_transcricao("quanto custa"), resposta_texto("O plano custa R$ 100.")]
        if alvo[1] is not None:   # o que a rota faz
            self.ia.responder(alvo[0], alvo[1], agora=AGORA)
        self.assertEqual(self.falsa.chamadas_chat(), [])
        self.assertEqual(self.envios(), [])


class TesteImagemRecusada(Comum):
    def test_400_que_nao_e_sem_visao_tem_motivo_proprio_e_a_imagem_nao_vai_de_novo(self):
        img, _ = self.chegar("i1", "imagem", PNG)
        self.falsa.fila.append(erro(400, "invalid_image_format", "You uploaded an unsupported image."))
        self.assertIsNone(self.rodar(img))
        self.assertEqual(self.motivos(), ["imagem_recusada"])
        self.assertEqual(self.con.execute("SELECT falha_ia FROM midias").fetchone()[0], "imagem_recusada")
        texto, _ = self.chegar("t1", texto="recebeu?")
        self.falsa.fila.append(resposta_texto("Recebi sim."))
        self.rodar(texto)
        self.assertEqual(len(self.falsa.chamadas_chat()), 2)
        self.assertEqual(imagens_do_pedido(self.falsa.chamadas_chat()[1]["corpo"]), [])   # não reenviada
        self.assertIn(("ia", "Recebi sim."), self.envios())

    def test_so_o_erro_real_de_sem_visao_e_modelo_sem_visao(self):
        img, _ = self.chegar("i1", "imagem", PNG)
        self.falsa.fila.append(erro(400, None, "Invalid content type. image_url is only supported by certain models."))
        self.rodar(img)
        self.assertEqual(self.motivos(), ["modelo_sem_visao"])
        self.assertEqual(self.con.execute("SELECT falha_ia FROM midias").fetchone()[0], "modelo_sem_visao")


class TesteSairNoLote(Comum):
    def test_sair_falado_vale_mesmo_com_midia_anterior_que_falhou(self):
        self.chegar("a0", "audio", None)   # o download desta falha
        audio, _ = self.chegar("a1", "audio", OGG)
        self.falsa.fila.append(resposta_transcricao("SAIR"))
        self.assertIsNone(self.rodar(audio))
        self.saiu_so_a_confirmacao()

    def pausar(self):
        ate = (AGORA + datetime.timedelta(minutes=15)).isoformat()
        self.con.execute("UPDATE conversas SET pausada_ate = ?", (ate,))

    def test_pausada_com_a_chave_ligada_sair_falado_vale(self):
        audio, depois = self.chegar("a1", "audio", OGG)
        self.assertIn("gancho", [a[0] for a in depois])
        self.pausar()
        self.falsa.fila.append(resposta_transcricao("Parar"))
        self.assertIsNone(self.rodar(audio))
        self.saiu_so_a_confirmacao()

    def test_pausada_com_audio_fica_precisa_de_voce_sem_chamar_o_chat(self):
        audio, _ = self.chegar("a1", "audio", OGG)
        self.pausar()
        self.falsa.fila.append(resposta_transcricao("quanto custa?"))
        self.assertIsNone(self.rodar(audio))
        self.assertEqual(self.falsa.chamadas_chat(), [])
        self.assertEqual(self.precisa(), 1)
        self.assertEqual(self.motivos(), ["pausa_humana"])
        self.assertIsNone(self.optout())
        self.assertEqual(self.envios(), [])

    def test_modo_humano_com_audio_nao_transcreve_e_fica_precisa_de_voce(self):
        audio, _ = self.chegar("a1", "audio", OGG)
        self.con.execute("UPDATE conversas SET modo = 'humano'")
        self.falsa.fila.append(resposta_transcricao("Parar"))
        self.assertIsNone(self.rodar(audio))
        self.assertEqual(self.falsa.chamadas_transcricao(), [])   # a voz do contato não vai à OpenAI
        self.assertEqual(self.falsa.pedidos, [])
        self.assertEqual(self.precisa(), 1)
        self.assertEqual(self.motivos(), ["pausa_humana"])
        self.assertIsNone(self.optout())
        self.assertEqual(self.envios(), [])


class TesteParadoEPreco(Comum):
    def test_servico_parando_na_espera_nao_marca_midia_indisponivel(self):
        recebimento.gravar(self.con, evolution.traduzir(corpo("a1", "audio")), agora=AGORA)   # fica pendente
        mid = self.con.execute("SELECT id FROM mensagens WHERE id_externo = 'a1'").fetchone()[0]
        self.assertEqual(self.con.execute("SELECT estado FROM midias").fetchone()[0], "pendente")
        self.ia._parar.set()
        self.assertIsNone(self.rodar(mid))
        self.assertEqual(self.motivos(), [])
        self.assertEqual(self.precisa(), 0)
        self.assertEqual(self.falsa.pedidos, [])

    def test_texto_do_preco_da_transcricao(self):
        motivos = abas_motivos()
        self.assertIn("modelo de transcrição", motivos["preco_transcricao"])
        for codigo in ("imagem_recusada", "midia_nao_entendida", "pausa_humana"):
            self.assertIn(codigo, motivos)

    def test_entender_desligado_nao_transcreve(self):
        banco.gravar_config(self.con, entender.CONFIG["audio"], "0")
        audio, depois = self.chegar("a1", "audio", OGG)
        self.assertNotIn("gancho", [a[0] for a in depois])   # limite documentado: nada é transcrito
        self.assertEqual(self.falsa.pedidos, [])


if __name__ == "__main__":
    unittest.main()
