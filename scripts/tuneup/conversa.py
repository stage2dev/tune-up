"""tune-up: talk mode (/tune-up:talk) — which write targets are free, denied or asked."""
import os
from .config import plans_relativo
from .sessao import dentro

LIVRE, NEGA, PERGUNTA = "livre", "nega", "pergunta"
CODIGO = {".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash", ".zsh", ".rb", ".go",
          ".rs", ".java", ".kt", ".swift", ".c", ".h", ".cc", ".cpp", ".php", ".pl", ".lua", ".sql",
          ".vue", ".svelte", ".css", ".scss", ".html", ".ipynb"}
_TOP = {}
_TOPO_PASTA = {}  # per run: real folder -> its git toplevel (or None)


def topo(cwd):
    """git toplevel of the session cwd (fallback: cwd); one git call per run."""
    if cwd not in _TOP:
        from .info import toplevel
        _TOP[cwd] = os.path.realpath(toplevel(cwd))
    return _TOP[cwd]


def topo_do_arquivo(caminho, cwd=None):
    """git toplevel of the file's nearest existing folder, or None (not in a repo). Cached per
    folder; inside the session's top (`cwd`) it looks for `.git` going up, without git."""
    import subprocess
    p = os.path.dirname(caminho)
    while p and not os.path.isdir(p):
        p = os.path.dirname(p) if os.path.dirname(p) != p else ""
    if not p:
        return None
    p = os.path.realpath(p)
    if p in _TOPO_PASTA:
        return _TOPO_PASTA[p]
    top = topo(cwd) if isinstance(cwd, str) else None
    if top and (p == top or p.startswith(top.rstrip(os.sep) + os.sep)):
        x = p
        while not os.path.lexists(os.path.join(x, ".git")) and x != top:
            x = os.path.dirname(x)
        _TOPO_PASTA[p] = x if os.path.lexists(os.path.join(x, ".git")) else None
        return _TOPO_PASTA[p]
    from .bash import restante
    res = None
    try:
        if restante(3) > 0.1:
            r = subprocess.run(["git", "-C", p, "rev-parse", "--show-toplevel"], capture_output=True,
                               text=True, timeout=restante(3), stdin=subprocess.DEVNULL)
            if r.returncode == 0 and r.stdout.strip():
                res = os.path.realpath(r.stdout.strip())
    except Exception:
        pass
    _TOPO_PASTA[p] = res
    return res


def memoria_ou_planos(c):
    """Claude's memory (~/.claude/projects/*/memory/**) or ~/.claude/plans/**."""
    claude = os.path.join(os.path.expanduser("~"), ".claude")
    if dentro(c, os.path.join(claude, "plans")):
        return True
    projetos = os.path.join(claude, "projects")
    if dentro(c, projetos):
        partes = os.path.relpath(c, projetos).split(os.sep)
        return len(partes) >= 3 and partes[1] == "memory"
    return False


def alvo_em_conversa(caminho, d, cfg):
    """LIVRE, NEGA (code inside the project) or PERGUNTA (outside the project, not free)."""
    from .escrita import livre_em_pesquisa
    c = os.path.normpath(caminho)
    if c == "/dev/null":
        return LIVRE
    reais = {c, os.path.realpath(c)}
    scratch = d.get("scratchpad_dir")
    if all((scratch and dentro(x, scratch)) or memoria_ou_planos(x) for x in reais):  # symlink: real too
        return LIVRE
    top = topo_do_arquivo(c, d.get("cwd")) or topo(d.get("cwd") or os.getcwd())  # the file's repo first
    plans = cfg.get("plans_dir") if cfg.get("_confiado") else None
    plans = plans if isinstance(plans, str) and plans_relativo(plans) else ".planning"
    livres = [os.path.join(top, "docs"), os.path.join(top, ".tune-up"), os.path.normpath(os.path.join(top, plans))]
    for x in reais:
        if dentro(x, top):
            if x.endswith(".md") and any(dentro(x, r) for r in livres):
                return LIVRE
            codigo = os.path.splitext(x)[1].lower() in CODIGO  # talk never frees code, not even in .planning
            return LIVRE if not codigo and livre_em_pesquisa(c, d, cfg) else NEGA
    return LIVRE if livre_em_pesquisa(c, d, cfg) else PERGUNTA
