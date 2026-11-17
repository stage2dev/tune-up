"""tune-up: PowerShell writes the guard cannot follow by itself (used by powershell.le).

- A method call on what a bracketed statement read (`(dir x).Delete()`) and a ForEach-Object
  consumer that is not a plain property read (`gci x | % Delete`, `% { $_.MoveTo(...) }`) are read
  as `Remove-Item` of those paths (a synthetic statement right after it).
- A write, copy, remove or New-Item whose target is built by a variable (other than $HOME/$env:X
  and the piped item `$_`), a `$(...)`, a .NET call (`::`) or a `(...)` subexpression asks
  (ps_alvo_variavel): the guard does not resolve variables.
"""
import re
from .mensagens import msg
from .powershell_parse import param

AVISO = "\x00aviso"  # marker statement [AVISO]: a write target the guard cannot read (asks)
POR_ITEM = {"%", "foreach", "foreach-object"}
PROPRIEDADES = {"name", "fullname", "basename", "extension", "length", "lastwritetime", "lastwritetimeutc",
                "creationtime", "lastaccesstime", "directory", "directoryname", "parent", "mode", "exists",
                "attributes", "pspath", "psparentpath", "pschildname", "psiscontainer", "linktype", "target",
                "count", "versioninfo", "isreadonly", "root"}  # `% Name`: a read, not a method
RE_ITEM = re.compile(r"\$(_|psitem)(\.\w+)*", re.I)  # `$_`, `$_.Name`
RE_ITEM_CAMINHO = re.compile(r"\$(_|psitem)(\.(fullname|pspath))?", re.I)  # the piped item's own path


def avisos(stmts, curto):
    """(statements without AVISO markers, the question when there was one)."""
    limpos = [s for s in stmts if s[:1] != [AVISO]]
    return limpos, ([("perguntar", msg("ps_alvo_variavel", curto))] if len(limpos) < len(stmts) else [])


def variavel(t):
    """A path token the guard cannot read: `$x`, `$(...)`, `[X]::Y` (not $HOME, $env:X, $_)."""
    from .powershell import RE_ENV, RE_HOME
    if "$(" in t or "::" in t:
        return True
    return "$" in RE_ENV.sub("", RE_HOME.sub("", t)) and not RE_ITEM_CAMINHO.fullmatch(t)


def _cabeca(stmts, tipos, k):
    """The write cmdlet statement an argument statement belongs to (back past `(`, `)`), or None."""
    from .powershell import COPIA, ESCREVE, _sem_chamada, nome_cmd
    j = k
    while True:
        if nome_cmd(_sem_chamada(stmts[j])[0]) in ESCREVE | COPIA | {"expand-archive"}:
            return j
        if j == 0 or tipos[j] not in "(b":
            return None
        j -= 1


def _so_valor(cab, toks):
    """The statement before a `(...)` ends in a parameter that takes a value, not a path."""
    from .powershell import P_CAMINHO, P_COMUM, P_VALOR, SO_PRIMEIRO, _e, _sem_chamada, caminhos, link, nome_cmd
    pr = param(toks[-1])
    if pr:
        lnk = link(cab) and _e(pr[0], ("value", "target"))
        return not lnk and not _e(pr[0], P_CAMINHO) and (_e(pr[0], P_VALOR) or _e(pr[0], P_COMUM))
    c = nome_cmd(_sem_chamada(cab)[0])  # `Set-Content x (Get-Date)`: the 2nd positional is the value
    return toks is cab and c in SO_PRIMEIRO and bool(caminhos(_sem_chamada(cab), True)[0])


def _ilegivel(stmts, tipos, out, k):
    """Statement k is (or adds to) a write whose target the guard cannot read."""
    from .powershell import SO_PRIMEIRO, _sem_chamada, caminhos, link, nome_cmd, valor_ps
    h = _cabeca(stmts, tipos, k)
    if h is None:
        return False
    cab = _sem_chamada(stmts[h])
    if h == k:
        alvos = caminhos(_sem_chamada(out[k]), nome_cmd(cab[0]) in SO_PRIMEIRO)[0]
        if link(cab):
            alvos += [x for x in (valor_ps(cab, "value", True), valor_ps(cab, "target", True)) if x]
        return any(variavel(t) for t in alvos)
    if tipos[k] == "b" and stmts[k][0].startswith("-"):  # `-Path $x` after a `(...)`
        return any(variavel(t) for t in caminhos(["_"] + stmts[k])[0])
    ant = stmts[k - 1]
    if tipos[k] == "(" and (k - 1 == h or tipos[k - 1] == "b" and ant[0].startswith("-")):
        return not _so_valor(cab, cab if k - 1 == h else ant)
    return False


def _le_item(stmts, tipos, metodos, k):
    """A ForEach-Object consumer that only reads: `% Name`, `% { $_.FullName }`."""
    from .powershell import _sem_chamada
    args = [t for t in _sem_chamada(stmts[k])[1:] if not (param(t) and "membername".startswith(param(t)[0]))]
    if args:
        return len(args) == 1 and args[0].casefold() in PROPRIEDADES
    n = len(stmts)
    return k + 1 < n and tipos[k + 1] == "{" and not metodos[k + 1] and \
        all(RE_ITEM.fullmatch(t) for t in stmts[k + 1]) and (k + 2 >= n or tipos[k + 2] in "|b")


def _apaga(stmts, fontes):
    """Synthetic `Remove-Item -Path <the paths of the statements in fontes>`, or None."""
    from .powershell import MAX_FONTES, fontes_de
    vals = list(dict.fromkeys(v for u in fontes for v in fontes_de(stmts[u])))
    if len(vals) > MAX_FONTES:
        raise ValueError("too many paths fed into a delete")
    return ["remove-item"] + [x for v in vals for x in ("-Path", v)] if vals else None


def revisa(stmts, tipos, metodos, out):
    """`out` (the statements after alimenta) with the synthetic deletes inserted and an AVISO marker
    at the end when a write target cannot be read."""
    from .powershell import _sem_chamada, nome_cmd
    novo, aviso, ultimo = [], False, None  # ultimo: (pipe start, index in novo) of the last ForEach delete
    for k, s in enumerate(stmts):
        novo.append(out[k])
        aviso = aviso or _ilegivel(stmts, tipos, out, k)
        extra = None
        if metodos[k] and s[0].startswith(".") and k:  # `(dir x).Delete()`: the bracketed statements
            j = k - 1
            while j > 0 and tipos[j] in "(b":
                j -= 1
            extra = _apaga(stmts, range(j, k))
        elif tipos[k] == "|" and nome_cmd(_sem_chamada(s)[0]) in POR_ITEM and not _le_item(stmts, tipos, metodos, k):
            j = k - 1  # the same sources as alimenta
            while j > 0 and tipos[j] != ";":
                j -= 1
            extra = _apaga(stmts, range(j, k))
            if extra and ultimo and ultimo[0] == j:  # `| % a | % b`: one delete, of all the pipe's paths
                del novo[ultimo[1]]
            ultimo = (j, len(novo)) if extra else ultimo
        if extra:
            novo.append(extra)
    return novo + ([[AVISO]] if aviso else [])
