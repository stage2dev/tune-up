"""Painel tune-up v2: servidor local (127.0.0.1) da tela e da API.

Uso: python3 painel.py [--port 8787] [--projeto PASTA] [--plans-dir PASTA]
Rotas: veja contrato/api.d.ts. O núcleo é genérico: o que é do projeto vem de
<raiz>/.tune-up/painel.json e do pacote do projeto (veja config.py). Todo POST exige X-Painel-Token (nasce a cada
subida), Origin do próprio endereço, Sec-Fetch-Site same-origin (ou ausente),
Content-Type application/json e corpo até 32 KB.
"""
import sys

sys.dont_write_bytecode = True  # nem __pycache__ em disco

import argparse  # noqa: E402
import hmac  # noqa: E402
import importlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import secrets  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import urllib.parse  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402

import config  # noqa: E402
import estaticos  # noqa: E402
import lancador as lanc  # noqa: E402
import leitor  # noqa: E402
import mascara  # noqa: E402
import modulos  # noqa: E402
import transcricao  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
HOSTS_OK = {"127.0.0.1", "localhost"}
TTL_ESTADO = 3  # segundos: várias abas abertas não refazem a leitura toda hora
CORPO_MAX = 32 * 1024  # uma mensagem do chat tem até 6000 letras (acento = 2 bytes)
RE_ROTA_EXEC = re.compile(r"^/api/execucoes/([^/]{1,40})/(eventos|parar|abrir|responder)$")
RE_ROTA_MODULO = re.compile(r"^/api/modulos/([^/]{1,80})$")
RE_ROTA_MODULO_ACAO = re.compile(r"^/api/modulos/([^/]{1,80})/acao$")
RE_SESSAO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

CSP = ("default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
       "font-src 'self'; connect-src 'self'; manifest-src 'self'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors 'none'")


class Estado:
    """/api/estado com cache curto. `dado()` serve o lançador para validar fase e Parte."""

    def __init__(self, plans_dir, cfg, rodar_externos=True):
        self.plans_dir, self.cfg, self.rodar_externos = plans_dir, cfg, rodar_externos
        self.cache = leitor.Cache()
        self._lock = threading.Lock()
        self._ultimo = (0.0, None, None)

    def _montar(self):
        with self._lock:
            quando, dado, corpo = self._ultimo
            if corpo is None or time.monotonic() - quando > TTL_ESTADO:
                try:
                    dado = leitor.montar_estado(self.plans_dir, self.cache, self.rodar_externos, self.cfg)
                except Exception as e:  # nunca derruba o servidor
                    dado = {"erro": "falha ao montar o estado: %s" % type(e).__name__, "avisos": [str(e)[:300]]}
                dado["projeto"] = {"nome": self.cfg.get("nome") or ""}
                avisos_cfg = [a for a in self.cfg.get("avisos") or [] if a not in (dado.get("avisos") or [])]
                dado["avisos"] = avisos_cfg + list(dado.get("avisos") or [])
                corpo = json.dumps(dado, ensure_ascii=False).encode("utf-8")
                self._ultimo = (time.monotonic(), dado, corpo)
            return dado, corpo

    def json(self):
        return self._montar()[1]

    def dado(self):
        return self._montar()[0]

    def invalidar(self):
        self.cache.esquecer("sessoes")
        with self._lock:
            self._ultimo = (0.0, None, None)


def host_permitido(valor):
    if not valor:
        return False
    host = valor.strip().lower()
    if host.startswith("["):
        return False  # IPv6 não é servido
    host = host.rsplit(":", 1)[0] if ":" in host else host
    return host in HOSTS_OK


