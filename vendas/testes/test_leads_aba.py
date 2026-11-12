"""Aba Leads (blocos, filtros, importar colado) e o comando importar.py contra um serviço de teste vivo."""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, importar, leads, travas  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402
from testes.test_webhook_modo import PORTA_PAINEL, Base  # noqa: E402


class Aba(Base):
    def setUp(self):
        super().setUp()
        self.mod = carregar_modulo()
        self.ctx = {"raiz": self.projeto, "config": {"porta": PORTA_PAINEL}}
        con = banco.abrir(self.pasta)  # fica aberta: sem conexão WAL não há -shm e a tela lê "serviço parado"
        self.addCleanup(con.close)
        self.manter_vivo()
        banco.registrar_servico(con, self.app.porta, self.app.marca)

    def aba(self):
        return [a for a in self.mod.montar(self.ctx, base=self.base)["abas"] if a["id"] == "leads"][0]["blocos"]

    def agir(self, acao, **dados):
        return self.mod.agir(self.ctx, acao, dados, base=self.base)


class TesteAba(Aba):
    def test_acoes_registradas_e_aba_existe(self):
        for a in leads_acoes():
            self.assertIn(a, self.mod.INFO["acoes"])
        self.assertTrue(self.aba())

    def test_importar_colado_mostra_resumo_e_lista_mascarada(self):
        r = self.agir("leads_importar", texto="nome,telefone\n=Ana,+55 11 90000-0001\nBia,zz\nCaio,\n",
                      origem="feira", base_legal="consentimento")
        self.assertTrue(r["ok"], r)
        self.assertIn("Importados: 1", r["mensagem"])
        self.assertIn("Recusados: 2", r["mensagem"])
        self.assertIn("linha 3 (telefone inválido)", r["mensagem"])
        tabela = [b for b in self.aba() if b["tipo"] == "tabela"][0]
        self.assertEqual(tabela["linhas"][0]["nome"], "=Ana")
        self.assertEqual(tabela["linhas"][0]["telefone"], "****0001")
        self.assertNotIn("90000", json.dumps(self.aba()))

    def test_importar_sem_base_legal_ou_vazio_ou_grande_e_recusado(self):
        self.assertFalse(self.agir("leads_importar", texto="nome,telefone\nA,11900000001\n", origem="x")["ok"])
        self.assertFalse(self.agir("leads_importar", texto="  ", origem="x", base_legal="consentimento")["ok"])
        grande = "nome,telefone\n" + "a" * 26000
        r = self.agir("leads_importar", texto=grande, origem="x", base_legal="consentimento")
        self.assertFalse(r["ok"])
        self.assertIn("terminal", r["mensagem"])

    def test_formulario_traz_o_comando_exato_e_nao_o_token(self):
        form = [b for b in self.aba() if b["tipo"] == "formulario" and b["acao"] == "leads_importar"][0]
        cli = self.mod.cliente
        self.assertIn("%s -B %s --projeto %s arquivo.csv" % (cli.PYTHON, cli.citar(self.mod.leads.IMPORTAR),
                                                             cli.citar(self.projeto)), form["descricao"])
        self.assertNotIn(self.token, json.dumps(self.aba()))
        self.assertEqual({o["valor"] for o in [c for c in form["campos"] if c["id"] == "base_legal"][0]["opcoes"]},
                         set(leads.BASES_LEGAIS))

    def test_filtrar_pela_tela(self):
        self.agir("leads_importar", texto="nome,telefone,origem\nAna,11900000001,feira\nBia,11900000002,site\n",
                  base_legal="consentimento")
        self.assertTrue(self.agir("leads_filtrar", origem="site")["ok"])
        tabela = [b for b in self.aba() if b["tipo"] == "tabela"][0]
        self.assertEqual([x["nome"] for x in tabela["linhas"]], ["Bia"])
        self.assertFalse(self.agir("leads_filtrar", optout="talvez")["ok"])

    def test_servico_parado_a_aba_avisa(self):
        self.parar_batimento()
        con = banco.abrir(self.pasta)
        try:
            con.execute("DELETE FROM batimento")
        finally:
            con.close()
        self.assertEqual(self.aba()[0]["tipo"], "texto")


def leads_acoes():
    return ("leads_filtrar", "leads_importar")


