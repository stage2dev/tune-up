"""tune-up: alvos de escrita, liberação, proteção da guarda e evento escrita."""
import fnmatch
import glob
import json
import os
import re
from .bash_parse import analisar_git, junta_dir, posicionais
from .caminhos import SEM_CAIXA, cadeia, grafia, ident, mesmo, nome
from .config import achar_perfil, arquivo_confiaveis, home_real
from .mensagens import msg
from .sessao import decisao_pre, dentro, ler_sessao, log_erro
from .usuario import caminho_user_json

RAIZ_PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


ESCREVE_TODOS = {"tee", "rm", "chmod", "mv", "truncate", "touch"}
ESCREVE_DESTINO = {"cp", "ln", "install", "rsync", "ditto"}
VALOR_CURTO = {"install": "mogtSB", "truncate": "sr", "touch": "trd", "rsync": "eT",
               "cp": "t", "mv": "t", "ln": "t"}  # short flags that take a value
RE_OPEN_ESCRITA = re.compile(
    r"""open\(\s*(['"])([^'"]+)\1\s*,\s*(?:mode\s*=\s*)?(['"])[^'"]*[wax+][^'"]*\3""")


def destino_t(args):
    """Directory of `-t DIR` / `--target-directory=DIR` (cp, mv, ln, install), or None."""
    for j, a in enumerate(args):
        if a in ("-t", "--target-directory") and j + 1 < len(args):
            return args[j + 1]
        if a.startswith("--target-directory="):
            return a.split("=", 1)[1]
        if a.startswith("-t") and len(a) > 2 and not a.startswith("--"):
            return a[2:]
    return None


def arquivos_com_script(args, flags_script):
    """Files of `sed -i` / `perl -i`: skip the script (value of -e/-f, or the first operand)
    and the empty suffix of BSD `-i ''`."""
    out, dado, pular = [], False, False
    for j, a in enumerate(args):
        if pular:
            pular = False
            continue
        if a.startswith("--"):
            if a.split("=", 1)[0] in ("--expression", "--file"):
                dado, pular = True, "=" not in a
            continue
        if a.startswith("-") and len(a) > 1:
            if a[-1] in flags_script:
                dado = pular = True
            elif a == "-i" and j + 1 < len(args) and args[j + 1] == "":
                pular = True
            continue
        out.append(a)
    return [x for x in (out if dado else out[1:]) if x]


def python_c_escreve(toks):
    """Literal paths that `python -c '...open(path, "w")...'` writes."""
    if not os.path.basename(toks[0]).startswith("python") or "-c" not in toks[1:-1]:
        return []
    codigo = toks[toks.index("-c", 1) + 1]
    return [m.group(2) for m in RE_OPEN_ESCRITA.finditer(codigo)]


def valor_de(args, curta, longa):
    """Value of `-d DIR`, `-dDIR` or `--longa=DIR` / `--longa DIR`, or None."""
    for j, a in enumerate(args):
        if a in (curta, longa) and j + 1 < len(args):
            return args[j + 1]
        if a.startswith(longa + "="):
            return a.split("=", 1)[1]
        if a.startswith(curta) and len(a) > 2 and not a.startswith("--"):
            return a[2:]
    return None


def tar_extrai(args):
    """`tar x...`, `tar -xf`, `tar --extract`."""
    return bool(args) and bool(re.fullmatch(r"[A-Za-z]*x[A-Za-z]*", args[0])) or any(
        re.fullmatch(r"-[A-Za-z]*x[A-Za-z]*", a) or a in ("--extract", "--get") for a in args)


def com_glob(caminhos):
    """`*?[` patterns expanded as the shell would (folder pattern when the file does not exist)."""
    out = []
    for p in caminhos:
        if not any(x in p for x in "*?["):
            out.append(p)
            continue
        try:
            achados = glob.glob(p) or [os.path.join(x, os.path.basename(p)) for x in glob.glob(os.path.dirname(p))]
        except Exception:  # `[n-i]`: a bad range is no glob for the shell either
            achados = []
        out.extend(achados or [p])
    return out


