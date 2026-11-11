"""Mídia (M1) pelas rotas do serviço: o webhook responde antes do download terminar; GET /midia/<id> entrega os bytes
com os cabeçalhos certos (Range, anexo/inline, nosniff) e recusa token de outro projeto, id com cara de caminho e id
desconhecido; POST /midia/<id>/baixar-de-novo. E o conector da Evolution contra uma Evolution falsa em 127.0.0.1."""
import sys

sys.dont_write_bytecode = True

import http.client  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
from unittest import mock  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import midia, recebimento, rotas  # noqa: E402
from servico.conectores import base, evolution  # noqa: E402
from testes.test_midia import INST, OGG, PDF, Base, corpo  # noqa: E402

TOKEN, SEGREDO = "token-deste-projeto", "segredo-do-webhook"


class Rotas(Base):
    def setUp(self):
        super().setUp()
        self.app = rotas.App(self.pasta, 0, "http://127.0.0.1:8787", TOKEN, SEGREDO,
                             despachar=recebimento.Recebimento(lambda: self.c), conector=self.c)
        servidor = rotas.criar_servidor(self.app, 0)
        threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)

    def pedir(self, metodo, caminho, token=TOKEN, corpo_=None, extra=None):
        cab = dict({"Host": "127.0.0.1:%d" % self.app.porta}, **(extra or {}))
        if token:
            cab[rotas.CAB_TOKEN] = token
        dados = None
        if corpo_ is not None:
            dados = json.dumps(corpo_).encode("utf-8")
            cab["Content-Type"] = "application/json"
        con = http.client.HTTPConnection("127.0.0.1", self.app.porta, timeout=10)
        try:
            con.request(metodo, caminho, body=dados, headers=cab)
            r = con.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            con.close()

    def pronta(self, ident, tipo="audio", conteudo=OGG, nome=None):
        mid = self.chegou(ident, tipo, conteudo, nome)
        self.assertEqual(self.baixar(mid), "pronta")
        return mid


class TesteWebhook(Rotas):
    def test_webhook_responde_antes_do_download_terminar(self):
        baixador = midia.Baixador(self.abrir, lambda: self.c, self.pasta)
        midia.registrar_baixador(baixador)
        parar = threading.Event()
        self.addCleanup(parar.set)
        baixador.iniciar(parar)
        self.c.midias["W1"] = (OGG, "audio/ogg", None)
        self.c.segurar_midia = threading.Event()
        self.addCleanup(self.c.segurar_midia.set)
        inicio = time.monotonic()
        status, _, _ = self.pedir("POST", "/webhook/%s" % INST, token=None, corpo_=corpo("W1"),
                                  extra={rotas.CAB_SEGREDO: SEGREDO})
        self.assertEqual(status, 200)
        self.assertLess(time.monotonic() - inicio, 2.0)
        self.assertEqual(self.con.execute("SELECT estado FROM midias").fetchone()[0], "pendente")
        self.c.segurar_midia.set()
        for _ in range(200):
            if self.con.execute("SELECT estado FROM midias").fetchone()[0] != "pendente":
                break
            time.sleep(0.02)
        self.assertEqual(self.con.execute("SELECT estado FROM midias").fetchone()[0], "pronta")


class TesteServir(Rotas):
    def test_audio_inline_com_cabecalhos(self):
        mid = self.pronta("S1")
        status, cab, corpo_ = self.pedir("GET", "/midia/%d" % mid)
        self.assertEqual((status, corpo_), (200, OGG))
        self.assertEqual((cab["content-type"], cab["content-length"]), ("audio/ogg", str(len(OGG))))
        self.assertEqual((cab["content-disposition"], cab["x-content-type-options"]), ("inline", "nosniff"))
        self.assertEqual(cab["accept-ranges"], "bytes")

    def test_range_para_pular_no_audio(self):
        mid = self.pronta("S2")
        status, cab, corpo_ = self.pedir("GET", "/midia/%d" % mid, extra={"Range": "bytes=2-5"})
        self.assertEqual((status, corpo_, cab["content-range"]), (206, OGG[2:6], "bytes 2-5/%d" % len(OGG)))
        status, _, corpo_ = self.pedir("GET", "/midia/%d" % mid, extra={"Range": "bytes=-4"})
        self.assertEqual((status, corpo_), (206, OGG[-4:]))
        status, cab, _ = self.pedir("GET", "/midia/%d" % mid, extra={"Range": "bytes=999-"})
        self.assertEqual((status, cab["content-range"]), (416, "bytes */%d" % len(OGG)))

    def test_documento_como_anexo_com_nome(self):
        mid = self.pronta("S3", "documento", PDF, nome="proposta;final ção.pdf")
        status, cab, corpo_ = self.pedir("GET", "/midia/%d" % mid)
        self.assertEqual((status, corpo_, cab["content-type"]), (200, PDF, "application/pdf"))
        self.assertEqual(cab["content-disposition"], 'attachment; filename="proposta_final __o.pdf"; '
                         "filename*=UTF-8''proposta%3Bfinal%20%C3%A7%C3%A3o.pdf")

    def test_token_de_outro_projeto_id_estranho_e_desconhecido(self):
        mid = self.pronta("S4")
        self.assertEqual(self.pedir("GET", "/midia/%d" % mid, token="token-de-outro-projeto")[0], 403)
        self.assertEqual(self.pedir("GET", "/midia/%d" % mid, token=None)[0], 403)
        for caminho in ("/midia/..%2F..%2Fvendas.db", "/midia/../vendas.db", "/midia/%d/../1" % mid, "/midia/-1",
                        "/midia/9999", "/midia/1e3"):
            status, _, corpo_ = self.pedir("GET", caminho)
            self.assertEqual(status, 404, caminho)
            self.assertNotIn(OGG, corpo_)

    def test_arquivo_com_linha_adulterada_nao_sai_da_pasta(self):
        mid = self.pronta("S5")
        self.con.execute("UPDATE midias SET arquivo = '../vendas.db' WHERE id = ?", (mid,))
        self.assertEqual(self.pedir("GET", "/midia/%d" % mid)[0], 404)

    def test_falhou_nao_serve_e_baixar_de_novo(self):
        mid = self.chegou("S6", conteudo=None)
        self.baixar(mid)
        self.assertEqual(self.pedir("GET", "/midia/%d" % mid)[0], 404)
        self.assertEqual(self.pedir("POST", "/midia/%d/baixar-de-novo" % mid, token="outro")[0], 403)
        midia.registrar_baixador(midia.Baixador(self.abrir, lambda: self.c, self.pasta))
        self.assertEqual(self.pedir("POST", "/midia/%d/baixar-de-novo" % mid)[0], 202)
        self.assertEqual(self.pedir("POST", "/midia/%d/baixar-de-novo" % mid)[0], 409)   # duplo clique
        self.assertEqual(self.pedir("POST", "/midia/9999/baixar-de-novo")[0], 409)
        self.assertEqual(self.pedir("GET", "/midia/%d/baixar-de-novo" % mid)[0], 404)

    def test_conversa_mostra_a_midia(self):
        mid = self.pronta("S7")
        cid = self.con.execute("SELECT id FROM conversas").fetchone()[0]
        status, _, corpo_ = self.pedir("GET", "/conversas/%d" % cid)
        m = json.loads(corpo_.decode("utf-8"))["mensagens"][0]
        self.assertEqual((status, m["midia"]["id"], m["midia"]["estado"], m["midia"]["mimetype"]),
                         (200, mid, "pronta", "audio/ogg"))


