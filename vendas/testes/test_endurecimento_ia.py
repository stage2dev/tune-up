"""Endurecimento da revisão da Parte D: modelo sem preço não chama (o dono informa o preço na aba IA, precos.json
inválido avisado), conexão recusada ainda tenta de novo, reserva do teto em BEGIN IMMEDIATE contra conversas ao
mesmo tempo, /v1/models lento não derruba a aba (e fica 10 min em cache), chave gravada de forma atômica e modelo
salvo fora da lista continua no seletor."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, cerebro, chave, ia, openai_cliente, precos, travas  # noqa: E402
from testes.openai_falsa import OpenAIFalsa, escrever_oferta, resposta_texto  # noqa: E402
from testes.test_aba_ia import CHAVE, OUTRA, Aba  # noqa: E402
from testes.test_cerebro import Base as BaseCerebro  # noqa: E402


class TestePrecoNaAba(Aba):
    def test_preco_informado_na_aba_libera_o_modelo(self):
        escrever_oferta(self.projeto)
        self.agir("ia_chave", chave=CHAVE)
        self.assertTrue(self.agir("ia_config", modelo="modelo-caro", teto_usd="5")["ok"])
        self.assertFalse(self.estado()["preco_conhecido"])
        texto = json.dumps(self.aba(), ensure_ascii=False)
        self.assertIn("NÃO chama a OpenAI", texto)
        campos = [c["id"] for c in self.form(self.aba(), "ia_config")["campos"]]
        self.assertEqual(campos[-2:], ["preco_entrada", "preco_saida"])
        self.assertFalse(self.agir("ia_config", modelo="modelo-caro", teto_usd="5", preco_entrada="3")["ok"])
        r = self.agir("ia_config", modelo="modelo-caro", teto_usd="5", preco_entrada="3,5", preco_saida="70")
        self.assertTrue(r["ok"], r)
        with open(os.path.join(self.pasta, precos.ARQUIVO), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"modelo-caro": [3.5, 70.0]})
        e = self.estado()
        self.assertEqual((e["preco_conhecido"], e["preco"], e["precos_invalido"]), (True, [3.5, 70.0], False))
        self.assertNotIn("NÃO chama a OpenAI", json.dumps(self.aba(), ensure_ascii=False))

    def test_precos_json_invalido_avisado_e_nao_sobrescrito(self):
        with open(os.path.join(self.pasta, precos.ARQUIVO), "w", encoding="utf-8") as f:
            f.write('{"gpt-4o-mini": [0.15, "caro"]}')
        self.assertTrue(self.estado()["precos_invalido"])
        self.assertIn("precos.json inválido", json.dumps(self.aba(), ensure_ascii=False))
        r = self.agir("ia_config", modelo="gpt-4o-mini", teto_usd="2", preco_entrada="1", preco_saida="2")
        self.assertFalse(r["ok"])
        self.assertIn("inválido", r["mensagem"])
        with open(os.path.join(self.pasta, precos.ARQUIVO), encoding="utf-8") as f:
            self.assertIn('"caro"', f.read())   # o arquivo do dono ficou como estava


class TesteListaDeModelos(Aba):
    def test_lista_lenta_nao_derruba_a_aba(self):
        self.agir("ia_chave", chave=CHAVE)
        self.agir("ia_config", modelo="gpt-4o-mini", teto_usd="2")
        self.mod.ia.TEMPO_MODELOS_S = 0.3   # painel desiste antes da OpenAI falsa responder (1,5 s)
        self.falsa.fila = [OpenAIFalsa.DORMIR]
        blocos = self.aba()
        texto = json.dumps(blocos, ensure_ascii=False)
        self.assertIn("configurada (****LMNO)", texto)
        self.assertIn("Lista de modelos indisponível", texto)
        self.assertEqual(self.form(blocos, "ia_config")["campos"][0]["tipo"], "texto")
        self.assertIsNotNone(self.form(blocos, "ia_chave"))
        self.assertIsNotNone(self.form(blocos, "ia_apagar_chave"))

    def test_servico_lista_em_uma_tentativa_e_menos_tempo_que_o_painel(self):
        self.assertLess(openai_cliente.TEMPO_MODELOS_S, self.mod.ia.TEMPO_MODELOS_S)
        self.falsa.fila = [OpenAIFalsa.DORMIR, OpenAIFalsa.DORMIR]
        with self.assertRaises(openai_cliente.ErroOpenAI):
            openai_cliente.listar_modelos(self.falsa.url, CHAVE, tempo=0.3)
        self.assertEqual(len(self.falsa.pedidos), 1)

    def test_lista_fica_10_min_em_cache_por_chave(self):
        self.agir("ia_chave", chave=CHAVE)
        modelos = lambda: [p for p in self.falsa.pedidos if p["caminho"] == "/v1/models"]  # noqa: E731
        self.aba()
        self.aba()
        self.assertEqual(len(modelos()), 1)
        marca, em, lista = self.app.cache_modelos
        self.app.cache_modelos = (marca, em - ia.CACHE_MODELOS_S - 1, lista)
        self.aba()
        self.assertEqual(len(modelos()), 2)
        self.agir("ia_chave", chave=OUTRA)
        self.aba()
        self.assertEqual(len(modelos()), 3)

    def test_modelo_salvo_fora_da_lista_continua_no_seletor(self):
        self.agir("ia_chave", chave=CHAVE)
        self.agir("ia_config", modelo="meu-modelo", teto_usd="2")
        campo = self.form(self.aba(), "ia_config")["campos"][0]
        self.assertEqual(campo["tipo"], "escolha")
        self.assertEqual(campo["valor"], "meu-modelo")
        self.assertIn("meu-modelo", [o["valor"] for o in campo["opcoes"]])


class TesteChaveAtomica(Aba):
    def test_falha_no_meio_deixa_a_chave_antiga_inteira(self):
        chave.gravar(self.pasta, CHAVE)
        original = travas.os.write

        def quebra(fd, dado):
            original(fd, dado[:5])
            raise OSError("disco cheio")
        travas.os.write = quebra
        self.addCleanup(setattr, travas.os, "write", original)
        with self.assertRaises(OSError):
            chave.gravar(self.pasta, OUTRA)
        travas.os.write = original
        self.assertEqual(chave.ler(self.pasta), CHAVE)
        self.assertEqual([n for n in os.listdir(self.pasta) if n.endswith(".tmp")], [])


class TesteReservaETentativa(BaseCerebro):
    def test_conversas_ao_mesmo_tempo_nao_passam_do_teto_juntas(self):
        with open(os.path.join(self.pasta, precos.ARQUIVO), "w", encoding="utf-8") as f:
            json.dump({"caro": [0.01, 500]}, f)   # pior caso ~ US$ 1,00 por chamada
        banco.gravar_config(self.con, "ia_modelo", "caro")
        banco.gravar_config(self.con, "ia_teto_usd", "1.5")
        outra = banco.abrir_conversa(self.con, banco.salvar_contato(self.con, "+55 11 90000-0002"))
        entrou, solta = threading.Event(), threading.Event()

        def segura():
            entrou.set()
            solta.wait(5)
            return resposta_texto("Oi", entrada=10, saida=10)
        self.falsa.fila = [segura, resposta_texto("Oi", entrada=10, saida=10)]
        self.cerebro.tempo = 5
        resultados = {}

        def rodar(conversa):
            con = banco.abrir(self.pasta)
            try:
                resultados[conversa] = self.cerebro.responder(con, conversa, [{"role": "user", "content": "Oi"}])
            finally:
                con.close()
        primeira = threading.Thread(target=rodar, args=(self.conversa,))
        primeira.start()
        self.assertTrue(entrou.wait(5))
        rodar(outra)   # a 1ª ainda está na OpenAI com a reserva aberta
        solta.set()
        primeira.join(5)
        self.assertEqual(resultados[outra]["motivo"], "teto_diario")
        self.assertEqual(resultados[self.conversa]["texto"], "Oi")
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)
        self.assertAlmostEqual(precos.gasto_hoje(self.con), (10 * 0.01 + 10 * 500) / 1e6, places=6)

    def test_erro_http_libera_a_reserva_e_tempo_esgotado_a_mantem(self):
        self.falsa.fila = [(400, {"error": {"code": "bad_request"}})]
        self.assertEqual(self.responder()["motivo"], "bad_request")
        self.assertEqual(precos.gasto_hoje(self.con), 0.0)
        self.falsa.fila = [OpenAIFalsa.DORMIR]
        self.assertEqual(self.responder()["motivo"], "tempo_esgotado")
        self.assertGreater(precos.gasto_hoje(self.con), cerebro.SAIDA_MAX * 0.60 / 1e6)

    def test_conexao_recusada_tenta_de_novo(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
        s.close()   # porta fechada: conexão recusada
        tentativas, original = [], openai_cliente._uma

        def contar(*a, **k):
            tentativas.append(1)
            return original(*a, **k)
        openai_cliente._uma = contar
        self.addCleanup(setattr, openai_cliente, "_uma", original)
        with self.assertRaises(openai_cliente.ErroOpenAI) as e:   # tempo 5: o Windows demora ~2 s a recusar
            openai_cliente.pedir("http://127.0.0.1:%d" % porta, CHAVE, "POST", "/v1/chat/completions", {}, 5)
        self.assertTrue(e.exception.recusada)
        self.assertEqual(len(tentativas), 2)


if __name__ == "__main__":
    unittest.main()
