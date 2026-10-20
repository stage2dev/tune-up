"""tune-up: the PowerShell tool (Windows) through the Bash guard.

How: the command is split into statements (`;`, `|`, `&&`, `||`, newline, and the insides of
`{}`, `()`, `$()`, `@()`), each one rewritten as a Bash simple command and handed to
achados_bash: git/gh/psql/supabase checks, protected files and bash_rules (these read the
original text) work as in Bash. Copy-Item/Move-Item become `cp -r`/`mv`, Remove-Item `rm -r`,
Rename-Item `mv p dirname(p)/new`, Expand-Archive `unzip -d` plus `rm -r <destination>` (it can
replace anything below it); other write cmdlets become `tee <targets>` (Set-Content, Out-File,
New-Item...; any `-OutFile`), Set-Location becomes `cd`, `>`/`>>` stay redirections,
`$env:X` becomes `$X` and `$env:X = v` becomes `export X=v`. Before parsing, `$($env:X)` is read
as `$env:X` and a `(Join-Path a b)` with literal parts as the path `a/b`.

Text check: statements that are not read-only, cd, git or gh count as script code (like
`python -c` in Bash); citing the plugin, a trust word or a protected root asks.

Talk and research modes: only obviously read-only commands pass without a question
(Get-ChildItem/ls/dir/gci, Get-Content/cat/type/gc, Select-String/sls, Test-Path,
Get-Location/pwd/gl, git status/log/diff/show without global options or --output), without
redirection, `$(`/`@(` or any other statement. Everything else asks.

Opened one level, like `eval`/`bash -c`: `iex "<x>"`, `powershell|pwsh [-Command] <x>`,
`cmd /c <x>` (read as Bash, `%X%` as `$X`), a string piped into iex/sh/bash/cmd/powershell, and
`& x` / `. x`.
Unparseable (open quote, here-string or block comment, `--%`, `<`, -EncodedCommand) always asks.

Limits: no variable, alias or function resolution (`$c = "rm"; & $c x` asks only through
the modes and the text check); a redefined alias (`Set-Alias ls Remove-Item`) is not
tracked; .NET calls (`[IO.File]::WriteAllText(...)`) are seen only by the text check;
`$(...)` inside double quotes is not analysed as a statement.
"""
import os
import re
import shlex
from .bash_guarda import nivel_do_texto
from .mensagens import msg
from .sessao import ler_sessao

REDIR = "\x00>"  # marker: `>`/`>>` redirection (the next token is the target)
LEITURA = {"get-childitem", "gci", "ls", "dir", "get-content", "gc", "cat", "type",
           "select-string", "sls", "test-path", "get-location", "gl", "pwd"}
GIT_LEITURA = {"status", "log", "diff", "show"}
CD = {"cd", "chdir", "sl", "set-location", "pushd", "push-location"}
ESCREVE = {"set-content", "sc", "add-content", "ac", "out-file", "tee-object", "tee", "new-item", "ni",
           "md", "mkdir", "remove-item", "rm", "del", "erase", "rd", "rmdir", "ri", "clear-content",
           "clc", "rename-item", "ren", "rni", "move-item", "mv", "move", "mi", "set-item", "si",
           "clear-item", "cli", "new-itemproperty", "set-itemproperty", "sp", "remove-itemproperty", "rp"}
COPIA = {"copy-item", "cp", "copy", "cpi"}
MOVE = {"move-item", "mv", "move", "mi"}
REMOVE = {"remove-item", "rm", "del", "erase", "rd", "rmdir", "ri"}
RENOMEIA = {"rename-item", "ren", "rni"}
INTERPRETA = {"iex", "invoke-expression"}
SHELLS_SH = {"bash", "sh", "zsh"}
EXTENSOES = (".exe", ".cmd", ".bat", ".ps1", ".com")
BASH_CRU = "\x00bash"  # marker statement [BASH_CRU, text]: text goes to achados_bash as it is
VALOR_PS_EXE = ("executionpolicy", "ep", "windowstyle", "outputformat", "inputformat", "configurationname",
                "workingdirectory", "wd", "version", "psconsolefile", "settingsfile", "custompipename")
SO_PRIMEIRO = {"set-content", "sc", "add-content", "ac"}  # 2nd positional is -Value, not a path
P_CAMINHO = ("path", "literalpath", "pspath", "lp", "filepath", "destination", "newname",
             "outfile", "destinationpath", "outputfile")
