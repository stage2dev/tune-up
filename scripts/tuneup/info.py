"""tune-up: `guarda.py info` — resolved profile as JSON for the skills (never reads stdin)."""
import glob
import json
import os
import re
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


LIMITE_SKILLS = 200  # runs at every skill invocation: bounded work
LIMITE_BYTES = 64 * 1024
RE_ARMADILHA = re.compile(r"pitfall|armadilha", re.I)


def _valor(v):
    v = v.strip()
    return v[1:-1] if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'" else v


def _lista(v):
    """`paths` value on the key line: "" (dash list follows), inline list, or None (scalar)."""
    if not v:
        return []
    if not v.startswith("["):
        return None
    try:
        lista = json.loads(v)
    except (ValueError, RecursionError):
        lista = [_valor(x) for x in v.strip("[]").split(",")]
    return [x for x in lista if isinstance(x, str) and x] if isinstance(lista, list) else None


def frontmatter(texto):
    """Top-level keys of the `---` frontmatter, tolerant, without yaml. `paths` becomes a list."""
    linhas = texto.splitlines()
    if not linhas or linhas[0].strip() != "---":
        return {}
    out, chave = {}, None
    for linha in linhas[1:]:
        if linha.strip() == "---":
            return out
        if linha[:1] in (" ", "\t", "-"):  # continuation: dash item or folded text
            item = linha.strip()
            if chave == "paths" and isinstance(out.get("paths"), list) and item.startswith("-"):
                if _valor(item[1:]):
                    out["paths"].append(_valor(item[1:]))
            elif isinstance(out.get(chave), str):
                out[chave] = (out[chave] + " " + item).strip()
            continue
        chave, _, v = linha.partition(":")
        chave, v = chave.strip(), v.strip()
        out[chave] = _lista(v) if chave == "paths" else ("" if v in (">", "|", ">-", "|-") else _valor(v))
    return {}  # no closing `---`


def _real(arq, base, real_base):
    """realpath(arq) without resolving the whole chain per file: only the skill folder and file can
    be symlinks below the already-resolved `skills` folder; otherwise fall back to realpath."""
    pasta = os.path.dirname(arq)
    if os.path.islink(pasta) or os.path.islink(arq):
        return os.path.realpath(arq)
    return os.path.join(real_base, os.path.relpath(pasta, base), os.path.basename(arq))


def pitfall_skills():
    """Installed pitfall skills (name or description says pitfall/armadilha, with `paths`):
    [{name, path, paths}] by name; same name twice: the newest install wins. [] on any problem."""
    caminho = os.path.join(os.path.expanduser("~"), ".claude", "plugins", "installed_plugins.json")
    try:
        with open(caminho, encoding="utf-8") as f:
            plugins = json.load(f).get("plugins")
        instalacoes = [x for v in plugins.values() for x in (v if isinstance(v, list) else [v])
                       if isinstance(x, dict) and isinstance(x.get("installPath"), str)]
    except FileNotFoundError:
        return []
    except Exception as e:
        log_erro("info", "installed_plugins.json unreadable: %r" % (e,))
        return []
    instalacoes.sort(key=lambda x: str(x.get("lastUpdated") or x.get("installedAt") or ""),
                     reverse=True)  # ISO dates; stable sort keeps file order on ties
    achadas, vistos = {}, 0
    for inst in instalacoes:
        base = os.path.join(inst["installPath"], "skills")
        real_base = os.path.realpath(base)  # once per plugin, not once per skill
        for arq in sorted(glob.glob(os.path.join(glob.escape(inst["installPath"]), "skills", "*", "SKILL.md"))):
            if vistos >= LIMITE_SKILLS:
                return [achadas[n] for n in sorted(achadas)]
            vistos += 1
            try:
                with open(arq, encoding="utf-8", errors="replace") as f:
                    fm = frontmatter(f.read(LIMITE_BYTES))
            except OSError:
                continue
            nome = fm.get("name") or os.path.basename(os.path.dirname(arq))
            if not isinstance(fm.get("paths"), list) or not fm["paths"] or nome in achadas or \
                    not RE_ARMADILHA.search("%s %s" % (fm.get("name") or "", fm.get("description") or "")):
                continue
            achadas[nome] = {"name": nome, "path": _real(arq, base, real_base), "paths": fm["paths"]}
    return [achadas[n] for n in sorted(achadas)]


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
        "pitfall_skills": pitfall_skills(),
    }


def roda_info():
    print(json.dumps(montar_info(), ensure_ascii=False))
