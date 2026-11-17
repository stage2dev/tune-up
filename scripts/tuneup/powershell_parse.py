"""tune-up: the PowerShell tokenizer (statements, pipes, redirections) used by powershell.py."""
import re

REDIR = "\x00>"  # marker: `>`/`>>` redirection (the next token is the target)
ASPAS_S = "'‘’‚‛"
ASPAS_D = '"“”„'
NULOS = {"$null", "nul", "nul:", "/dev/null"}  # a redirection there writes no file
CHAMA = ("&", ".")  # call operator / dot-source: a statement's first token, never read-only
FILTRO = "\x00filtro"  # first token of a `Where-Object { a -op b }` body that only compares
ONDE = {"where-object", "where", "?"}
RE_OPERANDO = re.compile(r"\$[\w:]+(\.\w+)*|[\w.*?/:\\~ -]*")  # `$_.Length`, `1`, `x*` (no call, no `=`)
RE_COMPARA = re.compile(r"-[ci]?(eq|ne|gt|ge|lt|le|like|notlike|match|notmatch|contains|notcontains|in|notin)", re.I)


def previo(texto):
    """`$($env:X)` -> `$env:X`; `(Join-Path a b c)` with literal parts -> 'a/b/c'."""
    texto = re.sub(r"\$\(\s*(\$\{?env:\w+\}?|\$home)\s*\)", r"\1", texto, flags=re.I)

    def junta(m):
        try:
            st = instrucoes(m.group(1))
        except ValueError:
            return m.group(0)
        partes = [t.replace("\\", "/") for t in (st[0] if len(st) == 1 else []) if not param(t)]
        if not partes:
            return m.group(0)
        p = "/".join([partes[0].rstrip("/")] + [x.strip("/") for x in partes[1:]])
        return "'" + p.replace("'", "''") + "'"
    return re.sub(r"\(\s*Join-Path\b([^()|;&{}`]*)\)", junta, texto, flags=re.I)


def sem_nulos(toks):
    """Tokens without the redirections to $null / NUL / /dev/null (operator and target)."""
    out, j = [], 0
    while j < len(toks):
        if toks[j] == REDIR and j + 1 < len(toks) and toks[j + 1].casefold() in NULOS:
            j += 2
            continue
        out.append(toks[j])
        j += 1
    return out


