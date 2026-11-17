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
Get-Location/pwd/gl, Select/Where/Sort/Measure-Object, Format-*, Out-Null, git
status/log/diff/show without global options or --output; bare names only, `sort.exe` is a
program; a sort with /o or -o is not), a `Where-Object { $_.x -gt 1 }` body that only compares,
without redirection (one to unquoted $null/NUL is none), `$(`/`@(`, -OutFile/-Destination/
-OutVariable, `& x`/`. x` or any other statement. Everything else asks.

Pipes: a write or copy cmdlet fed by a pipe without a path of its own (`gci x | Remove-Item`),
or one using `$_`, also writes the paths of the statements feeding it; any other consumer that
is not read-only (`gci x | % Delete`) hands them to the text check.

Opened one level, like `eval`/`bash -c`: `iex "<x>"`, `powershell|pwsh [-Command] <x>`,
`cmd /c <x>` (read as Bash: powershell_cmd), a string piped into iex/sh/bash/cmd/powershell,
and `& x` / `. x`. `pwsh -WorkingDirectory d` runs its text after `Set-Location d`.
Unparseable (open quote, here-string or block comment, `--%`, `<`, -EncodedCommand, an unknown
`--x`/`/x` pwsh switch, a NUL, over 300 statements or 50 paths fed into one consumer) always asks.

