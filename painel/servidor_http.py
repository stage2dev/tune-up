"""Servidor HTTP do painel: ThreadingHTTPServer com a porta exclusiva no Windows.

No Windows, SO_REUSEADDR deixa um segundo painel abrir a MESMA porta em silêncio
(as requisições caem em qualquer um dos dois). Lá o painel desliga o reuso e pede
SO_EXCLUSIVEADDRUSE: o segundo painel falha com WinError 10048, como no macOS/Linux.
Fora do Windows nada muda. Python 3.9, só biblioteca padrão.
"""
import os
import socket
from http.server import ThreadingHTTPServer


def fazer_classe(nt=None):
    """Classe do servidor; `nt` deixa os testes exercitarem o caminho do Windows."""
    if nt is None:
        nt = os.name == "nt"

    class ServidorPainel(ThreadingHTTPServer):
        allow_reuse_address = not nt
        daemon_threads = True

        def server_bind(self):
            if nt:
                exclusivo = getattr(socket, "SO_EXCLUSIVEADDRUSE", None)
                if exclusivo is not None:
                    self.socket.setsockopt(socket.SOL_SOCKET, exclusivo, 1)
            super().server_bind()

    return ServidorPainel


ServidorPainel = fazer_classe()
