#!/usr/bin/env python3
"""tune-up-mkt: guard for writes to ad accounts and public posts (PreToolUse).

Usage: sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda_mkt.py   (see hooks/hooks.json)
Reads the hook JSON on stdin; writes JSON only when there is a decision. Always exit 0.
Internal exception = no decision; one line in <data>/erros.log.
Per-project loosening: ~/.config/tune-up/mkt.json (TUNEUP_MKT_JSON), keyed by CLAUDE_PROJECT_DIR.
Messages: `language` and `owner` from ~/.config/tune-up/user.json (TUNEUP_USER_JSON).
"""
import json
import os
import re
import sys
import time

TESTE = os.environ.get("TUNEUP_TESTE") == "1"

# Factory policy; mkt.json may only set "deny" or "ask" per key (never pass).
PADRAO = {"meta_ads_write": "deny", "google_ads_write": "ask", "organic_publish": "ask"}
META = ("meta_ads_write", "meta")
ORGANICO = ("organic_publish", "organico")
GOOGLE = ("google_ads_write", "google")
RUN = (None, "run")            # None = fixed "ask", not configurable
MKT_JSON = (None, "mkt_json")

MENSAGENS = {
    "en": {
        "meta": ("Meta ad objects: writes through the API are blocked. Make the change in Ads Manager "
                 "in the browser, on {dono}'s explicit request."),
        "organico": "public post: only on {dono}'s order.",
        "google": "Google Ads change: confirm first (without {dono}'s order, read only).",
        "run": "`composio run` executes a file this guard cannot read: confirm first.",
        "mkt_json": "mkt.json loosens the marketing guard: confirm this change.",
        "afrouxado": " The default is to block; loosened to ask by {arq}.",
    },
    "pt-BR": {
        "meta": ("objetos de anúncio da Meta: escrita pela API está bloqueada. Faça a mudança no "
                 "Gerenciador de Anúncios, no navegador, com pedido explícito {dono}."),
        "organico": "publicação pública: só com ordem {dono}.",
        "google": "mudança no Google Ads: confirme antes (sem ordem {dono}, só leitura).",
        "run": "`composio run` executa um arquivo que esta guarda não lê: confirme antes.",
        "mkt_json": "o mkt.json afrouxa a guarda de marketing: confirme esta mudança.",
        "afrouxado": " O padrão é bloquear; afrouxado para perguntar por {arq}.",
    },
}

SHELLS = {"Bash", "PowerShell", "Monitor"}
ESCRITAS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
CHAVES_CAMINHO = ("file_path", "notebook_path", "path")
RE_FILTRO_MCP = re.compile(r"(?i)composio|meta|facebook|instagram|google_?ads|graph\.(?:facebook|instagram)")
RE_MKT_JSON = re.compile(r"(?i)(?<![\w.-])mkt\.json(?!\w)")

