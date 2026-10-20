"""tune-up: perfil do projeto, confiáveis, validação e carga do config."""
import json
import os
import re
from .mensagens import msg
from .sessao import abrir_privado, criar_dir, dentro, dir_dados, log_erro


AQUI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scripts/, onde fica o padrao.json
TESTE = os.environ.get("TUNEUP_TESTE") == "1"
SEVERIDADE = {"bloquear": 3, "perguntar": 2, "avisar": 1}
LISTAS_SOMAM = ("bash_rules", "free_repos")
# old Portuguese keys accepted as aliases of the English ones (applied before the trust filter)
ALIASES = {"branch_principal": "main_branches", "merge_pelo_claude": "claude_may_merge",
           "commit_na_principal": "commit_on_main", "raizes_sincronizadas": "synced_roots",
           "repos_livres": "free_repos", "caminhos_livres_modo_pesquisa": "research_free_paths",
           "frases_autorizacao": "auth_phrases", "frases_pesquisa_liga": "research_on_phrases",
           "frases_pesquisa_desliga": "research_off_phrases", "regras_bash": "bash_rules",
           "projeto": "project"}


# ---------------------------------------------------------------- config

AFROUXAM = ("claude_may_merge", "commit_on_main", "main_branches", "synced_roots",
            "free_repos", "research_free_paths", "supabase_guard", "line_limit",
            "line_limit_exclude")
RE_QUANT_ANINHADO = re.compile(r"\([^)]*[+*][^)]*\)[+*{]")
LIMITE_TEXTO = 120


_HOME_REAL = {}


def home_real():
    h = os.path.expanduser("~")
    if h not in _HOME_REAL:
        _HOME_REAL[h] = os.path.realpath(h)
    return _HOME_REAL[h]


_PERFIL = {}  # per run


def achar_perfil(cwd):
    """Pasta `.tune-up` do projeto: $CLAUDE_PROJECT_DIR, senão sobe de cwd até $HOME.
    Nunca sobe acima do HOME; fora do HOME não lê. Uma busca por cwd em cada execução."""
    chave = (cwd, os.environ.get("CLAUDE_PROJECT_DIR"), os.path.expanduser("~"))
    if chave not in _PERFIL:
        _PERFIL[chave] = _achar_perfil(cwd)
    return _PERFIL[chave]


def _achar_perfil(cwd):
    home = home_real()
    proj = os.environ.get("CLAUDE_PROJECT_DIR")
    if proj:
        proj = os.path.realpath(proj)
        if dentro(proj, home) and os.path.isdir(os.path.join(proj, ".tune-up")):
            return os.path.join(proj, ".tune-up")
    d = os.path.realpath(cwd or os.getcwd())
    if not dentro(d, home):
        return None
    while True:
        cand = os.path.join(d, ".tune-up")
        if os.path.isdir(cand):
            return cand
        if d == home:
            return None
        pai = os.path.dirname(d)
        if pai == d:
            return None
        d = pai


def arquivo_seguro(caminho):
    """Dono = usuário atual e sem escrita para grupo/outros.
    Windows: não há uid nem bits de modo (os.stat devolve uid 0 e 0o666), e as ACLs não são
    lidas. Vale só arquivo ou pasta cujo caminho real fica dentro do perfil do usuário, cuja ACL
    padrão só deixa o próprio usuário (mais SYSTEM e Administradores) gravar."""
    st = os.stat(caminho)
    if os.name == "nt":
        import stat
        return (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)) and \
            dentro(os.path.realpath(caminho), home_real())
    return st.st_uid == os.getuid() and not st.st_mode & 0o022


def arquivo_confiaveis():
    return os.path.join(dir_dados(), "perfis_confiaveis.txt")


RE_SHA = re.compile(r"[0-9a-f]{64}")


def sha256(dados):
    import hashlib
    return hashlib.sha256(dados).hexdigest()


def perfis_confiaveis():
    """{real path: sha256 of the trusted content, or None (old line without hash)}.
    Each line is `path<TAB>sha256`; the last line of a path wins."""
    p = arquivo_confiaveis()
    out = {}
    try:
        if not arquivo_seguro(p):
            log_erro("config", "perfis_confiaveis.txt has wrong owner or permissions: %s" % p)
            return out
        with open(p, encoding="utf-8") as f:
            for linha in f:
                linha = linha.rstrip("\r\n")
                if not linha.strip():
                    continue
                caminho, tab, h = linha.rpartition("\t")
                if not tab:
                    caminho, h = linha.strip(), ""
                out[caminho] = h if RE_SHA.fullmatch(h) else None
    except OSError:
        pass
    return out


