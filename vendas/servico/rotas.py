"""Rotas HTTP do serviço: saúde, token de envio (só para a origem exata do painel), estado com token e webhook
com segredo em header. Nenhum dado do pedido vai para log; nenhum segredo vai para resposta que não o peça."""
import hmac
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from servico import banco

CORPO_MAX = 1024 * 1024
HOSTS = ("127.0.0.1", "localhost")
HOST_DOCKER = "host.docker.internal"  # só na rota do webhook (a Evolution no Docker chama por ele)
CAB_TOKEN = "X-Vendas-Token"
CAB_SEGREDO = "X-Vendas-Segredo"
INSTANCIA = re.compile(r"^/webhook/([A-Za-z0-9_-]{1,64})$")
MODO_REGISTRA, MODO_RECUSA = "registra_e_conta", "recusa"


def origem_do_painel(valor):
    """Normaliza --painel para a origem exata (esquema://host:porta). Porta explícita obrigatória."""
    partes = urlsplit((valor or "").strip())
    if partes.scheme not in ("http", "https") or not partes.hostname or partes.path not in ("", "/") \
            or partes.query or partes.fragment or partes.username or partes.password:
        raise ValueError("--painel precisa ser só esquema://host:porta, ex. http://127.0.0.1:8787")
    try:
        porta = partes.port
    except ValueError:
        porta = None
    if not porta:
        raise ValueError("--painel precisa ter a porta explícita, ex. http://127.0.0.1:8787")
    return "%s://%s:%d" % (partes.scheme, partes.hostname, porta)


def igual(recebido, esperado):
    return hmac.compare_digest((recebido or "").encode("utf-8"), esperado.encode("utf-8"))


def guardar_evento(con, instancia, corpo, segredo_ok):
    """Gancho padrão do webhook: guarda o evento cru. Itens seguintes trocam por quem traduz e responde."""
    banco.registrar_evento(con, "webhook", json.dumps(
        {"instancia": instancia, "segredo_ok": segredo_ok, "corpo": corpo}, ensure_ascii=False))


class App:
    """Estado do serviço que o handler usa: porta, origem do painel, token, segredo e o gancho do webhook."""

    def __init__(self, pasta_dados, porta, painel, token, segredo, despachar=guardar_evento):
        self.pasta_dados = pasta_dados
        self.porta = porta
        self.painel = painel
        self.token = token
        self.segredo = segredo
        self.despachar = despachar
        self.desde = banco.agora()

    def abrir(self):
        return banco.abrir(self.pasta_dados)


def host_ok(valor, porta, webhook=False):
    host = (valor or "").strip().lower()
    if not host or host.startswith("["):
        return False
    nome, _, p = host.partition(":")
    if p and p != str(porta):
        return False
    return nome in HOSTS or (webhook and nome == HOST_DOCKER)


