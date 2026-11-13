"""tune-up: evento agent (subagentes e workflows) e modelo da sessão."""
import json
import os
import re
from .mensagens import msg
from .sessao import decisao_pre, log_erro
from .usuario import ler_usuario, modelo_proibido, sem_modelo
from .workflow import analisar, contagem, tokens, workflow_generico

# ---------------------------------------------------------------- agent

# new names (reviewer-failures, reviewer-database, reviewer-security, plan-reviewer, with or
# without the `tune-up:` prefix) and the old ones (revisor-*, silent-failure-hunter, ...)
RE_REVISOR = re.compile(r"(revisor|reviewer|silent-failure|security-review|database-review)", re.I)


def proibidos():
    """Forbidden subagent models from user.json (default ["fable"]), lowercase."""
    return [m.strip().lower() for m in ler_usuario()[0]["forbidden_subagent_models"] if m.strip()]


LIMITE_SCRIPT = 512 * 1024


RE_WF_ANTES = re.compile(r"model[\"']?\s*[:=]\s*$", re.I)


def workflow_proibido(script, lista, toks=None):
    """Forbidden name (token boundary) in a string literal. Passes: comments, and prose
    (3+ words: no model id has spaces) that is not the value of `model:`."""
    for ini, fim, t in tokens(script) if toks is None else toks:
        if t.startswith("/"):
            continue
        if len(t[1:-1].split()) >= 3 and not RE_WF_ANTES.search(script[max(0, ini - 40):ini]):
            continue
        f = modelo_proibido(t[1:-1], lista)
        if f:
            return f
    return None


def ler_script(caminho, cwd):
    """Text of a Workflow `scriptPath` (relative to the hook cwd), capped; None if unreadable."""
    try:
        p = os.path.join(cwd or "", os.path.expanduser(caminho))
        with open(p, "rb") as f:
            dados = f.read(LIMITE_SCRIPT + 1)
        return None if len(dados) > LIMITE_SCRIPT else dados.decode("utf-8", "ignore")  # too big = unreadable
    except (OSError, ValueError):
        return None


RE_TIPO = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
RAIZ_PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def modelo_frontmatter(caminho):
    try:
        with open(caminho, encoding="utf-8", errors="ignore") as f:
            linhas = f.read(8192).splitlines()
    except OSError:
        return None
    if not linhas or linhas[0].strip() != "---":
        return None
    achados = []
    for linha in linhas[1:]:
        if linha.strip() == "---":
            # only a top-level `model:` (column 0) counts; repeated, block/flow/tag/anchor values = no model
            if len(achados) != 1 or achados[0][:1] in tuple(">|[{&*!"):
                return None
            m = re.match(r"[\"']?([^\"'#\s]*)", achados[0])
            return m.group(1) or None
        m = re.match(r"model\s*:(.*)$", linha)
        if m:
            achados.append(m.group(1).strip())
    return None


