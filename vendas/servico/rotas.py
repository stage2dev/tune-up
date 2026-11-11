"""Rotas HTTP do serviço: saúde, token de envio (só para a origem exata do painel), estado com token e webhook
com segredo em header. Nenhum dado do pedido vai para log; nenhum segredo vai para resposta que não o peça."""
import hashlib
import hmac
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from servico import banco, instancia, portao, telefone
from servico.conectores.base import ErroConector

CORPO_MAX = 1024 * 1024
HOSTS = ("127.0.0.1", "localhost")
HOST_DOCKER = "host.docker.internal"  # só na rota do webhook (a Evolution no Docker chama por ele)
CAB_TOKEN = "X-Vendas-Token"
CAB_SEGREDO = "X-Vendas-Segredo"
INSTANCIA = re.compile(r"^/webhook/([A-Za-z0-9_-]{1,64})$")
MODO_REGISTRA, MODO_RECUSA = "registra_e_conta", "recusa"
VALIDOS_PARA_RECUSA = 20  # "recusa" só liga depois de tantos webhooks válidos seguidos (um inválido zera)
ID_TELA = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
TEXTO_MAX = 4096


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
    """Despachante padrão do webhook (testes): guarda o evento cru. O serviço usa recebimento.Recebimento, que pode
    devolver uma função para rodar depois do commit, fora da transação."""
    banco.registrar_evento(con, "webhook", json.dumps(
        {"instancia": instancia, "segredo_ok": segredo_ok, "corpo": corpo}, ensure_ascii=False))


def impressao(segredo):
    """Impressão digital curta do segredo (sha256), para notar a troca sem guardar o segredo no banco."""
    return hashlib.sha256(segredo.encode("utf-8")).hexdigest()[:16]


def conferir_segredo(con, segredo, novo=False):
    """Na subida: o segredo do webhook é novo (novo=True) ou mudou desde a última vez? Zera os válidos seguidos
    e, se o modo era 'recusa', volta para 'registra_e_conta' (a Evolution ainda manda o segredo velho). Devolve
    True nesse caso."""
    nova = impressao(segredo)
    con.execute("BEGIN IMMEDIATE")
    try:
        antiga = banco.ler_config(con, "webhook_impressao")
        voltou = False
        if novo or (antiga is not None and antiga != nova):
            banco.gravar_config(con, "webhook_validos_seguidos", "0")
            voltou = banco.ler_config(con, "webhook_modo", MODO_REGISTRA) != MODO_REGISTRA
            if voltou:
                banco.gravar_config(con, "webhook_modo", MODO_REGISTRA)
        if antiga != nova:
            banco.gravar_config(con, "webhook_impressao", nova)
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return voltou


