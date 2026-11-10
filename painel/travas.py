"""Travas de verdade das sessões que o painel dispara (não só frase no prompt).

O núcleo não conhece ferramenta de projeto nenhum: as travas de cada ação vêm do
JSON da própria ação, em dois campos opcionais:

  "negar":    [ "<regra de permissão>" | {regra do gancho} ]
  "permitir": [ "<regra de permissão>" | {regra do gancho} ]

- Texto vira regra de permissão do Claude Code (`permissions.deny` / `permissions.allow`),
  ex. "mcp__servidor__ferramenta", "Bash(rm *)".
- Objeto vira regra do gancho PreToolUse que roda ESTE arquivo e olha o conteúdo da
  chamada: {"ferramenta": regex (casa o nome inteiro), "campo"?: nome de um campo da
  entrada, "entrada"?: regex procurada nesse campo (ou na entrada inteira em JSON),
  "decisao"?: "deny" | "ask" (padrão deny), "motivo"?: texto curto}.
  Uma regra de "permitir" que casa cala o gancho (antes das de "negar"); a proteção
  fixa abaixo vale sempre.

Proteção fixa do núcleo (toda ação): mexer em .claude/settings*.json, .claude/hooks/,
no painel.json, no núcleo ou no pacote do painel (menos <pacote>/dados/) nega em ação
de risco leitura/rascunho e pergunta em código/crédito. Se o gancho falhar: nega em
leitura/rascunho, pergunta no resto. Deny de gancho vence o "allow" de outro gancho.
Python 3.9, só biblioteca padrão; o gancho não importa nada do painel.
"""
import base64
import json
import os
import re
import shlex
import sys

RISCO_LEVE = ("leitura", "rascunho")
DECISOES = ("deny", "ask")
MAX_REGRAS = 200
MAX_TEXTO = 300
MAX_REGEX = 1000  # lista do que pode (lookahead negativo) precisa de espaço
MAX_CONF = 48 * 1024
RE_CAMPO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
NEGAR_LEVE = ["Edit(**/.claude/settings*.json)", "Write(**/.claude/settings*.json)",
              "MultiEdit(**/.claude/settings*.json)"]
CAMINHO_CONFIG = re.compile(r"(^|[/\s'\"=])\.claude/(settings[^/\s'\"]*\.json|hooks/)"
                            r"|(^|[/\s'\"=])\.tune-up/painel(\.json|[\w.-]*/(?!dados/))")
BASH_ESCREVE = re.compile(r">|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b|\bchmod\b|\bln\b|\btouch\b|\btruncate\b")
FERR_ARQUIVO = ("Edit", "Write", "MultiEdit", "NotebookEdit")


# ---------------------------------------------------------------- validação (usada pelo catálogo)

def _regra(obj, onde):
    if not isinstance(obj.get("ferramenta"), str) or not obj["ferramenta"] or len(obj["ferramenta"]) > MAX_REGEX:
        raise ValueError("%s: regra sem 'ferramenta'" % onde)
    out = {"ferramenta": obj["ferramenta"]}
    for chave in ("ferramenta", "entrada"):
        if chave in obj:
            if not isinstance(obj[chave], str) or len(obj[chave]) > MAX_REGEX:
                raise ValueError("%s: '%s' precisa ser texto curto" % (onde, chave))
            try:
                re.compile(obj[chave])
            except re.error:
                raise ValueError("%s: regex '%s' inválida" % (onde, chave))
            out[chave] = obj[chave]
    if "campo" in obj:
        if not isinstance(obj["campo"], str) or not RE_CAMPO.match(obj["campo"]):
            raise ValueError("%s: 'campo' inválido" % onde)
        out["campo"] = obj["campo"]
    decisao = obj.get("decisao", "deny")
    if decisao not in DECISOES:
        raise ValueError("%s: 'decisao' precisa ser deny ou ask" % onde)
    out["decisao"] = decisao
    motivo = obj.get("motivo")
    out["motivo"] = (motivo if isinstance(motivo, str) and motivo.strip() else "regra da ação")[:160]
    return out


def validar_travas(acao):
    """Lê negar/permitir do JSON da ação. Devolve dict limpo ou levanta ValueError."""
    out = {"negar": [], "permitir": [], "regras_negar": [], "regras_permitir": []}
    for campo in ("negar", "permitir"):
        lista = acao.get(campo, [])
        if not isinstance(lista, list) or len(lista) > MAX_REGRAS:
            raise ValueError("'%s' precisa ser uma lista de até %d regras" % (campo, MAX_REGRAS))
        for i, item in enumerate(lista):
            onde = "%s[%d]" % (campo, i)
            if isinstance(item, str):
                if not item.strip() or len(item) > MAX_TEXTO or RE_CONTROLE.search(item):
                    raise ValueError("%s: regra de permissão inválida" % onde)
                out[campo].append(item.strip())
            elif isinstance(item, dict):
                out["regras_" + campo].append(_regra(item, onde))
            else:
                raise ValueError("%s: precisa ser texto ou objeto" % onde)
    if len(json.dumps(out, ensure_ascii=False)) > MAX_CONF:
        raise ValueError("travas grandes demais")
    return out


