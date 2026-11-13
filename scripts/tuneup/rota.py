"""tune-up: `guarda.py rota` — which executor and which reviewers for a work item, from its paths.

Rule: when in doubt the item goes UP (opus) and the security reviewer runs. Never reads stdin.
"""
import fnmatch
import json
import os
import re

from .config import TESTE, carregar_config
from .info import toplevel
from .sessao import log_erro

OPUS, SONNET = "tune-up:executor-opus", "tune-up:executor-sonnet"
ORDEM = ("failures", "security", "database")
PALAVRAS = ("auth", "token", "secret", "password", "hmac", "signature", "permission",
            "subprocess", "eval", "../", "..\\")
RE_ABS = re.compile(r"(/|[a-z]:/)")  # after `\` -> `/` and lowercase: POSIX, UNC or `C:/`


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


def _primeiro(rels, globs):
    """(original path, glob) of the first match, or None."""
    for orig, rel in rels:
        for g in globs:
            if casa(rel, str(g)):
                return orig, g
    return None


def palavras_no_diff(texto):
    """Keywords found in ADDED lines (`+`, not the `+++` file header right after `---`)."""
    achadas = []
    anterior = ""
    for linha in texto.splitlines():
        cabecalho = linha.startswith("+++ ") and anterior.startswith("--- ")
        anterior = linha
        if not linha.startswith("+") or cabecalho:
            continue
        baixa = linha[1:].lower()
        for k in PALAVRAS:
            if k in baixa and k not in achadas:
                achadas.append(k)
    return achadas


def ler_args(argv):
    files, diff, failed = [], None, None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--files":
            i += 1
            while i < len(argv) and not argv[i].startswith("--"):
                files.append(argv[i])
                i += 1
            continue
        if a in ("--diff-file", "--failed") and i + 1 < len(argv):
            if a == "--diff-file":
                diff = argv[i + 1]
            else:
                failed = argv[i + 1]
            i += 2
            continue
        raise ValueError("unknown or incomplete argument: %s" % a[:40])
    return files, diff, failed


def rota(files, diff_file, failed, cfg, raiz):
    risco = [str(x) for x in cfg.get("risk_globs") or []]
    seg = [str(x) for x in cfg.get("security_globs") or []]
    banco = [str(x) for x in cfg.get("database_globs") or []]
    if not (risco and seg and banco):
        raise RuntimeError("default glob lists missing (padrao.json unreadable?)")
    raizes = {_barra(raiz).lower().rstrip("/"), _barra(os.path.realpath(raiz)).lower().rstrip("/")}
    rels = [(f, relativo(f, raizes)) for f in files]
    why, executor, rev = [], SONNET, {"failures"}
    if not files:
        executor = OPUS
        rev.add("security")
        why.append("no files: no information, route up")
    m = _primeiro(rels, risco)
    if m:
        executor = OPUS
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
            for k in palavras_no_diff(texto):
                rev.add("security")
                why.append("diff keyword in added line: %s" % k)
    if not why:
        why.append("no rule fired: sonnet, failures only")
    return {"executor": executor, "reviewers": [r for r in ORDEM if r in rev], "why": why}


def rota_erro(e):
    return {"executor": OPUS, "reviewers": ["failures", "security"],
            "why": ["error (%s): route up" % type(e).__name__]}


def roda_rota(argv):
    """Always prints one JSON line; any error routes up."""
    try:
        if TESTE and os.environ.get("TUNEUP_FAKE_EXCECAO") == "1":
            raise RuntimeError("simulated exception")
        files, diff, failed = ler_args(argv)
        cwd = os.getcwd()
        saida = rota(files, diff, failed, carregar_config(cwd), toplevel(cwd))
    except Exception as e:
        log_erro("rota", "%s: %s" % (type(e).__name__, e))
        saida = rota_erro(e)
    print(json.dumps(saida, ensure_ascii=False))
