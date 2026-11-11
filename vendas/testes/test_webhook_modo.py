"""Modo do segredo do webhook: "recusa" só depois de 20 válidos seguidos (um inválido zera), pela rota do serviço e
pela ação modo_webhook da tela; fumaça com a Evolution falsa entregando o webhook com o header do segredo."""
import sys

sys.dont_write_bytecode = True

import http.client  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import sqlite3  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402
from urllib.parse import urlsplit  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)

from servico import banco, pasta, rotas  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from testes.test_conector_evolution import EvolutionFalsa  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402

PORTA_PAINEL = 18787
PAINEL = "http://127.0.0.1:%d" % PORTA_PAINEL
CTX_PAINEL = {"config": {"porta": PORTA_PAINEL}}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta = pasta.pasta_de_dados(self.projeto, base=self.base)
        self.token, self.segredo = "t" * 43, "s" * 43
        self.app = rotas.App(self.pasta, 0, PAINEL, self.token, self.segredo)
        self.servidor = rotas.criar_servidor(self.app, 0)
        threading.Thread(target=self.servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)

    def manter_vivo(self):
        """Batimento fresco o teste inteiro, como o serviço faz (conexão própria, a cada 2 s): numa máquina lenta o
        teste passa dos VIVO_S e um batimento só viraria "serviço parado". self.parar_batimento() para antes de testar
        o serviço parado; a limpeza para e fecha a conexão antes de apagar a pasta (o Windows não apaga aberto)."""
        parar, pronto = threading.Event(), threading.Event()

        def bater():
            con = banco.abrir(self.pasta)
            try:
                banco.bater(con)
                pronto.set()
                while not parar.wait(2):
                    try:
                        banco.bater(con)
                    except sqlite3.Error:
                        pass  # banco ocupado nesta volta: a próxima tenta, como no serviço
            finally:
                con.close()

        fio = threading.Thread(target=bater, daemon=True)
        fio.start()

        def parar_batimento():
            parar.set()
            fio.join(30)
        self.parar_batimento = parar_batimento
        self.addCleanup(parar_batimento)
        self.assertTrue(pronto.wait(30), "o primeiro batimento não saiu")

    def pedir(self, metodo, caminho, cab=None, corpo=None, host=None):
        cab = dict(cab or {})
        cab["Host"] = host or "127.0.0.1:%d" % self.app.porta
        if corpo is not None:
            corpo = json.dumps(corpo).encode("utf-8")
            cab.setdefault("Content-Type", "application/json")
        con = http.client.HTTPConnection("127.0.0.1", self.app.porta, timeout=5)
        try:
            con.request(metodo, caminho, body=corpo, headers=cab)
            r = con.getresponse()
            return r.status, r.read().decode("utf-8")
        finally:
            con.close()

    def webhook(self, ok=True):
        cab = {rotas.CAB_SEGREDO: self.segredo if ok else "errado"}
        return self.pedir("POST", "/webhook/loja", cab, {"event": "messages.upsert"})[0]

    def trocar(self, modo, token=None):
        return self.pedir("POST", "/modo-webhook", {rotas.CAB_TOKEN: token or self.token}, {"modo": modo})

    def config(self, chave, padrao="0"):
        con = banco.abrir(self.pasta)
        try:
            return banco.ler_config(con, chave, padrao)
        finally:
            con.close()


