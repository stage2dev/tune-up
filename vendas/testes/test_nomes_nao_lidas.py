"""Nome do perfil do WhatsApp, não lidas e tipo das mensagens: pushName do lead vira nome_whatsapp só sem nome do
CSV/dono (o de fromMe é do dono e é ignorado); não lidas contam entradas depois da última abertura (POST
/conversas/aberta zera); lista pela última atividade com prévia de texto e de áudio; conversa com `tipo`; migração
17 mantém as linhas; nenhum telefone ou nome no log."""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import io  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import banco, conversas  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from testes.test_recebimento import INST, LEAD, Base, corpo, jid  # noqa: E402

LEAD2 = "5511900000002"
LID = "998877665544332@lid"


def com_nome(c, nome):
    c["data"]["pushName"] = nome
    return c


class Nomes(Base):
    def contato(self, numero=LEAD):
        return self.um("SELECT * FROM contatos WHERE telefone = ?", numero)

    def test_lid_com_audio_e_pushname_guarda_o_nome_e_mostra_audio(self):
        # o caso do 1º teste real: remoteJid @lid, remoteJidAlt com o telefone, áudio, pushName
        c = corpo("A1", de=LID, mensagem={"audioMessage": {"seconds": 3}},
                  chave_extra={"remoteJidAlt": jid(LEAD), "addressingMode": "lid"})
        self.receber(com_nome(c, "Maria Teste"))
        self.assertIsNone(self.contato()["nome"])
        self.assertEqual(self.contato()["nome_whatsapp"], "Maria Teste")
        item = conversas.listar(self.con, {})["conversas"][0]
        self.assertEqual(item["nome_exibido"], "Maria Teste")
        self.assertEqual(item["ultima"], "[áudio]")
        self.assertEqual(item["ultima_tipo"], "audio")

    def test_nome_do_csv_vence_o_pushname(self):
        banco.salvar_contato(self.con, LEAD, nome="Cliente do CSV", origem="csv")
        self.receber(com_nome(corpo("A1"), "Apelido Zap"))
        self.assertEqual(self.contato()["nome"], "Cliente do CSV")
        self.assertIsNone(self.contato()["nome_whatsapp"])
        self.assertEqual(conversas.listar(self.con, {})["conversas"][0]["nome_exibido"], "Cliente do CSV")

    def test_pushname_de_fromme_e_do_dono_e_nao_vai_para_o_lead(self):
        self.receber(com_nome(corpo("F1", "oi, aqui é a loja", from_me=True), "Dono da Loja"))
        self.assertIsNone(self.contato()["nome_whatsapp"])
        ev = evolution.traduzir(com_nome(corpo("F2", from_me=True), "Dono da Loja"))[0]
        self.assertIsNone(ev["nome_perfil"])
        self.assertIsNone(conversas.listar(self.con, {})["conversas"][0]["nome_exibido"])

    def test_pushname_sem_controle_e_com_limite(self):
        self.receber(com_nome(corpo("A1"), "  Ana\x00\n\u202eX  " + "y" * 200))
        nome = self.contato()["nome_whatsapp"]
        self.assertTrue(nome.startswith("Ana X"))
        self.assertEqual(len(nome), banco.NOME_MAX)
        self.assertFalse(any(ord(ch) < 32 or ch == "\u202e" for ch in nome))

    def test_pushname_vazio_ou_nao_texto_nao_grava(self):
        self.receber(com_nome(corpo("A1"), "   "))
        self.receber(com_nome(corpo("A2"), 123))
        self.assertIsNone(self.contato()["nome_whatsapp"])

    def test_webhook_sem_segredo_nao_renomeia(self):
        self.con.execute("BEGIN IMMEDIATE")
        self.rec(self.con, INST, com_nome(corpo("A1"), "Forjado"), False)
        self.con.execute("COMMIT")
        self.assertIsNone(self.contato()["nome_whatsapp"])

    def test_pushname_novo_atualiza_nome_whatsapp(self):
        self.receber(com_nome(corpo("A1"), "Primeiro"))
        self.receber(com_nome(corpo("A2"), "Segundo"))
        self.assertEqual(self.contato()["nome_whatsapp"], "Segundo")

    def test_nenhum_telefone_ou_nome_no_log(self):
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            self.receber(com_nome(corpo("A1"), "Maria Teste"))
            self.receber(com_nome(corpo("L1", de=LID, mensagem={"audioMessage": {}}), "Sem Alternativa"))
            conversas.executar(None, self.con, "POST", "/conversas/aberta", {}, {"conversa_id": 1})
        log = saida.getvalue() + erro.getvalue()
        eventos = " ".join(r[0] or "" for r in self.con.execute("SELECT dados FROM eventos"))
        for proibido in (LEAD, LEAD[-8:], "Maria", "Sem Alternativa"):
            self.assertNotIn(proibido, log)
            self.assertNotIn(proibido, eventos)