class App:
    """Tudo que o handler precisa: config, token, estado, lançador e os módulos de fora."""

    def __init__(self, cfg, plans_dir=None, lancador=None, rodar_externos=True):
        self.cfg = cfg
        self.token = secrets.token_urlsafe(32)
        self.log = True
        self.porta = cfg.get("porta", 8787)
        self.estado = Estado(plans_dir, cfg, rodar_externos)
        self.lancador = lancador or lanc.Lancador(cfg, self.estado.dado)

    def origens(self):
        return {"http://127.0.0.1:%d" % self.porta, "http://localhost:%d" % self.porta} \
            | set(self.cfg.get("origens_extras") or [])

    def token_ok(self, valor):
        return bool(valor) and hmac.compare_digest(valor.encode("utf-8"), self.token.encode("utf-8"))

    def modulo(self, nome, **kw):
        """nome.montar(cfg, **kw) de um módulo do núcleo (acompanhamento, agentes): (codigo, dado)."""
        try:
            mod = importlib.import_module(nome)
        except Exception as e:
            return 503, {"erro": "Esta parte do painel ainda não está instalada.",
                         "avisos": ["módulo %s não carregou (%s)" % (nome, type(e).__name__)]}
        try:
            dado = mod.montar(self.cfg, **kw)
        except Exception as e:
            return 500, {"erro": "Não consegui montar esta parte do painel.",
                         "avisos": ["%s.montar quebrou: %s: %s" % (nome, type(e).__name__, str(e)[:200])]}
        if not isinstance(dado, dict):
            return 500, {"erro": "Esta parte do painel devolveu algo estranho.", "avisos": []}
        return 200, dado


def para_tela(ex):
    """Execução que sai pela API: nome, título e textos do pedido passam pela máscara (o registro guarda cru)."""
    if not isinstance(ex, dict):
        return ex
    params = {k: mascara.mascarar(v) if isinstance(v, str) else v for k, v in (ex.get("params") or {}).items()}
    return dict(ex, params=params, nome=mascara.mascarar(ex.get("nome")), titulo=mascara.mascarar(ex.get("titulo")))


