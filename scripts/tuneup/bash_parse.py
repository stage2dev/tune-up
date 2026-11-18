"""tune-up: leitura do comando de shell (heredoc, tokens, segmentos, redireções, git, flags)."""
import os
import re
from .bash_texto import legivel
from .caminhos import NT, nativo

# ---------------------------------------------------------------- parsing bash

SEPARADORES = {"&&", "||", ";", "|", "&", "\n", ";;", "|&", "(", ")", ";&", ";;&"}
PREFIXOS = {"env", "sudo", "command", "time", "exec", "nohup", "nice", "xargs", "timeout"}
PREFIXO_VALOR = {"nice": "n", "timeout": "sk", "xargs": "aEdILnPs"}  # flags curtas que levam valor
SEP_CHARS = set("();|&\n")
PONTUACAO = set("();<>|&\n")
RE_FIM_GRUDADO = re.compile(r"[\n;()]+|[^\n;()]+")
PALAVRAS_SHELL = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "}", "(", ")"}
SHELLS = {"bash", "sh", "zsh"}
TEXTO_PS = "\x00ps"  # marker segment [TEXTO_PS, words...]: PowerShell text-check words (see comandos)
ESCOPO = "\x00escopo"  # marker segments [ESCOPO, "+"] / [ESCOPO, "-"] around a wrapper's own segments
RE_ATRIB = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def sem_heredoc(cmd):
    """The command as the tokenizer can read it (bash_texto.legivel): no heredoc bodies or comments,
    `$'...'` as plain quoted words, and the substitutions inside double quotes as extra lines."""
    return legivel(cmd)


def tokens_de(texto):
    import shlex
    lx = shlex.shlex(texto, posix=True, punctuation_chars="();<>|&\n")
    lx.whitespace = " \t\r"
    lx.whitespace_split = True
    lx.commenters = ""
    return list(lx)


def segmentos(cmd):
    """Lista de listas de tokens, uma por comando simples."""
    try:
        toks = tokens_de(cmd)
    except ValueError:  # unreadable: split at every separator and redirection, quotes dropped
        segs = []
        for parte in re.split(r"&&|\|\||[;|&\n()`<>]|\$\(", cmd):
            parte = re.sub(r"['\"\\]", "", parte)
            if parte.strip():
                segs.append(parte.split())
        return segs
    segs, atual = [], []
    # shlex glues punctuation: "))\n" is one token, and so is "\n<<<" (a line end and a redirection)
    toks = [p for t in toks for p in (RE_FIM_GRUDADO.findall(t) if t and not set(t) - PONTUACAO else [t])]
    for t in toks:
        if t in SEPARADORES or (t and not set(t) - SEP_CHARS):
            if atual:
                segs.append(atual)
            atual = []
        else:
            atual.append(t)
    if atual:
        segs.append(atual)
    return segs


def comando_interno(toks):
    """String de `bash|sh|zsh -c "<x>"` ou `eval "<x>"`; senão None."""
    if not toks:
        return None
    exe = os.path.basename(toks[0])
    if exe == "eval":
        return " ".join(toks[1:])
    if exe in SHELLS:
        for j, t in enumerate(toks[1:], 1):
            if t.startswith("-") and not t.startswith("--") and "c" in t[1:]:
                return toks[j + 1] if j + 1 < len(toks) else None
            if not t.startswith("-"):
                return None
    return None


WSL_VALOR = {"-d", "--distribution", "--distribution-id", "-u", "--user", "--shell-type"}


