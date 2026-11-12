"""responder_em_audio: falhas DEPOIS do áudio sair. Exceção depois de chamar o conector (o portão não fecha a linha,
o arquivo temporário não apaga) não vira texto de reserva: o áudio pode ter saído, então nada de mensagem duplicada.
Rascunho como áudio: o balão de links que falha depois do áudio não some (evento, 'precisa de você', estado parcial)
e aprovar de novo manda só os links, sem gerar outro áudio."""
import sqlite3
import sys

sys.dont_write_bytecode = True

import unittest  # noqa: E402
from unittest import mock  # noqa: E402

from servico import banco, portao, rascunhos, voz_cliente  # noqa: E402
from testes.test_audio_ia import LINK, Base  # noqa: E402


class TesteExcecaoDepoisDoAudio(Base):
    def precisa(self):
        return self.con.execute("SELECT precisa_de_voce FROM conversas WHERE id = ?",
                                (self.conversa_id(),)).fetchone()[0]

    def test_fechar_do_portao_falha_depois_do_conector_sem_texto_de_reserva(self):
        self.chegar("a1")
        self.chegar("t1", "e o preço?")
        self.responder_em_audio("O curso custa R$ 100.")
        original = portao._fechar

        def fechar(con, envio_id, estado, *a, **k):
            if con.execute("SELECT origem FROM envios WHERE id = ?", (envio_id,)).fetchone()[0] == "audio_ia":
                raise sqlite3.OperationalError("database is locked")
            return original(con, envio_id, estado, *a, **k)
        with mock.patch.object(portao, "_fechar", side_effect=fechar):
            r = self.rodar("t1")
        self.assertEqual(self.chamadas(), ["enviar_audio"], "o texto inteiro não pode sair depois do áudio")
        self.assertEqual([(x["origem"], x["estado"]) for x in self.envios()], [("audio_ia", "pendente")])
        self.assertEqual(r["estado"], "incerto", r)
        self.assertEqual(self.precisa(), 1)
        self.assertEqual(self.eventos("ia_audio_virou_texto"), [])

    def test_apagar_temporario_falha_depois_do_envio_sem_texto_de_reserva(self):
        self.chegar("t1", "manda áudio")
        self.responder_em_audio("O curso custa R$ 100.")

        def apagar(*caminhos):
            if len(caminhos) == 2:   # o finally do voz._gerar_e_enviar, depois do envio
                raise PermissionError("arquivo travado")
        with mock.patch.object(voz_cliente, "apagar", side_effect=apagar):
            r = self.rodar("t1")
        self.assertEqual(self.chamadas(), ["enviar_audio"])
        self.assertEqual([(x["origem"], x["estado"]) for x in self.envios()], [("audio_ia", "enviado")])
        self.assertEqual(r["estado"], "incerto", r)
        self.assertEqual(self.precisa(), 1)

    def test_excecao_antes_do_portao_ainda_vira_texto(self):
        self.chegar("t1", "manda áudio")
        self.responder_em_audio("O curso custa R$ 100.")
        with mock.patch.object(voz_cliente, "sintetizar", side_effect=RuntimeError("quebrou")):
            r = self.rodar("t1")
        self.assertEqual((r["estado"], r["audio_motivo"]), ("enviado", "erro_interno:RuntimeError"), r)
        self.assertEqual(self.chamadas(), ["enviar_texto"])


class TesteLinksDoRascunho(Base):
    def setUp(self):
        super().setUp()
        banco.gravar_config(self.con, "ia_modo_padrao", "rascunho")
        self.chegar("a1")
        self.chegar("t1", "e o preço?")
        self.responder_em_audio()
        self.rodar("t1")
        self.rid = rascunhos.pendente(self.con, self.conversa_id())["id"]

    def estado_rascunho(self):
        return self.con.execute("SELECT estado FROM rascunhos WHERE id = ?", (self.rid,)).fetchone()[0]

    def test_links_recusados_depois_do_audio_avisam_e_reaprovar_manda_os_links(self):
        original = self.c.enviar_audio

        def audio_e_depois_recusa(*a):
            ident = original(*a)
            self.c.modo_envio = "recusar"   # o WhatsApp passa a recusar: o balão de links não sai
            return ident
        with mock.patch.object(self.c, "enviar_audio", side_effect=audio_e_depois_recusa):
            codigo, res = rascunhos.aprovar(self.app, self.con, self.rid)
        self.assertEqual(codigo, 200)
        self.assertEqual((res["estado"], res["motivo"]), ("parcial", "rascunho_links_nao_sairam"), res)
        self.assertEqual(self.estado_rascunho(), "aprovado", "o áudio saiu: o rascunho não volta a pendente")
        self.assertEqual(self.eventos("rascunho_links_nao_sairam")[0]["rascunho_id"], self.rid)
        self.assertEqual(self.con.execute("SELECT precisa_de_voce FROM conversas WHERE id = ?",
                                          (self.conversa_id(),)).fetchone()[0], 1)
        self.c.modo_envio = "ok"
        codigo, res = rascunhos.aprovar(self.app, self.con, self.rid)   # de novo: só os links, mesma linha
        self.assertEqual((codigo, res["estado"]), (200, "enviado"), res)
        self.assertEqual([e["tipo"] for e in self.c.entregues], ["audio", "texto"])
        self.assertEqual(self.c.entregues[1]["conteudo"], LINK)
        self.assertEqual(len(self.eleven.pedidos), 1, "nenhum áudio novo é gerado")
        self.assertEqual([(x["origem"], x["estado"]) for x in self.envios()],
                         [("audio_ia", "enviado"), ("rascunho_aprovado", "enviado")])
        codigo, res = rascunhos.aprovar(self.app, self.con, self.rid)   # terceiro clique: nada sai
        self.assertEqual(res["estado"], "duplicado")
        self.assertEqual(len(self.c.entregues), 2)

    def test_queda_entre_audio_e_links_reaprovar_manda_so_os_links(self):
        with mock.patch.object(portao, "enviar_rascunho_aprovado", side_effect=RuntimeError("caiu")):
            with self.assertRaises(RuntimeError):
                rascunhos.aprovar(self.app, self.con, self.rid)
        self.assertEqual([e["tipo"] for e in self.c.entregues], ["audio"])
        codigo, res = rascunhos.aprovar(self.app, self.con, self.rid)
        self.assertEqual((codigo, res["estado"]), (200, "enviado"), res)
        self.assertEqual([e["tipo"] for e in self.c.entregues], ["audio", "texto"])
        self.assertEqual(self.c.entregues[1]["conteudo"], LINK)
        self.assertEqual(len(self.eleven.pedidos), 1)
        self.assertEqual(self.estado_rascunho(), "aprovado")


if __name__ == "__main__":
    unittest.main()
