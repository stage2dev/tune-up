"""tune-up: `cmd /c <x>` text read as Bash for the PowerShell rewrite (powershell.py)."""
import re
import shlex
from .bash_parse import tokens_de
from .powershell_parse import REDIR, sem_nulos

VERBOS_CMD = {"del": "remove-item", "erase": "remove-item", "rd": "remove-item", "rmdir": "remove-item",
              "move": "move-item", "copy": "copy-item", "ren": "rename-item", "rename": "rename-item"}
CD_CMD = {"cd", "chdir", "pushd"}
COPIA_CMD = {"xcopy", "robocopy", "replace"}  # `<x> src dst` (robocopy: dst is the 2nd positional)
VERBOS_TODOS = set(VERBOS_CMD) | CD_CMD | COPIA_CMD | {"mklink"}
RE_VERBO = re.compile(r"(?i)(%s)(?:[/.]|$)" % "|".join(sorted(VERBOS_TODOS)))
RE_SWITCH_LONGO = re.compile(r"/[A-Za-z?]+(?::\S*)?")  # `/mir`, `/exclude:x` (xcopy, robocopy)
SE_DOIS = {"exist", "errorlevel", "cmdextversion", "defined"}  # `if [not] exist X <cmd>`
SE_TRES = {"==", "equ", "neq", "lss", "leq", "gtr", "geq"}  # `if [/i] [not] a == b <cmd>`
RE_SWITCH = r"/-?[A-Za-z](?::[^/\s]*)?"
RE_CASA = re.compile(r"%homedrive%%homepath%", re.I)
RE_CHAVE_CMD = re.compile(r"/([A-Za-z?])(:[^/\s]*)?")  # one `cmd` switch: `/q`, `/v:on`, `/c` (glued text after)


def apos_chaves(args):
    """The command text tokens of `cmd [/x...] /c|/k|/r <x>`: switches may be glued (`/q/c`) and
    the text glued to /c (`/cdel x`); None when there is no text. Text with no /c|/k|/r: ValueError."""
    for j, t in enumerate(args):
        t = t[1:] if t.startswith("//") else t
        while t[:1] == "/":
            m = RE_CHAVE_CMD.match(t)
            if not m:
                raise ValueError("cmd switch not read")
            if m.group(1).casefold() in "ckr":
                resto = ([t[2:]] if t[2:] else []) + list(args[j + 1:])
                return resto or None
            t = t[m.end():]
        if t:
            raise ValueError("cmd text without /c")
    return None


def comando_cmd(args):
    """Bash text of `cmd /c|/k|/r <x>` (`%X%` -> `$X` upper case, `^` escapes dropped, `\\` read as
    `/`, %HOMEDRIVE%%HOMEPATH% as `~`), or None. `!X!` (delayed expansion) or a `set X=` whose
    `%X%` is used cannot be read without resolving the variable: ValueError."""
    resto = apos_chaves(args)
    if not resto:
        return None
    x = resto[0] if len(resto) == 1 else " ".join(shlex.quote(r) if re.search(r"\s", r) else r for r in resto)
    usadas = {v.casefold() for v in re.findall(r"%(\w+)%", x)}
    if re.search(r"![^!\s]+!", x) or usadas & {v.casefold() for v in re.findall(
            r"(?i)(?<![\w.-])set\s+(?:/[ap]\s+)?\"?(\w+)=", x)}:
        raise ValueError("cmd variable set in the command")
    x = re.sub(r"%(\w+)%", lambda m: "$" + m.group(1).upper(), RE_CASA.sub("~", x))
    return verbos_cmd(re.sub(r"\^(.)", r"\1", x).replace("\\", "/"))


def _pedacos_cmd(x):
    """cmd text split at & | ( ) and newlines outside double quotes (not `>&`), separators kept."""
    out, ini, aspas = [], 0, False
    for i, c in enumerate(x):
        if c == '"':
            aspas = not aspas
        elif not aspas and c in "&|()\n" and not (c == "&" and i and x[i - 1] in "<>"):
            out += [x[ini:i], c]
            ini = i + 1
    return out + [x[ini:]]


def _inicio(toks):
    """Index where the command of a cmd piece starts, past `@`, `else`, `... do` and
    `if [/i] [not] exist X | errorlevel N | a == b`; None when an `if` cannot be read."""
    j = 0
    while j < len(toks):
        t = toks[j].casefold()
        if t in ("else", "do"):
            j += 1
        elif t == "if":
            j += 1
            for opcional in ("/i", "not"):
                if j < len(toks) and toks[j].casefold() == opcional:
                    j += 1
            if j < len(toks) and toks[j].casefold() in SE_DOIS:
                j += 2
            elif j < len(toks) and "==" in toks[j] and not toks[j].endswith("=="):
                j += 1
            elif j + 1 < len(toks) and toks[j + 1].casefold() in SE_TRES:
                j += 3
            else:
                return None
        else:
            return j
    return j


def _verbo(t):
    from .powershell import nome_cmd
    return nome_cmd(t) in VERBOS_TODOS or bool(RE_VERBO.match(t))