def fazer_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "tune-up-vendas"
        sys_version = ""
        timeout = 15
        protocol_version = "HTTP/1.0"

        def log_message(self, *_):
            pass  # nada do pedido (caminho, IP, cabeçalho) vai para log

        def _cors(self):
            if self.headers.get("Origin") == app.painel:
                self.send_header("Access-Control-Allow-Origin", app.painel)
                self.send_header("Vary", "Origin")

        def _json(self, codigo, dado, extra=None):
            corpo = json.dumps(dado, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self._cors()
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _erro(self, codigo, msg):
            self._json(codigo, {"erro": msg})

        def _caminho(self):
            return self.path.split("?", 1)[0]

        def _host(self, webhook=False):
            if host_ok(self.headers.get("Host"), app.porta, webhook):
                return True
            self._erro(421, "Endereço recusado.")
            return False

        def _origem_exata(self):
            if self.headers.get("Origin") == app.painel:
                return True
            self._erro(403, "Origem recusada.")
            return False

        def do_OPTIONS(self):
            if not self._host() or not self._origem_exata():
                return
            self.send_response(204)
            self.send_header("Access-Control-Allow-Methods", "GET, POST")
            self.send_header("Access-Control-Allow-Headers", "%s, Content-Type" % CAB_TOKEN)
            self.send_header("Access-Control-Max-Age", "600")
            self.send_header("Content-Length", "0")
            self._cors()
            self.end_headers()

        def do_GET(self):
            caminho = self._caminho()
            if not self._host():
                return
            if caminho == "/saude":
                return self._json(200, {"ok": True, "servico": "tune-up-vendas", "desde": app.desde})
            if caminho == "/token-de-envio":
                if self._origem_exata():
                    self._json(200, {"token": app.token})
                return
            if caminho == "/estado":
                if not igual(self.headers.get(CAB_TOKEN), app.token):
                    return self._erro(403, "Token de envio errado. Recarregue a tela.")
                con = app.abrir()
                try:
                    dado = {"webhook_modo": banco.ler_config(con, "webhook_modo", MODO_REGISTRA),
                            "webhook_validos": int(banco.ler_config(con, "webhook_validos", "0")),
                            "webhook_invalidos": int(banco.ler_config(con, "webhook_invalidos", "0")),
                            "webhook_validos_seguidos": int(banco.ler_config(con, "webhook_validos_seguidos", "0"))}
                finally:
                    con.close()
                return self._json(200, dado)
            self._erro(404, "Rota desconhecida.")

        def do_POST(self):
            achado = INSTANCIA.match(self._caminho())
            if not self._host(webhook=bool(achado)):
                return
            if not achado:
                self.close_connection = True
                return self._erro(404, "Rota desconhecida.")
            self._webhook(achado.group(1))

        def _webhook(self, instancia):
            segredo_ok = igual(self.headers.get(CAB_SEGREDO), app.segredo)
            con = app.abrir()
            try:
                modo = banco.ler_config(con, "webhook_modo", MODO_REGISTRA)
                if not segredo_ok:
                    banco.somar_config(con, "webhook_invalidos")
                    banco.gravar_config(con, "webhook_validos_seguidos", "0")
                    if modo != MODO_REGISTRA:  # modo desconhecido fecha: recusa
                        self.close_connection = True
                        return self._erro(401, "Segredo do webhook errado.")
                corpo = self._corpo_json()
                if corpo is None:
                    return
                if segredo_ok:
                    banco.somar_config(con, "webhook_validos")
                    banco.somar_config(con, "webhook_validos_seguidos")
                app.despachar(con, instancia, corpo, segredo_ok)
            finally:
                con.close()
            self._json(200, {"ok": True})

        def _corpo_json(self):
            tipo = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            self.close_connection = True
            if tipo != "application/json":
                return self._erro(415, "O pedido precisa ser JSON.")
            if self.headers.get("Transfer-Encoding"):
                return self._erro(411, "Mande o tamanho do pedido.")
            try:
                tamanho = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                tamanho = -1
            if tamanho <= 0 or tamanho > CORPO_MAX:
                if tamanho > CORPO_MAX:  # escoa um pouco para o cliente receber o 413 (e não um reset)
                    self.rfile.read(min(tamanho, 1024 * 1024))
                return self._erro(413 if tamanho > CORPO_MAX else 400,
                                  "Pedido grande demais." if tamanho > 0 else "Tamanho do pedido inválido.")
            try:
                corpo = json.loads(self.rfile.read(tamanho).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return self._erro(400, "O pedido não é um JSON válido.")
            if not isinstance(corpo, dict):
                return self._erro(400, "O pedido precisa ser um objeto JSON.")
            return corpo

    return Handler


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        # o padrão imprime o traceback (que pode levar dado do pedido); aqui só o tipo do erro
        print("vendas: erro num pedido: %s" % sys.exc_info()[0].__name__, file=sys.stderr)


def criar_servidor(app, porta):
    """Servidor preso em 127.0.0.1. porta 0 = qualquer livre (testes); app.porta recebe a porta real."""
    servidor = Servidor(("127.0.0.1", porta), fazer_handler(app))
    app.porta = servidor.server_address[1]
    return servidor
