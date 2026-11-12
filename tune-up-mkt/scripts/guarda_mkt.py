#!/usr/bin/env python3
"""tune-up-mkt: guard for writes to ad accounts and public posts (PreToolUse).

Usage: sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda_mkt.py   (see hooks/hooks.json)
Reads the hook JSON on stdin; writes JSON only when there is a decision. Always exit 0.
Internal exception = no decision; one line in <data>/erros.log.
Per-project loosening: ~/.config/tune-up/mkt.json, keyed by CLAUDE_PROJECT_DIR (absolute paths only).
Messages: `language` and `owner` from ~/.config/tune-up/user.json.
"""
import json
import os
import re
import sys
import time

# Factory policy; mkt.json may only set "deny" or "ask" per key (never pass).
PADRAO = {"meta_ads_write": "deny", "google_ads_write": "ask", "organic_publish": "ask"}
META = ("meta_ads_write", "meta")
ORGANICO = ("organic_publish", "organico")
GOOGLE = ("google_ads_write", "google")
RUN = (None, "run")            # None = fixed "ask", not configurable
MKT_JSON = (None, "mkt_json")
ILEGIVEL = (None, "ilegivel")

MENSAGENS = {
    "en": {
        "meta": ("Meta ad objects: writes through the API are blocked. Make the change in Ads Manager "
                 "in the browser, on {dono}'s explicit request."),
        "organico": "public post: only on {dono}'s order.",
        "google": "Google Ads change: confirm first (without {dono}'s order, read only).",
        "run": "`composio run` executes a file this guard cannot read: confirm first.",
        "mkt_json": "mkt.json loosens the marketing guard: confirm this change.",
        "ilegivel": "`composio execute` with a tool slug this guard cannot read: confirm first.",
        "afrouxado": " The default is to block; loosened to ask by {arq}.",
    },
    "pt-BR": {
        "meta": ("objetos de anúncio da Meta: escrita pela API está bloqueada. Faça a mudança no "
                 "Gerenciador de Anúncios, no navegador, com pedido explícito {dono}."),
        "organico": "publicação pública: só com ordem {dono}.",
        "google": "mudança no Google Ads: confirme antes (sem ordem {dono}, só leitura).",
        "run": "`composio run` executa um arquivo que esta guarda não lê: confirme antes.",
        "mkt_json": "o mkt.json afrouxa a guarda de marketing: confirme esta mudança.",
        "ilegivel": "`composio execute` com um slug que esta guarda não consegue ler: confirme antes.",
        "afrouxado": " O padrão é bloquear; afrouxado para perguntar por {arq}.",
    },
}

SHELLS = {"Bash", "PowerShell", "Monitor"}
ESCRITAS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
CHAVES_CAMINHO = ("file_path", "notebook_path", "path")
RE_FILTRO_MCP = re.compile(r"(?i)composio|meta|facebook|instagram|google_?ads|graph\.(?:facebook|instagram)|\bfb[_-]")
RE_MKT_JSON = re.compile(r"(?i)(?<![\w.-])mkt\.json(?!\w)")

RE_SLUG = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|[A-Z]{6,}")
PLATAFORMA_META = re.compile(r"^(META|FACEBOOK|FB|INSTAGRAM)")
TERMO_AD = re.compile(r"^(ADS?|ADSETS?|CAMPAIGNS?|AUDIENCES?|BUDGETS?|CREATIVES?|BIDS?|BIDDING)$")
VERBO_ESCRITA = re.compile(r"^(CREATE|UPDATE|DELETE|PAUSE|ACTIVATE|EDIT|SET|DUPLICATE|ARCHIVE|UPLOAD|PUBLISH)S?$")
VERBO_LEITURA = {"GET", "LIST", "FETCH", "SEARCH", "INSIGHTS", "REPORT", "READ", "FIND", "RETRIEVE"}
VERBO_ORGANICO = {"CREATE", "PUBLISH", "POST", "UPLOAD", "SEND", "COMMENT", "REPLY", "DELETE", "UPDATE", "SCHEDULE"}
RE_GOOGLE = re.compile(r"GOOGLE_?ADS[A-Z_]*(MUTATE|CREATE|UPDATE|REMOVE|PAUSE|ENABLE|SET)")
RE_METODO = re.compile(r"(?i)([\"']?method[\"']?\s*[:=]\s*[\"']?|-X\s*|--method[ =]|--request[ =])(POST|DELETE|PUT|PATCH)\b")
RE_GRAPH_URL = re.compile(r"(?i)graph\.(?:facebook|instagram)\.com/[^\s\"'\\]*")
RE_GRAPH_AD = re.compile(r"(?i)/(act_[^/?\s]*|campaigns|adsets|ads|adcreatives)(?=[/?#]|$)")
RE_DADOS = re.compile(r"(?:^|[\s\"'])(?:-d|-F|--data[\w-]*|--form)(?=[\s=\"']|\S)")
RE_GET = re.compile(r"(?i)(-X\s*|--request[ =]|--method[ =]|-Method[\s:]+['\"]?)GET\b")
# PowerShell -Method, requests/fetch .post(, httpie `POST url`, curl --json, wget --post-data
RE_ESCRITA = re.compile(r"(?i)-Method[\s:]+['\"]?(?:Post|Put|Patch|Delete)\b|\.(?:post|put|patch|delete)\(|"
                        r"\b(?:POST|PUT|PATCH|DELETE)\s+['\"]?https?://|(?:^|[\s\"'])--(?:json|post-data|post-file)\b")
