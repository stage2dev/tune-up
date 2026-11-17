"""tune-up: the Bash command text as the tokenizer (shlex) can read it.

shlex does not know `$'...'`, comments, heredocs or `$(...)` inside double quotes: it pairs the
quotes differently from Bash and a command can end up inside what it takes for a string. `legivel`
follows the quoting as Bash does and rewrites those parts. When in doubt it hides nothing."""
import re

RE_ANSI_NUM = re.compile(r"x([0-9A-Fa-f]{1,2})|u([0-9A-Fa-f]{1,4})|U([0-9A-Fa-f]{1,8})|([0-7]{1,3})")
RE_CASE = re.compile(r"(case|esac)(?![\w-])")
RE_ANTES_DE_COMANDO = re.compile(r"(do|then|else|elif|if|while|until|time|!|\{)(?=[ \t\n;]|$)")
ANSI = {"a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
        "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
INICIA_PALAVRA = " \t;|&()<>"  # after one of these (or a newline) a `#` opens a comment
OUTRA = "\x00escopo"  # = bash_parse.ESCOPO: a marker line `OUTRA +` / `OUTRA -` around a second reading
MAX_NIVEL = 25  # nested `"$( "$( ..."`: past this the text is handed over as commands


def legivel(cmd):
    """The command without heredoc bodies, comments and `\\<newline>`; each `$'...'` as a plain
    quoted word and `$"x"` as `"x"`; a double-quoted string shlex would misread as a single-quoted
    one. The command substitutions Bash runs where shlex does not split (inside double quotes, in
    the body of an unquoted heredoc, between backticks) come after the text, one per line.
    Two things can be read two ways: `<<` inside `((...))`, `${...}`, `$[...]` or `name[...]` (a
    shift or a heredoc) and `\\<CR><LF>` (joins two lines or not). Then both readings are given,
    each between OUTRA marker lines (bash_parse reads them as ESCOPO: a `cd` of one reading does
    not reach the other). An unclosed quote is closed at the end of the text.
    Where this reader may not pair the quotes as Bash does (something left unclosed, quotes inside
    `"${...}"`, a heredoc word with an expansion, a heredoc without its end line) one more reading
    is given: the text split at every separator, quotes ignored (`_cego`)."""
    del _DUVIDA[:]
    leituras = list(dict.fromkeys([_leitura(cmd, False), _leitura(cmd, True)]))
    if _DUVIDA:
        cego = _cego(cmd)  # a `cd` there may be inside a `$(...)`: also read without any `cd`
        leituras += [cego, re.sub(r"(?<![\w./-])(cd|pushd|popd)(?![\w./-])", "true", cego)]
    leituras = list(dict.fromkeys(leituras))  # before a marker line, a last `\` would eat its line end
    return "".join("%s +\n%s\n%s -\n" % (OUTRA, x + " " * x.endswith("\\"), OUTRA) for x in leituras[:-1]) + leituras[-1]


_DUVIDA = []  # filled while one command is read: why the quote pairing may be wrong


def _cego(cmd):
    """The text with no quoting at all: `\\<newline>` joined, then every `$(`, backtick and `#` that
    starts a word ends a command, and every quote and backslash ends a word."""
    t = re.sub(r"\$\(|`|(?<![^\s;|&()])#", " ; ", cmd.replace("\\\n", ""))
    return re.sub(r"['\"\\]", " ", t)


def _leitura(cmd, solto):
    texto, extras = _codigo(cmd, 0, False, 0, solto)[:2]
    return texto + "".join("\n" + e for e in extras if e.strip())


def _delimitador(cmd, i):
    """The heredoc word at `i` (after `<<` or `<<-`), as Bash removes its quotes.
    -> (word, the body expands, index after it) or None."""
    n = len(cmd)
    while i < n and cmd[i] in " \t":
        i += 1
    partes, citado, j = [], False, i
    while j < n and cmd[j] not in " \t\n;|&()<>":
        c = cmd[j]
        k = j + 1
        if c == "\\" and k < n:
            partes.append("" if cmd[k] == "\n" else cmd[k])
            citado, j = citado or cmd[k] != "\n", k + 1
            continue
        if c in "$`" and cmd[k:k + 1] not in ("'", '"'):  # `<<$(x)`, `<<$X`: Bash takes it literally
            _DUVIDA.append("heredoc word")
            return None
        if c == "$" and cmd[k:k + 1] == '"':
            j, c, k = k, '"', k + 1
        if c == "'" or cmd.startswith("$'", j):
            k += c == "$"
            a = k
            while k < n and cmd[k] != "'":
                k += 2 if c == "$" and cmd[k] == "\\" else 1
            partes.append(ansi_c(cmd[a:k]) if c == "$" else cmd[a:k])
        elif c == '"':
            while k < n and cmd[k] != '"':
                k += 2 if cmd[k] == "\\" else 1
            partes.append(re.sub(r'\\([$`"\\])', r"\1", cmd[j + 1:k]))
        else:
            partes.append(c)
            j += 1
            continue
        if k >= n:
            _DUVIDA.append("heredoc word")
            return None
        citado, j = True, k + 1
    if cmd[j:j + 1] == "(":
        _DUVIDA.append("heredoc word")
        return None
    return ("".join(partes), not citado, j) if j > i else None


def _q(s):
    return "'" + s.replace("'", "'\\''") + "'"


def ansi_c(corpo):
    """The text of a Bash `$'...'` string (body without the quotes); cut at a NUL, as Bash does."""
    out, i = [], 0
    while i < len(corpo):
        c, d = corpo[i], corpo[i + 1:i + 2]
        m = RE_ANSI_NUM.match(corpo, i + 1) if c == "\\" else None
        if c != "\\" or not d:
            out.append(c)
            i += 1
        elif d in ANSI:
            out.append(ANSI[d])
            i += 2
        elif d == "c" and corpo[i + 2:i + 3]:
            out.append(chr(ord(corpo[i + 2]) & 0x1F))
            i += 3
        elif m:
            v = int(m.group(4), 8) & 0xFF if m.group(4) else int(m.group(1) or m.group(2) or m.group(3), 16)
            out.append(chr(v) if v < 0xD800 or 0xDFFF < v < 0x110000 else "?")
            i = m.end()
        else:
            out.append(c + d)
            i += 2
    return "".join(out).split("\x00")[0]


def _crase(cmd, i, nivel, solto, aspas=False):
    """Backtick substitution opened at `i` (`aspas`: inside double quotes, where `\\"` is a quote).
    -> (command texts, index after it)."""
    j, n = i + 1, len(cmd)
    while j < n and cmd[j] != "`":
        j += 2 if cmd[j] == "\\" else 1
    if j >= n:
        _DUVIDA.append("backtick")
    corpo = re.sub(r'\\([`\\$"])' if aspas else r"\\([`\\$])", r"\1", cmd[i + 1:j])
    t, ex = _codigo(corpo, 0, False, nivel + 1, solto)[:2] if nivel < MAX_NIVEL else (corpo, [])
    return [t] + ex, min(j + 1, n)


def _expande(cmd, i, aspas, nivel, solto):
    """Text where Bash expands but does not split: a double-quoted string from `i` (after the
    opening quote, `aspas`) or a whole heredoc body. -> (its value before expansion, substitutions
    as command texts, index after it, shlex reads it the same way, closed)."""
    lit, bruto, extras, n, igual = [], [], [], len(cmd), True  # bruto: as written, without heredoc bodies
    while i < n:
        c, d = cmd[i], cmd[i + 1:i + 2]
        if c == '"' and aspas:
            return "".join(lit), extras, i + 1, igual, True, "".join(bruto)
        if c == "\\" and d:
            if d in '$`"\\' or d == "\n":
                igual = igual and d in '"\\'
                lit.append("" if d == "\n" else d)
            else:
                lit.append(c + d)
            bruto.append(c + d)
            i += 2
        elif c == "$" and d == "(":
            if d == "(" and cmd[i + 2:i + 3] == "(" and "<<" in cmd[i:]:
                _DUVIDA.append("arithmetic")  # `"$((1<<2` is read below as a command with a heredoc
            if nivel >= MAX_NIVEL:
                _DUVIDA.append("depth")
                extras.append(cmd[i + 2:])
                return "".join(lit) + cmd[i:], extras, n, False, False, "".join(bruto) + cmd[i:]
            t, ex, j, fechou, cru = _codigo(cmd, i + 2, True, nivel + 1, solto)
            extras += [t] + ex
            if not fechou:
                _DUVIDA.append("$(")
            dentro = "$(" + cru + ")" * fechou  # as written, without the heredoc bodies and comments inside
            igual = igual and dentro == cmd[i:j] and not re.search(r"[\"'\\]", dentro)
            lit.append(dentro)
            bruto.append(dentro)
            i = j
        elif c == "`":
            ex, j = _crase(cmd, i, nivel, solto, aspas)
            extras += ex
            igual = igual and not re.search(r"[\"'\\]", cmd[i:j])
            lit.append(cmd[i:j])
            bruto.append(cmd[i:j])
            i = j
        else:
            if c == "$" and d == "{":  # Bash may read quotes inside "${x#'...'}" as quotes
                j, fundo = i + 2, 1
                while j < n and fundo:  # up to its own `}`: `${x#${y}'"'}`
                    fundo += (cmd[j:j + 2] == "${") - (cmd[j] == "}")
                    j += 1
                if re.search(r"['\"\\`]", cmd[i:j]):
                    _DUVIDA.append("${")
            lit.append(c)
            bruto.append(c)
            i += 1
    if aspas:
        _DUVIDA.append('"')
    return "".join(lit), extras, n, igual, not aspas, "".join(bruto)


def _codigo(cmd, i, sub, nivel, solto):
    """Bash code from `i` (`sub`: up to the `)` that closes a `$(`). `solto`: the reading where
    `((`, `${`, `$[` and `name[` open nothing. -> (readable text, substitutions found where shlex
    does not split, index after it, the `)` was found, the text as written but without heredoc
    bodies, comments and continuations)."""
    out, cru, extras, pendentes = [], [], [], []

    def poe(lido, escrito=None):
        out.append(lido)
        cru.append(lido if escrito is None else escrito)

    n = len(cmd)
    inicio, chave, colch, par, arit, casos = True, 0, 0, 0, [], 0
    comando, abertos, teste = True, [], False  # at a command word; per open `(`: a plain subshell; in [[ ]]
    while i < n:
        c, dois = cmd[i], cmd[i:i + 2]
        if c == "\n":
            poe(c)
            i += 1
            while pendentes:  # the bodies start after the line that opened them
                fim, expande, tabs = pendentes.pop(0)
                a = b = i
                while i < n:
                    j = cmd.find("\n", i)
                    linha, b, i = cmd[i:n if j < 0 else j], i, n if j < 0 else j + 1
                    if (linha.lstrip("\t") if tabs else linha) == fim:  # exact, as Bash
                        break
                    b = i
                else:
                    _DUVIDA.append("heredoc end")
                if expande:
                    extras += _expande(cmd[a:b], 0, False, nivel, solto)[1]
            inicio = comando = True
            continue
        if dois == "\\\n" or (not solto and cmd.startswith("\\\r\n", i)):
            i += 2 + (dois != "\\\n")  # line continuation: Bash drops it. `\\<CR><LF>`: an escaped CR
            continue                    # and a line end for Bash; the first reading joins the lines
        if c == "#" and inicio and not (chave or arit):
            if not teste and (not abertos or abertos[-1]):
                j = cmd.find("\n", i)
                i = n if j < 0 else j
                continue
            _DUVIDA.append("#")  # inside `[[ x =~ (#) ]]` or an extglob `@(#x)`: no comment for Bash
        era_comando = comando and inicio
        if inicio and c not in " \t;|&()":  # `case`/`esac` count only where a command starts
            m = RE_CASE.match(cmd, i) if comando and not (chave or arit) else None
            casos = max(0, casos + (m.group(1) == "case") - (m.group(1) == "esac")) if m else casos
            teste = (teste or (comando and cmd.startswith("[[", i))) and not cmd.startswith("]]", i)
            comando = comando and bool(RE_ANTES_DE_COMANDO.match(cmd, i))
        inicio = False
        if c == "\\":
            j = i + 2
        elif c == "`":
            ex, j = _crase(cmd, i, nivel, solto)
            extras += ex
            poe(_q(cmd[i:j]), cmd[i:j])
            i = j
            continue
        elif c == "'":
            j = cmd.find("'", i + 1)
            if j < 0:  # unclosed (Bash runs nothing from this line on): closed here, to stay readable
                _DUVIDA.append("'")
                poe(cmd[i:] + "'")
                break
            j += 1
        elif c == '"' or dois == '$"':
            i += dois == '$"'  # locale string: Bash reads it as "..."
            valor, ex, j, igual, fechou, bruto = _expande(cmd, i + 1, True, nivel, solto)
            extras += ex
            if not fechou:
                poe(_q(valor), '"' + bruto + '"')
                break
            poe(cmd[i:j] if igual else _q(valor), '"' + bruto + '"')
            i = j
            continue
        elif dois == "$(" and cmd[i + 2:i + 3] != "(" and nivel < MAX_NIVEL:
            # as one word, its commands after the text: `rm $(x) f` keeps `f` as rm's argument, and
            # glued to a word (`rm$(x) f`) it is dropped, the word may be the command
            t, ex, j, fechou, dentro = _codigo(cmd, i + 2, True, nivel + 1, solto)
            extras += [t] + ex
            if not fechou:
                _DUVIDA.append("$(")
            dentro = "$(" + dentro + ")" * fechou
            antes = "".join(out[-8:])[-1:]  # the pieces are never all empty this far back
            colado = antes not in ("", " ", "\t", "\n", ";", "|", "&", "(", ")", "<", ">", "=")
            # where a command starts it is dropped too: `$(x) rm f` runs rm
            poe("" if colado or era_comando else _q(dentro), dentro)
            comando = era_comando
            i = j
            continue
        elif dois == "$'":
            j = i + 2
            while j < n and cmd[j] != "'":
                j += 2 if cmd[j] == "\\" else 1
            if j >= n:
                _DUVIDA.append("$'")
                poe(_q(ansi_c(cmd[i + 2:])), cmd[i:] + "'")
                break
            poe(_q(ansi_c(cmd[i + 2:j])), cmd[i:j + 1])
            i = j + 1
            continue
        else:
            aqui = dois == "<<" and not cmd.startswith("<<<", i) and not (chave or arit or colch)
            m = _delimitador(cmd, i + 2 + (cmd[i + 2:i + 3] == "-")) if aqui else None
            if m:
                pendentes.append((m[0], m[1], cmd[i + 2:i + 3] == "-"))
                j = m[2]
            elif cmd.startswith("<<<", i):
                j = i + 3
            elif dois in ("${", "$[") and not solto:
                chave, colch, j = chave + (dois == "${"), colch + (dois == "$["), i + 2
            else:
                simples = False
                comando = comando or c in ";|&("
                if c == "(":
                    if dois == "((" and not solto:
                        arit.append(par)
                    par += 1
                    abertos.append(not arit and (i == 0 or cmd[i - 1] in " \t\n;|&()"))
                elif c == ")":
                    if sub and par == 0 and not casos:
                        return "".join(out), extras, i + 1, True, "".join(cru)
                    par = max(0, par - 1)
                    simples = abertos.pop() if abertos else True  # `$(x)#` is one word: no comment
                    comando = simples  # after a `case` pattern `x)` or a subshell
                    if arit and par <= arit[-1]:
                        arit.pop()
                elif c == "[" and i and (cmd[i - 1].isalnum() or cmd[i - 1] == "_") and not solto:
                    colch += 1  # array subscript: arithmetic, `a[1<<2]=x`
                elif c == "]" and colch:
                    colch -= 1
                elif c == "}" and chave:
                    chave -= 1
                inicio, j = c in INICIA_PALAVRA and (c != ")" or simples), i + 1
        poe(cmd[i:j])
        i = j
    if casos:
        _DUVIDA.append("case")
    return "".join(out), extras, n, False, "".join(cru)
