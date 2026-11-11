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
import posixpath
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
RE_UNIDADE = re.compile(r"^[A-Za-z]:")
FIM_LIB = "/\\ \t\n'\""  # depois do liberado: separador, espaço, aspas ou fim (dadosx/ não é dados/)


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

def config_gancho(acao, protegidos=(), liberados=(), perguntas_dir=None):
    trv = acao.get("_travas") or {}
    leve = acao.get("risco") in RISCO_LEVE
    conf = {"v": 1, "falha": "deny" if leve else "ask", "forte": "deny" if leve else "ask",
            "prot": [p for p in protegidos if p], "lib": [p for p in liberados if p],
            "n": trv.get("regras_negar") or [], "p": trv.get("regras_permitir") or []}
    if perguntas_dir and acao.get("_perguntas_chat"):
        conf["perg"] = perguntas_dir  # pergunta de múltipla escolha vai para o chat, não para o terminal
    return conf


def _codificar(conf):
    bruto = json.dumps(conf, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii")


def _decodificar(texto):
    conf = json.loads(base64.urlsafe_b64decode(texto.encode("ascii")).decode("utf-8"))
    if not isinstance(conf, dict) or conf.get("v") != 1:
        raise ValueError("configuração da trava inválida")
    return conf


def settings_da_sessao(acao, protegidos=(), liberados=(), python=None, este_arquivo=None, perguntas_dir=None):
    """Texto JSON para `--settings`. Sem segredo: só regra e o caminho deste gancho."""
    python = python or sys.executable or "python3"
    este_arquivo = este_arquivo or os.path.abspath(__file__)
    conf = config_gancho(acao, protegidos, liberados, perguntas_dir)
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
    perguntas = os.path.join(cfg["dados_dir"], "perguntas") if cfg.get("dados_dir") else None
    return ["--settings", settings_da_sessao(acao, protegidos, liberados, perguntas_dir=perguntas)]


# ---------------------------------------------------------------- o gancho

def _sem_caixa(texto):
    """No Windows (ou com cara de caminho do Windows) o disco não diferencia maiúsculas."""
    return os.name == "nt" or "\\" in texto or RE_UNIDADE.match(texto) is not None


def _barra(texto, sem_caixa):
    texto = texto.replace("\\", "/")
    return texto.lower() if sem_caixa else texto


def caminho_comparavel(caminho, sem_caixa):
    """Forma única de comparar caminho (o da ferramenta e os protegidos/liberados): `\\` vira `/`,
    `.` e `..` resolvidos sem o os.path da plataforma, minúsculas se o disco não diferencia."""
    return posixpath.normpath(_barra(caminho, sem_caixa))


def _liberado(texto, i, libs):
    for lib in libs:
        fim = i + len(lib)
        if texto.startswith(lib, i) and (fim == len(texto) or texto[fim] in FIM_LIB):
            return True
    return False


def _protegido(texto, conf, forma=None):
    """`forma` (opcional) normaliza protegidos e liberados do mesmo jeito que o texto."""
    if CAMINHO_CONFIG.search(texto):
        return True
    libs = [forma(x) if forma else x for x in conf.get("lib") or []]
    for p in conf.get("prot") or []:
        p = forma(p) if forma else p
        i = texto.find(p)
        while i >= 0:
            if not _liberado(texto, i, libs):
                return True
            i = texto.find(p, i + 1)
    return False


def _protegido_normal(texto, conf, comando):
    """Mesma checagem com `\\` -> `/` (e `..` resolvido se for caminho). Só soma proteção."""
    sc = _sem_caixa(texto)
    norm = _barra(texto, sc) if comando else caminho_comparavel(texto, sc)
    if _protegido(norm, conf, lambda p: caminho_comparavel(p, sc)):
        return True
    return not comando and CAMINHO_CONFIG.search(RE_UNIDADE.sub("", norm)) is not None


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
        if caminho and (_protegido(caminho, conf) or _protegido(os.path.normpath(caminho), conf)
                        or _protegido_normal(caminho, conf, False)):
            return forte, "mexer nas regras do Claude ou do painel"
    if ferramenta == "Bash":
        cmd = entrada.get("command")
        if not isinstance(cmd, str):
            return forte, "comando ilegível"
        if (_protegido(cmd, conf) or _protegido_normal(cmd, conf, True)) and BASH_ESCREVE.search(cmd):
            return forte, "mexer nas regras do Claude ou do painel"
    for regra in conf.get("p") or []:
        if _casa(regra, ferramenta, entrada):
            return None
    for regra in conf.get("n") or []:
        if _casa(regra, ferramenta, entrada):
            return regra.get("decisao") if regra.get("decisao") in DECISOES else "deny", regra.get("motivo") or "regra"
    return None


RE_SESSAO_GANCHO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
FERR_PERGUNTA = "AskUserQuestion"
MOTIVO_PERGUNTA = ("esta sessão roda no chat do painel, sem terminal. Não use AskUserQuestion: escreva a pergunta "
                   "como texto na sua resposta (com as opções numeradas, a recomendada primeiro) e TERMINE a vez. "
                   "O dono responde pelo chat e a conversa continua")


def limpar_perguntas(entrada):
    """Entrada do AskUserQuestion -> lista curta e limpa para a tela."""
    out = []
    for q in (entrada.get("questions") if isinstance(entrada, dict) else None) or []:
        if not isinstance(q, dict) or not isinstance(q.get("question"), str) or not q["question"].strip():
            continue
        opcoes = []
        for o in q.get("options") or []:
            if isinstance(o, dict) and isinstance(o.get("label"), str) and o["label"].strip():
                opcoes.append({"rotulo": o["label"].strip()[:120],
                               "descricao": str(o.get("description") or "").strip()[:300]})
        out.append({"pergunta": q["question"].strip()[:500], "cabecalho": str(q.get("header") or "").strip()[:40],
                    "multipla": q.get("multiSelect") is True, "opcoes": opcoes[:6]})
    return out[:4]


def guardar_pergunta(pasta, sessao_id, entrada):
    """Grava <pasta>/<sessionId>.json (0600, troca atômica). Falha aqui nunca libera a ferramenta."""
    perguntas = limpar_perguntas(entrada)
    if not perguntas or not isinstance(sessao_id, str) or not RE_SESSAO_GANCHO.match(sessao_id):
        return False
    try:
        os.makedirs(pasta, mode=0o700, exist_ok=True)
        tmp = os.path.join(pasta, ".%s.%d.tmp" % (sessao_id, os.getpid()))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"perguntas": perguntas}, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(pasta, sessao_id + ".json"))
        return True
    except OSError:
        return False


