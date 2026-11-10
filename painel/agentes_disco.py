"""Leitura barata das conversas do Claude Code para a tela de Agentes.

Nunca lê um .jsonl inteiro a cada pedido:
- começo: só os primeiros 16 KB (hora da primeira linha), guardado por arquivo;
- fim: só os últimos 64 KB (até 512 KB se não achar resposta do modelo), guardado por (arquivo, tamanho);
- ferramentas: contadas aos pedaços, do ponto onde parou até o tamanho atual.
Só devolve nome de ferramenta e nome de arquivo; nunca texto de pedido ou de resposta.
Python 3.9, só biblioteca padrão.
"""
import datetime
import json
import os
import re
import threading

INICIO = 16 * 1024
CAUDA = 64 * 1024
CAUDA_MAX = 512 * 1024
PEDACO = 4 * 1024 * 1024
JSON_MAX = 256 * 1024
JOURNAL_MAX = 8 * 1024 * 1024
CACHE_MAX = 5000
ESFORCOS = ("low", "medium", "high", "xhigh", "max")
FERRAMENTAS_SUBAGENTE = ("Agent", "Task")
CHAVES_ARQUIVO = ("file_path", "notebook_path", "path")
RE_NOME_SIMPLES = re.compile(r"^[A-Za-z0-9_.:@+\-]{1,60}$")
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
RE_NOME_WF = re.compile(r"""\bname\s*:\s*['"]([^'"\n\r]{1,80})['"]""")
RE_FASE = re.compile(r"^[^\x00-\x1f\x7f]{1,80}$")

_trava = threading.Lock()
_inicio = {}    # (caminho, inode) -> iso | None
_cauda = {}     # (caminho, tamanho) -> dict
_contagem = {}  # caminho -> {"pos", "n", "spawns"}
_json = {}      # caminho -> ((mtime_ns, tamanho), dado)
_journal = {}   # caminho -> ((mtime_ns, tamanho), dado)


def _limitar(cache):
    if len(cache) > CACHE_MAX:
        cache.clear()


def esquecer_tudo():
    with _trava:
        for c in (_inicio, _cauda, _contagem, _json, _journal):
            c.clear()


def dentro(raiz_real, caminho):
    """True se o caminho real (symlinks resolvidos) fica dentro da raiz real."""
    try:
        real = os.path.realpath(caminho)
    except (OSError, ValueError):
        return False
    return real == raiz_real or real.startswith(raiz_real.rstrip(os.sep) + os.sep)


def iso_local(valor):
    """'2026-11-10T12:09:58.306Z' ou epoch -> ISO local com segundos; None se não der."""
    try:
        if isinstance(valor, (int, float)):
            dt = datetime.datetime.fromtimestamp(valor, datetime.timezone.utc).astimezone()
        else:
            texto = str(valor).strip().replace("Z", "+00:00")
            m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?([+-]\d\d:\d\d)?$", texto)
            if not m:
                return None
            dt = datetime.datetime.fromisoformat(m.group(1) + (m.group(3) or "+00:00")).astimezone()
        return dt.isoformat(timespec="seconds")
    except (ValueError, OverflowError, OSError):
        return None


def epoch_de(iso):
    try:
        return datetime.datetime.fromisoformat(iso).timestamp() if iso else None
    except (ValueError, TypeError):
        return None


def modelo_curto(modelo_id):
    """claude-opus-5-5 -> opus; claude-3-5-sonnet-2024 -> sonnet; opus -> opus. Sem lista de versões."""
    if not isinstance(modelo_id, str) or not modelo_id.strip():
        return None
    texto = modelo_id.strip().lower().split("[")[0]
    texto = texto.rsplit("/", 1)[-1].rsplit(".", 1)[-1] if "anthropic." in texto else texto
    for parte in re.split(r"[-_]", texto):
        if parte and parte != "claude" and parte.isalpha():
            return parte[:20]
    return None


def esforco_valido(valor):
    return valor if isinstance(valor, str) and valor in ESFORCOS else None


def _linhas(bloco, do_comeco):
    linhas = bloco.split(b"\n")
    if not do_comeco and linhas:
        linhas = linhas[1:]  # primeira linha do pedaço pode estar cortada
    return linhas


