"""Modelo da mensagem e trava de número descartável (D2b): variáveis fechadas, empresa + origem + "responda SAIR"
obrigatórios (ao salvar e no texto já preenchido), contato sem valor pulado com motivo, link só da lista, campanha
fria só com número descartável e sem jeito de burlar pelo corpo do pedido. Conector falso; nada de rede."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import agendador, banco, campanha, cerebro, modelo  # noqa: E402
from testes.test_campanha import MODELO, Base, numero  # noqa: E402

COLADO = "Olá {nome}.Aqui é a {empresa}, você veio de {origem}. Responda SAIR para não receber mais."


class AppFalso:
    def __init__(self, raiz):
        self.raiz = raiz


class Modelo(Base):
    def setUp(self):
        Base.setUp(self)
        self.app = AppFalso(os.path.join(self.tmp, "projeto"))

    def contatos(self, *dados):
        return [banco.salvar_contato(self.con, numero(i + 1), nome, origem) for i, (nome, origem) in enumerate(dados)]

    def criar(self, texto=MODELO, ids=None):
        ids = ids or self.contatos(("Ana", "a feira"))
        return campanha.executar(self.app, self.con, "POST", "/campanhas",
                                 {}, {"nome": "c", "modelo": texto, "contato_ids": ids})

    def ativar(self, cid, corpo=None):
        return campanha.executar(self.app, self.con, "POST", "/campanhas/%d/ativar" % cid, {}, corpo or {})

    def links(self, **lista):
        pasta = os.path.join(self.tmp, "projeto", ".tune-up", "painel-projeto", "vendas")
        os.makedirs(pasta)
        with open(os.path.join(pasta, "links.json"), "w", encoding="utf-8") as f:
            json.dump(lista, f)


class TestSalvar(Modelo):
    antes = 0

    def recusa(self, texto, trecho):
        codigo, corpo = self.criar(texto)
        self.assertEqual(codigo, 400)
        self.assertIn(trecho, corpo["erro"])
        self.assertEqual(len(campanha.listar(self.con)["campanhas"]), self.antes)   # nada gravado

    def test_modelo_valido_salva(self):
        self.assertEqual(self.criar()[0], 200)

    def test_sem_sair(self):
        self.recusa("Oi {nome}, aqui é a {empresa}. Você veio de {origem}.", "responda SAIR")

    def test_sem_empresa(self):
        self.recusa("Oi {nome}. Você veio de {origem}. Responda SAIR para parar.", "{empresa}")

    def test_sem_origem(self):
        self.recusa("Oi {nome}, aqui é a {empresa}. Responda SAIR para parar.", "{origem}")

    def test_variavel_desconhecida_e_chave_solta(self):
        self.recusa(MODELO + " {telefone}", "{telefone}")
        self.recusa(MODELO + " }", "chave")

    def test_longo(self):
        self.recusa(MODELO + " x" * 600, "1000")

    def test_link_fora_da_lista_recusado_e_da_lista_aceito(self):
        self.recusa(MODELO + " Veja https://golpe.example/x", "link")
        self.recusa(MODELO + " Veja golpe.example/x", "link")
        self.links(site="https://loja.example/oferta")
        self.assertEqual(self.criar(MODELO + " Veja https://loja.example/oferta")[0], 200)
        self.antes = 1
        self.recusa(MODELO + " Veja https://loja.example/outra", "link")

    def test_variavel_colada_que_forma_link_recusada(self):
        banco.gravar_config(self.con, "empresa", "Loja Teste")
        self.recusa(COLADO, "link")
        self.recusa(COLADO.replace("{nome}.Aqui", "{nome}. Aqui").replace("{origem}.", "{origem}.br"), "link")
        self.assertEqual(self.criar(COLADO.replace("{nome}.Aqui", "{nome}. Aqui"))[0], 200)

    def test_empresa_literal_basta_como_identificacao(self):
        banco.gravar_config(self.con, "empresa", "Loja Teste")
        self.assertEqual(self.criar("Oi, aqui é a Loja Teste. Você veio de {origem}. Responda SAIR.")[0], 200)


class TestAtivar(Modelo):
    def test_sem_empresa_nao_ativa(self):
        cid = self.criar()[1]["id"]
        self.con.execute("DELETE FROM config WHERE chave = 'empresa'")
        codigo, corpo = self.ativar(cid)
        self.assertEqual(codigo, 409)
        self.assertIn("empresa", corpo["erro"])
        self.assertEqual(campanha.listar(self.con)["campanhas"][0]["estado"], "rascunho")

    def test_fria_sem_descartavel_recusada_e_corpo_nao_burla(self):
        cid = self.criar()[1]["id"]
        banco.gravar_config(self.con, "numero_descartavel", "0")
        for corpo in ({}, {"numero_descartavel": True}, {"numero_descartavel": "1", "instancia": "x"}):
            codigo, r = self.ativar(cid, corpo)
            self.assertEqual(codigo, 403)
            self.assertIn("Política do WhatsApp", r["erro"])
        self.assertEqual(banco.ler_config(self.con, "numero_descartavel"), "0")
        self.assertEqual(campanha.listar(self.con)["campanhas"][0]["estado"], "rascunho")
        self.rodar(3)
        self.assertEqual(self.c.envios(), 0)

    def test_com_descartavel_ativa_e_envia_texto_preenchido(self):
        cid = self.criar()[1]["id"]
        self.assertEqual(self.ativar(cid)[0], 200)
        self.rodar(2)
        self.assertEqual([e["conteudo"] for e in self.c.entregues], [
            "Oi Ana, aqui é a Loja Teste. Falamos com você porque veio de a feira. Responda SAIR para não receber mais."])

    def test_contato_ja_atendido_com_consentimento_nao_e_frio(self):
        i = banco.salvar_contato(self.con, numero(1), "Ana", "a feira", "consentimento")
        self.assertTrue(campanha.fria(self.con, i))                     # nunca recebeu nada: frio
        banco.registrar_envio(self.con, "pre:1", "manual", estado="enviado", contato_id=i, instancia="loja")
        self.assertFalse(campanha.fria(self.con, i))
        banco.gravar_config(self.con, "numero_descartavel", "0")
        cid = self.criar(ids=[i])[1]["id"]
        self.assertEqual(self.ativar(cid)[0], 200)
        j = banco.salvar_contato(self.con, numero(2), "Bia", "a feira", "outro: lista comprada")
        banco.registrar_envio(self.con, "pre:2", "manual", estado="enviado", contato_id=j, instancia="loja")
        self.assertTrue(campanha.fria(self.con, j))                     # base fora de consentimento/cliente: frio

    def test_trava_vale_tambem_no_envio(self):
        cid = self.criar()[1]["id"]
        self.assertEqual(self.ativar(cid)[0], 200)
        banco.gravar_config(self.con, "numero_descartavel", "0")      # a instância foi trocada depois de ativar
        self.rodar(3)
        c = campanha.listar(self.con)["campanhas"][0]
        self.assertEqual((self.c.envios(), c["estado"], c["motivo"]), (0, "pausada", "sem_numero_descartavel"))


class TestEnvio(Modelo):
    def test_contato_sem_nome_ou_origem_e_pulado_com_motivo(self):
        ids = self.contatos(("", "a feira"), ("Bia", ""), ("Caio", "a feira"))
        cid = self.criar(ids=ids)[1]["id"]
        self.ativar(cid)
        self.rodar(6)
        self.assertEqual(self.estados(cid), ["pulado", "pulado", "enviado"])
        self.assertEqual(self.motivos(cid), ["sem_nome", "sem_origem", None])
        self.assertEqual(self.c.envios(), 1)
        self.assertNotIn("{", self.c.entregues[0]["conteudo"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios").fetchone()[0], 1)
        self.assertEqual(self.con.execute("SELECT estado FROM campanhas").fetchone()[0], "concluida")

    def test_modelo_que_nao_precisa_de_nome_envia_sem_nome(self):
        ids = self.contatos(("", "a feira"))
        cid = self.criar("Aqui é a {empresa}; você veio de {origem}. Responda SAIR.", ids)[1]["id"]
        self.ativar(cid)
        self.rodar(2)
        self.assertEqual(self.estados(cid), ["enviado"])

    def pausada(self, cid, motivo, estados):
        c = campanha.listar(self.con)["campanhas"][0]
        self.assertEqual((c["estado"], c["motivo"], self.estados(cid)), ("pausada", motivo, estados))

    def test_empresa_mudou_depois_do_salvar_pausa_sem_pular(self):
        ids = self.contatos(("Ana", "a feira"), ("Bia", "a feira"))
        cid = self.criar("Oi, aqui é a Loja Teste. Você veio de {origem}. Responda SAIR.", ids)[1]["id"]
        self.ativar(cid)
        banco.gravar_config(self.con, "empresa", "Outra Loja")
        self.rodar(4)
        self.assertEqual(self.c.envios(), 0)
        self.pausada(cid, "modelo_invalido", ["pendente", "pendente"])

    def test_sem_empresa_no_envio_pausa_sem_pular(self):
        cid = self.criar(ids=self.contatos(("Ana", "a feira"), ("Bia", "a feira")))[1]["id"]
        self.ativar(cid)
        self.con.execute("DELETE FROM config WHERE chave = 'empresa'")
        self.rodar(4)
        self.assertEqual(self.c.envios(), 0)
        self.pausada(cid, "sem_empresa", ["pendente", "pendente"])

    def test_links_quebrado_no_meio_pausa_e_retomar_continua(self):
        self.links(site="https://loja.example/oferta")
        ids = self.contatos(*[("C%d" % i, "a feira") for i in range(5)])
        cid = self.criar(MODELO + " Veja https://loja.example/oferta", ids)[1]["id"]
        ag = agendador.Agendador(lambda: banco.abrir(self.pasta), lambda: self.c, relogio=lambda: self.agora,
                                 aleatorio=random.Random(7),
                                 permitidos=lambda: list(cerebro.ler_links(self.app.raiz).values()))
        self.assertEqual(self.ativar(cid)[0], 200)
        self.rodar(1, ag=ag)
        arquivo = cerebro.caminho_links(self.app.raiz)
        with open(arquivo, "w", encoding="utf-8") as f:
            f.write('{"site": "https://loja.ex')                         # edição pela metade
        self.rodar(6, passo_s=15, ag=ag)
        self.assertEqual(self.c.envios(), 1)
        self.pausada(cid, "modelo_invalido", ["enviado"] + ["pendente"] * 4)
        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump({"site": "https://loja.example/oferta"}, f)
        self.assertEqual(campanha.executar(self.app, self.con, "POST", "/campanhas/%d/retomar" % cid, {}, {})[0], 200)
        self.rodar(10, passo_s=15, ag=ag)
        self.assertEqual((self.estados(cid), self.c.envios()), (["enviado"] * 5, 5))

    def test_modelo_antigo_que_forma_link_pausa_sem_pular(self):
        cid = self.criar(ids=self.contatos(("Ana", "a feira"), ("Bia", "a feira")))[1]["id"]
        self.con.execute("UPDATE campanhas SET modelo = ?", (COLADO,))   # gravado antes da checagem existir
        codigo, corpo = self.ativar(cid)
        self.assertEqual((codigo, "link" in corpo["erro"]), (400, True))   # ativar recusa
        self.con.execute("UPDATE campanhas SET modelo = ?", (MODELO,))
        self.assertEqual(self.ativar(cid)[0], 200)
        self.con.execute("UPDATE campanhas SET modelo = ?", (COLADO,))   # já ativa: o envio confere de novo
        self.rodar(15)
        self.assertEqual(self.c.envios(), 0)
        self.pausada(cid, "modelo_invalido", ["pendente", "pendente"])

    def test_link_da_empresa_fora_da_lista_pausa(self):
        cid = self.criar(ids=self.contatos(("Ana", "a feira")))[1]["id"]
        self.ativar(cid)
        banco.gravar_config(self.con, "empresa", "golpe.example/x")
        self.rodar(2)
        self.pausada(cid, "modelo_invalido", ["pendente"])

    def test_valor_com_chave_ou_link_e_pulado(self):
        ids = self.contatos(("An{a}", "a feira"), ("Bia", "golpe.example/x"))
        cid = self.criar(ids=ids)[1]["id"]
        self.ativar(cid)
        self.rodar(4)
        self.assertEqual(self.motivos(cid), ["valor_invalido", "link_fora_da_lista"])
        self.assertEqual(self.c.envios(), 0)


class TestRenderizar(unittest.TestCase):
    def test_texto_final_e_conferido(self):
        texto, motivo = modelo.renderizar(MODELO, "Ana", "a feira", "Loja", [])
        self.assertEqual(motivo, None)
        self.assertTrue(texto.startswith("Oi Ana, aqui é a Loja."))
        self.assertEqual(modelo.renderizar(MODELO, "x" * 1000, "a feira", "Loja", []), (None, "mensagem_longa"))
        self.assertEqual(modelo.renderizar(MODELO, "Ana", "a feira", "", [])[1], "sem_empresa")
        self.assertEqual(modelo.renderizar(MODELO, "Ana", "a feira", "Loja", [])[1], None)
        for motivo in ("modelo_invalido", "sem_empresa", "sem_identificacao", "sem_sair"):
            self.assertIn(motivo, modelo.DA_CAMPANHA)
        for motivo in ("sem_nome", "sem_origem", "valor_invalido", "link_fora_da_lista", "mensagem_longa"):
            self.assertNotIn(motivo, modelo.DA_CAMPANHA)
        self.assertEqual(modelo.renderizar(COLADO, "Ana", "a feira", "Loja Teste", []), (None, "modelo_invalido"))
        self.assertEqual(modelo.renderizar(MODELO + " " + "x" * 880, "Ana", "a feira", "L" * 100, [])[1],
                         "modelo_invalido")   # passa de 1000 só pela empresa: problema da campanha toda


class TestEmpresa(Modelo):
    def test_rota_grava_e_recusa_chaves(self):
        self.assertEqual(campanha.executar(self.app, self.con, "POST", "/campanhas/empresa", {},
                                           {"empresa": " Acme  "})[0], 200)
        self.assertEqual(banco.ler_config(self.con, "empresa"), "Acme")
        for ruim in ("", "{x}", "a" * 101, 5):
            self.assertEqual(campanha.executar(self.app, self.con, "POST", "/campanhas/empresa", {},
                                               {"empresa": ruim})[0], 400)


if __name__ == "__main__":
    unittest.main()
