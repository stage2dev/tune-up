"""Importação de leads (servico/leads.py e rotas /leads): origem e base legal obrigatórias, BOM, ; e latin-1,
duplicado por variante do 9º dígito mesclado, opt-out e origem do contato que já existe intactos, limite de 2 MB
(413), injeção de fórmula guardada como texto, sem telefone em log, evento nem motivo de recusa."""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import http.client  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, leads, rotas  # noqa: E402
from testes.test_webhook_modo import Base  # noqa: E402

CAB = None


class Importa(Base):
    def csv(self, texto, query="origem=feira&base_legal=consentimento", token=True, tipo="text/csv"):
        cab = {"Host": "127.0.0.1:%d" % self.app.porta, "Content-Type": tipo}
        if token:
            cab[rotas.CAB_TOKEN] = self.token
        corpo = texto if isinstance(texto, bytes) else texto.encode("utf-8")
        con = http.client.HTTPConnection("127.0.0.1", self.app.porta, timeout=10)
        try:
            con.request("POST", "/leads/importar?" + query, body=corpo, headers=cab)
            r = con.getresponse()
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
        finally:
            con.close()

    def contatos(self):
        con = banco.abrir(self.pasta)
        try:
            return [dict(r) for r in con.execute("SELECT * FROM contatos ORDER BY id")]
        finally:
            con.close()


class TesteImportar(Importa):
    def test_linha_sem_origem_e_recusada_e_relatada(self):
        codigo, r = self.csv("nome,telefone,origem\nAna,+55 11 90000-0001,\nBia,+55 11 90000-0002,site\n",
                             query="base_legal=consentimento")
        self.assertEqual(codigo, 200)
        self.assertEqual((r["importados"], r["recusados"]), (1, 1))
        self.assertEqual(r["motivos"], [{"linha": 2, "motivo": "sem origem"}])
        self.assertEqual([c["nome"] for c in self.contatos()], ["Bia"])

    def test_origem_do_arquivo_vale_para_linha_sem_coluna(self):
        _, r = self.csv("nome,telefone\nAna,11900000001\n")
        self.assertEqual(r["importados"], 1)
        self.assertEqual(self.contatos()[0]["origem"], "feira")

    def test_base_legal_obrigatoria_e_da_lista(self):
        for query in ("origem=x", "origem=x&base_legal=qualquer", "origem=x&base_legal=outro"):
            codigo, r = self.csv("nome,telefone\nAna,11900000001\n", query=query)
            self.assertEqual(codigo, 400, query)
        self.assertEqual(self.contatos(), [])
        codigo, _ = self.csv("nome,telefone\nAna,11900000001\n", query="origem=x&base_legal=outro&base_legal_texto=parceiro")
        self.assertEqual(codigo, 200)
        self.assertEqual(self.contatos()[0]["base_legal"], "outro: parceiro")

    def test_bom_ponto_e_virgula_e_cabecalho_em_maiusculas(self):
        texto = "﻿NOME;Telefone;ORIGEM\nAna;+55 11 90000-0001;feira\n"
        _, r = self.csv(texto)
        self.assertEqual((r["importados"], r["recusados"]), (1, 0))
        self.assertEqual(self.contatos()[0]["nome"], "Ana")

    def test_latin1(self):
        _, r = self.csv("nome;telefone\nJoão;11900000001\n".encode("latin-1"))
        self.assertEqual(r["importados"], 1)
        self.assertEqual(self.contatos()[0]["nome"], "João")

    def test_telefone_invalido_relatado_com_a_linha_sem_o_numero(self):
        _, r = self.csv("nome,telefone\nAna,123\nBia,11900000002\nCaio,abc\n")
        self.assertEqual([m["linha"] for m in r["motivos"]], [2, 4])
        self.assertEqual((r["importados"], r["recusados"]), (1, 2))
        self.assertNotIn("123", json.dumps(r))

    def test_duplicado_por_variante_do_nono_digito_e_mesclado(self):
        _, r = self.csv("nome,telefone\nAna,+55 11 98888-0001\nAna de novo,+55 11 8888-0001\nOutra,5511988880001\n")
        self.assertEqual((r["importados"], r["mesclados"]), (1, 2))
        self.assertEqual(len(self.contatos()), 1)
        _, r2 = self.csv("nome,telefone\nX,1188880001\n")  # de novo, em outra importação
        self.assertEqual((r2["importados"], r2["mesclados"]), (0, 1))
        self.assertEqual(len(self.contatos()), 1)

    def test_existente_nao_muda_e_optout_fica(self):
        con = banco.abrir(self.pasta)
        try:
            banco.salvar_contato(con, "5511900000001", "Original", "indicacao", "cliente_existente")
            banco.marcar_optout(con, "5511900000001", "2026-01-01T00:00:00+00:00")
        finally:
            con.close()
        _, r = self.csv("nome,telefone,origem\nTroca,11900000001,outra\n", query="base_legal=consentimento")
        self.assertEqual((r["importados"], r["mesclados"]), (0, 1))
        c = self.contatos()[0]
        self.assertEqual((c["nome"], c["origem"], c["base_legal"], c["optout_em"]),
                         ("Original", "indicacao", "cliente_existente", "2026-01-01T00:00:00+00:00"))

    def test_formula_e_guardada_como_texto(self):
        _, r = self.csv('nome,telefone\n"=HYPERLINK(""http://x"")",11900000001\n+cmd,11900000002\n')
        self.assertEqual(r["importados"], 2)
        self.assertEqual([c["nome"] for c in self.contatos()], ['=HYPERLINK("http://x")', "+cmd"])

    def test_resumo_conta_tudo(self):
        _, r = self.csv("nome,telefone,origem\nA,11900000001,\nB,11900000002,x\nC,11900000002,x\nD,zz,x\n",
                        query="base_legal=consentimento")
        self.assertEqual((r["importados"], r["mesclados"], r["recusados"]), (1, 1, 2))

    def test_motivos_cortam_em_50(self):
        linhas = "".join("n%d,zz\n" % i for i in range(60))
        _, r = self.csv("nome,telefone\n" + linhas)
        self.assertEqual((r["recusados"], len(r["motivos"]), r["motivos_cortados"]), (60, 50, True))

    def test_arquivo_acima_de_2mb_e_413_e_nada_entra(self):
        grande = "nome,telefone\n" + "a" * (leads.ARQUIVO_MAX)
        codigo, _ = self.csv(grande)
        self.assertEqual(codigo, 413)
        self.assertEqual(self.contatos(), [])

    def test_token_e_tipo_obrigatorios(self):
        self.assertEqual(self.csv("nome,telefone\nA,11900000001\n", token=False)[0], 403)
        self.assertEqual(self.csv("nome,telefone\nA,11900000001\n", tipo="application/json")[0], 415)
        self.assertEqual(self.csv("sem,coluna\nA,B\n")[0], 400)
        self.assertEqual(self.contatos(), [])

    def test_sem_telefone_em_evento_nem_log(self):
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            self.csv("nome,telefone\nAna,+55 11 91234-5678\nRuim,99\n")
        con = banco.abrir(self.pasta)
        try:
            eventos = " ".join(r[0] or "" for r in con.execute("SELECT dados FROM eventos"))
        finally:
            con.close()
        for lugar in (saida.getvalue(), erro.getvalue(), eventos):
            self.assertNotIn("91234", lugar)
            self.assertNotIn("5678", lugar)
        self.assertIn("leads_importados", [r[0] for r in self.eventos_tipos()])

    def eventos_tipos(self):
        con = banco.abrir(self.pasta)
        try:
            return con.execute("SELECT tipo FROM eventos").fetchall()
        finally:
            con.close()

    def test_rota_json_do_painel_e_limite(self):
        cab = {rotas.CAB_TOKEN: self.token}
        codigo, bruto = self.pedir("POST", "/leads/importar-texto", cab, {
            "texto": "nome,telefone\nAna,11900000001\n", "origem": "x", "base_legal": "consentimento"})
        self.assertEqual((codigo, json.loads(bruto)["importados"]), (200, 1))
        self.assertEqual(self.pedir("POST", "/leads/importar-texto", {}, {"texto": "x"})[0], 403)


