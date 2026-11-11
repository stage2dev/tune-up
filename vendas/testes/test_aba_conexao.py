"""Aba Conexão: montar com serviço parado e com o serviço + conector falso em cada estado (QR no bloco imagem,
conectado sem QR), criar sem confirmar número descartável grava false, ação desconhecida e serviço de outro projeto
recusados, nenhum segredo nos blocos, nunca logout/delete."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, rotas  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402
from testes.test_webhook_modo import PORTA_PAINEL, Base  # noqa: E402

QR = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg=="


class Aba(Base):
    def setUp(self):
        super().setUp()
        self.falso = ConectorFalso()
        self.app.conector = self.falso
        self.mod = carregar_modulo()
        self.ctx = {"raiz": self.projeto, "config": {"porta": PORTA_PAINEL}}
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        banco.bater(self.con)
        banco.registrar_servico(self.con, self.app.porta, self.app.marca)

    def blocos(self):
        r = self.mod.montar(self.ctx, base=self.base)
        self.assertEqual(r["avisos"], [])
        return r["abas"][0]["blocos"]

    def tipos(self, blocos, tipo):
        return [b for b in blocos if b["tipo"] == tipo]

    def criar(self, **dados):
        dados.setdefault("instancia", "loja")
        return self.mod.agir(self.ctx, "conectar_instancia", dados, base=self.base)


class TesteMontar(Aba):
    def test_servico_parado_mostra_comandos_sem_formulario_de_instancia(self):
        self.con.execute("UPDATE batimento SET em = '2000-01-01T00:00:00+00:00' WHERE id = 1")
        blocos = self.blocos()
        titulos = [b.get("titulo") for b in blocos]
        self.assertIn("Serviço parado", titulos)
        self.assertIn("Evolution não preparada", titulos)
        texto = json.dumps(blocos)
        self.assertIn("python3 -B", texto)
        self.assertIn("preparar --projeto", texto)
        self.assertEqual(self.tipos(blocos, "imagem"), [])
        self.assertEqual(self.tipos(blocos, "formulario"), [])
        self.assertEqual(self.falso.chamadas, [])

    def test_aguardando_qr_mostra_imagem_e_aviso(self):
        self.criar()
        self.falso.estado_atual, self.falso.qr_atual = "aguardando_qr", QR
        blocos = self.blocos()
        imagens = self.tipos(blocos, "imagem")
        self.assertEqual(len(imagens), 1)
        self.assertTrue(imagens[0]["data_uri"].startswith("data:image/png;base64,"))
        texto = json.dumps(blocos, ensure_ascii=False)
        for trecho in ("NÃO oficial", "banido", "Política do WhatsApp Business", "descartável"):
            self.assertIn(trecho, texto)
        form = [b for b in self.tipos(blocos, "formulario") if b["acao"] == "conectar_instancia"][0]
        campo = [c for c in form["campos"] if c["id"] == "numero_descartavel"][0]
        self.assertTrue(campo["obrigatorio"])
        self.assertIn("Aguardando QR", texto)

    def test_qr_nao_e_guardado_em_cache(self):
        self.criar()
        self.falso.estado_atual, self.falso.qr_atual = "aguardando_qr", QR
        self.blocos()
        self.falso.qr_atual = "data:image/png;base64,AAAA"
        self.assertEqual(self.tipos(self.blocos(), "imagem")[0]["data_uri"], "data:image/png;base64,AAAA")

    def test_conectado_sem_qr(self):
        self.criar()
        self.falso.estado_atual, self.falso.qr_atual = "conectado", QR
        self.falso.chamadas.clear()
        blocos = self.blocos()
        self.assertEqual(self.tipos(blocos, "imagem"), [])
        self.assertIn("Conectado", json.dumps(blocos))
        self.assertNotIn("qr", [n for n, _ in self.falso.chamadas], "conectado não pede QR")

    def test_desconectado_sem_instancia_so_formulario(self):
        blocos = self.blocos()
        self.assertEqual(self.tipos(blocos, "imagem"), [])
        self.assertIn("Desconectado", json.dumps(blocos))
        self.assertEqual(self.falso.chamadas, [])

    def test_contadores_do_webhook_seguem_na_aba(self):
        self.assertIn("Segredo do webhook", [b.get("titulo") for b in self.blocos()])

    def test_nenhum_segredo_nos_blocos(self):
        self.criar()
        self.falso.estado_atual, self.falso.qr_atual = "aguardando_qr", QR
        texto = json.dumps(self.blocos())
        self.assertNotIn(self.token, texto)
        self.assertNotIn(self.segredo, texto)


class TesteAgir(Aba):
    def test_criar_com_descartavel_grava_true_e_sem_grava_false(self):
        r = self.criar(numero_descartavel="sim")
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.config("instancia", ""), "loja")
        self.assertEqual(self.config("numero_descartavel"), "1")
        self.assertEqual(self.falso.chamadas[0], ("criar", ("loja",)))
        self.assertTrue(self.criar(numero_descartavel="nao")["ok"])
        self.assertEqual(self.config("numero_descartavel"), "0")
        self.assertTrue(self.criar()["ok"], "sem o campo ainda é permitido")
        self.assertEqual(self.config("numero_descartavel"), "0")

    def test_nome_invalido_recusado_sem_chamar_conector(self):
        for nome in ("", "a b", "../x", "x" * 65):
            self.assertFalse(self.criar(instancia=nome)["ok"])
        self.assertEqual(self.falso.chamadas, [])
        self.assertEqual(self.config("instancia", ""), "")

    def test_acao_desconhecida_recusada(self):
        for acao in ("logout", "apagar_instancia", "x"):
            self.assertEqual(self.mod.agir(self.ctx, acao, {}, base=self.base),
                             {"ok": False, "mensagem": "Ação desconhecida."})
        self.assertEqual(sorted(self.mod.INFO["acoes"]), sorted([
            "conectar_instancia", "modo_webhook", "abrir_conversa", "enviar_mensagem", "assumir_conversa",
            "devolver_ia", "liberar_saida", "reenviar_envio", "descartar_envio", "ia_chave", "ia_config",
            "ia_apagar_chave", "ia_modo", "aprovar_rascunho", "editar_rascunho", "descartar_rascunho",
            "ia_automatico_conversa", "ia_rascunho_conversa", "leads_filtrar", "leads_importar", "disparos_empresa", "disparos_previa", "disparos_criar",
            "disparos_ativar", "disparos_pausar", "disparos_retomar"]))
        self.assertEqual(self.falso.chamadas, [])

    def test_servico_de_outro_projeto_recusado(self):
        banco.gravar_config(self.con, "servico_marca", "outramarca0000000")
        r = self.criar(numero_descartavel="sim")
        self.assertFalse(r["ok"])
        self.assertEqual(self.falso.chamadas, [])

    def test_sem_conector_503_vira_mensagem(self):
        self.app.conector = None
        r = self.criar()
        self.assertFalse(r["ok"])
        self.assertIn("não configurado", r["mensagem"])

    def test_conector_fora_do_ar_nao_vaza_erro_cru(self):
        from servico.conectores import base

        def quebra(_):
            raise base.NaoEnviado("segredo-interno-123", 500)
        self.falso.criar = quebra
        r = self.criar()
        self.assertFalse(r["ok"])
        self.assertNotIn("segredo-interno-123", json.dumps(r))

    def test_criar_que_falha_nao_troca_a_instancia_gravada(self):
        from servico.conectores import base
        self.assertTrue(self.criar(numero_descartavel="sim")["ok"])

        def quebra(_):
            raise base.NaoEnviado("fora", 500)
        self.falso.criar = quebra
        self.assertFalse(self.criar(instancia="loja2", numero_descartavel="nao")["ok"])
        self.assertEqual(self.config("instancia", ""), "loja")
        self.assertEqual(self.config("numero_descartavel"), "1")

    def test_troca_recusada_com_a_antiga_conectada(self):
        self.assertTrue(self.criar(numero_descartavel="sim")["ok"])
        self.falso.estado = lambda nome: {"loja": "conectado"}.get(nome, "desconectado")
        r = self.criar(instancia="loja2", numero_descartavel="sim")
        self.assertFalse(r["ok"])
        self.assertIn("loja", r["mensagem"])
        self.assertEqual(self.config("instancia", ""), "loja")
        self.assertEqual([c for c in self.falso.chamadas if c[0] == "criar"], [("criar", ("loja",))])
        self.assertTrue(self.criar(instancia="loja", numero_descartavel="sim")["ok"], "mesma instância segue")

    def test_troca_permitida_com_a_antiga_desconectada(self):
        self.assertTrue(self.criar(numero_descartavel="sim")["ok"])
        self.assertTrue(self.criar(instancia="loja2", numero_descartavel="sim")["ok"])
        self.assertEqual(self.config("instancia", ""), "loja2")

    def test_rota_exige_token(self):
        self.assertEqual(self.pedir("GET", "/instancia")[0], 403)
        self.assertEqual(self.pedir("POST", "/instancia", {rotas.CAB_TOKEN: "errado"}, {"instancia": "x"})[0], 403)

    def test_nunca_logout_nem_delete(self):
        self.criar(numero_descartavel="sim")
        self.blocos()
        for nome, _ in self.falso.chamadas:
            self.assertIn(nome, ("criar", "estado", "qr"))


if __name__ == "__main__":
    unittest.main()
