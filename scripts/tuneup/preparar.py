"""tune-up: automatic preparation (ECC, Ponytail and Caveman, pinned and limited) in the background.

Hook side (`ao_iniciar`, called by ev_inicio): reads the marker, shows the last result once and, when
needed and allowed, takes the lock and starts `principal` (preparar_execucao.py) detached. That run side
only adds what is missing; what the user already has, or removed, stays as it is.

Files in ~/.config/tune-up, never where TUNEUP_USER_JSON points (a project can set env): pronto.json
(marker: this plugin version is prepared; written only on success), preparo.json (what earlier runs
installed), preparo.resultado.json (last result; both written only under the lock), preparo.visto.json
(announced and shown; written only by hooks), preparo.lock.
"""
import json
import os
import subprocess
import sys
import time

from .config import AQUI, TESTE
from .mensagens import msg
from .sessao import abrir_privado, criar_dir, log_erro
from .usuario import ler_usuario

# Content that enters the machine: `commit` is checked in the clone before and after the install.
FONTES = (
    {"nome": "ecc", "repo": "affaan-m/ecc", "ref": "v2.2.3",
     "commit": "c05b2d6614f62f6db0047669aa4eefb223d478f9", "config": "hooks_enabled=false"},
    {"nome": "ponytail", "repo": "DietrichGebert/ponytail", "ref": "v5.3.3",
     "commit": "7801d061243d7b753bad0e0b3c057cd250b11755", "config": "ledger=false"},
    {"nome": "caveman", "repo": "JuliusBrussee/caveman", "ref": "v4.2.0",
     "commit": "70f4f34e834893ea9af9f4fc6022266bd56d18b1", "config": None},
)
MATCHER = ("PONYTAIL_SUBAGENT_MATCHER", "^tune-up:executor")
RECURSAO = "TUNEUP_PREPARANDO"
TRANCA_VELHA = 40 * 60  # above PRAZO_TOTAL plus the undo commands: a live run is never stale
NOMES = tuple(f["nome"] for f in FONTES) + ("claude", "git", "node", "tune-up")
MOTIVOS = {"missing": lambda: msg("prep_m_missing"), "state": lambda: msg("prep_m_state"),
           "list": lambda: msg("prep_m_list"), "add": lambda: msg("prep_m_add"),
           "commit": lambda: msg("prep_m_commit"), "limit": lambda: msg("prep_m_limit"),
           "install": lambda: msg("prep_m_install"), "disable": lambda: msg("prep_m_disable"),
           "left": lambda: msg("prep_m_left"), "catalog": lambda: msg("prep_m_catalog"),
           "error": lambda: msg("prep_m_error")}


# ---------------------------------------------------------------- files

def _arq(nome):
    return os.path.join(os.path.expanduser("~"), ".config", "tune-up", nome)


def _ler(nome):
    """dict; {} when the file does not exist; None when unreadable."""
    try:
        with open(_arq(nome), encoding="utf-8-sig") as f:  # user.json too: PowerShell 5.1 saves a BOM
            d = json.load(f)
        return d if isinstance(d, dict) else None
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, RecursionError):
        return None


def _gravar(nome, dados):
    tmp = "%s.%d.tmp" % (_arq(nome), os.getpid())
    with abrir_privado(tmp, "w") as f:
        json.dump(dados, f, indent=1)
    os.replace(tmp, _arq(nome))


def versao():
    with open(os.path.join(os.path.dirname(AQUI), ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        return json.load(f)["version"]


def pronto():
    return (_ler("pronto.json") or {}).get("version") == versao()


# ---------------------------------------------------------------- hook side

def permitido(cfg):
    """The HOME user.json, the one in use and the project must all allow it; unreadable counts as off."""
    u, casa = ler_usuario()[0], _ler("user.json")
    return casa is not None and casa.get("auto_prepare", True) is True and not (TESTE or os.environ.get("CI") or os.environ.get(RECURSAO)) and \
        u["auto_prepare"] and not u["invalid"] and cfg.get("auto_prepare") is True and \
        not cfg.get("_erro_config") and "auto_prepare" not in cfg.get("_invalidas", ())


def trancar():
    """Token of the lock just taken, or None: another session holds it."""
    criar_dir(os.path.dirname(_arq("x")))
    token = "%d-%s" % (os.getpid(), os.urandom(8).hex())
    for _ in range(2):
        try:
            fd = os.open(_arq("preparo.lock"), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            try:
                if abs(time.time() - os.path.getmtime(_arq("preparo.lock"))) < TRANCA_VELHA:
                    return None
                os.remove(_arq("preparo.lock"))
            except FileNotFoundError:
                pass
            continue
        with os.fdopen(fd, "w") as f:
            f.write(token)
        return token
    return None


def tranca_e_minha(token):
    try:
        with open(_arq("preparo.lock"), encoding="utf-8") as f:
            return f.read() == token
    except OSError:
        return False


def soltar(token):
    if tranca_e_minha(token):
        os.remove(_arq("preparo.lock"))


def argv_filho(token):
    """-I: no module comes from the current directory or the environment."""
    return [sys.executable, "-I", "-X", "utf8", "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); "
            "from tuneup.preparar_execucao import principal; principal(sys.argv[2])", AQUI, token]


def lancar(token):
    extra = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    subprocess.Popen(argv_filho(token), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, cwd=os.path.dirname(_arq("x")),
                     env=dict(os.environ, **{RECURSAO: "1"}), **extra)


def _origem():
    return ", ".join("%s (%s#%s %s)" % (f["nome"], f["repo"], f["ref"], f["commit"][:7]) for f in FONTES)


def linha_resultado(res):
    """Only names and reasons known here: no text of the file reaches the session."""
    pulados = res["skipped"] if isinstance(res.get("skipped"), dict) else {}
    falhas = res["failed"] if isinstance(res.get("failed"), list) else []
    fora = [f["nome"] for f in FONTES if pulados.get(f["nome"]) == "marketplace"]
    if res.get("ok"):
        linha = msg("prep_pronto")
    else:
        itens = ["%s: %s" % (n, MOTIVOS[m]()) for n in NOMES for m in MOTIVOS if [n, m] in falhas]
        linha = msg("prep_falhou", "; ".join(itens), _arq("user.json"))
    return linha + (msg("prep_fora", ", ".join(fora)) if fora else "")


def ao_iniciar(d, cfg):
    """Lines for the session start; starts the background run when it is needed and allowed."""
    if TESTE or d.get("source") not in ("startup", "resume"):
        return []
    linhas = []
    visto = _ler("preparo.visto.json") or {}
    res = _ler("preparo.resultado.json")
    if res and res.get("run") != visto.get("shown"):
        visto["shown"] = res.get("run")
        _gravar("preparo.visto.json", visto)
        linhas.append(linha_resultado(res))
    if not permitido(cfg) or pronto():
        return linhas
    token = trancar()
    if not token:
        return linhas
    try:
        if pronto():  # a run ended between the check and the lock
            soltar(token)
            return linhas
        lancar(token)
    except BaseException:
        soltar(token)
        raise
    if visto.get("announced") != _origem():
        linhas.append(msg("prep_anuncio", _origem(), _arq("user.json")))
        visto["announced"] = _origem()
        try:
            _gravar("preparo.visto.json", visto)
        except OSError as e:  # already started: the line still goes out
            log_erro("preparar", "preparo.visto.json: %r" % (e,))
    return linhas