class App:
    """Estado do serviço que o handler usa: porta, origem do painel, token, segredo e o gancho do webhook."""

    def __init__(self, pasta_dados, porta, painel, token, segredo, despachar=guardar_evento, conector=None):
        self.pasta_dados = pasta_dados
        self.porta = porta
        self.painel = painel
        self.token = token
        self.segredo = segredo
        self.despachar = despachar
        self.conector = conector  # só o portão chama o envio dele
        self.desde = banco.agora()
        self.marca = os.path.basename(os.path.normpath(pasta_dados))  # hash da pasta de dados = qual projeto

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
            if caminho == "/instancia":
                return self._instancia()
            if caminho == "/saude":
                return self._json(200, {"ok": True, "servico": "tune-up-vendas", "desde": app.desde,
                                        "marca": app.marca})
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
            if self._caminho() == "/enviar":
                return self._enviar()
            if self._caminho() == "/modo-webhook":
                return self._modo_webhook()
            if self._caminho() == "/instancia":
                return self._instancia()
            if not achado:
                self.close_connection = True
                return self._erro(404, "Rota desconhecida.")
            self._webhook(achado.group(1))

        def _webhook(self, instancia):
            segredo_ok = igual(self.headers.get(CAB_SEGREDO), app.segredo)
            con = app.abrir()
            try:
                if not segredo_ok:  # zera e lê o modo numa transação só (a troca de modo também usa uma)
                    con.execute("BEGIN IMMEDIATE")
                    try:
                        banco.somar_config(con, "webhook_invalidos")
                        banco.gravar_config(con, "webhook_validos_seguidos", "0")
                        modo = banco.ler_config(con, "webhook_modo", MODO_REGISTRA)
                        con.execute("COMMIT")
                    except Exception:
                        if con.in_transaction:
                            con.execute("ROLLBACK")
                        raise
                    if modo != MODO_REGISTRA:  # modo desconhecido fecha: recusa
                        self.close_connection = True
                        return self._erro(401, "Segredo do webhook errado.")
                corpo = self._corpo_json()
                if corpo is None:
                    return
                if not segredo_ok:
                    depois = app.despachar(con, instancia, corpo, False)
                else:  # o válido só conta se o evento foi guardado: os dois na mesma transação
                    con.execute("BEGIN IMMEDIATE")
                    try:
                        depois = app.despachar(con, instancia, corpo, True)
                        banco.somar_config(con, "webhook_validos")
                        banco.somar_config(con, "webhook_validos_seguidos")
                        con.execute("COMMIT")
                    except BaseException:
                        if con.in_transaction:
                            con.execute("ROLLBACK")
                        raise
                if callable(depois):  # o que fala para fora (portão, gancho da IA) roda depois do commit
                    depois(con)
            finally:
                con.close()
            self._json(200, {"ok": True})

        def _modo_webhook(self):
            """Troca o modo do segredo do webhook. "recusa" só com VALIDOS_PARA_RECUSA válidos seguidos (lidos e
            gravados na mesma transação: um inválido que chega junto não passa por baixo)."""
            if not igual(self.headers.get(CAB_TOKEN), app.token):
                self.close_connection = True
                return self._erro(403, "Token de envio errado. Recarregue a tela.")
            corpo = self._corpo_json()
            if corpo is None:
                return
            modo = corpo.get("modo")
            if modo not in (MODO_REGISTRA, MODO_RECUSA):
                return self._erro(400, "Modo desconhecido.")
            con = app.abrir()
            try:
                con.execute("BEGIN IMMEDIATE")
                try:
                    seguidos = int(banco.ler_config(con, "webhook_validos_seguidos", "0"))
                    if modo == MODO_RECUSA and seguidos < VALIDOS_PARA_RECUSA:
                        con.execute("ROLLBACK")
                        return self._erro(409, "Faltam %d webhooks válidos seguidos para ligar a recusa."
                                          % (VALIDOS_PARA_RECUSA - seguidos))
                    banco.gravar_config(con, "webhook_modo", modo)
                    con.execute("COMMIT")
                except Exception:
                    if con.in_transaction:
                        con.execute("ROLLBACK")
                    raise
            finally:
                con.close()
            self._json(200, {"webhook_modo": modo, "webhook_validos_seguidos": seguidos})

        def _instancia(self):
            """GET: estado + QR (lido na hora). POST: cria/conecta; sem `numero_descartavel` true fica false."""
            if not igual(self.headers.get(CAB_TOKEN), app.token):
                self.close_connection = True
                return self._erro(403, "Token de envio errado. Recarregue a tela.")
            corpo = None
            if self.command == "POST":
                corpo = self._corpo_json()
                if corpo is None:
                    return
            if app.conector is None:
                return self._erro(503, "WhatsApp não configurado no serviço.")
            con = app.abrir()
            try:
                if corpo is None:
                    return self._json(200, instancia.ler(con, app.conector))
                try:
                    r = instancia.conectar(con, app.conector, corpo.get("instancia"),
                                           corpo.get("numero_descartavel"))
                except ValueError:
                    return self._erro(400, "Nome de instância inválido (letras, números, _ e -, até 64).")
                except ErroConector:
                    return self._erro(502, instancia.ERRO_CONECTOR)
            finally:
                con.close()
            self._json(200, r)

        def _enviar(self):
            """Envio manual da tela: origem 'manual' fixada aqui; 'origem' no corpo é ignorada."""
            if not igual(self.headers.get(CAB_TOKEN), app.token):
                self.close_connection = True
                return self._erro(403, "Token de envio errado. Recarregue a tela.")
            corpo = self._corpo_json()
            if corpo is None:
                return
            texto, id_tela = corpo.get("texto"), corpo.get("id_tela")
            if not isinstance(texto, str) or not texto.strip() or len(texto) > TEXTO_MAX:
                return self._erro(400, "Mensagem vazia ou longa demais.")
            if not isinstance(id_tela, str) or not ID_TELA.match(id_tela):
                return self._erro(400, "Envio sem identificador da tela.")
            if not isinstance(corpo.get("telefone"), str):
                return self._erro(400, "Telefone inválido.")
            if app.conector is None:
                return self._erro(503, "WhatsApp não configurado no serviço.")
            con = app.abrir()
            try:
                instancia = banco.ler_config(con, "instancia")
                if not instancia:
                    return self._erro(503, "Conecte o WhatsApp primeiro.")
                try:
                    r = portao.enviar_manual(con, app.conector, instancia, corpo["telefone"], texto, id_tela,
                                             confirmar_optout=corpo.get("confirmar_optout") is True)
                except telefone.TelefoneInvalido:
                    return self._erro(400, "Telefone inválido.")
            finally:
                con.close()
            self._json(200, {"estado": r["estado"], "motivo": r["motivo"], "envio_id": r["envio_id"]})

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
