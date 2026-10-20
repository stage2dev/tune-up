"""tune-up: git externo (branch, mergeadas, prazo), evento bash e análise do push."""
import json
import os
import re
import time
from .bash_parse import analisar_git, comandos, flags_curtas, junta_dir, posicionais, sem_heredoc
from .config import SEVERIDADE, TESTE
from .bash_guarda import chamada_info, citacoes, grava_algo, ln_da_guarda, nega_em_conversa, nivel_do_texto
from .escrita import alvos_de_escrita, alvos_que_contem, contem_protegida, protecao_da_guarda
from .mensagens import msg
from .sessao import decisao_pre, dentro, ler_sessao, log_erro
from .sql_prod import pg_remoto, pg_remoto_no_texto, supabase_remoto

# ---------------------------------------------------------------- git/gh externos

INICIO = time.time()
PRAZO = 7.0  # segundos para o evento inteiro (o hook do Bash tem 10)
if TESTE and os.environ.get("TUNEUP_PRAZO"):
    PRAZO = float(os.environ["TUNEUP_PRAZO"])
_BRANCH = {}
_MERGEADAS = {}


def restante(maximo):
    return max(0.0, min(maximo, PRAZO - (time.time() - INICIO)))


def branch_atual(diretorio):
    if TESTE and "TUNEUP_FAKE_BRANCH" in os.environ:
        return os.environ["TUNEUP_FAKE_BRANCH"] or None
    chave = os.path.normpath(diretorio)
    if chave not in _BRANCH:
        _BRANCH[chave] = _ler_branch(diretorio)
    return _BRANCH[chave]