class NaoLidas(Base):
    def abrir(self, cid):
        return conversas.executar(None, self.con, "POST", "/conversas/aberta", {}, {"conversa_id": cid})

    def item(self, numero=LEAD):
        lista = conversas.listar(self.con, {})
        return lista, next(i for i in lista["conversas"] if i["telefone_mascarado"].endswith(numero[-4:]))

    def test_conta_entradas_e_zera_ao_abrir(self):
        for i in range(3):
            self.receber(corpo("A%d" % i, "oi %d" % i))
        self.receber(corpo("F1", "resposta do dono", from_me=True))   # saída não conta
        self.receber(corpo("B1", "oi", de=LEAD2))
        lista, item = self.item()
        self.assertEqual(item["nao_lidas"], 3)
        self.assertEqual(lista["nao_lidas_total"], 4)
        self.assertEqual(lista["conversas_nao_lidas"], 2)
        self.assertEqual(self.abrir(item["id"]), (200, {"aberta": item["id"]}))
        lista, item = self.item()
        self.assertEqual(item["nao_lidas"], 0)
        self.assertEqual(lista["aberta"], item["id"])
        self.assertEqual((lista["nao_lidas_total"], lista["conversas_nao_lidas"]), (1, 1))
        self.receber(corpo("A9", "mais uma"))
        self.assertEqual(self.item()[1]["nao_lidas"], 1)

    def test_abrir_conversa_que_nao_existe_nao_muda_nada(self):
        self.receber(corpo("A1"))
        self.assertEqual(self.abrir(999)[0], 404)
        self.assertIsNone(conversas.aberta(self.con))
        self.assertEqual(self.item()[1]["nao_lidas"], 1)

    def test_ordem_pela_ultima_atividade_e_previa(self):
        agora = int(time.time())
        self.receber(corpo("A1", "x" * 200, ts=agora - 60))
        self.receber(corpo("B1", de=LEAD2, mensagem={"audioMessage": {}}, ts=agora - 30))
        lista = conversas.listar(self.con, {})["conversas"]
        self.assertTrue(lista[0]["telefone_mascarado"].endswith(LEAD2[-4:]))   # a mais recente primeiro
        self.assertEqual(lista[0]["ultima"], "[áudio]")
        self.assertEqual(len(lista[1]["ultima"]), conversas.PREVIA)
        self.assertTrue(lista[1]["ultima"].endswith("…"))
        self.receber(corpo("A2", "voltei"))   # nova atividade sobe a conversa
        lista = conversas.listar(self.con, {})["conversas"]
        self.assertTrue(lista[0]["telefone_mascarado"].endswith(LEAD[-4:]))
        self.assertEqual(lista[0]["ultima"], "voltei")
        self.assertRegex(lista[0]["quando"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")
        for chave in ("precisa_de_voce", "ia_pausada", "ia_desligada", "motivo_humano", "saiu", "modo", "nao_lidas"):
            self.assertIn(chave, lista[0])
        self.assertEqual(lista[0]["telefone"], LEAD)   # a tela do dono mostra o telefone formatado; o mascarado fica para logs

    def test_conversa_traz_o_tipo_e_as_ultimas_100(self):
        self.receber(corpo("I1", mensagem={"imageMessage": {"caption": "foto do carro"}}))
        self.receber(corpo("D1", mensagem={"documentMessage": {}}))
        for i in range(105):
            self.receber(corpo("T%03d" % i, "msg %d" % i))
        cid = self.item()[1]["id"]
        r = conversas.abrir(self.con, cid, {})
        self.assertEqual(len(r["mensagens"]), 100)
        self.assertEqual(r["mensagens"][-1]["texto"], "msg 104")
        self.assertEqual({m["tipo"] for m in r["mensagens"]}, {"texto"})
        r = conversas.abrir(self.con, cid, {"limite": ["107"]})
        self.assertEqual(len(r["mensagens"]), conversas.LIMITE_MAX)
        tudo = conversas.abrir(self.con, cid, {"limite": ["100"]})
        self.assertEqual(tudo["mensagens"][0]["tipo"], "texto")
        self.con.execute("DELETE FROM mensagens WHERE id_externo LIKE 'T%'")
        r = conversas.abrir(self.con, cid, {})
        self.assertEqual([(m["tipo"], m["texto"]) for m in r["mensagens"]],
                         [("imagem", "foto do carro"), ("documento", "[documento]")])


class Migracao17(unittest.TestCase):
    def test_banco_da_versao_16_mantem_as_linhas(self):
        con = sqlite3.connect(":memory:", isolation_level=None)
        con.row_factory = sqlite3.Row
        for comandos in banco.MIGRACOES[:16]:
            for comando in comandos:
                con.execute(comando)
        con.execute("PRAGMA user_version = 16")
        con.execute("INSERT INTO contatos (telefone, nome, criado_em) VALUES (?, 'Lead Antigo', 't')", (LEAD,))
        con.execute("INSERT INTO contatos (telefone, criado_em) VALUES (?, 't')", (LEAD2,))
        con.execute("INSERT INTO conversas (contato_id, criado_em) VALUES (1, 't'), (2, 't')")
        con.execute("INSERT INTO mensagens (conversa_id, direcao, texto, criado_em) VALUES (1, 'entrada', 'oi', 't'),"
                    " (2, 'entrada', 'olá', 't'), (2, 'saida', 'tchau', 't')")
        for _ in range(2):   # rodar de novo não muda nada
            self.assertEqual(banco.migrar(con), banco.VERSAO)
        self.assertEqual([tuple(r) for r in con.execute("SELECT telefone, nome, nome_whatsapp FROM contatos")],
                         [(LEAD, "Lead Antigo", None), (LEAD2, None, None)])
        self.assertEqual(con.execute("SELECT COUNT(*) FROM mensagens").fetchone()[0], 3)
        lista = conversas.listar(con, {})
        self.assertEqual(lista["nao_lidas_total"], 2)   # nunca aberta: toda entrada conta
        self.assertEqual({i["nome_exibido"] for i in lista["conversas"]}, {"Lead Antigo", None})
        con.close()


if __name__ == "__main__":
    unittest.main()
