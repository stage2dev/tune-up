"""A IA vê a imagem do lead (parte image_url, data URL, detail low; no máximo 4 por rodada), modelo sem visão =
modelo_sem_visao sem enviar nada, documento nunca vai à IA (documento_recebido), chave 'IA entende imagens' desligada
= comportamento antigo, o pior caso conta tokens fixos por imagem (não os bytes) e a aba IA grava as chaves."""
import sys

sys.dont_write_bytecode = True

import base64  # noqa: E402
import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, entender, ia, precos  # noqa: E402
from testes.openai_falsa import erro, imagens_do_pedido, resposta_texto  # noqa: E402
from testes.test_entender import CHAVE, OGG, PDF, PNG, Base  # noqa: E402

JPG = b"\xff\xd8\xff\xe0" + b"\x03" * 40


class TesteImagem(Base):
    def test_imagem_vai_como_image_url_com_detail_low(self):
        mid, depois = self.chegar("i1", "imagem", PNG)
        self.assertIn("gancho", [a[0] for a in depois])
        self.falsa.fila.append(resposta_texto("Que foto bonita! Quer saber do curso?"))
        self.rodar(mid)
        self.assertEqual(self.falsa.chamadas_transcricao(), [])
        corpo = self.falsa.chamadas_chat()[0]["corpo"]
        (parte,) = imagens_do_pedido(corpo)
        self.assertEqual(parte["image_url"]["detail"], "low")
        prefixo = "data:image/png;base64,"
        self.assertTrue(parte["image_url"]["url"].startswith(prefixo))
        self.assertEqual(base64.b64decode(parte["image_url"]["url"][len(prefixo):]), PNG)
        self.assertNotIn("reasoning_effort", corpo)
        self.assertEqual(self.rascunhos(), ["Que foto bonita! Quer saber do curso?"])
        self.nada_saiu()

    def test_no_maximo_4_imagens_e_o_resto_avisado(self):
        mids = [self.chegar("i%d" % n, "imagem", JPG if n % 2 else PNG)[0] for n in range(5)]
        self.falsa.fila.append(resposta_texto("Recebi as fotos."))
        self.rodar(mids[-1])
        self.assertEqual(len(imagens_do_pedido(self.falsa.chamadas_chat()[0]["corpo"])), 4)
        self.assertIn("imagens_demais", self.motivos())

    def test_modelo_sem_visao_nada_sai_e_motivo_gravado(self):
        mid, _ = self.chegar("i1", "imagem", PNG)
        self.falsa.fila.append(erro(400, "invalid_request_error", "image_url is only supported by certain models"))
        self.assertIsNone(self.rodar(mid))
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)   # sem nova tentativa escondida sem a imagem
        self.assertEqual(self.motivos(), ["modelo_sem_visao"])
        self.assertEqual(self.precisa(), 1)
        self.assertEqual(self.rascunhos(), [])
        self.nada_saiu()

    def test_imagem_desligada_volta_ao_comportamento_antigo(self):
        banco.gravar_config(self.con, entender.CONFIG["imagem"], "0")
        _, depois = self.chegar("i1", "imagem", PNG)
        self.assertEqual([a for a in depois if a[0] == "gancho"], [])
        self.assertEqual(self.precisa(), 1)
        tid, _ = self.chegar("t1", texto="viu a foto?")
        self.falsa.fila.append(resposta_texto("Ainda não."))
        self.rodar(tid)
        self.assertEqual(imagens_do_pedido(self.falsa.chamadas_chat()[0]["corpo"]), [])

    def test_pior_caso_conta_tokens_fixos_por_imagem(self):
        grande = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {
            "url": "data:image/png;base64," + "A" * 4000000, "detail": "low"}}]}]}
        pequeno = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {
            "url": "data:image/png;base64,AAAA", "detail": "low"}}]}]}
        par = [0.15, 0.60]
        self.assertEqual(precos.pior_caso_usd(par, grande, 0), precos.pior_caso_usd(par, pequeno, 0))
        sem = precos.pior_caso_usd(par, {"messages": [{"role": "user", "content": []}]}, 0)
        self.assertGreaterEqual(precos.pior_caso_usd(par, pequeno, 0) - sem,
                                precos.IMAGEM_TOKENS * par[0] / 1e6 * 0.99)


