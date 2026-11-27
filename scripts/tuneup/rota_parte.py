"""tune-up: `guarda.py rota --part` — which reviewers a whole Part needs, from its paths and its diff.

Rule: low risk (one failures reviewer) only when every path is proven front and no risk word shows;
anything else, or anything this module cannot read, is risk.
"""
import re

from .rota import (ORDEM, PADROES, PALAVRAS, RE_HUNK, ZERO, _barra, _normal, _primeiro, candidatos,
                   casa, globs_efetivos, ler_args, limpar, raizes_de, relativo, tem_diff)
from .agent import proibidos
from .sessao import log_erro
from .usuario import ler_usuario, modelo_proibido, sem_modelo

TAMANHO_PEDACO = 1500  # changed lines one reviewer reads
PALAVRAS_FRENTE = ("supabase.auth", "service_role", ".rpc(", "functions.invoke",
                   "dangerouslysetinnerhtml", "innerhtml", "import.meta.env", "localstorage",
                   "password", "secret")
PALAVRAS_RESTO = tuple(k for k in PALAVRAS if k not in ("../", "..\\")) + (
    "service_role", "dangerouslysetinnerhtml")
RE_COLCHETE = re.compile(r"\[!?\]?[^\]]*\]")  # as fnmatch reads it: a first `]` is literal
NEUTRAS = ("index ", "new file mode ", "deleted file mode ", "old mode ", "new mode ", "\\ ")
MODOS_RUINS = (" 120000", " 160000")  # symlink, submodule: the hunk does not show what it points to


def front_globs(cfg):
    """(valid, rejected) `front_globs`: an entry without a letter or digit outside brackets
    matches everything."""
    lista = cfg.get("front_globs")
    validos, ruins = [], []
    for g in lista if isinstance(lista, list) else []:
        ok = isinstance(g, str) and any(c.isalnum() for c in RE_COLCHETE.sub("", _barra(g)))
        (validos if ok else ruins).append(g)
    if ruins:
        log_erro("rota", "front_globs entries rejected (match everything): %r" % (ruins,))
    return validos, ruins


def globs_parte(cfg):
    """(the effective lists without the defaults in `globs_off`, the defaults turned off).
    Never database_globs, nor a database default from any list. A default the project also lists
    (so it is there twice) stays."""
    gl, tirados = globs_efetivos(cfg), []
    fora = cfg.get("globs_off")
    for k in ("risk_globs", "security_globs"):
        extra = cfg.get(k) if isinstance(cfg.get(k), list) else []
        tira = [g for g in PADROES[k] if isinstance(fora, list) and g in fora
                and extra.count(g) < 2 and g not in PADROES["database_globs"]]
        gl[k] = [g for g in gl[k] if g not in tira]
        tirados += [g for g in tira if g not in tirados]
    return gl, tirados


