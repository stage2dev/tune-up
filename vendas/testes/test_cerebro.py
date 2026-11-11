"""Cérebro (servico/cerebro.py) contra a OpenAI FALSA em 127.0.0.1: ida e volta de cada ferramenta, link fora da
lista recusado, sem links.json = nenhum link, error.code lido do corpo, tempo esgotado = nada a enviar + "precisa de
você", teto atingido = 0 chamadas, conta de preço pela usage, nunca reasoning_effort, POST sem nova tentativa depois
de tempo esgotado ou resposta cortada."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, cerebro, chave, openai_cliente, pasta, precos  # noqa: E402
from testes.openai_falsa import OpenAIFalsa, erro, escrever_oferta, resposta_ferramenta, resposta_texto  # noqa: E402

CHAVE = "sk-test-" + "A1b2C3d4E5f6G7h8J9k0" + "WXYZ"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.pasta = pasta.pasta_de_dados(self.projeto, base=os.path.join(self.tmp, "dados"))
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        self.contato = banco.salvar_contato(self.con, "+55 11 90000-0001")
        self.conversa = banco.abrir_conversa(self.con, self.contato)
        self.falsa = OpenAIFalsa()
        self.addCleanup(self.falsa.fechar)
        chave.gravar(self.pasta, CHAVE)
        banco.gravar_config(self.con, "ia_modelo", "gpt-4o-mini")
        self.cerebro = cerebro.Cerebro(self.pasta, self.projeto, self.falsa.url, tempo=0.5)
        escrever_oferta(self.projeto)

    def links(self, dado):
        os.makedirs(os.path.dirname(cerebro.caminho_links(self.projeto)), exist_ok=True)
        with open(cerebro.caminho_links(self.projeto), "w", encoding="utf-8") as f:
            f.write(dado if isinstance(dado, str) else json.dumps(dado))

    def responder(self):
        return self.cerebro.responder(self.con, self.conversa, [{"role": "user", "content": "Oi, quanto custa?"}])

    def precisa(self):
        return self.con.execute("SELECT precisa_de_voce FROM conversas WHERE id = ?",
                                (self.conversa,)).fetchone()[0]


class TesteFerramentas(Base):
    def test_texto_simples_volta_sem_marcar(self):
        self.falsa.fila = [resposta_texto("Custa pouco!")]
        r = self.responder()
        self.assertEqual(r["texto"], "Custa pouco!")
        self.assertFalse(r["precisa_de_voce"])
        self.assertEqual(self.precisa(), 0)
        pedido = self.falsa.chamadas_chat()[0]
        self.assertEqual(pedido["cab"]["Authorization"], "Bearer " + CHAVE)
        self.assertEqual(pedido["corpo"]["model"], "gpt-4o-mini")

    def test_guardar_dado_do_lead_ida_e_volta(self):
        self.falsa.fila = [resposta_ferramenta("guardar_dado_do_lead", {"campo": "nome", "valor": "Ana"}),
                           resposta_texto("Prazer, Ana!")]
        r = self.responder()
        self.assertEqual(r["texto"], "Prazer, Ana!")
        self.assertEqual(self.con.execute("SELECT nome FROM contatos WHERE id = ?", (self.contato,)).fetchone()[0],
                         "Ana")
        segunda = self.falsa.chamadas_chat()[1]["corpo"]["messages"]
        self.assertEqual(segunda[-2]["tool_calls"][0]["function"]["name"], "guardar_dado_do_lead")
        self.assertEqual(segunda[-1], {"role": "tool", "tool_call_id": "call_1", "content": "{\"ok\": true}"})
        evento = self.con.execute("SELECT dados FROM eventos WHERE tipo = 'dado_do_lead'").fetchone()[0]
        self.assertEqual(json.loads(evento)["valor"], "Ana")

    def test_qualificar_ida_e_volta_e_nivel_fora_recusado(self):
        self.falsa.fila = [resposta_ferramenta("qualificar", {"nivel": "quente"}), resposta_texto("Ótimo!")]
        self.assertEqual(self.responder()["texto"], "Ótimo!")
        self.assertEqual(self.con.execute("SELECT estado FROM conversas").fetchone()[0], "quente")
        self.falsa.fila = [resposta_ferramenta("qualificar", {"nivel": "fervendo"}), resposta_texto("Ok")]
        self.responder()
        self.assertEqual(self.con.execute("SELECT estado FROM conversas").fetchone()[0], "quente")
        volta = json.loads(self.falsa.chamadas_chat()[-1]["corpo"]["messages"][-1]["content"])
        self.assertFalse(volta["ok"])

    def test_enviar_link_da_lista(self):
        self.links({"site": "https://exemplo.test/oferta"})
        self.falsa.fila = [resposta_ferramenta("enviar_link", {"nome": "site"}), resposta_texto("Segue o link.")]
        r = self.responder()
        self.assertEqual(r["links"], ["https://exemplo.test/oferta"])
        nomes = [f["function"]["name"] for f in self.falsa.chamadas_chat()[0]["corpo"]["tools"]]
        self.assertIn("enviar_link", nomes)

    def test_enviar_link_fora_da_lista_recusado(self):
        self.links({"site": "https://exemplo.test/oferta"})
        self.falsa.fila = [resposta_ferramenta("enviar_link", {"nome": "https://golpe.test"}), resposta_texto("Ok")]
        r = self.responder()
        self.assertEqual(r["links"], [])
        volta = json.loads(self.falsa.chamadas_chat()[1]["corpo"]["messages"][-1]["content"])
        self.assertEqual(volta, {"ok": False, "erro": "link fora da lista do projeto"})
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM eventos WHERE tipo = 'ia_link_recusado'")
                         .fetchone()[0], 1)

    def test_sem_links_json_ou_vazio_nenhum_link(self):
        for preparar in (lambda: None, lambda: self.links({}), lambda: self.links("")):
            preparar()
            self.falsa.pedidos.clear()
            self.falsa.fila = [resposta_ferramenta("enviar_link", {"nome": "site"}), resposta_texto("Ok")]
            r = self.responder()
            self.assertEqual(r["links"], [])
            nomes = [f["function"]["name"] for f in self.falsa.chamadas_chat()[0]["corpo"]["tools"]]
            self.assertNotIn("enviar_link", nomes)

    def test_links_no_pacote_do_projeto(self):
        self.assertEqual(cerebro.caminho_links(self.projeto), os.path.join(
            self.projeto, ".tune-up", "painel-projeto", "vendas", "links.json"))
        os.makedirs(os.path.join(self.projeto, ".tune-up"), exist_ok=True)
        with open(os.path.join(self.projeto, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump({"pacote": "meu-pacote"}, f)
        self.links({"site": "https://exemplo.test/a"})
        self.assertIn(os.path.join("meu-pacote", "vendas"), cerebro.caminho_links(self.projeto))
        self.assertEqual(cerebro.ler_links(self.projeto), {"site": "https://exemplo.test/a"})
        with open(os.path.join(self.projeto, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump({"pacote": "../fora"}, f)
        self.assertEqual(cerebro.caminho_links(self.projeto), os.path.join(
            self.projeto, ".tune-up", "painel-projeto", "vendas", "links.json"))

    def test_pedir_humano_marca_precisa_de_voce(self):
        self.falsa.fila = [resposta_ferramenta("pedir_humano", {"motivo": "pediu desconto"}),
                           resposta_texto("Já chamo o responsável.")]
        r = self.responder()
        self.assertTrue(r["precisa_de_voce"])
        self.assertEqual(r["motivo"], "pedir_humano")
        self.assertEqual(self.precisa(), 1)

    def test_nunca_manda_reasoning_effort(self):
        self.falsa.fila = [resposta_ferramenta("qualificar", {"nivel": "morno"}), resposta_texto("Ok")]
        self.responder()
        self.assertEqual(len(self.falsa.chamadas_chat()), 2)
        for p in self.falsa.chamadas_chat():
            self.assertIn("tools", p["corpo"])
            self.assertNotIn("reasoning_effort", p["corpo"])
            self.assertNotIn("reasoning_effort", json.dumps(p["corpo"]))


class TesteFalhas(Base):
    def test_error_code_do_corpo_e_nada_a_enviar(self):
        self.falsa.fila = [erro(401, "invalid_api_key")]
        r = self.responder()
        self.assertIsNone(r["texto"])
        self.assertEqual(r["motivo"], "invalid_api_key")
        self.assertEqual(self.precisa(), 1)
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)  # 401 não tenta de novo

    def test_tempo_esgotado_nao_tenta_de_novo_e_nao_envia(self):
        self.falsa.fila = [OpenAIFalsa.DORMIR, resposta_texto("tarde demais")]
        r = self.responder()
        self.assertIsNone(r["texto"])
        self.assertTrue(r["precisa_de_voce"])
        self.assertEqual(r["motivo"], "tempo_esgotado")
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)  # a 1ª pode ter sido cobrada: nunca repete
        self.assertEqual(self.precisa(), 1)

    def test_500_tenta_de_novo_uma_vez(self):
        self.falsa.fila = [erro(500, "server_error"), resposta_texto("Oi!")]
        self.assertEqual(self.responder()["texto"], "Oi!")
        self.assertEqual(len(self.falsa.chamadas_chat()), 2)

    def test_429_sem_credito_nao_tenta_de_novo(self):
        self.falsa.fila = [erro(429, "insufficient_quota"), resposta_texto("Oi!")]
        self.assertEqual(self.responder()["motivo"], "insufficient_quota")
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)

    def test_sem_chave_ou_sem_modelo_nao_chama(self):
        chave.apagar(self.pasta)
        self.assertEqual(self.responder()["motivo"], "sem_chave")
        chave.gravar(self.pasta, CHAVE)
        self.con.execute("DELETE FROM config WHERE chave = 'ia_modelo'")
        self.assertEqual(self.responder()["motivo"], "sem_modelo")
        self.assertEqual(self.falsa.pedidos, [])

    def test_resposta_cortada_nao_tenta_de_novo_e_marca(self):
        self.falsa.fila = [OpenAIFalsa.CORTADO, resposta_texto("tarde demais")]
        r = self.responder()
        self.assertIsNone(r["texto"])
        self.assertEqual(r["motivo"], "rede")
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)
        self.assertEqual(self.precisa(), 1)

    def test_erro_inesperado_nada_a_enviar_e_marca(self):
        original = openai_cliente.pedir

        def explode(*_a, **_k):
            raise RuntimeError("inesperado")
        openai_cliente.pedir = explode
        self.addCleanup(setattr, openai_cliente, "pedir", original)
        r = self.responder()   # não sobe: termina com nada a enviar
        self.assertIsNone(r["texto"])
        self.assertEqual((r["precisa_de_voce"], r["motivo"]), (True, "erro_interno"))
        self.assertEqual(self.precisa(), 1)
        self.assertEqual(self.con.execute("SELECT modo FROM conversas WHERE id = ?", (self.conversa,)).fetchone()[0],
                         "humano")

    def test_ferramenta_em_laco_para_e_marca(self):
        self.falsa.fila = [resposta_ferramenta("qualificar", {"nivel": "morno"})] * cerebro.RODADAS_MAX
        r = self.responder()
        self.assertIsNone(r["texto"])
        self.assertEqual(r["motivo"], "rodadas")


class TesteTeto(Base):
    def test_teto_atingido_zero_chamadas(self):
        banco.gravar_config(self.con, "ia_teto_usd", "0.5")
        precos.somar(self.con, 0.5)
        self.falsa.fila = [resposta_texto("não devia")]
        r = self.responder()
        self.assertEqual(self.falsa.pedidos, [])
        self.assertEqual(r["chamadas"], 0)
        self.assertIsNone(r["texto"])
        self.assertEqual(r["motivo"], "teto_diario")
        self.assertEqual(self.precisa(), 1)

    def test_conta_de_preco_pela_usage(self):
        # gpt-4o-mini na tabela padrão: 0,15 entrada e 0,60 saída por 1 milhão de tokens
        self.falsa.fila = [resposta_texto("Oi", entrada=1000000, saida=500000)]
        r = self.responder()
        self.assertAlmostEqual(r["custo_usd"], 0.15 + 0.30)
        self.assertAlmostEqual(precos.gasto_hoje(self.con), 0.45)

    def test_modelo_sem_preco_nao_chama_e_precos_json_soma_a_tabela(self):
        banco.gravar_config(self.con, "ia_teto_usd", "100")
        banco.gravar_config(self.con, "ia_modelo", "modelo-novo")
        self.falsa.fila = [resposta_texto("não devia")]
        r = self.responder()
        self.assertEqual((r["motivo"], r["chamadas"]), ("preco_desconhecido", 0))
        self.assertEqual(self.falsa.pedidos, [])
        self.assertEqual(self.precisa(), 1)
        with open(os.path.join(self.pasta, precos.ARQUIVO), "w", encoding="utf-8") as f:
            json.dump({"modelo-novo": [10, 20]}, f)
        self.falsa.fila = [resposta_texto("Oi", entrada=1000000, saida=1000000)]
        self.assertAlmostEqual(self.responder()["custo_usd"], 30.0)
        self.assertEqual(precos.preco(precos.tabela(self.pasta), "gpt-4o"), [2.5, 10.0])  # PADRAO continua

    def test_teto_conta_entre_rodadas_e_vira_o_dia(self):
        banco.gravar_config(self.con, "ia_teto_usd", "0.10")
        self.falsa.fila = [resposta_ferramenta("qualificar", {"nivel": "morno"}, entrada=1000000, saida=0),
                           resposta_texto("não devia")]
        r = self.responder()
        self.assertEqual(r["motivo"], "teto_diario")
        self.assertEqual(len(self.falsa.chamadas_chat()), 1)
        self.assertAlmostEqual(precos.gasto_hoje(self.con, "2000-01-01"), 0.0)
        self.assertAlmostEqual(precos.somar(self.con, 0.01, "2000-01-01"), 0.01)

    def test_resposta_sem_usage_cobra_o_pior_caso(self):
        self.falsa.fila = [(200, {"choices": [{"message": {"content": "Oi"}}]})]
        r = self.responder()
        self.assertIsNone(r["texto"])
        self.assertEqual(r["motivo"], "resposta_invalida")
        corpo = self.falsa.chamadas_chat()[0]["corpo"]
        self.assertEqual(corpo["max_completion_tokens"], cerebro.SAIDA_MAX)
        pior = (len(json.dumps(corpo, ensure_ascii=False).encode("utf-8")) * 0.15 + cerebro.SAIDA_MAX * 0.60) / 1e6
        self.assertGreater(precos.gasto_hoje(self.con), cerebro.SAIDA_MAX * 0.60 / 1e6)
        self.assertAlmostEqual(precos.gasto_hoje(self.con), pior, places=5)


class TesteCliente(unittest.TestCase):
    def test_redirecionamento_nao_segue(self):
        falsa = OpenAIFalsa()
        self.addCleanup(falsa.fechar)
        falsa.fila = [(302, {})]
        with self.assertRaises(openai_cliente.ErroOpenAI) as e:
            openai_cliente.pedir(falsa.url, CHAVE, "GET", "/v1/x", tempo=1)
        self.assertEqual(e.exception.codigo, "http_302")

    def test_listar_modelos_cortado_vira_erro_openai(self):
        falsa = OpenAIFalsa()
        self.addCleanup(falsa.fechar)
        falsa.fila = [OpenAIFalsa.CORTADO, OpenAIFalsa.CORTADO]
        with self.assertRaises(openai_cliente.ErroOpenAI) as e:
            openai_cliente.listar_modelos(falsa.url, CHAVE, tempo=1)
        self.assertEqual(e.exception.codigo, "rede")


if __name__ == "__main__":
    unittest.main()