class TesteLista(Importa):
    def test_lista_mascara_filtra_e_conta(self):
        self.csv("nome,telefone,origem\nAna,+55 11 90000-0001,feira\nBia,+55 11 90000-0002,site\n"
                 "Caio,+55 11 90000-0003,feira\n")
        con = banco.abrir(self.pasta)
        try:
            banco.marcar_optout(con, "5511900000002")
            cid = banco.abrir_conversa(con, banco.buscar_contato(con, "5511900000001")["id"])
            con.execute("UPDATE conversas SET estado = 'quente' WHERE id = ?", (cid,))
        finally:
            con.close()
        cab = {rotas.CAB_TOKEN: self.token}
        pega = lambda q: json.loads(self.pedir("GET", "/leads" + q, cab)[1])  # noqa: E731
        tudo = pega("")
        self.assertEqual(tudo["contagens"], {"total": 3, "optout": 1, "com_conversa": 1, "frio": 0, "morno": 0,
                                             "quente": 1})
        self.assertEqual(sorted(x["telefone_mascarado"] for x in tudo["leads"]), ["****0001", "****0002", "****0003"])
        self.assertNotIn("90000", json.dumps(tudo))
        self.assertEqual([x["nome"] for x in pega("?origem=feira")["leads"]], ["Caio", "Ana"])
        self.assertEqual([x["nome"] for x in pega("?qualificacao=quente")["leads"]], ["Ana"])
        self.assertEqual([x["nome"] for x in pega("?optout=sim")["leads"]], ["Bia"])
        self.assertEqual(len(pega("?conversa=nao")["leads"]), 2)
        self.assertEqual(len(pega("?qualificacao=sem")["leads"]), 2)

    def test_filtro_guardado_vale_na_lista_e_invalido_e_recusado(self):
        self.csv("nome,telefone,origem\nAna,11900000001,feira\nBia,11900000002,site\n")
        cab = {rotas.CAB_TOKEN: self.token}
        self.assertEqual(self.pedir("POST", "/leads/filtro", cab, {"optout": "talvez"})[0], 400)
        self.assertEqual(self.pedir("POST", "/leads/filtro", cab, {"origem": "site"})[0], 200)
        r = json.loads(self.pedir("GET", "/leads", cab)[1])
        self.assertEqual([x["nome"] for x in r["leads"]], ["Bia"])


if __name__ == "__main__":
    unittest.main()