def alvos_de_escrita(seg, toks, diretorio):
    """Caminhos que o comando simples grava: alvo de `>`/`>>` e argumentos de tee, sed -i,
    perl -i, cp, mv, rm, chmod, ln, install, rsync, ditto, truncate, touch, dd of=, curl -o
    python -c com open(..., "w"), patch, git apply, tar -x -C e unzip -d (globs expandidos)."""
    brutos = []
    for j, t in enumerate(seg[:-1]):
        if t[:1] == ">" or t in ("&>", "&>>"):
            alvo = seg[j + 1]
            if t.endswith("&") and (alvo == "-" or alvo.isdigit()):
                continue  # >&N, N>&M, >&-: duplicação de descritor, não arquivo
            brutos.append(alvo)
    if toks:
        exe = os.path.basename(toks[0])
        args = toks[1:]
        tdir = destino_t(args) if exe in ("cp", "mv", "ln", "install") else None
        pos = posicionais(args, VALOR_CURTO.get(exe, ""))
        if exe == "sed" and any(a.startswith(("-i", "--in-place")) for a in args):
            brutos.extend(arquivos_com_script(args, "ef"))
        elif exe == "perl" and any(re.match(r"-[a-zA-Z]*i", a) for a in args):
            brutos.extend(arquivos_com_script(args, "eE"))
        elif exe in ESCREVE_TODOS or (exe == "install" and "-d" in args):
            brutos.extend(pos)
        elif exe in ESCREVE_DESTINO and pos and not tdir:
            brutos.append(pos[-1])
        if tdir:
            brutos.append(tdir)
            brutos.extend(os.path.join(tdir, os.path.basename(x)) for x in pos)
        elif exe in ESCREVE_DESTINO | {"mv"} and len(pos) > 1:
            destino = junta_dir(diretorio, os.path.expandvars(pos[-1]))
            if os.path.isdir(destino):
                brutos.extend(os.path.join(destino, os.path.basename(x)) for x in pos[:-1])
        if exe == "dd":
            brutos.extend(a[3:] for a in args if a.startswith("of="))
        elif exe == "curl":
            for j, a in enumerate(args):
                if a.startswith("--output="):
                    brutos.append(a.split("=", 1)[1])
                elif (a == "--output" or re.fullmatch(r"-[a-zA-Z]*o", a)) and j + 1 < len(args):
                    brutos.append(args[j + 1])
                elif re.match(r"-o.", a):
                    brutos.append(a[2:])
        elif exe == "patch":
            pdir, ppos = valor_de(args, "-d", "--directory"), posicionais(args, "BDdFiopVYzr")
            alvo = os.path.join(pdir or "", ppos[0]) if ppos else pdir or "."
            brutos.extend([alvo] + [x for x in [valor_de(args, "-o", "--output")] if x])
        elif exe == "git":
            gdir, sub, gargs = analisar_git(toks, diretorio)
            if sub == "apply" and not set(gargs) & {"--check", "--stat", "--numstat", "--summary"}:
                brutos.append(gdir)
        elif exe in ("tar", "bsdtar", "gtar") and tar_extrai(args):
            brutos.append(valor_de(args, "-C", "--directory"))
        elif exe == "unzip":
            brutos.append(valor_de(args, "-d", "--exdir"))
        brutos.extend(python_c_escreve(toks))
    return com_glob([junta_dir(diretorio, os.path.expandvars(x)) for x in brutos if x])


