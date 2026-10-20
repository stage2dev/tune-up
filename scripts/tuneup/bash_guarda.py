"""tune-up: Bash that reaches the guard by indirection (trust, symlinks, protected text) and
the commands that talk mode denies inside the project."""
import os
import re
from .bash_parse import analisar_git, junta_dir, posicionais
from .caminhos import NT, nome
from .config import achar_perfil, home_real
from .escrita import RAIZ_PLUGIN, alvos_de_escrita, contem_protegida, raizes_protegidas, tar_extrai, valor_de

RE_EXECUTOR = re.compile(r"(?<![\w.-])(python[\d.]*|py|exec|xargs|node|nodejs|perl|ruby|deno|bun|osascript)(?![\w-])")
RE_CAMINHO = re.compile(r"\S*[/.]\S*")  # a path-like word: its name is not a trust word
RE_ATRIBUI = re.compile(r"[A-Za-z_]\w*=")
RE_CONFIAR = re.compile(r"guarda\.py|perfis_confiaveis|(?<![\w-])(tuneup|confiar|trust)(?![\w-])")
SAIDAS_NULAS = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"}


def resolvidos(toks, diretorio):
    """Real paths of the arguments that are symlinks (`ln -s guarda.py g; python3 g trust`)."""
    out = []
    for t in toks:
        if not t or t.startswith("-") or len(t) > 4096:
            continue
        p = junta_dir(diretorio, t)
        try:
            if os.path.islink(p):
                out.append(os.path.realpath(p))
        except (OSError, ValueError):
            pass
    return out


def grava_algo(seg, toks, diretorio):
    """The simple command writes some file (a redirection or a write verb)."""
    return any(a not in SAIDAS_NULAS for a in alvos_de_escrita(seg, toks, diretorio))


def ln_da_guarda(toks, diretorio, cwd):
    """`ln [-s]` whose source or target is guarda.py or a protected path: guard level."""
    if not toks or os.path.basename(toks[0]) != "ln":
        return None
    nivel = None
    for p in posicionais(toks[1:], "t"):
        c = junta_dir(diretorio, os.path.expandvars(p))
        if "guarda.py" in (nome(c), nome(os.path.realpath(c))):
            nivel = nivel or "turno"
        n = contem_protegida(c, cwd)  # `ln -s ~/A/.tune-up .tune-up` hands over a whole profile
        if n == "sempre":
            return n
        nivel = nivel or n
    return nivel


def expandido(texto):
    """Text with ~ and $HOME (Windows: also $USERPROFILE) expanded, casefolded, then `_nt`."""
    for h in {os.path.expanduser("~"), home_real()}:
        texto = texto.replace("${HOME}", h).replace("$HOME", h)
        if NT:
            texto = texto.replace("${USERPROFILE}", h).replace("$USERPROFILE", h)
        texto = re.sub(r"(?<![\w/~])~(?=/|\s|$|['\"])", lambda _m, h=h: h, texto)  # h is a path, not a template
    return _nt(texto.casefold())


def _nt(t):
    """Windows: text and roots compared alike: `/` for `\\`, no `//?/` prefix, Git Bash `/c/` as
    `c:/`, and no trailing dot after a name (`settings.json.` opens settings.json). Elsewhere: t."""
    if not NT:
        return t
    t = t.replace("\\", "/").replace("//?/", "").replace("//./", "")
    t = re.sub(r"(?<![\w/:.~$-])/([a-z])(?=/)", r"\1:", t)
    return re.sub(r"(?<=\w)\.+(?=[/'\"\s:]|$)", "", t)


def citacoes(seg, toks, diretorio, alvos):
    """(executor words, their symlink arguments, write text) of a simple command. A root or a
    trust word counts only as an executor's argument (python, node, xargs...) or in the write
    text: the write targets and the VAR=value words (`D=~/.config/tune-up; cp a $D/user.json`)."""
    escrita = " ".join(alvos + [t for t in seg if RE_ATRIBUI.match(t)])
    if not RE_EXECUTOR.search(" ".join(seg).casefold()):
        return [], [], escrita
    return list(seg), resolvidos(toks, diretorio), escrita


def nivel_do_texto(executor, links, cwd, escrita):
    """Guard level read from the command (after heredocs are dropped):
    - executor words citing guarda.py, tuneup, confiar, trust, perfis_confiaveis or the plugin
      root -> 'turno' (trust by indirection); a path-like word (`scripts/trust.py`) is no
      trust word;
    - write text (targets, VAR=value; empty when nothing is written) citing a protected root ->
      that root's level.
    `links`: real paths of the executors' symlink arguments. Words are matched before ~ expands
    (a HOME path must not count as a citation); roots after."""
    palavras = " ".join([x for x in executor if not RE_CAMINHO.fullmatch(x) or
                         re.search(r"guarda\.py|perfis_confiaveis", x, re.I)] +
                        [os.path.basename(x) for x in links]).casefold()
    t = expandido(" ".join(executor + links))
    raizes = {_nt(os.path.normpath(r).casefold()) for r in (RAIZ_PLUGIN, os.path.realpath(RAIZ_PLUGIN))}
    if executor and (RE_CONFIAR.search(palavras) or cita(t, raizes)):
        return "turno"
    if not escrita:
        return None
    t = expandido(escrita)
    homes = {os.path.expanduser("~"), home_real()}
    for h in homes:
        if re.search(re.escape(_nt(os.path.join(h, ".claude", "settings").casefold())) + r"[^/\s]*\.json(?![\w.-])", t):
            return "sempre"  # settings*.json (a `settings.json.bak` copy is not)
    protegidas = {_nt(os.path.normpath(r).casefold()) for r in raizes_protegidas(homes, cwd)}
    protegidas |= {"perfis_confiaveis", ".tune-up/config.json"}
    return "turno" if cita(t, protegidas) else None


