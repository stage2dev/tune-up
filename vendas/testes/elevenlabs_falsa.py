"""ElevenLabs FALSA em 127.0.0.1 para os testes: guarda cada pedido (caminho, cabeçalhos, corpo JSON) e responde da
fila (código, bytes ou objeto JSON); fila vazia = `padrao`. Nunca fala com a rede de verdade."""
import json
import shutil
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def mp3_de_teste(caminho):
    """1 s de seno gerado pelo ffmpeg (lavfi) em mp3, como a resposta da ElevenLabs. None sem ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=1", "-ac", "2", "-ar", "44100", "-c:a", "libmp3lame", "-b:a", "128k",
                    caminho], check=True, stdin=subprocess.DEVNULL, timeout=60)
    with open(caminho, "rb") as f:
        return f.read()


class ElevenLabsFalsa:
    def __init__(self, padrao=(200, b"ID3-falso")):
        self.pedidos = []
        self.fila = []
        self.padrao = padrao
        falsa = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                tamanho = int(self.headers.get("Content-Length") or 0)
                bruto = self.rfile.read(tamanho) if tamanho else b""
                falsa.pedidos.append({"caminho": self.path, "cabecalhos": {k.lower(): v for k, v in self.headers.items()},
                                      "corpo": json.loads(bruto.decode("utf-8")) if bruto else None})
                codigo, corpo = falsa.fila.pop(0) if falsa.fila else falsa.padrao
                if not isinstance(corpo, bytes):
                    corpo = json.dumps(corpo).encode("utf-8")
                self.send_response(codigo)
                self.send_header("Content-Length", str(len(corpo)))
                self.end_headers()
                self.wfile.write(corpo)

        self.servidor = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d" % self.servidor.server_address[1]
        threading.Thread(target=self.servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()