P_DESTINO = ("outfile", "destination", "destinationpath", "outputfile")  # writes in any cmdlet
P_VALOR = ("value", "encoding", "filter", "include", "exclude", "itemtype", "type", "credential",
           "stream", "delimiter", "inputobject", "width", "name", "propertytype", "uri", "method",
           "body", "headers", "message", "pattern", "first", "last", "tail", "totalcount", "depth")
ASPAS_S = "'‘’‚‛"
ASPAS_D = '"“”„'
RE_HOME = re.compile(r"\$\{?env:(userprofile|home)\}?|\$\{home\}|\$home(?![\w:])", re.I)
RE_ENV = re.compile(r"\$\{?env:([A-Za-z_]\w*)\}?", re.I)
RE_ENV_ATRIB = re.compile(r"\$\{?env:([A-Za-z_]\w*)\}?(?:=(.*))?", re.I | re.S)


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


def instrucoes(texto):
    """Statements of a PowerShell command, each a list of tokens. ValueError when unreadable."""
    stmts, atual, tem, i, n = [[]], "", False, 0, len(texto)

    def fecha():
        nonlocal atual, tem
        if tem:
            stmts[-1].append(atual)
        atual, tem = "", False

    def separa():
        fecha()
        if stmts[-1]:
            stmts.append([])

    while i < n:
        c = texto[i]
        if c in " \t\r":
            fecha()
            i += 1
        elif c == "`":
            if i + 1 >= n:
                raise ValueError("backtick at the end")
            if texto[i + 1] != "\n":
                atual, tem = atual + texto[i + 1], True
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
            atual, tem = atual + texto[texto.index("\n", i) + 1:m.start()], True
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
            atual, tem, i = atual + buf, True, j + 1
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
            atual, tem, i = atual + buf, True, j + 1
        elif c in ";|{}()\n" or texto.startswith("&&", i):
            separa()
            i += 2 if texto.startswith(("&&", "||"), i) else 1
        elif c == "$" and texto[i + 1:i + 2] == "{":  # ${env:X}: one variable, not a block
            j = texto.find("}", i)
            if j < 0:
                raise ValueError("open ${")
            atual, tem, i = atual + texto[i:j + 1], True, j + 1
        elif c == "&":  # call operator: what follows is a statement of its own
            separa()
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
    return [s for s in stmts if s]


def abre(stmts):
    """One level of the wrappers opened, like `eval`/`bash -c` in Bash: `iex "<x>"`,
    `powershell|pwsh [-Command] <x>`, `cmd /c <x>`, a string piped into iex/sh/bash/cmd/powershell,
    `. x` (dot-source). `-EncodedCommand` cannot be read: ValueError."""
    out = []
    for k, s in enumerate(stmts):
        if s[0] == "." and len(s) > 1:
            s = s[1:]
        c, interno, cru = nome_cmd(s[0]), None, None
        if c in INTERPRETA and len(s) > 1:
            interno = valor_ps(s, "command") or s[-1]
        elif c in ("powershell", "pwsh"):
            interno = comando_ps(s)
        elif c == "cmd":
            cru = comando_cmd(s[1:])
        ant = stmts[k - 1] if k else []
        if len(s) == 1 and ant and c in INTERPRETA | SHELLS_SH | {"cmd", "powershell", "pwsh"}:
            texto = ant[0] if len(ant) == 1 else (" ".join(ant[1:]) if nome_cmd(ant[0]) in (
                "echo", "write-output", "write") else None)  # `"x" | iex`, `echo x | bash`
            if texto is not None and c in SHELLS_SH:
                cru = texto
            elif texto is not None and c == "cmd":
                cru = comando_cmd(["/c", texto])
            elif texto is not None:
                interno = texto
        if cru is not None:
            out.append([BASH_CRU, cru])
        elif interno:
            out.extend(instrucoes(previo(interno)))
        else:
            out.append(s)
    return out


def _ps_q(t):
    return t if re.fullmatch(r"[\w./:~$=@%+,\\-]+", t) else "'" + t.replace("'", "''") + "'"


def _resto(toks):
    """The rest of a powershell command line as command text (one token: the string itself)."""
    return toks[0] if len(toks) == 1 else " ".join(map(_ps_q, toks))


