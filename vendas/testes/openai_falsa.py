"""OpenAI FALSA em 127.0.0.1 para os testes: guarda cada pedido (caminho, cabeçalhos, corpo) e responde da fila
(código, corpo) ou dorme além do tempo limite do cliente. Nunca fala com a rede de verdade."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def escrever_oferta(projeto, texto="Curso de teste por R$ 100."):
    """Sem oferta.md a IA fica desligada: os testes do cérebro precisam de uma."""
    from servico import conhecimento
    pasta = conhecimento.pasta_vendas(projeto)
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "oferta.md"), "w", encoding="utf-8") as f:
        f.write(texto)


def resposta_texto(texto, entrada=1000, saida=500):
    return 200, {"choices": [{"message": {"role": "assistant", "content": texto}}],
                 "usage": {"prompt_tokens": entrada, "completion_tokens": saida}}


def resposta_ferramenta(nome, argumentos, entrada=1000, saida=100, ident="call_1"):
    return 200, {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
        {"id": ident, "type": "function", "function": {"name": nome, "arguments": json.dumps(argumentos)}}]}}],
        "usage": {"prompt_tokens": entrada, "completion_tokens": saida}}


def erro(status, codigo, mensagem="Incorrect API key provided"):
    return status, {"error": {"message": mensagem, "type": "invalid_request_error", "code": codigo}}


class OpenAIFalsa:
    DORMIR = "dormir"
    CORTADO = "cortado"  # anuncia Content-Length 500, manda 10 bytes e fecha

    def __init__(self):
        self.pedidos = []
        self.fila = []
        self.modelos = ["gpt-4o-mini", "gpt-4.1"]
        falsa = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def _responder(self):
                tamanho = int(self.headers.get("Content-Length") or 0)
                corpo = json.loads(self.rfile.read(tamanho).decode("utf-8")) if tamanho else None
                falsa.pedidos.append({"metodo": self.command, "caminho": self.path,
                                      "cab": dict(self.headers), "corpo": corpo})
                if self.path == "/v1/models" and not falsa.fila:
                    item = (200, {"data": [{"id": m} for m in falsa.modelos]})
                else:
                    item = falsa.fila.pop(0) if falsa.fila else (500, {"error": {"code": "fila_vazia"}})
                if callable(item):  # o teste age NO MEIO da chamada e devolve a resposta
                    item = item()
                if item == OpenAIFalsa.DORMIR:
                    time.sleep(1.5)
                    item = (200, {})
                anunciado = None
                if item == OpenAIFalsa.CORTADO:
                    self.close_connection = True
                    item, dado, anunciado = (200, None), b'{"choices"', 500
                else:
                    dado = json.dumps(item[1]).encode("utf-8")
                try:
                    self.send_response(item[0])
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(anunciado or len(dado)))
                    self.end_headers()
                    self.wfile.write(dado)
                except OSError:
                    pass  # o cliente já desistiu (tempo esgotado)

            do_GET = do_POST = _responder

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.servidor.daemon_threads = True
        self.url = "http://127.0.0.1:%d" % self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def chamadas_chat(self):
        return [p for p in self.pedidos if p["caminho"] == "/v1/chat/completions"]

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()
