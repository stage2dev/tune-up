"""Tela de Agentes: sessões do Claude Code deste projeto e os sub-agentes de cada uma.

montar(cfg, sessao=None, todos=False) devolve o formato "Agentes" do contrato
(contrato/agentes.d.ts). Fontes:
- `claude agents --json --all`: sessões (id, sessionId, cwd, kind, name, state/status);
- ~/.claude/projects/<pasta>/<sessionId>.jsonl: modelo e esforço da sessão;
- <mesma pasta>/<sessionId>/subagents/agent-<id>.jsonl + .meta.json: sub-agentes diretos;
  sub-agente criado por outro sub-agente fica na MESMA pasta subagents/ (plana), com
  spawnDepth 2 e "parentAgentId" no meta (medido no disco em 10/11, CLI 2.1.32x); o
  "toolUseId" do meta é o id do tool_use Agent/Task na conversa do pai (usado como reserva);
- <mesma pasta>/<sessionId>/subagents/workflows/<wf_id>/agent-*.jsonl + .meta.json + journal.jsonl.
Lê pouco de cada arquivo (ver agentes_disco.py) e guarda o resultado por 2 s.
Python 3.9, só biblioteca padrão.
"""
import json
import os
import re
import subprocess
import threading
import time

import agentes_disco as disco

try:  # mesmo mapeamento de estado do lançador (regra dos 180 s sem escrita)
    from lancador import mapear_estado as _mapear_estado
except Exception:  # pragma: no cover - núcleo em obra: cai num mapeamento mínimo
    _mapear_estado = None
try:
    from lancador import Registro as _Registro
except Exception:  # pragma: no cover
    _Registro = None
try:
    from transcricao import localizar as _localizar
except Exception:  # pragma: no cover
    _localizar = None

CACHE_S = 2.0
TTL_TERMINADOS = 30 * 60
VIVO_S = 120
MAX_AGENTES = 200
MAX_TODOS = 2000
MAX_ARQUIVOS = 5000
RE_SESSAO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
RE_ID_CURTO = re.compile(r"^[0-9a-f]{6,16}$")
RE_AGENTE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
RE_WF = re.compile(r"^wf_[A-Za-z0-9_\-]{1,40}$")
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
ATIVOS = ("rodando", "precisa_de_voce")

_trava = threading.Lock()
_cache = {}


def esquecer():
    with _trava:
        _cache.clear()
    disco.esquecer_tudo()


def _pegar(cfg, *chaves):
    for k in chaves:
        v = None
        if isinstance(cfg, dict):
            v = cfg.get(k)
        elif cfg is not None:
            v = getattr(cfg, k, None)
        if v:
            return v
    return None


def _opcoes(cfg):
    raiz = _pegar(cfg, "raiz", "workspace") or os.getcwd()
    projects = _pegar(cfg, "projects_dir") or os.path.join(os.path.expanduser("~"), ".claude", "projects")
    return {"raiz": os.path.realpath(os.path.expanduser(str(raiz))),
            "projects": os.path.realpath(os.path.expanduser(str(projects))),
            "claude_bin": str(_pegar(cfg, "claude_bin") or "claude"),
            "dados_dir": _pegar(cfg, "dados_dir")}


def _rodar_padrao(cmd, cwd, timeout):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, shell=False)
    except (OSError, subprocess.SubprocessError):
        return 1, "", ""
    return r.returncode, r.stdout or "", r.stderr or ""


def _listar_cli(op, rodar):
    cwd = op["raiz"] if os.path.isdir(op["raiz"]) else None
    cod, out, _err = (rodar or _rodar_padrao)([op["claude_bin"], "agents", "--json", "--all"], cwd, 8)
    try:
        lista = json.loads(out) if cod == 0 else None
    except ValueError:
        lista = None
    if not isinstance(lista, list):
        return None
    return [x for x in lista if isinstance(x, dict)]


def _texto(valor, n):
    return RE_CONTROLE.sub("", str(valor or "")).strip()[:n]


def _no_projeto(cwd, raiz):
    if not isinstance(cwd, str) or not cwd or "\x00" in cwd:
        return False
    real = os.path.realpath(cwd)
    return real == raiz or real.startswith(raiz.rstrip(os.sep) + os.sep)


def _estado_basico(linha, ocioso_ha):
    """Reserva se o lancador não importar: mesma regra (180 s sem escrita = terminou)."""
    state = str(linha.get("state") or "").lower()
    status = str(linha.get("status") or "").lower()
    if state == "blocked" or status == "waiting":
        return "precisa_de_voce"
    if status == "busy":
        return "rodando"
    if state in ("working", "running", "busy", "active"):
        return "terminou" if status == "idle" and ocioso_ha is not None and ocioso_ha > 180 else "rodando"
    if state in ("done", "completed", "finished"):
        return "terminou"
    if state in ("stopped", "killed", "failed", "error", "exited"):
        return "parada"
    return "terminou" if status == "idle" else "rodando"