RE_SLUG = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{6,}")
PLATAFORMA_META = re.compile(r"^(META|FACEBOOK|FB|INSTAGRAM)")
TERMO_AD = re.compile(r"^(ADS?|ADSETS?|CAMPAIGNS?|AUDIENCES?|BUDGETS?|CREATIVES?|BIDS?|BIDDING)$")
VERBO_ESCRITA = re.compile(r"^(CREATE|UPDATE|DELETE|PAUSE|ACTIVATE|EDIT|SET|DUPLICATE|ARCHIVE|UPLOAD|PUBLISH)S?$")
VERBO_LEITURA = {"GET", "LIST", "FETCH", "SEARCH", "INSIGHTS", "REPORT", "READ", "FIND", "RETRIEVE"}
VERBO_ORGANICO = {"CREATE", "PUBLISH", "POST", "UPLOAD", "SEND", "COMMENT", "REPLY", "DELETE", "UPDATE", "SCHEDULE"}
RE_GOOGLE = re.compile(r"GOOGLE_?ADS[A-Z_]*(MUTATE|CREATE|UPDATE|REMOVE|PAUSE|ENABLE|SET)")
RE_METODO = re.compile(r"(?i)(\"?method\"?\s*[:=]\s*\"?|-X\s*|--method[ =]|--request[ =])(POST|DELETE|PUT|PATCH)\b")
RE_GRAPH_URL = re.compile(r"(?i)graph\.(?:facebook|instagram)\.com/[^\s\"'\\]*")
RE_GRAPH_AD = re.compile(r"(?i)/(act_[^/?\s]*|campaigns|adsets|ads|adcreatives)(?=[/?#]|$)")
RE_DADOS = re.compile(r"(?:^|[\s\"'])(?:-d|-F|--data[\w-]*|--form)(?=[\s=\"']|\S)")
RE_GET = re.compile(r"(?i)(-X\s*|--request[ =]|--method[ =])GET\b")
RE_CURL_G = re.compile(r"(?:^|[\s\"'])(?:-G|--get)(?=[\s\"']|$)")  # -d becomes a GET query; no (?i): -g is --globoff
RE_REMOTO = re.compile(r"(?i)COMPOSIO_REMOTE_(WORKBENCH|BASH_TOOL)$")
RE_CITA_META = re.compile(r"(?i)\bmeta\b|\bmetaads\b|facebook|instagram|graph\.")
RE_EXECUTE = re.compile(r"(?i)(?:^|[\s/;&|(])(?:composio|@composio/cli)(?:@\S*)?\s+execute\s+['\"]?([A-Za-z0-9_]+)")
RE_EXECUTE_INICIO = re.compile(r"(?i)(?:^|[\s/;&|(])(?:composio|@composio/cli)(?:@\S*)?\s.*?\bexecute\b", re.S)
RE_RUN = re.compile(r"(?i)\bcomposio\s+run\b")
RE_TOKEN_SLUG = re.compile(r"^[A-Za-z]+(_[A-Za-z0-9]+)+$")
CHAVES_SLUG = {"tool_slug", "slug", "action", "tool"}
RE_BASH_ALVO = re.compile(r"(?i)composio|graph\.facebook\.com|graph\.instagram\.com")
RE_HEREDOC = re.compile(r"<<(?!<)-?\s*['\"]?(\w+)['\"]?")