def comando_ps(s):
    """Command text of `powershell|pwsh [options] [-Command] <x>`; None for -File or none."""
    j = 1
    while j < len(s):
        pr = param(s[j])
        if not pr:
            return _resto(s[j:])
        p, v = pr
        if "encodedcommand".startswith(p) or p == "ec":
            raise ValueError("-EncodedCommand")
        if "command".startswith(p):
            return v if v is not None else _resto(s[j + 1:])
        if "file".startswith(p):
            return None
        if v is None and _e(p, VALOR_PS_EXE):
            j += 1
        j += 1
    return None


def comando_cmd(args):
    """Bash text of `cmd /c|/k <x>` (`%X%` -> `$X`, `^` escapes dropped), or None."""
    for j, t in enumerate(args):
        if re.fullmatch(r"/{1,2}[cCkK]", t):
            resto = args[j + 1:]
            if not resto:
                return None
            x = resto[0] if len(resto) == 1 else " ".join(shlex.quote(r) if re.search(r"\s", r) else r for r in resto)
            return re.sub(r"\^(.)", r"\1", re.sub(r"%(\w+)%", r"$\1", x))
    return None


def nome_cmd(t):
    b = re.split(r"[\\/]", t)[-1].casefold()
    return b[:-4] if b.endswith(EXTENSOES) else b


def param(t):
    """(parameter name, inline value or None) of `-Name` / `-Name:value`; None when not one."""
    m = re.fullmatch(r"-([A-Za-z][\w-]*)(?::(.*))?", t, re.S)
    return (m.group(1).casefold(), m.group(2)) if m else None


def _e(p, nomes):  # PowerShell accepts any unique prefix of a parameter name
    return any(x.startswith(p) for x in nomes)


def caminhos(toks, so_primeiro=False):
    """(path parameters and positionals, destinations: -OutFile/-Destination...) of a statement."""
    todos, destino, pos, j = [], [], [], 1
    while j < len(toks):
        t = toks[j]
        pr = param(t) if t != REDIR else None
        if pr:
            nome, valor = pr
            leva = _e(nome, P_CAMINHO) or _e(nome, P_VALOR)
            if valor is None and leva and j + 1 < len(toks):
                valor, j = toks[j + 1], j + 1
            if valor is not None and _e(nome, P_CAMINHO):  # ambiguous (-f, -d): a path too
                todos.append(valor)
                if _e(nome, P_DESTINO) and not _e(nome, P_VALOR):
                    destino.append(valor)
        elif t == REDIR:
            j += 1
        else:
            pos.append(t)
        j += 1
    return todos + (pos[:1] if so_primeiro else pos), destino, pos


def leitura(toks):
    """Obviously read-only statement (no redirection)."""
    if REDIR in toks:
        return False
    c = nome_cmd(toks[0])
    if c in LEITURA:
        return True
    return c == "git" and len(toks) > 1 and toks[1] in GIT_LEITURA and \
        not any(t.startswith(("--output", "--ext-diff", "--textconv")) or t == "-o" for t in toks)


def valor_ps(toks, nome, prefixo=False):
    """Value of `-<nome>` / `-<nome>:v` (full name; `prefixo`: any prefix), or None."""
    for j, t in enumerate(toks):
        pr = param(t)
        if pr and (pr[0] == nome or prefixo and nome.startswith(pr[0])):
            return pr[1] if pr[1] is not None else (toks[j + 1] if j + 1 < len(toks) else None)
    return None