RE_CORPO = re.compile(r"(?i)(?:^|[\s\"'])-(?:Body|InFile)\b")  # PowerShell body (a write unless -Method Get)
RE_CURL_G = re.compile(r"(?:^|[\s\"'])(?:-G|--get)(?=[\s\"']|$)")  # -d becomes a GET query; no (?i): -g is --globoff
RE_REMOTO = re.compile(r"(?i)(?:^|_)REMOTE_(WORKBENCH|BASH_TOOL)$")
RE_CITA_META = re.compile(r"(?i)\bmeta\b|\bmetaads\b|facebook|instagram|graph\.")
# composio, composio.cmd/.exe/.ps1, 'composio', `composio, node_modules\.bin\composio, @composio/cli@x
NOME_COMPOSIO = r"(?:^|[\s/\\;&|(])[\"'`]?(?:composio|@composio/cli)(?:\.(?:cmd|exe|ps1))?[\"'`]?(?:@\S*)?"
RE_EXECUTE = re.compile(r"(?i)" + NOME_COMPOSIO + r"\s+execute\s+['\"]?([A-Za-z0-9_]+)")
RE_EXECUTE_INICIO = re.compile(r"(?i)" + NOME_COMPOSIO + r"\s.*?\bexecute\b", re.S)
RE_RUN = re.compile(r"(?i)\bcomposio\s+run\b")
RE_TOKEN_SLUG = re.compile(r"^[A-Za-z]+(_[A-Za-z0-9]+)+$")
CHAVES_SLUG = {"tool_slug", "slug", "action", "tool", "tool_name", "toolSlug"}
RE_BASH_ALVO = re.compile(r"(?i)composio|graph\.facebook\.com|graph\.instagram\.com")
RE_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*['\"]?(\w+)['\"]?")
# dedicated MCP servers: normalized server name -> synthetic slug prefix for the classifier
RE_SERVIDOR_META = re.compile(r"^(meta|facebook|fb|instagram)(_?ads)?$")
RE_SERVIDOR_GOOGLE = re.compile(r"^google_?ads$")


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
    except Exception as e:  # invalid JSON, RecursionError on deep nesting, ...
        log_erro("unreadable JSON in %s: %s" % (caminho, type(e).__name__))
        return None


def caminho_mkt_json():
    return os.path.join(os.path.expanduser("~"), ".config", "tune-up", "mkt.json")


def normalizar(p):
    """Comparable form of an absolute path; None when relative or unusable (a bad key never disables the guard)."""
    try:
        p = os.path.expanduser(p.strip())
        if not os.path.isabs(p):
            return None
        p = os.path.normcase(os.path.realpath(p))
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
    d = ler_json(os.path.join(os.path.expanduser("~"), ".config", "tune-up", "user.json"))
    d = d if isinstance(d, dict) else {}
    lang = d.get("language")
    idioma = "pt-BR" if isinstance(lang, str) and lang.strip().lower() == "pt-br" else "en"
    dono = d.get("owner").strip() if nome_simples(d.get("owner")) else None
    if idioma == "pt-BR":
        return idioma, ("de " + dono) if dono else "do dono"
    return idioma, dono or "the owner"


def sem_heredoc(cmd):
    """Bash heredoc bodies removed; a marker never terminated (e.g. `$((1<<2))`) = original command."""
    saida, pendentes = [], []
    for linha in cmd.split("\n"):
        if pendentes:
            if linha.strip() == pendentes[0]:
                pendentes.pop(0)
            continue
        saida.append(linha)
        pendentes.extend(RE_HEREDOC.findall(linha))
    return cmd if pendentes else "\n".join(saida)


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
    escrita = RE_METODO.search(texto) or RE_ESCRITA.search(texto) or (
        (RE_DADOS.search(texto) or RE_CORPO.search(texto)) and not RE_GET.search(texto) and not RE_CURL_G.search(texto))
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


def slugs_mcp(v, out=None, fundo=0):
    """Values (str or list of str) of the CHAVES_SLUG keys, recursive; a JSON string is decoded (depth <= 5)."""
    out = [] if out is None else out
    if isinstance(v, dict):
        for k, x in v.items():
            if k in CHAVES_SLUG and isinstance(x, (str, list)):
                out.extend(i for i in ([x] if isinstance(x, str) else x) if isinstance(i, str))
            slugs_mcp(x, out, fundo)
    elif isinstance(v, list):
        for x in v:
            slugs_mcp(x, out, fundo)
    elif isinstance(v, str) and fundo < 5 and v.lstrip()[:1] in ("[", "{"):
        try:
            slugs_mcp(json.loads(v), out, fundo + 1)
        except ValueError:
            pass
    return out