def _estado_sessao(linha, reg, agora, ocioso_ha, interativa):
    try:
        e = _mapear_estado(reg or {}, linha, agora, ocioso_ha) if _mapear_estado else None
    except Exception:
        e = None
    e = e or _estado_basico(linha, ocioso_ha)
    if e == "sumiu":
        e = "parada"
    if interativa and e == "terminou":
        e = "ocioso"
    return e if e in ("rodando", "precisa_de_voce", "ocioso", "terminou", "parada") else "rodando"


def _achar_conversa(op, sid, cwd):
    caminho = None
    if _localizar:
        try:
            caminho = _localizar(op["projects"], sid, cwd)
        except Exception:
            caminho = None
    if not caminho:
        import glob
        achados = glob.glob(os.path.join(op["projects"], "*", sid + ".jsonl"))
        caminho = achados[0] if achados else None
    if not caminho or os.path.islink(caminho) or not disco.dentro(op["projects"], caminho):
        return None
    return caminho


def _varrer_pasta(pasta, wf, op, saida, contador):
    """Acha agent-<id>.jsonl (sem seguir symlink) e junta com o .meta.json."""
    try:
        entradas = list(os.scandir(pasta))
    except OSError:
        return
    metas = {}
    for e in entradas:
        if e.name.endswith(".meta.json") and e.name.startswith("agent-") and not e.is_symlink():
            metas[e.name[len("agent-"):-len(".meta.json")]] = e
    for e in entradas:
        if not (e.name.startswith("agent-") and e.name.endswith(".jsonl")) or e.is_symlink():
            continue
        aid = e.name[len("agent-"):-len(".jsonl")]
        if not RE_AGENTE.match(aid) or not e.is_file(follow_symlinks=False):
            continue
        contador[0] += 1
        if contador[0] > MAX_ARQUIVOS:
            return
        try:
            st = e.stat(follow_symlinks=False)
        except OSError:
            continue
        meta = None
        if aid in metas:
            try:
                meta = disco.ler_json(metas[aid].path, metas[aid].stat(follow_symlinks=False))
            except OSError:
                meta = None
        saida.append({"id": aid, "caminho": e.path, "st": st, "meta": meta or {}, "wf": wf})


def _agentes_crus(pasta_sessao, op):
    """Lista crua dos sub-agentes da sessão + dados dos workflows."""
    crus, wfs, contador = [], {}, [0]
    sub = os.path.join(pasta_sessao, "subagents")
    if not os.path.isdir(sub) or os.path.islink(sub) or not disco.dentro(op["projects"], sub):
        return crus, wfs
    _varrer_pasta(sub, None, op, crus, contador)
    pasta_wf = os.path.join(sub, "workflows")
    if not os.path.isdir(pasta_wf) or os.path.islink(pasta_wf):
        return crus, wfs
    try:
        dirs = [e for e in os.scandir(pasta_wf) if RE_WF.match(e.name) and e.is_dir(follow_symlinks=False)]
    except OSError:
        dirs = []
    scripts = os.path.join(pasta_sessao, "workflows", "scripts")
    for d in dirs:
        jornal = {"fases": [], "fase_de": {}, "terminados": set()}
        caminho_j = os.path.join(d.path, "journal.jsonl")
        try:
            if not os.path.islink(caminho_j) and os.path.isfile(caminho_j):
                jornal = disco.ler_journal(caminho_j, os.stat(caminho_j))
        except OSError:
            pass
        nome = None
        if os.path.isdir(scripts) and not os.path.islink(scripts):
            nome = disco.nome_workflow(scripts, d.name, op["projects"])
        wfs[d.name] = {"nome": nome or d.name, "jornal": jornal}
        _varrer_pasta(d.path, d.name, op, crus, contador)
    return crus, wfs


def _estado_agente(cru, wfs, agora, sessao_ativa):
    recente = agora - cru["st"].st_mtime < VIVO_S
    if cru["wf"]:
        if cru["id"] in wfs[cru["wf"]]["jornal"]["terminados"]:
            return "terminou"
        return "rodando" if recente or sessao_ativa else "terminou"
    fim = cru["meta"].get("finished")
    if fim is True:
        return "terminou"
    if fim is False:
        return "rodando" if recente or sessao_ativa else "terminou"
    return "rodando" if recente else "terminou"