def alvos_que_contem(toks, diretorio):
    """Paths whose whole subtree `rm`, `mv`, `cp -r` or `rsync` replace or delete."""
    exe = os.path.basename(toks[0]) if toks else ""
    args = toks[1:]
    pos = com_glob([junta_dir(diretorio, os.path.expandvars(p)) for p in posicionais(args, VALOR_CURTO.get(exe, ""))])
    if exe == "rm":
        return pos
    letras = {c for a in args if a.startswith("-") and not a.startswith("--") for c in a[1:]}
    recursivo = exe in ("mv", "rsync", "ditto") or letras & {"r", "R", "a"} or \
        any(a in ("--recursive", "--archive") for a in args)
    if exe not in ("mv", "cp", "rsync", "ditto") or not recursivo or len(pos) < 2:
        return []
    fontes, destino = pos[:-1], pos[-1]
    out = list(fontes) if exe == "mv" else []
    apaga = exe == "rsync" and any(a.startswith("--delete") for a in args)
    if apaga or not os.path.isdir(destino):
        out.append(destino)
    else:
        out.extend(os.path.join(destino, os.path.basename(f.rstrip("/"))) for f in fontes)
    return out


# ---------------------------------------------------------------- escrita

def liberar_escrita(caminho, raiz):
    """chmod u+w no arquivo (e no diretório pai) ou no ancestral existente mais próximo,
    sem sair da raiz sincronizada. Compara caminhos reais; pula symlink, `.git` e
    arquivo de outro dono."""
    import stat
    raiz = os.path.realpath(raiz)

    def pode(p):
        return dentro(p, raiz) and ".git" not in os.path.relpath(p, raiz).split(os.sep)

    def chmod_uw(p):
        try:
            if os.path.islink(p) or not pode(p):
                return
            st = os.lstat(p)
            if st.st_uid != os.getuid():
                return
            if not st.st_mode & stat.S_IWUSR:
                os.chmod(p, stat.S_IMODE(st.st_mode) | stat.S_IWUSR)
        except OSError as e:
            log_erro("escrita", "chmod %s: %r" % (p, e))

    if os.path.islink(caminho):
        return
    caminho = os.path.realpath(caminho)
    if not pode(caminho):
        return
    if os.path.exists(caminho):
        chmod_uw(caminho)
        pai = os.path.dirname(caminho)
        if os.path.isdir(pai):
            chmod_uw(pai)
        return
    p = os.path.dirname(caminho)
    while pode(p) and not os.path.exists(p):
        p = os.path.dirname(p)
    if os.path.isdir(p):
        chmod_uw(p)


def livre_em_pesquisa(caminho, d, cfg, real=True):
    """Free in research mode; a symlink is free only when its real path is free too."""
    r = os.path.realpath(caminho)
    if real and r != os.path.normpath(caminho) and not livre_em_pesquisa(r, d, cfg, False):
        return False
    raizes = [d.get("scratchpad_dir"), "/tmp", "/private/tmp"]
    if any(dentro(caminho, r) for r in raizes if r):
        return True
    c = caminho
    if not cfg.get("_confiado"):  # trusted: config.py already adds the absolute plans_dir
        from .conversa import topo, topo_do_arquivo
        top = topo_do_arquivo(c, d.get("cwd")) or topo(d.get("cwd") or os.getcwd())
        if any(dentro(x, os.path.join(top, ".planning")) for x in {c, os.path.realpath(c)}):
            return True
    if dentro(c, os.path.join(os.path.expanduser("~"), ".claude", "plans")):
        return True
    projetos = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    if dentro(c, projetos):
        partes = os.path.relpath(c, projetos).split(os.sep)
        if len(partes) >= 3 and partes[1] == "memory":
            return True
    for livre in cfg.get("research_free_paths") or []:
        livre = str(livre)
        if livre.startswith("/") or livre.startswith("~"):
            if dentro(caminho, livre):
                return True
        elif "/" + livre.strip("/") + "/" in c:
            return True
    return False


_PROTEGIDOS = {}