def confiar(caminho):
    """Trust this exact content: editing the config later drops the trust."""
    real = os.path.realpath(os.path.expanduser(caminho))
    if not os.path.isfile(real):
        print(msg("confiar_nao_existe", real))
        return
    with open(real, "rb") as f:
        h = sha256(f.read())
    if perfis_confiaveis().get(real) != h:
        criar_dir(dir_dados())
        with abrir_privado(arquivo_confiaveis(), "a") as f:
            f.write("%s\t%s\n" % (real, h))
    print(msg("confiar_ok", real))


def texto_curto(v):
    return re.sub(r"[\r\n]+", " ", str(v))[:LIMITE_TEXTO]


def regras_validas(regras, invalidas=None):
    out = []
    for r in regras if isinstance(regras, list) else []:
        rx = r.get("regex") if isinstance(r, dict) else None
        if not isinstance(rx, str) or len(rx) > 300 or RE_QUANT_ANINHADO.search(rx):
            log_erro("config", "bash_rules rule discarded (long, nested or invalid regex): %r"
                     % (str(rx)[:80],))
            if invalidas is not None:
                invalidas.add("bash_rules")
            continue
        if r.get("acao", "avisar") not in SEVERIDADE or not isinstance(r.get("msg", ""), str):
            log_erro("config", "bash_rules rule discarded (acao not in avisar|perguntar|bloquear "
                     "or msg is not text): %r" % (str(rx)[:80],))
            if invalidas is not None:
                invalidas.add("bash_rules")
            continue
        r = dict(r)
        if "msg" in r:
            r["msg"] = texto_curto(r["msg"])
        out.append(r)
    return out


LISTAS_STR = ("main_branches", "synced_roots", "free_repos", "research_free_paths")
BOOLS = ("claude_may_merge", "commit_on_main", "supabase_guard")
TEXTOS = ("project", "language", "plans_dir")


def com_aliases(dados):
    """Old PT key -> EN key. If both are present, the EN key wins. `prod_supabase` is dropped."""
    out = {}
    for k, v in dados.items():
        if k == "prod_supabase":
            continue
        en = ALIASES.get(k, k)
        if en != k and en in dados:
            continue
        out[en] = v
    return out


def tipos_validos(dados, origem, invalidas):
    """Descarta (com log) chave de tipo errado. `main_branches` em texto vira lista."""
    out = {}
    for k, v in com_aliases(dados).items():
        if k == "main_branches" and isinstance(v, str):
            v = [v]
        lista = k in LISTAS_STR or k.endswith("_phrases")
        ok = True
        if lista:
            ok = isinstance(v, list) and all(isinstance(x, str) for x in v)
        elif k in BOOLS:
            ok = isinstance(v, bool)
        elif k in TEXTOS:
            ok = isinstance(v, str)
        elif k == "bash_rules":
            ok = isinstance(v, list)
        elif k == "line_limit":
            ok = isinstance(v, int) and not isinstance(v, bool)
        elif k == "line_limit_exclude":
            ok = isinstance(v, list) and all(isinstance(x, str) for x in v)
        if not ok:
            log_erro("config", "key %s discarded in %s (wrong type: %s)"
                     % (k, origem, type(v).__name__))
            invalidas.add(k)
            continue
        out[k] = v
    return out


