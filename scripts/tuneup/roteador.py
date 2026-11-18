"""tune-up: optional model router for `guarda.py rota` (asks the Jev scorer about the item text).

Runs only when the trusted config has `router.enabled: true`. It can only keep or RAISE the
fixed rule's executor, never lower it. Sends only the `--text-file` content, and only when its
base name ends `.rota.txt` and it is not a symlink: lines from the first REAL DATA / PITFALLS /
diff marker on (any case, after `#`, `*`, `-`, `>` or spaces) are dropped, the rest masked and
cut to max_chars.
"""
import os
import re

from . import jev
from .config import router_valido
from .mascara import mascarar
from .sessao import log_erro

OPUS, SONNET = "tune-up:executor-opus", "tune-up:executor-sonnet"
LIMITE_BYTES = 64 * 1024
CORTE = re.compile(r"[\s#*>-]*(?:real data|pitfalls|diff --git|@@ )", re.IGNORECASE)
PERGUNTAS = {
    "mechanical": "Is this task mechanical: a small, well-specified edit (rename, copy change, "
                  "config value, one obvious line) that needs no design decisions?",
    "risk": "Could a mistake in this task cause serious harm: touch authentication, permissions, "
            "money or payments, user data, database schema or migrations, secrets, or messages "
            "sent to real people?",
    "hard": "Is this task hard: several files or components must change together, tricky logic, "
            "concurrency, or a subtle bug whose cause is not stated?",
    "visual": "Is this task mainly visual: user interface layout, styling, components or screens "
              "that someone has to look at to verify?",
}


def modelo(executor):
    return {OPUS: "opus", SONNET: "sonnet"}.get(executor)


def nome_aceito(caminho):
    """The base name (`/` or `\\`) ends `.rota.txt` and the path is not a symlink."""
    return re.split(r"[/\\]", caminho)[-1].endswith(".rota.txt") and not os.path.islink(caminho)


def texto_para_enviar(caminho, max_chars):
    """What may reach the scorer, or None (missing, over 64 KB, not UTF-8, or empty)."""
    try:
        with open(caminho, "rb") as f:
            bruto = f.read(LIMITE_BYTES + 1)
        if len(bruto) > LIMITE_BYTES:
            log_erro("rota", "router: text file over 64 KB")
            return None
        texto = bruto.decode("utf-8")
    except (OSError, ValueError) as e:
        log_erro("rota", "router: text file unreadable (%s)" % type(e).__name__)
        return None
    linhas = []
    for linha in texto.splitlines():
        if CORTE.match(linha):
            break
        linhas.append(linha)
    texto = mascarar("\n".join(linhas).strip())[:max_chars].strip()
    return texto or None


def decidir(fixo, risco_glob, failed, texto_arq, cfg):
    """(executor, scores, source, why) in this fixed order:
    a. risk_globs matched: the fixed rule (opus), source `globs`, the scorer is NOT called.
    b. router off/invalid, no --text-file, unusable text or no answer (no key, error): fixed rule.
    c. scorer answered: risk >= threshold -> opus; else hard >= threshold -> opus.
    d. router on, `--failed opus` and hard_agent set: hard_agent (with or without an answer).
    e. visual_agent set, visual >= threshold, no risk glob, risk below its threshold, and the
       executor so far is sonnet: visual_agent.
    f. otherwise the fixed rule's executor (sonnet or opus). Never haiku, never below fixed.
    `source` says who decided the LEVEL (`globs`, `fixed` or `jev`); a hard_agent/visual_agent
    substitution is named in `why`. A text file not named `*.rota.txt` (or a symlink) is never
    read: fixed rule."""
    fonte = "globs" if risco_glob else "fixed"
    r = cfg.get("router")
    if not isinstance(r, dict) or r.get("enabled") is not True or not router_valido(r):
        return fixo, {}, fonte, []
    t = r.get("thresholds") or {}
    executor, scores, why = fixo, {}, []
    if not risco_glob and texto_arq is not None and not nome_aceito(texto_arq):
        why.append("router: text file name refused (not *.rota.txt, or a symlink): fixed rule")
    elif not risco_glob and texto_arq is not None:
        texto = texto_para_enviar(texto_arq, r.get("max_chars", 6000))
        resp = jev.perguntar(texto, PERGUNTAS) if texto else None
        if isinstance(resp, dict) and set(resp) == set(PERGUNTAS):
            scores, fonte = resp, "jev"
            if resp["risk"] >= t.get("risk", 0.0):
                executor = OPUS
                why.append("router: risk %.2f >= %s: opus" % (resp["risk"], t.get("risk", 0.0)))
            elif resp["hard"] >= t.get("hard", 0.0):
                executor = OPUS
                why.append("router: hard %.2f >= %s: opus" % (resp["hard"], t.get("hard", 0.0)))
            elif (r.get("visual_agent") and executor == SONNET
                  and resp["visual"] >= t.get("visual", 1.1)):
                executor = r["visual_agent"]
                why.append("router: visual %.2f: visual_agent %s" % (resp["visual"], executor))
        else:
            why.append("router: no score, fixed rule")
    if failed == "opus" and r.get("hard_agent"):
        executor = r["hard_agent"]
        why.append("router: failed on opus: hard_agent %s" % executor)
    return executor, scores, fonte, why
