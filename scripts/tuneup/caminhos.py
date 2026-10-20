"""tune-up: compare paths by file identity (case-insensitive disks, hard links, symlinks).

Windows: every path goes through `nativo` first, so the spellings Windows opens as the same
file compare as the same path (Git Bash `/c/x`, `/tmp`, `\\?\`, admin shares, `name.`,
`name:stream`). 8.3 short names (PROGRA~1) are matched by file identity (os.stat) or by
realpath of the existing ancestor; a junction or subst drive the same way."""
import os
import re
import sys

SEM_CAIXA = sys.platform in ("darwin", "win32")  # default disks there ignore letter case
NT = os.name == "nt"
RE_ABS_NT = re.compile(r"[A-Za-z]:[\\/]|[\\/]")
_ESTA_MAQUINA = {}


def absoluto(x):
    """Absolute path for config items: `/x`, `~`, and on Windows `C:\\x`, `C:/x`, `\\\\host\\share`."""
    return x.startswith(("/", "~")) or bool(NT and RE_ABS_NT.match(x))


def temporarios():
    """Shared temp folders that are free in research mode (Windows: %TEMP%, the Git Bash /tmp)."""
    if NT:
        import tempfile
        return [tempfile.gettempdir()]
    return ["/tmp", "/private/tmp"]


def _esta_maquina(host):
    if not _ESTA_MAQUINA:
        import socket
        try:
            _ESTA_MAQUINA[socket.gethostname().casefold()] = True
        except OSError:
            pass
        _ESTA_MAQUINA.update({"localhost": True, "127.0.0.1": True, "::1": True, "[::1]": True, ".": True})
    return host.casefold() in _ESTA_MAQUINA


def nativo(p):
    """Windows: the path as Windows opens it, with / separators. Git Bash `/c/x` -> `C:/x`,
    `/tmp` -> temp dir, `\\\\?\\` and `\\\\.\\` dropped, `\\\\?\\UNC\\h\\s` -> `//h/s`,
    this machine's admin share (`\\\\localhost\\c$\\x`) -> `C:/x`, and in each part the
    `:stream` and the trailing dots and spaces Windows ignores (`settings.json. ` = settings.json).
    Drive-relative `C:x` stays (junta_dir resolves it). Elsewhere: `p` unchanged."""
    if not NT or not isinstance(p, str) or not p:
        return p
    q = p.replace("\\", "/")
    if q[:8].upper() == "//?/UNC/":
        q = "//" + q[8:]
    elif q[:4] in ("//?/", "//./"):
        q = q[4:]
    m = re.match(r"//([^/]+)/([A-Za-z])\$(?=/|$)", q)
    if m and _esta_maquina(m.group(1)):
        q = m.group(2) + ":" + q[m.end():]
    m = re.match(r"/([A-Za-z])(?=/|$)", q)
    if m:
        q = m.group(1).upper() + ":" + (q[2:] or "/")
    elif q == "/tmp" or q.startswith("/tmp/"):
        q = temporarios()[0].replace("\\", "/") + q[4:]
    unidade, resto = os.path.splitdrive(q)
    partes = [x if x in ("", ".", "..") else x.split(":", 1)[0].rstrip(". ") or "."
              for x in resto.split("/")]
    return unidade + "/".join(partes)


def grafia(p):
    """Spelling used to compare paths that do not exist yet."""
    p = os.path.normcase(os.path.normpath(nativo(p)))
    return p.casefold() if SEM_CAIXA else p


def ident(p):
    try:
        st = os.stat(nativo(p))
        return (st.st_dev, st.st_ino)
    except (OSError, ValueError):
        return None


def cadeia(caminho, real=None):
    """(dev, ino) of the real path (when it exists) and of every existing ancestor.
    `real`: realpath(caminho) when the caller already has it."""
    p = real or os.path.realpath(nativo(caminho))
    ids = set()
    while True:
        i = ident(p)
        if i:
            ids.add(i)
        pai = os.path.dirname(p)
        if pai == p:
            return ids
        p = pai


def _prefixo(c, r):
    return c == r or c.startswith(r.rstrip(os.sep) + os.sep)


def dentro(caminho, raiz):
    """`caminho` is `raiz` or below it. Same spelling, or same file (dev, ino) as `raiz` or
    one of its ancestors; when `raiz` does not exist yet, spelling without case on darwin/win32."""
    if not raiz:
        return False
    c = os.path.normpath(nativo(caminho))
    r = os.path.normpath(nativo(os.path.expanduser(raiz)))
    if _prefixo(c, r):
        return True
    ri = ident(r)
    if ri is not None:
        return ri in cadeia(c)
    if SEM_CAIXA:
        for a in {c, os.path.realpath(c)}:
            for b in {r, os.path.realpath(r)}:
                if _prefixo(grafia(a), grafia(b)):
                    return True
    return False


def mesmo(a, b):
    """Same file (identity), or same spelling ignoring case on darwin/win32."""
    ia = ident(a)
    if ia is not None and ia == ident(b):
        return True
    a, b = nativo(a), nativo(b)
    return grafia(a) == grafia(b) or grafia(os.path.realpath(a)) == grafia(os.path.realpath(b))


def nome(p):
    """Base name for comparisons (casefolded on darwin/win32)."""
    b = os.path.basename(os.path.normpath(nativo(p)))
    return b.casefold() if SEM_CAIXA else b
