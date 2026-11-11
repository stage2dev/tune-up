"""Aba Voz, travas da voz clonada e do número do dono: a voz que a lista da conta marca como clonada (cloned ou
professional) fica clonada mesmo com "Não" no formulário (sem consentimento não liga e nada é gerado; com ele, o
aviso de IA é falado); o número do dono não muda pelo formulário da voz, só pela ação própria com confirmação, que
recusa o número de um contato (lead) e mostra só os 4 últimos dígitos."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import unittest  # noqa: E402

from servico import banco, voz  # noqa: E402
from testes.test_aba_voz import CLONADA, TEXTO, VOZ, AbaVoz  # noqa: E402
from testes.test_voz import CHAVE, DONO, OUTRO  # noqa: E402


class TesteClonadaPelaLista(AbaVoz):
    def enviados(self):
        return [c[1][1] for c in self.app.conector.chamadas if c[0] == "enviar_audio"]

    def test_voz_marcada_cloned_com_nao_fica_clonada_e_desligada(self):
        self.configurar(CLONADA, "nao")
        self.assertEqual(self.kpis()["Voz"]["valor"], "%s (clonada)" % CLONADA)
        self.assertIn("Voz clonada desligada", self.texto())
        r = self.agir("voz_teste")
        self.assertFalse(r["ok"])
        self.assertEqual((self.enviados(), self.falsa.pedidos), ([], []))
        self.assertEqual(self.config("voz_clonada"), "1")

    def test_voz_marcada_cloned_com_consentimento_fala_o_aviso(self):
        self.configurar(CLONADA, "nao")
        self.assertTrue(self.agir("voz_consentimento", nome="Fulana", data="2026-01-02", texto=TEXTO,
                                  confirmo="sim")["ok"])
        self.assertTrue(self.agir("voz_teste")["ok"])
        self.assertTrue(self.falsa.pedidos[0]["corpo"]["text"].startswith(voz.AVISO_IA))

    def test_voz_professional_tambem_e_clonada(self):
        self.falsa.vozes = (200, {"voices": [{"voice_id": "VozProfissional01", "name": "Cida",
                                              "category": "professional"}]})
        self.configurar("VozProfissional01", "nao")
        self.assertEqual(self.config("voz_clonada"), "1")

    def test_config_antiga_com_zero_respeita_a_lista_em_cache(self):
        self.configurar()
        con = banco.abrir(self.pasta)
        try:
            banco.gravar_config(con, "voz_id", CLONADA)   # gravado antes da trava, com voz_clonada = 0
        finally:
            con.close()
        self.assertFalse(self.agir("voz_teste")["ok"])
        self.assertEqual(self.falsa.pedidos, [])

    def test_formulario_ja_vem_com_sim_para_a_voz_clonada(self):
        self.configurar(CLONADA, "sim")
        campos = {c["id"]: c for c in self.form("voz_config")["campos"]}
        self.assertEqual(campos["clonada"]["valor"], "sim")

    def test_voz_de_catalogo_segue_catalogo(self):
        self.configurar(VOZ, "nao")
        self.assertEqual(self.config("voz_clonada"), "0")
        self.assertTrue(self.agir("voz_teste")["ok"])
        self.assertFalse(self.falsa.pedidos[0]["corpo"]["text"].startswith(voz.AVISO_IA))


class TesteNumeroDoDono(AbaVoz):
    def enviados(self):
        return [c[1][1] for c in self.app.conector.chamadas if c[0] == "enviar_audio"]

    def test_formulario_da_voz_nao_muda_o_numero_do_dono(self):
        self.configurar()
        r = self.agir("voz_config", voz_id=VOZ, clonada="nao", teto_caracteres_dia="5000", numero_dono=OUTRO)
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.config("numero_dono"), DONO)
        self.assertNotIn("numero_dono", [c["id"] for c in self.form("voz_config")["campos"]])

    def test_numero_de_lead_em_optout_e_recusado_e_o_teste_nao_vai_para_ele(self):
        self.configurar()
        con = banco.abrir(self.pasta)
        try:
            banco.marcar_optout(con, OUTRO)
        finally:
            con.close()
        r = self.agir("voz_dono", numero=OUTRO, confirmar="sim")
        self.assertFalse(r["ok"])
        self.assertIn("contato", r["mensagem"])
        self.assertEqual(self.config("numero_dono"), DONO)
        self.assertTrue(self.agir("voz_teste")["ok"])
        self.assertEqual(self.enviados(), [DONO])

    def test_numero_de_contato_sem_optout_tambem_e_recusado(self):
        con = banco.abrir(self.pasta)
        try:
            banco.salvar_contato(con, OUTRO)
        finally:
            con.close()
        self.assertFalse(self.agir("voz_dono", numero=OUTRO, confirmar="sim")["ok"])
        self.assertIsNone(self.config("numero_dono"))

    def test_trocar_o_numero_pede_confirmacao(self):
        r = self.agir("voz_dono", numero=DONO, confirmar="nao")
        self.assertFalse(r["ok"])
        self.assertIsNone(self.config("numero_dono"))

    def test_numero_salvo_aparece_so_com_os_4_ultimos(self):
        r = self.agir("voz_dono", numero=DONO, confirmar="sim")
        self.assertEqual(r, {"ok": True, "mensagem": "Seu número salvo (final %s)." % DONO[-4:]})
        self.assertEqual(self.kpis()["Seu número (teste)"]["valor"], "configurado (final %s)" % DONO[-4:])
        self.assertNotIn(DONO, self.texto())

    def test_numero_invalido_e_recusado(self):
        r = self.agir("voz_dono", numero="123", confirmar="sim")
        self.assertFalse(r["ok"])
        self.assertIn("inválido", r["mensagem"])

    def test_numero_do_dono_nao_ecoa_a_chave(self):
        self.agir("voz_chave", chave=CHAVE)
        r = self.agir("voz_dono", numero=DONO, confirmar="sim")
        self.assertNotIn(CHAVE, json.dumps(r))

    def test_acao_registrada_no_info(self):
        self.assertIn("voz_dono", self.mod.INFO["acoes"])


if __name__ == "__main__":
    unittest.main()
