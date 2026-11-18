"""tune-up: `guarda.py rota` — which executor and which reviewers for a work item, from its paths.

Rule: when in doubt the item goes UP (opus) and the security reviewer runs. Never reads stdin.
"""
import fnmatch
import json
import os
import re

from . import roteador
from .config import TESTE, carregar_config
from .info import toplevel
from .sessao import log_erro

OPUS, SONNET = "tune-up:executor-opus", "tune-up:executor-sonnet"
ORDEM = ("failures", "security", "database")
PALAVRAS = ("auth", "token", "secret", "password", "hmac", "signature", "permission",
            "subprocess", "eval", "../", "..\\")
RE_ABS = re.compile(r"(/|[a-z]:/)")  # after `\` -> `/` and lowercase: POSIX, UNC or `C:/`
# A trailing line reference: `:12`, `:10-40`, `:L10`, `:10:5`, `#10`, `#L10-L20` (`C:` has no digits).
RE_LINHA = re.compile("(?:[:#]l?\\d+(?:[-\u2013\u2014:]l?\\d+)?)$", re.IGNORECASE)
RE_HUNK = re.compile(r"@@ -\d+(?:,(\d+))? \+\d+(?:,(\d+))? @@")
ZERO = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))
BORDA = "\"'`()[]{}<>*"
# Defaults live here too (padrao.json may be stale or broken); config can only ADD to them.
# tests/test_rota.py checks they equal the padrao.json lists.
RISCO_PADRAO = ("**/migrations/**", "**/*.sql", "**/auth/**", "**/*auth*", "**/*webhook*",
                "**/*payment*", "**/*billing*", "**/*worker*", "**/*queue*", "**/hooks/**")
SEG_PADRAO = ("**/*auth*", "**/*webhook*", "**/*secret*", "**/*token*", "**/*payment*",
              "**/hooks/**", "**/*guard*", "**/*permission*", "**/*upload*")
BANCO_PADRAO = ("**/*.sql", "**/migrations/**")
PADROES = {"risk_globs": RISCO_PADRAO, "security_globs": SEG_PADRAO, "database_globs": BANCO_PADRAO}


def _barra(p):
    return p.replace("\\", "/")


def relativo(caminho, raizes):
    """Path relative to the repo root when absolute and inside it; `/` separators, no leading
    `./`, lowercase. The host's os.path is not used for the separator (a Windows path works
    on any OS)."""
    p = _barra(caminho).lower()
    if RE_ABS.match(p):
        cands = [p]
        if os.path.isabs(caminho):
            cands.append(_barra(os.path.realpath(caminho)).lower())
        for c in cands:
            for r in raizes:
                if r and c.startswith(r + "/"):
                    return c[len(r) + 1:]
        return p
    while p.startswith("./"):
        p = p[2:]
    return p


def casa(rel, padrao):
    """`fnmatchcase` on the lowercased pattern, also without its leading `**/`
    (so `**/*.sql` matches `schema.sql` at the root)."""
    pad = _barra(padrao).lower()
    if fnmatch.fnmatchcase(rel, pad):
        return True
    return pad.startswith("**/") and fnmatch.fnmatchcase(rel, pad[3:])


def globs_efetivos(cfg):
    """The three glob lists `rota` uses (and `info` shows): built-in defaults + config extras."""
    saida = {}
    for k, padrao in PADROES.items():
        extra = cfg.get(k) if isinstance(cfg.get(k), list) else []
        lista = list(padrao)
        for g in extra:
            if isinstance(g, str) and g not in lista:
                lista.append(g)
        saida[k] = lista
    return saida


def limpar(files):
    """One path per line, ends stripped, empties dropped."""
    return [p.strip() for f in files for p in str(f).splitlines() if p.strip()]


def _normal(peca):
    """`peca` without quotes/backticks/brackets around it, a leading list dash, trailing
    `,;:.` and a trailing line reference, repeated until nothing changes."""
    anterior = None
    while peca != anterior:
        anterior = peca
        peca = peca.strip().strip(BORDA)
        if peca.startswith("- "):
            peca = peca[2:]
        peca = RE_LINHA.sub("", peca.rstrip(",;:."))
    return peca


def candidatos(caminho):
    """The whole path plus normalised pieces (split on whitespace, `,`, `;` and `|`, zero-width
    characters dropped). Used only to ADD matches: the whole path is always first."""
    limpo = caminho.translate(ZERO)
    saida = [caminho]
    for peca in [limpo] + re.split(r"[\s,;|]+", limpo):
        for c in (peca, _normal(peca)):
            if c and c not in saida:
                saida.append(c)
    return saida


def _primeiro(rels, globs):
    """(path as matched, glob) of the first match, or None. Each entry holds the whole path
    and its candidates: a candidate can only add a match."""
    for orig, cands in rels:
        for g in globs:
            for rel in cands:
                if casa(rel, g):
                    return (orig if rel == cands[0] else "%s (as %s)" % (orig, rel)), g
    return None


def tem_diff(texto):
    """A diff has an `@@` line or a changed line (`+`/`-`) that is not a `+++ `/`--- ` header;
    anything else counts as missing."""
    return any(linha.startswith("@@") or (linha.startswith(("+", "-"))
                                          and not linha.startswith(("+++ ", "--- ")))
               for linha in texto.splitlines())


def _cabecalho(linhas, i):
    """Line i is part of a `--- `/`+++ ` pair followed by an `@@` line (a header-only patch
    is scanned whole and already forces security through `tem_diff`)."""
    def em(j, prefixo):
        return 0 <= j < len(linhas) and linhas[j].startswith(prefixo)
    if linhas[i].startswith("--- "):
        return em(i + 1, "+++ ") and em(i + 2, "@@")
    return linhas[i].startswith("+++ ") and i > 0 and em(i - 1, "--- ") and em(i + 1, "@@")


