"""Aba IA e rotas /ia: colar, trocar e apagar a chave (só 'configurada' + 4 últimos), arquivo 0600 na pasta de dados,
seletor de modelo pela lista da conta (lista falhou = nome digitado), teto diário, preço desconhecido avisado, token
obrigatório, e a varredura do C5: a chave colada não aparece em resposta de rota, bloco, mensagem, arquivo da raiz
do projeto nem em linha de log."""
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

from servico import banco, chave, rotas  # noqa: E402
from testes.openai_falsa import OpenAIFalsa, erro  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402
from testes.test_webhook_modo import PORTA_PAINEL, Base  # noqa: E402

CHAVE = "sk-test-" + "Q9w8E7r6T5y4U3i2O1p0" + "LMNO"
OUTRA = "sk-test-" + "Z1x2C3v4B5n6M7a8S9d0" + "RSTU"


class Aba(Base):
    def setUp(self):
        super().setUp()
        self.falsa = OpenAIFalsa()
        self.addCleanup(self.falsa.fechar)
        self.app.openai_url = self.falsa.url
        self.mod = carregar_modulo()
        self.ctx = {"raiz": self.projeto, "config": {"porta": PORTA_PAINEL}}
        con = banco.abrir(self.pasta)  # fica aberta: sem conexão WAL não há -shm e a tela lê "serviço parado"
        self.addCleanup(con.close)
        banco.bater(con)
        banco.registrar_servico(con, self.app.porta, self.app.marca)

    def aba(self):
        r = self.mod.montar(self.ctx, base=self.base)
        return [a for a in r["abas"] if a["id"] == "ia"][0]["blocos"]

    def form(self, blocos, acao):
        achados = [b for b in blocos if b["tipo"] == "formulario" and b["acao"] == acao]
        return achados[0] if achados else None

    def agir(self, acao, **dados):
        return self.mod.agir(self.ctx, acao, dados, base=self.base)

    def estado(self):
        codigo, bruto = self.pedir("GET", "/ia", {rotas.CAB_TOKEN: self.token})
        self.assertEqual(codigo, 200)
        return json.loads(bruto)


class TesteChave(Aba):
    def test_sem_chave_mostra_campo_segredo_e_nome_digitado(self):
        blocos = self.aba()
        self.assertIn("não configurada", json.dumps(blocos, ensure_ascii=False))
        campo = self.form(blocos, "ia_chave")["campos"][0]
        self.assertEqual((campo["id"], campo["tipo"]), ("chave", "segredo"))
        self.assertNotIn("valor", campo)
        modelo = self.form(blocos, "ia_config")["campos"][0]
        self.assertEqual((modelo["tipo"], modelo["valor"]), ("texto", "gpt-4o-mini"))
        self.assertIsNone(self.form(blocos, "ia_apagar_chave"))
        self.assertEqual(self.falsa.pedidos, [])

    def test_colar_chave_grava_0600_fora_do_projeto_e_mostra_4_ultimos(self):
        r = self.agir("ia_chave", chave=CHAVE)
        self.assertEqual(r, {"ok": True, "mensagem": "Chave salva (final ****LMNO)."})
        arquivo = chave.caminho(self.pasta)
        self.assertFalse(arquivo.startswith(self.projeto))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(arquivo).st_mode), 0o600)
        self.assertEqual(self.estado()["chave"], {"configurada": True, "final": "LMNO"})
        blocos = self.aba()
        self.assertIn("configurada (****LMNO)", json.dumps(blocos))
        modelo = self.form(blocos, "ia_config")["campos"][0]
        self.assertEqual(modelo["tipo"], "escolha")
        self.assertEqual([o["valor"] for o in modelo["opcoes"]], ["gpt-4.1", "gpt-4o-mini"])
        self.assertEqual(self.falsa.pedidos[-1]["caminho"], "/v1/models")
        self.assertEqual(self.falsa.pedidos[-1]["cab"]["Authorization"], "Bearer " + CHAVE)
        self.assertEqual(self.form(blocos, "ia_chave")["botao"], "Trocar chave")

    def test_trocar_chave(self):
        self.agir("ia_chave", chave=CHAVE)
        self.assertTrue(self.agir("ia_chave", chave=OUTRA)["ok"])
        self.assertEqual(chave.ler(self.pasta), OUTRA)
        self.assertEqual(self.estado()["chave"]["final"], "RSTU")

    def test_chave_estranha_recusada_sem_eco(self):
        r = self.agir("ia_chave", chave="sk bad key with spaces " + "x" * 20)
        self.assertFalse(r["ok"])
        self.assertNotIn("spaces", r["mensagem"])
        self.assertIsNone(chave.ler(self.pasta))

    def test_apagar_exige_confirmar(self):
        self.agir("ia_chave", chave=CHAVE)
        self.assertFalse(self.agir("ia_apagar_chave", confirmar="nao")["ok"])
        codigo, _ = self.pedir("POST", "/ia/chave/apagar", {rotas.CAB_TOKEN: self.token}, {"confirmar": "sim"})
        self.assertEqual(codigo, 400)
        self.assertTrue(chave.estado(self.pasta)["configurada"])
        self.assertEqual(self.agir("ia_apagar_chave", confirmar="sim"), {"ok": True, "mensagem": "Chave apagada."})
        self.assertFalse(os.path.exists(chave.caminho(self.pasta)))
        self.assertEqual(self.estado()["chave"], {"configurada": False, "final": None})

    def test_rotas_exigem_token(self):
        for metodo, caminho, corpo in (("GET", "/ia", None), ("GET", "/ia/modelos", None),
                                       ("POST", "/ia/chave", {"chave": CHAVE}),
                                       ("POST", "/ia/chave/apagar", {"confirmar": True}),
                                       ("POST", "/ia/config", {"modelo": "x", "teto_usd": 1})):
            codigo, _ = self.pedir(metodo, caminho, {rotas.CAB_TOKEN: "errado"}, corpo)
            self.assertEqual(codigo, 403, caminho)
        self.assertIsNone(chave.ler(self.pasta))