def comando_wsl(toks):
    """Texts the Linux shell may get from `wsl [options] [--] <words>` (`--cd D` as a leading `cd`;
    `-e|--exec`: the words as one command, no shell); None for any other command and for wsl's
    own management options (`--list`, `--shutdown`...)."""
    if not toks or os.path.basename(toks[0]).lower() not in ("wsl", "wsl.exe"):
        return None
    import shlex
    i, cd, exato = 1, "", False
    while i < len(toks) and toks[i].startswith("-"):
        t = toks[i]
        i += 1
        if t == "--" or t in ("-e", "--exec"):
            exato = t != "--"
            break
        if t in WSL_VALOR or t == "--cd":
            if t == "--cd" and i < len(toks):
                cd = "cd %s ; " % shlex.quote(toks[i])
            i += 1
        elif t != "--system":
            return None
    resto = toks[i:]
    if exato:
        return [cd + " ".join(shlex.quote(t) for t in resto)]
    # Windows hands wsl one command line: a word with a blank goes in double quotes, the rest bare.
    # Both readings of such a word are given (one word, or shell text).
    citado = " ".join('"%s"' % re.sub(r'(["\\])', r"\\\1", t) if re.search(r"\s", t) else t for t in resto)
    return [cd + x for x in dict.fromkeys([citado, " ".join(resto)])]


def comandos(limpo, nivel=0):
    """Comandos simples do texto, abrindo `bash -c`/`eval`/`wsl` (até 3 níveis). `powershell|pwsh <x>`
    and `cmd /c|//c <x>` are read as the PowerShell tool reads them (powershell.do_bash): the command
    itself, its Bash rewrite between ESCOPO markers (a `cd` inside does not reach the segments after
    the wrapper), and a TEXTO_PS segment with the words of its text check (unreadable: all its words).
    `wsl <x>`: the command itself, then what the Linux shell runs, between ESCOPO markers.
    The markers are always there."""
    from .powershell import do_bash
    out, escopo = [], True

    def dentro(texto):  # the commands of an inner command line
        if nivel < 2:
            return comandos(sem_heredoc(texto), nivel + 1)
        return [(s2, comando_simples(s2)) for s2 in segmentos(sem_heredoc(texto))]

    for seg in segmentos(limpo):
        toks = comando_simples(seg)
        try:
            ps = do_bash(toks)
        except ValueError:
            ps = ("", toks)
        wsl = comando_wsl(toks) if ps is None else None
        if ps is not None or wsl is not None:
            out += [(seg, toks)] + [([ESCOPO, "+"], [ESCOPO, "+"])] * escopo
            if wsl is not None:
                for k, texto in enumerate(wsl):
                    out += [([ESCOPO, x], [ESCOPO, x]) for x in "-+"] * (escopo and k > 0)
                    out.extend(dentro(texto))
            else:
                out.extend((s2, comando_simples(s2)) for s2 in segmentos(sem_heredoc(ps[0])))
            out += [([ESCOPO, "-"], [ESCOPO, "-"])] * escopo
            if ps and ps[1]:
                out.append(([TEXTO_PS] + ps[1], [TEXTO_PS] + ps[1]))
            continue
        interno = comando_interno(toks)
        if interno is None:
            out.append((seg, toks))
        else:
            out.extend(dentro(interno))
    return out


def limpar_redirecoes(toks):
    """Tira `>`, `2>&1`, `< arq` etc. (o operador e o alvo)."""
    out = []
    pular = False
    for t in toks:
        if pular:
            pular = False
            continue
        if t[:1] in ("<", ">") or t in ("&>", "&>>"):
            if out and out[-1].isdigit():
                out.pop()
            pular = True
            continue
        out.append(t)
    return out


def comando_simples(seg):
    """Remove atribuições e prefixos; devolve tokens a partir do executável."""
    toks = limpar_redirecoes(seg)
    i = 0
    while i < len(toks):
        t = toks[i] = _sem_ext(toks[i])  # only command positions: `rm npx.cmd` keeps its target
        if RE_ATRIB.match(t) or t in PALAVRAS_SHELL:
            i += 1
        elif t in PREFIXOS:
            i += 1
            valor = PREFIXO_VALOR.get(t, "")
            while i < len(toks) and toks[i].startswith("-") and toks[i] != "--":
                f = toks[i]
                i += 1
                if len(f) == 2 and f[1] in valor:
                    i += 1
            if i < len(toks) and toks[i] == "--":
                i += 1
            if t == "timeout":
                i += 1  # duração
        elif t in ("npx", "bunx") or (t == "yarn" and toks[i + 1:i + 2] != ["dlx"]):
            i += 1
            while i < len(toks) and toks[i].startswith("-"):
                i += 1
        elif t == "npm" and toks[i + 1:i + 2] == ["exec"]:
            i += 2
            while i < len(toks) and toks[i].startswith("-") and toks[i] != "--":
                i += 1
            if i < len(toks) and toks[i] == "--":
                i += 1
        elif t in ("pnpm", "yarn") and i + 1 < len(toks) and toks[i + 1] in ("dlx", "exec"):
            i += 2
            while i < len(toks) and toks[i].startswith("-"):
                i += 1
        else:
            break
    return lancador(toks[i:])