def linhas_mudadas(texto):
    """(`+` or `-`, text) of each changed line. Inside a hunk counted from its
    `@@ -a,b +c,d @@` header every `+`/`-` line is content; outside one only a `--- `/`+++ `
    pair followed by `@@` is a file header. Context lines never count."""
    linhas = texto.splitlines()
    velho = novo = 0
    for i, linha in enumerate(linhas):
        m = RE_HUNK.match(linha)
        if m:
            velho, novo = int(m.group(1) or 1), int(m.group(2) or 1)
            continue
        dentro = velho > 0 or novo > 0
        if linha.startswith("-"):
            velho -= 1
        elif linha.startswith("+"):
            novo -= 1
        elif not linha.startswith("\\"):
            velho, novo = velho - 1, novo - 1
        if not linha.startswith(("+", "-")):
            continue
        if not dentro and _cabecalho(linhas, i):
            continue
        yield linha[0], linha[1:]


def palavras_no_diff(texto):
    """(`added`/`removed`, keyword) found in CHANGED lines: removing a check is as much a
    security change as adding one."""
    achadas = []
    for sinal, resto in linhas_mudadas(texto):
        baixa = resto.lower()
        tipo = "added" if sinal == "+" else "removed"
        for k in PALAVRAS:
            if k in baixa and (tipo, k) not in achadas:
                achadas.append((tipo, k))
    return achadas


def ler_args(argv):
    files, diff, failed, texto = [], None, None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--files":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                files.append(argv[i])
                i += 1
            continue
        if a in ("--diff-file", "--failed", "--text-file") and i + 1 < len(argv):
            if a == "--diff-file":
                diff = argv[i + 1]
            elif a == "--text-file":
                texto = argv[i + 1]
            else:
                failed = argv[i + 1]
            i += 2
            continue
        raise ValueError("unknown or incomplete argument: %s" % a[:40])
    return files, diff, failed, texto


def rota(files, diff_file, failed, cfg, raiz, text_file=None):
    gl = globs_efetivos(cfg)
    risco, seg, banco = gl["risk_globs"], gl["security_globs"], gl["database_globs"]
    files = limpar(files)
    raizes = {_barra(raiz).lower().rstrip("/"), _barra(os.path.realpath(raiz)).lower().rstrip("/")}
    rels = [(f, [relativo(x, raizes) for x in candidatos(f)]) for f in files]
    why, executor, rev, risco_glob = [], SONNET, {"failures"}, None
    if not files:
        executor = OPUS
        rev.add("security")
        why.append("no files: no information, route up")
    m = _primeiro(rels, risco)
    if m:
        executor = risco_glob = OPUS
        why.append("risk_globs: %s matches %s" % m)
    if failed == "sonnet":
        executor = OPUS
        why.append("failed on sonnet: retry on opus")
    elif failed == "opus":
        executor = OPUS
        why.append("failed on opus: stays on opus")
    elif failed is not None:
        executor = OPUS
        why.append("unknown --failed value: route up")
    m = _primeiro(rels, banco)
    if m:
        rev.add("database")
        why.append("database_globs: %s matches %s" % m)
    m = _primeiro(rels, seg)
    if m:
        rev.add("security")
        why.append("security_globs: %s matches %s" % m)
    if diff_file is None:
        rev.add("security")
        why.append("no diff: cannot rule security out")
    else:
        try:
            with open(diff_file, "rb") as f:
                texto = f.read().decode("utf-8")
        except (OSError, ValueError) as e:
            rev.add("security")
            why.append("diff unreadable (%s): security runs" % type(e).__name__)
        else:
            if not tem_diff(texto):
                rev.add("security")
                why.append("diff file has no diff content: security runs")
            for tipo, k in palavras_no_diff(texto):
                rev.add("security")
                why.append("diff keyword in %s line: %s" % (tipo, k))
    if not why:
        why.append("no rule fired: sonnet, failures only")
    scores, fonte = {}, "globs" if risco_glob else "fixed"
    try:  # the router can only keep or raise `executor`; any error keeps the fixed rule
        executor, scores, fonte, extra = roteador.decidir(executor, bool(risco_glob), failed,
                                                          text_file, cfg)
        why.extend(extra)
    except Exception as e:
        log_erro("rota", "router: %s" % type(e).__name__)
        why.append("router error (%s): fixed rule" % type(e).__name__)
    return {"executor": executor, "reviewers": [r for r in ORDEM if r in rev], "why": why,
            "model": roteador.modelo(executor), "scores": scores, "source": fonte}


def rota_erro(e):
    return {"executor": OPUS, "reviewers": ["failures", "security", "database"],
            "why": ["error (%s): route up" % type(e).__name__],
            "model": "opus", "scores": {}, "source": "fixed"}


def roda_rota(argv):
    """Always prints one JSON line; any error routes up."""
    try:
        if TESTE and os.environ.get("TUNEUP_FAKE_EXCECAO") == "1":
            raise RuntimeError("simulated exception")
        files, diff, failed, texto = ler_args(argv)
        cwd = os.getcwd()
        saida = rota(files, diff, failed, carregar_config(cwd), toplevel(cwd), texto)
    except Exception as e:
        log_erro("rota", "%s: %s" % (type(e).__name__, e))
        saida = rota_erro(e)
    print(json.dumps(saida, ensure_ascii=False))