class TesteModeloETeto(Aba):
    def test_salvar_modelo_e_teto(self):
        self.assertEqual(self.estado()["teto_usd"], 2.0)
        r = self.agir("ia_config", modelo="gpt-4.1", teto_usd="3,50")
        self.assertEqual(r, {"ok": True, "mensagem": "Modelo gpt-4.1 e teto de US$ 3.50 salvos."})
        e = self.estado()
        self.assertEqual((e["modelo"], e["teto_usd"], e["preco_conhecido"]), ("gpt-4.1", 3.5, True))

    def test_teto_e_modelo_invalidos(self):
        for modelo, teto in (("gpt-4.1", "-1"), ("gpt-4.1", "abc"), ("gpt-4.1", "nan"), ("x y", "1"), ("", "1")):
            self.assertFalse(self.agir("ia_config", modelo=modelo, teto_usd=teto)["ok"], (modelo, teto))
        self.assertIsNone(self.estado()["modelo"])

    def test_modelo_sem_preco_avisado(self):
        self.agir("ia_config", modelo="modelo-novo", teto_usd="2")
        self.assertFalse(self.estado()["preco_conhecido"])
        self.assertIn("Preço do modelo desconhecido", json.dumps(self.aba(), ensure_ascii=False))

    def test_lista_falhou_oferece_nome_digitado_com_codigo(self):
        self.agir("ia_chave", chave=CHAVE)
        self.falsa.fila = [erro(401, "invalid_api_key")]
        blocos = self.aba()
        self.assertEqual(self.form(blocos, "ia_config")["campos"][0]["tipo"], "texto")
        texto = json.dumps(blocos, ensure_ascii=False)
        self.assertIn("invalid_api_key", texto)
        self.assertNotIn("Incorrect API key", texto)


class TesteSegredoC5(Aba):
    def test_chave_colada_nao_aparece_em_rota_bloco_arquivo_ou_log(self):
        saidas, log = [], io.StringIO()
        with contextlib.redirect_stderr(log), contextlib.redirect_stdout(log):
            saidas.append(self.agir("ia_chave", chave=CHAVE))
            saidas.append(self.mod.montar(self.ctx, base=self.base))
            saidas.append(self.agir("ia_config", modelo="gpt-4o-mini", teto_usd="2"))
            self.falsa.fila = [erro(401, "invalid_api_key", "Incorrect API key provided: " + CHAVE)]
            saidas.append(self.mod.montar(self.ctx, base=self.base))
            for metodo, caminho, corpo in (("GET", "/ia", None), ("GET", "/ia/modelos", None),
                                           ("GET", "/estado", None), ("GET", "/saude", None),
                                           ("POST", "/ia/chave", {"chave": CHAVE}),
                                           ("POST", "/ia/config", {"modelo": "gpt-4.1", "teto_usd": 1})):
                saidas.append(self.pedir(metodo, caminho, {rotas.CAB_TOKEN: self.token}, corpo))
            self.falsa.fila = [erro(500, "server_error", CHAVE), erro(500, "server_error", CHAVE)]
            saidas.append(self.pedir("GET", "/ia/modelos", {rotas.CAB_TOKEN: self.token}))
            saidas.append(self.agir("ia_apagar_chave", confirmar="sim"))
            saidas.append(self.mod.montar(self.ctx, base=self.base))
        tudo = json.dumps(saidas, ensure_ascii=False)
        self.assertGreater(len(tudo), 1000)
        self.assertIn("LMNO", tudo)  # a varredura viu as respostas (4 últimos aparecem)
        self.assertNotIn(CHAVE, tudo)
        self.assertNotIn(CHAVE[:-4], tudo)
        self.assertNotIn(CHAVE, log.getvalue())
        vistos = 0
        for pasta_atual, _, nomes in os.walk(self.projeto):
            for nome in nomes:
                vistos += 1
                with open(os.path.join(pasta_atual, nome), "rb") as f:
                    self.assertNotIn(CHAVE.encode("utf-8"), f.read(), nome)
        for nome in os.listdir(self.pasta):  # nem o banco nem os eventos guardam a chave
            if nome != chave.ARQUIVO and os.path.isfile(os.path.join(self.pasta, nome)):
                with open(os.path.join(self.pasta, nome), "rb") as f:
                    self.assertNotIn(CHAVE.encode("utf-8"), f.read(), nome)


if __name__ == "__main__":
    unittest.main()