class TesteDocumento(Base):
    def test_documento_marca_e_nunca_chama_o_modelo(self):
        mid, depois = self.chegar("d1", "documento", PDF)
        self.assertEqual([a for a in depois if a[0] == "gancho"], [])
        self.assertEqual(self.motivos(), ["documento_recebido"])
        self.assertEqual(self.precisa(), 1)
        self.assertIsNone(self.rodar(mid))   # nem a rodada forçada aceita documento como gatilho
        self.assertEqual(self.falsa.pedidos, [])

    def test_documento_depois_de_texto_cala_a_rodada_do_texto(self):
        tid, _ = self.chegar("t1", texto="segue o contrato")
        self.chegar("d1", "documento", PDF)
        self.assertIsNone(self.rodar(tid))
        self.assertEqual(self.falsa.pedidos, [])


class TesteAbaIA(Base):
    def setUp(self):
        super().setUp()
        self.app = types.SimpleNamespace(pasta_dados=self.pasta, raiz=self.projeto)
        caminho = os.path.join(os.path.dirname(AQUI), "painel", "modulos", "vendas", "abas", "ia.py")
        spec = importlib.util.spec_from_file_location("aba_ia_entender", caminho)
        self.aba = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.aba)

    def post(self, corpo):
        return ia.executar(self.app, self.con, "POST", "/ia/entender", {}, corpo)

    def test_padrao_ligado_e_desligar_grava(self):
        estado = ia.estado(self.app, self.con)
        self.assertEqual((estado["entende"]["audio"], estado["entende"]["imagem"]), (True, True))
        self.assertEqual(estado["entende"]["modelo_transcricao"], "gpt-4o-mini-transcribe")
        self.assertEqual(estado["entende"]["preco_minuto"], 0.003)
        codigo, r = self.post({"audio": False, "imagem": True, "modelo_transcricao": "outro-transcritor",
                               "preco_minuto": "0,01"})
        self.assertEqual(codigo, 200)
        self.assertEqual((r["entende"]["audio"], r["entende"]["imagem"], r["entende"]["preco_minuto"]),
                         (False, True, 0.01))
        self.assertFalse(entender.ligado(self.con, self.pasta, "audio"))
        self.assertTrue(entender.ligado(self.con, self.pasta, "imagem"))
        with open(os.path.join(self.pasta, precos.ARQUIVO), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"por_minuto": {"outro-transcritor": 0.01}})
        precos.gravar_preco(self.pasta, "modelo-x", 1.0, 2.0)   # salvar preço de chat mantém o por minuto
        self.assertEqual(precos.preco_minuto(self.pasta, "outro-transcritor"), 0.01)
        self.assertEqual(precos.preco(precos.tabela(self.pasta), "modelo-x"), [1.0, 2.0])

    def test_entradas_invalidas_recusadas(self):
        for corpo in ({"audio": "sim", "imagem": True, "modelo_transcricao": "m"},
                      {"audio": True, "imagem": True, "modelo_transcricao": "nome com espaço"},
                      {"audio": True, "imagem": True, "modelo_transcricao": "m", "preco_minuto": "-1"}):
            self.assertEqual(self.post(corpo)[0], 400, corpo)
        self.assertIsNone(banco.ler_config(self.con, entender.CONFIG["audio"]))

    def test_formulario_da_aba_e_acao(self):
        blocos = self.aba.blocos(ia.estado(self.app, self.con), None, None)
        (form,) = [b for b in blocos if b.get("acao") == "ia_entender"]
        self.assertEqual([c["id"] for c in form["campos"]], ["audio", "imagem", "modelo_transcricao", "preco_minuto"])
        self.assertEqual(form["campos"][0]["valor"], "sim")
        self.assertIn("ia_entender", self.aba.ACOES)
        self.assertNotIn(CHAVE, json.dumps(blocos))
        self.assertEqual(self.aba.agir({}, None, "ia_entender", {"audio": "talvez", "imagem": "sim"})["ok"], False)


class TesteMidiaDoAudioNaoPassaComoImagem(Base):
    def test_audio_e_imagem_na_mesma_rajada(self):
        aid, _ = self.chegar("a1", "audio", OGG)
        iid, _ = self.chegar("i1", "imagem", PNG)
        from testes.openai_falsa import resposta_transcricao
        self.falsa.fila += [resposta_transcricao("olha essa foto"), resposta_texto("Vi a foto.")]
        self.rodar(iid)
        corpo = self.falsa.chamadas_chat()[0]["corpo"]
        self.assertEqual(len(imagens_do_pedido(corpo)), 1)
        textos = [m["content"] for m in corpo["messages"] if m["role"] == "user" and isinstance(m["content"], str)]
        self.assertTrue(any("olha essa foto" in t for t in textos))
        self.assertEqual(self.rascunhos(), ["Vi a foto."])


if __name__ == "__main__":
    unittest.main()