def _ler_bytes(caminho, de, ate):
    with open(caminho, "rb") as f:
        f.seek(de)
        return f.read(max(0, ate - de))


def primeiro_ts(caminho, st):
    """Hora (ISO local) da primeira linha que tem timestamp, lendo só o começo."""
    chave = (caminho, st.st_ino)
    with _trava:
        if chave in _inicio:
            return _inicio[chave]
    achado = None
    try:
        bloco = _ler_bytes(caminho, 0, min(st.st_size, INICIO))
    except OSError:
        bloco = b""
    for linha in _linhas(bloco, True)[:40]:
        m = re.search(rb'"timestamp"\s*:\s*"([0-9T:.\-+Z]{10,40})"', linha)
        if m:
            achado = iso_local(m.group(1).decode("ascii", "replace"))
            if achado:
                break
    if not achado:
        achado = iso_local(getattr(st, "st_birthtime", st.st_mtime))
    with _trava:
        _limitar(_inicio)
        _inicio[chave] = achado
    return achado


def _texto_limpo(valor, n=60):
    return RE_CONTROLE.sub("", str(valor or ""))[:n].strip()


def descrever_ferramenta(bloco):
    """'Edit painel.py', 'Bash', 'Agent Explore'. Só nome da ferramenta + nome de arquivo."""
    nome = _texto_limpo(bloco.get("name"), 60) or "?"
    entrada = bloco.get("input") if isinstance(bloco.get("input"), dict) else {}
    extra = ""
    for chave in CHAVES_ARQUIVO:
        v = entrada.get(chave)
        if isinstance(v, str) and v.strip():
            extra = os.path.basename(v.strip().rstrip("/\\")) or ""
            break
    if not extra and nome in FERRAMENTAS_SUBAGENTE:
        v = entrada.get("subagent_type")
        extra = v if isinstance(v, str) and RE_NOME_SIMPLES.match(v) else ""
    if not extra and nome == "Skill":
        v = entrada.get("skill")
        extra = v if isinstance(v, str) and RE_NOME_SIMPLES.match(v) else ""
    texto = (nome + " " + _texto_limpo(extra, 100)).strip()
    return texto[:120]


def _assistente(linha):
    """Linha do .jsonl -> dict se for resposta do modelo (type=assistant no topo), senão None."""
    if linha.startswith(b'{"type":"api-request') or b'"assistant"' not in linha:
        return None
    try:
        obj = json.loads(linha.decode("utf-8", "replace"))
    except ValueError:
        return None
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return None
    return obj


def cauda(caminho, tamanho):
    """{modelo_id, esforco, ultima_acao} lendo só o fim do arquivo."""
    chave = (caminho, tamanho)
    with _trava:
        if chave in _cauda:
            return _cauda[chave]
    out = {"modelo_id": None, "esforco": None, "ultima_acao": None}
    janela = CAUDA
    while True:
        de = max(0, tamanho - janela)
        try:
            bloco = _ler_bytes(caminho, de, tamanho)
        except OSError:
            break
        for linha in reversed(_linhas(bloco, de == 0)):
            obj = _assistente(linha)
            if obj is None:
                continue
            msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
            mod = msg.get("model")
            if out["modelo_id"] is None and isinstance(mod, str) and mod and not mod.startswith("<"):
                out["modelo_id"] = _texto_limpo(mod, 80)
            if out["esforco"] is None:
                out["esforco"] = esforco_valido(obj.get("effort")) or esforco_valido(obj.get("perTurnEffort"))
            if out["ultima_acao"] is None and isinstance(msg.get("content"), list):
                usos = [b for b in msg["content"] if isinstance(b, dict) and b.get("type") == "tool_use"]
                if usos:
                    out["ultima_acao"] = descrever_ferramenta(usos[-1])
            if out["modelo_id"] and out["esforco"] and out["ultima_acao"]:
                break
        if out["modelo_id"] or de == 0 or janela >= CAUDA_MAX:
            break
        janela = CAUDA_MAX
    with _trava:
        _limitar(_cauda)
        for k in [k for k in _cauda if k[0] == caminho]:
            del _cauda[k]
        _cauda[chave] = out
    return out


