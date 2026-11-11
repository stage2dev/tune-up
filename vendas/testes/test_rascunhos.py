"""Modos da IA (servico/rascunhos.py): em 'rascunho' (padrão) nada chega ao conector sem aprovação; aprovar envia uma
vez com a origem rascunho_aprovado; aprovar duas vezes (também ao mesmo tempo) = 1 envio; descartar não envia;
conversa em 'automatico' responde com a origem ia; opt-out depois do rascunho = negado; rascunho de mais de 24 h
expira; rascunho novo troca o pendente; o banco do esquema 7 migra sem perder dado; a tela mostra os botões."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, ia, rascunhos  # noqa: E402
from testes.openai_falsa import resposta_texto  # noqa: E402
from testes.test_aba_conversas import MARIA, Conversas  # noqa: E402
from testes.test_atendente import LEAD, Base  # noqa: E402


class BaseRascunho(Base):
    def setUp(self):
        super().setUp()
        self.con.execute("DELETE FROM config WHERE chave = 'ia_modo_padrao'")   # volta ao padrão do produto
        self.app = types.SimpleNamespace(conector=self.c)

    def rascunho(self, ident="m1", resposta="Oi! Posso ajudar com o plano."):
        self.falsa.fila = [resposta_texto(resposta)]
        self.chegar(ident, "oi, quanto custa?")
        self.assertTrue(self.esperar(lambda: self.pendente() is not None))
        return self.pendente()

    def pendente(self):
        c = self.conversa()
        return None if c is None else rascunhos.pendente(self.con, c["id"])

    def estado(self, rid):
        return self.con.execute("SELECT estado FROM rascunhos WHERE id = ?", (rid,)).fetchone()["estado"]


class TesteRascunho(BaseRascunho):
    def test_em_rascunho_nada_chega_ao_conector(self):
        d = self.rascunho()
        time.sleep(self.ESPERA)
        self.assertEqual(d["texto"], "Oi! Posso ajudar com o plano.")
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.c.entregues, [])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios").fetchone()[0], 0)

    def test_aprovar_envia_uma_vez_com_origem_rascunho_aprovado(self):
        d = self.rascunho()
        codigo, r = rascunhos.aprovar(self.app, self.con, d["id"])
        self.assertEqual((codigo, r["estado"]), (200, "enviado"))
        self.assertEqual([(e["conteudo"]) for e in self.c.entregues], ["Oi! Posso ajudar com o plano."])
        envio = self.con.execute("SELECT origem, chave_dedupe FROM envios").fetchone()
        self.assertEqual((envio["origem"], envio["chave_dedupe"]), ("rascunho_aprovado", "rascunho_aprovado:%d"
                                                                    % d["id"]))
        self.assertEqual(self.estado(d["id"]), "aprovado")

    def test_aprovar_duas_vezes_envia_uma(self):
        d = self.rascunho()
        rascunhos.aprovar(self.app, self.con, d["id"])
        codigo, r = rascunhos.aprovar(self.app, self.con, d["id"])
        self.assertEqual(codigo, 200)
        self.assertEqual(r["estado"], "duplicado")
        self.assertEqual(self.c.envios(), 1)

    def test_aprovar_ao_mesmo_tempo_envia_uma(self):
        d = self.rascunho()
        res = []

        def clicar():
            con = banco.abrir(self.pasta)
            try:
                res.append(rascunhos.aprovar(self.app, con, d["id"]))
            finally:
                con.close()
        fios = [threading.Thread(target=clicar) for _ in range(4)]
        [f.start() for f in fios]
        [f.join(10) for f in fios]
        self.assertEqual(len(res), 4)
        self.assertEqual(self.c.envios(), 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios").fetchone()[0], 1)

    def test_editar_e_enviar_manda_o_texto_do_dono(self):
        d = self.rascunho()
        codigo, r = rascunhos.aprovar(self.app, self.con, d["id"], "Texto que o dono escreveu.")
        self.assertEqual((codigo, r["estado"]), (200, "enviado"))
        self.assertEqual([e["conteudo"] for e in self.c.entregues], ["Texto que o dono escreveu."])
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"], "Texto que o dono escreveu.")[1]["estado"], "duplicado")
        self.assertEqual(self.c.envios(), 1)

    def test_editar_com_texto_vazio_e_recusado_e_nada_sai(self):
        d = self.rascunho()
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"], "   ")[0], 400)
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.estado(d["id"]), "pendente")

    def test_descartar_nao_envia_e_nao_deixa_aprovar_depois(self):
        d = self.rascunho()
        self.assertEqual(rascunhos.descartar(self.con, d["id"])[0], 200)
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"])[0], 409)
        self.assertEqual(rascunhos.descartar(self.con, d["id"])[0], 409)
        self.assertEqual(self.c.envios(), 0)
        self.assertIsNone(self.pendente())

    def test_optout_depois_do_rascunho_e_negado_no_portao(self):
        d = self.rascunho()
        banco.marcar_optout(self.con, LEAD)
        codigo, r = rascunhos.aprovar(self.app, self.con, d["id"])
        self.assertEqual((codigo, r["estado"], r["motivo"]), (200, "negado", "optout"))
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.estado(d["id"]), "negado")

    def test_rascunho_com_mais_de_24h_nao_e_aprovavel(self):
        d = self.rascunho()
        velho = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)).isoformat()
        self.con.execute("UPDATE rascunhos SET criado_em = ? WHERE id = ?", (velho, d["id"]))
        self.assertTrue(self.pendente()["expirado"])
        codigo, r = rascunhos.aprovar(self.app, self.con, d["id"])
        self.assertEqual(codigo, 409)
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.estado(d["id"]), "expirado")

    def test_mensagem_nova_do_lead_troca_o_rascunho_pendente(self):
        d1 = self.rascunho("m1", "Primeira resposta.")
        self.falsa.fila = [resposta_texto("Segunda resposta.")]
        self.chegar("m2", "e o prazo?")
        self.assertTrue(self.esperar(lambda: self.pendente()["id"] != d1["id"]))
        self.assertEqual(self.pendente()["texto"], "Segunda resposta.")
        self.assertEqual(self.estado(d1["id"]), "substituido")
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d1["id"])[0], 409)
        self.assertEqual(self.c.envios(), 0)

    def test_texto_barrado_pelo_sanitizador_nao_vira_rascunho(self):
        self.falsa.fila = [resposta_texto("Use o código sk-abcdefghijklmnop1234 agora")]
        self.chegar("m1", "oi")
        self.assertTrue(self.esperar(lambda: self.conversa() and self.conversa()["precisa_de_voce"] == 1))
        self.assertIsNone(self.pendente())
        self.assertEqual(self.c.envios(), 0)


class TesteModos(BaseRascunho):
    def test_conversa_em_automatico_responde_com_origem_ia(self):
        self.rascunho("m1")
        c = self.conversa()
        self.assertTrue(rascunhos.definir_modo_ia(self.con, c["id"], "automatico"))
        self.assertEqual(rascunhos.modo_da_conversa(self.con, c["id"]), "automatico")
        self.falsa.fila = [resposta_texto("Agora vai direto.")]
        self.chegar("m2", "e o prazo?")
        self.assertTrue(self.esperar(lambda: self.c.envios() == 1))
        self.assertEqual(self.con.execute("SELECT origem FROM envios").fetchone()["origem"], "ia")
        self.assertEqual([e["conteudo"] for e in self.c.entregues], ["Agora vai direto."])

    def test_padrao_do_projeto_e_a_conversa_vale_mais(self):
        self.rascunho("m1")
        cid = self.conversa()["id"]
        self.assertEqual(rascunhos.modo_padrao(self.con), "rascunho")
        self.assertEqual(ia.executar(self.app_ia(), self.con, "POST", "/ia/modo", {}, {"modo": "automatico"})[0], 200)
        self.assertEqual(rascunhos.modo_da_conversa(self.con, cid), "automatico")
        rascunhos.definir_modo_ia(self.con, cid, "rascunho")
        self.assertEqual(rascunhos.modo_da_conversa(self.con, cid), "rascunho")   # a da conversa vence
        rascunhos.definir_modo_ia(self.con, cid, "padrao")
        self.assertEqual(rascunhos.modo_da_conversa(self.con, cid), "automatico")
        self.assertEqual(ia.executar(self.app_ia(), self.con, "POST", "/ia/modo", {}, {"modo": "x"})[0], 400)

    def app_ia(self):
        return types.SimpleNamespace(pasta_dados=self.pasta, raiz=None, openai_url=self.falsa.url)

    def test_rota_do_modo_valida_o_corpo(self):
        self.rascunho()
        cid = self.conversa()["id"]
        ok = rascunhos.executar(self.app, self.con, "POST", "/conversas/%d/modo-ia" % cid, {}, {"modo_ia": "automatico"})
        self.assertEqual(ok, (200, {"modo_ia": "automatico"}))
        self.assertEqual(rascunhos.executar(self.app, self.con, "POST", "/conversas/%d/modo-ia" % cid, {},
                                            {"modo_ia": "root"})[0], 400)
        self.assertEqual(rascunhos.executar(self.app, self.con, "POST", "/conversas/999/modo-ia", {},
                                            {"modo_ia": "rascunho"})[0], 404)


class TesteMigracao(unittest.TestCase):
    def test_banco_do_esquema_7_migra_sem_perder_dado(self):
        con = banco.sqlite3.connect(":memory:", isolation_level=None)
        con.row_factory = banco.sqlite3.Row
        for comandos in banco.MIGRACOES[:7]:
            for comando in comandos:
                con.execute(comando)
        con.execute("PRAGMA user_version = 7")
        con.execute("INSERT INTO contatos (telefone, criado_em) VALUES ('5511900000001', 'x')")
        con.execute("INSERT INTO conversas (contato_id, modo, criado_em) VALUES (1, 'humano', 'x')")
        con.execute("INSERT INTO mensagens (conversa_id, direcao, texto, criado_em) VALUES (1, 'entrada', 'oi', 'x')")
        self.assertEqual(banco.migrar(con), banco.VERSAO)
        self.assertEqual(banco.migrar(con), banco.VERSAO)   # de novo: nada muda
        c = con.execute("SELECT modo, modo_ia FROM conversas").fetchone()
        self.assertEqual((c["modo"], c["modo_ia"]), ("humano", None))
        self.assertEqual(con.execute("SELECT texto FROM mensagens").fetchone()["texto"], "oi")
        self.assertEqual(rascunhos.modo_da_conversa(con, 1), "rascunho")
        con.execute("INSERT INTO rascunhos (conversa_id, mensagem_id, texto, criado_em) VALUES (1, 1, 'a', 'x')")
        with self.assertRaises(banco.sqlite3.IntegrityError):   # só um pendente por conversa
            con.execute("INSERT INTO rascunhos (conversa_id, mensagem_id, texto, criado_em) VALUES (1, 1, 'b', 'x')")


class TesteTela(Conversas):
    def rascunho(self):
        mid = self.con.execute("SELECT id FROM mensagens WHERE conversa_id = ?", (self.maria,)).fetchone()["id"]
        r = rascunhos.guardar(self.con, self.maria, mid, "Claro, o plano custa R$ 99.")
        self.assertEqual(r["estado"], "rascunho")
        return r["rascunho_id"]

    def conversa_aberta(self):
        self.agir("abrir_conversa", conversa_id=self.maria)
        blocos = self.aba()
        return [b for b in blocos if b["tipo"] == "conversa" and b["id"] == "conversa_%d" % self.maria][0], blocos

    def test_rascunho_aparece_com_aprovar_editar_e_descartar(self):
        rid = self.rascunho()
        bloco, blocos = self.conversa_aberta()
        rotulos = [b["acao"] for b in bloco["botoes"]]
        self.assertIn("aprovar_rascunho", rotulos)
        self.assertIn("descartar_rascunho", rotulos)
        self.assertEqual(bloco["mensagens"][-1]["texto"], "Claro, o plano custa R$ 99.")
        self.assertIn("NÃO foi enviado", bloco["mensagens"][-1]["nota"])
        form = [b for b in blocos if b["tipo"] == "formulario" and b.get("id") == "editar_rascunho"][0]
        self.assertEqual((form["acao"], form["dados_fixos"], form["campos"][0]["valor"]),
                         ("editar_rascunho", {"rascunho_id": rid}, "Claro, o plano custa R$ 99."))
        self.assertEqual(self.falso.envios(), 0)

    def test_aprovar_pela_tela_envia_uma_vez_e_clique_repetido_nao_duplica(self):
        rid = self.rascunho()
        self.assertTrue(self.agir("aprovar_rascunho", rascunho_id=rid)["ok"])
        self.assertTrue(self.agir("aprovar_rascunho", rascunho_id=rid)["ok"])
        self.assertEqual([e["origem"] for e in self.envios()], ["rascunho_aprovado"])
        self.assertEqual(self.falso.envios(), 1)

    def test_editar_pela_tela_manda_o_texto_editado(self):
        rid = self.rascunho()
        self.assertTrue(self.agir("editar_rascunho", rascunho_id=rid, texto="Custa R$ 89 hoje.")["ok"])
        self.assertEqual([e["conteudo"] for e in self.falso.entregues], ["Custa R$ 89 hoje."])
        self.assertFalse(self.agir("editar_rascunho", rascunho_id=rid, texto="")["ok"])

    def test_descartar_pela_tela_nao_envia(self):
        rid = self.rascunho()
        self.assertTrue(self.agir("descartar_rascunho", rascunho_id=rid)["ok"])
        self.assertFalse(self.agir("aprovar_rascunho", rascunho_id=rid)["ok"])
        self.assertEqual(self.falso.envios(), 0)

    def test_pedidos_ruins_nao_chegam_ao_conector(self):
        self.assertFalse(self.agir("aprovar_rascunho", rascunho_id="abc")["ok"])
        self.assertFalse(self.agir("aprovar_rascunho", rascunho_id=99999)["ok"])
        self.assertEqual(self.falso.envios(), 0)

    def test_modo_por_conversa_e_padrao_na_aba_ia(self):
        self.assertTrue(self.agir("ia_automatico_conversa", conversa_id=self.maria)["ok"])
        bloco, _ = self.conversa_aberta()
        self.assertEqual(rascunhos.modo_da_conversa(self.con, self.maria), "automatico")
        self.assertIn("ia_rascunho_conversa", [b["acao"] for b in bloco["botoes"]])
        self.assertTrue(self.agir("ia_rascunho_conversa", conversa_id=self.maria)["ok"])
        self.assertTrue(self.agir("ia_modo", modo="automatico")["ok"])
        self.assertEqual(rascunhos.modo_padrao(self.con), "automatico")
        self.assertFalse(self.agir("ia_modo", modo="qualquer")["ok"])
        ia_aba = self.mod.montar(self.ctx, base=self.base)["abas"][2]["blocos"]
        form = [b for b in ia_aba if b.get("id") == "ia_modo"][0]
        self.assertEqual(form["campos"][0]["valor"], "automatico")


if __name__ == "__main__":
    unittest.main()
