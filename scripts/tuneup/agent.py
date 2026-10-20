"""tune-up: evento agent (subagentes e workflows) e modelo da sessão."""
import json
import os
import re
from .mensagens import msg
from .sessao import decisao_pre, log_erro
from .usuario import ler_usuario, modelo_proibido, sem_modelo

# ---------------------------------------------------------------- agent

# new names (reviewer-failures, reviewer-database, reviewer-security, plan-reviewer, with or
# without the `tune-up:` prefix) and the old ones (revisor-*, silent-failure-hunter, ...)
RE_REVISOR = re.compile(r"(revisor|reviewer|silent-failure|security-review|database-review)", re.I)


def proibidos():
    """Forbidden subagent models from user.json (default ["fable"]), lowercase."""
    return [m.strip().lower() for m in ler_usuario()[0]["forbidden_subagent_models"] if m.strip()]


RE_WF_MODELO = re.compile(r"[\"']?model[\"']?\s*[:=]\s*[`'\"]([^`'\"]*)", re.I)


def workflow_proibido(script, lista):
    """Forbidden name in a `model:` value or anywhere in the script text (token boundary)."""
    for m in RE_WF_MODELO.finditer(script):
        f = modelo_proibido(m.group(1), lista)
        if f:
            return f
    return modelo_proibido(script, lista)


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
            return None
        f = workflow_proibido(script, lista)
        if f:
            return decisao_pre("bloquear", msg("modelo_proibido", f))
        # agent(...) without model inherits the session model, as in Agent
        if len(re.findall(r"\bagent\s*\(", script)) > len(re.findall(r"\bmodel[\"']?\s*[:=]", script)):
            sm = modelo_da_sessao(d.get("transcript_path"))
            f = modelo_proibido(sm, lista) if sm else None
            if f:
                return decisao_pre("bloquear", msg("modelo_proibido_sessao", f))
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
    if not modelo:
        sm = modelo_da_sessao(d.get("transcript_path"))
        f = modelo_proibido(sm, lista) if sm else None
        if f and not m_papel and not revisor:  # an allowed role model (or opus for reviewers) replaces it
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