def cita(texto, caminhos):
    """Some path appears whole in the text (`/x/tune-up` does not match `/x/tune-up-extra`)."""
    return any(re.search(re.escape(c) + r"(?![\w.-])", texto) for c in caminhos)


def _no_projeto(diretorio):
    from .conversa import topo_do_arquivo
    return bool(topo_do_arquivo(os.path.join(diretorio, "x"), diretorio) or achar_perfil(diretorio))


def nega_em_conversa(seg, toks, diretorio):
    """Talk mode: commands that change code without a readable target, run inside a project."""
    exe = os.path.basename(toks[0])
    a = toks[1:]
    nega, local = False, diretorio  # local: the folder that must be inside a project
    if exe == "git":
        gdir, sub, args = analisar_git(toks, diretorio)
        nega = sub in ("apply", "am") and not set(args) & {"--check", "--stat", "--numstat", "--summary"}
        so_indice = set(args) & {"--staged", "-S"} and not set(args) & {"--worktree", "-W"}
        nega = nega or (sub == "checkout" and "--" in args) or (sub == "restore" and not so_indice)
        arvore = sub in ("pull", "merge", "switch", "cherry-pick", "revert", "mv", "rm", "reset") or \
            (sub == "stash" and args[:1] in (["pop"], ["apply"])) or \
            (sub == "checkout" and bool(posicionais(args, "bB")))  # git that rewrites the working tree
        nega, local = nega or arvore, gdir
    elif exe == "patch":
        nega = "--dry-run" not in a
    elif exe == "perl":
        nega = any(re.fullmatch(r"-[a-zA-Z]*[ice]", x) or re.match(r"-[a-zA-Z]*i", x) for x in a)
    elif re.match(r"(python[\d.]*|node|nodejs|ruby)$", exe):
        nega = any(x in ("-", "--eval", "-p", "--print") or x.startswith("--eval=") or
                   re.fullmatch(r"-[A-Za-z]*[ce]", x) for x in a)
    elif exe in ("tar", "bsdtar", "gtar") and tar_extrai(a):
        nega, local = True, junta_dir(diretorio, valor_de(a, "-C", "--directory") or ".")
    elif exe == "unzip" and not set(a) & {"-l", "-t", "-v", "-p", "-Z"}:  # those only list or print
        nega, local = True, junta_dir(diretorio, valor_de(a, "-d", "--exdir") or ".")
    elif exe in ("install", "touch", "rsync"):
        nega = True
    elif exe == "dd":
        nega = any(x.startswith("of=") for x in a)
    nega = nega or any(t in ("--write", "--fix") or t.startswith("--fix=") for t in seg)  # formatters
    for j, t in enumerate(seg):  # raw tokens: comando_simples drops `yarn` as a runner
        if os.path.basename(t) in ("npm", "pnpm", "yarn"):
            nega = nega or seg[j + 1:j + 2] in (["install"], ["i"], ["ci"], ["add"], ["init"]) or \
                (t == "yarn" and len(seg) == j + 1)
            break
    return nega and _no_projeto(local)


def chamada_info(cmd):
    """The command is exactly what the skills inject: `sh <this plugin>/scripts/py
    scripts/guarda.py info` (the launcher; guarda.py relative to the plugin or its exact path),
    or the older `python3 <this plugin>/scripts/guarda.py info`. No other argument, operator,
    redirection or expansion; no copy or symlink. Windows: the `C:/x` spelling (a backslash is
    refused, like any `\\`), without letter case."""
    import shlex
    if re.search(r"[;&|<>$`()\n\\]", cmd):
        return False
    try:
        toks = shlex.split(cmd)
    except ValueError:
        return False
    g = os.path.join(RAIZ_PLUGIN, "scripts", "guarda.py")
    if len(toks) == 4 and toks[0] == "sh" and toks[3] == "info":
        if not _exato(toks[1], os.path.join(RAIZ_PLUGIN, "scripts", "py")):
            return False
        return toks[2] == "scripts/guarda.py" or _exato(toks[2], g)
    if len(toks) != 3 or toks[0] not in ("python3", "python") or toks[2] != "info":
        return False
    return _exato(toks[1], g)


def _exato(tok, alvo):
    """`tok` spells `alvo` (or its realpath) itself, and resolves to it."""
    if ".." in re.split(r"[/\\]", tok):  # `~/dev/L/../tune-up/...`: the kernel resolves L first
        return False
    if NT:
        def norm(x):
            return os.path.normcase(os.path.normpath(x))
        return norm(tok) in {norm(alvo), norm(os.path.realpath(alvo))} and \
            norm(os.path.realpath(tok)) == norm(os.path.realpath(alvo))
    return tok in {alvo, os.path.realpath(alvo)} and os.path.realpath(tok) == os.path.realpath(alvo)