def instrucoes(texto, tipos=None, metodos=None):
    """Statements of a PowerShell command, each a list of tokens. ValueError when unreadable.
    `tipos`: list that receives, per statement, '|' (a pipe feeds it), ';' (`;`, newline, `&&`,
    `||`), '{' (a block opened right after the statement before), '(' (a `(`/`$(` opened right
    after it) or 'b' (after `)`, `}` or `&`: the same expression). `metodos`: list that receives,
    per statement, whether it holds a method call (`.Delete(`, `$_.MoveTo(`). `& x` keeps `&` as its first token; a quoted `$null`/`nul`
    redirection target is a file (`./$null`); a comparing Where-Object body starts with FILTRO."""
    stmts, seps, atual, tem, i, n, aspas = [[]], [";"], "", False, 0, len(texto), False
    blocos, com_parenteses, chamadas = [], set(), set()  # open `{`; blocks holding a `(`; method calls

    def fecha():
        nonlocal atual, tem, aspas
        if tem:
            nulo = aspas and stmts[-1][-1:] == [REDIR] and atual.casefold() in NULOS - {"/dev/null"}
            stmts[-1].append("./" + atual if nulo else atual)
        atual, tem, aspas = "", False, False

    def separa(tipo):
        fecha()
        if stmts[-1]:
            stmts.append([])
            seps.append(tipo)
        elif "|" in (tipo, seps[-1]) or ";" in (tipo, seps[-1]):
            seps[-1] = "|" if "|" in (tipo, seps[-1]) else ";"

    while i < n:
        c = texto[i]
        if c in " \t\r":
            fecha()
            i += 1
        elif c == "`":
            if i + 1 >= n:
                raise ValueError("backtick at the end")
            if texto[i + 1] != "\n":
                atual, tem, aspas = atual + texto[i + 1], True, True  # `` `$null ``: a literal name
            i += 2
        elif texto.startswith("<#", i) and not tem:
            j = texto.find("#>", i + 2)
            if j < 0:
                raise ValueError("open block comment")
            i = j + 2
        elif c == "#" and not tem:
            j = texto.find("\n", i)
            i = n if j < 0 else j
        elif c == "@" and texto[i + 1:i + 2] and texto[i + 1] in ASPAS_S + ASPAS_D and \
                re.match(r"[ \t]*\r?\n", texto[i + 2:]):
            q = texto[i + 1]
            m = re.compile(r"\n[ \t]*[%s]@" % re.escape(q)).search(texto, i + 2)
            if not m:
                raise ValueError("open here-string")
            atual, tem, aspas = atual + texto[texto.index("\n", i) + 1:m.start()], True, True
            i = m.end()
        elif c in ASPAS_S:
            j, buf = i + 1, ""
            while True:
                if j >= n:
                    raise ValueError("open quote")
                if texto[j] in ASPAS_S:
                    if texto[j + 1:j + 2] and texto[j + 1] in ASPAS_S:
                        buf, j = buf + "'", j + 2
                        continue
                    break
                buf, j = buf + texto[j], j + 1
            atual, tem, i, aspas = atual + buf, True, j + 1, True
        elif c in ASPAS_D:
            j, buf = i + 1, ""
            while True:
                if j >= n:
                    raise ValueError("open quote")
                if texto[j] == "`" and j + 1 < n:
                    buf, j = buf + texto[j + 1], j + 2
                    continue
                if texto[j] in ASPAS_D:
                    if texto[j + 1:j + 2] and texto[j + 1] in ASPAS_D:
                        buf, j = buf + '"', j + 2
                        continue
                    break
                buf, j = buf + texto[j], j + 1
            atual, tem, i, aspas = atual + buf, True, j + 1, True
        elif c in ";|{}()\n" or texto.startswith("&&", i):
            dois = texto.startswith(("&&", "||"), i)
            metodo = c == "(" and tem and re.search(r"\.\w+$", atual)  # `x.Delete(`: a call on x
            separa("|" if c == "|" and not dois else ("{" if c == "{" else "(" if c == "(" else "b" if c in "})" else ";"))
            if metodo:
                chamadas.add(len(stmts) - 2)
            if c == "{":
                blocos.append(len(stmts) - 1)
            elif c == "}" and blocos:
                blocos.pop()
            elif c == "(":  # `$_ -eq $_.Delete()`: a call, so no block around it only compares
                com_parenteses.update(blocos)
            i += 2 if dois else 1
        elif c == "$" and texto[i + 1:i + 2] == "{":  # ${env:X}: one variable, not a block
            j = texto.find("}", i)
            if j < 0:
                raise ValueError("open ${")
            atual, tem, i = atual + texto[i:j + 1], True, j + 1
        elif c == "&":  # call operator: what follows is a statement of its own, `&` first
            separa("b")
            stmts[-1].append("&")
            i += 1
        elif c in "$@" and texto[i + 1:i + 2] in ("(", "{") and not tem:
            fecha()  # $( @( @{: the bracket splits next
            i += 1
        elif c == "<":
            raise ValueError("'<' is reserved")
        elif c == ">" or (c in "123456*" and texto[i + 1:i + 2] == ">" and not tem):
            m = re.compile(r"[1-6*]?>>?(&[1-6])?").match(texto, i)
            fecha()
            if not m.group(1):
                stmts[-1].append(REDIR)
            i = m.end()
        elif c == ",":  # `Remove-Item a,b`: two paths
            fecha()
            i += 1
        else:
            atual, tem = atual + c, True
            i += 1
    fecha()
    if any(t == "--%" for s in stmts for t in s):
        raise ValueError("--% stop-parsing")
    out = [(sem_nulos(s), t, k in com_parenteses, k in chamadas) for k, (s, t) in enumerate(zip(stmts, seps)) if s]
    out = [x for x in out if x[0] and x[0] != ["&"]]  # `& { x }`: the block's statements
    out = [([FILTRO] + s if t == "{" and not p and k and out[k - 1][0][0].casefold() in ONDE and comparacao(s)
             else s, t, m) for k, (s, t, p, m) in enumerate(out)]
    if tipos is not None:
        tipos.extend(t for _, t, _ in out)
    if metodos is not None:
        metodos.extend(m for _, _, m in out)
    return [s for s, _, _ in out]


def param(t):
    """(parameter name, inline value or None) of `-Name` / `-Name:value`; None when not one."""
    m = re.fullmatch(r"-([A-Za-z][\w-]*)(?::(.*))?", t, re.S)
    return (m.group(1).casefold(), m.group(2)) if m else None


def comparacao(toks):
    """A `{ $_.Length -gt 1 }` block body: operands compared and joined by -and/-or, nothing else."""
    if len(toks) % 4 != 3 or not re.fullmatch(r"\$[\w:]+(\.\w+)*|\d[\d.]*", toks[0]):
        return False  # a bareword first is a command (`Remove-Item -in x` = -Include)
    for j, t in enumerate(toks):
        papel = j % 4
        if papel in (0, 2) and (t.startswith("-") or not RE_OPERANDO.fullmatch(t)):
            return False
        if papel == 1 and not RE_COMPARA.fullmatch(t) or papel == 3 and t.lower() not in ("-and", "-or"):
            return False
    return True