class TesteComando(Aba):
    def setUp(self):
        super().setUp()
        travas.gravar_segredo(os.path.join(self.pasta, "token_envio"), self.token)
        self.arquivo = os.path.join(self.tmp, "lista.csv")

    def escrever(self, texto):
        with open(self.arquivo, "wb") as f:
            f.write(texto if isinstance(texto, bytes) else texto.encode("utf-8"))

    def rodar(self, *args):
        saida, erro = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(saida), contextlib.redirect_stderr(erro):
            try:
                codigo = importar.main(["--projeto", self.projeto, "--base", self.base] + list(args))
            except SystemExit as e:
                codigo = e.code
        return codigo, saida.getvalue(), erro.getvalue()

    def test_importa_pelo_servico_vivo(self):
        self.escrever("nome;telefone;origem\nAna;+55 11 90000-0001;feira\nBia;+55 11 90000-0002;\n")
        codigo, saida, erro = self.rodar(self.arquivo, "--base-legal", "cliente_existente")
        self.assertEqual(codigo, 0, erro)
        self.assertIn("Importados: 1", saida)
        self.assertIn("linha 3: sem origem", saida)
        self.assertNotIn("90000", saida + erro)
        con = banco.abrir(self.pasta)
        try:
            self.assertEqual(con.execute("SELECT nome, base_legal FROM contatos").fetchall()[0][:], ("Ana", "cliente_existente"))
        finally:
            con.close()

    def test_origem_e_base_legal_pela_linha_de_comando(self):
        self.escrever("nome,telefone\nAna,11900000001\n")
        codigo, saida, _ = self.rodar(self.arquivo, "--origem", "feira", "--base-legal", "outro",
                                      "--base-legal-texto", "parceiro")
        self.assertEqual(codigo, 0)
        con = banco.abrir(self.pasta)
        try:
            self.assertEqual(con.execute("SELECT origem, base_legal FROM contatos").fetchone()[:], ("feira", "outro: parceiro"))
        finally:
            con.close()

    def test_base_legal_obrigatoria_e_outro_pede_texto(self):
        self.escrever("nome,telefone\nAna,11900000001\n")
        self.assertNotEqual(self.rodar(self.arquivo, "--origem", "x")[0], 0)
        codigo, _, erro = self.rodar(self.arquivo, "--origem", "x", "--base-legal", "outro")
        self.assertEqual(codigo, 1)
        self.assertIn("texto", erro)

    def test_arquivo_acima_de_2mb_recusado(self):
        self.escrever(b"nome,telefone\n" + b"a" * leads.ARQUIVO_MAX)
        codigo, _, erro = self.rodar(self.arquivo, "--origem", "x", "--base-legal", "consentimento")
        self.assertEqual(codigo, 1)
        self.assertIn("2 MB", erro)

    def test_recusa_com_servico_parado(self):
        self.parar_batimento()
        con = banco.abrir(self.pasta)
        try:
            con.execute("DELETE FROM batimento")
        finally:
            con.close()
        self.escrever("nome,telefone\nAna,11900000001\n")
        codigo, _, erro = self.rodar(self.arquivo, "--origem", "x", "--base-legal", "consentimento")
        self.assertEqual(codigo, 1)
        self.assertIn("parado", erro)

    def test_sem_token_na_pasta_recusa(self):
        os.remove(os.path.join(self.pasta, "token_envio"))
        self.escrever("nome,telefone\nAna,11900000001\n")
        codigo, _, erro = self.rodar(self.arquivo, "--origem", "x", "--base-legal", "consentimento")
        self.assertEqual(codigo, 1)
        self.assertIn("token", erro)


class TesteCitar(unittest.TestCase):
    def test_windows_usa_python_e_aspas_duplas(self):
        cli = carregar_modulo().cliente
        self.assertEqual(cli.PYTHON, "python" if os.name == "nt" else "python3")
        with mock.patch.object(cli, "WINDOWS", True):
            self.assertEqual(cli.citar("C:\\Users\\Ana Maria\\p"), '"C:\\Users\\Ana Maria\\p"')
        with mock.patch.object(cli, "WINDOWS", False):
            self.assertEqual(cli.citar("/a b/c"), "'/a b/c'")
            self.assertEqual(cli.citar("/a/c"), "/a/c")


if __name__ == "__main__":
    unittest.main()
