"""Aba Disparos, achados da revisão: campanha ativa ou pausada nunca some da tela atrás de rascunhos novos; criar por
filtro não pega quem já está noutra campanha (a prévia avisa quantos); criar repetido com o mesmo id_cliente do
formulário não cria outra campanha. Serviço de teste vivo."""
import sys

sys.dont_write_bytecode = True

import unittest  # noqa: E402
from unittest import mock  # noqa: E402

from servico import banco, disparos  # noqa: E402
from testes.test_aba_disparos import TELEFONES, Disparos  # noqa: E402
from testes.test_campanha import MODELO  # noqa: E402


class TesteVivasSempreNaTela(Disparos):
    def test_ativa_e_pausada_antigas_aparecem_com_botao_e_motivo(self):
        self.pronto()
        ids = self.contatos(1)
        ativa = self.campanha(ids, "ativa")
        pausada = self.campanha(ids, "pausada", "5_falhas_seguidas:erro_de_rede")
        for _ in range(10):
            self.campanha(ids)   # 10 rascunhos mais novos
        botoes = self.botoes()
        self.assertIn({"campanha_id": ativa}, [b["dados"] for b in botoes if b["acao"] == "disparos_pausar"])
        self.assertIn({"campanha_id": pausada}, [b["dados"] for b in botoes if b["acao"] == "disparos_retomar"])
        self.assertTrue(self.blocos_de("texto", "Por que está pausada"))
        self.assertEqual(len(self.blocos_de("kpis", "#")), 10)   # o corte continua: 2 vivas + 8 rascunhos
        self.assertIn("Mostrando 10 de 12", str(self.blocos_de("texto", "Campanhas")))

    def test_servico_nao_corta_ativa_nem_pausada(self):
        ids = self.contatos(1)
        ativa, pausada = self.campanha(ids, "ativa"), self.campanha(ids, "pausada", "pausada_pelo_dono")
        for _ in range(3):
            self.campanha(ids)
        con = banco.abrir(self.pasta)
        try:
            with mock.patch.object(disparos, "CAMPANHAS_MAX", 1):
                r = disparos.estado(None, con)
        finally:
            con.close()
        self.assertEqual([c["id"] for c in r["campanhas"]], [pausada, ativa])
        self.assertEqual((r["total_campanhas"], r["ultima_campanha"]), (5, 5))


class TesteSemRepetirContato(Disparos):
    def setUp(self):
        super().setUp()
        self.contatos(3, origem="feira")
        self.sql("gravar", "empresa", "Loja Teste")

    def criar(self, id_cliente, origem="feira"):
        return self.agir("disparos_criar", nome="Feira", modelo=MODELO, origem=origem, id_cliente=id_cliente)

    def test_segunda_campanha_do_mesmo_filtro_nao_pega_os_mesmos(self):
        self.assertTrue(self.criar("a1")["ok"])
        con = banco.abrir(self.pasta)
        try:
            novo = banco.salvar_contato(con, TELEFONES[3], "Dani", "feira", "consentimento")
        finally:
            con.close()
        r = self.agir("disparos_previa", modelo=MODELO, origem="feira")
        self.assertIn("1 contato(s) escolhido(s)", r["mensagem"])
        self.assertIn("3 já em outra campanha", r["mensagem"])
        self.assertTrue(self.criar("a2")["ok"])
        por_contato = self.sql("SELECT contato_id, COUNT(*) FROM campanha_contatos GROUP BY contato_id")
        self.assertEqual(por_contato, [(1, 1), (2, 1), (3, 1), (novo, 1)])
        r = self.criar("a3")
        self.assertFalse(r["ok"])
        self.assertIn("já em outra campanha", r["mensagem"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM campanhas")[0][0], 2)

    def test_quem_recebeu_de_campanha_concluida_fica_de_fora_e_quem_foi_negado_volta(self):
        self.assertTrue(self.criar("a1")["ok"])
        self.sql("UPDATE campanhas SET estado = 'concluida'")
        self.sql("UPDATE campanha_contatos SET estado = 'enviado' WHERE contato_id = 1")
        self.sql("UPDATE campanha_contatos SET estado = 'negado', motivo = 'fora_da_janela' WHERE contato_id > 1")
        self.assertTrue(self.criar("a2")["ok"])
        self.assertEqual(self.sql("SELECT contato_id FROM campanha_contatos WHERE campanha_id = 2 ORDER BY 1"),
                         [(2,), (3,)])


class TesteCriarIdempotente(Disparos):
    def setUp(self):
        super().setUp()
        self.contatos(2, origem="feira")
        self.sql("gravar", "empresa", "Loja Teste")

    def form(self):
        return [b for b in self.aba() if b["tipo"] == "formulario" and b["acao"] == "disparos_criar"][0]

    def test_mesmo_id_cliente_nao_cria_de_novo(self):
        fixos = self.form()["dados_fixos"]
        self.assertTrue(fixos.get("id_cliente"))
        primeira = self.agir("disparos_criar", nome="Feira", modelo=MODELO, **fixos)
        repetida = self.agir("disparos_criar", nome="Feira", modelo=MODELO, **fixos)
        self.assertTrue(primeira["ok"], primeira)
        self.assertTrue(repetida["ok"], repetida)
        self.assertIn("já tinha sido criada", repetida["mensagem"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM campanhas")[0][0], 1)
        self.assertNotEqual(self.form()["dados_fixos"], fixos)   # depois de criar, o formulário ganha id novo

    def test_sem_id_cliente_ou_id_ruim_e_erro(self):
        self.assertFalse(self.agir("disparos_criar", nome="Feira", modelo=MODELO)["ok"])
        self.assertFalse(self.agir("disparos_criar", nome="Feira", modelo=MODELO, id_cliente="a b;c")["ok"])
        self.assertEqual(self.sql("SELECT COUNT(*) FROM campanhas")[0][0], 0)


if __name__ == "__main__":
    unittest.main()
