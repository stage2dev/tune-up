"""Aba Disparos (D3): blocos de um banco semeado em cada estado de campanha, ativar recusado sem empresa e sem número
descartável (com o motivo), confirmação obrigatória, pausar e retomar mudam o estado, motivos agrupados, prévia e
criação por filtro, falha do serviço = erro, nenhum telefone e nenhum token nos blocos. Serviço de teste vivo."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import banco, campanha  # noqa: E402
from testes.test_campanha import MODELO  # noqa: E402
from testes.test_leads_aba import Aba  # noqa: E402

TELEFONES = ["+55 11 90000-%04d" % i for i in range(1, 7)]


class Disparos(Aba):
    def setUp(self):
        super().setUp()
        self.sql("gravar", "fuso", "-03:00")

    def sql(self, modo, *args):
        """'gravar' = config; qualquer outro texto = SQL direto (args[0] = texto, args[1] = parâmetros)."""
        con = banco.abrir(self.pasta)
        try:
            if modo == "gravar":
                return banco.gravar_config(con, *args)
            return [tuple(r) for r in con.execute(modo, *args).fetchall()]
        finally:
            con.close()

    def contatos(self, n=3, base="consentimento", origem="feira"):
        con = banco.abrir(self.pasta)
        try:
            return [banco.salvar_contato(con, TELEFONES[i], "Ana%d" % i, origem, base) for i in range(n)]
        finally:
            con.close()

    def campanha(self, ids, estado=None, motivo=None):
        con = banco.abrir(self.pasta)
        try:
            cid = campanha.criar(con, "Black Friday", MODELO, ids)
            if estado:
                con.execute("UPDATE campanhas SET estado = ?, motivo = ? WHERE id = ?", (estado, motivo, cid))
            return cid
        finally:
            con.close()

    def estado(self, cid):
        return self.sql("SELECT estado FROM campanhas WHERE id = ?", (cid,))[0][0]

    def aba(self):
        return [a for a in self.mod.montar(self.ctx, base=self.base)["abas"] if a["id"] == "disparos"][0]["blocos"]

    def blocos_de(self, tipo, titulo=""):
        return [b for b in self.aba() if b["tipo"] == tipo and titulo in (b.get("titulo") or "")]

    def botoes(self):
        return [x for b in self.aba() if b["tipo"] == "conversa" for x in b["botoes"]]

    def pronto(self):
        self.sql("gravar", "empresa", "Loja Teste")
        self.sql("gravar", "numero_descartavel", "1")


class TesteBlocos(Disparos):
    def test_acoes_registradas_e_aba_existe(self):
        for a in ("disparos_empresa", "disparos_previa", "disparos_criar", "disparos_ativar", "disparos_pausar",
                  "disparos_retomar"):
            self.assertIn(a, self.mod.INFO["acoes"])
        self.assertTrue(self.aba())

    def test_sem_campanha_e_sem_empresa(self):
        hoje = self.blocos_de("kpis", "Hoje")[0]["itens"]
        self.assertEqual({i["rotulo"]: i["valor"] for i in hoje}["Empresa"], "falta informar")
        self.assertIn("Nenhuma campanha", json.dumps(self.aba()))

    def test_um_bloco_por_estado_e_botoes_certos(self):
        self.pronto()
        ids = self.contatos(1)
        ra, at = self.campanha(ids), self.campanha(ids, "ativa")
        pa = self.campanha(ids, "pausada", "5_falhas_seguidas:erro_de_rede")
        co = self.campanha(ids, "concluida")
        titulos = [b["titulo"] for b in self.blocos_de("kpis", "#")]
        for cid, rotulo in ((co, "concluída"), (pa, "pausada"), (at, "ativa"), (ra, "rascunho")):
            self.assertIn("#%d Black Friday (%s)" % (cid, rotulo), titulos)
        botoes = {b["acao"]: b for b in self.botoes()}
        self.assertEqual(botoes["disparos_ativar"]["dados"], {"campanha_id": ra, "confirmar": True})
        self.assertEqual(botoes["disparos_pausar"]["dados"], {"campanha_id": at})
        self.assertEqual(botoes["disparos_retomar"]["dados"], {"campanha_id": pa})
        self.assertEqual(len(self.botoes()), 3)   # a concluída não tem botão
        texto = [b for b in self.blocos_de("texto", "Por que está pausada")][0]["texto"]
        self.assertIn("5 falhas seguidas do envio (erro_de_rede)", texto)
        self.assertIn("Ana0", [b for b in self.blocos_de("texto", "Prévia")][0]["texto"])   # só o rascunho tem prévia
        self.assertEqual(len(self.blocos_de("texto", "Prévia")), 1)

    def test_progresso_e_motivos_agrupados(self):
        ids = self.contatos(6)
        cid = self.campanha(ids, "ativa")
        estados = [("enviado", None), ("enviado", None), ("incerto", None), ("respondeu", None),
                   ("negado", "optout"), ("negado", "optout")]
        for contato, (estado, motivo) in zip(ids, estados):
            self.sql("UPDATE campanha_contatos SET estado = ?, motivo = ? WHERE contato_id = ?", (estado, motivo, contato))
        self.sql("UPDATE campanha_contatos SET estado = 'pendente', motivo = 'fora_da_janela' WHERE contato_id = ?",
                 (ids[3],))
        self.sql("UPDATE contatos SET optout_em = '2026-11-01T00:00:00+00:00' WHERE id IN (?, ?)", (ids[4], ids[5]))
        itens = {i["rotulo"]: i["valor"] for i in self.blocos_de("kpis", "#%d " % cid)[0]["itens"]}
        self.assertEqual((itens["Enviadas"], itens["Incertas"], itens["Na fila"], itens["Negadas"],
                          itens["Saíram (opt-out)"], itens["Responderam"]), (2, 1, 1, 2, 2, 0))
        # lista exata: um item por motivo (dois contatos com opt-out = UM item com 2), maior contagem primeiro
        motivos = [(i["titulo"], i["detalhe"]) for i in self.blocos_de("lista", "por motivo")[0]["itens"]]
        self.assertEqual(motivos, [("saiu da lista (opt-out)", "2 contato(s), situação: negado"),
                                   ("fora da janela 09:00-19:00 (espera abrir)", "1 contato(s), situação: pendente")])

    def test_hoje_janela_e_aquecimento(self):
        itens = {i["rotulo"]: i for i in self.blocos_de("kpis", "Hoje")[0]["itens"]}
        self.assertIn(itens["Janela 09-19"]["valor"], ("dentro", "fora"))
        self.assertEqual(itens["Contatos novos hoje"]["valor"], "sem número conectado")
        self.sql("gravar", "instancia", "loja")
        itens = {i["rotulo"]: i for i in self.blocos_de("kpis", "Hoje")[0]["itens"]}
        self.assertEqual(itens["Contatos novos hoje"]["valor"], "0 de 5")
        ids = self.contatos(1)
        self.sql("INSERT INTO envios (chave_dedupe, contato_id, estado, origem, criado_em, tentado_em, instancia) "
                 "VALUES ('k', ?, 'enviado', 'campanha', ?, ?, 'loja')", (ids[0],) + (banco.agora(),) * 2)
        itens = {i["rotulo"]: i for i in self.blocos_de("kpis", "Hoje")[0]["itens"]}
        self.assertEqual(itens["Contatos novos hoje"]["valor"], "1 de 5")

    def test_nenhum_telefone_nem_token(self):
        ids = self.contatos(3)
        self.campanha(ids)
        self.agir("disparos_previa", modelo=MODELO)
        tudo = json.dumps(self.aba(), ensure_ascii=False)
        for pedaco in ("90000", "5511", "+55", self.token, self.segredo):
            self.assertNotIn(pedaco, tudo)

    def test_servico_parado_aba_avisa(self):
        self.parar_batimento()
        self.sql("DELETE FROM batimento")
        self.assertEqual(self.aba()[0]["tipo"], "texto")
        r = self.agir("disparos_pausar", campanha_id=1)
        self.assertFalse(r["ok"])
        self.assertIn("parado", r["mensagem"])


class TesteAtivar(Disparos):
    def test_sem_empresa_recusa_com_o_motivo(self):
        cid = self.campanha(self.contatos(1))
        r = self.agir("disparos_ativar", campanha_id=cid, confirmar=True)
        self.assertFalse(r["ok"])
        self.assertIn("nome da empresa", r["mensagem"])
        self.assertEqual(self.estado(cid), "rascunho")

    def test_frio_sem_numero_descartavel_recusa_com_o_motivo_e_o_botao_avisa(self):
        self.sql("gravar", "empresa", "Loja Teste")
        cid = self.campanha(self.contatos(1, base="contato_publico_da_empresa"))
        r = self.agir("disparos_ativar", campanha_id=cid, confirmar=True)
        self.assertFalse(r["ok"])
        self.assertIn("descartável", r["mensagem"])
        self.assertEqual(self.estado(cid), "rascunho")
        self.assertIn("pode banir o número", self.botoes()[0]["confirmar"])

    def test_botao_sem_contato_frio_nao_traz_o_aviso(self):
        self.pronto()
        self.campanha(self.contatos(1))   # consentimento, mas nunca recebeu nada: continua frio
        self.assertIn("pode banir", self.botoes()[0]["confirmar"])
        self.sql("gravar", "instancia", "loja")
        self.sql("INSERT INTO envios (chave_dedupe, contato_id, estado, origem, criado_em, instancia) VALUES ('k', 1, "
                 "'enviado', 'manual', ?, 'outra')", (banco.agora(),))
        self.assertIn("pode banir", self.botoes()[0]["confirmar"])   # recebeu de OUTRO número: frio para este
        self.sql("UPDATE envios SET instancia = 'loja' WHERE chave_dedupe = 'k'")
        self.assertNotIn("pode banir", self.botoes()[0]["confirmar"])

    def test_sem_confirmar_nada_muda(self):
        self.pronto()
        cid = self.campanha(self.contatos(1))
        for dados in ({"campanha_id": cid}, {"campanha_id": cid, "confirmar": "sim"}):
            r = self.agir("disparos_ativar", **dados)
            self.assertFalse(r["ok"], r)
        self.assertEqual(self.estado(cid), "rascunho")

    def test_com_tudo_ativa_e_o_bloco_muda(self):
        self.pronto()
        cid = self.campanha(self.contatos(2))
        self.assertTrue(self.agir("disparos_ativar", campanha_id=cid, confirmar=True)["ok"])
        self.assertEqual(self.estado(cid), "ativa")
        self.assertEqual([b["acao"] for b in self.botoes()], ["disparos_pausar"])

    def test_campanha_invalida(self):
        for valor in (None, "1", True, 0, -3):
            self.assertFalse(self.agir("disparos_pausar", campanha_id=valor)["ok"], valor)
        r = self.agir("disparos_pausar", campanha_id=999)
        self.assertFalse(r["ok"])


class TestePausar(Disparos):
    def test_pausar_e_retomar_mudam_o_estado_e_zeram_o_motivo(self):
        self.pronto()
        cid = self.campanha(self.contatos(1), "ativa")
        self.assertTrue(self.agir("disparos_pausar", campanha_id=cid)["ok"])
        self.assertEqual(self.estado(cid), "pausada")
        self.assertIn("você pausou", json.dumps(self.aba(), ensure_ascii=False))
        self.assertEqual([b["acao"] for b in self.botoes()], ["disparos_retomar"])
        self.assertTrue(self.agir("disparos_retomar", campanha_id=cid)["ok"])
        self.assertEqual(self.estado(cid), "ativa")
        self.assertEqual(self.sql("SELECT motivo FROM campanhas WHERE id = ?", (cid,))[0][0], None)

    def test_estado_errado_vira_erro_nao_sucesso(self):
        cid = self.campanha(self.contatos(1))   # rascunho
        for acao in ("disparos_pausar", "disparos_retomar"):
            r = self.agir(acao, campanha_id=cid)
            self.assertFalse(r["ok"])
            self.assertIn("estado", r["mensagem"])
        self.assertEqual(self.estado(cid), "rascunho")


class TesteCriar(Disparos):
    def setUp(self):
        super().setUp()
        self.contatos(2, origem="feira")
        con = banco.abrir(self.pasta)
        try:
            banco.salvar_contato(con, TELEFONES[2], "Caio", "site", "contato_publico_da_empresa")
            banco.marcar_optout(con, TELEFONES[1])
        finally:
            con.close()
        self.sql("gravar", "empresa", "Loja Teste")

    def test_previa_conta_novos_e_mostra_3_mensagens_sem_telefone(self):
        self.contatos(0)
        r = self.agir("disparos_previa", modelo=MODELO)
        self.assertTrue(r["ok"], r)
        self.assertIn("2 contato(s) escolhido(s); 2 novo(s)", r["mensagem"])   # quem saiu fica de fora
        self.assertIn("Oi Ana0, aqui é a Loja Teste", r["mensagem"])
        self.assertNotIn("90000", r["mensagem"])
        r = self.agir("disparos_previa", modelo=MODELO, origem="site", base_legal="contato_publico_da_empresa")
        self.assertIn("1 contato(s) escolhido(s); 1 novo(s) para o aquecimento; 1 frio(s)", r["mensagem"])

    def test_previa_so_conta_como_novo_quem_nao_recebeu_da_instancia(self):
        self.sql("gravar", "instancia", "loja")
        self.sql("INSERT INTO envios (chave_dedupe, contato_id, estado, origem, criado_em, tentado_em, instancia) "
                 "VALUES ('k', 1, 'enviado', 'campanha', ?, ?, 'loja')", (banco.agora(),) * 2)
        r = self.agir("disparos_previa", modelo=MODELO)
        self.assertIn("2 contato(s) escolhido(s); 1 novo(s)", r["mensagem"])

    def test_previa_de_amostra_que_nao_sai_diz_o_motivo(self):
        self.sql("UPDATE contatos SET nome = NULL WHERE id = 1")
        r = self.agir("disparos_previa", modelo=MODELO)
        self.assertIn("não sairia: contato sem nome", r["mensagem"])

    def test_modelo_ruim_e_filtro_ruim_sao_erro(self):
        r = self.agir("disparos_previa", modelo="Oi {nome}")
        self.assertFalse(r["ok"])
        self.assertIn("empresa", r["mensagem"])
        self.assertFalse(self.agir("disparos_previa", modelo=MODELO, qualificacao="quentissimo")["ok"])
        self.assertFalse(self.agir("disparos_criar", id_cliente="t1", nome="x", modelo=MODELO, base_legal="inventada")["ok"])

    def test_criar_por_filtro_cria_rascunho_sem_quem_saiu(self):
        r = self.agir("disparos_criar", id_cliente="t1", nome="Feira", modelo=MODELO, origem="feira")
        self.assertTrue(r["ok"], r)
        linhas = self.sql("SELECT c.estado, COUNT(cc.contato_id) FROM campanhas c JOIN campanha_contatos cc ON "
                          "cc.campanha_id = c.id GROUP BY c.id")
        self.assertEqual(linhas, [("rascunho", 1)])
        self.assertEqual(len(self.botoes()), 1)

    def test_criar_sem_ninguem_ou_sem_nome_e_erro(self):
        self.assertFalse(self.agir("disparos_criar", id_cliente="t1", nome="x", modelo=MODELO, origem="nao-existe")["ok"])
        self.assertFalse(self.agir("disparos_criar", id_cliente="t1", nome="  ", modelo=MODELO)["ok"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM campanhas")[0][0], 0)

    def test_empresa_grava_e_recusa_vazio_ou_com_chave(self):
        self.sql("DELETE FROM config WHERE chave = 'empresa'")
        self.assertFalse(self.agir("disparos_empresa", empresa="")["ok"])
        self.assertFalse(self.agir("disparos_empresa", empresa="A {b}")["ok"])
        self.assertTrue(self.agir("disparos_empresa", empresa="Loja Teste")["ok"])
        self.assertEqual(self.sql("SELECT valor FROM config WHERE chave = 'empresa'")[0][0], "Loja Teste")


if __name__ == "__main__":
    unittest.main()