class TesteModoWebhook(Base):
    def test_recusa_negada_antes_de_20_validos(self):
        for _ in range(rotas.VALIDOS_PARA_RECUSA - 1):
            self.assertEqual(self.webhook(), 200)
        codigo, bruto = self.trocar(rotas.MODO_RECUSA)
        self.assertEqual(codigo, 409)
        self.assertIn("Faltam 1", bruto)
        self.assertEqual(self.config("webhook_modo", rotas.MODO_REGISTRA), rotas.MODO_REGISTRA)
        self.assertEqual(self.webhook(ok=False), 200, "ainda registra e conta")

    def test_recusa_liberada_depois_de_20_validos(self):
        for _ in range(rotas.VALIDOS_PARA_RECUSA):
            self.webhook()
        codigo, _ = self.trocar(rotas.MODO_RECUSA)
        self.assertEqual(codigo, 200)
        self.assertEqual(self.config("webhook_modo"), rotas.MODO_RECUSA)
        self.assertEqual(self.webhook(ok=False), 401)
        self.assertEqual(self.webhook(), 200)
        self.assertEqual(self.trocar(rotas.MODO_REGISTRA)[0], 200, "voltar para registra é sempre livre")
        self.assertEqual(self.webhook(ok=False), 200)

    def test_um_invalido_zera_a_contagem(self):
        for _ in range(rotas.VALIDOS_PARA_RECUSA):
            self.webhook()
        self.assertEqual(self.webhook(ok=False), 200)
        self.assertEqual(self.config("webhook_validos_seguidos"), "0")
        self.assertEqual(self.config("webhook_invalidos"), "1")
        self.assertEqual(self.trocar(rotas.MODO_RECUSA)[0], 409)
        self.assertEqual(self.config("webhook_modo", rotas.MODO_REGISTRA), rotas.MODO_REGISTRA)

    def test_troca_exige_token_e_modo_conhecido(self):
        for _ in range(rotas.VALIDOS_PARA_RECUSA):
            self.webhook()
        self.assertEqual(self.trocar(rotas.MODO_RECUSA, token="x" * 43)[0], 403)
        self.assertEqual(self.pedir("POST", "/modo-webhook", {}, {"modo": rotas.MODO_RECUSA})[0], 403)
        self.assertEqual(self.trocar("aberto")[0], 400)
        self.assertEqual(self.config("webhook_modo", rotas.MODO_REGISTRA), rotas.MODO_REGISTRA)
        codigo, _ = self.pedir("POST", "/modo-webhook", {rotas.CAB_TOKEN: self.token}, {"modo": rotas.MODO_RECUSA},
                               host="host.docker.internal:%d" % self.app.porta)
        self.assertEqual(codigo, 421, "host do Docker só vale na rota do webhook")

    def test_fumaca_evolution_falsa_entrega_com_o_header(self):
        falsa = EvolutionFalsa()
        self.addCleanup(falsa.fechar)
        falsa.srv.respostas[("POST", "/instance/create")] = (201, {"instance": {"instanceName": "loja"}})
        conector = evolution.Evolution(falsa.url, "chave-de-teste", "http://%s:%d" % (rotas.HOST_DOCKER,
                                                                                      self.app.porta),
                                       self.segredo, tempo_limite=2)
        conector.criar("loja")
        gancho = falsa.srv.pedidos[0]["corpo"]["webhook"]
        url = urlsplit(gancho["url"])
        self.assertEqual(url.hostname, "host.docker.internal")
        # a Evolution entrega no endereço registrado, com os headers registrados (aqui o Docker vira 127.0.0.1)
        codigo, _ = self.pedir("POST", url.path, gancho["headers"], {"event": "messages.upsert", "instance": "loja"},
                               host=url.netloc)
        self.assertEqual(codigo, 200)
        self.assertEqual(self.config("webhook_validos"), "1")
        self.assertEqual(self.config("webhook_validos_seguidos"), "1")
        con = banco.abrir(self.pasta)
        try:
            dados = json.loads(con.execute("SELECT dados FROM eventos ORDER BY id DESC").fetchone()["dados"])
        finally:
            con.close()
        self.assertTrue(dados["segredo_ok"])
        self.assertEqual(dados["instancia"], "loja")
        codigo, _ = self.pedir("POST", url.path, {}, {"event": "messages.upsert"}, host=url.netloc)
        self.assertEqual(codigo, 200)
        self.assertEqual(self.config("webhook_invalidos"), "1", "sem o header = inválido")


