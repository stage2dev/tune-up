"""Trava de arquivo do registro do painel: flock em POSIX, msvcrt.locking no Windows."""
import errno
import os
import sys
import time

try:
    import fcntl
    msvcrt = None
except ImportError:
    fcntl = None
    import msvcrt

PRAZO_TRAVA = 90    # s: no Windows, quanto esperar a trava; maior que o maior `rodar` feito sob ela
OCUPADA = {errno.EACCES, getattr(errno, "EDEADLOCK", errno.EDEADLK)}  # o que msvcrt dá com a trava tomada


class _TravaArquivo:
    """Trava exclusiva e bloqueante: vale entre threads (fd próprio) e entre processos.
    POSIX: flock. Windows: msvcrt.locking no 1º byte, tentando até `prazo` segundos."""

    def __init__(self, caminho, prazo=None):
        self.caminho = caminho
        self.prazo = PRAZO_TRAVA if prazo is None else prazo

    def __enter__(self):
        self.fd = os.open(self.caminho, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(self.fd, fcntl.LOCK_EX)
            else:
                self._travar_msvcrt()
        except BaseException:
            os.close(self.fd)
            raise
        return self

    def _travar_msvcrt(self):
        # LK_LOCK desiste sozinho em ~10 s: laço próprio com LK_NBLCK e prazo nosso
        limite = time.monotonic() + self.prazo
        while True:
            os.lseek(self.fd, 0, os.SEEK_SET)
            try:
                msvcrt.locking(self.fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError as e:
                if e.errno not in OCUPADA:
                    raise
                if time.monotonic() >= limite:
                    raise TimeoutError("trava %s ocupada por mais de %s s" % (self.caminho, self.prazo))
                time.sleep(0.05)

    def __exit__(self, tipo, *_):
        try:
            if fcntl is not None:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            else:
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
        except OSError as e:
            if tipo is None:
                raise
            # já há exceção do corpo subindo: ela é a que importa; o fechamento abaixo solta a trava
            print("painel: erro ao destravar %s: %s" % (self.caminho, e), file=sys.stderr)
        finally:
            os.close(self.fd)