def caminhos_protegidos(registrar=False):
    """(absolute items, ignored items) of user.json `protected_paths`, read raw so one bad item
    does not drop the good ones. `registrar`: log each ignored item (SessionStart)."""
    p = caminho_user_json()
    if p not in _PROTEGIDOS:
        lst = None
        try:
            with open(p, encoding="utf-8") as f:
                bruto = json.load(f)
            lst = bruto.get("protected_paths") if isinstance(bruto, dict) else None
        except Exception:
            pass  # missing or invalid user.json: usuario.py reports it
        abs_, ign = [], []
        for x in lst if isinstance(lst, list) else ([] if lst is None else [lst]):
            if not isinstance(x, str):
                ign.append(("not text", repr(x)[:80]))
            elif x.startswith(("/", "~")):
                abs_.append(x)
            else:
                ign.append(("not absolute", x[:120]))
        _PROTEGIDOS[p] = (abs_, ign)
    abs_, ign = _PROTEGIDOS[p]
    if registrar:
        for motivo, x in ign:
            log_erro("user", "protected_paths ignored (%s): %s" % (motivo, x))
    return abs_, ign


_RAIZES = {}  # per run: (homes, cwd, ...) -> [(root, ident, idents of its chain, spellings)]


def raizes_protegidas(homes, cwd=None):
    """Plugin root (from __file__), ~/.claude/plugins, ~/.config/tune-up, user.json, the trust
    list, this project's .tune-up/config.json and user.json `protected_paths` (absolute or `~`).
    Computed once per run (with each root's file identity)."""
    return {x[0] for x in _raizes_com_ids(homes, cwd)}


def _raizes_com_ids(homes, cwd):
    chave = (tuple(sorted(homes)), cwd, caminho_user_json(), arquivo_confiaveis(),
             os.environ.get("CLAUDE_PROJECT_DIR"))
    if chave in _RAIZES:
        return _RAIZES[chave]
    raizes = {RAIZ_PLUGIN, os.path.realpath(RAIZ_PLUGIN), os.path.normpath(caminho_user_json()),
              os.path.normpath(arquivo_confiaveis())}
    for h in homes:
        raizes.add(os.path.join(h, ".claude", "plugins"))
        raizes.add(os.path.join(h, ".config", "tune-up"))
        raizes.add(os.path.join(h, ".config", "tune-up", "user.json"))  # hard links compare by file
    perfil = achar_perfil(cwd) if cwd else None
    if perfil:
        raizes.add(os.path.join(perfil, "config.json"))
    for p in caminhos_protegidos()[0]:
        raizes.add(os.path.normpath(os.path.expanduser(p)))
    _RAIZES[chave] = [(os.path.normpath(r), ident(r), cadeia(r), {grafia(r), grafia(os.path.realpath(r))})
                      for r in raizes]
    return _RAIZES[chave]


_CLAUDE = {}  # per run: home -> identities of ~/.claude/settings*.json


def settings_do_claude(caminho, h, real=None):
    """`caminho` is (or is the same file as) ~/.claude/settings*.json. `real`: its realpath."""
    claude = os.path.join(h, ".claude")
    for c in {os.path.normpath(caminho), real or os.path.realpath(caminho)}:
        if fnmatch.fnmatchcase(nome(c), "settings*.json") and mesmo(os.path.dirname(c), claude):
            return True
    if h not in _CLAUDE:
        try:
            nomes = os.listdir(claude)
        except OSError:
            nomes = []
        _CLAUDE[h] = {ident(os.path.join(claude, n)) for n in nomes
                      if fnmatch.fnmatchcase(nome(n), "settings*.json")} - {None}
    i = ident(caminho)
    return i is not None and i in _CLAUDE[h]


