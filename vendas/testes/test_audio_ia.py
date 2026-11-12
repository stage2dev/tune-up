"""Ferramenta responder_em_audio (F3) pelo caminho real: webhook traduzido -> recebimento.gravar -> atendente ->
cérebro na OpenAI FALSA -> audio_ia -> voz.py na ElevenLabs FALSA -> portão -> conector falso. O ffmpeg é trocado
por um conversor falso (a conversão real tem teste em test_voz.py). A ferramenta só existe com voz ligada E (áudio do
lead antes do gatilho OU pedido de áudio); teto por contato = texto; ElevenLabs 500 = texto uma vez; rascunho não gera
nada antes da aprovação; opt-out entre gerar e enviar = negado no portão; nenhum link no texto falado."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import atendente, audio_ia, banco, cerebro, chave, pasta, portao, rascunhos, recebimento, voz, \
    voz_cliente  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.elevenlabs_falsa import ElevenLabsFalsa  # noqa: E402
from testes.openai_falsa import OpenAIFalsa, escrever_oferta, resposta_ferramenta, resposta_texto  # noqa: E402

INST = "loja"
LEAD = "5511900000001"
LEAD2 = "5511900000002"
LINK = "https://loja.exemplo/curso"
RESPOSTA = "Oi! O curso custa R$ 100. Veja aqui: %s" % LINK


def corpo(ident, texto=None, de=LEAD):
    mensagem = {"conversation": texto} if texto is not None else {"audioMessage": {"seconds": 3}}
    return {"event": "messages.upsert", "instance": INST, "data": {
        "key": {"remoteJid": de + "@s.whatsapp.net", "fromMe": False, "id": ident},
        "message": mensagem, "messageTimestamp": int(time.time())}}


def converter_falso(ffmpeg, entrada, saida, *a, **k):
    with open(saida, "wb") as f:
        f.write(b"OggS-falso")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(projeto)
        escrever_oferta(projeto)
        with open(cerebro.caminho_links(projeto), "w", encoding="utf-8") as f:
            json.dump({"curso": LINK}, f)
        self.pasta = pasta.pasta_de_dados(projeto, base=os.path.join(self.tmp, "dados"))
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        chave.gravar(self.pasta, "sk-test-" + "0" * 24)
        chave.gravar(self.pasta, "sk_" + "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6WXYZ", voz.ARQUIVO_CHAVE)
        for k, v in (("ia_modelo", "gpt-4o-mini"), ("instancia", INST), ("ia_modo_padrao", "automatico"),
                     ("voz_id", "VozCatalogo0001")):
            banco.gravar_config(self.con, k, v)
        for alvo, valor in (("achar_ffmpeg", {"return_value": os.path.join(self.tmp, "ffmpeg-falso")}),
                            ("converter", {"side_effect": converter_falso})):
            p = mock.patch.object(voz_cliente, alvo, **valor)
            p.start()
            self.addCleanup(p.stop)
        self.openai = OpenAIFalsa()
        self.addCleanup(self.openai.fechar)
        self.eleven = ElevenLabsFalsa()
        self.addCleanup(self.eleven.fechar)
        self.c = ConectorFalso()
        self.app = types.SimpleNamespace(pasta_dados=self.pasta, elevenlabs_url=self.eleven.url, conector=self.c)
        self.ia = atendente.Atendente(lambda: banco.abrir(self.pasta),
                                      cerebro.Cerebro(self.pasta, projeto, self.openai.url, tempo=5),
                                      lambda: self.c, espera=0.1, app=self.app)

    def chegar(self, ident, texto=None, de=LEAD):
        """Grava como o webhook (sem o gancho: a rodada roda aqui, síncrona). Devolve o id da mensagem."""
        recebimento.gravar(self.con, evolution.traduzir(corpo(ident, texto, de)))
        return self.con.execute("SELECT id FROM mensagens WHERE id_externo = ?", (ident,)).fetchone()["id"]

    def conversa_id(self, numero=LEAD):
        return self.con.execute("SELECT c.id FROM conversas c JOIN contatos k ON k.id = c.contato_id WHERE "
                                "k.telefone LIKE ?", ("%" + numero[-8:],)).fetchone()["id"]

    def rodar(self, ident, numero=LEAD):
        mid = self.con.execute("SELECT id FROM mensagens WHERE id_externo = ?", (ident,)).fetchone()["id"]
        return self.ia.responder(self.conversa_id(numero), mid)

    def ferramentas_oferecidas(self, i=0):
        return [t["function"]["name"] for t in self.openai.chamadas_chat()[i]["corpo"]["tools"]]

    def responder_em_audio(self, texto=RESPOSTA):
        self.openai.fila += [resposta_ferramenta("responder_em_audio", {}), resposta_texto(texto)]

    def envios(self):
        return [dict(l) for l in self.con.execute("SELECT origem, estado, tipo, motivo, chave_dedupe, conteudo FROM "
                                                  "envios ORDER BY id")]

    def chamadas(self):
        return [n for n, _ in self.c.chamadas if n.startswith("enviar_")]

    def eventos(self, tipo):
        return [json.loads(l["dados"]) for l in self.con.execute("SELECT dados FROM eventos WHERE tipo = ?", (tipo,))]


class TesteOferta(Base):
    def test_voz_desligada_ferramenta_ausente_mesmo_depois_de_audio(self):
        chave.apagar(self.pasta, voz.ARQUIVO_CHAVE)
        self.chegar("a1")
        self.chegar("t1", "oi, quanto custa?")
        self.openai.fila.append(resposta_texto("O curso custa R$ 100."))
        self.rodar("t1")
        self.assertNotIn("responder_em_audio", self.ferramentas_oferecidas())
        self.assertEqual(self.chamadas(), ["enviar_texto"])

    def test_texto_sem_pedido_ferramenta_ausente(self):
        self.chegar("t1", "oi, tudo bem?")
        self.chegar("t2", "quanto custa o curso?")
        self.openai.fila.append(resposta_texto("O curso custa R$ 100."))
        self.rodar("t2")
        self.assertNotIn("responder_em_audio", self.ferramentas_oferecidas())
        self.assertEqual(self.eleven.pedidos, [])

    def test_depois_de_audio_do_lead_ferramenta_presente(self):
        self.chegar("a1")
        self.chegar("t1", "e aí?")
        self.openai.fila.append(resposta_texto("O curso custa R$ 100."))
        self.rodar("t1")
        self.assertIn("responder_em_audio", self.ferramentas_oferecidas())
        self.assertEqual(self.eleven.pedidos, [], "oferecida e não usada: nada é gerado")

    def test_pedido_explicito_ferramenta_presente(self):
        self.chegar("t1", "Pode mandar áudio? Tô dirigindo")
        self.openai.fila.append(resposta_texto("Claro."))
        self.rodar("t1")
        self.assertIn("responder_em_audio", self.ferramentas_oferecidas())

    def test_padroes_de_pedido(self):
        for sim in ("manda áudio", "pode mandar audio?", "prefiro áudio", "responde por áudio", "me manda um audio"):
            self.assertTrue(audio_ia.pediu_audio(sim), sim)
        for nao in ("não manda áudio", "nao consigo ouvir audio agora", "quanto custa?", "te mandei um audio", ""):
            self.assertFalse(audio_ia.pediu_audio(nao), nao)

    def test_chamada_forcada_sem_oferta_nao_liga_o_audio(self):
        self.chegar("t1", "quanto custa?")
        self.responder_em_audio("O curso custa R$ 100.")
        self.rodar("t1")
        self.assertEqual(self.chamadas(), ["enviar_texto"])
        self.assertEqual(self.eleven.pedidos, [])


class TesteEnvio(Base):
    def test_audio_sai_pelo_portao_como_audio_ia_e_link_vai_em_texto(self):
        self.chegar("a1")
        self.chegar("t1", "e o preço?")
        self.responder_em_audio()
        r = self.rodar("t1")
        self.assertEqual(r["estado"], "enviado", r)
        falado = self.eleven.pedidos[0]["corpo"]["text"]
        self.assertEqual(falado, "Oi! O curso custa R$ 100. Veja aqui:")
        self.assertNotIn("http", falado)
        self.assertNotIn("loja.exemplo", falado)
        self.assertEqual(self.chamadas(), ["enviar_audio", "enviar_texto"])
        cid = self.conversa_id()
        e = self.envios()
        self.assertEqual((e[0]["origem"], e[0]["estado"], e[0]["tipo"], e[0]["chave_dedupe"]),
                         ("audio_ia", "enviado", "audio", "audio_ia:%d:t1:1:audio" % cid))
        self.assertEqual((e[1]["origem"], e[1]["conteudo"]), ("ia", LINK))
        self.assertEqual(len(e), 2)
        self.responder_em_audio()   # rodada repetida para a mesma mensagem do lead: nada é gerado de novo
        self.assertEqual(self.rodar("t1")["estado"], "duplicado")
        self.assertEqual(len(self.eleven.pedidos), 1)

    def test_teto_por_contato_vira_texto(self):
        banco.gravar_config(self.con, "teto_audio_contato_dia", "1")
        self.chegar("t1", "manda áudio por favor")
        self.responder_em_audio("O curso custa R$ 100.")
        self.assertEqual(self.rodar("t1")["estado"], "enviado")
        self.chegar("t2", "e tem parcelamento?")
        self.responder_em_audio("Tem sim, em 3 vezes.")
        r = self.rodar("t2")
        self.assertEqual((r["estado"], r["audio_motivo"]), ("enviado", "teto_audio_contato_dia"), r)
        self.assertEqual(len(self.eleven.pedidos), 1, "o teto é conferido antes de gerar")
        self.assertEqual(self.chamadas(), ["enviar_audio", "enviar_texto"])
        self.assertEqual(self.c.chamadas[-1][1][2], "Tem sim, em 3 vezes.")
        self.assertEqual(self.eventos("ia_audio_virou_texto")[-1]["motivo"], "teto_audio_contato_dia")
        # o teto é por contato: outro lead ainda pode receber áudio hoje
        self.chegar("u1", "prefiro áudio", de=LEAD2)
        self.assertEqual(portao.pode_enviar(self.con, "audio_ia", LEAD2), (True, None))

    def test_elevenlabs_500_vira_texto_uma_vez(self):
        self.eleven.padrao = (500, {"detail": {"status": "erro"}})
        self.chegar("a1")
        self.chegar("t1", "e o preço?")
        self.responder_em_audio("O curso custa R$ 100.")
        r = self.rodar("t1")
        self.assertEqual(r["estado"], "enviado", r)
        self.assertEqual(self.chamadas(), ["enviar_texto"])
        self.assertEqual([x["origem"] for x in self.envios()], ["ia"])
        self.assertEqual(len(self.eventos("ia_audio_virou_texto")), 1)
        self.responder_em_audio("O curso custa R$ 100.")
        self.assertEqual(self.rodar("t1")["estado"], "duplicado")   # a mesma mensagem do lead não gera outra
        self.assertEqual(self.chamadas(), ["enviar_texto"])
        self.assertEqual(voz.usados_hoje(self.con), 0, "erro HTTP da ElevenLabs devolve a reserva")

    def test_optout_entre_gerar_e_enviar_negado_no_portao(self):
        self.chegar("a1")
        self.chegar("t1", "e o preço?")
        self.responder_em_audio("O curso custa R$ 100.")
        original = voz_cliente.sintetizar

        def sintetizar(*a, **k):
            audio = original(*a, **k)
            banco.marcar_optout(self.con, LEAD, banco.agora())   # o lead mandou SAIR enquanto o áudio era gerado
            return audio
        with mock.patch.object(voz_cliente, "sintetizar", side_effect=sintetizar):
            r = self.rodar("t1")
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "optout"), r)
        self.assertEqual(self.chamadas(), [])
        self.assertEqual([(x["origem"], x["estado"], x["motivo"]) for x in self.envios()],
                         [("audio_ia", "negado", "optout")])

    def test_voz_clonada_sem_consentimento_desliga_a_ferramenta(self):
        banco.gravar_config(self.con, "voz_clonada", "1")
        self.chegar("t1", "manda áudio")
        self.openai.fila.append(resposta_texto("Oi."))
        self.rodar("t1")
        self.assertNotIn("responder_em_audio", self.ferramentas_oferecidas())


class TesteRascunho(Base):
    def setUp(self):
        super().setUp()
        banco.gravar_config(self.con, "ia_modo_padrao", "rascunho")

    def test_rascunho_nao_gera_nada_antes_da_aprovacao(self):
        self.chegar("a1")
        self.chegar("t1", "e o preço?")
        self.responder_em_audio()
        r = self.rodar("t1")
        self.assertEqual(r["estado"], "rascunho", r)
        self.assertEqual(self.eleven.pedidos, [])
        self.assertEqual(self.chamadas(), [])
        p = rascunhos.pendente(self.con, self.conversa_id())
        self.assertTrue(p["como_audio"])
        self.assertEqual(p["texto"], "Oi! O curso custa R$ 100. Veja aqui:\n" + LINK)
        codigo, res = rascunhos.aprovar(self.app, self.con, p["id"])
        self.assertEqual((codigo, res["estado"]), (200, "enviado"), res)
        self.assertEqual(self.eleven.pedidos[0]["corpo"]["text"], "Oi! O curso custa R$ 100. Veja aqui:")
        self.assertEqual(self.chamadas(), ["enviar_audio", "enviar_texto"])
        self.assertEqual([(x["origem"], x["chave_dedupe"]) for x in self.envios()],
                         [("audio_ia", "audio_ia:rascunho:%d" % p["id"]),
                          ("rascunho_aprovado", "rascunho_aprovado:%d" % p["id"])])
        self.assertEqual(self.envios()[1]["conteudo"], LINK)
        self.assertEqual(self.con.execute("SELECT estado FROM rascunhos WHERE id = ?", (p["id"],)).fetchone()[0],
                         "aprovado")
        codigo, res = rascunhos.aprovar(self.app, self.con, p["id"])   # clique repetido
        self.assertEqual(res["estado"], "duplicado")
        self.assertEqual(len(self.eleven.pedidos), 1)
        self.assertEqual(len(self.chamadas()), 2)

    def test_aprovacao_com_falha_da_voz_manda_o_texto(self):
        self.eleven.padrao = (500, {"detail": {"status": "erro"}})
        self.chegar("t1", "manda áudio")
        self.responder_em_audio("O curso custa R$ 100.")
        self.rodar("t1")
        p = rascunhos.pendente(self.con, self.conversa_id())
        codigo, res = rascunhos.aprovar(self.app, self.con, p["id"])
        self.assertEqual(res["estado"], "enviado", res)
        self.assertEqual(self.chamadas(), ["enviar_texto"])
        self.assertEqual([(x["origem"], x["conteudo"]) for x in self.envios()],
                         [("rascunho_aprovado", "O curso custa R$ 100.")])
        self.assertEqual(self.eventos("ia_audio_virou_texto")[0]["rascunho_id"], p["id"])
        rascunhos.aprovar(self.app, self.con, p["id"])   # de novo: o texto já saiu, nenhum áudio é gerado
        self.assertEqual(len(self.eleven.pedidos), 1)
        self.assertEqual(self.chamadas(), ["enviar_texto"])

    def test_aprovacao_com_optout_nao_envia(self):
        self.chegar("t1", "manda áudio")
        self.responder_em_audio("O curso custa R$ 100.")
        self.rodar("t1")
        p = rascunhos.pendente(self.con, self.conversa_id())
        banco.marcar_optout(self.con, LEAD, banco.agora())
        codigo, res = rascunhos.aprovar(self.app, self.con, p["id"])
        self.assertEqual((res["estado"], res["motivo"]), ("negado", "optout"))
        self.assertEqual(self.chamadas(), [])
        self.assertEqual(self.eleven.pedidos, [])


class TesteSeparar(unittest.TestCase):
    def test_link_sai_da_fala_e_fala_fica_no_limite(self):
        fala, links, _ = audio_ia.separar("Veja www.loja.exemplo/a e %s. Obrigado!" % LINK)
        self.assertNotIn("loja.exemplo", fala)
        self.assertEqual(links, ["www.loja.exemplo/a", LINK])
        longa = " ".join(["Frase número %d." % i for i in range(10)])
        fala, _, cortou = audio_ia.separar(longa)
        self.assertTrue(cortou)
        self.assertEqual(fala.count("."), 4)
        fala, _, cortou = audio_ia.separar("palavra " * 200)
        self.assertLessEqual(len(fala), voz.LIMITE_TEXTO)


if __name__ == "__main__":
    unittest.main()
