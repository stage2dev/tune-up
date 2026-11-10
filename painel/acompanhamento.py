"""GET /api/acompanhamento: listas de trabalho do claude-mem (work state), só leitura.

Lê ~/.claude-mem/claude-mem.db em modo somente leitura (uri mode=ro), tabela
work_state_entries, e repete a regra do worker do claude-mem (15.14.0):
- log só de inserção; agrupa por lista, em ordem de id;
- linha sem `task` é ESTADO da lista (última chave vence, null apaga);
- linha com `task` é ITEM: junta os campos por nome da tarefa (null apaga);
- item fechado = status done ou dropped; lista fechada = estado status done.
Cada lista cai na primeira área de painel.json "areas_acompanhamento" cuja
regex casa o nome (ou na área do campo `area` do estado da lista); sem área
que case, vai para "geral". Banco ausente, travado ou fora do formato: listas
vazias + aviso. Nunca escreve.
"""
import json
import os
import re
import sqlite3
import threading
import time

from mascara import mascarar

TTL = 15
TIMEOUT_DB = 2.0
STATUS = ("todo", "doing", "done", "dropped")
FECHADO = ("done", "dropped")
IGNORAR_LISTAS = ("agent-lifecycle",)
EXTRAS_NOTAS = (("proximo", "Próximo"), ("falta", "Falta"))
GERAL = {"id": "geral", "titulo": "Geral"}
MAX_TEXTO = 1500

_cache = {}
_lock = threading.Lock()