def fazer_handler(app):
    class Handler(BaseHTTPRequestHandler):
        server_version = "painel-tune-up"
        sys_version = ""
        timeout = 15
        protocol_version = "HTTP/1.0"

        # ---- respostas
        def _enviar(self, codigo, corpo, tipo, cache="no-store", csp=CSP):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", csp)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)

        def _json(self, codigo, dado):
            corpo = dado if isinstance(dado, bytes) else json.dumps(dado, ensure_ascii=False).encode("utf-8")
            self._enviar(codigo, corpo, "application/json; charset=utf-8")

        def _erro(self, codigo, msg, **extra):
            dado = {"erro": msg}
            dado.update(extra)
            self._json(codigo, dado)

        # ---- defesas
        def _origem_ok(self):
            if not host_permitido(self.headers.get("Host")):
                self._erro(421, "Endereço recusado.")
                return False
            if (self.headers.get("Sec-Fetch-Site") or "same-origin") not in ("same-origin", "none"):
                # Abrir a página por link, favorito ou outro app é navegação comum;
                # só a API fica fechada para outros sites.
                navegacao = (self.headers.get("Sec-Fetch-Mode") == "navigate"
                             and self.headers.get("Sec-Fetch-Dest") == "document"
                             and not self.path.startswith("/api/"))
                if not navegacao:
                    self._erro(403, "Pedido de outro site recusado.")
                    return False
            return True

        def _post_ok(self):
            if (self.headers.get("Sec-Fetch-Site") or "same-origin") != "same-origin":
                self._erro(403, "Pedido de outro site recusado.")
                return None
            if self.headers.get("Origin") not in app.origens():
                self._erro(403, "Pedido de outra origem recusado.")
                return None
            if not app.token_ok(self.headers.get("X-Painel-Token")):
                self._erro(403, "Chave do painel errada. Recarregue a página.")
                return None
            tipo = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            if tipo != "application/json":
                self._erro(415, "O pedido precisa ser JSON.")
                return None
            if self.headers.get("Transfer-Encoding"):
                self.close_connection = True
                self._erro(411, "Mande o tamanho do pedido.")
                return None
            try:
                tamanho = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                tamanho = -1
            if tamanho < 0 or tamanho > CORPO_MAX:
                self.close_connection = True
                if tamanho > CORPO_MAX:  # escoa um pouco para o cliente receber o 413 (e não um reset)
                    self.rfile.read(min(tamanho, 1024 * 1024))
                self._erro(413 if tamanho > CORPO_MAX else 400, "Pedido grande demais." if tamanho > 0
                           else "Tamanho do pedido inválido.")
                return None
            bruto = self.rfile.read(tamanho) if tamanho else b""
            if not bruto.strip():
                return {}
            try:
                corpo = json.loads(bruto.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._erro(400, "O pedido não é um JSON válido.")
                return None
            if not isinstance(corpo, dict):
                self._erro(400, "O pedido precisa ser um objeto JSON.")
                return None
            return corpo

        # ---- GET
        def do_GET(self):
            if not self._origem_ok():
                return
            partes = urllib.parse.urlsplit(self.path)
            caminho = partes.path
            if caminho.startswith("/api/") or caminho == "/api":
                try:
                    return self._api_get(caminho, urllib.parse.parse_qs(partes.query))
                except Exception as e:  # nunca derruba a conexão sem resposta
                    return self._erro(500, "Erro inesperado no painel (%s)." % type(e).__name__)
            codigo, corpo, tipo, cache = estaticos.resolver(self.path, app.cfg["web_dir"])
            if codigo != 200:
                return self._erro(codigo, "Não encontrado." if codigo == 404 else "Erro ao ler a página.")
            self._enviar(200, corpo, tipo, cache)

        def _api_get(self, caminho, query):
            if caminho == "/api/sessao":
                # O token só sai para o fetch do próprio painel: sem o cabeçalho
                # (curl, outro programa local) ou de outro site, recusa.
                if self.headers.get("Sec-Fetch-Site") != "same-origin":
                    return self._erro(403, "Pedido de outro site recusado.")
                return self._json(200, {"token": app.token, "projeto": {"nome": app.cfg["nome"]},
                                        "versao": app.cfg.get("versao", config.VERSAO)})
            if caminho == "/api/estado":
                return self._json(200, app.estado.json())
            if caminho == "/api/acoes":
                acoes, avisos = app.lancador.acoes()
                return self._json(200, {"acoes": acoes, "avisos": avisos})
            if caminho == "/api/execucoes":
                return self._json(200, {"execucoes": [para_tela(e) for e in app.lancador.execucoes()]})
            if caminho == "/api/modelos":
                return self._json(200, {"modelos": app.lancador.status_modelos()})
            if caminho == "/api/acompanhamento":
                return self._json(*app.modulo("acompanhamento"))
            if caminho == "/api/agentes":
                return self._agentes(query)
            if caminho == "/api/modulos":
                return self._json(200, modulos.listar(app.cfg))
            m = RE_ROTA_MODULO.match(caminho)
            if m:
                fresco = (query.get("fresco") or ["0"])[0] in ("1", "true")
                return self._json(*modulos.montar(app.cfg, urllib.parse.unquote(m.group(1)), usar_cache=not fresco))
            m = RE_ROTA_EXEC.match(caminho)
            if m and m.group(2) == "eventos":
                return self._eventos(m.group(1), query)
            if m:
                return self._erro(405, "Use POST nesta rota.")
            return self._erro(404, "Não encontrado.")

        def _agentes(self, query):
            sessao = (query.get("sessao") or [None])[0]
            if sessao is not None and not RE_SESSAO.match(sessao):
                return self._erro(400, "Sessão inválida.")
            todos = (query.get("todos") or ["0"])[0] in ("1", "true")
            return self._json(*app.modulo("agentes", sessao=sessao, todos=todos))

        def _eventos(self, exec_id, query):
            reg = app.lancador.achar(exec_id)
            if reg is None:
                return self._erro(404, "Não achei essa execução.")
            ex = app.lancador.execucao(exec_id) or {}
            desde = (query.get("desde") or ["0"])[0]
            if not re.fullmatch(r"\d{1,15}", desde):
                return self._erro(400, "O número 'desde' é inválido.")
            caminho = transcricao.localizar(app.cfg["projects_dir"], ex.get("sessao_id") or reg.get("sessao_id"),
                                            reg.get("cwd") or app.cfg["workspace"])
            inteiro = (query.get("inteiro") or ["0"])[0] in ("1", "true")
            dado = transcricao.ler(caminho, int(desde),
                                   corte_fala=transcricao.CORTE_INTEIRO if inteiro else transcricao.CORTE)
            dado["estado"] = ex.get("estado", "sumiu")
            return self._json(200, dado)

        def do_HEAD(self):
            self.do_GET()

        # ---- POST
        def do_POST(self):
            if not self._origem_ok():
                return
            corpo = self._post_ok()
            if corpo is None:
                return
            caminho = urllib.parse.urlsplit(self.path).path
            try:
                if caminho == "/api/execucoes":
                    ex = app.lancador.iniciar(corpo.get("acao"), corpo.get("params"))
                    app.estado.invalidar()
                    return self._json(201, {"execucao": para_tela(ex)})
                m = RE_ROTA_EXEC.match(caminho)
                if m and m.group(2) == "parar":
                    r = app.lancador.parar(m.group(1))
                    app.estado.invalidar()
                    return self._json(200, r)
                if m and m.group(2) == "abrir":
                    return self._json(200, app.lancador.abrir(m.group(1)))
                if m and m.group(2) == "responder":
                    ex = app.lancador.responder(m.group(1), corpo.get("texto"),
                                                interromper=corpo.get("interromper") is True)
                    app.estado.invalidar()
                    return self._json(200, {"execucao": para_tela(ex)})
                m = RE_ROTA_MODULO_ACAO.match(caminho)
                if m:  # `dados` vai intacto para o módulo e nunca é registrado nem ecoado
                    return self._json(*modulos.agir(app.cfg, urllib.parse.unquote(m.group(1)),
                                                    corpo.get("acao"), corpo.get("dados")))
                return self._erro(404, "Não encontrado.")
            except lanc.ErroAcao as e:
                extra = {"execucao_id": e.execucao_id} if e.execucao_id else {}
                return self._erro(e.codigo, e.mensagem, **extra)
            except Exception as e:
                return self._erro(500, "Erro inesperado no painel (%s)." % type(e).__name__)

        def _recusar(self):
            self._erro(405, "Método não permitido.")

        do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _recusar

        def log_message(self, fmt, *args):
            if app.log:
                sys.stderr.write("painel: %s\n" % (fmt % args))

    return Handler


def criar_servidor(app, porta):
    """Bind só em 127.0.0.1. Porta 0 = uma livre (testes)."""
    servidor = ThreadingHTTPServer(("127.0.0.1", porta), fazer_handler(app))
    servidor.daemon_threads = True
    app.porta = servidor.server_address[1]
    return servidor


def main(argv=None):
    ap = argparse.ArgumentParser(description="Painel local do tune-up.")
    ap.add_argument("--port", type=int, default=None, help="porta (padrão: painel.json ou 8787)")
    ap.add_argument("--projeto", "--workspace", dest="projeto", default=None,
                    help="raiz do projeto (padrão: $%s, a 1ª pasta com .tune-up/ acima do cwd, "
                         "ou dois níveis acima do painel)" % config.ENV_PROJETO)
    ap.add_argument("--plans-dir", default=None, help="pasta .planning (padrão: painel.json ou procurada)")
    args = ap.parse_args(argv)
    raiz, origem = config.achar_raiz(args.projeto)
    cfg = config.carregar(raiz)
    config.migrar_registro_antigo(cfg)  # registro da versão antiga (<painel>/dados), uma vez
    print("painel: projeto %s (%s, achado por %s)" % (cfg["nome"], raiz, origem), file=sys.stderr)
    leitor._CFG[:] = [cfg]
    for aviso in cfg["avisos"]:
        print("painel: aviso: %s" % aviso, file=sys.stderr)
    app = App(cfg, args.plans_dir)
    servidor = criar_servidor(app, args.port or cfg["porta"])
    print("painel: http://127.0.0.1:%d/  (Ctrl+C para sair)" % app.porta, flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
