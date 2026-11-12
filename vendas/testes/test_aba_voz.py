"""Aba Voz pelo módulo da tela e pelo serviço de verdade: blocos de cada estado (sem ffmpeg, sem chave, chave + voz de
catálogo, clonada sem e com consentimento), lista de vozes lenta ou fora do ar mantém a aba de pé, consentimento
gravado com data e texto, áudio de teste só para o número do dono (número no corpo da ação é ignorado), nenhuma
chave em bloco ou mensagem, falhas mostradas como erro."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, voz, voz_cliente  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.elevenlabs_falsa import ElevenLabsFalsa  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402
from testes.test_voz import CHAVE, DONO, OUTRO, SEM_FFMPEG  # noqa: E402
from testes.test_webhook_modo import PORTA_PAINEL, Base  # noqa: E402

VOZ = "VozCatalogo0001"
CLONADA = "VozClonada0001"
VOZES = {"voices": [{"voice_id": VOZ, "name": "Ana", "category": "premade"},
                    {"voice_id": CLONADA, "name": "Bruna", "category": "cloned"}, {"nome": "sem id"}]}
TEXTO = "Autorizo o uso da minha voz clonada nas vendas."


class AbaVoz(Base):
    def setUp(self):
        super().setUp()
        self.falsa = ElevenLabsFalsa()
        self.addCleanup(self.falsa.fechar)
        self.falsa.vozes = (200, VOZES)
        self.app.elevenlabs_url = self.falsa.url
        self.app.conector = ConectorFalso()
        self.mod = carregar_modulo()
        self.ctx = {"raiz": self.projeto, "config": {"porta": PORTA_PAINEL}}
        con = banco.abrir(self.pasta)  # fica aberta: sem conexão WAL não há -shm e a tela lê "serviço parado"
        self.addCleanup(con.close)
        self.manter_vivo()
        banco.registrar_servico(con, self.app.porta, self.app.marca)
        banco.gravar_config(con, "instancia", "loja")
        self.ffmpeg(SEM_FFMPEG)

        def converter(_ffmpeg, _entrada, saida):
            with open(saida, "wb") as f:
                f.write(b"OggS ogg falso")
        for alvo, valor in (("converter", converter),):
            p = mock.patch.object(voz_cliente, alvo, valor)
            p.start()
            self.addCleanup(p.stop)
        self.falsa.padrao = (200, b"ID3 mp3 falso")

    def ffmpeg(self, achado):
        p = mock.patch.object(voz_cliente, "achar_ffmpeg", return_value=achado)
        p.start()
        self.addCleanup(p.stop)

    def blocos(self):
        r = self.mod.montar(self.ctx, base=self.base)
        return [a for a in r["abas"] if a["id"] == "voz"][0]["blocos"]

    def texto(self):
        return json.dumps(self.blocos(), ensure_ascii=False)

    def form(self, acao):
        achados = [b for b in self.blocos() if b["tipo"] == "formulario" and b["acao"] == acao]
        return achados[0] if achados else None

    def kpis(self):
        return {i["rotulo"]: i for b in self.blocos() if b["tipo"] == "kpis" for i in b["itens"]}

    def agir(self, acao, **dados):
        return self.mod.agir(self.ctx, acao, dados, base=self.base)

    def configurar(self, voz_id=VOZ, clonada="nao", dono=DONO, chave=True):
        if chave:
            self.assertTrue(self.agir("voz_chave", chave=CHAVE)["ok"])
        r = self.agir("voz_config", voz_id=voz_id, clonada=clonada, teto_caracteres_dia="5000")
        self.assertTrue(r["ok"], r)
        if dono:
            self.assertTrue(self.agir("voz_dono", numero=dono, confirmar="sim")["ok"])

    def config(self, chave, padrao=None):
        con = banco.abrir(self.pasta)
        try:
            return banco.ler_config(con, chave, padrao)
        finally:
            con.close()


class TesteBlocos(AbaVoz):
    def test_sem_ffmpeg(self):
        self.ffmpeg(None)
        self.assertEqual(self.kpis()["ffmpeg"]["valor"], "não encontrado")
        self.assertIn("instale o ffmpeg", self.texto())

    def test_sem_chave_nao_pede_a_lista_e_mostra_campo_segredo(self):
        self.assertEqual(self.kpis()["Chave da ElevenLabs"]["valor"], "não configurada")
        campo = self.form("voz_chave")["campos"][0]
        self.assertEqual((campo["id"], campo["tipo"]), ("chave", "segredo"))
        self.assertNotIn("valor", campo)
        self.assertIsNone(self.form("voz_apagar_chave"))
        self.assertEqual(self.falsa.pedidos_get, [])
        self.assertEqual(self.form("voz_config")["campos"][0]["tipo"], "texto")

    def test_chave_e_voz_de_catalogo(self):
        self.configurar()
        k = self.kpis()
        self.assertEqual(k["Chave da ElevenLabs"]["valor"], "configurada (****%s)" % CHAVE[-4:])
        self.assertEqual(k["Voz"]["valor"], "%s (catálogo)" % VOZ)
        self.assertNotIn("Consentimento", k)
        self.assertIsNone(self.form("voz_consentimento"))
        campo = self.form("voz_config")["campos"][0]
        self.assertEqual((campo["tipo"], campo["valor"]), ("escolha", VOZ))
        self.assertEqual([o["rotulo"] for o in campo["opcoes"]], ["Ana (premade)", "Bruna (cloned)"])
        self.assertEqual(self.falsa.pedidos_get[0]["cabecalhos"].get("xi-api-key"), CHAVE)
        self.assertIsNotNone(self.form("voz_apagar_chave"))
        self.assertIn("é a padrão", self.texto())

    def test_clonada_sem_consentimento_fica_desligada_e_mostra_o_formulario(self):
        self.configurar(CLONADA, "sim")
        k = self.kpis()
        self.assertIn("faltando", k["Consentimento"]["valor"])
        self.assertIn("Voz clonada desligada", self.texto())
        campos = {c["id"]: c for c in self.form("voz_consentimento")["campos"]}
        self.assertEqual(set(campos), {"nome", "data", "texto", "confirmo"})
        self.assertEqual(campos["confirmo"]["valor"], "nao")
        self.assertIn("gerada por IA", self.texto())
        self.assertIn("política da ElevenLabs", self.texto())

    def test_clonada_com_consentimento_liga(self):
        self.configurar(CLONADA, "sim")
        r = self.agir("voz_consentimento", nome="Fulana de Teste", data="2026-01-02", texto=TEXTO, confirmo="sim")
        self.assertEqual(r, {"ok": True, "mensagem": "Consentimento de Fulana de Teste gravado."})
        self.assertEqual(self.kpis()["Consentimento"]["valor"], "Fulana de Teste, 2026-01-02")
        self.assertNotIn("Voz clonada desligada", self.texto())

    def test_consentimento_sem_confirmar_nao_grava_e_nao_liga(self):
        self.configurar(CLONADA, "sim")
        r = self.agir("voz_consentimento", nome="Fulana", data="2026-01-02", texto=TEXTO, confirmo="nao")
        self.assertFalse(r["ok"])
        con = banco.abrir(self.pasta)
        try:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM voz_consentimentos").fetchone()[0], 0)
            self.assertIsNone(voz.consentimento(con, CLONADA))
        finally:
            con.close()
        self.assertIn("faltando", self.kpis()["Consentimento"]["valor"])

    def test_consentimento_gravado_com_data_e_texto(self):
        self.configurar(CLONADA, "sim")
        self.agir("voz_consentimento", nome="Fulana de Teste", data="2026-01-02", texto=TEXTO, confirmo="sim")
        con = banco.abrir(self.pasta)
        try:
            linha = con.execute("SELECT voz_id, nome, data, texto FROM voz_consentimentos").fetchone()
        finally:
            con.close()
        self.assertEqual(tuple(linha), (CLONADA, "Fulana de Teste", "2026-01-02", TEXTO))

    def test_consentimento_invalido_do_servico_vira_erro(self):
        self.configurar(CLONADA, "sim")
        r = self.agir("voz_consentimento", nome="Fulana", data="02/01/2026", texto=TEXTO, confirmo="sim")
        self.assertFalse(r["ok"])
        self.assertIn("AAAA-MM-DD", r["mensagem"])


class TesteListaDeVozes(AbaVoz):
    def test_lista_lenta_mantem_a_aba_de_pe_com_voice_id_digitado(self):
        self.configurar()
        self.app.cache_vozes = None
        self.falsa.atraso_get = 1.0
        with mock.patch.object(voz_cliente, "TEMPO_VOZES_S", 0.2):
            blocos = self.blocos()
        titulos = [b.get("titulo") for b in blocos]
        self.assertIn("Lista de vozes", titulos)
        self.assertIn("Voz do atendimento", titulos)
        campo = [b for b in blocos if b.get("acao") == "voz_config"][0]["campos"][0]
        self.assertEqual((campo["tipo"], campo["valor"]), ("texto", VOZ))
        self.assertTrue([b for b in blocos if b.get("acao") == "voz_chave"])

    def test_lista_com_erro_mantem_a_aba(self):
        self.configurar()
        self.app.cache_vozes = None
        self.falsa.vozes = (401, {"detail": {"status": "invalid_api_key"}})
        texto = self.texto()
        self.assertIn("Não consegui a lista de vozes", texto)
        self.assertIn("invalid_api_key", texto)
        self.assertEqual(self.form("voz_config")["campos"][0]["tipo"], "texto")

    def test_lista_fica_10_minutos_em_cache(self):
        self.configurar()
        self.blocos()
        self.blocos()
        self.assertEqual(len(self.falsa.pedidos_get), 1)

    def test_valor_salvo_fora_da_lista_nao_some(self):
        self.configurar("OutraVoz00001", "sim")   # fora da lista, "não" é recusado (não dá para conferir)
        campo = self.form("voz_config")["campos"][0]
        self.assertEqual(campo["valor"], "OutraVoz00001")
        self.assertIn("fora da lista", campo["opcoes"][0]["rotulo"])


class TesteTeste(AbaVoz):
    def enviados(self):
        return [c[1][1] for c in self.app.conector.chamadas if c[0] == "enviar_audio"]

    def test_teste_vai_so_para_o_numero_do_dono(self):
        self.configurar()
        r = self.agir("voz_teste")
        self.assertEqual(r, {"ok": True, "mensagem": "Áudio de teste enviado para o seu número."})
        self.assertEqual(self.enviados(), [DONO])

    def test_numero_no_corpo_da_acao_e_ignorado(self):
        self.configurar()
        r = self.agir("voz_teste", numero=OUTRO, telefone=OUTRO, numero_dono=OUTRO)
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.enviados(), [DONO])
        self.assertEqual(self.config("numero_dono"), DONO)

    def test_sem_numero_do_dono_mostra_o_motivo_e_nada_sai(self):
        self.configurar(dono="")
        self.assertEqual(self.kpis()["Seu número (teste)"]["valor"], "não configurado")
        r = self.agir("voz_teste")
        self.assertFalse(r["ok"])
        self.assertIn("Salve o seu número", r["mensagem"])
        self.assertEqual((self.enviados(), self.falsa.pedidos), ([], []))

    def test_numero_do_dono_invalido_e_recusado(self):
        r = self.agir("voz_dono", numero="123", confirmar="sim")
        self.assertFalse(r["ok"])
        self.assertIn("Número do dono inválido", r["mensagem"])

    def test_botao_do_teste_e_o_pedido(self):
        f = self.form("voz_teste")
        self.assertEqual((f["botao"], f["campos"]), ("Enviar áudio de teste para o meu número", []))

    def test_clonada_sem_consentimento_o_teste_nao_gera_audio(self):
        self.configurar(CLONADA, "sim")
        r = self.agir("voz_teste")
        self.assertFalse(r["ok"])
        self.assertIn("consentimento", r["mensagem"])
        self.assertEqual((self.enviados(), self.falsa.pedidos), ([], []))

    def test_falha_da_elevenlabs_aparece_como_erro_sem_a_chave(self):
        self.configurar()
        self.falsa.fila.append((401, {"detail": {"status": "invalid_api_key", "message": CHAVE}}))
        r = self.agir("voz_teste")
        self.assertFalse(r["ok"])
        self.assertIn("recusou a chave", r["mensagem"])
        self.assertNotIn(CHAVE, r["mensagem"])
        self.assertEqual(self.enviados(), [])

    def test_teto_acabado_vira_erro(self):
        self.configurar()
        self.assertTrue(self.agir("voz_config", voz_id=VOZ, clonada="nao", teto_caracteres_dia="3")["ok"])
        r = self.agir("voz_teste")
        self.assertFalse(r["ok"])
        self.assertIn("teto de voz", r["mensagem"])
        self.assertEqual(self.falsa.pedidos, [])

    def test_servico_parado_vira_erro(self):
        ctx = {"raiz": os.path.join(self.tmp, "outro"), "config": {}}
        r = self.mod.agir(ctx, "voz_teste", {}, base=self.base)
        self.assertFalse(r["ok"])


class TesteSegredo(AbaVoz):
    def test_chave_nunca_aparece_em_bloco_ou_mensagem(self):
        saidas = [self.agir("voz_chave", chave=CHAVE)]
        self.configurar(chave=False)
        saidas += [self.agir("voz_teste"), self.agir("voz_chave", chave="  "), self.agir("voz_apagar_chave")]
        saidas.append(self.blocos())
        self.assertEqual(saidas[0], {"ok": True, "mensagem": "Chave salva (final ****%s)." % CHAVE[-4:]})
        self.assertNotIn(CHAVE, json.dumps(saidas, ensure_ascii=False))
        self.assertNotIn(self.pasta, json.dumps(saidas, ensure_ascii=False))

    def test_apagar_chave_pede_confirmacao_e_apaga(self):
        self.configurar()
        self.assertFalse(self.agir("voz_apagar_chave", confirmar="nao")["ok"])
        self.assertEqual(self.kpis()["Chave da ElevenLabs"]["valor"], "configurada (****%s)" % CHAVE[-4:])
        self.assertEqual(self.agir("voz_apagar_chave", confirmar="sim"), {"ok": True, "mensagem": "Chave apagada."})
        self.assertEqual(self.kpis()["Chave da ElevenLabs"]["valor"], "não configurada")

    def test_acoes_registradas_no_info(self):
        for a in ("voz_chave", "voz_apagar_chave", "voz_config", "voz_consentimento", "voz_teste"):
            self.assertIn(a, self.mod.INFO["acoes"])

    def test_servico_parado_mostra_aviso_na_aba(self):
        ctx = {"raiz": os.path.join(self.tmp, "outro"), "config": {}}
        r = self.mod.montar(ctx, base=self.base)
        aba = [a for a in r["abas"] if a["id"] == "voz"][0]["blocos"]
        self.assertEqual(aba[0]["titulo"], "Serviço parado")


if __name__ == "__main__":
    unittest.main()