class TesteTelaModoWebhook(Base):
    """A ação modo_webhook da tela passa pelo serviço (token pela origem do painel) e nunca devolve o token."""

    def setUp(self):
        super().setUp()
        self.mod = carregar_modulo()
        self.ctx = {"raiz": self.projeto, "config": {"porta": PORTA_PAINEL}}
        self.con = banco.abrir(self.pasta)  # conexão aberta = -shm existe, como com o serviço no ar
        self.addCleanup(self.con.close)
        self.manter_vivo()
        banco.registrar_servico(self.con, self.app.porta, self.app.marca)

    def agir(self, modo, ctx=None):
        r = self.mod.agir(ctx or self.ctx, "modo_webhook", {"modo": modo}, base=self.base)
        self.assertNotIn(self.token, json.dumps(r))
        return r

    def test_agir_respeita_os_20_validos(self):
        self.assertIn("modo_webhook", self.mod.INFO["acoes"])
        r = self.agir(rotas.MODO_RECUSA)
        self.assertFalse(r["ok"])
        self.assertIn("Faltam 20", r["mensagem"])
        for _ in range(rotas.VALIDOS_PARA_RECUSA):
            self.webhook()
        self.assertTrue(self.agir(rotas.MODO_RECUSA)["ok"])
        self.assertTrue(self.agir(rotas.MODO_RECUSA)["ok"], "repetir é idempotente")
        self.assertEqual(self.config("webhook_modo"), rotas.MODO_RECUSA)
        self.assertFalse(self.agir("qualquer")["ok"])

    def test_agir_com_outro_painel_ou_servico_parado(self):
        r = self.agir(rotas.MODO_REGISTRA, ctx={"raiz": self.projeto, "config": {"porta": 18788}})
        self.assertFalse(r["ok"])
        self.assertIn("403", r["mensagem"])
        livre = socket.socket()
        livre.bind(("127.0.0.1", 0))
        porta = livre.getsockname()[1]
        livre.close()
        banco.registrar_servico(self.con, porta, self.app.marca)
        r = self.agir(rotas.MODO_REGISTRA)
        self.assertEqual(r, {"ok": False, "mensagem": "O serviço de Vendas não respondeu. Ligue-o e tente de novo."})

    def test_agir_nunca_mexe_no_servico_de_outro_projeto(self):
        outro = os.path.join(self.tmp, "outro")
        os.makedirs(outro)
        app2 = rotas.App(pasta.pasta_de_dados(outro, base=self.base), 0, PAINEL, "u" * 43, "v" * 43)
        srv2 = rotas.criar_servidor(app2, 0)
        threading.Thread(target=srv2.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(srv2.server_close)
        self.addCleanup(srv2.shutdown)
        con2 = banco.abrir(app2.pasta_dados)
        self.addCleanup(con2.close)
        for _ in range(rotas.VALIDOS_PARA_RECUSA):  # o outro projeto já pode recusar
            banco.somar_config(con2, "webhook_validos_seguidos")
        # o banco DESTE projeto aponta para a porta onde agora responde o serviço do outro projeto
        banco.registrar_servico(self.con, app2.porta, self.app.marca)
        r = self.agir(rotas.MODO_RECUSA)
        self.assertFalse(r["ok"])
        self.assertIn("OUTRO projeto", r["mensagem"])
        self.assertEqual(banco.ler_config(con2, "webhook_modo", rotas.MODO_REGISTRA), rotas.MODO_REGISTRA)

    def test_agir_recusa_batimento_velho_ou_porta_sem_registro(self):
        self.parar_batimento()
        self.con.execute("UPDATE batimento SET em = '2000-01-01T00:00:00+00:00' WHERE id = 1")
        r = self.agir(rotas.MODO_REGISTRA)
        self.assertFalse(r["ok"])
        self.assertIn("parado", r["mensagem"])
        banco.bater(self.con)
        self.con.execute("DELETE FROM config WHERE chave = 'servico_porta'")
        r = self.agir(rotas.MODO_REGISTRA)
        self.assertFalse(r["ok"])
        self.assertIn("não registrou a porta", r["mensagem"])
        self.assertFalse(self.agir(rotas.MODO_REGISTRA, ctx=CTX_PAINEL)["ok"], "sem raiz = recusa")

    def test_tela_mostra_contadores_e_a_troca(self):
        for ok in (True, True, False, True):
            self.webhook(ok)
        tela = self.mod.montar({"raiz": self.projeto, "config": {"porta": PORTA_PAINEL}}, base=self.base)
        blocos = tela["abas"][0]["blocos"]
        i = [b.get("titulo") for b in blocos].index("Avançado: segurança do recebimento")
        self.assertEqual(len(blocos), i + 3, "o bloco avançado fica no FIM da aba")
        kpis = {it["rotulo"]: it["valor"] for it in blocos[i + 1]["itens"]}
        self.assertEqual(kpis, {"Jeito atual": "Só contar (recomendado)", "Com senha certa": 3, "Com senha errada": 1,
                                "Certas em sequência": 1})
        self.assertEqual(blocos[i + 2]["tipo"], "formulario")
        self.assertEqual(blocos[i + 2]["acao"], "modo_webhook")
        self.assertEqual([o["valor"] for o in blocos[i + 2]["campos"][0]["opcoes"]],
                         [rotas.MODO_REGISTRA, rotas.MODO_RECUSA])


if __name__ == "__main__":
    unittest.main()