def esquecer_pergunta(pasta, sessao_id):
    if isinstance(sessao_id, str) and RE_SESSAO_GANCHO.match(sessao_id):
        try:
            os.unlink(os.path.join(pasta, sessao_id + ".json"))
        except OSError:
            pass


def principal(argv, stdin, stdout):
    falha = "deny"
    try:
        conf = _decodificar(argv[1] if len(argv) > 1 else "")
        falha = conf.get("falha") if conf.get("falha") in DECISOES else "deny"
        dados = json.load(stdin)
        resposta = decidir(conf, str(dados.get("tool_name") or ""), dados.get("tool_input") or {})
        if isinstance(conf.get("perg"), str) and conf["perg"]:
            if dados.get("tool_name") == FERR_PERGUNTA:
                guardar_pergunta(conf["perg"], dados.get("session_id"), dados.get("tool_input") or {})
                resposta = "deny", MOTIVO_PERGUNTA
            else:  # usou outra ferramenta: seguiu em frente, a pergunta antiga não vale mais
                esquecer_pergunta(conf["perg"], dados.get("session_id"))
    except Exception as erro:  # nunca libera no escuro
        resposta = falha, "a trava do painel falhou: " + type(erro).__name__
    if resposta:
        stdout.write(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": resposta[0],
            "permissionDecisionReason": "Trava do painel: " + resposta[1]}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv, sys.stdin, sys.stdout))
