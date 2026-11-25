"""Custo por sessão do Claude Code, só leitura, a partir dos transcritos (.jsonl).

Lógica de medir-uso.py: dedupe por message.id (aqui, o MÁXIMO de cada campo entre as linhas
repetidas), soma entrada/saída/cache por modelo; conversa principal + subagentes em
<sessao>/subagents/**. Lê só as sessões pedidas, linha a linha em binário, com cache por
caminho (mtime_ns, tamanho). A resposta não leva texto, caminho nem título. Python 3.9, stdlib.
"""
import json
import os
import re
import stat
import threading

import agentes
import agentes_disco as disco
from transcricao import RE_SESSAO

MAX_SESSOES = 60
LINHA_MAX = 8 * 1024 * 1024
CACHE_MAX = 5000
# ESTIMATIVA: preços ASSUMIDOS (não são o preço oficial; Fable assumido em 2x o Opus), US$ por Mtok.
# Escrita de cache: 5 min = 1,25x a entrada, 1 h = 2x a entrada.
PRECOS = {"opus": (5.0, 25.0, 0.5), "sonnet": (3.0, 15.0, 0.3), "haiku": (1.0, 5.0, 0.1), "fable": (10.0, 50.0, 1.0)}
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")

_trava = threading.Lock()
_cache = {}  # caminho -> (assinatura, resultado)


def esquecer():
    with _trava:
        _cache.clear()


