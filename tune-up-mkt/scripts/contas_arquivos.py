"""File side of contas.py: state paths kept inside the project, a short lock, atomic writes, executable lookup.

Stdlib only. No lock is held while the account commands run: only around read-merge-write.
"""
import contextlib
import errno
import json
import os
import tempfile
import time

TRAVA_VELHA = 30  # seconds: an older lock file was left by a killed run and is removed
ESPERA_TRAVA = 5.0


class Recusado(Exception):
    """`.tune-up`, `.tune-up/mkt` or the state file is a symlink or resolves outside the project."""


def caminho(raiz, nome):
    """<raiz>/.tune-up/mkt/<nome>, refusing symlinks on the way and anything resolving outside <raiz>."""
    base = os.path.realpath(raiz)
    atual = base
    for parte in (".tune-up", "mkt", nome):
        atual = os.path.join(atual, parte)
        if os.path.islink(atual):
            raise Recusado()
    if not os.path.realpath(atual).startswith(base.rstrip(os.sep) + os.sep):
        raise Recusado()
    return atual


def ler_json(arquivo):
    """(dict or None, invalid): invalid=True when the file exists but cannot be read as a JSON object."""
    try:
        with open(arquivo, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return None, False
    except (OSError, ValueError):
        return None, True
    return (d, False) if isinstance(d, dict) else (None, True)


def gravar_json(arquivo, dados):
    """Atomic write: temp file in the same folder (0600 on POSIX) + os.replace."""
    pasta = os.path.dirname(arquivo)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=pasta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, arquivo)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


@contextlib.contextmanager
def trava(arquivo, espera=ESPERA_TRAVA):
    """Lock file `<arquivo>.lock` created with O_EXCL; short retry; a lock older than TRAVA_VELHA is stale."""
    nome = arquivo + ".lock"
    fim = time.monotonic() + espera
    while True:
        try:
            os.close(os.open(nome, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            break
        except FileExistsError:
            try:
                if time.time() - os.lstat(nome).st_mtime > TRAVA_VELHA:
                    os.remove(nome)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > fim:
                raise OSError(errno.EBUSY, "another run holds the lock")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(nome)
        except OSError:
            pass


def atualizar(raiz, nome, fazer):
    """Read, fazer(old dict or None) -> new dict, write, all under the lock. Returns (new, old_was_invalid)."""
    arquivo = caminho(raiz, nome)
    os.makedirs(os.path.dirname(arquivo), exist_ok=True)
    with trava(caminho(raiz, nome)):
        arquivo = caminho(raiz, nome)  # checked again: the folder may have changed while waiting
        antigo, ruim = ler_json(arquivo)
        novo = fazer(antigo)
        gravar_json(arquivo, novo)
    return novo, ruim


def achar(nome, raiz, path=None, cwd=None):
    """Executable `nome` on PATH, skipping empty and relative entries, the cwd and the project folder.

    shutil.which on Windows looks in the current folder first, so a `claude.bat` planted in the project
    would run; this walk never does.
    """
    proibidas = {os.path.normcase(os.path.realpath(p)) for p in (cwd or os.getcwd(), raiz)}
    path = os.environ.get("PATH", "") if path is None else path
    exts = [""]
    if os.name == "nt":
        exts = [e for e in os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD").split(os.pathsep) if e]
    for pasta in path.split(os.pathsep):
        if not pasta.strip() or not os.path.isabs(pasta):
            continue
        if os.path.normcase(os.path.realpath(pasta)) in proibidas:
            continue
        for e in exts:
            c = os.path.join(pasta, nome + e)
            if os.path.isfile(c) and os.access(c, os.X_OK):
                return c
    return None