def textos(v, out=None):
    """Every string value of tool_input, recursive."""
    out = [] if out is None else out
    if isinstance(v, dict):
        for x in v.values():
            textos(x, out)
    elif isinstance(v, list):
        for x in v:
            textos(x, out)
    elif isinstance(v, str):
        out.append(v)
    return out


def slug_do_servidor(nome):
    """`mcp__<server>__<tool>` of a dedicated ads/social server -> synthetic slug (e.g. METAADS_UPDATE_CAMPAIGN)."""
    partes = nome.split("__")
    if len(partes) < 3:
        return None
    srv = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", "__".join(partes[1:-1])).lower()
    srv = re.sub(r"^(claude_ai_|plugin_[^_]+_)", "", srv)
    srv = re.sub(r"[^a-z0-9]+", "_", srv).strip("_")
    if RE_SERVIDOR_GOOGLE.match(srv):
        prefixo = "GOOGLEADS"
    elif RE_SERVIDOR_META.match(srv):
        # "ads" in the name = ad object (write verbs deny); plain facebook/instagram/meta = organic
        prefixo = "METAADS" if "ads" in srv else ("INSTAGRAM" if srv == "instagram" else "FACEBOOK")
    else:
        return None
    ferramenta = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", partes[-1])
    return prefixo + "_" + re.sub(r"[^A-Za-z0-9]+", "_", ferramenta).upper().strip("_")


def execute_em(cmd):
    """(slugs after `composio ... execute`, True when the command has an execute without a readable slug)."""
    slugs = RE_EXECUTE.findall(cmd) + slugs_execute(cmd)
    return slugs, bool(RE_EXECUTE_INICIO.search(cmd)) and not slugs


def achados_da_chamada(nome, ti):
    """List of (policy key or None, message id) for one tool call."""
    if nome in SHELLS:
        cmd = ti.get("command") if isinstance(ti, dict) else None
        bruto = cmd if isinstance(cmd, str) else ""
        base = bruto if nome == "PowerShell" else sem_heredoc(bruto)  # PowerShell has no << heredoc
        texto = base if RE_BASH_ALVO.search(base) else ""
        lista, ilegivel = execute_em(base)
        slugs = "\n".join(lista)
        extra = [RUN] if RE_RUN.search(base) else []  # file content is unknown: always ask
        if ilegivel:
            extra.append(ILEGIVEL)
        if RE_MKT_JSON.search(bruto):
            extra.append(MKT_JSON)
    elif nome in ESCRITAS:
        caminhos = [ti.get(k) for k in CHAVES_CAMINHO] if isinstance(ti, dict) else []
        return [MKT_JSON] if any(isinstance(c, str) and RE_MKT_JSON.search(c) for c in caminhos) else []
    elif nome.startswith("mcp__"):
        sintetico = slug_do_servidor(nome)
        if not sintetico and not RE_FILTRO_MCP.search(nome) and not RE_FILTRO_MCP.search(
                json.dumps(ti, ensure_ascii=False)):
            return []
        bruto = "\n".join(achatar(ti))
        ferramenta = nome.rsplit("__", 1)[-1]
        texto = ferramenta + "\n" + bruto
        remoto = bool(RE_REMOTO.search(nome))
        lista, ilegiveis = [], False
        for t in textos(ti):
            s, i = execute_em(t)
            lista += s
            ilegiveis = ilegiveis or i
        slugs = "\n".join(([texto] if remoto else [ferramenta] + slugs_mcp(ti)) + lista + [sintetico or ""])
        extra = [ORGANICO] if remoto and RE_CITA_META.search(bruto) else []
        if remoto and ilegiveis:
            extra.append(ILEGIVEL)
    else:
        return []
    g = graph_escrita(bruto)
    return ([g] if g else []) + (classificar(texto, slugs) if texto else []) + extra


def decidir(achados):
    """(action, message id, loosened-by file or None) or None. Deny wins over ask."""
    if not achados:
        return None
    try:
        pol, arq = politica() if any(c for c, _ in achados) else (PADRAO, None)
    except Exception as e:  # a config failure never drops a decision: defaults apply
        log_erro("policy: %s: %s" % (type(e).__name__, e))
        pol, arq = PADRAO, None
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
        r = decidir(achados_da_chamada(str(d.get("tool_name") or ""), d.get("tool_input") or {}))
        if r:
            acao, msg, afrouxado = r
            try:
                texto = razao(msg, afrouxado)
            except Exception as e:  # never lose the decision over its wording
                log_erro("reason: %s: %s" % (type(e).__name__, e))
                texto = MENSAGENS["en"][msg].format(dono="the owner")
            sys.stdout.write(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny" if acao == "bloquear" else "ask",
                "permissionDecisionReason": "tune-up: " + texto}}) + "\n")
    except Exception as e:
        log_erro("%s: %s" % (type(e).__name__, e))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
