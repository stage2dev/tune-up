"""Rules of contas.py: classify command outputs, merge session marks, refuse secret-looking values.

Pure functions, stdlib only. A `detalhe` is always one of the fixed strings below (or an mcp state
phrase), never text taken from a command output.
"""
import json
import re
from datetime import datetime, timedelta, timezone

PIOR_PRIMEIRO = ("nao_instalado", "desligado", "falhou", "falta_autenticar", "nao_sei", "ligado")
AUTOMATICOS = ("plugin", "mcp", "cli")
ESTADOS_MARCA = ("ligado", "falta_autenticar", "nao_instalado")
PROVAS = ("whoami_ok", "connections_ok", "manual")
VIAS_MARCA = ("cli", "mcp", "manual")
VALIDADE = timedelta(days=7)
FOLGA_FUTURO = timedelta(minutes=5)

# The six states `claude mcp list` can print, keyed by their words (the mark character is not trusted).
# Doc: https://code.claude.com/docs/en/mcp ("Not configured" was observed for real but is not in the doc).
ESTADOS_MCP = (
    ("Connected", "ligado"),
    ("Needs authentication", "falta_autenticar"),
    ("Not configured", "falta_autenticar"),
    ("Failed to connect", "falhou"),
    ("Pending approval", "desligado"),
    ("Disabled", "desligado"),
)

D_HABILITADO = "enabled"
D_DESABILITADO = "disabled"
D_FORA_DA_LISTA = "not in list"
D_FORMATO = "unknown format"
D_SEM_SERVIDOR = "no matching server"
D_ATIVA = "ACTIVE"
D_INATIVA = "only inactive"
D_SEM_LINK = "not linked"
D_SEM_COMANDO = "command not found"
D_TEMPO = "timeout"
D_SAIDA = "exit not zero"
D_NAO_RODOU = "could not run"
D_MARCADA = "marked"
D_VENCIDA = "mark expired"
D_SO_SESSAO = "needs the session"
D_NAO_CONFERIDO = "not checked"
DETALHES = {D_HABILITADO, D_DESABILITADO, D_FORA_DA_LISTA, D_FORMATO, D_SEM_SERVIDOR, D_ATIVA, D_INATIVA,
            D_SEM_LINK, D_SEM_COMANDO, D_TEMPO, D_SAIDA, D_NAO_RODOU, D_MARCADA, D_VENCIDA, D_SO_SESSAO,
            D_NAO_CONFERIDO} | {p for p, _ in ESTADOS_MCP}

_RX_ESTADO_MCP = re.compile(r"\s-\s+(?:\S+\s+)?(" + "|".join(re.escape(p) for p, _ in ESTADOS_MCP) + ")")
_RX_LINHA_MCP = re.compile(r"^\S.*?: .* - \S.*$")  # `name: url-or-command - <mark> <state>`
_RX_SEGREDO = re.compile(r"(?:^|[^A-Za-z0-9])(?:oseo_|sk-)|Bearer\s|[A-Za-z0-9+/=]{32,}")
_RX_EMAIL = re.compile(r"[^\s@:/]+@[^\s@/]+\.[A-Za-z]{2,}")
_RX_INDEXNOW = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def pior(estados):
    """Worst state of the list (order PIOR_PRIMEIRO); an unknown state counts as nao_sei."""
    idx = [PIOR_PRIMEIRO.index(e) if e in PIOR_PRIMEIRO else PIOR_PRIMEIRO.index("nao_sei") for e in estados]
    return PIOR_PRIMEIRO[min(idx)] if idx else "nao_sei"


def _pior_par(pares):
    estado = pior([e for e, _ in pares])
    return next(p for p in pares if p[0] == estado)


def classificar_plugin(saida, alvo):
    """`claude plugin list --json`: (estado, detalhe) of the plugins whose id starts with alvo."""
    try:
        dados = json.loads(saida)
    except ValueError:
        return "nao_sei", D_FORMATO
    if not isinstance(dados, list) or not all(isinstance(p, dict) and isinstance(p.get("id"), str) for p in dados):
        return "nao_sei", D_FORMATO
    achados = [p for p in dados if p["id"].startswith(alvo)]
    if not achados:
        return "nao_instalado", D_FORA_DA_LISTA
    return _pior_par([("ligado", D_HABILITADO) if p.get("enabled") is True else
                      ("desligado", D_DESABILITADO) if p.get("enabled") is False else
                      ("nao_sei", D_FORMATO) for p in achados])


def classificar_mcp(saida, alvo):
    """`claude mcp list`: (estado, detalhe) of the server lines whose name/URL contains alvo (any case).

    Several matching lines: the worst one. No matching line: nao_instalado, unless no line looks like a
    server line at all (unknown format) -> nao_sei.
    """
    alvo = alvo.lower()
    por_frase = dict(ESTADOS_MCP)
    reconhecidas, achados = 0, []
    for linha in saida.splitlines():
        linha = linha.strip()
        servidor = bool(_RX_LINHA_MCP.match(linha))
        reconhecidas += servidor
        m = _RX_ESTADO_MCP.search(linha)
        nome = linha[:m.start()] if m else linha
        if linha and alvo in nome.lower():
            achados.append((por_frase[m.group(1)], m.group(1)) if m and servidor else ("nao_sei", D_FORMATO))
    if achados:
        return _pior_par(achados)
    return ("nao_instalado", D_SEM_SERVIDOR) if reconhecidas else ("nao_sei", D_FORMATO)


