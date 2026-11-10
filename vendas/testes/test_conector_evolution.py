"""Conector Evolution contra um servidor falso em 127.0.0.1: criar com webhook e segredo, QR, estado, envio com id,
4xx = NaoEnviado, conexão recusada = NaoEnviado, pedido lido e conexão fechada / timeout / 5xx = EnvioIncerto,
nenhuma URL com logout e nenhum DELETE; e o conector falso dos itens seguintes."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)

from servico.conectores import base, evolution, falso  # noqa: E402
from servico.conectores.base import EnvioIncerto, NaoEnviado  # noqa: E402

CHAVE = "chave-de-teste-123"
SEGREDO = "segredo-de-teste-456"
PNG = "data:image/png;base64,iVBORw0KGgo="
FECHAR, DORMIR = "fechar", "dormir"


class _Manipulador(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _tratar(self):
        tamanho = int(self.headers.get("Content-Length") or 0)
        corpo = self.rfile.read(tamanho) if tamanho else b""
        srv = self.server
        cabecalhos = {k.lower(): v for k, v in self.headers.items()}  # urllib manda "Apikey"
        srv.pedidos.append({"metodo": self.command, "caminho": self.path, "headers": cabecalhos,
                            "corpo": json.loads(corpo) if corpo else None})
        resposta = srv.respostas.get((self.command, self.path), (404, {"message": "nada"}))
        if resposta == FECHAR:  # leu o pedido inteiro e cai sem responder
            self.close_connection = True
            return
        if resposta == DORMIR:
            time.sleep(1.5)
            resposta = (200, {"key": {"id": "tarde"}})
        status, dados = resposta
        bruto = json.dumps(dados).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(bruto)))
        self.end_headers()
        self.wfile.write(bruto)

    do_GET = do_POST = do_DELETE = do_PUT = _tratar


class EvolutionFalsa:
    def __init__(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Manipulador)
        self.srv.daemon_threads = True
        self.srv.pedidos, self.srv.respostas = [], {}
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def fechar(self):
        self.srv.shutdown()
        self.srv.server_close()


class TestEvolution(unittest.TestCase):
    def setUp(self):
        self.falsa = EvolutionFalsa()
        self.addCleanup(self.falsa.fechar)
        self.resp = self.falsa.srv.respostas
        self.pedidos = self.falsa.srv.pedidos
        self.con = evolution.Evolution(self.falsa.url, CHAVE, "http://host.docker.internal:8790", SEGREDO,
                                       tempo_limite=0.5)

    def tearDown(self):
        for p in self.pedidos:  # vale para todo teste: nada de logout nem DELETE
            self.assertNotIn("logout", p["caminho"].lower())
            self.assertNotIn("delete", p["caminho"].lower())
            self.assertNotEqual(p["metodo"], "DELETE")

    def test_criar_registra_webhook_com_header_do_segredo(self):
        self.resp[("POST", "/instance/create")] = (201, {"instance": {"instanceName": "loja"}})
        self.con.criar("loja")
        self.assertEqual(len(self.pedidos), 1)
        p = self.pedidos[0]
        self.assertEqual(p["headers"].get("apikey"), CHAVE)
        self.assertEqual(p["corpo"]["instanceName"], "loja")
        gancho = p["corpo"]["webhook"]
        self.assertEqual(gancho["url"], "http://host.docker.internal:8790/webhook/loja")
        self.assertEqual(gancho["headers"]["X-Vendas-Segredo"], SEGREDO)
        self.assertIn("MESSAGES_UPSERT", gancho["events"])
        self.assertIn("CONNECTION_UPDATE", gancho["events"])

    def test_criar_instancia_existente_regrava_o_webhook(self):
        self.resp[("POST", "/instance/create")] = (403, {"message": "in use"})
        self.resp[("POST", "/webhook/set/loja")] = (201, {"enabled": True})
        self.con.criar("loja")
        self.assertEqual([p["caminho"] for p in self.pedidos], ["/instance/create", "/webhook/set/loja"])
        gancho = self.pedidos[1]["corpo"]["webhook"]
        self.assertTrue(gancho["enabled"])
        self.assertEqual(gancho["headers"]["X-Vendas-Segredo"], SEGREDO)

    def test_criar_com_chave_errada_sobe_erro(self):
        self.resp[("POST", "/instance/create")] = (401, {"message": "Unauthorized"})
        with self.assertRaises(NaoEnviado):
            self.con.criar("loja")
        self.assertEqual(len(self.pedidos), 1)

    def test_nome_de_instancia_invalido_nao_chama_a_rede(self):
        with self.assertRaises(ValueError):
            self.con.criar("../instance/logout/x")
        self.assertEqual(self.pedidos, [])

    def test_qr_devolve_data_uri(self):
        self.resp[("GET", "/instance/connect/loja")] = (200, {"pairingCode": None, "code": "2@x", "base64": PNG})
        self.assertEqual(self.con.qr("loja"), PNG)
        self.resp[("GET", "/instance/connect/loja")] = (200, {"instance": {"instanceName": "loja", "state": "open"}})
        self.assertIsNone(self.con.qr("loja"))

    def test_estado_mapeado(self):
        for bruto, esperado in (("open", "conectado"), ("connecting", "aguardando_qr"), ("close", "desconectado"),
                                ("refused", "desconectado")):
            self.resp[("GET", "/instance/connectionState/loja")] = (
                200, {"instance": {"instanceName": "loja", "state": bruto}})
            self.assertEqual(self.con.estado("loja"), esperado, bruto)
        self.resp.pop(("GET", "/instance/connectionState/loja"))
        self.assertEqual(self.con.estado("loja"), "desconectado")  # 404: instância não existe

    def test_enviar_texto_devolve_id(self):
        self.resp[("POST", "/message/sendText/loja")] = (
            201, {"key": {"remoteJid": "5511900000001@s.whatsapp.net", "fromMe": True, "id": "ABC123"}})
        self.assertEqual(self.con.enviar_texto("loja", "+55 11 90000-0001", "oi"), "ABC123")
        self.assertEqual(self.pedidos[0]["corpo"], {"number": "5511900000001", "text": "oi"})

    def test_enviar_audio_manda_base64_e_devolve_id(self):
        self.resp[("POST", "/message/sendWhatsAppAudio/loja")] = (201, {"key": {"id": "AUD1"}})
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as arq:
            arq.write(b"OggS-falso")
        self.addCleanup(os.remove, arq.name)
        self.assertEqual(self.con.enviar_audio("loja", "5511900000001", arq.name), "AUD1")
        self.assertEqual(self.pedidos[0]["corpo"]["audio"], "T2dnUy1mYWxzbw==")

    def test_audio_ilegivel_nao_enviado_sem_rede(self):
        with self.assertRaises(NaoEnviado):
            self.con.enviar_audio("loja", "5511900000001", os.path.join(tempfile.gettempdir(), "nao-existe.ogg"))
        self.assertEqual(self.pedidos, [])

    def test_4xx_e_nao_enviado(self):
        self.resp[("POST", "/message/sendText/loja")] = (400, {"message": "número inexistente"})
        with self.assertRaises(NaoEnviado) as ctx:
            self.con.enviar_texto("loja", "5511900000001", "oi")
        self.assertNotIsInstance(ctx.exception, EnvioIncerto)
        self.assertEqual(ctx.exception.status, 400)

    def test_5xx_e_incerto(self):
        self.resp[("POST", "/message/sendText/loja")] = (500, {"message": "erro"})
        with self.assertRaises(EnvioIncerto):
            self.con.enviar_texto("loja", "5511900000001", "oi")

    def test_lido_e_fechado_sem_resposta_e_incerto(self):
        self.resp[("POST", "/message/sendText/loja")] = FECHAR
        with self.assertRaises(EnvioIncerto):
            self.con.enviar_texto("loja", "5511900000001", "oi")
        self.assertEqual(len(self.pedidos), 1)  # o pedido chegou inteiro do outro lado

    def test_timeout_e_incerto(self):
        self.resp[("POST", "/message/sendText/loja")] = DORMIR
        with self.assertRaises(EnvioIncerto):
            self.con.enviar_texto("loja", "5511900000001", "oi")

    def test_aceito_sem_id_e_incerto(self):
        self.resp[("POST", "/message/sendText/loja")] = (201, {"status": "PENDING"})
        with self.assertRaises(EnvioIncerto):
            self.con.enviar_texto("loja", "5511900000001", "oi")

    def test_erro_nao_carrega_chave_nem_texto(self):
        self.resp[("POST", "/message/sendText/loja")] = (400, {"message": "x"})
        with self.assertRaises(NaoEnviado) as ctx:
            self.con.enviar_texto("loja", "5511900000001", "texto-pessoal")
        for proibido in (CHAVE, SEGREDO, "texto-pessoal"):
            self.assertNotIn(proibido, str(ctx.exception))
            self.assertNotIn(proibido, repr(self.con))


class TestSemServidor(unittest.TestCase):
    def test_conexao_recusada_e_nao_enviado(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
        s.close()
        con = evolution.Evolution("http://127.0.0.1:%d" % porta, CHAVE, "http://x", SEGREDO, tempo_limite=2)
        with self.assertRaises(NaoEnviado) as ctx:
            con.enviar_texto("loja", "5511900000001", "oi")
        self.assertNotIsInstance(ctx.exception, EnvioIncerto)

    def test_do_ambiente_exige_url_e_chave(self):
        with self.assertRaises(ValueError):
            evolution.Evolution.do_ambiente("http://x", SEGREDO, {})
        con = evolution.Evolution.do_ambiente("http://x", SEGREDO, {
            evolution.VAR_URL: "http://127.0.0.1:9", evolution.VAR_CHAVE: CHAVE})
        self.assertEqual(con.url, "http://127.0.0.1:9")

    def test_codigo_do_conector_nao_desconecta_nem_apaga(self):
        caminho = os.path.join(VENDAS, "servico", "conectores", "evolution.py")
        with open(caminho, encoding="utf-8") as arq:
            fonte = arq.read().lower()
        self.assertNotIn("logout", fonte)
        self.assertNotIn('"delete"', fonte)
        self.assertNotIn("/delete", fonte)

    def test_nenhuma_url_montada_tem_logout(self):
        """Intercepta _pedir e chama todo método público, inclusive os caminhos de erro (criar com 4xx)."""
        con = evolution.Evolution("http://127.0.0.1:9", CHAVE, "http://x", SEGREDO)
        urls = []

        def pedir(metodo, caminho, corpo=None):
            urls.append((metodo, con.url + caminho))
            if caminho == "/instance/create":
                raise NaoEnviado("em uso", 403)
            return {"key": {"id": "1"}, "instance": {"state": "open"}}

        con._pedir = pedir
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as arq:
            arq.write(b"x")
        self.addCleanup(os.remove, arq.name)
        con.criar("loja")
        con.qr("loja")
        con.estado("loja")
        con.enviar_texto("loja", "5511900000001", "oi")
        con.enviar_audio("loja", "5511900000001", arq.name)
        self.assertEqual(len(urls), 6)
        for metodo, url in urls:
            self.assertNotIn("logout", url.lower())
            self.assertNotEqual(metodo, "DELETE")


class TestFalso(unittest.TestCase):
    def test_modos(self):
        c = falso.ConectorFalso()
        self.assertEqual(c.enviar_texto("loja", "5511900000001", "oi"), "falso-1")
        c.modo_envio = "recusar"
        with self.assertRaises(NaoEnviado):
            c.enviar_texto("loja", "5511900000001", "oi")
        c.modo_envio = "timeout"
        with self.assertRaises(EnvioIncerto):
            c.enviar_texto("loja", "5511900000001", "oi")
        c.modo_envio = "aceitar_e_cair"
        with self.assertRaises(EnvioIncerto):
            c.enviar_audio("loja", "5511900000001", "/x.ogg")
        self.assertEqual(c.envios(), 4)
        self.assertEqual([e["id_externo"] for e in c.entregues], ["falso-1", "falso-2"])
        self.assertIsInstance(c, base.Conector)


if __name__ == "__main__":
    unittest.main()