def contar(caminho, tamanho):
    """(ferramentas usadas, ids dos tool_use que criaram sub-agentes). Lê só o que entrou depois."""
    with _trava:
        est = dict(_contagem.get(caminho) or {"pos": 0, "n": 0, "spawns": ()})
    if tamanho < est["pos"]:  # arquivo trocado ou encolheu
        est = {"pos": 0, "n": 0, "spawns": ()}
    spawns = list(est["spawns"])
    pos, n = est["pos"], est["n"]
    try:
        with open(caminho, "rb") as f:
            while pos < tamanho:
                f.seek(pos)
                bloco = f.read(min(PEDACO, tamanho - pos))
                fim = bloco.rfind(b"\n")
                if fim < 0:
                    if len(bloco) >= PEDACO:  # linha gigante sem fim: pula
                        pos += len(bloco)
                        continue
                    break
                for linha in bloco[:fim].split(b"\n"):
                    if b'"tool_use"' not in linha:
                        continue
                    obj = _assistente(linha)
                    if obj is None:
                        continue
                    msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
                    for b in msg.get("content") if isinstance(msg.get("content"), list) else []:
                        if isinstance(b, dict) and b.get("type") == "tool_use":
                            n += 1
                            if b.get("name") in FERRAMENTAS_SUBAGENTE and isinstance(b.get("id"), str):
                                spawns.append(b["id"][:80])
                pos += fim + 1
    except OSError:
        pass
    with _trava:
        _limitar(_contagem)
        _contagem[caminho] = {"pos": pos, "n": n, "spawns": tuple(spawns[-500:])}
    return n, spawns


def ler_json(caminho, st, limite=JSON_MAX):
    """JSON pequeno (meta) com cache por (mtime, tamanho). None se ilegível."""
    marca = (st.st_mtime_ns, st.st_size)
    with _trava:
        hit = _json.get(caminho)
        if hit and hit[0] == marca:
            return hit[1]
    dado = None
    if st.st_size <= limite:
        try:
            with open(caminho, "rb") as f:
                dado = json.loads(f.read(limite + 1).decode("utf-8"))
        except (OSError, ValueError, UnicodeDecodeError):
            dado = None
    if not isinstance(dado, dict):
        dado = None
    with _trava:
        _limitar(_json)
        _json[caminho] = (marca, dado)
    return dado


def ler_journal(caminho, st):
    """journal.jsonl do workflow -> {"fases": [...em ordem], "fase_de": {id: fase}, "terminados": set}."""
    marca = (st.st_mtime_ns, st.st_size)
    with _trava:
        hit = _journal.get(caminho)
        if hit and hit[0] == marca:
            return hit[1]
    fases, fase_de, terminados = [], {}, set()
    try:
        bloco = _ler_bytes(caminho, max(0, st.st_size - JOURNAL_MAX), st.st_size)
    except OSError:
        bloco = b""
    for linha in bloco.split(b"\n"):
        if b'"agentId"' not in linha:
            continue
        try:
            obj = json.loads(linha.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(obj, dict) or not isinstance(obj.get("agentId"), str):
            continue
        aid = obj["agentId"][:64]
        if obj.get("type") == "result":
            terminados.add(aid)
        elif obj.get("type") == "started":
            fase = obj.get("phase")
            if isinstance(fase, str) and RE_FASE.match(fase):
                fase_de[aid] = fase
                if fase not in fases:
                    fases.append(fase)
    dado = {"fases": fases, "fase_de": fase_de, "terminados": terminados}
    with _trava:
        _limitar(_journal)
        _journal[caminho] = (marca, dado)
    return dado


def nome_workflow(pasta_scripts, wf_id, raiz_real):
    """meta.name do script <pasta>/*<wf_id>.js por regex simples; None se não achar."""
    try:
        nomes = [e for e in os.scandir(pasta_scripts)
                 if e.name.endswith(wf_id + ".js") and e.is_file(follow_symlinks=False)]
    except OSError:
        return None
    for e in nomes:
        if not dentro(raiz_real, e.path):
            continue
        try:
            with open(e.path, "rb") as f:
                cabeca = f.read(4096).decode("utf-8", "replace")
        except OSError:
            continue
        m = RE_NOME_WF.search(cabeca)
        if m:
            return _texto_limpo(m.group(1), 80)
    return None
