"""Google Places opcional (E3), contra um servidor falso em 127.0.0.1: máscara de campos enviada, resultado desenhado
com a atribuição do Google, NADA do conteúdo de Places no banco nem na pasta de dados nem em log, Guardar grava só o
place_id, teto diário sem chamada ao Google, chave nunca em resposta e 403 com mensagem clara."""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import stat  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, places, rotas  # noqa: E402
from testes.openai_falsa import OpenAIFalsa  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402
from testes.test_webhook_modo import PORTA_PAINEL, Base  # noqa: E402

CHAVE = "AIza" + "SyTestePlaces0123456789abcdefghi"
MARCAS = ("NOME_MARCA_ZZ", "Rua Marca 123 ZZ", "(11) 90000-7777", "https://marca-zz.example.test")


def lugar(i, pid):
    return {"id": pid, "displayName": {"text": "%s %d" % (MARCAS[0], i), "languageCode": "pt-BR"},
            "formattedAddress": "%s, %d" % (MARCAS[1], i), "websiteUri": MARCAS[3] + "/%d" % i,
            "nationalPhoneNumber": MARCAS[2]}


def resposta(n=2):
    return 200, {"places": [lugar(i, "ChIJ_id%d" % i) for i in range(1, n + 1)]}


class Aba(Base):
    def setUp(self):
        super().setUp()
        self.falsa = OpenAIFalsa()   # só um servidor HTTP falso que registra e responde da fila
        self.addCleanup(self.falsa.fechar)
        self.app.places_url = self.falsa.url
        self.mod = carregar_modulo()
        self.ctx = {"raiz": self.projeto, "config": {"porta": PORTA_PAINEL}}
        con = banco.abrir(self.pasta)
        try:
            banco.bater(con)
            banco.registrar_servico(con, self.app.porta, self.app.marca)
        finally:
            con.close()

    def agir(self, acao, **dados):
        return self.mod.agir(self.ctx, acao, dados, base=self.base)

    def aba(self):
        r = self.mod.montar(self.ctx, base=self.base)
        return [a for a in r["abas"] if a["id"] == "buscador"][0]["blocos"]

    def salvar_chave(self):
        self.assertTrue(self.agir("places_chave", chave=CHAVE)["ok"])

    def buscar(self, nicho="clínica", cidade="Cidade Teste"):
        return self.agir("places_buscar", nicho=nicho, cidade=cidade)

    def tudo_do_banco(self):
        con = banco.abrir(self.pasta)
        try:
            saida = []
            for (nome,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall():
                saida += [tuple(l) for l in con.execute("SELECT * FROM %s" % nome).fetchall()]
            return json.dumps(saida, default=str, ensure_ascii=False)
        finally:
            con.close()

    def tudo_da_pasta(self):
        partes = []
        for raiz, _, nomes in os.walk(self.tmp):
            for n in nomes:
                with open(os.path.join(raiz, n), "rb") as f:
                    partes.append(f.read().decode("latin-1"))
        return "\n".join(partes)


class TesteBusca(Aba):
    def test_pedido_leva_mascara_de_campos_e_chave_so_no_cabecalho(self):
        self.salvar_chave()
        self.falsa.fila.append(resposta())
        self.assertTrue(self.buscar()["ok"])
        p = self.falsa.pedidos[0]
        p["cab"] = {k.lower(): v for k, v in p["cab"].items()}   # urllib muda a caixa dos nomes
        self.assertEqual((p["metodo"], p["caminho"]), ("POST", "/v1/places:searchText"))
        self.assertEqual(p["cab"]["x-goog-fieldmask"], "places.id,places.displayName,places.formattedAddress,"
                                                       "places.websiteUri,places.nationalPhoneNumber")
        self.assertEqual(p["cab"]["x-goog-api-key"], CHAVE)
        self.assertEqual(p["corpo"]["textQuery"], "clínica em Cidade Teste")

    def test_resultado_na_tela_com_atribuicao_e_botao_guardar(self):
        self.salvar_chave()
        self.falsa.fila.append(resposta())
        self.buscar()
        blocos = self.aba()
        texto = json.dumps(blocos, ensure_ascii=False)
        self.assertIn(MARCAS[0] + " 1", texto)
        self.assertIn("Google Maps", texto)
        guardar = [b for b in blocos if b.get("acao") == "places_guardar"]
        self.assertEqual([b["dados_fixos"]["place_id"] for b in guardar], ["ChIJ_id1", "ChIJ_id2"])

    def test_nada_de_places_no_banco_nem_nos_arquivos_nem_no_log(self):
        log = io.StringIO()
        with contextlib.redirect_stderr(log), contextlib.redirect_stdout(log):
            self.salvar_chave()
            self.falsa.fila.append(resposta())
            self.buscar()
            self.aba()
            self.agir("places_guardar", place_id="ChIJ_id1", nicho="clínica", cidade="Cidade Teste")
        banco_todo, pasta_toda = self.tudo_do_banco(), self.tudo_da_pasta()
        for marca in MARCAS:
            self.assertNotIn(marca, banco_todo)
            self.assertNotIn(marca, pasta_toda)
            self.assertNotIn(marca, log.getvalue())
        self.assertIn("ChIJ_id1", banco_todo)

    def test_guardar_grava_so_place_id_nicho_cidade(self):
        r = self.agir("places_guardar", place_id="ChIJ_id1", nicho="clínica", cidade="Cidade Teste",
                      nome="NOME_MARCA_ZZ", telefone="(11) 90000-7777")
        self.assertTrue(r["ok"])
        self.assertTrue(self.agir("places_guardar", place_id="ChIJ_id1", nicho="clínica", cidade="Cidade Teste")["ok"])
        con = banco.abrir(self.pasta)
        try:
            self.assertEqual([tuple(l) for l in con.execute("SELECT place_id, nicho, cidade FROM places_guardados")],
                             [("ChIJ_id1", "clínica", "Cidade Teste")])
            self.assertEqual([c[1] for c in con.execute("PRAGMA table_info(places_guardados)")],
                             ["place_id", "nicho", "cidade", "criado_em"])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM contatos").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM candidatos").fetchone()[0], 0)
        finally:
            con.close()
        self.assertFalse(self.agir("places_guardar", place_id="x y;", nicho="a", cidade="b")["ok"])

    def test_teto_atingido_nao_chama_o_google(self):
        self.salvar_chave()
        self.assertTrue(self.agir("places_teto", teto_dia="2")["ok"])
        for _ in range(2):
            self.falsa.fila.append(resposta())
            self.assertTrue(self.buscar()["ok"])
        r = self.buscar()
        self.assertFalse(r["ok"])
        self.assertIn("teto", r["mensagem"])
        self.assertEqual(len(self.falsa.pedidos), 2)

    def test_teto_padrao_50_e_zero_bloqueia(self):
        con = banco.abrir(self.pasta)
        try:
            self.assertEqual(places.teto(con), 50)
            banco.gravar_config(con, "places_teto_dia", "0")
            self.assertFalse(places.reservar(con))
        finally:
            con.close()

    def test_403_vira_mensagem_clara_sem_corpo_do_google(self):
        self.salvar_chave()
        self.falsa.fila.append((403, {"error": {"code": 403, "message": "SEGREDO_DO_CORPO " + CHAVE}}))
        r = self.buscar()
        self.assertFalse(r["ok"])
        self.assertIn("recusou a chave", r["mensagem"])
        self.assertNotIn("SEGREDO_DO_CORPO", r["mensagem"])
        self.assertNotIn(CHAVE, r["mensagem"])
        self.falsa.fila.append((429, {"error": {"code": 429}}))
        self.assertIn("limite de uso", self.buscar()["mensagem"])

    def test_sem_chave_nao_chama_o_google(self):
        r = self.buscar()
        self.assertFalse(r["ok"])
        self.assertEqual(self.falsa.pedidos, [])