def _cabecalho_git(linha):
    """Path of a `diff --git a/P b/P`, `--- a/P` or `+++ b/P` line, "" for /dev/null, None when
    it cannot be read (rename, quoted path, other prefix)."""
    if linha.startswith("diff "):
        resto = linha[len("diff --git "):]
        p = resto[2:2 + (len(resto) - 5) // 2]
        return p if p and linha == "diff --git a/%s b/%s" % (p, p) else None
    resto = linha[4:].split("\t")[0]  # git ends a path with spaces with a tab
    if resto == "/dev/null":
        return ""
    return resto[2:] or None if resto.startswith("a/" if linha[0] == "-" else "b/") else None


def ler_diff(texto):
    """(paths in the file headers, [(`+` or `-`, text)], numbers of the lines it cannot read, the
    header paths that have a changed line in a hunk).
    Split on `\\n` only: a form feed or U+2028 inside a line does not start another one. Inside a
    hunk (counted from its `@@` header) nothing is a header; outside, only known lines pass."""
    caminhos, mudadas, ruins, com_hunk, atual = [], [], [], set(), ""
    velho = novo = 0
    linhas = texto.split("\n")
    if linhas[-1] == "":
        linhas.pop()
    for n, linha in enumerate(linhas, 1):
        sinal = linha[:1]
        if velho > 0 or novo > 0:
            if sinal == "\\":
                continue
            velho -= sinal != "+"
            novo -= sinal != "-"
            if sinal in ("+", "-", " ", "", "\r") and velho >= 0 and novo >= 0:
                if sinal in ("+", "-"):
                    mudadas.append((sinal, linha[1:]))
                    com_hunk.add(atual)
                    if linha.startswith("Subproject commit ", 1):
                        ruins.append(n)
                continue
            ruins.append(n)  # the counts lie: read the rest as outside a hunk
            velho = novo = 0
        linha = linha.rstrip("\r")
        m = RE_HUNK.match(linha)
        if m:
            velho, novo = int(m.group(1) or 1), int(m.group(2) or 1)
            if not caminhos:  # a hunk of no known file
                ruins.append(n)
        elif linha.startswith(("diff ", "--- ", "+++ ")):
            p = _cabecalho_git(linha)
            if p is None:
                ruins.append(n)
                p = linha.split(" ", 1)[1]  # raw: its pieces can still match database_globs
            atual = p or atual
            if p and p not in caminhos:
                caminhos.append(p)
        else:
            if sinal in ("+", "-"):
                mudadas.append((sinal, linha[1:]))
            if linha and not linha.startswith(NEUTRAS) or linha.endswith(MODOS_RUINS):
                ruins.append(n)
    if velho > 0 or novo > 0:
        ruins.append(len(linhas))  # truncated
    return caminhos, mudadas, ruins, com_hunk


def _exato(caminho, raizes):
    """`relativo` without losing the letter case (A.tsx and a.tsx are two files)."""
    rel, p = relativo(caminho, raizes), _barra(caminho)
    fim = p[len(p) - len(rel):]
    return fim if fim.lower() == rel else rel


def fora_do_diff(files, do_diff, com_hunk, raizes):
    """(`--files` or header paths without a hunk, header paths that are not in `--files`). An
    argument is one path or, when that is not in the diff, several in one string."""
    com_hunk = {_exato(p, raizes) for p in com_hunk}
    citados, sem = set(), []
    for f in files:
        ps = [_exato(f, raizes)]
        if ps[0] not in com_hunk:
            ps = [_exato(p, raizes) for p in map(_normal, re.split(r"[\s,;|]+", f.translate(ZERO))) if p] or ps
        citados.update(ps)
        sem += [p for p in ps if p not in com_hunk and p not in sem]
    do_diff = [_exato(p, raizes) for p in do_diff]
    sem += [p for p in do_diff if p not in com_hunk and p not in sem]
    return sem, [p for p in do_diff if p not in citados]


def motivo_fora(rel, front, gl):
    """Why this path is not front, or None. `rel` is (path, its candidates made relative)."""
    if any(s.strip() == ".." for c in candidatos(rel[0]) for s in _barra(c).split("/")):
        return "`..` in path: %s" % rel[0]
    for k in ("risk_globs", "security_globs", "database_globs"):
        m = _primeiro([rel], gl[k])
        if m:
            return "%s: %s matches %s" % ((k,) + m)
    if not all(any(casa(c, g) for g in front) for c in rel[1]):
        return "not in front_globs: %s" % rel[0]
    return None


def _mais(lista):
    return " (+%d more)" % (len(lista) - 1) if len(lista) > 1 else ""


def rota_parte(files, diff_file, cfg, raiz):
    front, rejeitados = front_globs(cfg)
    gl, tirados = globs_parte(cfg)
    risco, notas = [], ["globs_off: %s is off in Part mode" % g for g in tirados]
    notas += ["front_globs entry rejected (matches everything): %s" % g for g in rejeitados]
    caminhos, mudadas, linhas, raizes = limpar(files), [], None, raizes_de(raiz)
    if not caminhos:
        risco.append("no files: no information")
    if diff_file is None:
        risco.append("no diff: cannot rule risk out")
    else:
        try:
            with open(diff_file, "rb") as f:
                bruto = f.read()
        except OSError as e:
            risco.append("diff unreadable (%s)" % type(e).__name__)
        else:
            texto = bruto.decode("utf-8", "replace")
            do_diff, mudadas, ruins, com_hunk = ler_diff(texto)
            linhas = len(mudadas)
            if texto.encode("utf-8") != bruto:  # still counted: a big Part is still split
                risco.append("diff is not UTF-8")
                linhas = linhas or None
            for motivo, ps in zip(("no hunk in the diff", "in the diff but not in --files"),
                                  fora_do_diff(caminhos, do_diff, com_hunk, raizes)):
                if ps:
                    risco.append("%s: %s" % (motivo, ps[0]) + _mais(ps))
            caminhos += [p for p in do_diff if p not in caminhos]
            if not tem_diff(texto):
                risco.append("diff file has no diff content")
            if ruins:
                risco.append("diff line %d cannot be read (use plain `git diff --no-renames`)"
                             % ruins[0])
    rels = [(p, [relativo(c, raizes) for c in candidatos(p)]) for p in caminhos]
    fora = [m for m in (motivo_fora(r, front, gl) for r in rels) if m]
    if fora:
        risco.append(fora[0] + _mais(fora))
    baixas = [("added" if s == "+" else "removed", t.lower()) for s, t in mudadas]
    # outside the front (already risk) the general words only inform the reviewers
    for k in PALAVRAS_RESTO if fora else PALAVRAS_FRENTE:
        for tipo in ("added", "removed"):
            if any(t == tipo and k in b for t, b in baixas):
                risco.append("diff keyword in %s line: %s" % (tipo, k))
    rev = {"failures", "security"} if risco else {"failures"}
    m = _primeiro(rels, gl["database_globs"])
    if m:
        rev.add("database")
        notas.append("database_globs: %s matches %s" % m)
    pedacos = max(1, -(-(linhas or 0) // TAMANHO_PEDACO))
    if pedacos > 1:
        notas.append("%d changed lines: the coordinator splits by side or item group and adds one "
                     "failures reviewer for the boundaries" % linhas)
    lentes = [r for r in ORDEM if r in rev]
    return {"part": True, "risk": bool(risco), "reviewers": lentes,
            "models": modelos_lentes(lentes), "effort": "high", "lines": linhas, "chunks": pedacos,
            "why": (risco or ["every file is front and no risk word: low risk"]) + notas}


def modelos_lentes(lentes):
    """Model per lens from the user.json role table; missing, inherit, forbidden or haiku: opus."""
    papeis, lista = ler_usuario()[0]["models"], proibidos()
    out = {}
    for r in lentes:
        m = (papeis.get("reviewer-" + r) or {}).get("model")
        ruim = sem_modelo(m) or modelo_proibido(m, lista) or "haiku" in str(m).lower()
        out[r] = "opus" if ruim else m
    return out


def rota_parte_args(argv, cfg, raiz):
    if argv.count("--diff-file") > 1:  # ler_args keeps only the last one
        raise ValueError("one --diff-file in Part mode")
    files, diff, failed, texto = ler_args([a for a in argv if a != "--part"])
    if failed is not None or texto is not None:
        raise ValueError("--failed and --text-file do not exist in Part mode")
    return rota_parte(files, diff, cfg, raiz)