def _comeco(toks):
    """A cmd piece's command past `call`, `start [/x...]`, `cmd|%COMSPEC% [/x...] /c|/k`; a glued
    `cd\\x`, `cd..`, `cd.x` split (`cd/d`: a switch or the folder `\\d`, cannot tell: ValueError)."""
    from .powershell import nome_cmd
    while toks:
        m = re.fullmatch(r"(?i)(cd|chdir|pushd)([/.].*)", toks[0], re.S)
        c = toks[0].casefold()
        if m:
            if re.fullmatch(RE_SWITCH, m.group(2)):
                raise ValueError("glued cd switch")
            return [m.group(1), m.group(2)] + toks[1:]
        if c == "call":
            toks = toks[1:]
        elif c == "start":
            toks = toks[1:]
            while toks and toks[0][:1] == "/":
                toks = toks[1:]
        elif nome_cmd(toks[0]) in ("cmd", "$comspec"):
            resto = apos_chaves(toks[1:])
            if not resto:
                return toks
            toks = (tokens_de(resto[0]) if re.search(r"\s", resto[0]) else resto[:1]) + resto[1:]
        else:
            return toks
    return toks


def verbos_cmd(x):
    """cmd's del/erase/rd/rmdir/move/copy/ren(ame) rewritten as rm/mv/cp (`/s /q` switches dropped),
    cd/chdir [/d] X and pushd X as `cd X`; a verb found after `@`, `if ...`, `... do`. A verb on a
    loop variable (`for %d in (x) do rd %d`) cannot be read: ValueError. Past `call`, `start [/x]`,
    `cmd|%COMSPEC% /c`; xcopy/robocopy/replace as copies. A piece that cannot be tokenised, or that
    holds a verb but was not rewritten (not after echo/rem): ValueError. Other text stays."""
    from .powershell import MAX_INSTRUCOES, como_bash, nome_cmd
    partes = _pedacos_cmd(x)
    if len(partes) > 2 * MAX_INSTRUCOES:
        raise ValueError("too many cmd pieces")
    for k in range(0, len(partes), 2):
        p = re.sub(r"(?<!\S)\d?>&\d", "", partes[k])  # `2>&1`: no file
        p = re.sub(r"(?<!\S)\d(?=>)", "", re.sub(r"^(\s*)@", r"\1", p))  # `2>nul`, `@rd`
        toks = tokens_de(p)  # ValueError: a verb could hide in a piece not read
        j = _inicio(toks)
        if j is None:
            if any(_verbo(t) for t in toks):
                raise ValueError("cmd `if` not read")
            continue
        toks = _comeco(toks[j:])
        if toks and re.fullmatch(r"[A-Za-z]+(%s)+" % RE_SWITCH, toks[0]):  # `rd/s/q`, `del/q`
            m = re.match(r"[A-Za-z]+", toks[0])
            toks = [m.group(0)] + re.findall(RE_SWITCH, toks[0][m.end():]) + toks[1:]
        c = nome_cmd(toks[0]) if toks else ""
        if c == "mklink":  # `mklink [/D|/H|/J] link target`: a link, read as `ln -s target link`
            pos = [t for t in toks[1:] if not re.fullmatch(r"/{1,2}[A-Za-z]", t) and t[:1] not in "<>"]
            if any(re.search(r"%%?~?\w", t) for t in pos):
                raise ValueError("cmd loop variable")
            partes[k] = " %s " % (como_bash(["new-item", "-Path", pos[0], "-ItemType", "Junction", "-Target", pos[1]])
                                  if len(pos) > 1 else "true")
            continue
        if c not in VERBOS_CMD and c not in CD_CMD and c not in COPIA_CMD:
            if c not in ("echo", "rem") and any(_verbo(t) for t in toks):
                raise ValueError("cmd verb not read")
            continue  # the piece stays as it is
        ps, i = [VERBOS_CMD.get(c, "copy-item" if c in COPIA_CMD else "set-location")], 1
        chave = RE_SWITCH_LONGO if c in COPIA_CMD else re.compile(RE_SWITCH)
        while i < len(toks):
            t = toks[i]
            if t[:1] == "<":  # input: no write
                i += 1
            elif t[:1] == ">":
                ps.append(REDIR)
            elif not chave.fullmatch(t):
                ps.append(t)
            i += 1
        if any(re.search(r"%%?~?\w", t) for t in ps[1:]):
            raise ValueError("cmd loop variable")
        if c in COPIA_CMD:
            pos = [t for n, t in enumerate(ps) if n and t != REDIR and ps[n - 1] != REDIR]
            if len(pos) < (2 if c == "robocopy" else 1):
                raise ValueError("cmd copy without its paths")
            redir = [y for n, t in enumerate(ps[:-1]) if t == REDIR for y in (REDIR, ps[n + 1])]
            base = pos[0].rstrip("/") or "/"  # a folder copies what is in it: `src/*`, robocopy's `src/<file>`
            fontes = [base + "/" + f for f in pos[2:]] if c == "robocopy" and len(pos) > 2 else [pos[0], base + "/*"]
            ps = ["copy-item"] + fontes + ["-Destination", pos[1] if len(pos) > 1 else "."] + redir
        if c in CD_CMD:
            alvo = [t for t in ps[1:] if t != REDIR][:1]
            ps = ps[:1] + [re.sub(r"^\$(\{userprofile\}|userprofile|\{home\}|home)(?=/|$)", "~", alvo[0], flags=re.I)
                           ] if alvo else []
        partes[k] = " %s " % ((como_bash(sem_nulos(ps)) if len(ps) > 1 else "") or "true")
    return "".join(partes)