def protecao_da_guarda(caminho, cwd=None):
    """'sempre' (settings do Claude), 'turno' (perfil, plugin, confiáveis) ou None.
    Compares by file identity, and without letter case on darwin/win32."""
    homes = {os.path.expanduser("~"), home_real()}
    c, real, cad, graf = os.path.normpath(caminho), os.path.realpath(caminho), None, None
    if any(settings_do_claude(caminho, h, real) for h in homes):
        return "sempre"
    for r, ri, _, grafias in _raizes_com_ids(homes, cwd):  # = dentro(caminho, r), computed once
        if c == r or c.startswith(r.rstrip(os.sep) + os.sep):
            return "turno"
        if ri is not None:
            cad = cadeia(caminho, real) if cad is None else cad
            if ri in cad:
                return "turno"
        elif SEM_CAIXA:  # root does not exist yet: spelling without case
            graf = graf or {grafia(c), grafia(real)}
            if any(a == b or a.startswith(b.rstrip(os.sep) + os.sep) for a in graf for b in grafias):
                return "turno"
    for c in {c, real}:
        if nome(c) == "config.json" and nome(os.path.dirname(c)) == ".tune-up":
            return "turno"
    return None


def contem_protegida(caminho, cwd=None):
    """Same level as protecao_da_guarda when `caminho` is a protected root's ancestor
    (`~/.claude`, `~/.config`, a `.tune-up` folder...)."""
    homes = {os.path.expanduser("~"), home_real()}
    if any(dentro(os.path.join(h, ".claude", "settings.json"), caminho) for h in homes):
        return "sempre"
    ci, c = ident(caminho), os.path.normpath(caminho)
    for r, _, cad, _ in _raizes_com_ids(homes, cwd):  # = dentro(r, caminho) with the root's chain cached
        if r == c or r.startswith(c.rstrip(os.sep) + os.sep) or (ci is not None and ci in cad) or \
                (ci is None and dentro(r, caminho)):
            return "turno"
    if nome(caminho) == ".tune-up":
        return "turno"
    return protecao_da_guarda(caminho, cwd)


def ev_escrita(d, cfg):
    ti = d.get("tool_input") or {}
    if not isinstance(ti, dict) or not isinstance(d.get("cwd") or "", str):
        log_erro("escrita", "malformed input: tool_input %s, cwd %s" % (type(ti).__name__, type(d.get("cwd")).__name__))
        return decisao_pre("perguntar", "tune-up: malformed hook input (tool_input/cwd); confirm the write.")
    alvo = ti.get("file_path") or ti.get("notebook_path")
    if not isinstance(alvo, str) or not alvo:
        return None
    caminho = junta_dir(d.get("cwd") or os.getcwd(), alvo)
    nivel = protecao_da_guarda(caminho, d.get("cwd"))
    if nivel == "sempre":
        return decisao_pre("perguntar", msg("prot_settings_escrita", alvo))
    if nivel == "turno":
        pid = d.get("prompt_id")
        if not pid or ler_sessao(d.get("session_id")).get("aprender_prompt_id") != pid:
            return decisao_pre("perguntar", msg("prot_perfil_escrita", alvo))
    sess = ler_sessao(d.get("session_id"))
    if sess.get("modo_conversa"):
        from .conversa import NEGA, PERGUNTA, alvo_em_conversa
        r = alvo_em_conversa(caminho, d, cfg)
        if r == NEGA:
            return decisao_pre("bloquear", msg("talk_codigo", alvo))
        if r == PERGUNTA:
            return decisao_pre("perguntar", msg("talk_pergunta", alvo))
    elif sess.get("modo_pesquisa") and not livre_em_pesquisa(caminho, d, cfg):
        return decisao_pre("perguntar", msg("pesquisa_escrita", alvo))
    from .linhas import checar_seguro
    limite = checar_seguro(d, caminho, cfg, alvo)
    if limite and "permissionDecision" in limite["hookSpecificOutput"]:
        return limite
    # chmod só quando este evento não pergunta nem bloqueia
    raizes = cfg.get("synced_roots") or []
    real = os.path.realpath(caminho)
    for r in raizes:
        r = os.path.normpath(os.path.expanduser(r))
        if dentro(caminho, r) or dentro(real, os.path.realpath(r)):
            try:
                liberar_escrita(caminho, r)
            except Exception as e:
                log_erro("escrita", "chmod: %r" % (e,))
            break
    return limite