def _n(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and v > 0 else 0


def _familia(modelo):
    baixo = modelo.lower()
    for f in PRECOS:
        if f in baixo:
            return f
    return RE_CONTROLE.sub("", modelo).strip()[:60]


def _linhas(f):
    """Linhas completas (terminam em \\n); a última, ainda sendo escrita, e as gigantes ficam de fora."""
    while True:
        bruta = f.readline(LINHA_MAX + 1)
        if not bruta:
            return
        if len(bruta) > LINHA_MAX and not bruta.endswith(b"\n"):
            while bruta and not bruta.endswith(b"\n"):  # descarta o resto da linha gigante
                bruta = f.readline(LINHA_MAX)
            continue
        if bruta.endswith(b"\n"):
            yield bruta


def _registro(msg, usos, sem_id):
    uso = msg.get("usage")
    modelo = msg.get("model")
    if not isinstance(uso, dict) or not isinstance(modelo, str) or not modelo.strip() or modelo.startswith("<"):
        return
    mid = msg.get("id")
    chave = mid if isinstance(mid, str) and mid else ("sem", sem_id[0])
    sem_id[0] += 1
    cc = _n(uso.get("cache_creation_input_tokens"))
    cri = uso.get("cache_creation")
    h1 = min(_n(cri.get("ephemeral_1h_input_tokens")) if isinstance(cri, dict) else 0, cc)
    r = usos.get(chave)
    if r is None:
        r = usos[chave] = {"m": _familia(modelo.strip()), "i": 0, "o": 0, "r": 0, "c": -1, "h": 0}
    r["i"] = max(r["i"], _n(uso.get("input_tokens")))
    r["o"] = max(r["o"], _n(uso.get("output_tokens")))
    r["r"] = max(r["r"], _n(uso.get("cache_read_input_tokens")))
    if cc > r["c"]:  # a divisão 5m/1h vem da linha de maior cache_creation
        r["c"], r["h"] = cc, h1


def _ler(caminho):
    """Lê um .jsonl: {"ok", "ctx", "mod": {modelo: [entrada, saída, cache 5m, cache 1h, leitura]}}."""
    usos, sem_id, ok = {}, [0], True
    try:
        with open(caminho, "rb") as f:
            for linha in _linhas(f):
                if b'"usage"' not in linha:
                    continue
                try:
                    obj = json.loads(linha)
                except ValueError:
                    continue
                msg = obj.get("message") if isinstance(obj, dict) else None
                if isinstance(msg, dict):
                    _registro(msg, usos, sem_id)
    except OSError:
        ok = False
    mod, ctx = {}, None
    for r in usos.values():
        c = max(r["c"], 0)
        v = mod.setdefault(r["m"], [0, 0, 0, 0, 0])
        for k, x in enumerate((r["i"], r["o"], c - r["h"], r["h"], r["r"])):
            v[k] += x
        ctx = max(ctx or 0, r["i"] + c + r["r"])
    return {"ok": ok, "ctx": ctx, "mod": mod}


def _arquivo(caminho):
    """Resultado em cache por (mtime_ns, tamanho); stat ANTES de ler. None: não é arquivo comum."""
    try:
        st = os.lstat(caminho)
    except OSError:
        return {"ok": False, "ctx": None, "mod": {}}
    if not stat.S_ISREG(st.st_mode):
        return None
    sig = (st.st_mtime_ns, st.st_size)
    with _trava:
        c = _cache.get(caminho)
    if c and c[0] == sig:
        return c[1]
    res = _ler(caminho)
    if res["ok"]:
        with _trava:
            _cache[caminho] = (sig, res)
            while len(_cache) > CACHE_MAX:
                _cache.pop(next(iter(_cache)))
    return res


def _usd(v, preco):
    pe, ps, pl = preco
    return (v[0] * pe + v[1] * ps + v[2] * 1.25 * pe + v[3] * 2 * pe + v[4] * pl) / 1e6


def _sessao(op, sid):
    vazio = {"sessao_id": sid, "encontrada": False, "parcial": False, "tokens": None, "contexto_maximo": None,
             "subagentes": 0, "usd": None, "usd_incompleto": False, "modelos": []}
    try:
        caminho = agentes._achar_conversa(op, sid, None)
    except Exception:
        caminho = None
    if not caminho:
        return vazio
    principal = _arquivo(caminho)
    parcial = principal is None or not principal["ok"]
    resultados = [] if principal is None else [principal]
    subs = []
    try:
        subs, _wfs = agentes._agentes_crus(caminho[:-len(".jsonl")], op)
    except Exception:
        parcial = True
    if len(subs) >= agentes.MAX_ARQUIVOS:
        parcial = True
    n_subs = 0
    for s in subs:
        if not disco.dentro(op["projects"], s["caminho"]):
            continue
        r = _arquivo(s["caminho"])
        if r is None:
            continue
        n_subs += 1
        parcial = parcial or not r["ok"]
        resultados.append(r)
    total = {}
    for r in resultados:
        for m, v in r["mod"].items():
            t = total.setdefault(m, [0, 0, 0, 0, 0])
            for i in range(5):
                t[i] += v[i]
    modelos = [{"modelo": m, "tokens": sum(v), "usd": _usd(v, PRECOS[m]) if m in PRECOS else None}
               for m, v in total.items()]
    precificados = [x["usd"] for x in modelos if x["usd"] is not None]
    soma = sum(precificados)
    for x in modelos:
        x["pct"] = None if x["usd"] is None else (round(100.0 * x["usd"] / soma, 1) if soma > 0 else 0.0)
        x["usd"] = None if x["usd"] is None else round(x["usd"], 4)
    modelos.sort(key=lambda x: (x["usd"] is None, -(x["usd"] or 0), -x["tokens"]))
    t = [sum(v[i] for v in total.values()) for i in range(5)]
    vazio.update(encontrada=True, parcial=parcial, subagentes=n_subs, modelos=modelos,
                 tokens={"entrada": t[0], "saida": t[1], "cache_escrita": t[2] + t[3], "cache_leitura": t[4],
                         "total": sum(t)},
                 contexto_maximo=principal["ctx"] if principal else None,
                 usd=round(soma, 4) if precificados else None,
                 usd_incompleto=any(m not in PRECOS for m in total))
    return vazio


def responder(cfg, ids):
    """(codigo, corpo) de GET /api/custo?sessao=...; ids = lista crua da query."""
    vistos = []
    for i in ids or []:
        if not isinstance(i, str) or not RE_SESSAO.fullmatch(i):
            return 400, {"erro": "Sessão inválida."}
        if i not in vistos:
            vistos.append(i)
    if len(vistos) > MAX_SESSOES:
        return 400, {"erro": "Sessão inválida."}
    op = agentes._opcoes(cfg)
    return 200, {"estimativa": True, "sessoes": [_sessao(op, i) for i in vistos]}
