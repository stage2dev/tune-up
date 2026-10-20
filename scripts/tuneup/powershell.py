"""tune-up: the PowerShell tool (Windows) through the Bash guard.

How: the command is split into statements (`;`, `|`, `&&`, `||`, newline, and the insides of
`{}`, `()`, `$()`, `@()`), each one rewritten as a Bash simple command and handed to
achados_bash: git/gh/psql/supabase checks, protected files and bash_rules (these read the
original text) work as in Bash. Write cmdlets become `tee <targets>` (Set-Content, Out-File,
Remove-Item, Move-Item, New-Item, Rename-Item...; Copy-Item: the destination; any `-OutFile`,
`-Destination`), Set-Location becomes `cd`, `>`/`>>` stay redirections.

Text check: statements that are not read-only, cd, git or gh count as script code (like
`python -c` in Bash); citing the plugin, a trust word or a protected root asks.

Talk and research modes: only obviously read-only commands pass without a question
(Get-ChildItem/ls/dir/gci, Get-Content/cat/type/gc, Select-String/sls, Test-Path,
Get-Location/pwd/gl, git status/log/diff/show without global options or --output), without
redirection, `$(`/`@(` or any other statement. Everything else asks.

Unparseable (open quote, here-string or block comment, `--%`, `<`) always asks.

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
        elif c == "&" or (c in "$@" and texto[i + 1:i + 2] in ("(", "{") and not tem):
            separa() if c == "&" else fecha()  # call operator / $( @( @{: the bracket splits next
            i += 1
        elif c == "<":
            raise ValueError("'<' is reserved")
        elif c == ">" or (c in "123456*" and texto[i + 1:i + 2] == ">" and not tem):
            m = re.compile(r"[1-6*]?>>?(&[1-6])?").match(texto, i)
            fecha()
            if not m.group(1):
                stmts[-1].append(REDIR)
            i = m.end()
        elif c == "," and not tem:
            i += 1
        elif c == ",":
            fecha()
            i += 1
        else:
            atual, tem = atual + c, True
            i += 1
    fecha()
    if any(t == "--%" for s in stmts for t in s):
        raise ValueError("--% stop-parsing")
    return [s for s in stmts if s]


def nome_cmd(t):
    b = re.split(r"[\\/]", t)[-1].casefold()
    return b[:-4] if b.endswith(".exe") else b


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
            if valor is not None and _e(nome, P_CAMINHO) and not _e(nome, P_VALOR):
                todos.append(valor)
                if _e(nome, P_DESTINO):
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
    return c == "git" and toks[1:2] and toks[1] in GIT_LEITURA and \
        not any(t.startswith(("--output", "--ext-diff", "--textconv")) or t == "-o" for t in toks)


def como_bash(toks):
    """Bash spelling of one statement for achados_bash."""
    c = nome_cmd(toks[0])
    if c in CD:
        todos = caminhos(toks)[0]
        out = ["cd"] + todos[:1]
    elif c in ESCREVE or c in COPIA:
        todos, destino, pos = caminhos(toks, c in SO_PRIMEIRO)
        if c in COPIA:
            todos = destino or pos[-1:] if len(pos) > 1 or destino else []
        out = ["tee"] + todos if todos else []
    else:
        destino = caminhos(toks)[1]
        out = [t for t in toks if t != REDIR] and list(toks)
        if destino:
            return " ".join(_q(t) for t in out) + " ; tee " + " ".join(_q(t) for t in destino)
    if not out:
        return ""
    alvos = [toks[j + 1] for j, t in enumerate(toks[:-1]) if t == REDIR]
    return " ".join(_q(t) for t in out) + "".join(" > " + _q(a) for a in alvos)


def _q(t):
    if t == REDIR:
        return ">"
    t = RE_HOME.sub("~", t) if t[:1] == "$" else t
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
        stmts = instrucoes(cmd.replace("\r\n", "\n"))
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
    if pesquisa and (escreve or "$(" in cmd or "@(" in cmd):
        rotulo = "PowerShell: " + (escreve[0][0] if escreve else curto)
        achados.append(("perguntar", msg("talk_pergunta", rotulo) if conversa else msg("pesquisa", rotulo)))
    return decidir(achados)