class EvolutionFalsa(BaseHTTPRequestHandler):
    respostas = []   # (código, corpo) em ordem
    pedidos = []

    def log_message(self, *_):
        pass

    def do_POST(self):
        dados = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        type(self).pedidos.append((self.path, self.headers.get("apikey"), json.loads(dados.decode("utf-8"))))
        codigo, corpo_ = type(self).respostas.pop(0)
        bruto = json.dumps(corpo_).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(bruto)))
        self.end_headers()
        self.wfile.write(bruto)


class TesteConectorEvolution(unittest.TestCase):
    def setUp(self):
        EvolutionFalsa.respostas, EvolutionFalsa.pedidos = [], []
        servidor = ThreadingHTTPServer(("127.0.0.1", 0), EvolutionFalsa)
        threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        self.evo = evolution.Evolution("http://127.0.0.1:%d" % servidor.server_address[1], "chave-falsa",
                                       "http://127.0.0.1:1", "s")
        self.chave = {"id": "ABC", "remoteJid": "5511900000001@s.whatsapp.net", "fromMe": False}
        patcher = mock.patch.object(evolution, "ESPERA_NOVA_TENTATIVA_S", 0.01)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_formato_do_pedido_e_resposta(self):
        import base64
        EvolutionFalsa.respostas = [(201, {"base64": base64.b64encode(OGG).decode(), "mimetype": "audio/ogg",
                                           "fileName": "ABC.oga"})]
        self.assertEqual(self.evo.baixar_midia(INST, self.chave), (OGG, "audio/ogg", "ABC.oga"))
        caminho, chave, enviado = EvolutionFalsa.pedidos[0]
        self.assertEqual((caminho, chave), ("/chat/getBase64FromMediaMessage/%s" % INST, "chave-falsa"))
        self.assertEqual(enviado, {"message": {"key": self.chave}, "convertToMp4": False})

    def test_nao_achada_vira_expirada_sem_nova_tentativa(self):
        EvolutionFalsa.respostas = [(400, {"response": {"message": "Message not found"}})]
        with self.assertRaises(base.MidiaExpirada):
            self.evo.baixar_midia(INST, self.chave)
        self.assertEqual(len(EvolutionFalsa.pedidos), 1)

    def test_5xx_tenta_uma_vez_mais(self):
        import base64
        EvolutionFalsa.respostas = [(500, {}), (200, {"base64": base64.b64encode(PDF).decode()})]
        self.assertEqual(self.evo.baixar_midia(INST, self.chave)[0], PDF)
        EvolutionFalsa.respostas = [(502, {}), (503, {})]
        with self.assertRaises(base.MidiaIndisponivel):
            self.evo.baixar_midia(INST, self.chave)
        self.assertEqual(len(EvolutionFalsa.pedidos), 4)   # 2 + 2, nunca mais que isso

    def test_resposta_acima_do_teto_e_lixo(self):
        EvolutionFalsa.respostas = [(200, {"base64": "não é base64"})]
        with self.assertRaises(base.MidiaIndisponivel):
            self.evo.baixar_midia(INST, self.chave)
        with mock.patch.object(evolution, "RESPOSTA_MIDIA_MAX", 10):
            EvolutionFalsa.respostas = [(200, {"base64": "QUJDREVGR0hJSktMTU5PUA=="})]
            with self.assertRaises(base.MidiaGrandeDemais):
                self.evo.baixar_midia(INST, self.chave)


if __name__ == "__main__":
    unittest.main()
