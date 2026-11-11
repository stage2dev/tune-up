"""Trava do processo (um serviço por projeto) e arquivos de segredo 0600 na pasta de dados.
Trava: flock LOCK_EX|LOCK_NB em POSIX, msvcrt.locking LK_NBLCK no Windows; nunca espera a vez."""
import errno
import os
import secrets


try:
    import fcntl
    msvcrt = None
except ImportError:
    fcntl = None
    import msvcrt

ARQUIVO_TRAVA = "servico.trava"
OCUPADA = {errno.EACCES, errno.EAGAIN, errno.EWOULDBLOCK, getattr(errno, "EDEADLOCK", errno.EDEADLK)}


class TravaOcupada(RuntimeError):
    pass


class TravaDoProcesso:
    """Trava exclusiva NÃO bloqueante, mantida enquanto o processo vive. Ocupada = TravaOcupada na hora."""

    def __init__(self, pasta_dados):
        self.caminho = os.path.join(pasta_dados, ARQUIVO_TRAVA)
        self.fd = None

    def pegar(self):
        fd = os.open(self.caminho, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as e:
            os.close(fd)
            if e.errno in OCUPADA:
                raise TravaOcupada("outro serviço de Vendas já está rodando para este projeto (trava %s)"
                                   % self.caminho)
            raise
        self.fd = fd
        return self

    def soltar(self):
        if self.fd is None:
            return
        try:
            if fcntl is not None:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            else:
                os.lseek(self.fd, 0, os.SEEK_SET)
                msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
        finally:
            os.close(self.fd)
            self.fd = None


def gravar_segredo(caminho, valor):
    """Grava o segredo de forma atômica: temporário 0600 (criado já com esse modo) na mesma pasta + os.replace.
    Falha no meio = o arquivo antigo fica inteiro e o temporário é apagado."""
    temp = "%s.%s.tmp" % (caminho, secrets.token_hex(6))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        try:
            dado = valor.encode("utf-8")
            while dado:
                dado = dado[os.write(fd, dado):]
            os.fsync(fd)
        finally:
            os.close(fd)
        if os.name != "nt":
            os.chmod(temp, 0o600)
        os.replace(temp, caminho)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def ler_segredo(caminho):
    """Segredo já gravado (32 caracteres ou mais), ou None se falta ou é curto demais."""
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            valor = f.read().strip()
        if len(valor) >= 32:
            return valor
    return None


def ler_ou_criar_segredo(caminho):
    """Segredo que sobrevive à reinicialização (o do webhook vai para a configuração da Evolution)."""
    valor = ler_segredo(caminho)
    if valor is not None:
        return valor
    valor = secrets.token_urlsafe(32)
    gravar_segredo(caminho, valor)
    return valor