EXTENSOES = (".exe", ".cmd", ".bat", ".ps1", ".com")
CORREDORES = PREFIXOS | {"npx", "bunx", "npm", "pnpm", "yarn"}


def _sem_ext(t):
    """`npx.cmd`/`sudo.exe` (Windows) -> `npx`/`sudo` for the prefixes and runners."""
    if t.lower().endswith(EXTENSOES) and os.path.basename(t).rsplit(".", 1)[0].lower() in CORREDORES:
        return os.path.basename(t).rsplit(".", 1)[0].lower()
    return t


def lancador(toks):
    """The plugin launcher (`sh .../scripts/py x.py`, `.../scripts/py x.py`) and the Windows `py`
    launcher (`py -3 x.py`) run Python: they become `python x.py`. `git.exe` -> `git`, also
    `.cmd`, `.bat`, `.ps1`, `.com` (Windows; `npx.cmd`)."""
    if len(toks) > 1 and os.path.basename(toks[0]) in SHELLS and os.path.basename(toks[1]) == "py":
        toks = ["python"] + toks[2:]
    elif toks and os.path.basename(toks[0]).lower() in ("py", "py.exe"):
        j = 1
        while j < len(toks) and re.fullmatch(r"-(\d[\d.]*(-\d+)?|V:\S+)", toks[j]):
            j += 1
        toks = ["python"] + toks[j:]
    elif toks and toks[0].lower().endswith(EXTENSOES):
        toks = [os.path.basename(toks[0]).rsplit(".", 1)[0].lower()] + toks[1:]
    return toks


def junta_dir(base, d):
    """Absolute path of `d` from `base` (Windows: Git Bash spellings first, see caminhos.nativo;
    a drive-relative `D:x` on another drive resolves against that drive's current folder)."""
    p = os.path.normpath(os.path.join(nativo(base), nativo(os.path.expanduser(d))))
    return os.path.abspath(p) if NT and not os.path.isabs(p) else p


def analisar_git(toks, cwd):
    """toks começa em 'git'. Devolve (diretorio, subcomando, args)."""
    i = 1
    d = cwd
    while i < len(toks):
        t = toks[i]
        if t == "-C" and i + 1 < len(toks):
            d = junta_dir(d, toks[i + 1])
            i += 2
        elif t in ("-c", "--git-dir", "--work-tree", "--namespace") and i + 1 < len(toks):
            i += 2
        elif t.startswith("-"):
            i += 1
        else:
            return d, t, toks[i + 1:]
    return d, None, []


def flags_curtas(args, com_valor, ate_duplo=True):
    """Letras das flags curtas (antes da 1ª que leva valor), e flags longas."""
    letras, longas = set(), set()
    pular = False
    for a in args:
        if pular:
            pular = False
            continue
        if a == "--" and ate_duplo:
            break
        if a.startswith("--"):
            longas.add(a.split("=", 1)[0])
        elif a.startswith("-") and len(a) > 1:
            for j, c in enumerate(a[1:]):
                if c in com_valor:
                    if j == len(a) - 2:
                        pular = True
                    break
                letras.add(c)
    return letras, longas


def posicionais(args, com_valor_curto=(), com_valor_longo=()):
    out, pular, apos = [], False, False
    for a in args:
        if pular:
            pular = False
            continue
        if apos:
            out.append(a)
            continue
        if a == "--":
            apos = True
        elif a.startswith("--"):
            if a in com_valor_longo:
                pular = True
        elif a.startswith("-") and len(a) > 1:
            if a[-1] in com_valor_curto and len(a) == 2:
                pular = True
        else:
            out.append(a)
    return out
