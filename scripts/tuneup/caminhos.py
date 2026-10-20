"""tune-up: compare paths by file identity (case-insensitive disks, hard links, symlinks)."""
import os
import sys

SEM_CAIXA = sys.platform in ("darwin", "win32")  # default disks there ignore letter case


def grafia(p):
    """Spelling used to compare paths that do not exist yet."""
    p = os.path.normcase(os.path.normpath(p))
    return p.casefold() if SEM_CAIXA else p


def ident(p):
    try:
        st = os.stat(p)
        return (st.st_dev, st.st_ino)
    except (OSError, ValueError):
        return None


def cadeia(caminho, real=None):
    """(dev, ino) of the real path (when it exists) and of every existing ancestor.
    `real`: realpath(caminho) when the caller already has it."""
    p = real or os.path.realpath(caminho)
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
    c = os.path.normpath(caminho)
    r = os.path.normpath(os.path.expanduser(raiz))
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
    return grafia(a) == grafia(b) or grafia(os.path.realpath(a)) == grafia(os.path.realpath(b))


def nome(p):
    """Base name for comparisons (casefolded on darwin/win32)."""
    b = os.path.basename(os.path.normpath(p))
    return b.casefold() if SEM_CAIXA else b
