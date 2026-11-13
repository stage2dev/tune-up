"""tune-up-mkt: read-only check of which marketing accounts are connected, per project.

Usage (from the plugin root): sh scripts/py scripts/contas.py <command> [...] [--raiz DIR]
  status [--json]   run the free local checks (claude plugin list --json, claude mcp list,
                    composio connections list), merge still-valid marks, write .tune-up/mkt/contas.json
  marcar <id> <estado> --prova {whoami_ok,connections_ok,manual} [--via {mcp,cli,manual}]
                    record a check only the session can do; valid for 7 days (via follows prova)
  falta [--json]    next step for each service or channel that is not `ligado`, then accounts to verify;
                    needs a `status` from the last 24 h
  config [...]      create/update .tune-up/mkt/config.json; no flags = print it
Commands run in the project folder (--raiz). Only the classified state is stored, never command output.
Secret-looking values and e-mails are refused with exit code 2 (the value is not echoed); so are state
files reached through a symlink. Exit 0 even when services are missing; 1 when a file cannot be written.
"""
import argparse
import json
import os
import secrets
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contas_arquivos as A  # noqa: E402
import contas_regras as R  # noqa: E402

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMANDOS = {"plugin": (("claude", "plugin", "list", "--json"), 20), "mcp": (("claude", "mcp", "list"), 60)}
TEMPO_CLI = 20
CREDITO_PADRAO = 2000
IDADE_FALTA = timedelta(hours=24)
TEXTOS = {
    "en": {"nada": "Every service and channel is connected.",
           "rode": "No recent check (missing or older than 24 h): run `contas.py status` first.",
           "idade": "Last check: {} min ago.", "link": "Refused: .tune-up, .tune-up/mkt or the state file is a "
           "symlink or points outside the project. Nothing was read or written.",
           "verificar": "Connected, but the account itself was not verified (or the check expired): run the "
           "connect skill to verify it with a free read.",
           "ruim": "{} was unreadable or invalid and was replaced (marks lost).",
           "segredo": "Refused: a value looks like a secret or an e-mail address (not shown). Nothing was written.",
           "marcado": "Marked {} as {} (valid 7 days)."},
    "pt": {"nada": "Todos os serviços e canais estão ligados.",
           "rode": "Sem conferência recente (ausente ou com mais de 24 h): rode `contas.py status` antes.",
           "idade": "Última conferência: há {} min.", "link": "Recusado: .tune-up, .tune-up/mkt ou o arquivo "
           "de estado é um link simbólico ou aponta para fora do projeto. Nada foi lido nem gravado.",
           "verificar": "Ligado, mas a conta em si não foi conferida (ou a conferência venceu): rode a skill "
           "connect para conferir com uma leitura grátis.",
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


def rodar_real(args, timeout, cwd=None):
    """(exit code, stdout), run in cwd (the project). Raises subprocess.TimeoutExpired on timeout."""
    r = subprocess.run(list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                       timeout=timeout, cwd=cwd)
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


def conferir_tudo(catalogo, rodar=rodar_real, which=None, agora=None, raiz=None):
    """key -> list of automatic check results. Each distinct command runs once, all in parallel, in raiz."""
    agora = agora or datetime.now(timezone.utc)
    raiz = raiz or os.getcwd()
    which = which or (lambda nome: A.achar(nome, raiz))
    pares = list(automaticas(catalogo))
    tempos = {}
    for _, c in pares:
        args, _, tempo = comando_de(c)
        tempos.setdefault(args, tempo)
    caminhos = {args: which(args[0]) for args in tempos}

    def um(args):
        try:
            rc, saida = rodar((caminhos[args],) + tuple(args[1:]), tempos[args], raiz)
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
            estado, detalhe = R.classificar(c["tipo"], saidas[args][0], c["alvo"], toolkit, c.get("host"))
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


def tabela(dados):
    linhas = ["  {:<28} {:<17} {}".format("service", "estado", "conta")]
    for sid, item in dados["servicos"].items():
        extra = "  (cli: {}, mcp: {})".format(item["cli"], item["mcp"]) if "cli" in item else ""
        marca = "✔" if item["estado"] == "ligado" else "-"
        linhas.append("{} {:<28} {:<17} {}{}".format(marca, sid, item["estado"], item["conta"], extra))
        for cid, canal in item.get("canais", {}).items():
            marca = "✔" if canal["estado"] == "ligado" else "-"
            linhas.append("    {} {:<24} {}".format(marca, sid + ":" + cid, canal["estado"]))
    return "\n".join(linhas)


def avisar_ruim(ruim, raiz, lang):
    texto = TEXTOS[lang]["ruim"].format(A.caminho(raiz, "contas.json")) if ruim else None
    if texto:
        escrever(texto, sys.stderr)
    return texto


def cmd_status(a, raiz, catalogo, agora, rodar, which, lang):
    A.caminho(raiz, "contas.json")  # refuse a symlinked state file before running anything
    _, marcas_antes = guardados(A.ler_json(A.caminho(raiz, "contas.json"))[0], catalogo, agora)
    auto = conferir_tudo(catalogo, rodar, which, agora, raiz)

    def fazer(antigo):  # marks recorded while the commands ran are merged, never lost
        _, marcas = guardados(antigo, catalogo, agora)
        return R.montar(catalogo, auto, R.juntar(marcas_antes, marcas), agora)
    dados, ruim = A.atualizar(raiz, "contas.json", fazer)
    aviso = avisar_ruim(ruim, raiz, lang)
    saida = dict(dados, aviso=aviso) if aviso else dados
    escrever(json.dumps(saida, ensure_ascii=False, indent=2) if a.json else tabela(dados))
    return 0


def cmd_marcar(a, raiz, catalogo, agora, lang):
    validas = dict(R.chaves(catalogo))
    if a.id not in validas:
        escrever("Unknown id. Valid: " + ", ".join(validas), sys.stderr)
        return 2
    via = a.via or R.VIA_DA_PROVA[a.prova]
    if via != R.VIA_DA_PROVA[a.prova]:
        escrever("--via must match --prova: whoami_ok -> mcp, connections_ok -> cli, manual -> manual.", sys.stderr)
        return 2
    nova = {"estado": a.estado, "prova": a.prova, "via": via, "conferido_em": R.iso(agora)}

    def fazer(antigo):
        auto, marcas = guardados(antigo, catalogo, agora)
        return R.montar(catalogo, auto, R.juntar(marcas, {a.id: nova}), agora)
    _, ruim = A.atualizar(raiz, "contas.json", fazer)
    avisar_ruim(ruim, raiz, lang)
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


def cmd_falta(a, raiz, catalogo, agora, lang):
    """Rebuilt from the sanitized stored checks (same cleaning as status); refuses a check older than 24 h."""
    dados, _ = A.ler_json(A.caminho(raiz, "contas.json"))
    quando = R.ler_iso(dados.get("conferido_em")) if dados else None
    if quando is None or agora - quando > IDADE_FALTA or quando > agora + R.FOLGA_FUTURO:
        escrever(TEXTOS[lang]["rode"], sys.stderr)
        return 1
    servicos = R.montar(catalogo, *guardados(dados, catalogo, agora), agora)["servicos"]
    lista, verificar = [], []
    for s in catalogo["servicos"]:
        item = servicos[s["id"]]
        alvos = [(s["id"], None, item)] + [(s["id"] + ":" + c["id"], c, item["canais"][c["id"]])
                                           for c in s.get("canais", [])]
        for chave, canal, dado in alvos:
            if dado["estado"] != "ligado":
                lista.append({"id": chave, "estado": dado["estado"], "passos": passos(s, canal, dado["estado"], lang)})
            elif dado["conta"] in ("nao_conferida", "conferir_de_novo"):
                verificar.append({"id": chave, "estado": "ligado", "conta": dado["conta"],
                                  "passos": [TEXTOS[lang]["verificar"]]})
    lista += verificar
    minutos = int(max(0, (agora - quando).total_seconds()) // 60)
    if a.json:
        escrever(json.dumps({"conferido_em": R.iso(quando), "minutos": minutos, "itens": lista},
                            ensure_ascii=False, indent=2))
        return 0
    linhas = [TEXTOS[lang]["idade"].format(minutos)]
    if not lista:
        linhas.append(TEXTOS[lang]["nada"])
    for i in lista:
        rotulo = i["estado"] + (", conta: " + i["conta"] if "conta" in i else "")
        linhas.append("{} ({})\n".format(i["id"], rotulo) + "\n".join("  - " + p for p in i["passos"]))
    escrever("\n".join(linhas))
    return 0


def cmd_config(a, raiz, lang):
    """Only the known keys are read, printed and written (anything else in the file is dropped)."""
    atual, _ = A.ler_json(A.caminho(raiz, "config.json"))
    mudou = any(v is not None for v in (a.site, a.canais, a.indexnow_key, a.credit_ask_above)) or a.gerar_indexnow
    if not mudou:
        escrever(json.dumps(R.limpar_config(atual), ensure_ascii=False, indent=2))
        return 0
    canais = None if a.canais is None else [c.strip() for c in a.canais.split(",") if c.strip()]
    erro = None
    if a.site is not None and not R.site_valido(a.site):
        erro = ("--site must be http(s)://host[:port][/path] with no user info, query (?) or fragment (#); "
                "path parts of letters, digits, - _ . ~ % under 40 characters each.")
    elif canais is not None and not R.canais_validos(canais):
        erro = "--canais accepts only: " + ",".join(R.CANAIS) + " (value not shown)."
    elif a.indexnow_key is not None and not R.indexnow_valida(a.indexnow_key):
        erro = ("--indexnow-key must be 8 to 128 characters of a-z, A-Z, 0-9 and -, and never another "
                "provider's key (value not shown). Prefer --gerar-indexnow.")
    elif a.credit_ask_above is not None and a.credit_ask_above < 0:
        erro = "--credit-ask-above must be 0 or more."
    if erro:
        escrever(erro, sys.stderr)
        return 2

    def fazer(antigo):
        novo = R.limpar_config(antigo)
        novo.setdefault("credit_ask_above", CREDITO_PADRAO)
        if a.site is not None:
            novo["site"] = a.site
        if canais is not None:
            novo["canais"] = canais
        if a.indexnow_key is not None:
            novo["indexnow_key"] = a.indexnow_key
        elif a.gerar_indexnow and "indexnow_key" not in novo:  # an existing key is kept (it may be published)
            novo["indexnow_key"] = secrets.token_hex(16)
        if a.credit_ask_above is not None:
            novo["credit_ask_above"] = a.credit_ask_above
        return novo
    novo, ruim = A.atualizar(raiz, "config.json", fazer)
    if ruim:
        escrever(TEXTOS[lang]["ruim"].format(A.caminho(raiz, "config.json")), sys.stderr)
    escrever(json.dumps(novo, ensure_ascii=False, indent=2))
    return 0


def recusado(argv):
    """True when any argument looks like a secret or e-mail. Exempt: the value of --raiz (a local path, never
    stored) and, for `config` only, the IndexNow key (public by design; still checked for e-mail)."""
    config = bool(argv) and argv[0] == "config"
    pular = None
    for v in argv:
        if pular:
            pular, livre = None, pular == "--raiz"
            if livre or not R.tem_email(v):
                continue
        if v == "--raiz" or (config and v == "--indexnow-key"):
            pular = v
            continue
        if v.startswith("--raiz="):
            continue
        if config and v.startswith("--indexnow-key="):
            v = v.split("=", 1)[1]
            if not R.tem_email(v):
                continue
        if R.parece_segredo(v) or R.tem_email(v):
            return True
    return False


class Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse would echo the offending value
        escrever("Invalid arguments (values not shown). Run with --help.", sys.stderr)
        sys.exit(2)


def parser():
    p = Parser(prog="contas.py", allow_abbrev=False, description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="comando", required=True)
    raiz = Parser(add_help=False, allow_abbrev=False)
    raiz.add_argument("--raiz", help="project root (default: $CLAUDE_PROJECT_DIR if absolute, else cwd)")
    s = sub.add_parser("status", parents=[raiz], allow_abbrev=False, help="run the checks and write contas.json")
    s.add_argument("--json", action="store_true")
    m = sub.add_parser("marcar", parents=[raiz], allow_abbrev=False, help="record a check made by the session")
    m.add_argument("id", help="service id or composio:<channel>")
    m.add_argument("estado", choices=R.ESTADOS_MARCA)
    m.add_argument("--prova", required=True, choices=R.PROVAS)
    m.add_argument("--via", choices=R.VIAS_MARCA, help="default and only accepted value follows --prova: "
                                                         "whoami_ok -> mcp, connections_ok -> cli, manual -> manual")
    f = sub.add_parser("falta", parents=[raiz], allow_abbrev=False, help="next step for what is not connected")
    f.add_argument("--json", action="store_true")
    c = sub.add_parser("config", parents=[raiz], allow_abbrev=False, help="create/update config.json")
    c.add_argument("--site", help="http(s)://host[:port][/path], no user info, query or fragment")
    c.add_argument("--canais", help="comma-separated, only: " + ",".join(R.CANAIS))
    k = c.add_mutually_exclusive_group()
    k.add_argument("--gerar-indexnow", action="store_true", help="create the IndexNow key (kept if one exists)")
    k.add_argument("--indexnow-key", help="an existing IndexNow key (8-128 chars of a-z A-Z 0-9 -). It is PUBLIC by "
                                          "design: it is served as <key>.txt on the site, so storing it is safe. "
                                          "Never put any other key here.")
    c.add_argument("--credit-ask-above", type=int, help="ask before spending more credits than this (default 2000)")
    return p


def main(argv=None, agora=None, rodar=rodar_real, which=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    lang = idioma()
    if recusado(argv):
        escrever(TEXTOS[lang]["segredo"], sys.stderr)
        return 2
    a = parser().parse_args(argv)
    raiz = os.path.abspath(a.raiz) if a.raiz else raiz_padrao()
    agora = agora or datetime.now(timezone.utc)
    try:
        if a.comando == "config":
            return cmd_config(a, raiz, lang)
        catalogo = ler_catalogo()
        if a.comando == "status":
            return cmd_status(a, raiz, catalogo, agora, rodar, which, lang)
        if a.comando == "marcar":
            return cmd_marcar(a, raiz, catalogo, agora, lang)
        return cmd_falta(a, raiz, catalogo, agora, lang)
    except A.Recusado:
        escrever(TEXTOS[lang]["link"], sys.stderr)
        return 2
    except OSError as e:
        escrever("Could not read or write the state in .tune-up/mkt: {}.".format(e.strerror or "error"), sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
