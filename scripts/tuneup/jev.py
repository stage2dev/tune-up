"""tune-up: stdlib client for the Jev scorer (yes/no likelihood questions about a text).

`perguntar(texto, perguntas)` -> {name: float in 0..1}, or None on ANY error.
The key is never printed, logged or written; the text is masked before it leaves.
"""
import json
import os
import urllib.request

from .mascara import mascarar
from .sessao import log_erro

URL = "https://api.typesafe.ai/v1/systemone"
MODELO = "jev-latest"
TIMEOUT = 5


class _SemRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect: the Authorization header must never reach another host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib then raises HTTPError with the 3xx code


def _abridor(*extra):
    return urllib.request.build_opener(_SemRedirect, *extra)


def _urllib(url, cabecalhos, corpo, timeout, abridor=None):
    """Default transport: one POST attempt, no redirects. Returns the response bytes or raises."""
    req = urllib.request.Request(url, data=corpo, headers=cabecalhos, method="POST")
    with (abridor or _abridor()).open(req, timeout=timeout) as r:
        return r.read()


def _chave(ambiente, settings):
    k = (ambiente.get("TYPESAFE_API_KEY") or "").strip()
    if k:
        return k
    try:
        with open(settings, encoding="utf-8") as f:
            v = (json.load(f).get("env") or {}).get("TYPESAFE_API_KEY")
        return v.strip() if isinstance(v, str) else ""
    except Exception:
        return ""


def _numero(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    v = float(v)
    return v if 0.0 <= v <= 1.0 else None  # NaN fails both comparisons


def perguntar(texto, perguntas, *, transporte=None, ambiente=None, settings=None):
    """perguntas: {name: instructions}. Returns {name: float} or None (reason in erros.log)."""
    try:
        if not perguntas:
            log_erro("jev", "no questions")
            return None
        if ambiente is None:
            ambiente = os.environ
        if settings is None:
            settings = os.path.expanduser(os.path.join("~", ".claude", "settings.json"))
        chave = _chave(ambiente, settings)
        if not chave:
            log_erro("jev", "no key")
            return None
        corpo = json.dumps({
            "model": MODELO,
            "state": {"task": mascarar(texto)},
            "questions": {n: {"type": "noul", "instructions": i} for n, i in perguntas.items()},
        }).encode("utf-8")
        cabecalhos = {"authorization": "Bearer " + chave, "content-type": "application/json"}
        bruto = (transporte or _urllib)(URL, cabecalhos, corpo, TIMEOUT)
    except Exception as e:  # timeout, HTTP error, refused redirect...: only the type, never the message
        log_erro("jev", "request failed: %s%s" % (type(e).__name__, " %s" % e.code if isinstance(getattr(e, "code", None), int) else ""))
        return None
    try:
        respostas = json.loads(bruto)["answers"]
        saida = {n: _numero(respostas[n]["noul"]) for n in perguntas}
    except Exception as e:
        log_erro("jev", "bad response: %s" % type(e).__name__)
        return None
    if any(v is None for v in saida.values()):
        log_erro("jev", "bad response: answer is not a number in 0..1")
        return None
    return saida
