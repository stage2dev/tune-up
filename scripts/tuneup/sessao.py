"""tune-up: dados, log de erros, sessão, saída do hook, evento de início e erros novos."""
import json
import os
import re
import sys
import time
from .caminhos import dentro  # noqa: F401  (identity-aware; re-exported)

# ---------------------------------------------------------------- dados

def dir_dados():
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(
        os.path.expanduser("~"), ".cache", "tune-up")
    return base


def criar_dir(p):
    """Pasta de dados só do usuário (0700), também a pasta-base."""
    base = dir_dados()
    if p != base and dentro(p, base):
        os.makedirs(base, mode=0o700, exist_ok=True)
    os.makedirs(p, mode=0o700, exist_ok=True)


def abrir_privado(caminho, modo):
    """open() de arquivo de dados com 0600 na criação. modo: "a" ou "w"."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_APPEND if modo == "a" else os.O_TRUNC)
    return os.fdopen(os.open(caminho, flags, 0o600), modo, encoding="utf-8")


def log_erro(evento, texto):
    try:
        d = dir_dados()
        criar_dir(d)
        with abrir_privado(os.path.join(d, "erros.log"), "a") as f:
            linha = "%s %s %s" % (time.strftime("%Y-%m-%dT%H:%M:%S"), evento, texto)
            f.write(linha.replace("\n", " ")[:2000] + "\n")
    except Exception:
        pass


def arquivo_sessao(session_id):
    sid = re.sub(r"[^A-Za-z0-9_.-]", "_", str(session_id or "sem-sessao"))
    return os.path.join(dir_dados(), "sessoes", sid + ".json")


def ler_sessao(session_id):
    caminho = arquivo_sessao(session_id)
    try:
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict):
                return d
            log_erro("sessao", "corrupted session (not an object): %s" % caminho)
    except FileNotFoundError:
        pass
    except Exception as e:
        log_erro("sessao", "corrupted session %s: %r" % (caminho, e))
    return {"auth_prompt_id": None, "modo_pesquisa": False, "atualizado": 0}


def gravar_sessao(session_id, estado):
    caminho = arquivo_sessao(session_id)
    criar_dir(os.path.dirname(caminho))
    estado["atualizado"] = int(time.time())
    tmp = "%s.%d.tmp" % (caminho, os.getpid())
    with abrir_privado(tmp, "w") as f:
        json.dump(estado, f)
    os.replace(tmp, caminho)


def limpar_sessoes_velhas():
    pasta = os.path.join(dir_dados(), "sessoes")
    limite = time.time() - 3 * 86400
    try:
        nomes = os.listdir(pasta)
    except OSError:
        return
    for nome in nomes:
        p = os.path.join(pasta, nome)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < limite:
                os.remove(p)
        except OSError:
            pass


# ---------------------------------------------------------------- saída

def emitir(obj):
    sys.stdout.write(json.dumps(obj))
    sys.stdout.write("\n")


def decisao_pre(acao, msg):
    msg = "tune-up: " + msg
    if acao == "avisar":
        return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                       "additionalContext": msg}}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny" if acao == "bloquear" else "ask",
                                   "permissionDecisionReason": msg}}


def contexto(evento, linhas):
    return {"hookSpecificOutput": {"hookEventName": evento,
                                   "additionalContext": "\n".join(linhas)}}


def arquivo_perfil(perfil):
    """`.tune-up/project.md`, or the legacy `projeto.md`; None when neither exists."""
    for nome in ("project.md", "projeto.md"):
        if perfil and os.path.isfile(os.path.join(perfil, nome)):
            return os.path.join(perfil, nome)
    return None


def ev_inicio(d, cfg):
    from .mensagens import dono, idioma, msg
    from .usuario import ler_usuario
    limpar_sessoes_velhas()
    linhas = []
    if d.get("source") == "startup":
        usuario, existe = ler_usuario()
        linhas.append(msg("inicio_linha", idioma(), dono(), usuario["reply_style"]) if existe
                      else msg("inicio_setup"))
    perfil = cfg.get("_perfil")
    md = arquivo_perfil(perfil)
    if md:
        nome = cfg.get("project") or os.path.basename(os.path.dirname(perfil))
        quem = "Claude" if cfg.get("claude_may_merge") else dono()
        linhas.append(msg("inicio_projeto", nome, md, quem))
    if d.get("source") == "compact":
        linhas.append(msg("inicio_compact"))
    sistema = []
    if cfg.get("_erro_config"):
        sistema.append(msg("cfg_invalido", cfg["_erro_config"]))
    if cfg.get("_invalidas"):
        sistema.append(msg("cfg_tipos", ", ".join(cfg["_invalidas"])))
    if ler_usuario()[0].get("invalid"):
        from .usuario import caminho_user_json
        sistema.append(msg("user_json_invalido", caminho_user_json()))
    if cfg.get("_perfil_mudou"):
        sistema.append(msg("perfil_mudou", cfg["_perfil_mudou"]))
    elif cfg.get("_nao_confiado"):
        sistema.append(msg("nao_confiado", cfg["_nao_confiado"]))
    sem_hash = aviso_sem_hash()
    if sem_hash:
        sistema.append(msg("confiaveis_sem_hash", sem_hash))
    from .escrita import caminhos_protegidos
    ignorados = caminhos_protegidos(registrar=True)[1]
    if ignorados:
        sistema.append(msg("protected_paths_ignorados", ", ".join(x for _, x in ignorados)))
    n, log = erros_novos()
    if n:
        sistema.append(msg("erros_hooks", n, log))
    linhas.extend(sistema)
    if not linhas:
        return None
    saida = contexto("SessionStart", linhas)
    if sistema:
        saida["systemMessage"] = "\n".join(sistema)
    return saida


def aviso_sem_hash():
    """Count of trust lines without a content hash, reported once (marker in the data dir)."""
    from .config import perfis_confiaveis
    n = sum(1 for h in perfis_confiaveis().values() if h is None)
    marca = os.path.join(dir_dados(), "confiaveis.sem_hash.visto")
    if not n or os.path.exists(marca):
        return 0
    try:
        with abrir_privado(marca, "w") as f:
            f.write(str(n))
    except OSError as e:
        log_erro("inicio", "could not write %s: %r" % (marca, e))
    return n


def erros_novos():
    """Linhas do erros.log depois da marca em erros.visto; atualiza a marca."""
    log = os.path.join(dir_dados(), "erros.log")
    marca = os.path.join(dir_dados(), "erros.visto")
    try:
        tam = os.path.getsize(log)
    except OSError:
        return 0, log
    try:
        with open(marca, encoding="utf-8") as f:
            visto = int(f.read().strip() or 0)
    except (OSError, ValueError):
        visto = 0
    if visto > tam:  # log foi truncado/rotacionado
        visto = 0
    if tam == visto:
        return 0, log
    with open(log, "rb") as f:
        f.seek(visto)
        n = f.read().count(b"\n")
    try:
        with abrir_privado(marca, "w") as f:
            f.write(str(tam))
    except OSError as e:
        log_erro("inicio", "could not write erros.visto: %r" % (e,))
    return n, log