class TesteChave(Aba):
    def test_chave_arquivo_0600_e_nunca_devolvida(self):
        log = io.StringIO()
        saidas = []
        with contextlib.redirect_stderr(log), contextlib.redirect_stdout(log):
            self.salvar_chave()
            self.falsa.fila.append(resposta())
            saidas.append(self.buscar())
            saidas.append(self.aba())
            codigo, bruto = self.pedir("GET", "/places", {rotas.CAB_TOKEN: self.token})
            self.assertEqual(codigo, 200)
            saidas.append(bruto)
            saidas.append(self.agir("places_chave", chave="curta"))
        tudo = json.dumps(saidas, ensure_ascii=False) + log.getvalue()
        self.assertNotIn(CHAVE, tudo)
        self.assertNotIn(CHAVE, self.tudo_do_banco())
        self.assertIn(CHAVE[-4:], json.loads(bruto)["chave"]["final"])
        arquivo = os.path.join(self.pasta, "places_chave")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(arquivo).st_mode), 0o600)
        projeto = [os.path.join(r, n) for r, _, ns in os.walk(self.projeto) for n in ns]
        for p in projeto:
            with open(p, "rb") as f:
                self.assertNotIn(CHAVE.encode(), f.read())

    def test_rota_exige_token(self):
        codigo, _ = self.pedir("GET", "/places")
        self.assertEqual(codigo, 403)

    def test_apagar_chave_pede_confirmacao(self):
        self.salvar_chave()
        self.assertFalse(self.agir("places_apagar_chave", confirmar="nao")["ok"])
        self.assertTrue(self.agir("places_apagar_chave", confirmar="sim")["ok"])
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "places_chave")))


if __name__ == "__main__":
    unittest.main()