def _ler_branch(diretorio):
    """Fora de repositório ou detached HEAD = None sem log (só o aviso)."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", diretorio, "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=restante(3))
        if r.returncode == 0:
            b = r.stdout.strip()
            return b if b and b != "HEAD" else None
        erro = r.stderr.strip()
        if "not a git repository" not in erro and "cannot change to" not in erro:
            log_erro("branch", "git rev-parse in %s (exit %d): %s"
                     % (diretorio, r.returncode, erro[:300]))
    except Exception as e:
        log_erro("branch", "git rev-parse in %s: %r" % (diretorio, e))
    return None


def mergeadas(diretorio):
    """{branch: numero} das últimas 200 PRs mergeadas; uma chamada do gh por diretório.
    Devolve (dict|None, erro) com erro em (None, "gh", "prazo")."""
    chave = os.path.normpath(diretorio)
    if chave in _MERGEADAS:
        return _MERGEADAS[chave]
    import subprocess
    res = (None, "gh")
    try:
        t = restante(6)
        if t <= 0.1:
            res = (None, "prazo")
        else:
            r = subprocess.run(["gh", "pr", "list", "--state", "merged", "--json",
                                "headRefName,number", "--limit", "200"],
                               capture_output=True, text=True, timeout=t,
                               cwd=diretorio if os.path.isdir(diretorio) else None)
            if r.returncode == 0:
                lst = json.loads(r.stdout or "[]")
                m = {}
                for pr in lst if isinstance(lst, list) else []:
                    if isinstance(pr, dict) and pr.get("headRefName") and \
                            pr.get("headRefName") not in m:
                        m[pr["headRefName"]] = str(pr.get("number"))
                res = (m, None)
    except subprocess.TimeoutExpired:
        res = (None, "prazo")
    except Exception:
        res = (None, "gh")
    _MERGEADAS[chave] = res
    return res


def pr_mergeada(branch, diretorio):
    """Devolve (numero|None, erro: None|"gh"|"prazo")."""
    if TESTE:
        if os.environ.get("TUNEUP_FAKE_GH_ERRO") == "1":
            return None, "gh"
        if "TUNEUP_FAKE_GH_MERGED" in os.environ:
            n = os.environ["TUNEUP_FAKE_GH_MERGED"].strip()
            return (n or None), None
    m, erro = mergeadas(diretorio)
    if erro:
        return None, erro
    return m.get(branch), None


def copia_da_guarda(t, diretorio):
    """A .py with another name that is a copy of guarda.py (imports `tuneup`, has `confiar`)."""
    if not t.endswith(".py"):
        return False
    try:
        with open(junta_dir(diretorio, t), "rb") as f:
            b = f.read(65536)
    except OSError:
        return False
    return b"tuneup" in b and b"confiar" in b


def roda_confiar(toks, diretorio="."):
    """guarda.py (or a copy) run with `confiar`/`trust`, or with a non-literal argument
    (`$S`, `$(...)`, backtick) that could expand to them."""
    executa = bool(toks) and (os.path.basename(toks[0]).startswith("python") or toks[0].endswith(".py"))
    for j, t in enumerate(toks):
        guarda = os.path.basename(t) == "guarda.py"
        if not guarda and not (executa and j <= 1 and copia_da_guarda(t, diretorio)):
            continue
        resto = toks[j + 1:]
        if "confiar" in resto or "trust" in resto:
            return True
        if executa and any("$" in x or "`" in x for x in resto):
            return True
    return False


def ev_bash(d, cfg):
    ti = d.get("tool_input") or {}
    if not isinstance(ti, dict) or not isinstance(d.get("cwd") or "", str):
        log_erro("bash", "malformed input: tool_input %s, cwd %s" % (type(ti).__name__, type(d.get("cwd")).__name__))
        return decisao_pre("perguntar", "tune-up: malformed hook input (tool_input/cwd); confirm the command.")
    cmd = ti.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return None
    if chamada_info(cmd.strip()):  # skills inject `python3 <root>/scripts/guarda.py info`
        return None
    cwd = d.get("cwd") or os.getcwd()
    principais = list(cfg.get("main_branches") or ["main", "master"])
    sess = ler_sessao(d.get("session_id"))
    conversa = bool(sess.get("modo_conversa"))
    pesquisa = bool(sess.get("modo_pesquisa")) or conversa  # talk = research engine + no code
    scratch = d.get("scratchpad_dir")
    limpo = sem_heredoc(cmd)
    limpo = re.sub(r"\\\r?\n", " ", limpo)
    achados = []  # (acao, msg)

    def add(acao, msg):
        achados.append((acao, msg))

    def pesq(rotulo):  # talk mode asks with its own message (it names the phrase that leaves it)
        return msg("talk_pergunta", rotulo) if conversa else msg("pesquisa", rotulo)

    diretorio = cwd
    aprender = d.get("prompt_id") and sess.get("aprender_prompt_id") == d.get("prompt_id")
    executor, links, escrita, escreve = [], [], [], False  # for nivel_do_texto
    for seg, toks in comandos(limpo):
        if not toks:  # `D=~/.config/tune-up` alone still feeds the write text
            escrita.append(citacoes(seg, toks, diretorio, [])[2])
            continue
        alvos = alvos_de_escrita(seg, toks, diretorio)
        niveis = {protecao_da_guarda(c, cwd) for c in alvos}
        niveis |= {contem_protegida(c, cwd) for c in alvos_que_contem(toks, diretorio)}
        niveis.add(ln_da_guarda(toks, diretorio, cwd))
        e, l, w = citacoes(seg, toks, diretorio, alvos)
        executor, links, escrita = executor + e, links + l, escrita + [w]
        escreve = escreve or grava_algo(seg, toks, diretorio)
        if conversa and (codigo_em_conversa(alvos, toks, diretorio, d, cfg) or
                         nega_em_conversa(seg, toks, diretorio)):
            add("bloquear", msg("talk_codigo", os.path.basename(toks[0])))
        if roda_confiar(toks, diretorio):
            niveis.add("turno")
        if "sempre" in niveis:
            add("perguntar", msg("prot_settings_bash"))
        elif "turno" in niveis and not aprender:
            add("perguntar", msg("prot_perfil_bash"))
        exe = os.path.basename(toks[0])
        if exe == "cd":
            if len(toks) > 1 and toks[1] != "-":
                diretorio = junta_dir(diretorio, toks[1])
            elif len(toks) == 1:
                diretorio = os.path.expanduser("~")
            continue

        if exe == "git":
            gdir, sub, args = analisar_git(toks, diretorio)
            if sub == "stash":
                s = args[0] if args and not args[0].startswith("-") else None
                if s in (None, "push", "save"):
                    resto = args[1:] if s else args
                    letras, longas = flags_curtas(resto, "m")
                    if letras & {"u", "a"} or longas & {"--include-untracked", "--all"}:
                        add("bloquear", msg("stash_u"))
                    else:
                        add("perguntar", msg("stash"))
                elif s in ("drop", "clear"):
                    add("perguntar", msg("perigoso", ("git stash " + s)))
            elif sub == "add":
                letras, longas = flags_curtas(args, "")
                pos = posicionais(args, (), ("--chmod", "--pathspec-from-file"))
                alvos_amplos = {".", "./", ":/", "*", ":/*"}
                if letras & {"A", "u"} or longas & {"--all", "--update"} or \
                        any(p in alvos_amplos for p in pos):
                    add("bloquear", msg("add"))
            elif sub == "commit":
                letras, longas = flags_curtas(args, "mFCct")
                if "a" in letras or "--all" in longas:
                    add("bloquear", msg("commit_a"))
                if not cfg.get("commit_on_main"):
                    b = branch_atual(gdir)
                    if b is None:
                        add("avisar", msg("branch_ilegivel", gdir))
                    elif b in principais and not repo_livre(gdir, cfg):
                        add("bloquear", msg("commit_main", b, b, b))
                if pesquisa:
                    add("perguntar", pesq("git commit"))
            elif sub == "push":
                analisar_push(args, gdir, principais, add, cfg)
                if pesquisa:
                    add("perguntar", pesq("git push"))
            elif sub == "merge" and not cfg.get("claude_may_merge") and \
                    not cfg.get("commit_on_main"):
                b = branch_atual(gdir)
                if b in principais and not repo_livre(gdir, cfg):
                    add("perguntar", msg("merge_local", b))
            elif sub == "reset" and "--hard" in args:
                add("perguntar", msg("perigoso", "git reset --hard"))
            elif sub == "checkout" and "--" in args and args[args.index("--") + 1:]:
                add("perguntar", msg("perigoso", "git checkout -- <caminho>"))
            elif sub == "checkout" and ("." in posicionais(args) and args[:1] == ["."]):
                add("perguntar", msg("perigoso", "git checkout ."))
            elif sub == "switch":
                letras, longas = flags_curtas(args, "cC")
                if "f" in letras or longas & {"--force", "--discard-changes"}:
                    add("perguntar", msg("perigoso", "git switch -f/--discard-changes"))
            elif sub == "restore":
                letras, longas = flags_curtas(args, "s")
                if "--staged" not in longas and "S" not in letras and \
                        any(p in (".", "./", ":/") for p in posicionais(args, ("s",), ("--source",))):
                    add("perguntar", msg("perigoso", "git restore ."))
            elif sub == "clean":
                letras, longas = flags_curtas(args, "e")
                if "f" in letras or "--force" in longas:
                    add("perguntar", msg("perigoso", "git clean -f"))
            elif sub == "branch":
                letras, longas = flags_curtas(args, "")
                if "D" in letras or ("--force" in longas and ("--delete" in longas or "d" in letras)):
                    add("perguntar", msg("perigoso", "git branch -D"))

        elif exe == "gh":
            a = toks[1:]
            if a[:2] == ["pr", "merge"] and not cfg.get("claude_may_merge"):
                add("bloquear", msg("merge"))
            elif a[:2] == ["pr", "create"]:
                base = None
                for j, t in enumerate(a):
                    if t in ("--base", "-B") and j + 1 < len(a):
                        base = a[j + 1]
                    elif t.startswith("--base="):
                        base = t.split("=", 1)[1]
                    elif t.startswith("-B") and len(t) > 2:
                        base = t[2:]
                if base is not None and base not in principais:
                    add("bloquear", msg("empilhada", base))
                if pesquisa:
                    add("perguntar", pesq("gh pr create"))

        elif exe.split("@")[0] == "supabase" and cfg.get("supabase_guard") is not False:
            rotulo = supabase_remoto(toks[1:])
            if rotulo:
                add("perguntar", msg("prod_cli", rotulo))

        elif exe in ("psql", "pg_dump", "pg_restore") or (exe.startswith("$") and any(
                x.startswith(("-h", "-c", "-d", "-U", "-f", "--host", "--command", "--dbname"))
                for x in toks[1:])):  # `$PSQL -h ...`
            a = toks[1:]
            apaga = exe != "pg_dump" or "--clean" in a or "c" in flags_curtas(a, "dfhnNptTUZ")[0]
            if apaga and (pg_remoto(a) or pg_remoto_no_texto(limpo)):
                add("perguntar", msg("prod_cli", exe))

        elif exe in ("rm", "mv") and pesquisa:
            alvos = [junta_dir(diretorio, p) for p in posicionais(toks[1:])]
            if not alvos or not scratch or not all(dentro(p, scratch) for p in alvos):
                add("perguntar", pesq(exe))

    nivel = nivel_do_texto(executor, links, cwd, " ".join(escrita) if escreve else "")
    if nivel == "sempre":
        add("perguntar", msg("prot_settings_bash"))
    elif nivel == "turno" and not aprender:
        add("perguntar", msg("prot_perfil_bash"))

    for regra in cfg.get("bash_rules") or []:
        try:
            if isinstance(regra, dict) and re.search(regra.get("regex", "(?!)"), limpo):
                acao = regra.get("acao", "avisar")
                if acao in SEVERIDADE:
                    add(acao, regra.get("msg") or msg("regra_projeto"))
        except Exception as e:
            log_erro("bash", "bash_rules rule failed %r: %r" % (str(regra)[:120], e))

    if not achados:
        return None
    melhor = max(achados, key=lambda x: SEVERIDADE[x[0]])  # max devolve o primeiro empatado
    return decisao_pre(*melhor)


def codigo_em_conversa(alvos, toks, diretorio, d, cfg):
    """Talk mode: does this simple command write code inside the project? (`sed -i` scripts
    are not targets: alvos_de_escrita skips them.)"""
    from .conversa import NEGA, alvo_em_conversa
    return any(alvo_em_conversa(a, dict(d, cwd=d.get("cwd") or diretorio), cfg) == NEGA for a in alvos)


def toplevel(diretorio):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", diretorio, "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, timeout=restante(3))
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception as e:
        log_erro("bash", "rev-parse --show-toplevel: %r" % (e,))
    return None


def repo_livre(diretorio, cfg):
    """O repositório do comando fica dentro de algum item de `free_repos`?"""
    livres = [str(x) for x in (cfg.get("free_repos") or []) if x]
    if not livres:
        return False
    raiz = toplevel(diretorio) or diretorio
    cands = {os.path.normpath(raiz), os.path.realpath(raiz)}
    for r in livres:
        rr = os.path.expanduser(r)
        for c in cands:
            if dentro(c, rr) or dentro(c, os.path.realpath(rr)):
                return True
    return False


def analisar_push(args, gdir, principais, add, cfg=None):
    cfg = cfg or {}
    forca, apagar = False, False
    pos = []
    pular = False
    for a in args:
        if pular:
            pular = False
            continue
        if a in ("--force", "-f") or a.startswith("--force-with-lease") or a == "--force-if-includes":
            forca = True
        elif a in ("--delete", "-d"):
            apagar = True
        elif a in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
            pular = True
        elif a.startswith("--"):
            continue
        elif a.startswith("-") and len(a) > 1:
            if "f" in a[1:]:
                forca = True
            if "d" in a[1:]:
                apagar = True
        else:
            pos.append(a)
    refspecs = pos[1:]
    atual = None
    alvos = []
    for r in refspecs:
        if r.startswith("+"):
            forca = True
            r = r[1:]
        if r.startswith(":"):
            apagar = True
            continue
        alvo = r.split(":", 1)[1] if ":" in r else r
        if alvo.startswith("refs/heads/"):
            alvo = alvo[len("refs/heads/"):]
        if alvo == "HEAD":
            atual = atual or branch_atual(gdir)
            alvo = atual
        if alvo:
            alvos.append(alvo)
    if not refspecs:
        atual = branch_atual(gdir)
        if atual:
            alvos.append(atual)
        else:
            add("avisar", msg("branch_ilegivel", gdir))
    if forca:
        for b in alvos:
            if b in principais:
                add("bloquear", msg("force_main", b))
                return
    if apagar:
        return
    if not cfg.get("claude_may_merge") and not cfg.get("commit_on_main"):
        na_principal = [b for b in alvos if b in principais]
        if na_principal and not repo_livre(gdir, cfg):
            add("bloquear", msg("push_main", na_principal[0]))
    for b in alvos:
        if b in principais:
            continue
        n, erro = pr_mergeada(b, gdir)
        if erro == "prazo":
            add("avisar", msg("gh_prazo"))
        elif erro:
            add("avisar", msg("gh_falhou"))
        elif n:
            add("bloquear", msg("push_merged", n, b))