def log_erro(texto):
    try:
        d = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(os.path.expanduser("~"), ".cache", "tune-up-mkt")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "erros.log"), "a", encoding="utf-8") as f:
            f.write(("%s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), texto)).replace("\n", " ")[:2000] + "\n")
    except Exception:
        pass


def ler_json(caminho):
    """Parsed JSON or None (missing/unreadable file = None; invalid JSON = None + log line)."""
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except OSError:
        return None
    except ValueError:
        log_erro("invalid JSON in %s" % caminho)
        return None


def caminho_mkt_json():
    return os.environ.get("TUNEUP_MKT_JSON") or os.path.join(
        os.path.expanduser("~"), ".config", "tune-up", "mkt.json")


def normalizar(p):
    """Comparable form of a path; None when the path is unusable (a bad key never disables the guard)."""
    try:
        p = os.path.normcase(os.path.realpath(os.path.expanduser(p.strip())))
    except (OSError, ValueError):
        return None
    return p.rstrip("/\\") or p


def politica():
    """(action per key, file that set it or None). Project = CLAUDE_PROJECT_DIR only, never the hook cwd."""
    out = dict(PADRAO)
    raiz = os.environ.get("CLAUDE_PROJECT_DIR") or ""
    if not raiz.strip():
        return out, None
    arq = caminho_mkt_json()
    d = ler_json(arq)
    projetos = d.get("projetos") if isinstance(d, dict) else None
    if not isinstance(projetos, dict):
        return out, None
    alvo = normalizar(raiz)
    if alvo is None:
        return out, None
    regras = next((v for k, v in projetos.items() if isinstance(k, str) and k.strip() and normalizar(k) == alvo), None)
    if not isinstance(regras, dict):
        return out, None
    for k in PADRAO:
        if regras.get(k) in ("deny", "ask"):
            out[k] = regras[k]
    return out, arq


def nome_simples(v):
    return isinstance(v, str) and 0 < len(v.strip()) and len(v) <= 80 and not any(
        x in v for x in ("/", "\\", "..", "\n", "\r"))


def perfil():
    """(language, owner phrase) from user.json; any other language or bad file -> English, 'the owner'."""
    d = ler_json(os.environ.get("TUNEUP_USER_JSON") or os.path.join(
        os.path.expanduser("~"), ".config", "tune-up", "user.json"))
    d = d if isinstance(d, dict) else {}
    lang = d.get("language")
    idioma = "pt-BR" if isinstance(lang, str) and lang.strip().lower() == "pt-br" else "en"
    dono = d.get("owner").strip() if nome_simples(d.get("owner")) else None
    if idioma == "pt-BR":
        return idioma, ("de " + dono) if dono else "do dono"
    return idioma, dono or "the owner"


def sem_heredoc(cmd):
    saida, pendentes = [], []
    for linha in cmd.split("\n"):
        if pendentes:
            if linha.strip() == pendentes[0]:
                pendentes.pop(0)
            continue
        saida.append(linha)
        pendentes.extend(RE_HEREDOC.findall(linha))
    return "\n".join(saida)


def slugs_execute(cmd):
    """Every slug-looking token after `composio ... execute` (a flag before the slug does not hide it)."""
    m = RE_EXECUTE_INICIO.search(cmd)
    if not m:
        return []
    return [t for t in (x.strip("'\"") for x in cmd[m.end():].split()) if RE_TOKEN_SLUG.match(t)]


def partes_do_slug(slug):
    """Split on `_` and join AD+SET(S) into ADSET(S) so SET is not read as a verb."""
    brutas = slug.split("_")
    out, i = [], 0
    while i < len(brutas):
        p = brutas[i]
        if p == "AD" and i + 1 < len(brutas) and brutas[i + 1] in ("SET", "SETS"):
            out.append("AD" + brutas[i + 1])
            i += 2
            continue
        out.append(p)
        i += 1
    return out


def tem_termo_ad(partes):
    if any(TERMO_AD.match(p) for p in partes[1:]):
        return True
    primeira = partes[0]
    return bool(re.match(r"^(META|FACEBOOK|FB|INSTAGRAM)ADS?$", primeira))


def graph_escrita(texto):
    """Graph API with a write method: ad object = META, other path = ORGANICO."""
    if not re.search(r"(?i)graph\.(facebook|instagram)\.com", texto):
        return None
    escrita = RE_METODO.search(texto) or (RE_DADOS.search(texto) and not RE_GET.search(texto)
                                          and not RE_CURL_G.search(texto))
    if not escrita:
        return None
    if any(RE_GRAPH_AD.search(u) for u in RE_GRAPH_URL.findall(texto)):
        return META
    return ORGANICO


def classificar(texto, slugs):
    """`texto`: proxy rule; `slugs`: only where a slug is a tool name. Returns the list of hits (META/ORGANICO/GOOGLE)."""
    if re.search(r"(?i)proxy", texto) and "graph.facebook.com" in texto and RE_METODO.search(texto):
        return [META]
    achados = []
    for slug in set(RE_SLUG.findall(slugs.upper())):
        partes = partes_do_slug(slug)
        leitura = any(p in VERBO_LEITURA for p in partes)
        if PLATAFORMA_META.match(slug):
            if tem_termo_ad(partes):
                # allowlist: an ad object only passes with a read verb; a bare toolkit name (METAADS, META_ADS) passes
                if not leitura and any(not TERMO_AD.match(p) for p in partes[1:]):
                    achados.append(META)
                continue
            if slug.startswith(("INSTAGRAM", "FACEBOOK")) and not leitura and any(p in VERBO_ORGANICO for p in partes):
                achados.append(ORGANICO)
        elif RE_GOOGLE.search(slug) and not leitura:
            achados.append(GOOGLE)
    return achados


def achatar(v, chave=None, out=None):
    """Decoded values of tool_input, recursive; a scalar becomes `key=value`."""
    out = [] if out is None else out
    if isinstance(v, dict):
        for k, x in v.items():
            achatar(x, k, out)
    elif isinstance(v, list):
        for x in v:
            achatar(x, chave, out)
    else:
        out.append("%s=%s" % (chave, v) if chave is not None else str(v))
    return out


def slugs_mcp(v, out=None):
    """Values (str or list of str) of the tool_slug/slug/action/tool keys, recursive."""
    out = [] if out is None else out
    if isinstance(v, dict):
        for k, x in v.items():
            if k in CHAVES_SLUG and isinstance(x, (str, list)):
                out.extend(i for i in ([x] if isinstance(x, str) else x) if isinstance(i, str))
            slugs_mcp(x, out)
    elif isinstance(v, list):
        for x in v:
            slugs_mcp(x, out)
    return out


def achados_da_chamada(nome, ti):
    """List of (policy key or None, message id) for one tool call."""
    if nome in SHELLS:
        cmd = ti.get("command") if isinstance(ti, dict) else None
        bruto = cmd if isinstance(cmd, str) else ""
        base = sem_heredoc(bruto)
        texto = base if RE_BASH_ALVO.search(base) else ""
        slugs = "\n".join(RE_EXECUTE.findall(base) + slugs_execute(base))
        extra = [RUN] if RE_RUN.search(base) else []  # file content is unknown: always ask
        if RE_MKT_JSON.search(bruto):
            extra.append(MKT_JSON)
    elif nome in ESCRITAS:
        caminhos = [ti.get(k) for k in CHAVES_CAMINHO] if isinstance(ti, dict) else []
        return [MKT_JSON] if any(isinstance(c, str) and RE_MKT_JSON.search(c) for c in caminhos) else []
    elif nome.startswith("mcp__"):
        if not RE_FILTRO_MCP.search(nome) and not RE_FILTRO_MCP.search(json.dumps(ti, ensure_ascii=False)):
            return []
        bruto = "\n".join(achatar(ti))
        ferramenta = nome.rsplit("__", 1)[-1]
        texto = ferramenta + "\n" + bruto
        remoto = bool(RE_REMOTO.search(nome))
        slugs = texto if remoto else "\n".join([ferramenta] + slugs_mcp(ti))  # remote: slug may sit inside code
        extra = [ORGANICO] if remoto and RE_CITA_META.search(bruto) else []
    else:
        return []
    g = graph_escrita(bruto)
    return ([g] if g else []) + (classificar(texto, slugs) if texto else []) + extra


def decidir(achados):
    """(action, message id, loosened-by file or None) or None. Deny wins over ask."""
    if not achados:
        return None
    pol, arq = politica() if any(c for c, _ in achados) else (PADRAO, None)
    rs = []
    for chave, msg in achados:
        acao = pol[chave] if chave else "ask"
        afrouxado = arq if chave and PADRAO[chave] == "deny" and acao == "ask" else None
        rs.append(("bloquear" if acao == "deny" else "perguntar", msg, afrouxado))
    return next((r for r in rs if r[0] == "bloquear"), rs[0])


def razao(msg, afrouxado):
    idioma, dono = perfil()
    m = MENSAGENS[idioma]
    texto = m[msg].format(dono=dono)
    if afrouxado:
        texto += m["afrouxado"].format(arq=afrouxado)
    return texto


def main():
    try:
        d = json.loads(sys.stdin.read())
    except ValueError:
        log_erro("stdin is not JSON")
        return
    try:
        if not isinstance(d, dict):
            return
        if TESTE and os.environ.get("TUNEUP_FAKE_EXCECAO") == "1":
            raise RuntimeError("simulated exception")
        r = decidir(achados_da_chamada(str(d.get("tool_name") or ""), d.get("tool_input") or {}))
        if r:
            acao, msg, afrouxado = r
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny" if acao == "bloquear" else "ask",
                "permissionDecisionReason": "tune-up: " + razao(msg, afrouxado)}}) + "\n")
    except Exception as e:
        log_erro("%s: %s" % (type(e).__name__, e))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