def ler_config_projeto(perfil):
    """(dict, erro, confiado). `confiado`: True only when the trusted hash matches the content;
    "mudou" (edited after trust) or "sem_hash" (old line) count as not trusted. Config fora do HOME, de outro dono ou gravável por
    grupo/outros é ignorada inteira."""
    caminho = os.path.join(perfil, "config.json")
    if not os.path.exists(caminho):
        return {}, None, False
    real = os.path.realpath(caminho)
    if not dentro(real, home_real()) or not arquivo_seguro(real) or \
            not arquivo_seguro(os.path.dirname(real)):
        log_erro("config", "config.json ignored (outside HOME, other owner or writable by "
                 "group/others): %s" % real)
        return {}, None, False
    try:
        with open(real, "rb") as f:
            dados = f.read()  # one read: the hash and the parsed JSON are the same bytes
        proj = json.loads(dados.decode("utf-8"))
        if not isinstance(proj, dict):
            raise ValueError("not a JSON object")
    except Exception as e:
        erro = "%s: %s" % (type(e).__name__, e)
        log_erro("config", "project config.json invalid (%s): %s" % (caminho, erro))
        return {}, erro, False
    confiaveis = perfis_confiaveis()
    if real not in confiaveis:
        return proj, None, False
    h = confiaveis[real]
    return proj, None, True if h == sha256(dados) else ("sem_hash" if h is None else "mudou")


RE_PLANS = re.compile(r"[A-Za-z0-9._/-]{1,%d}" % LIMITE_TEXTO)


def plans_relativo(p):
    """Valid `plans_dir`: relative, only [A-Za-z0-9._/-], no `..` segment, not the repo root."""
    if not isinstance(p, str) or not RE_PLANS.fullmatch(p) or p.startswith("/"):
        return False
    partes = [x for x in p.split("/") if x not in ("", ".")]
    return bool(partes) and ".." not in partes


def carregar_config(cwd):
    erro_proj = None
    nao_confiado = mudou = None
    invalidas = set()
    try:
        with open(os.path.join(AQUI, "padrao.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise ValueError("not a JSON object")
        cfg = tipos_validos(cfg, "padrao.json", invalidas)
    except Exception as e:
        log_erro("config", "padrao.json invalid: %r" % (e,))
        cfg = {}
    cfg.setdefault("main_branches", ["main", "master"])
    perfil = achar_perfil(cwd if isinstance(cwd, str) else None)
    confiado = False
    if perfil:
        proj, erro_proj, confiado = ler_config_projeto(perfil)
        if confiado == "mudou":
            mudou = os.path.realpath(os.path.join(perfil, "config.json"))
        confiado = confiado is True
        esperado = os.path.join(os.path.realpath(os.path.dirname(perfil)), ".tune-up", "config.json")
        if confiado and os.path.realpath(os.path.join(perfil, "config.json")) != esperado:
            confiado = False  # a symlinked .tune-up (or config.json) does not inherit trust
            log_erro("config", "profile not trusted: %s is a symlink to %s" % (
                esperado, os.path.realpath(os.path.join(perfil, "config.json"))))
        proj = tipos_validos(proj, os.path.join(perfil, "config.json"), invalidas)
        for k, v in proj.items():
            if not confiado and (k in AFROUXAM or k.endswith("_phrases")):
                nao_confiado = os.path.realpath(os.path.join(perfil, "config.json"))
                continue
            if isinstance(v, list) and (k in LISTAS_SOMAM or k.endswith("_phrases")):
                cfg[k] = list(cfg.get(k) or []) + v
            else:
                cfg[k] = v
    if cfg.get("project"):
        cfg["project"] = texto_curto(cfg["project"])
    cfg["bash_rules"] = regras_validas(cfg.get("bash_rules") or [], invalidas)
    if "plans_dir" in cfg and not plans_relativo(cfg["plans_dir"]):
        log_erro("config", "plans_dir invalid (%r), using .planning" % (cfg["plans_dir"][:LIMITE_TEXTO],))
    if not plans_relativo(cfg.get("plans_dir")):
        cfg["plans_dir"] = ".planning"
    lim = cfg.get("line_limit", 450)
    if isinstance(lim, bool) or not isinstance(lim, int) or lim < 50:
        log_erro("config", "line_limit invalid (%r), using 450" % (lim,))
        cfg["line_limit"] = 450
    if confiado:  # plans folder (anchored at the project root) is free in research mode
        raiz = os.path.dirname(os.path.realpath(perfil))
        cfg["research_free_paths"] = list(cfg.get("research_free_paths") or []) + [
            os.path.normpath(os.path.join(raiz, cfg["plans_dir"]))]
    cfg["_confiado"] = confiado
    cfg["_invalidas"] = sorted(invalidas)
    cfg["_perfil"] = perfil
    cfg["_erro_config"] = erro_proj
    cfg["_nao_confiado"] = nao_confiado
    cfg["_perfil_mudou"] = mudou
    return cfg