def _inteiro(v):
    return v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v < 100 else None


def _agente(cru, wfs, estado, agora, pais):
    meta, st = cru["meta"], cru["st"]
    fim = disco.cauda(cru["caminho"], st.st_size)
    n, _spawns = disco.contar(cru["caminho"], st.st_size)
    iniciado = disco.primeiro_ts(cru["caminho"], st)
    ultima = disco.iso_local(st.st_mtime)
    t0 = disco.epoch_de(iniciado)
    t1 = agora if estado == "rodando" else st.st_mtime
    modelo_id = fim["modelo_id"] or (_texto(meta.get("model"), 80) or None)
    fase = None
    if cru["wf"]:
        fase = wfs[cru["wf"]]["jornal"]["fase_de"].get(cru["id"])
    fase = fase or (_texto(meta.get("workflowPhase"), 80) or None)
    return {
        "id": cru["id"],
        "tipo_agente": _texto(meta.get("agentType"), 60) or "sub-agente",
        "descricao": _texto(meta.get("description"), 120),
        "fase": fase,
        "modelo": disco.modelo_curto(modelo_id),
        "modelo_id": modelo_id,
        "esforco": disco.esforco_valido(meta.get("effort")) or fim["esforco"],
        "estado": estado,
        "profundidade": _inteiro(meta.get("spawnDepth")) or 1,
        "pai_id": pais.get(cru["id"]),
        "iniciado_em": iniciado,
        "ultima_atividade": ultima,
        "duracao_s": int(max(0, t1 - t0)) if t0 else None,
        "ferramentas": n,
        "ultima_acao": fim["ultima_acao"],
    }


def _pais(escolhidos, crus):
    """pai_id: parentAgentId do meta; senão o agente cujo tool_use Agent/Task tem o toolUseId do meta."""
    ids = {c["id"] for c in crus}
    pais, faltam = {}, []
    for c in escolhidos:
        pai = c["meta"].get("parentAgentId")
        if isinstance(pai, str) and pai in ids and pai != c["id"]:
            pais[c["id"]] = pai
        elif (_inteiro(c["meta"].get("spawnDepth")) or 1) > 1 and isinstance(c["meta"].get("toolUseId"), str):
            faltam.append(c)
    if faltam:
        dono = {}
        for c in crus:
            for tid in disco.contar(c["caminho"], c["st"].st_size)[1]:
                dono[tid] = c["id"]
        for c in faltam:
            pai = dono.get(c["meta"]["toolUseId"])
            if pai and pai != c["id"]:
                pais[c["id"]] = pai
    return pais


def _grupos(agentes, crus_por_id, wfs):
    direto, por_wf = [], {}
    for a in agentes:
        wf = crus_por_id[a["id"]]["wf"]
        (por_wf.setdefault(wf, []) if wf else direto).append(a)
    chave = lambda a: a["iniciado_em"] or ""  # noqa: E731
    grupos = []
    if direto:
        grupos.append({"tipo": "direto", "id": "direto", "nome": "Sub-agentes diretos", "fases": [],
                       "agentes": sorted(direto, key=chave)})
    recente = lambda wf: max(crus_por_id[a["id"]]["st"].st_mtime for a in por_wf[wf])  # noqa: E731
    for wf in sorted(por_wf, key=recente, reverse=True):
        fases = list(wfs[wf]["jornal"]["fases"])
        for a in por_wf[wf]:
            if a["fase"] and a["fase"] not in fases:
                fases.append(a["fase"])
        grupos.append({"tipo": "workflow", "id": wf, "nome": wfs[wf]["nome"], "fases": fases,
                       "agentes": sorted(por_wf[wf], key=chave)})
    return grupos