Limits: no variable, alias or function resolution (`$c = "rm"; & $c x` asks only through
the modes and the text check); a redefined alias (`Set-Alias ls Remove-Item`) is not
tracked; .NET calls (`[IO.File]::WriteAllText(...)`) are seen only by the text check;
`$(...)` inside double quotes is not analysed as a statement. A write whose target is built by a
variable or an expression asks instead (powershell_alvo).
"""
import os
import re
import shlex
from .bash_guarda import nivel_do_texto
from .powershell_alvo import avisos, revisa
from .powershell_cmd import comando_cmd
from .powershell_parse import CHAMA, FILTRO, REDIR, instrucoes, param, previo
from .mensagens import msg
from .sessao import ler_sessao

LEITURA = {"get-childitem", "gci", "ls", "dir", "get-content", "gc", "cat", "type",
           "select-string", "sls", "test-path", "get-location", "gl", "pwd", "select-object", "select",
           "where-object", "where", "?", "sort-object", "sort", "measure-object", "measure", "out-null",
           "format-table", "ft", "format-list", "fl", "format-wide", "fw", "format-custom", "fc"}
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
CHAVES_PS_EXE = VALOR_PS_EXE + ("command", "file", "encodedcommand", "ec", "noprofile", "nop", "noninteractive",
                                "noni", "nologo", "noexit", "sta", "mta", "login", "interactive", "help",
                                "commandwithargs", "cwa", "encodedarguments", "ea", "removeworkingdirectorytrailingcharacter")
MAX_FONTES = 50  # paths fed into one pipe consumer; more cannot be read
MAX_INSTRUCOES = 300  # statements or pipe stages (also cmd pieces); more cannot be read in time
SO_PRIMEIRO = {"set-content", "sc", "add-content", "ac"}  # 2nd positional is -Value, not a path
P_CAMINHO = ("path", "literalpath", "pspath", "lp", "filepath", "destination", "newname",
             "outfile", "destinationpath", "outputfile")
P_DESTINO = ("outfile", "destination", "destinationpath", "outputfile")  # writes in any cmdlet
P_VALOR = ("value", "encoding", "filter", "include", "exclude", "itemtype", "type", "credential",
           "stream", "delimiter", "inputobject", "width", "name", "propertytype", "uri", "method",
           "body", "headers", "message", "pattern", "first", "last", "tail", "totalcount", "depth")
P_COMUM = ("erroraction", "ea", "warningaction", "wa", "informationaction", "infa", "errorvariable", "ev",
           "warningvariable", "wv", "informationvariable", "iv", "outvariable", "ov", "outbuffer", "ob",
           "pipelinevariable", "pv", "progressaction", "proga")  # common parameters: a value, never a path
RE_SORT_SAIDA = re.compile(r"(?i:/o(?:utput)?(?::.*)?)|--o[\w-]*(?:=.*)?|-[bcCdfghiMmnRrsuVz]*[oO].*")
RE_HOME = re.compile(r"\$\{?env:homedrive\}?\$\{?env:homepath\}?|\$\{?env:(?:userprofile|home)(?!\w)\}?|"
                     r"\$\{home\}|\$home(?![\w:])", re.I)
RE_ENV = re.compile(r"\$\{?env:([A-Za-z_]\w*)\}?", re.I)
RE_ENV_ATRIB = re.compile(r"\$\{?env:([A-Za-z_]\w*)\}?(?:=(.*))?", re.I | re.S)


def abre(stmts):
    """One level of the wrappers opened, like `eval`/`bash -c` in Bash: `iex "<x>"`,
    `powershell|pwsh [-Command] <x>`, `cmd /c <x>`, a string piped into iex/sh/bash/cmd/powershell,
    `. x` (dot-source). `-EncodedCommand` cannot be read: ValueError."""
    out = []
    for k, orig in enumerate(stmts):
        s = _sem_chamada(orig)
        c, interno, cru = nome_cmd(s[0]), None, None
        if c in INTERPRETA and len(s) > 1:
            interno = valor_ps(s, "command") or s[-1]
        elif c in ("powershell", "pwsh"):
            interno = comando_ps(s)
        elif c == "cmd":
            cru = comando_cmd(s[1:])
        ant = _sem_chamada(stmts[k - 1]) if k else []
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
            out.extend(le(previo(interno)))
        else:
            out.append(orig)
    if len(out) > MAX_INSTRUCOES:
        raise ValueError("too many statements")
    return out


def _sem_chamada(s):
    """The statement without its `&`/`.` (call operator, dot-source) or FILTRO marker."""
    return s[1:] if s[0] in CHAMA + (FILTRO,) and len(s) > 1 else s


def _ps_q(t):
    return t if re.fullmatch(r"[\w./:~$=@%+,\\-]+", t) else "'" + t.replace("'", "''") + "'"


def _resto(toks):
    """The rest of a powershell command line as command text (one token: the string itself)."""
    return toks[0] if len(toks) == 1 else " ".join(map(_ps_q, toks))


def comando_ps(s):
    """Command text of `powershell|pwsh [options] [-Command] <x>` (`-WorkingDirectory d`: led by
    `Set-Location d;`); None for -File or none. A switch may be written `--x` or `/x` too (an unknown
    one cannot be read: ValueError)."""
    j, wd, texto = 1, None, None
    while j < len(s) and texto is None:
        m = re.fullmatch(r"(?:--|/)([A-Za-z][\w-]*)((?::.*)?)", s[j], re.S)
        if m and not _e(m.group(1).casefold(), CHAVES_PS_EXE):
            raise ValueError("unknown powershell switch")
        pr = param("-" + m.group(1) + m.group(2) if m else s[j])
        if not pr:
            texto = _resto(s[j:])
            break
        p, v = pr
        if "encodedcommand".startswith(p) or p == "ec":
            raise ValueError("-EncodedCommand")
        if "command".startswith(p):
            texto = v if v is not None else _resto(s[j + 1:])
        if "file".startswith(p):
            return None
        if p == "wd" or len(p) > 1 and "workingdirectory".startswith(p):
            wd = v if v is not None else (s[j + 1] if j + 1 < len(s) else None)
        if v is None and _e(p, VALOR_PS_EXE):
            j += 1
        j += 1
    return texto if texto is None or wd is None else "Set-Location %s; %s" % (_ps_q(wd), texto)


def nome_cmd(t):
    b = re.split(r"[\\/]", t)[-1].casefold()
    return b[:-4] if b.endswith(EXTENSOES) else b


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
            leva = _e(nome, P_CAMINHO) or _e(nome, P_VALOR) or _e(nome, P_COMUM)
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
    """Obviously read-only statement (no redirection, -OutFile/-Destination/-OutVariable)."""
    if REDIR in toks or any(pr and (len(pr[0]) > 2 and _e(pr[0], P_DESTINO + ("outvariable",)) or pr[0] == "ov")
                            for pr in map(param, toks[1:])):
        return False
    if toks[0] == FILTRO:  # a comparing Where-Object body
        return True
    c = toks[0].casefold()  # bare names only: `sort.exe`, `C:/x/sort` are programs
    if c in ("sort", "sort-object") and any(RE_SORT_SAIDA.fullmatch(t) for t in toks[1:]):
        return False
    if c in LEITURA:
        return True
    return nome_cmd(c) == "git" and len(toks) > 1 and toks[1] in GIT_LEITURA and \
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
    while toks and toks[0] in CHAMA + (FILTRO,):  # a loop: `. . . x` must not recurse per token
        toks = toks[1:]
    if not toks:
        return ""
    if toks[0] == BASH_CRU:
        return " ".join(toks[1:])
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
    elif c in ("new-item", "ni") and link(toks):
        alvo = valor_ps(toks, "value", True) or valor_ps(toks, "target", True)  # junction/symlink: `ln -s`
        links = [x for x in todos + extras(toks, todos) if x != alvo]
        if not links:
            return " ".join(map(_q, ["tee", alvo or "."]))
        return " ".join(map(_q, ["ln", "-s", "--", alvo or "."] + links)) + " ; " + " ".join(map(_q, ["tee"] + links))
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


CONHECIDOS = LEITURA | ESCREVE | COPIA | CD | INTERPRETA | {"echo", "write-output", "write", "git", "get-item",
                                                       "gi", "%", "foreach", "foreach-object"}
LISTA = {"get-childitem", "gci", "ls", "dir"}
ALIMENTADO = (ESCREVE | COPIA) - {"out-file", "tee-object", "tee", "md", "mkdir"}  # take paths from the pipe
NAO_ALIMENTA = INTERPRETA | SHELLS_SH | CD | {"cmd", "powershell", "pwsh", "git", "gh"}


def alimenta(stmts, tipos):
    """A write cmdlet fed by a pipe with no path of its own, or using `$_`, also gets as `-Path` the
    paths of the statements feeding it (`gci ~/.claude -Recurse | Remove-Item`; with `$_`: all the
    statements before it). Any other consumer that is not read-only gets them too, so the text
    check sees them (`gci ~/.claude -Filter settings.json | % Delete`)."""
    out, valores = [list(s) for s in stmts], {}

    def vals_de(u):  # a statement's own paths, computed once
        if u not in valores:
            valores[u] = fontes_de(stmts[u])
        return valores[u]
    for k, s in enumerate(map(_sem_chamada, stmts)):
        c = nome_cmd(s[0])
        outro = c not in ALIMENTADO and tipos[k] == "|" and c not in NAO_ALIMENTA and not leitura(stmts[k])
        if c not in ALIMENTADO and not outro:
            continue
        if any(re.search(r"\$(_|psitem)(?!\w)", t, re.I) for t in s[1:]) and not outro:
            fontes = range(k)
        elif tipos[k] == "|" and (outro or not caminhos(s)[2] and not any(
                pr and (_e(pr[0], ("path", "literalpath", "pspath")) or pr[0] == "lp") for pr in map(param, s[1:]))):
            j = k - 1
            while j > 0 and tipos[j] != ";":
                j -= 1
            fontes = range(j, k)
        else:
            continue
        vals = list(dict.fromkeys(v for u in fontes for v in vals_de(u)))
        if len(vals) > MAX_FONTES:
            raise ValueError("too many paths fed into a pipe")
        out[k] += [x for v in vals for x in ("-Path", v)]
    return out


def fontes_de(s):
    """The paths a statement hands down a pipe: its own, and for a listing the items below the folder
    (`gci ~/.claude -Filter *.json` -> ~/.claude/*.json)."""
    t = _sem_chamada(s)
    v = ([] if nome_cmd(t[0]) in CONHECIDOS else [t[0]]) + caminhos(t)[0]
    if nome_cmd(t[0]) in LISTA:
        filtro = valor_ps(t, "filter", True) or "*"
        v += [x.replace("\\", "/").rstrip("/") + "/" + filtro for x in (caminhos(t)[2] or ["."])]
    return v


def le(texto):
    """Statements of a PowerShell command, pipes fed into write cmdlets (alimenta), deletes hidden in
    a method call or a ForEach-Object and targets built by a variable (powershell_alvo.revisa)."""
    tipos, metodos = [], []
    stmts = instrucoes(texto, tipos, metodos)
    if len(stmts) > MAX_INSTRUCOES:
        raise ValueError("too many statements")
    return revisa(stmts, tipos, metodos, alimenta(stmts, tipos))


def traduz(stmts):
    """(Bash text for achados_bash, words of the text check: the statements that are not
    read-only, cd, git or gh) of the statements."""
    bash = " ; ".join(x for x in map(como_bash, stmts) if x)
    codigo = [s for s in stmts if not leitura(s) and nome_cmd(s[0]) not in CD | {"git", "gh"}]
    return bash, [RE_HOME.sub("$HOME", t) for s in codigo for t in s if t != REDIR]


def modos(stmts, texto, curto, sess):
    """Talk and research modes: anything not obviously read-only asks (both tools)."""
    conversa = bool(sess.get("modo_conversa"))
    escreve = [s for s in stmts if not leitura(s)]
    if not (sess.get("modo_pesquisa") or conversa) or not (escreve or "$(" in texto or "@(" in texto):
        return []
    s = _sem_chamada(escreve[0]) if escreve else None
    rotulo = "PowerShell: " + (("cmd" if s[0] == BASH_CRU else s[0]) if s else curto)
    return [("perguntar", msg("talk_pergunta", rotulo) if conversa else msg("pesquisa", rotulo))]


def no_bash(toks, sess):
    """Bash tool: what `powershell|pwsh|cmd` asks as the PowerShell tool would (unreadable: ps_ilegivel;
    talk/research modes: modos)."""
    if not toks or nome_cmd(toks[0]) not in ("powershell", "pwsh", "cmd"):
        return []
    curto = " ".join(" ".join(toks).split())[:60]
    try:
        stmts, perguntas = avisos(abre([list(toks)]), curto)
    except ValueError:
        return [("perguntar", msg("ps_ilegivel", curto))]
    return perguntas + modos(stmts, " ".join(toks[1:]), curto, sess)


def do_bash(toks):
    """`powershell|pwsh <x>` / `cmd /c <x>` run from the Bash tool, read as the PowerShell tool
    reads them: (Bash text, text-check words); None for any other command. ValueError: unreadable."""
    if not toks or nome_cmd(toks[0]) not in ("powershell", "pwsh", "cmd"):
        return None
    return traduz(avisos(abre([list(toks)]), "")[0])


def link(toks):
    """New-Item -ItemType|-Type SymbolicLink|Junction|HardLink."""
    tipo = valor_ps(toks, "itemtype", True) or valor_ps(toks, "type", True) or ""
    return bool(re.search(r"link|junc", tipo.casefold()))


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
    curto = " ".join(cmd.replace("\x00", " ").split())[:60]
    try:
        if "\x00" in cmd:  # a NUL could forge the parser's internal markers
            raise ValueError("NUL")
        texto = previo(cmd.replace("\r\n", "\n"))
        stmts, perguntas = avisos(abre(le(texto)), curto)
    except ValueError:
        return decidir([("perguntar", msg("ps_ilegivel", curto))])
    bash, palavras = traduz(stmts)
    achados = achados_bash(bash, d, cfg, regras_em=cmd)
    nivel = nivel_do_texto(palavras, [], d.get("cwd") or os.getcwd(), " ".join(palavras))
    if nivel == "sempre":
        achados.append(("perguntar", msg("prot_settings_bash")))
    elif nivel == "turno":
        pid = d.get("prompt_id")
        if not pid or sess.get("aprender_prompt_id") != pid:
            achados.append(("perguntar", msg("prot_perfil_bash")))
    return decidir(achados + perguntas + modos(stmts, texto, curto, sess))
