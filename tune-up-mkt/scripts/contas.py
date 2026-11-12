"""tune-up-mkt: read-only check of which marketing accounts are connected, per project.

Usage (from the plugin root): sh scripts/py scripts/contas.py <command> [...] [--raiz DIR]
  status [--json]   run the free local checks (claude plugin list --json, claude mcp list,
                    composio connections list), merge still-valid marks, write .tune-up/mkt/contas.json
  marcar <id> <estado> --prova {whoami_ok,connections_ok,manual} [--via {cli,mcp,manual}]
                    record a check only the session can do; valid for 7 days
  falta [--json]    next step for each service or channel that is not `ligado`
  config [...]      create/update .tune-up/mkt/config.json; no flags = print it
Only the classified state is stored, never command output. Secret-looking values and e-mails are
refused with exit code 2 (the value is not echoed). Exit 0 even when services are missing.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contas_regras as R  # noqa: E402

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMANDOS = {"plugin": (("claude", "plugin", "list", "--json"), 20), "mcp": (("claude", "mcp", "list"), 60)}
TEMPO_CLI = 20
CREDITO_PADRAO = 2000
TEXTOS = {
    "en": {"nada": "Every service and channel is connected.", "rode": "Run: contas.py status",
           "ruim": "{} was unreadable or invalid and was replaced (marks lost).",
           "segredo": "Refused: a value looks like a secret or an e-mail address (not shown). Nothing was written.",
           "marcado": "Marked {} as {} (valid 7 days)."},
    "pt": {"nada": "Todos os serviços e canais estão ligados.", "rode": "Rode: contas.py status",
           "ruim": "{} estava ilegível ou inválido e foi substituído (marcas perdidas).",
           "segredo": "Recusado: um valor parece segredo ou e-mail (não exibido). Nada foi gravado.",
           "marcado": "Marcado {} como {} (vale 7 dias)."},
}


def escrever(texto, fluxo=None):
    """Writes text on any console encoding (cp1252 included): unencodable characters become '?'."""
    fluxo = fluxo or sys.stdout
    buf = getattr(fluxo, "buffer", None)
    if buf is None:
        fluxo.write(texto + "\n")
        return
    fluxo.flush()
    buf.write((texto + "\n").encode(fluxo.encoding or "utf-8", errors="replace"))
    buf.flush()


def idioma():
    try:
        with open(os.path.join(os.path.expanduser("~"), ".config", "tune-up", "user.json"), encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return "en"
    lang = d.get("language") if isinstance(d, dict) else None
    return "pt" if isinstance(lang, str) and lang.strip().lower() == "pt-br" else "en"


def raiz_padrao():
    p = os.environ.get("CLAUDE_PROJECT_DIR", "")
    return p if p and os.path.isabs(p) else os.getcwd()


def ler_catalogo():
    with open(os.path.join(PLUGIN, "servicos.json"), encoding="utf-8") as f:
        return json.load(f)


def ler_json(caminho):
    """(dict or None, invalid): invalid=True when the file exists but cannot be read as a JSON object."""
    try:
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
    except FileNotFoundError:
        return None, False
    except (OSError, ValueError):
        return None, True
    return (d, False) if isinstance(d, dict) else (None, True)


def gravar_json(caminho, dados):
    """Atomic write: temp file in the same folder (0600 on POSIX) + os.replace."""
    pasta = os.path.dirname(caminho)
    os.makedirs(pasta, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=pasta)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if os.name != "nt":
            os.chmod(tmp, 0o600)
        os.replace(tmp, caminho)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def rodar_real(args, timeout):
    """(exit code, stdout). Raises subprocess.TimeoutExpired on timeout."""
    r = subprocess.run(list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       timeout=timeout)
    return r.returncode, r.stdout.decode("utf-8", errors="replace")


def comando_de(checagem):
    """(command tuple, toolkit or None, timeout). `--toolkit x` is read from the full list (one run)."""
    if checagem["tipo"] in COMANDOS:
        args, tempo = COMANDOS[checagem["tipo"]]
        return args, None, tempo
    alvo, toolkit = list(checagem["alvo"]), None
    if "--toolkit" in alvo:
        i = alvo.index("--toolkit")
        toolkit = alvo[i + 1]
        alvo = alvo[:i] + alvo[i + 2:]
    return tuple(alvo), toolkit, TEMPO_CLI


def automaticas(catalogo):
    for chave, conferir in R.chaves(catalogo):
        for c in conferir:
            if c["tipo"] in R.AUTOMATICOS:
                yield chave, c


def conferir_tudo(catalogo, rodar=rodar_real, which=shutil.which, agora=None):
    """key -> list of automatic check results. Each distinct command runs once, all in parallel."""
    agora = agora or datetime.now(timezone.utc)
    pares = list(automaticas(catalogo))
    tempos = {}
    for _, c in pares:
        args, _, tempo = comando_de(c)
        tempos.setdefault(args, tempo)
    caminhos = {args: which(args[0]) for args in tempos}

    def um(args):
        try:
            rc, saida = rodar((caminhos[args],) + tuple(args[1:]), tempos[args])
        except subprocess.TimeoutExpired:
            return None, R.D_TEMPO
        except (OSError, ValueError, subprocess.SubprocessError):
            return None, R.D_NAO_RODOU
        return (saida, None) if rc == 0 else (None, R.D_SAIDA)

    rodaveis = [a for a in tempos if caminhos[a]]
    saidas = {}
    if rodaveis:
        with ThreadPoolExecutor(max_workers=len(rodaveis)) as ex:
            saidas = dict(zip(rodaveis, ex.map(um, rodaveis)))
    auto = {}
    for chave, c in pares:
        args, toolkit, _ = comando_de(c)
        if not caminhos[args]:
            estado, detalhe = ("nao_instalado" if c["tipo"] == "cli" else "nao_sei"), R.D_SEM_COMANDO
        elif saidas[args][0] is None:
            estado, detalhe = "nao_sei", saidas[args][1]
        else:
            estado, detalhe = R.classificar(c["tipo"], saidas[args][0], c["alvo"], toolkit)
        auto.setdefault(chave, []).append({"tipo": c["tipo"], "via": c["tipo"], "estado": estado,
                                           "detalhe": detalhe, "conferido_em": R.iso(agora)})
    return auto


def guardados(dados, catalogo, agora):
    """(automatic results, marks) read back from contas.json; anything malformed is dropped.

    A key whose stored automatic checks do not match the catalog gets `nao_sei` placeholders, so a mark
    can never upgrade a service that was not checked.
    """
    servicos = dados.get("servicos") if isinstance(dados, dict) else None
    servicos = servicos if isinstance(servicos, dict) else {}
    auto, marcas = {}, {}
    for chave, conferir in R.chaves(catalogo):
        sid, _, canal = chave.partition(":")
        item = servicos.get(sid)
        if canal:
            canais = item.get("canais") if isinstance(item, dict) else None
            item = canais.get(canal) if isinstance(canais, dict) else None
        item = item if isinstance(item, dict) else {}
        marca = R.limpar_marca(item.get("marca"))
        if marca:
            marcas[chave] = marca
        esperadas = [c["tipo"] for c in conferir if c["tipo"] in R.AUTOMATICOS]
        lidas = item.get("checagens") if isinstance(item.get("checagens"), list) else []
        lidas = [c for c in map(R.limpar_checagem, lidas) if c]
        if [c["tipo"] for c in lidas] != esperadas:
            lidas = [{"tipo": t, "via": t, "estado": "nao_sei", "detalhe": R.D_NAO_CONFERIDO,
                      "conferido_em": R.iso(agora)} for t in esperadas]
        if lidas:
            auto[chave] = lidas
    return auto, marcas


def caminho(raiz, nome):
    return os.path.join(raiz, ".tune-up", "mkt", nome)


def tabela(dados):
    linhas = []
    for sid, item in dados["servicos"].items():
        extra = "  (cli: {}, mcp: {})".format(item["cli"], item["mcp"]) if "cli" in item else ""
        marca = "✔" if item["estado"] == "ligado" else "-"
        linhas.append("{} {:<28} {}{}".format(marca, sid, item["estado"], extra))
        for cid, canal in item.get("canais", {}).items():
            marca = "✔" if canal["estado"] == "ligado" else "-"
            linhas.append("    {} {:<24} {}".format(marca, sid + ":" + cid, canal["estado"]))
    return "\n".join(linhas)


def status(raiz, catalogo, agora, rodar, which, lang):
    arquivo = caminho(raiz, "contas.json")
    antigo, ruim = ler_json(arquivo)
    if ruim:
        escrever(TEXTOS[lang]["ruim"].format(arquivo), sys.stderr)
    _, marcas = guardados(antigo, catalogo, agora)
    dados = R.montar(catalogo, conferir_tudo(catalogo, rodar, which, agora), marcas, agora)
    gravar_json(arquivo, dados)
    return dados


def cmd_status(a, raiz, catalogo, agora, rodar, which, lang):
    dados = status(raiz, catalogo, agora, rodar, which, lang)
    escrever(json.dumps(dados, ensure_ascii=False, indent=2) if a.json else tabela(dados))
    return 0


def cmd_marcar(a, raiz, catalogo, agora, lang):
    validas = dict(R.chaves(catalogo))
    if a.id not in validas:
        escrever("Unknown id. Valid: " + ", ".join(validas), sys.stderr)
        return 2
    arquivo = caminho(raiz, "contas.json")
    antigo, ruim = ler_json(arquivo)
    if ruim:
        escrever(TEXTOS[lang]["ruim"].format(arquivo), sys.stderr)
    auto, marcas = guardados(antigo, catalogo, agora)
    marcas[a.id] = {"estado": a.estado, "prova": a.prova, "via": a.via, "conferido_em": R.iso(agora)}
    gravar_json(arquivo, R.montar(catalogo, auto, marcas, agora))
    escrever(TEXTOS[lang]["marcado"].format(a.id, a.estado))
    return 0


def passos(s, canal, estado, lang):
    if canal:
        return ["composio link " + canal["id"]] + [p[lang] for p in canal.get("pre_requisitos", [])]
    instalar = [s["cadastro_url"]] + list(s["instalar"])
    if estado == "nao_instalado":
        return instalar
    if estado == "falta_autenticar":
        return [s["autenticar"][lang]]
    return instalar + [s["autenticar"][lang]]


def cmd_falta(a, raiz, catalogo, agora, rodar, which, lang):
    dados, _ = ler_json(caminho(raiz, "contas.json"))
    servicos = dados.get("servicos") if dados else None
    if not isinstance(servicos, dict):
        servicos = status(raiz, catalogo, agora, rodar, which, lang)["servicos"]
    lista = []
    for s in catalogo["servicos"]:
        item = servicos.get(s["id"]) if isinstance(servicos.get(s["id"]), dict) else {}
        alvos = [(s["id"], None, item)]
        canais = item.get("canais") if isinstance(item.get("canais"), dict) else {}
        alvos += [(s["id"] + ":" + c["id"], c, canais.get(c["id"]) or {}) for c in s.get("canais", [])]
        for chave, canal, dado in alvos:
            estado = dado.get("estado") if isinstance(dado, dict) else None
            estado = estado if estado in R.PIOR_PRIMEIRO + ("conferir_de_novo",) else "nao_sei"
            if estado != "ligado":
                lista.append({"id": chave, "estado": estado, "passos": passos(s, canal, estado, lang)})
    if a.json:
        escrever(json.dumps(lista, ensure_ascii=False, indent=2))
    elif not lista:
        escrever(TEXTOS[lang]["nada"])
    else:
        escrever("\n".join("{} ({})\n".format(i["id"], i["estado"]) + "\n".join("  - " + p for p in i["passos"])
                           for i in lista))
    return 0


def site_valido(url):
    try:
        u = urlsplit(url)
        u.port  # noqa: B018  (raises ValueError on a bad port)
    except ValueError:
        return False
    consulta = u.query.lower()
    return (u.scheme in ("http", "https") and bool(u.hostname) and "@" not in u.netloc
            and not any(k in consulta for k in ("key=", "token=", "secret=")))


def cmd_config(a, raiz, lang):
    arquivo = caminho(raiz, "config.json")
    atual, ruim = ler_json(arquivo)
    mudou = any(v is not None for v in (a.site, a.canais, a.indexnow_key, a.credit_ask_above))
    if not mudou:
        escrever(json.dumps(atual or {}, ensure_ascii=False, indent=2))
        return 0
    if a.site is not None and not site_valido(a.site):
        escrever("--site must be an http(s) URL without credentials or key/token/secret in the query.", sys.stderr)
        return 2
    if a.indexnow_key is not None and not R.indexnow_valida(a.indexnow_key):
        escrever("--indexnow-key must be 8 to 128 characters of a-z, A-Z, 0-9 and -.", sys.stderr)
        return 2
    if a.credit_ask_above is not None and a.credit_ask_above < 0:
        escrever("--credit-ask-above must be 0 or more.", sys.stderr)
        return 2
    if ruim:
        escrever(TEXTOS[lang]["ruim"].format(arquivo), sys.stderr)
    novo = dict(atual or {})
    novo.setdefault("credit_ask_above", CREDITO_PADRAO)
    if a.site is not None:
        novo["site"] = a.site
    if a.canais is not None:
        novo["canais"] = [c.strip() for c in a.canais.split(",") if c.strip()]
    if a.indexnow_key is not None:
        novo["indexnow_key"] = a.indexnow_key
    if a.credit_ask_above is not None:
        novo["credit_ask_above"] = a.credit_ask_above
    gravar_json(arquivo, novo)
    escrever(json.dumps(novo, ensure_ascii=False, indent=2))
    return 0


def recusado(argv):
    """True when any argument (except the IndexNow key, public by design) looks like a secret or e-mail."""
    pular = False
    for v in argv:
        if pular:
            pular = False
            if not R.tem_email(v):
                continue
        if v == "--indexnow-key":
            pular = True
            continue
        if v.startswith("--indexnow-key="):
            v = v.split("=", 1)[1]
            if not R.tem_email(v):
                continue
        if R.parece_segredo(v) or R.tem_email(v):
            return True
    return False


def parser():
    p = argparse.ArgumentParser(prog="contas.py", allow_abbrev=False, description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)
    raiz = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    raiz.add_argument("--raiz", help="project root (default: $CLAUDE_PROJECT_DIR if absolute, else cwd)")
    s = sub.add_parser("status", parents=[raiz], allow_abbrev=False, help="run the checks and write contas.json")
    s.add_argument("--json", action="store_true")
    m = sub.add_parser("marcar", parents=[raiz], allow_abbrev=False, help="record a check made by the session")
    m.add_argument("id", help="service id or composio:<channel>")
    m.add_argument("estado", choices=R.ESTADOS_MARCA)
    m.add_argument("--prova", required=True, choices=R.PROVAS)
    m.add_argument("--via", default="manual", choices=R.VIAS_MARCA)
    f = sub.add_parser("falta", parents=[raiz], allow_abbrev=False, help="next step for what is not connected")
    f.add_argument("--json", action="store_true")
    c = sub.add_parser("config", parents=[raiz], allow_abbrev=False, help="create/update config.json")
    c.add_argument("--site", help="http(s) URL of the site, without credentials")
    c.add_argument("--canais", help="comma-separated channel list")
    c.add_argument("--indexnow-key", help="IndexNow key (8-128 chars of a-z A-Z 0-9 -). It is PUBLIC by design: "
                                          "it is served as <key>.txt on the site, so storing it is safe.")
    c.add_argument("--credit-ask-above", type=int, help="ask before spending more credits than this (default 2000)")
    return p


def main(argv=None, agora=None, rodar=rodar_real, which=shutil.which):
    argv = sys.argv[1:] if argv is None else list(argv)
    lang = idioma()
    if recusado(argv):
        escrever(TEXTOS[lang]["segredo"], sys.stderr)
        return 2
    a = parser().parse_args(argv)
    raiz = os.path.abspath(a.raiz) if a.raiz else raiz_padrao()
    agora = agora or datetime.now(timezone.utc)
    if a.comando == "config":
        return cmd_config(a, raiz, lang)
    catalogo = ler_catalogo()
    if a.comando == "status":
        return cmd_status(a, raiz, catalogo, agora, rodar, which, lang)
    if a.comando == "marcar":
        return cmd_marcar(a, raiz, catalogo, agora, lang)
    return cmd_falta(a, raiz, catalogo, agora, rodar, which, lang)


if __name__ == "__main__":
    sys.exit(main())
