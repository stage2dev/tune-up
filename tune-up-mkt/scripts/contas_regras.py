"""Rules of contas.py: classify command outputs, merge session marks, refuse secret-looking values.

Pure functions, stdlib only. A `detalhe` is always one of the fixed strings below (or an mcp state
phrase), never text taken from a command output.
"""
import json
import re
from urllib.parse import urlsplit
from datetime import datetime, timedelta, timezone

PIOR_PRIMEIRO = ("nao_instalado", "desligado", "falhou", "falta_autenticar", "nao_sei", "ligado")
AUTOMATICOS = ("plugin", "mcp", "cli")
ESTADOS_MARCA = ("ligado", "falta_autenticar", "nao_instalado")
PROVAS = ("whoami_ok", "connections_ok", "manual")
VIAS_MARCA = ("cli", "mcp", "manual")
VIA_DA_PROVA = {"whoami_ok": "mcp", "connections_ok": "cli", "manual": "manual"}
CONTAS = ("conferida", "confirmada_pelo_dono", "conferir_de_novo", "nao_conferida", "nao_se_aplica")
CANAIS = ("metaads", "googleads", "instagram", "facebook", "seo", "video", "voz")  # config --canais ids
PREFIXOS_SEGREDO = ("sk-", "oseo_", "ghp_", "gho_", "akia", "xox", "ya29.", "eyj")  # compared lower-case
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
_RX_SEGREDO = re.compile(r"(?:^|[^A-Za-z0-9])(?:oseo_|sk-)|Bearer\s|[A-Za-z0-9+=]{32,}")
_RX_EMAIL = re.compile(r"[^\s@:/]+@[^\s@/]+\.[A-Za-z]{2,}")
_RX_INDEXNOW = re.compile(r"^[A-Za-z0-9-]{8,128}$")
_RX_HOST = re.compile(r"^[A-Za-z0-9.-]+$")
_RX_SEGMENTO = re.compile(r"^[A-Za-z0-9._~%-]{0,39}$")


def pior(estados):
    """Worst state of the list (order PIOR_PRIMEIRO); an unknown state counts as nao_sei."""
    idx = [PIOR_PRIMEIRO.index(e) if e in PIOR_PRIMEIRO else PIOR_PRIMEIRO.index("nao_sei") for e in estados]
    return PIOR_PRIMEIRO[min(idx)] if idx else "nao_sei"


def melhor(estados):
    """Best state of the list (ligado first); an unknown state counts as nao_sei."""
    idx = [PIOR_PRIMEIRO.index(e) if e in PIOR_PRIMEIRO else PIOR_PRIMEIRO.index("nao_sei") for e in estados]
    return PIOR_PRIMEIRO[max(idx)] if idx else "nao_sei"


def _pior_par(pares):
    estado = pior([e for e, _ in pares])
    return next(p for p in pares if p[0] == estado)


def classificar_plugin(saida, alvo):
    """`claude plugin list --json`: (estado, detalhe) of the plugins whose id is exactly one of alvo."""
    alvos = {alvo} if isinstance(alvo, str) else set(alvo)
    try:
        dados = json.loads(saida)
    except ValueError:
        return "nao_sei", D_FORMATO
    if not isinstance(dados, list) or not all(isinstance(p, dict) and isinstance(p.get("id"), str) for p in dados):
        return "nao_sei", D_FORMATO
    achados = [p for p in dados if p["id"] in alvos]
    if not achados:
        return "nao_instalado", D_FORA_DA_LISTA
    return _pior_par([("ligado", D_HABILITADO) if p.get("enabled") is True else
                      ("desligado", D_DESABILITADO) if p.get("enabled") is False else
                      ("nao_sei", D_FORMATO) for p in achados])


def _tokens(texto):
    return [t for t in re.split(r"[^a-z0-9]+", texto.lower()) if t]


def _casa_nome(nome, alvo):
    """alvo's tokens appear in a row among the tokens of the server name (whole words, any case)."""
    n, a = _tokens(nome), _tokens(alvo)
    return bool(a) and any(n[i:i + len(a)] == a for i in range(len(n) - len(a) + 1))


def _host(resto):
    palavra = resto.split()[0] if resto.split() else ""
    try:
        return (urlsplit(palavra).hostname or "") if palavra.lower().startswith(("http://", "https://")) else ""
    except ValueError:
        return ""


def classificar_mcp(saida, alvo, host=None):
    """`claude mcp list`: (estado, detalhe) of the server lines whose NAME (text before the first ': ') holds
    alvo as whole words, or whose URL host is exactly `host`. The URL path never counts.

    Several matching lines: the worst one. No matching line: nao_instalado, unless no line looks like a
    server line at all (unknown format) -> nao_sei. The state is read from the last ` - <state>` of the line.
    """
    por_frase = dict(ESTADOS_MCP)
    reconhecidas, achados = 0, []
    for linha in saida.splitlines():
        linha = linha.strip()
        servidor = bool(_RX_LINHA_MCP.match(linha))
        reconhecidas += servidor
        ms = list(_RX_ESTADO_MCP.finditer(linha))
        m = ms[-1] if ms else None
        nome, _, resto = linha.partition(": ")
        resto = resto[:m.start() - len(nome) - 2] if m and resto else resto
        if linha and (_casa_nome(nome, alvo) or (host and servidor and _host(resto) == host.lower())):
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


