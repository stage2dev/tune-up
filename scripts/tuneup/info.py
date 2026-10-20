"""tune-up: `guarda.py info` — resolved profile as JSON for the skills (never reads stdin)."""
import json
import os
import shutil
import subprocess

from .config import AQUI, carregar_config, plans_relativo
from .sessao import arquivo_perfil, log_erro
from .usuario import caminho_user_json, idioma_efetivo, ler_usuario, modelo_proibido

FERRAMENTAS = ("gh", "graphify", "uv", "node")


def toplevel(cwd):
    try:
        r = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True,
                           text=True, timeout=3, stdin=subprocess.DEVNULL)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception as e:
        log_erro("info", "git rev-parse --show-toplevel: %r" % (e,))
    return cwd


def nomes(language, override):
    caminho = os.path.join(os.path.dirname(AQUI), "templates", "names.json")
    try:
        with open(caminho, encoding="utf-8") as f:
            todos = json.load(f)
    except Exception as e:
        log_erro("info", "names.json unreadable: %r" % (e,))
        todos = {}
    out = dict(todos.get("en") or {})
    out.update(todos.get(language) or {})
    out.update(override)
    return out


def repo_git(caminho):
    if not caminho:
        return None
    real = os.path.realpath(os.path.expanduser(caminho))
    return real if os.path.exists(os.path.join(real, ".git")) else None


def montar_info(cwd=None):
    cwd = os.path.realpath(cwd or os.getcwd())
    usuario, existe = ler_usuario()
    cfg = carregar_config(cwd)
    language = idioma_efetivo(cfg)
    plans = cfg["plans_dir"] if plans_relativo(cfg.get("plans_dir")) else ".planning"  # validated
    models = {papel: m for papel, m in usuario["models"].items()
              if not modelo_proibido(m.get("model"), usuario["forbidden_subagent_models"])}
    tools = dict(usuario["tools"])
    tools.update({t: bool(shutil.which(t)) for t in FERRAMENTAS})
    catalogo = os.path.join(os.path.dirname(caminho_user_json()), "skills-catalog.md")
    return {
        "language": language,
        "owner": usuario["owner"],
        "reply_style": usuario["reply_style"],
        "names": nomes(language, usuario["names_override"]),
        "models": models,
        "forbidden_subagent_models": usuario["forbidden_subagent_models"],
        "profile_path": arquivo_perfil(cfg.get("_perfil")),
        "plans_dir": os.path.normpath(os.path.join(toplevel(cwd), plans)),
        "setup_done": existe,
        "tools": tools,
        "plugin_source": repo_git(usuario["plugin_source"]),
        "catalog_path": os.path.realpath(catalogo) if os.path.isfile(catalogo) else None,
    }


def roda_info():
    print(json.dumps(montar_info(), ensure_ascii=False))
