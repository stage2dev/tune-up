"""Mídia recebida (M1): download depois do commit, guardado fora do projeto com 0600, tipo pelo conteúdo, tetos,
falha com motivo (a mensagem continua na conversa), retenção, teto de disco, migração e nenhuma transação de escrita
segurada durante o download (um envio do portão no meio passa)."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402
import stat  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import banco, conversas, midia, pasta, portao, recebimento  # noqa: E402
from servico.conectores import base  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402

INST = "loja"
LEAD = "5511900000001"
MB = 1024 * 1024
OGG = b"OggS\x00\x02" + b"\x00" * 58
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 40
HTML = b"<html><script>alert(1)</script></html>"
PDF = b"%PDF-1.4\n%fim\n"
CAMPOS = {"audio": "audioMessage", "imagem": "imageMessage", "documento": "documentMessage"}


def corpo(ident, tipo="audio", de=LEAD, grupo=False):
    jid = "1203630000000@g.us" if grupo else de + "@s.whatsapp.net"
    chave = {"remoteJid": jid, "fromMe": False, "id": ident}
    if grupo:
        chave["participant"] = de + "@s.whatsapp.net"
    return {"event": "messages.upsert", "instance": INST, "data": {
        "key": chave, "message": {CAMPOS[tipo]: {"mimetype": "x"}}, "messageTimestamp": int(time.time())}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.pasta = pasta.pasta_de_dados(self.projeto, base=os.path.join(self.tmp, "dados"))
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        banco.gravar_config(self.con, "instancia", INST)
        self.c = ConectorFalso()
        self.rec = recebimento.Recebimento(lambda: self.c)
        recebimento.registrar_gancho(None)
        self.addCleanup(midia.registrar_baixador, None)

    def abrir(self):
        return banco.abrir(self.pasta)

    def receber(self, c, segredo_ok=True):
        self.con.execute("BEGIN IMMEDIATE")
        try:
            depois = self.rec(self.con, INST, c, segredo_ok)
            self.con.execute("COMMIT")
        except BaseException:
            self.con.execute("ROLLBACK")
            raise
        if depois:
            depois(self.con)

    def chegou(self, ident, tipo="audio", conteudo=OGG, nome=None):
        """Lead manda a mídia; devolve o id da linha em midias (ainda pendente)."""
        if conteudo is not None:
            self.c.midias[ident] = (conteudo, "image/png" if tipo == "imagem" else "x", nome)
        self.receber(corpo(ident, tipo))
        return self.con.execute("SELECT d.id FROM midias d JOIN mensagens m ON m.id = d.mensagem_id "
                                "WHERE m.id_externo = ?", (ident,)).fetchone()[0]

    def baixar(self, midia_id):
        return midia.baixar(self.abrir, self.c, self.pasta, midia_id)

    def linha(self, midia_id):
        return self.con.execute("SELECT * FROM midias WHERE id = ?", (midia_id,)).fetchone()

    def arquivos(self):
        return [os.path.join(r, f) for r, _, fs in os.walk(os.path.join(self.pasta, "midia")) for f in fs]

    def conversa(self):
        cid = self.con.execute("SELECT id FROM conversas").fetchone()[0]
        return conversas.abrir(self.con, cid, {})["mensagens"]


class TesteDownload(Base):
    def test_audio_guardado_fora_do_projeto_com_0600_e_na_conversa(self):
        mid = self.chegou("A1")
        self.assertEqual(self.linha(mid)["estado"], "pendente")
        self.assertEqual(self.c.chamadas[-1][0], "traduzir_evento")   # nada baixado dentro do recebimento
        self.assertEqual(self.baixar(mid), "pronta")
        self.assertEqual(self.c.chamadas[-1], ("baixar_midia", (INST, {"id": "A1", "remoteJid": LEAD + "@s.whatsapp.net",
                                                                      "fromMe": False})))
        linha = self.linha(mid)
        caminho = midia.caminho_do_arquivo(self.pasta, linha["arquivo"])
        with open(caminho, "rb") as f:
            self.assertEqual(f.read(), OGG)
        self.assertFalse(caminho.startswith(self.projeto + os.sep))
        self.assertTrue(caminho.startswith(os.path.join(self.pasta, "midia") + os.sep))
        self.assertEqual(self.arquivos(), [caminho])   # nenhum temporário sobrou
        self.assertEqual((linha["mimetype"], linha["bytes"], len(linha["sha256"])), ("audio/ogg", len(OGG), 64))
        m = self.conversa()[0]
        self.assertEqual(m["midia"], {"id": mid, "tipo": "audio", "estado": "pronta", "motivo": None,
                                      "mimetype": "audio/ogg", "bytes": len(OGG), "duracao_s": m["midia"]["duracao_s"],
                                      "nome_arquivo": None})
        self.assertEqual(self.um("SELECT precisa_de_voce FROM conversas"), 1)   # regra antiga continua

    def um(self, sql):
        return self.con.execute(sql).fetchone()[0]

    @unittest.skipIf(os.name == "nt", "Windows não tem modos 0700/0600")
    def test_modos_0700_e_0600(self):
        mid = self.chegou("A2")
        self.baixar(mid)
        caminho = midia.caminho_do_arquivo(self.pasta, self.linha(mid)["arquivo"])
        self.assertEqual(stat.S_IMODE(os.stat(caminho).st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(caminho)).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.pasta, "midia")).st_mode), 0o700)

    def test_png_declarado_que_e_html_recusado_sem_arquivo(self):
        mid = self.chegou("I1", "imagem", HTML)
        self.assertEqual(self.baixar(mid), "falhou")
        self.assertEqual((self.linha(mid)["estado"], self.linha(mid)["motivo"]), ("falhou", "tipo_recusado"))
        self.assertEqual(self.arquivos(), [])

    def test_imagem_png_de_verdade_aceita(self):
        mid = self.chegou("I2", "imagem", PNG)
        self.assertEqual(self.baixar(mid), "pronta")
        self.assertEqual(self.linha(mid)["mimetype"], "image/png")

    def test_acima_do_teto_recusado_sem_escrever(self):
        mid = self.chegou("I3", "imagem", PNG + b"\x00" * (10 * MB))
        self.assertEqual(self.baixar(mid), "falhou")
        self.assertEqual(self.linha(mid)["motivo"], "grande_demais")
        self.assertEqual(self.arquivos(), [])
        self.c.midias["G1"] = base.MidiaGrandeDemais("teto")   # o conector também corta
        mid = self.chegou("G1", conteudo=None)
        self.assertEqual((self.baixar(mid), self.linha(mid)["motivo"]), ("falhou", "grande_demais"))

    def test_documento_vira_octet_stream_com_nome_limpo_e_pdf_reconhecido(self):
        mid = self.chegou("D1", "documento", b"PK\x03\x04qualquer", nome="../../etc/‮planilha.xlsx")
        self.baixar(mid)
        self.assertEqual((self.linha(mid)["mimetype"], self.linha(mid)["nome_arquivo"]),
                         ("application/octet-stream", "planilha.xlsx"))
        mid = self.chegou("D2", "documento", PDF, nome="proposta.pdf")
        self.baixar(mid)
        self.assertEqual(self.linha(mid)["mimetype"], "application/pdf")

    def test_expirada_vira_falhou_com_motivo_e_mensagem_continua(self):
        mid = self.chegou("X1", conteudo=None)   # o falso responde 400 "não achada"
        self.assertEqual(self.baixar(mid), "falhou")
        self.assertEqual((self.linha(mid)["estado"], self.linha(mid)["motivo"]), ("falhou", "expirada"))
        m = self.conversa()[0]
        self.assertEqual((m["tipo"], m["texto"], m["midia"]["estado"], m["midia"]["motivo"]),
                         ("audio", "[áudio]", "falhou", "expirada"))
        self.assertEqual(len([c for c in self.c.chamadas if c[0] == "baixar_midia"]), 1)   # sem laço

    def test_pedir_de_novo_so_de_falhou_e_um_por_vez(self):
        mid = self.chegou("X2", conteudo=None)
        self.baixar(mid)
        self.assertFalse(midia.pedir_de_novo(self.con, mid))   # sem trabalhador: volta a falhou
        self.assertEqual(self.linha(mid)["motivo"], "sem_baixador")
        midia.registrar_baixador(midia.Baixador(self.abrir, lambda: self.c, self.pasta))
        self.c.midias["X2"] = (OGG, "audio/ogg", None)
        self.assertTrue(midia.pedir_de_novo(self.con, mid))
        self.assertFalse(midia.pedir_de_novo(self.con, mid))   # clique repetido: já pendente
        self.assertEqual(self.baixar(mid), "pronta")
        self.assertFalse(midia.pedir_de_novo(self.con, mid))   # pronta não volta

    def test_grupo_e_webhook_sem_segredo_nao_baixam(self):
        self.receber(corpo("GR1", grupo=True))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM midias").fetchone()[0], 0)
        midia.registrar_baixador(midia.Baixador(self.abrir, lambda: self.c, self.pasta))
        self.receber(corpo("F1"), segredo_ok=False)
        linha = self.con.execute("SELECT estado, motivo FROM midias").fetchone()
        self.assertEqual(tuple(linha), ("falhou", "sem_segredo"))
        self.assertTrue(midia._baixador.fila.empty())

    def test_fila_cheia_vira_falhou_sem_esperar(self):
        midia.registrar_baixador(midia.Baixador(self.abrir, lambda: self.c, self.pasta, fila_max=1))
        um, dois = self.chegou("Q1"), self.chegou("Q2")
        self.assertEqual((self.linha(um)["estado"], self.linha(dois)["estado"]), ("pendente", "falhou"))
        self.assertEqual(self.linha(dois)["motivo"], "fila_cheia")

    def test_pendente_da_subida_anterior_vira_interrompida(self):
        mid = self.chegou("P1")
        self.assertEqual(midia.interrompidas(self.con), 1)
        self.assertEqual((self.linha(mid)["estado"], self.linha(mid)["motivo"]), ("falhou", "interrompida"))
        self.assertIsNone(self.baixar(mid))


class TesteSemTransacao(Base):
    def test_envio_do_portao_passa_durante_o_download(self):
        mid = self.chegou("T1")
        self.c.segurar_midia = threading.Event()
        self.addCleanup(self.c.segurar_midia.set)
        fio = threading.Thread(target=self.baixar, args=(mid,))
        fio.start()
        for _ in range(200):
            if any(c[0] == "baixar_midia" for c in self.c.chamadas):
                break
            time.sleep(0.01)
        outro = self.abrir()
        try:
            inicio = time.monotonic()
            r = portao.enviar_manual(outro, self.c, INST, LEAD, "oi", "tela-1")
            gasto = time.monotonic() - inicio
        finally:
            outro.close()
        self.assertEqual(r["estado"], "enviado")
        self.assertLess(gasto, 2.0)   # com escrita segurada esperaria o busy_timeout (5 s) e falharia
        self.assertEqual(self.linha(mid)["estado"], "pendente")   # o download ainda não acabou
        self.c.segurar_midia.set()
        fio.join(10)
        self.assertEqual(self.linha(mid)["estado"], "pronta")


class TesteRetencao(Base):
    def test_mais_de_30_dias_sai_e_a_linha_fica_expirada(self):
        velha, nova = self.chegou("R1"), self.chegou("R2")
        self.baixar(velha)
        self.baixar(nova)
        arquivo_velho = midia.caminho_do_arquivo(self.pasta, self.linha(velha)["arquivo"])
        antes = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=31)).isoformat(
            timespec="seconds")
        self.con.execute("UPDATE midias SET baixada_em = ? WHERE id = ?", (antes, velha))
        self.assertEqual(midia.purgar(self.con, self.pasta), 1)
        self.assertFalse(os.path.exists(arquivo_velho))
        self.assertEqual((self.linha(velha)["estado"], self.linha(velha)["motivo"]), ("expirada", "retencao"))
        self.assertEqual(self.linha(nova)["estado"], "pronta")
        self.assertEqual(len(self.conversa()), 2)   # as mensagens continuam
        banco.gravar_config(self.con, "midia_dias", "0")   # inválido: vale o padrão
        self.assertEqual(midia.purgar(self.con, self.pasta), 0)

    def test_teto_de_disco_tira_a_mais_antiga_primeiro(self):
        banco.gravar_config(self.con, "midia_teto_bytes", str(len(OGG) * 2 + 10))
        ids = [self.chegou("C%d" % i) for i in range(3)]
        for mid in ids:
            self.baixar(mid)
        self.assertEqual([self.linha(i)["estado"] for i in ids], ["expirada", "pronta", "pronta"])
        self.assertEqual(self.linha(ids[0])["motivo"], "espaco")
        self.assertEqual(len(self.arquivos()), 2)


class TesteMigracao(unittest.TestCase):
    def test_banco_da_versao_17_mantem_as_linhas(self):
        con = sqlite3.connect(":memory:", isolation_level=None)
        con.row_factory = sqlite3.Row
        for comandos in banco.MIGRACOES[:17]:
            for comando in comandos:
                con.execute(comando)
        con.execute("PRAGMA user_version = 17")
        con.execute("INSERT INTO contatos (telefone, criado_em) VALUES (?, 't')", (LEAD,))
        con.execute("INSERT INTO conversas (contato_id, criado_em) VALUES (1, 't')")
        con.execute("INSERT INTO mensagens (conversa_id, direcao, tipo, criado_em) VALUES (1, 'entrada', 'audio', 't')")
        for _ in range(2):
            self.assertEqual(banco.migrar(con), banco.VERSAO)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM mensagens").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM midias").fetchone()[0], 0)
        m = conversas.abrir(con, 1, {})["mensagens"][0]
        self.assertEqual((m["tipo"], m["midia"]), ("audio", None))   # mídia antiga: sem linha, sem download
        con.close()


if __name__ == "__main__":
    unittest.main()