def classificar(tipo, saida, alvo, toolkit=None, host=None):
    if tipo == "plugin":
        return classificar_plugin(saida, alvo)
    if tipo == "mcp":
        return classificar_mcp(saida, alvo, host)
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
            or m.get("via") != VIA_DA_PROVA[m["prova"]] or ler_iso(m.get("conferido_em")) is None:
        return None
    return {k: m[k] for k in ("estado", "prova", "via", "conferido_em")}


def limpar_checagem(c):
    if not isinstance(c, dict) or c.get("tipo") not in AUTOMATICOS or c.get("via") != c.get("tipo") \
            or c.get("estado") not in PIOR_PRIMEIRO or c.get("detalhe") not in DETALHES \
            or ler_iso(c.get("conferido_em")) is None:
        return None
    return {k: c[k] for k in ("tipo", "via", "estado", "detalhe", "conferido_em")}


def juntar(marcas, novas):
    """Marks of both, per key the newest conferido_em wins (a tie goes to `novas`)."""
    junto = dict(marcas)
    for k, m in novas.items():
        if k not in junto or ler_iso(m["conferido_em"]) >= ler_iso(junto[k]["conferido_em"]):
            junto[k] = m
    return junto


def conta_de(conferir, marca, agora):
    """Whether the ACCOUNT was checked by the session or confirmed by the owner (separate from `estado`)."""
    if all(c["tipo"] in AUTOMATICOS for c in conferir):
        return "nao_se_aplica"
    if not marca:
        return "nao_conferida"
    if not marca_valida(marca, agora):
        return "conferir_de_novo"
    return "confirmada_pelo_dono" if marca["prova"] == "manual" else "conferida"


def _item(conferir, auto, marca, agora, modo="todas"):
    """estado: from the deciding automatic checks (`papel` decide; `modo` todas = worst, qualquer = best);
    a valid mark below ligado still lowers it. Only manual/tool checks: from the mark. Never raised by a mark."""
    regras = [c for c in conferir if c["tipo"] in AUTOMATICOS]
    checagens = [dict(r, papel=c.get("papel", "decide")) for c, r in zip(regras, auto)]
    decide = [r["estado"] for c, r in zip(regras, auto) if c.get("papel", "decide") == "decide"]
    if any(c.get("papel", "decide") == "decide" for c in regras) and len(auto) != len(regras):
        decide = ["nao_sei"]
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
    if decide:  # a valid mark never upgrades what the automatic checks say
        estado = melhor(decide) if modo == "qualquer" else pior(decide)
        estado = pior([estado] + ([estado_marca] if estado_marca in ESTADOS_MARCA else []))
    else:
        estado = estado_marca or "nao_sei"
    item = {"estado": estado, "conta": conta_de(conferir, marca, agora), "checagens": checagens}
    if marca:
        item["marca"] = dict(marca)
    return item


def montar(catalogo, auto, marcas, agora):
    """contas.json content. auto: key -> automatic check results; marcas: key -> mark (key = id or id:canal)."""
    servicos = {}
    for s in catalogo["servicos"]:
        item = _item(s["conferir"], auto.get(s["id"], []), marcas.get(s["id"]), agora, s.get("modo", "todas"))
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
    """8-128 chars of a-z A-Z 0-9 - and not starting like another provider's secret."""
    return bool(_RX_INDEXNOW.match(valor)) and not valor.lower().startswith(PREFIXOS_SEGREDO)


def site_valido(url):
    """Only http(s)://host[:port][/plain/path]: no user info, query or fragment; short plain path segments."""
    if not isinstance(url, str) or any(c in url for c in "?#@ \\"):
        return False
    try:
        u = urlsplit(url)
        u.port  # noqa: B018  (raises ValueError on a bad port)
    except ValueError:
        return False
    return (u.scheme in ("http", "https") and bool(u.hostname) and bool(_RX_HOST.match(u.hostname))
            and all(_RX_SEGMENTO.match(p) for p in u.path.split("/")))


def canais_validos(lista):
    return all(c in CANAIS for c in lista)


def limpar_config(d):
    """config.json reduced to the known keys with valid values; anything else is dropped."""
    d = d if isinstance(d, dict) else {}
    novo = {}
    if site_valido(d.get("site")):
        novo["site"] = d["site"]
    if isinstance(d.get("canais"), list) and all(isinstance(c, str) for c in d["canais"]) \
            and canais_validos(d["canais"]):
        novo["canais"] = list(d["canais"])
    if isinstance(d.get("indexnow_key"), str) and indexnow_valida(d["indexnow_key"]):
        novo["indexnow_key"] = d["indexnow_key"]
    c = d.get("credit_ask_above")
    if isinstance(c, int) and not isinstance(c, bool) and c >= 0:
        novo["credit_ask_above"] = c
    return novo