# ---------------------------------------------------------------- argv da sessão

def config_gancho(acao, protegidos=(), liberados=()):
    trv = acao.get("_travas") or {}
    leve = acao.get("risco") in RISCO_LEVE
    return {"v": 1, "falha": "deny" if leve else "ask", "forte": "deny" if leve else "ask",
            "prot": [p for p in protegidos if p], "lib": [p for p in liberados if p],
            "n": trv.get("regras_negar") or [], "p": trv.get("regras_permitir") or []}


def _codificar(conf):
    bruto = json.dumps(conf, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii")


def _decodificar(texto):
    conf = json.loads(base64.urlsafe_b64decode(texto.encode("ascii")).decode("utf-8"))
    if not isinstance(conf, dict) or conf.get("v") != 1:
        raise ValueError("configuração da trava inválida")
    return conf


def settings_da_sessao(acao, protegidos=(), liberados=(), python=None, este_arquivo=None):
    """Texto JSON para `--settings`. Sem segredo: só regra e o caminho deste gancho."""
    python = python or sys.executable or "python3"
    este_arquivo = este_arquivo or os.path.abspath(__file__)
    conf = config_gancho(acao, protegidos, liberados)
    comando = " ".join(shlex.quote(x) for x in (python, "-I", "-B", este_arquivo, _codificar(conf)))
    cfg = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": comando, "timeout": 15}]}]}}
    trv = acao.get("_travas") or {}
    negar = (list(NEGAR_LEVE) if acao.get("risco") in RISCO_LEVE else []) + list(trv.get("negar") or [])
    perm = {}
    if negar:
        perm["deny"] = negar
    if trv.get("permitir"):
        perm["allow"] = list(trv["permitir"])
    if perm:
        cfg["permissions"] = perm
    return json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))


def argv_travas(acao, cfg=None):
    """Pedaço do argv do `claude --bg` com as travas da ação."""
    cfg = cfg or {}
    protegidos = [cfg.get("painel_dir"), cfg.get("pacote_dir"), cfg.get("arquivo")]
    liberados = [os.path.join(cfg["pacote_dir"], "dados")] if cfg.get("pacote_dir") else []
    return ["--settings", settings_da_sessao(acao, protegidos, liberados)]


# ---------------------------------------------------------------- o gancho

def _protegido(texto, conf):
    if CAMINHO_CONFIG.search(texto):
        return True
    for p in conf.get("prot") or []:
        i = texto.find(p)
        while i >= 0:
            if not any(texto.startswith(lib, i) for lib in conf.get("lib") or []):
                return True
            i = texto.find(p, i + 1)
    return False


def _casa(regra, ferramenta, entrada):
    if not re.fullmatch(regra["ferramenta"], ferramenta):
        return False
    if "entrada" not in regra:
        return True
    if "campo" in regra:
        valor = entrada.get(regra["campo"])
        if valor is None:
            return False
        texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, sort_keys=True)
    else:
        texto = json.dumps(entrada, ensure_ascii=False, sort_keys=True)
    return re.search(regra["entrada"], texto) is not None


def decidir(conf, ferramenta, entrada):
    """(decisão, motivo) ou None quando a trava não tem nada a dizer."""
    entrada = entrada if isinstance(entrada, dict) else {}
    forte = conf.get("forte") if conf.get("forte") in DECISOES else "deny"
    if ferramenta in FERR_ARQUIVO:
        caminho = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
        if caminho and (_protegido(caminho, conf) or _protegido(os.path.normpath(caminho), conf)):
            return forte, "mexer nas regras do Claude ou do painel"
    if ferramenta == "Bash":
        cmd = entrada.get("command")
        if not isinstance(cmd, str):
            return forte, "comando ilegível"
        if _protegido(cmd, conf) and BASH_ESCREVE.search(cmd):
            return forte, "mexer nas regras do Claude ou do painel"
    for regra in conf.get("p") or []:
        if _casa(regra, ferramenta, entrada):
            return None
    for regra in conf.get("n") or []:
        if _casa(regra, ferramenta, entrada):
            return regra.get("decisao") if regra.get("decisao") in DECISOES else "deny", regra.get("motivo") or "regra"
    return None


def principal(argv, stdin, stdout):
    falha = "deny"
    try:
        conf = _decodificar(argv[1] if len(argv) > 1 else "")
        falha = conf.get("falha") if conf.get("falha") in DECISOES else "deny"
        dados = json.load(stdin)
        resposta = decidir(conf, str(dados.get("tool_name") or ""), dados.get("tool_input") or {})
    except Exception as erro:  # nunca libera no escuro
        resposta = falha, "a trava do painel falhou: " + type(erro).__name__
    if resposta:
        stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": resposta[0],
            "permissionDecisionReason": "Trava do painel: " + resposta[1]}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv, sys.stdin, sys.stdout))