def classificar_composio(saida, toolkit=None):
    """`composio connections list`: JSON object keyed by toolkit, each a list of {status}. No toolkit: all."""
    try:
        dados = json.loads(saida)
    except ValueError:
        return "nao_sei", D_FORMATO
    if not isinstance(dados, dict) or not all(
            isinstance(v, list) and all(isinstance(c, dict) and isinstance(c.get("status"), str) for c in v)
            for v in dados.values()):
        return "nao_sei", D_FORMATO
    conexoes = dados.get(toolkit, []) if toolkit else [c for v in dados.values() for c in v]
    if not conexoes:
        return "falta_autenticar", D_SEM_LINK
    if any(c["status"].strip().upper() == "ACTIVE" for c in conexoes):
        return "ligado", D_ATIVA
    return "falta_autenticar", D_INATIVA


def classificar(tipo, saida, alvo, toolkit=None):
    if tipo == "plugin":
        return classificar_plugin(saida, alvo)
    if tipo == "mcp":
        return classificar_mcp(saida, alvo)
    return classificar_composio(saida, toolkit)


def iso(momento):
    return momento.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def ler_iso(texto):
    """Aware datetime or None."""
    if not isinstance(texto, str):
        return None
    try:
        t = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t if t.tzinfo else None


def marca_valida(marca, agora):
    """A mark lasts 7 days from conferido_em; a date in the future (beyond a small skew) is not trusted."""
    t = ler_iso(marca.get("conferido_em"))
    return t is not None and agora - VALIDADE <= t <= agora + FOLGA_FUTURO


def limpar_marca(m):
    """The stored mark rebuilt from the allowed fields only, or None when anything is off."""
    if not isinstance(m, dict) or m.get("estado") not in ESTADOS_MARCA or m.get("prova") not in PROVAS \
            or m.get("via") not in VIAS_MARCA or ler_iso(m.get("conferido_em")) is None:
        return None
    return {k: m[k] for k in ("estado", "prova", "via", "conferido_em")}


def limpar_checagem(c):
    if not isinstance(c, dict) or c.get("tipo") not in AUTOMATICOS or c.get("via") != c.get("tipo") \
            or c.get("estado") not in PIOR_PRIMEIRO or c.get("detalhe") not in DETALHES \
            or ler_iso(c.get("conferido_em")) is None:
        return None
    return {k: c[k] for k in ("tipo", "via", "estado", "detalhe", "conferido_em")}


def _item(conferir, auto, marca, agora):
    checagens = list(auto)
    estado_marca = None
    if marca:
        estado_marca = marca["estado"] if marca_valida(marca, agora) else "conferir_de_novo"
    for c in conferir:
        if c["tipo"] in AUTOMATICOS:
            continue
        if marca:
            checagens.append({"tipo": c["tipo"], "via": marca["via"], "estado": estado_marca,
                              "detalhe": D_MARCADA if estado_marca != "conferir_de_novo" else D_VENCIDA,
                              "conferido_em": marca["conferido_em"]})
        else:
            checagens.append({"tipo": c["tipo"], "via": "manual", "estado": "nao_sei", "detalhe": D_SO_SESSAO,
                              "conferido_em": iso(agora)})
    if auto:  # a valid mark never upgrades what the automatic checks say
        estado = pior([c["estado"] for c in auto] + ([estado_marca] if estado_marca in ESTADOS_MARCA else []))
    else:
        estado = estado_marca or "nao_sei"
    item = {"estado": estado, "checagens": checagens}
    if marca:
        item["marca"] = dict(marca)
    return item


def montar(catalogo, auto, marcas, agora):
    """contas.json content. auto: key -> automatic check results; marcas: key -> mark (key = id or id:canal)."""
    servicos = {}
    for s in catalogo["servicos"]:
        item = _item(s["conferir"], auto.get(s["id"], []), marcas.get(s["id"]), agora)
        tipos = {c["tipo"] for c in item["checagens"]}
        if {"cli", "mcp"} <= tipos:
            for t in ("cli", "mcp"):
                item[t] = pior([c["estado"] for c in item["checagens"] if c["tipo"] == t])
        if s.get("canais"):
            item["canais"] = {}
            for c in s["canais"]:
                chave = s["id"] + ":" + c["id"]
                item["canais"][c["id"]] = _item(c["conferir"], auto.get(chave, []), marcas.get(chave), agora)
        servicos[s["id"]] = item
    return {"versao": 1, "conferido_em": iso(agora), "servicos": servicos}


def chaves(catalogo):
    """Every key `marcar` accepts: service ids and <service>:<channel>."""
    for s in catalogo["servicos"]:
        yield s["id"], s["conferir"]
        for c in s.get("canais", []):
            yield s["id"] + ":" + c["id"], c["conferir"]


def parece_segredo(valor):
    return bool(_RX_SEGREDO.search(valor))


def tem_email(valor):
    return bool(_RX_EMAIL.search(valor))


def indexnow_valida(valor):
    return bool(_RX_INDEXNOW.match(valor))
