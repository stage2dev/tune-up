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

Proteção fixa do núcleo (toda ação): mexer em .claude/settings*.json, .claude/hooks|skills|plugins,
CLAUDE.md, .mcp.json, no painel.json, no núcleo ou no pacote do painel (menos <pacote>/dados/) nega
em ação de risco leitura/rascunho e pergunta em código/crédito. No Bash de leitura/rascunho, só
verbo de leitura conhecido pode citar essas árvores. Ação com Bash no `permitir`: comando composto,
código inline, heredoc ou script é negado antes do `permitir`. Se o gancho falhar: nega em
leitura/rascunho, pergunta no resto; se o processo nem rodar, sai com 2 (bloqueia).
Deny de gancho vence o "allow" de outro gancho.
Python 3.9, só biblioteca padrão; o gancho não importa nada do painel.
"""
import base64
import json
import os
import posixpath
import re
import shlex
import sys
import unicodedata

RISCO_LEVE = ("leitura", "rascunho")
DECISOES = ("deny", "ask")
NEGAR_LEVE = ["Edit(**/.claude/settings*.json)", "Write(**/.claude/settings*.json)",
              "MultiEdit(**/.claude/settings*.json)"]
_CONFIG = (r"(?i)(^|[/\s'\"=])\.claude/(settings[^/\s'\"]*\.json|(hooks|skills|plugins)\b)"
           r"|(^|[/\s'\"=])(claude(\.local)?\.md|\.mcp\.json)($|[/\s'\";|&)<>])"
           r"|(^|[/\s'\"=])\.tune-up/painel(\.json|[\w.-]*/%s)")
# <pacote>/dados/ fica de fora, menos o que é do dono; com `..` no Bash, a exceção `dados/` não vale
CAMINHO_CONFIG = re.compile(_CONFIG % r"((?!dados/)|dados/(estudio-dono\.json|aprovados)\b)")
CAMINHO_CONFIG_PP = re.compile(_CONFIG % "")
BASH_ESCREVE = re.compile(r">|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b|\bchmod\b|\bln\b|\btouch\b|\btruncate\b")
# Bash por texto: o que mais escreve (verbo no início do comando, heredoc, find -delete...).
BASH_ESCREVE_MAIS = re.compile(r"(?i)<<|\s-(delete|exec|execdir|ok)\b|\bsort\b[^;|&]*\s-o|\b(perl|ruby)\b[^;|&]*\s-\w*i")
INTERPRETES = {"python", "py", "node", "perl", "ruby", "php", "bash", "sh", "zsh", "dash", "ksh", "fish", "pwsh",
               "powershell", "cmd", "deno", "bun", "osascript", "source", "."}
VERBOS_ESCRITA = INTERPRETES | {
    "dd", "install", "rsync", "unlink", "mkdir", "rmdir", "patch", "xargs", "copy", "xcopy", "robocopy", "move",
    "del", "erase", "ren", "rename", "rd", "md", "set-content", "add-content", "out-file", "remove-item",
    "copy-item", "move-item", "new-item", "rename-item", "sudo", "doas", "env", "eval", "exec", "git", "tar",
    "unzip", "ditto", "scp", "curl", "wget"}
VERBOS_LEITURA = {"cat", "ls", "head", "tail", "grep", "egrep", "fgrep", "rg", "wc", "stat", "file", "du", "diff",
                  "cmp", "less", "more", "type", "dir", "findstr", "pwd", "cd", "echo", "printf", "test", "true",
                  "realpath", "readlink", "basename", "dirname", "tree", "jq", "md5", "md5sum", "shasum",
                  "sha256sum", "get-content", "get-childitem"}
SEP_BASH = re.compile(r"&&|\|\||\$\(|[;&|\n(){}`]")
META_BASH = re.compile(r";|&&|\|\||\||\$\(|`|<<|[<>]\(|\n|(?<![<>])&(?!>)")
CURINGA = re.compile(r"[*?\[{$`]")
NOMES_CONFIG = (".claude", ".tune-up", "claude.md", "claude.local.md", ".mcp.json")
DONO = ("estudio-dono.json", "aprovados", "extensoes.json")  # em <dados>: só o servidor grava (sandbox.DONO)
# escrita que cita esses nomes em qualquer caminho: `cd <dados> && echo > estudio-dono.json` não passa
RE_DONO = re.compile(r"(?i)(^|[/\s'\"=<>;|&()])(%s)($|[/\s'\";|&)<>])" % "|".join(re.escape(n) for n in DONO))
PONTO_PONTO = re.compile(r"(^|[/\s'\"=])\.\.($|[/\s'\";|&)<>])")
FERR_ARQUIVO = ("Edit", "Write", "MultiEdit", "NotebookEdit")
RE_UNIDADE = re.compile(r"^[A-Za-z]:")
FIM_LIB = "/\\ \t\n'\""  # depois do liberado: separador, espaço, aspas ou fim (dadosx/ não é dados/)
# com sandbox o QA confia nos relatórios que o hyperframes grava em <fonte>/.hyperframes/: Write/Edit não
# grava lá (o Bash do hyperframes grava). `.hyperframes.` e `.hyperframes ` são a mesma pasta no Windows.
# Pelo gancho, não por regra: `Write(**/.hyperframes/**)` não barrou o Write numa sessão real; `Edit(...)`
# barra, mas o Claude Code soma regra Edit de deny ao denyWrite do sandbox e calaria o próprio hyperframes.
RE_HF = re.compile(r"(^|/)\.hyperframes[. ]*(/|$)")
MOTIVO_HF = "relatório do hyperframes (.hyperframes/) só o próprio hyperframes grava"


def _dobrado(texto):
    """NFKC + casefold antes de casar RE_HF/RE_DONO: o APFS dobra a caixa e `.hyperframeſ` (U+017F) cai em
    `.hyperframes`; `(?i)` do re não dobra ligadura (`ﬆ` = `st`). Só soma proteção."""
    return unicodedata.normalize("NFKC", texto).casefold()


# ---------------------------------------------------------------- argv da sessão

def config_gancho(acao, protegidos=(), liberados=(), perguntas_dir=None):
    trv = acao.get("_travas") or {}
    leve = acao.get("risco") in RISCO_LEVE
    bash = (any(re.match(r"Bash(\(|$)", r) for r in trv.get("permitir") or [])
            or any(re.fullmatch(r["ferramenta"], "Bash") for r in trv.get("regras_permitir") or []))
    conf = {"v": 1, "falha": "deny" if leve else "ask", "forte": "deny" if leve else "ask",
            "leve": leve, "bash": bash, "sb": bool(acao.get("sandbox")),
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


def settings_da_sessao(acao, protegidos=(), liberados=(), python=None, este_arquivo=None, workspace="", dados="",
                       perguntas_dir=None):
    """Texto JSON para `--settings`. Sem segredo: só regra, o caminho deste gancho e o bloco `sandbox`/`env`."""
    python = python or sys.executable or "python3"
    este_arquivo = este_arquivo or os.path.abspath(__file__)
    conf = config_gancho(acao, protegidos, liberados, perguntas_dir)
    comando = " ".join(shlex.quote(x) for x in (python, "-I", "-B", este_arquivo, _codificar(conf)))
    comando += " || exit 2"  # python ausente ou quebrado: código 2 bloqueia a chamada (não deixa passar)
    cfg = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": comando, "timeout": 15}]}]}}
    trv = acao.get("_travas") or {}
    import sandbox  # aqui dentro: o gancho roda com -I e não importa nada do painel
    topo, negar_sb, perm = sandbox.bloco(acao, workspace, dados)
    negar = (list(NEGAR_LEVE) if acao.get("risco") in RISCO_LEVE else []) + list(trv.get("negar") or [])
    negar += [r for r in negar_sb if r not in negar]
    if negar:
        perm["deny"] = negar
    if trv.get("permitir"):
        perm["allow"] = list(trv["permitir"])
    if perm:
        cfg["permissions"] = perm
    cfg.update(topo)
    return json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))


def argv_travas(acao, cfg=None):
    """Pedaço do argv do `claude --bg` com as travas da ação."""
    cfg = cfg or {}
    protegidos = [cfg.get("painel_dir"), cfg.get("pacote_dir"), cfg.get("arquivo")]
    liberados = [os.path.join(cfg["pacote_dir"], "dados")] if cfg.get("pacote_dir") else []
    dados = cfg.get("dados_dir") or ""  # estes saem da exceção `dados`: só o servidor grava
    import sandbox
    protegidos += [os.path.join(dados, x) for x in sandbox.DONO] if dados else []
    perguntas = os.path.join(dados, "perguntas") if dados else None
    return ["--settings", settings_da_sessao(acao, protegidos, liberados, workspace=cfg.get("workspace") or "",
                                             dados=dados, perguntas_dir=perguntas)]


# ---------------------------------------------------------------- o gancho

def _sem_caixa(texto):
    """No Windows e no macOS (ou com cara de caminho do Windows) o disco não diferencia maiúsculas."""
    return os.name == "nt" or sys.platform == "darwin" or "\\" in texto or RE_UNIDADE.match(texto) is not None


def _barra(texto, sem_caixa):
    texto = texto.replace("\\", "/")
    return texto.lower() if sem_caixa else texto


def caminho_comparavel(caminho, sem_caixa):
    """Forma única de comparar caminho (o da ferramenta e os protegidos/liberados): `\\` vira `/`,
    `.` e `..` resolvidos sem o os.path da plataforma, minúsculas se o disco não diferencia."""
    return posixpath.normpath(_barra(caminho, sem_caixa))


def _liberado(texto, i, libs):
    """No Windows `\\` e `/` são o mesmo separador e o disco não diferencia caixa: o liberado vem de
    os.path.join (`...\\dados`) e o caminho da ferramenta pode vir com `/` (ou o contrário)."""
    for lib in libs:
        fim = i + len(lib)
        igual = texto.startswith(lib, i) or os.name == "nt" and _barra(texto[i:fim], True) == _barra(lib, True)
        if igual and (fim == len(texto) or texto[fim] in FIM_LIB):
            return True
    return False


def _protegido(texto, conf, forma=None, sem_lib=False):
    """`forma` (opcional) normaliza protegidos e liberados do mesmo jeito que o texto."""
    if (CAMINHO_CONFIG_PP if sem_lib else CAMINHO_CONFIG).search(texto):
        return True
    libs = [] if sem_lib else [forma(x) if forma else x for x in conf.get("lib") or []]
    for p in conf.get("prot") or []:
        p = forma(p) if forma else p
        libs_p = [lib for lib in libs if not p.startswith(lib)]  # protegido dentro do liberado vale
        i = texto.find(p)
        while i >= 0:
            if not _liberado(texto, i, libs_p):
                return True
            i = texto.find(p, i + 1)
    return False


def _bash_comparavel(cmd, sc, escape=False):
    """Comando com aspas tiradas ("/a"'b' = /ab), `\\` -> `/` (escape=True: `\\x` -> `x`, como o shell POSIX lê),
    `/./` e `//` no meio da palavra colapsados."""
    t = re.sub(r"[\"']", "", cmd)
    t = _barra(re.sub(r"\\(.)", r"\1", t) if escape else t, sc)
    t = re.sub(r"/\.(?=/)", "", t)
    return re.sub(r"(?<=[^\s=<>;|&(])/{2,}", "/", t)


def _disfarcado(norm, conf, forma):
    """Palavra com curinga ou variável que o shell pode expandir para dentro de uma árvore protegida."""
    prots = [forma(p) for p in conf.get("prot") or []]
    for tok in re.split(r"[\s=<>;|&()]+", norm):
        m = CURINGA.search(tok)
        if not m:
            continue
        fixo = tok[:m.start()]
        if tok[m.start()] in "$`" and "/" in tok[m.start():]:
            return True  # $X/y, `pwd`/y: o shell decide o caminho
        if (fixo.startswith("/") or RE_UNIDADE.match(fixo)) and any(p.startswith(fixo) for p in prots):
            return True
        ultimo = fixo.rsplit("/", 1)[-1].lower()
        if (ultimo and any(n.startswith(ultimo) for n in NOMES_CONFIG + DONO)) or re.search(
                r"(?i)\.(claude|tune-up)/", fixo):
            return True
    return False


def _resolvidos(norm, cwd, sc):
    """Cada palavra relativa resolvida contra o cwd da sessão (`../../x` a partir de {trabalho})."""
    base = caminho_comparavel(cwd, sc)
    return " ".join(posixpath.normpath(posixpath.join(base, tok)) for tok in re.split(r"[\s=<>;|&()]+", norm)
                    if tok and not tok.startswith(("/", "-", "~", "$")) and not RE_UNIDADE.match(tok))


def _protegido_normal(texto, conf, comando, cwd=""):
    """Mesma checagem com `\\` -> `/` (e `..` resolvido se for caminho). Só soma proteção.
    No Bash: aspas, `//`, `/./`, escape `\\x` e curinga/variável não disfarçam; com `..` a exceção `dados`
    não vale; palavra relativa também é conferida resolvida contra o cwd da sessão (se veio)."""
    sc = _sem_caixa(texto) or _sem_caixa(cwd)
    forma = lambda p: caminho_comparavel(p, sc)  # noqa: E731
    if not comando:
        norm = caminho_comparavel(texto, sc)
        return (_protegido(norm, conf, forma) or CAMINHO_CONFIG.search(RE_UNIDADE.sub("", norm)) is not None
                or RE_DONO.search(_dobrado(norm)) is not None)
    for norm in {_bash_comparavel(texto, sc), _bash_comparavel(texto, sc, escape=True)}:
        pp = PONTO_PONTO.search(norm) is not None
        if (_protegido(norm, conf, forma, sem_lib=pp) or _disfarcado(norm, conf, forma)
                or RE_DONO.search(_dobrado(norm))
                or cwd and _protegido(_resolvidos(norm, cwd, sc), conf, forma,
                                      sem_lib=pp and re.search(r"\b(cd|pushd)\b", norm))):
            return True
    return False


def _verbos(cmd):
    """Primeira palavra de cada comando (pula VAR=valor), em minúsculas, sem pasta, `.exe` nem versão."""
    out = []
    for seg in SEP_BASH.split(cmd):
        for w in seg.split():
            w = w.strip("\"'")
            if re.match(r"^[A-Za-z_]\w*=", w):
                continue
            v = posixpath.basename(w.replace("\\", "/")).lower()
            v = re.sub(r"^(python|node|perl|ruby|php|pwsh)[\d.]*$", r"\1", re.sub(r"\.exe$", "", v))
            out.append((w, v))
            break
    return out


def _escreve(cmd, verbos):
    return bool(BASH_ESCREVE.search(cmd) or BASH_ESCREVE_MAIS.search(cmd)
                or any(v in VERBOS_ESCRITA for _, v in verbos))


def _composto_ou_script(cmd, verbos):
    """Metacaractere de shell, código inline, heredoc ou script executado (gravado antes ou não)."""
    return bool(META_BASH.search(cmd)) or any(
        v in INTERPRETES or w.startswith(("./", ".\\", "/", "~")) or RE_UNIDADE.match(w)
        or re.search(r"(?i)\.(sh|bash|zsh|py|js|mjs|pl|rb|php|ps1|bat|cmd)$", w) for w, v in verbos)


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


def _em_hyperframes(caminho, cwd):
    """Pelo texto (`..` resolvido, sem caixa) e pelo caminho real (link simbólico para dentro também vale)."""
    alvos = [caminho]
    try:
        alvos.append(os.path.realpath(os.path.join(cwd if isinstance(cwd, str) else "", caminho)))
    except (OSError, ValueError):
        pass
    return any(RE_HF.search(caminho_comparavel(_dobrado(a), True)) for a in alvos)


def decidir(conf, ferramenta, entrada, cwd=""):
    """(decisão, motivo) ou None quando a trava não tem nada a dizer. `cwd`: o da sessão (entrada do gancho)."""
    entrada = entrada if isinstance(entrada, dict) else {}
    forte = conf.get("forte") if conf.get("forte") in DECISOES else "deny"
    if ferramenta in FERR_ARQUIVO:
        caminho = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
        if caminho and conf.get("sb") and _em_hyperframes(caminho, cwd):
            return "deny", MOTIVO_HF  # nem "ask": o dono não deve aprovar relatório forjado
        if caminho and (_protegido(caminho, conf) or _protegido(os.path.normpath(caminho), conf)
                        or _protegido_normal(caminho, conf, False)):
            return forte, "mexer nas regras do Claude ou do painel"
    if ferramenta == "Bash":
        cmd = entrada.get("command")
        if not isinstance(cmd, str):
            return forte, "comando ilegível"
        verbos = _verbos(cmd)
        # leitura/rascunho: só verbo de leitura conhecido pode citar árvore protegida
        if (_protegido(cmd, conf) or _protegido_normal(cmd, conf, True, cwd if isinstance(cwd, str) else "")) and (
                _escreve(cmd, verbos) or conf.get("leve") and any(v not in VERBOS_LEITURA for _, v in verbos)):
            return forte, "mexer nas regras do Claude ou do painel"
        if conf.get("bash") and _composto_ou_script(cmd, verbos):  # antes do `permitir`: nada o cala
            return "deny", "comando composto, código inline ou script numa ação com Bash liberado"
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
        resposta = decidir(conf, str(dados.get("tool_name") or ""), dados.get("tool_input") or {},
                           dados.get("cwd") or "")
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
