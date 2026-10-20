"""tune-up: line limit per code file (Write/Edit/MultiEdit), computed in memory."""
import fnmatch
import os
import re
from .mensagens import msg
from .sessao import decisao_pre, log_erro

PADRAO = 450
MAX_BYTES = 5 * 1024 * 1024
CODIGO = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".java", ".kt",
          ".rb", ".php", ".vue", ".svelte", ".css", ".scss"}
PASTAS_FORA = {"dist", "build", "vendor", "node_modules", "migrations", "seeds", "__snapshots__"}
RE_ALLOW = re.compile(r"tune-up: allow-long[ \t]+\S")


class _SemDecisao(Exception):
    pass


def conta(texto):
    """Same count as `wc -l`, plus a last line without a trailing newline."""
    n = texto.count("\n")
    return n + 1 if texto and not texto.endswith("\n") else n


def _raiz(cfg):
    p = cfg.get("_perfil")
    return os.path.dirname(os.path.realpath(p)) if p else None


def conta_codigo(caminho, cfg):
    """True when the file counts: code extension and not on any exclusion list."""
    base = os.path.basename(caminho)
    _, ext = os.path.splitext(base)
    if ext.lower() not in CODIGO:
        return False
    if base.endswith(".d.ts") or ".generated." in base or ".min." in base:
        return False
    if PASTAS_FORA & set(caminho.replace(os.sep, "/").split("/")[:-1]):
        return False
    raiz = _raiz(cfg)
    extras = cfg.get("line_limit_exclude") or []
    if raiz and extras:
        for c in {caminho, os.path.realpath(caminho)}:
            rel = os.path.relpath(c, raiz).replace(os.sep, "/")
            if rel.startswith("../"):
                continue
            if any(fnmatch.fnmatch(rel, g) for g in extras if isinstance(g, str)):
                return False
    return True


def _ler(caminho):
    """Current text (read once) or None if the file does not exist. Raises _SemDecisao on
    binary, huge or unreadable files."""
    try:
        if not os.path.isfile(caminho):
            if os.path.exists(caminho):
                raise _SemDecisao()
            return None
        if os.path.getsize(caminho) > MAX_BYTES:
            raise _SemDecisao()
        with open(caminho, "rb") as f:
            dados = f.read()
    except OSError:
        raise _SemDecisao()
    if b"\0" in dados:
        raise _SemDecisao()
    try:
        return dados.decode("utf-8")
    except UnicodeDecodeError:
        raise _SemDecisao()


def _aplica(texto, ed):
    velho, novo = ed.get("old_string"), ed.get("new_string")
    if not isinstance(velho, str) or not isinstance(novo, str):
        raise _SemDecisao()
    if texto is None:  # Edit with empty old_string creates the file
        if velho:
            raise _SemDecisao()
        return novo
    if velho not in texto and "\r\n" in texto:  # CRLF file (Windows), old_string with \n: same lines
        texto, velho, novo = (x.replace("\r\n", "\n") for x in (texto, velho, novo))
    if not velho or velho not in texto:
        raise _SemDecisao()
    return texto.replace(velho, novo) if ed.get("replace_all") else texto.replace(velho, novo, 1)


def antes_depois(d, caminho):
    """(old text or None, resulting text). Raises _SemDecisao when nothing can be decided."""
    ti = d.get("tool_input") or {}
    ferramenta = d.get("tool_name")
    if ferramenta == "Write":
        novo = ti.get("content")
        if not isinstance(novo, str) or len(novo) > MAX_BYTES:
            raise _SemDecisao()
        try:
            if os.path.isfile(caminho) and os.path.getsize(caminho) > MAX_BYTES:
                raise _SemDecisao()
        except OSError:
            raise _SemDecisao()
        return _ler(caminho), novo
    if ferramenta == "Edit":
        edicoes = [ti]
    elif ferramenta == "MultiEdit" and isinstance(ti.get("edits"), list):
        edicoes = ti["edits"]
    else:
        raise _SemDecisao()
    velho = _ler(caminho)
    texto = velho
    for ed in edicoes:
        if not isinstance(ed, dict):
            raise _SemDecisao()
        texto = _aplica(texto, ed)
    return velho, texto


def limite(cfg):
    v = cfg.get("line_limit", PADRAO)
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 50 else PADRAO


def checar_linhas(d, caminho, cfg, alvo):
    """deny (new file or was <= limit and goes over), warn (was over and grows) or None."""
    if not conta_codigo(caminho, cfg):
        return None
    try:
        velho, novo = antes_depois(d, caminho)
    except _SemDecisao:
        return None
    lim = limite(cfg)
    n = conta(novo)
    if n <= lim or RE_ALLOW.search("\n".join(novo.split("\n", 5)[:5])):
        return None
    if velho is None:
        return decisao_pre("bloquear", msg("linhas_nega", alvo, n, lim))
    antes = conta(velho)
    if antes <= lim:
        return decisao_pre("bloquear", msg("linhas_nega", alvo, n, lim))
    if n > antes:
        return decisao_pre("avisar", msg("linhas_avisa", alvo, antes, n, lim))
    return None


def checar_seguro(d, caminho, cfg, alvo):
    try:
        return checar_linhas(d, caminho, cfg, alvo)
    except Exception as e:
        log_erro("linhas", "%s: %s" % (type(e).__name__, e))
        return None