def _sessao(linha, op, registro, agora, todos, avisos):
    sid = str(linha.get("sessionId") or "")
    if not RE_SESSAO.match(sid):
        return None
    sess_id = str(linha.get("id") or "")
    if not RE_ID_CURTO.match(sess_id):
        sess_id = sid[:8]
    interativa = str(linha.get("kind") or "").lower() != "background"
    conversa = _achar_conversa(op, sid, linha.get("cwd"))
    crus, wfs = ([], {})
    ultimo = None
    st_conv = None
    if conversa:
        try:
            st_conv = os.stat(conversa)
            ultimo = st_conv.st_mtime
        except OSError:
            st_conv = None
        crus, wfs = _agentes_crus(conversa[:-len(".jsonl")], op)
    for c in crus:
        ultimo = max(ultimo or 0, c["st"].st_mtime)
    reg = registro.get(sess_id) or {}
    estado = _estado_sessao(linha, reg, agora, None if ultimo is None else agora - ultimo, interativa)
    ativa = estado in ATIVOS
    estados = {c["id"]: _estado_agente(c, wfs, agora, ativa) for c in crus}
    ativos = sum(1 for e in estados.values() if e == "rodando")
    if todos:
        escolhidos = list(crus)
    else:
        escolhidos = [c for c in crus if estados[c["id"]] == "rodando" or agora - c["st"].st_mtime <= TTL_TERMINADOS]
    escolhidos.sort(key=lambda c: (estados[c["id"]] != "rodando", -c["st"].st_mtime))
    teto = MAX_TODOS if todos else MAX_AGENTES
    nome = _texto(linha.get("name"), 80) or _texto(reg.get("nome"), 80) or sess_id
    if len(escolhidos) > teto:
        avisos.append("Sessão %s: mostrando %d de %d sub-agentes." % (nome, teto, len(escolhidos)))
        escolhidos = escolhidos[:teto]
    pais = _pais(escolhidos, crus)
    agentes = [_agente(c, wfs, estados[c["id"]], agora, pais) for c in escolhidos]
    fim = disco.cauda(conversa, st_conv.st_size) if st_conv else {"modelo_id": None, "esforco": None}
    inicio = linha.get("startedAt")
    iniciado = disco.iso_local(inicio / 1000.0) if isinstance(inicio, (int, float)) and inicio > 0 else None
    if not iniciado and st_conv:
        iniciado = disco.primeiro_ts(conversa, st_conv)
    return {
        "id": sess_id,
        "sessao_id": sid,
        "nome": nome,
        "tipo": "interativa" if interativa else "segundo_plano",
        "estado": estado,
        "modelo": disco.modelo_curto(fim["modelo_id"]),
        "esforco": fim["esforco"],
        "iniciado_em": iniciado,
        "ultima_atividade": disco.iso_local(ultimo) if ultimo else None,
        "execucao_id": sess_id if (reg and not interativa) else None,
        "agentes_ativos": ativos,
        "agentes_total": len(crus),
        "grupos": _grupos(agentes, {c["id"]: c for c in crus}, wfs),
        "_ordem": (estado not in ATIVOS, -(ultimo or 0)),
    }


def _registro(op):
    if not _Registro or not op["dados_dir"]:
        return {}
    try:
        return {r["id"]: r for r in _Registro(op["dados_dir"]).ler()}
    except Exception:
        return {}


def _montar(op, sessao, todos, rodar, agora):
    avisos = []
    out = {"gerado_em": disco.iso_local(agora), "sessoes": [], "avisos": avisos}
    if sessao is not None and not (isinstance(sessao, str) and (RE_SESSAO.match(sessao) or RE_ID_CURTO.match(sessao))):
        avisos.append("Sessão inválida.")
        return out
    if not os.path.isdir(op["projects"]):
        avisos.append("Não achei a pasta de conversas do Claude (~/.claude/projects).")
    linhas = _listar_cli(op, rodar)
    if linhas is None:
        avisos.append("Não consegui listar as sessões do Claude (o comando 'claude agents' falhou).")
        return out
    registro = _registro(op)
    for linha in linhas:
        if not _no_projeto(linha.get("cwd"), op["raiz"]):
            continue
        if sessao and sessao not in (str(linha.get("id") or ""), str(linha.get("sessionId") or "")):
            continue
        try:
            s = _sessao(linha, op, registro, agora, todos, avisos)
        except Exception as e:  # uma sessão estranha não derruba a tela
            avisos.append("Não consegui ler uma sessão (%s)." % type(e).__name__)
            s = None
        if s:
            out["sessoes"].append(s)
    out["sessoes"].sort(key=lambda s: s.pop("_ordem"))
    if sessao and not out["sessoes"]:
        avisos.append("Não achei essa sessão neste projeto.")
    return out


def montar(cfg=None, sessao=None, todos=False, rodar=None, agora=None):
    """Formato "Agentes" do contrato. `rodar`/`agora` só para testes (desligam o cache)."""
    op = _opcoes(cfg)
    todos = bool(todos)
    usar_cache = rodar is None and agora is None
    chave = (op["raiz"], op["projects"], op["claude_bin"], sessao, todos)
    if usar_cache:
        with _trava:
            hit = _cache.get(chave)
            if hit and time.time() - hit[0] < CACHE_S:
                return hit[1]
    resultado = _montar(op, sessao, todos, rodar, time.time() if agora is None else agora)
    if usar_cache:
        with _trava:
            if len(_cache) > 50:
                _cache.clear()
            _cache[chave] = (time.time(), resultado)
    return resultado