def candidatos_agente(tipo, cwd):
    """Definition files of an agent type: .claude/agents walking up from cwd, ~/.claude/agents, plugin agents."""
    t = str(tipo or "").strip()
    plugin, _, nome = t.rpartition(":")
    if not RE_TIPO.match(nome) or (plugin and not RE_TIPO.match(plugin)):
        return []
    if plugin:
        try:
            with open(os.path.join(RAIZ_PLUGIN, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
                proprio = json.load(f).get("name")
        except (OSError, ValueError, AttributeError):
            proprio = None
        raiz = RAIZ_PLUGIN if plugin == proprio else os.path.join(os.path.dirname(RAIZ_PLUGIN), plugin)
        return [os.path.join(raiz, "agents", nome + ".md")]
    saida, d = [], os.path.abspath(cwd) if cwd else None
    while d:
        saida.append(os.path.join(d, ".claude", "agents", nome + ".md"))
        pai = os.path.dirname(d)
        d = pai if pai != d else None
    saida.append(os.path.join(os.path.expanduser("~"), ".claude", "agents", nome + ".md"))
    return saida


def modelo_do_agente(tipo, cwd, lista):
    """Frontmatter `model:` of the first definition found; forbidden or inherit/default does not count."""
    for c in candidatos_agente(tipo, cwd):
        if os.path.isfile(c):
            m = modelo_frontmatter(c)
            return None if sem_modelo(m) or modelo_proibido(m, lista) else m
    return None


def papel_de(subagent_type):
    t = str(subagent_type or "").strip()
    return t.split(":", 1)[1] if t.startswith("tune-up:") else t


JANELA_TRANSCRIPT = 2 * 1024 * 1024


def modelo_valido(m):
    return m if isinstance(m, str) and m.strip() and m != "<synthetic>" else None


def modelo_da_sessao(caminho):
    if not caminho or not os.path.isfile(caminho):
        return None
    with open(caminho, "rb") as f:
        f.seek(0, 2)
        tam = f.tell()
        f.seek(max(0, tam - JANELA_TRANSCRIPT))
        bloco = f.read()
    linhas = bloco.split(b"\n")
    if tam > JANELA_TRANSCRIPT:
        linhas = linhas[1:]
    for linha in reversed(linhas):
        if b'"assistant"' not in linha and b'"requestedModel"' not in linha:
            continue
        try:
            obj = json.loads(linha.decode("utf-8", "replace"))
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
        if obj.get("type") == "assistant":
            m = modelo_valido(msg.get("model"))
            if m:
                return m
        m = modelo_valido(obj.get("requestedModel")) or modelo_valido(msg.get("requestedModel"))
        if m:
            return m
    return None


def ev_agent(d, cfg):
    nome = d.get("tool_name")
    ti = d.get("tool_input")
    if not isinstance(ti, dict):
        return None
    lista = proibidos()
    if nome == "Workflow":
        script = ti.get("script")
        if not isinstance(script, str):
            caminho = ti.get("scriptPath")
            if not isinstance(caminho, str) or not caminho.strip():
                return None
            script = ler_script(caminho, d.get("cwd"))
            if script is None:
                sm = modelo_da_sessao(d.get("transcript_path"))
                f = modelo_proibido(sm, lista) if sm else None
                if f:
                    return decisao_pre("bloquear", msg("modelo_proibido_sessao", f) +
                                       " scriptPath unreadable: pass the script inline or write a literal "
                                       "model on every agent() call.")
                return None
        an = analisar(script) if len(script.encode("utf-8", "ignore")) <= LIMITE_SCRIPT else None
        f = workflow_proibido(script, lista, an and an["toks"])
        if f:
            return decisao_pre("bloquear", msg("modelo_proibido", f))
        # agent(...) without model inherits the session model, as in Agent; too big: counted raw, as before
        chamadas, modelos = contagem(an) if an else (len(re.findall(r"\bagent\s*\(", script)),
                                                     len(re.findall(r"\bmodel[\"']?\s*[:=]", script)))
        if chamadas > modelos:
            sm = modelo_da_sessao(d.get("transcript_path"))
            f = modelo_proibido(sm, lista) if sm else None
            if f:
                return decisao_pre("bloquear", msg("modelo_proibido_sessao", f))
        modo = cfg.get("workflow_generic")
        linhas = workflow_generico(script, an) if modo != "off" and an else []
        if linhas:
            return decisao_pre("bloquear" if modo == "block" else "avisar", msg(
                "workflow_generico", len(linhas), ", ".join(str(n) for n in linhas[:5])))
        return None
    if nome not in ("Agent", "Task"):
        return None
    modelo = ti.get("model")
    f = modelo_proibido(modelo, lista)
    if f:
        return decisao_pre("bloquear", msg("modelo_proibido", f))
    if sem_modelo(modelo):  # "inherit"/"default" = no model: the session model applies
        modelo = None
    modelo_l = str(modelo or "").lower()
    revisor = bool(RE_REVISOR.search(str(ti.get("subagent_type") or "")))
    # explicit Agent parameter > user.json models[role] > agent frontmatter
    papel = ler_usuario()[0]["models"].get(papel_de(ti.get("subagent_type"))) or {}
    m_papel = papel.get("model")
    if sem_modelo(m_papel) or modelo_proibido(m_papel, lista):
        m_papel = None
    sem_modelo_lido = False
    m_fm = None
    if not modelo:
        sm = modelo_da_sessao(d.get("transcript_path"))
        f = modelo_proibido(sm, lista) if sm else None
        if f and not m_papel and not revisor:
            # an allowed role model, opus for reviewers or an allowed frontmatter model replaces it
            m_fm = modelo_do_agente(ti.get("subagent_type"), d.get("cwd"), lista)
            if not m_fm:
                return decisao_pre("bloquear", msg("modelo_proibido_sessao", f))
        if not sm:
            sem_modelo_lido = True
            log_erro("agent", "session model not read (transcript %r)" % (d.get("transcript_path"),))
    novo = dict(ti)
    feitos, avisos = [], []
    if not modelo and m_papel:
        novo["model"] = m_papel
        feitos.append("model=" + m_papel)
    elif not modelo and revisor:
        novo["model"] = "opus"
        feitos.append("model=opus")
    elif m_fm:  # pin the validated frontmatter model so the run uses exactly it
        novo["model"] = m_fm
        feitos.append("model=" + m_fm)
    elif sem_modelo_lido and not revisor:  # revisor recebe model=opus acima
        avisos.append(msg("modelo_nao_lido"))
    if revisor and modelo and ("haiku" in modelo_l or "sonnet" in modelo_l):
        avisos.append(msg("revisor_opus"))
    if not ti.get("effort"):
        e = papel.get("effort") or ("high" if revisor else "medium")
        novo["effort"] = e
        feitos.append("effort=" + e)
    regra = msg("regra_revisor") if revisor else msg("regra_esforco")
    if feitos:
        ctx = [msg("preenchido", ", ".join(feitos), regra)] + avisos
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "updatedInput": novo,
                                       "additionalContext": "\n".join(ctx)}}
    if avisos:
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "additionalContext": "\n".join(avisos)}}
    return None
