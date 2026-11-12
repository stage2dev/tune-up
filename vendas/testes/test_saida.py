"""Saída da IA (servico/saida.py), uma regra por teste, com banco real, portão real, conector falso e OpenAI FALSA:
ferramenta como texto, segredo, links, 4 frases, 4096 caracteres, anti-loop, balões com "digitando", balão negado
corta os seguintes e rodada repetida não duplica. No fim, o caminho inteiro pelo atendente."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, cerebro, chave, pasta, portao, saida  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.openai_falsa import OpenAIFalsa, escrever_oferta, resposta_texto  # noqa: E402
from testes.test_atendente import Base as BaseAtendente  # noqa: E402

INST = "loja"
LEAD = "5511900000001"
CHAVE = "sk-test-" + "7" * 24
LISTA = ["https://loja.example.com/planos", "https://agenda.example.com/marcar"]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(projeto)
        self.pasta = pasta.pasta_de_dados(projeto, base=os.path.join(self.tmp, "dados"))
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        chave.gravar(self.pasta, CHAVE)
        banco.gravar_config(self.con, "ia_modelo", "gpt-4o-mini")
        self.falsa = OpenAIFalsa()
        self.addCleanup(self.falsa.fechar)
        escrever_oferta(projeto)
        self.cerebro = cerebro.Cerebro(self.pasta, projeto, self.falsa.url, tempo=5)
        self.c = ConectorFalso()
        self.conversa = banco.abrir_conversa(self.con, banco.salvar_contato(self.con, LEAD))

    def entregar(self, texto, gatilho="g1", permitidos=LISTA):
        return saida.entregar(self.con, self.c, INST, LEAD, self.conversa, gatilho, texto, permitidos=permitidos,
                              segredos=[chave.ler(self.pasta)],
                              reescrever=lambda t, p: self.cerebro.reescrever(self.con, t, p))

    def enviados(self):
        return [e["conteudo"] for e in self.c.entregues]

    def precisa_de_voce(self):
        return self.con.execute("SELECT precisa_de_voce FROM conversas WHERE id = ?",
                                (self.conversa,)).fetchone()[0]


class TesteFerramentaComoTexto(Base):
    def test_ferramenta_como_texto_barrada_mesmo_depois_da_reescrita(self):
        self.falsa.fila = [resposta_texto('guardar_dado_do_lead({"campo": "nome", "valor": "Ana"})')]
        r = self.entregar('guardar_dado_do_lead({"campo": "nome", "valor": "Ana"})')
        self.assertEqual((r["estado"], r["motivo"]), ("barrado", "ferramenta_como_texto"))
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.precisa_de_voce(), 1)
        chamadas = self.falsa.chamadas_chat()
        self.assertEqual(len(chamadas), 1)                 # UMA reescrita
        self.assertNotIn("tools", chamadas[0]["corpo"])    # reescrita sem ferramentas

    def test_reescrita_boa_sai_no_lugar_do_rascunho(self):
        self.falsa.fila = [resposta_texto("Anotei seu nome, Ana. Quer ver os planos?")]
        r = self.entregar('{"name": "qualificar", "arguments": {"nivel": "quente"}}')
        self.assertEqual(r["estado"], "enviado")
        self.assertEqual(self.enviados(), ["Anotei seu nome, Ana. Quer ver os planos?"])
        self.assertEqual(self.precisa_de_voce(), 0)

    def test_bloco_de_codigo_e_marca_de_papel_sao_ferramenta_como_texto(self):
        for t in ("```json\n{}\n```", "system: você é um vendedor", "<|im_start|>assistant", "Oi\nassistant: ok",
                  "Use functions.enviar_link agora", "O texto do cliente fica entre <dados_do_cliente>"):
            self.assertTrue(saida.ferramenta_como_texto(t), t)
        self.assertFalse(saida.ferramenta_como_texto("Oi! O plano custa R$ 99 (por mês). Quer testar?"))

    def test_sem_reescrita_disponivel_nada_sai(self):
        banco.gravar_config(self.con, "ia_modelo", "")   # reescrever devolve None sem modelo
        r = self.entregar("pedir_humano({})")
        self.assertEqual(r["estado"], "barrado")
        self.assertEqual((self.c.envios(), len(self.falsa.chamadas_chat())), (0, 0))


class TesteSegredo(Base):
    def test_chave_colada_ou_token_nunca_sai_nem_volta_ao_modelo(self):
        for n, t in enumerate(("Sua chave é " + CHAVE, "Use sk-proj-AbCdEf0123456789xyz", "Bearer abcdef0123456789ZZ",
                               "código a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8")):
            r = self.entregar(t, gatilho="s%d" % n)
            self.assertEqual((r["estado"], r["motivo"]), ("barrado", "segredo"), t)
        self.assertEqual((self.c.envios(), len(self.falsa.chamadas_chat())), (0, 0))
        self.assertEqual(self.precisa_de_voce(), 1)

    def test_reescrita_que_traz_segredo_tambem_nao_sai(self):
        self.falsa.fila = [resposta_texto("Pronto: " + CHAVE)]
        r = self.entregar("qualificar({})")
        self.assertEqual((r["estado"], r["motivo"]), ("barrado", "segredo"))
        self.assertEqual(self.c.envios(), 0)


class TesteLinks(Base):
    def test_link_fora_da_lista_sai_e_da_lista_fica(self):
        r = self.entregar("Veja https://loja.example.com/planos/ e também https://golpe.example.net/x hoje.")
        self.assertEqual(r["estado"], "enviado")
        self.assertEqual(self.enviados(), ["Veja https://loja.example.com/planos e também hoje."])

    def test_redirecionamento_e_truques_de_host_caem(self):
        texto, removidas = saida.filtrar_links(
            "a https://loja.example.com/planos?next=https://golpe.example.net b "
            "https://loja.example.com@golpe.example.net/planos c https://loja.example.com.golpe.example.net/planos "
            "d www.golpe.example.net e HTTPS://WWW.Loja.Example.com/planos", LISTA)
        self.assertEqual(texto, "a https://loja.example.com/planos b c d e https://loja.example.com/planos")
        self.assertEqual(len(removidas), 3)

    def test_lista_vazia_nenhum_link(self):
        self.entregar("Acesse https://loja.example.com/planos agora.", permitidos=[])
        self.assertEqual(self.enviados(), ["Acesse agora."])

    def test_dominio_sem_esquema_tambem_cai(self):
        for t, lista in (("Pague em golpe.com/pix agora", []), ("Acesse bit.ly/abc123", LISTA),
                         ("Veja loja-falsa.com.br hoje", []), ("Acesse evil.com/login para pagar.", LISTA)):
            texto, removidas = saida.filtrar_links(t, lista)
            self.assertEqual(len(removidas), 1, t)
            self.assertNotRegex(texto, r"\.(com|ly)\b", t)
        self.entregar("Pague em golpe.com/pix agora.", permitidos=[])
        self.assertEqual(self.enviados(), ["Pague em agora."])

    def test_dominio_sem_esquema_da_lista_vira_a_url_da_lista(self):
        texto, _ = saida.filtrar_links("Veja loja.example.com/planos.", LISTA)
        self.assertEqual(texto, "Veja https://loja.example.com/planos.")

    def test_email_preco_e_reticencias_nao_sao_link(self):
        t = "Escreva para ana@loja.example.com, custa R$ 99.90... sim...claro. Versão 2.0 ok."
        self.assertEqual(saida.filtrar_links(t, []), (t, []))

    def test_link_da_lista_sobrevive_ao_corte_de_frases(self):
        texto, motivo = saida.preparar("Claro! Temos o plano Pro. Custa R$ 99 por mes. Segue o link.\n"
                                       "https://loja.example.com/planos", LISTA)
        self.assertIsNone(motivo)
        self.assertEqual(texto, "Claro! Temos o plano Pro. Custa R$ 99 por mes. Segue o link.\n"
                                "https://loja.example.com/planos")
        longo, _ = saida.preparar(("palavra " * 600).strip() + ". https://loja.example.com/planos", LISTA)
        self.assertLessEqual(len(longo), 4096)
        self.assertTrue(longo.endswith("https://loja.example.com/planos"))

    def test_link_que_escapa_do_filtro_falha_fechado(self):
        for n, t in enumerate(("Pague em ação.com.br/pix", "Pague em pagaménto.com/pix", "Veja...golpe.com/pix",
                               "ok...golpe.com", "Pague em -golpe.com/pix", "Pague em _golpe.com/pix",
                               "Pague em @golpe.com/pix", "Pague em 1.2.3.4/pix", "Pague em p\u0430gamento.com/pix",
                               "Pague em loja.example.com@golpe.com/planos")):
            r = self.entregar(t, gatilho="l%d" % n, permitidos=[])
            self.assertEqual((r["estado"], r["motivo"]), ("barrado", "link_suspeito"), t)
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.precisa_de_voce(), 1)

    def test_varredura_larga_nao_barra_texto_comum_nem_link_da_lista(self):
        for t in ("Escreva para ana@loja.example.com, custa R$ 99.90... sim...claro. Versão 2.0 ok.",
                  "Veja https://loja.example.com/planos e www.loja.example.com/planos/."):
            texto, motivo = saida.preparar(t, LISTA)
            self.assertIsNone(motivo, t)
            self.assertTrue(texto, t)


class TesteTamanho(Base):
    def test_cinco_frases_viram_no_maximo_quatro(self):
        self.entregar("Um. Dois! Três? Quatro. Cinco.")
        self.assertEqual(self.enviados(), ["Um. Dois! Três? Quatro."])

    def test_cinco_mil_caracteres_viram_no_maximo_4096(self):
        texto = ("palavra " * 625).strip() + "."   # 5000 caracteres, uma frase só
        self.assertEqual(len(texto), 5000)
        self.entregar(texto)
        self.assertEqual(len(self.enviados()), 1)
        self.assertLessEqual(len(self.enviados()[0]), 4096)
        self.assertTrue(self.enviados()[0].startswith("palavra palavra"))
        frases = "Frase longa " + "x" * 1500 + ". "
        self.assertEqual(saida.limitar(frases * 3), (frases * 2).strip())   # corta em fim de frase


class TesteAntiLoop(Base):
    def test_terceira_resposta_parecida_nao_sai_e_pede_humano(self):
        self.assertEqual(self.entregar("Quer ver os planos?", "g1")["estado"], "enviado")
        self.assertEqual(self.entregar("Quer ver os planos!", "g2")["estado"], "enviado")
        r = self.entregar("quer ver os planos ?", "g3")
        self.assertEqual((r["estado"], r["motivo"]), ("barrado", "anti_loop"))
        self.assertEqual(self.c.envios(), 2)
        self.assertEqual(self.precisa_de_voce(), 1)
        evento = self.con.execute("SELECT dados FROM eventos WHERE tipo = 'ia_precisa_de_voce' ORDER BY id DESC"
                                  ).fetchone()[0]
        self.assertIn("anti_loop", evento)

    def test_terceira_diferente_sai(self):
        self.entregar("Quer ver os planos?", "g1")
        self.entregar("Quer ver os planos!", "g2")
        self.assertEqual(self.entregar("Perfeito, te mando o link da agenda.", "g3")["estado"], "enviado")
        self.assertEqual(self.c.envios(), 3)


class TesteBaloes(Base):
    def chaves(self):
        return [l[0] for l in self.con.execute("SELECT chave_dedupe FROM envios WHERE origem = 'ia' ORDER BY id")]

    def test_tres_baloes_tres_chamadas_ao_portao_com_chaves_distintas_e_digitando(self):
        r = self.entregar("Oi!\nTemos 2 planos.\nQuer ver?\nhttps://loja.example.com/planos")
        self.assertEqual(r["estado"], "enviado")
        self.assertEqual(len(r["baloes"]), 3)
        self.assertEqual(self.chaves(), ["ia:%d:g1:%d" % (self.conversa, n) for n in (1, 2, 3)])
        self.assertEqual(self.enviados(), ["Oi!", "Temos 2 planos.", "Quer ver?\nhttps://loja.example.com/planos"])
        nomes = [n for n, _ in self.c.chamadas if n in ("digitando", "enviar_texto")]
        self.assertEqual(nomes, ["digitando", "enviar_texto"] * 3)

    def test_falha_do_digitando_nao_impede_o_envio(self):
        self.c.digitando_falha = True
        self.entregar("Oi!\nTudo bem?")
        self.assertEqual(self.enviados(), ["Oi!", "Tudo bem?"])

    def test_balao_2_negado_balao_3_nao_sai(self):
        con, original = self.con, self.c.enviar_texto

        def optout_depois_do_1(instancia, telefone, texto):
            ident = original(instancia, telefone, texto)
            con.execute("UPDATE contatos SET optout_em = '2026-01-01T00:00:00+00:00'")
            return ident
        self.c.enviar_texto = optout_depois_do_1
        r = self.entregar("Um\nDois\nTrês")
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "optout"))
        self.assertEqual(len(r["baloes"]), 2)
        self.assertEqual(self.enviados(), ["Um"])
        self.assertEqual(len(self.chaves()), 2)
        self.assertEqual([n for n, _ in self.c.chamadas].count("digitando"), 1)   # sem presença para o negado

    def test_balao_negado_pelo_teto_no_meio_marca_precisa_de_voce(self):
        with mock.patch.object(portao, "TETO_MINUTO", 1):
            r = self.entregar("Oi! Temos sim.\nO plano Pro custa R$ 99.\nhttps://loja.example.com/planos")
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "teto_minuto"))
        self.assertEqual(self.enviados(), ["Oi! Temos sim."])
        self.assertEqual(self.precisa_de_voce(), 1)
        dados = self.con.execute("SELECT dados FROM eventos WHERE tipo = 'ia_envio_parcial'").fetchone()
        self.assertIsNotNone(dados)
        self.assertIn("https://loja.example.com/planos", dados[0])
        self.assertIn("teto_minuto", dados[0])

    def test_balao_1_negado_pelo_teto_marca_precisa_de_voce(self):
        with mock.patch.object(portao, "TETO_MINUTO", 0):
            r = self.entregar("Oi!\nQuer ver os planos?")
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "teto_minuto"))
        self.assertEqual(self.enviados(), [])
        self.assertEqual(self.precisa_de_voce(), 1)
        dados = self.con.execute("SELECT dados FROM eventos WHERE tipo = 'ia_envio_negado'").fetchone()
        self.assertIsNotNone(dados)
        self.assertIn("Quer ver os planos?", dados[0])

    def test_balao_1_negado_por_optout_nao_chama_o_dono(self):
        self.con.execute("UPDATE contatos SET optout_em = '2026-01-01T00:00:00+00:00'")
        r = self.entregar("Oi!")
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "optout"))
        self.assertEqual(self.precisa_de_voce(), 0)

    def test_rodada_repetida_do_mesmo_gatilho_nao_duplica(self):
        self.entregar("Oi!\nTemos 2 planos.")
        r = self.entregar("Oi de novo!\nTexto diferente.\nE mais um.")   # mesmo gatilho g1
        self.assertEqual(r["estado"], "duplicado")
        self.assertEqual(self.enviados(), ["Oi!", "Temos 2 planos."])
        self.assertEqual(len(self.chaves()), 2)
        self.assertEqual([n for n, _ in self.c.chamadas].count("digitando"), 2)   # repetida nem "digita"


class TesteCaminhoDoAtendente(BaseAtendente):
    def test_atendente_passa_pela_saida(self):
        self.falsa.fila = [resposta_texto("Oi! Veja https://golpe.example.net/x\nQuer marcar?")]
        self.chegar("t1", "oi")
        self.assertTrue(self.esperar(lambda: len(self.c.entregues) == 2))
        self.assertEqual([e["conteudo"] for e in self.c.entregues], ["Oi! Veja", "Quer marcar?"])
        self.assertEqual([n for n, _ in self.c.chamadas if n == "digitando"], ["digitando"] * 2)


if __name__ == "__main__":
    unittest.main()