def _texto(v, maximo=MAX_TEXTO):
    if v is None:
        return ""
    s = mascarar(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    return s if len(s) <= maximo else s[: maximo - 1] + "…"


def _produtos(wp):
    """work_product: URL/caminho, lista, ou string JSON '[{"title","url"}]'."""
    if wp is None or wp == "":
        return []
    if isinstance(wp, str) and wp.strip().startswith("["):
        try:
            wp = json.loads(wp)
        except ValueError:
            pass
    itens = wp if isinstance(wp, list) else [wp]
    saida = []
    for x in itens:
        if isinstance(x, dict):
            url = x.get("url") or x.get("path")
            if url:
                saida.append({"titulo": _texto(x.get("title") or x.get("titulo") or os.path.basename(str(url).rstrip("/")), 200),
                              "url": _texto(url, 600)})
        elif isinstance(x, str) and x.strip():
            u = x.strip()
            saida.append({"titulo": os.path.basename(u.rstrip("/")) or u, "url": _texto(u, 600)})
    return saida


def _status(v):
    s = str(v or "").strip().lower()
    return s if s in STATUS else "todo"


def _pegar(cfg, chave):
    if isinstance(cfg, dict):
        return cfg.get(chave)
    return getattr(cfg, chave, None)


def normalizar_cfg(cfg=None):
    """Aceita dict, objeto simples ou None. Só o que este módulo usa."""
    raiz = str(_pegar(cfg, "raiz") or _pegar(cfg, "workspace") or os.getcwd())
    areas = [a for a in _pegar(cfg, "areas_acompanhamento") or []
             if isinstance(a, dict) and isinstance(a.get("id"), str) and isinstance(a.get("regex"), str)]
    return {"claude_mem_db": str(_pegar(cfg, "claude_mem_db") or os.path.expanduser("~/.claude-mem/claude-mem.db")),
            "projeto_mem": str(_pegar(cfg, "projeto_mem") or os.path.basename(raiz.rstrip("/"))),
            "areas": areas}


def classificar(nome, estado, areas):
    """Id da área da lista. `estado.area` manda se for uma área conhecida; senão a 1ª regex que casa."""
    ids = [a["id"] for a in areas] + [GERAL["id"]]
    area = str((estado or {}).get("area") or "").strip().lower()
    if area in ids:
        return area
    for a in areas:
        try:
            if re.search(a["regex"], nome, re.I):
                return a["id"]
        except re.error:
            continue
    return GERAL["id"]


def reduzir(linhas, cfg):
    """linhas: [(list_name, fields_json, created_at)] em ordem de id."""
    listas = {}
    avisos = 0
    for nome, campos_txt, criado in linhas:
        if nome in IGNORAR_LISTAS:
            continue
        try:
            campos = json.loads(campos_txt)
        except (TypeError, ValueError):
            avisos += 1
            continue
        if not isinstance(campos, dict):
            avisos += 1
            continue
        lista = listas.setdefault(nome, {"estado": {}, "itens": {}, "atualizado_em": criado})
        lista["atualizado_em"] = criado
        tarefa = campos.get("task")
        alvo = lista["estado"]
        if tarefa:
            tarefa = str(tarefa)
            alvo = lista["itens"].setdefault(tarefa, {"_atualizado_em": criado})
            alvo["_atualizado_em"] = criado
        for k, v in campos.items():
            if v is None:
                alvo.pop(k, None)
            else:
                alvo[k] = v
    saida = []
    for nome, l in listas.items():
        itens = []
        for tarefa, campos in l["itens"].items():
            notas = _texto(campos.get("notas"))
            extras = list(EXTRAS_NOTAS) + [(k, "Falta (%s)" % k[6:].replace("_", " ")) for k in sorted(campos)
                                            if re.match(r"^falta_[a-z0-9_]{1,30}$", str(k))]
            for chave, rotulo in extras:
                if campos.get(chave) not in (None, ""):
                    notas = (notas + "\n" if notas else "") + "%s: %s" % (rotulo, _texto(campos[chave], 600))
            itens.append({"tarefa": _texto(tarefa, 300), "status": _status(campos.get("status")),
                          "notas": notas, "produtos": _produtos(campos.get("work_product")),
                          "atualizado_em": campos["_atualizado_em"]})
        itens.sort(key=lambda i: i["atualizado_em"], reverse=True)
        estado = {str(k): _texto(v, 500) for k, v in l["estado"].items()}
        fechada = str(l["estado"].get("status") or "").lower() in FECHADO
        aberta = (not fechada) and (not itens or any(i["status"] not in FECHADO for i in itens))
        saida.append({"nome": nome,
                      "area": classificar(nome, l["estado"], cfg["areas"]),
                      "atualizado_em": l["atualizado_em"], "aberta": aberta,
                      "itens": itens, "estado": estado})
    saida.sort(key=lambda x: x["atualizado_em"], reverse=True)
    return saida, avisos


def ler_linhas(caminho_db, projeto):
    if not os.path.isfile(caminho_db):
        raise FileNotFoundError("banco do claude-mem não encontrado")
    uri = "file:%s?mode=ro" % caminho_db.replace("?", "%3f").replace("#", "%23")
    con = sqlite3.connect(uri, uri=True, timeout=TIMEOUT_DB)
    try:
        con.execute("PRAGMA query_only = ON")
        return con.execute(
            "SELECT list_name, fields, created_at FROM work_state_entries "
            "WHERE project = ? COLLATE NOCASE ORDER BY id", (projeto,)).fetchall()
    finally:
        con.close()


def montar(cfg=None, usar_cache=True):
    c = normalizar_cfg(cfg)
    chave = (c["claude_mem_db"], c["projeto_mem"], json.dumps(c["areas"], sort_keys=True))
    agora = time.monotonic()
    if usar_cache:
        with _lock:
            item = _cache.get(chave)
            if item and agora - item[0] < TTL:
                return item[1]
    avisos = []
    try:
        linhas = ler_linhas(c["claude_mem_db"], c["projeto_mem"])
        listas, ruins = reduzir(linhas, c)
        if ruins:
            avisos.append("%d linha(s) do claude-mem com campos ilegíveis foram puladas." % ruins)
        if not listas:
            avisos.append("Nenhuma lista do projeto %s no claude-mem." % c["projeto_mem"])
    except (OSError, sqlite3.Error) as e:
        listas = []
        avisos.append("Não deu para ler o claude-mem (%s). Listas vazias por enquanto." % type(e).__name__)
    usadas = {x["area"] for x in listas}
    areas = [{"id": a["id"], "titulo": a.get("titulo") or a["id"]} for a in c["areas"]]
    if GERAL["id"] in usadas or not areas:
        areas.append(dict(GERAL))
    dados = {"areas": areas, "listas": listas, "avisos": avisos}
    if usar_cache:
        with _lock:
            _cache.clear()
            _cache[chave] = (time.monotonic(), dados)
    return dados
