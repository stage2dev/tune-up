"""tune-up: leitura do comando de shell (heredoc, tokens, segmentos, redireções, git, flags)."""
import os
import re
from .caminhos import NT, nativo

# ---------------------------------------------------------------- parsing bash

SEPARADORES = {"&&", "||", ";", "|", "&", "\n", ";;", "|&", "(", ")", ";&", ";;&"}
PREFIXOS = {"env", "sudo", "command", "time", "exec", "nohup", "nice", "xargs", "timeout"}
PREFIXO_VALOR = {"nice": "n", "timeout": "sk", "xargs": "aEdILnPs"}  # flags curtas que levam valor
SEP_CHARS = set("();|&\n")
PALAVRAS_SHELL = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "}", "(", ")"}
SHELLS = {"bash", "sh", "zsh"}
RE_ATRIB = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
# heredoc de verdade, ou trecho entre aspas / $((…)) onde `<<` não abre heredoc
RE_HEREDOC_OU_ASPAS = re.compile(
    r"<<(?!<)-?\s*['\"]?(\w+)['\"]?|'[^']*'|\"(?:[^\"\\]|\\.)*\"|\$\(\([^)]*\)\)")


def sem_heredoc(cmd):
    saida = []
    pendentes = []
    for linha in cmd.split("\n"):
        if pendentes:
            if linha.strip() == pendentes[0]:
                pendentes.pop(0)
            continue
        saida.append(linha)
        pendentes.extend(m.group(1) for m in RE_HEREDOC_OU_ASPAS.finditer(linha) if m.group(1))
    return "\n".join(saida)


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
    except ValueError:
        segs = []
        for parte in re.split(r"&&|\|\||[;|&\n]", cmd):
            if parte.strip():
                segs.append(parte.split())
        return segs
    segs, atual = [], []
    for t in toks:
        if t in SEPARADORES or (t and not set(t) - SEP_CHARS):  # "))\n" vem grudado
            if atual:
                segs.append(atual)
            atual = []
        else:
            atual.append(t)
    if atual:
        segs.append(atual)
    return segs


def comando_interno(toks):
    """String de `bash|sh|zsh -c "<x>"`, `eval "<x>"` ou `cmd /c|/k <x>` (Windows; `%X%` vira
    `$X`); senão None."""
    if not toks:
        return None
    exe = os.path.basename(toks[0])
    if exe == "eval":
        return " ".join(toks[1:])
    if exe == "cmd":
        for j, t in enumerate(toks[1:], 1):
            if re.fullmatch(r"/{1,2}[cCkK]", t):  # Git Bash needs `//c`
                return re.sub(r"%(\w+)%", r"$\1", " ".join(toks[j + 1:])) if toks[j + 1:] else None
        return None
    if exe in SHELLS:
        for j, t in enumerate(toks[1:], 1):
            if t.startswith("-") and not t.startswith("--") and "c" in t[1:]:
                return toks[j + 1] if j + 1 < len(toks) else None
            if not t.startswith("-"):
                return None
    return None


def comandos(limpo):
    """Comandos simples do texto, abrindo `bash -c`/`eval` um nível."""
    out = []
    for seg in segmentos(limpo):
        toks = comando_simples(seg)
        interno = comando_interno(toks)
        if interno is None:
            out.append((seg, toks))
            continue
        for s2 in segmentos(sem_heredoc(interno)):
            out.append((s2, comando_simples(s2)))
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