def como_bash(toks):
    """Bash spelling of one statement for achados_bash."""
    if toks[0] == BASH_CRU:
        return toks[1]
    m = RE_ENV_ATRIB.fullmatch(toks[0])
    if m and (m.group(2) is not None or toks[1:2] == ["="] or toks[1:2] and toks[1].startswith("=")):
        valor = m.group(2) if m.group(2) is not None else (
            (toks[2] if len(toks) > 2 else "") if toks[1] == "=" else toks[1][1:])
        return "export %s=%s" % (m.group(1).upper(), _q(valor))  # `$env:PGHOST = "h"`
    c = nome_cmd(toks[0])
    redir = [x for j, t in enumerate(toks[:-1]) if t == REDIR for x in (REDIR, toks[j + 1])]
    todos, destino, pos = caminhos(toks, c in SO_PRIMEIRO)
    if c in CD:
        out = ["cd"] + todos[:1]
    elif c in COPIA or c in MOVE:
        dest = destino[-1] if destino else (pos[-1] if len(pos) > 1 else ".")
        fontes = [x for x in todos if x != dest]
        out = (["cp", "-r"] if c in COPIA else ["mv"]) + ["--"] + fontes + [dest] if fontes else []
    elif c in REMOVE:
        out = ["rm", "-r", "--"] + todos if todos else []
    elif c in RENOMEIA:
        novo = valor_ps(toks, "newname", True) or (pos[1] if len(pos) > 1 else None)
        velho = ([x for x in todos if x != novo] or [None])[0]
        base = (velho or "").replace("\\", "/").rstrip("/")
        out = ["mv", "--", velho, (base.rsplit("/", 1)[0] if "/" in base else ".") + "/" + novo] \
            if velho and novo else (["tee"] + todos if todos else [])
    elif c == "expand-archive":
        fonte = valor_ps(toks, "path", True) or valor_ps(toks, "literalpath", True) or (pos[:1] or ["x.zip"])[0]
        dest = valor_ps(toks, "destinationpath", True) or (pos[1] if len(pos) > 1 else ".")
        return " ".join(map(_q, ["unzip", fonte, "-d", dest])) + " ; rm -r -- " + _q(dest)
    elif c in ESCREVE:
        alvos = todos + extras(toks, todos) + redir[1::2]
        out = ["tee"] + alvos if alvos else []
        redir = []
    else:
        sem = [t for j, t in enumerate(toks) if t != REDIR and (j == 0 or toks[j - 1] != REDIR)]
        out = " ".join(map(_q, sem + redir))
        return out + (" ; tee " + " ".join(map(_q, destino)) if destino else "")
    if not out:
        return " ".join(map(_q, ["true"] + redir)) if redir else ""
    return " ".join(map(_q, out + redir))


def extras(toks, todos):
    """New-Item -Path d -Name n -> d/n."""
    nome = valor_ps(toks, "name")
    base = (todos or ["."])[0].replace("\\", "/").rstrip("/")
    return [base + "/" + nome] if nome else []


def _q(t):
    if t == REDIR:
        return ">"
    t = RE_ENV.sub(lambda m: "$" + m.group(1).upper(), RE_HOME.sub("~", t) if t[:1] == "$" else t)
    if t.startswith("~"):
        return "~" + shlex.quote(t[1:]) if t[1:] else "~"
    return shlex.quote(t)


def ev_powershell(cmd, d, cfg):
    from .bash import achados_bash, decidir
    sess = ler_sessao(d.get("session_id"))
    conversa = bool(sess.get("modo_conversa"))
    pesquisa = bool(sess.get("modo_pesquisa")) or conversa
    curto = " ".join(cmd.split())[:60]
    try:
        texto = previo(cmd.replace("\r\n", "\n"))
        stmts = abre(instrucoes(texto))
    except ValueError:
        return decidir([("perguntar", msg("ps_ilegivel", curto))])
    achados = achados_bash(" ; ".join(x for x in map(como_bash, stmts) if x), d, cfg, regras_em=cmd)
    codigo = [s for s in stmts if not leitura(s) and nome_cmd(s[0]) not in CD | {"git", "gh"}]
    palavras = [RE_HOME.sub("$HOME", t) for s in codigo for t in s if t != REDIR]
    nivel = nivel_do_texto(palavras, [], d.get("cwd") or os.getcwd(), " ".join(palavras))
    if nivel == "sempre":
        achados.append(("perguntar", msg("prot_settings_bash")))
    elif nivel == "turno":
        pid = d.get("prompt_id")
        if not pid or sess.get("aprender_prompt_id") != pid:
            achados.append(("perguntar", msg("prot_perfil_bash")))
    escreve = [s for s in stmts if not leitura(s)]
    if pesquisa and (escreve or "$(" in texto or "@(" in texto):
        rotulo = "PowerShell: " + (escreve[0][0] if escreve else curto)
        achados.append(("perguntar", msg("talk_pergunta", rotulo) if conversa else msg("pesquisa", rotulo)))
    return decidir(achados)
