"""tune-up: automatic preparation (ECC, Ponytail and Caveman, pinned and limited) in the background.

Hook side (`ao_iniciar`, called by ev_inicio): reads the marker, shows the last result once and, when
needed and allowed, takes the lock and starts `principal` detached. Run side (`principal`): only adds
what is missing; what the user already has, or removed, stays as it is.

Files next to user.json: pronto.json (marker: this plugin version is prepared; written only on
success), preparo.json (what earlier runs installed), preparo.resultado.json (last result; both written
only under the lock), preparo.visto.json (announced and shown; written only by hooks), preparo.lock.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from .config import AQUI, TESTE
from .mensagens import msg
from .sessao import abrir_privado, criar_dir, log_erro
from .usuario import caminho_user_json, ler_usuario

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
PRAZO_CMD, PRAZO_LIMPEZA, PRAZO_TOTAL = 300, 60, 20 * 60
TRANCA_VELHA = 40 * 60  # above PRAZO_TOTAL plus the undo commands: a live run is never stale
FORA = ("CLAUDE_PROJECT_DIR", "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")  # would redirect claude or git
SETUP = os.path.join(os.path.dirname(AQUI), "skills", "setup", "scripts")
MOTIVOS = {"missing": lambda: msg("prep_m_missing"), "state": lambda: msg("prep_m_state"),
           "list": lambda: msg("prep_m_list"), "add": lambda: msg("prep_m_add"),
           "commit": lambda: msg("prep_m_commit"), "limit": lambda: msg("prep_m_limit"),
           "install": lambda: msg("prep_m_install"), "disable": lambda: msg("prep_m_disable"),
           "left": lambda: msg("prep_m_left"), "catalog": lambda: msg("prep_m_catalog"),
           "error": lambda: msg("prep_m_error")}


class Falha(Exception):
    """A step that failed; the text is a key of MOTIVOS."""


class Perdeu(Exception):
    """The lock belongs to another run now: stop and write nothing."""


# ---------------------------------------------------------------- files

def _arq(nome):
    return os.path.join(os.path.dirname(caminho_user_json()), nome)


def _ler(nome):
    """dict; {} when the file does not exist; None when unreadable."""
    try:
        with open(_arq(nome), encoding="utf-8") as f:
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
    """Both the user and the project must allow it; a value that cannot be read counts as off."""
    u = ler_usuario()[0]
    return not (TESTE or os.environ.get("CI") or os.environ.get(RECURSAO)) and \
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
            "from tuneup.preparar import principal; principal(sys.argv[2])", AQUI, token]


def lancar(token):
    extra = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
    subprocess.Popen(argv_filho(token), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, cwd=os.path.dirname(_arq("x")),
                     env=dict(os.environ, **{RECURSAO: "1"}), **extra)


def _origem():
    return ", ".join("%s (%s#%s %s)" % (f["nome"], f["repo"], f["ref"], f["commit"][:7]) for f in FONTES)


def linha_resultado(res):
    pulados = res.get("skipped") or {}
    fora = [f["nome"] for f in FONTES if pulados.get(f["nome"]) == "marketplace"]
    if res.get("ok"):
        linha = msg("prep_pronto")
    else:
        itens = ["%s: %s" % (n, MOTIVOS[m]()) for n, m in res.get("failed") or [] if m in MOTIVOS]
        linha = msg("prep_falhou", "; ".join(itens), caminho_user_json())
    return linha + (msg("prep_fora", ", ".join(fora)) if fora else "")


def ao_iniciar(d, cfg):
    """Lines for the session start; starts the background run when it is needed and allowed."""
    if d.get("source") not in ("startup", "resume"):
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
        linhas.append(msg("prep_anuncio", _origem(), caminho_user_json()))
        visto["announced"] = _origem()
        try:
            _gravar("preparo.visto.json", visto)
        except OSError as e:  # already started: the line still goes out
            log_erro("preparar", "preparo.visto.json: %r" % (e,))
    return linhas


# ---------------------------------------------------------------- run side

def pasta_claude():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(os.path.expanduser("~"), ".claude")


def config_caveman():
    """Same places as getConfigDir() of the pinned Caveman."""
    base = os.environ.get("XDG_CONFIG_HOME")
    if not base and os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Roaming")
    return os.path.join(base or os.path.join(os.path.expanduser("~"), ".config"), "caveman", "config.json")


def _matar(p):
    """The whole tree: a killed `claude` would leave its git clone running."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                           creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    p.kill()
    p.wait()


class Preparo:
    def __init__(self, token):
        self.token, self.fim = token, time.time() + PRAZO_TOTAL
        self.estado, self.falhas, self.pulados, self.detalhe, self.mudou = {}, [], {}, [], False
        sys.path.insert(0, SETUP)
        import settings_merge  # the one writer of settings.json (backup, atomic, read back)
        self.merge = settings_merge
        self.settings = os.path.join(pasta_claude(), "settings.json")

    def rodar(self, argv, limpeza=False):
        """(exit code, stdout); code None = timeout or could not start."""
        if not tranca_e_minha(self.token):
            raise Perdeu()
        prazo = PRAZO_LIMPEZA if limpeza else min(PRAZO_CMD, self.fim - time.time())
        rc, texto = None, "out of time"
        env = {k: v for k, v in os.environ.items() if k not in FORA}
        env.update({RECURSAO: "1", "GIT_TERMINAL_PROMPT": "0"})
        extra = {"start_new_session": True} if os.name != "nt" else {"creationflags": subprocess.CREATE_NO_WINDOW}
        if prazo > 0:
            try:
                with tempfile.TemporaryFile() as saida:  # a pipe would hang on a grandchild that outlives the kill
                    p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=saida, stderr=subprocess.DEVNULL,
                                         cwd=os.path.dirname(_arq("x")), env=env, **extra)
                    try:
                        rc = p.wait(prazo)
                    except subprocess.TimeoutExpired:
                        _matar(p)
                    saida.seek(0)
                    texto = saida.read().decode("utf-8", "replace")
            except OSError as e:
                rc, texto = None, repr(e)
        if rc != 0:
            self.detalhe.append([" ".join(argv[1:4]), rc, texto[-300:]])
        return rc, texto

    def claude(self, *args, **kw):
        return self.rodar([shutil.which("claude") or "claude", "plugin"] + list(args) + ["--json"], **kw)

    def lista(self, *args, **kw):
        rc, texto = self.claude(*(args + ("list",)), **kw)
        try:
            itens = json.loads(texto)
        except ValueError:
            itens = None
        if rc != 0 or not isinstance(itens, list) or not all(isinstance(x, dict) for x in itens):
            raise Falha("list")
        return itens

    def instalado(self, nome, **kw):
        """Any marketplace: `ecc@mine` is the user's ECC too."""
        return next((p for p in self.lista(**kw) if str(p.get("id")).split("@")[0] == nome), None)

    def marketplace(self, f):
        """None = not registered; True = registered from the pin and its clone is at the commit; False."""
        m = next((x for x in self.lista("marketplace") if x.get("name") == f["nome"]), None)
        if m is None:
            declarado = self.config().get("extraKnownMarketplaces", {})
            origem = declarado.get(f["nome"], {}).get("source") if isinstance(declarado, dict) else None
            if origem is None:
                return None
            return None if (origem.get("repo"), origem.get("ref")) == (f["repo"], f["ref"]) else False
        if (m.get("repo"), m.get("ref")) != (f["repo"], f["ref"]) or not isinstance(m.get("installLocation"), str):
            return False
        # --git-dir: never climbs to a parent repository
        rc, texto = self.rodar([shutil.which("git") or "git", "--git-dir", os.path.join(m["installLocation"], ".git"),
                                "rev-parse", "HEAD"])
        return rc == 0 and texto.strip() == f["commit"]

    def config(self):
        try:
            return self.merge.load(self.settings)[0]
        except (self.merge.MergeError, OSError, ValueError):
            raise Falha("limit")

    def anotar(self, nome, valor):
        """valor None removes. Written before the step it describes: a killed run is recognized later."""
        if valor is None:
            self.estado["installed"].pop(nome, None)
        else:
            self.estado["installed"][nome] = valor
        _gravar("preparo.json", self.estado)

    def desfazer(self, f, motivo):
        """Uninstall what this run (or a killed one) put there. Always raises."""
        try:
            self.claude("uninstall", "%s@%s" % (f["nome"], f["nome"]), "--scope", "user", limpeza=True)
            ficou = self.instalado(f["nome"], limpeza=True)
        except Falha:
            ficou = True
        if ficou:
            raise Falha("left")
        self.anotar(f["nome"], None)
        raise Falha(motivo)

    def limitar(self, nome):
        try:
            if nome == "ponytail" and MATCHER[0] not in self.config().get("env", {}):
                self.merge.merge(self.settings, dict([MATCHER]))
            elif nome == "caveman":
                arq = config_caveman()
                os.makedirs(os.path.dirname(arq), exist_ok=True)
                try:
                    fd = os.open(arq, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                except FileExistsError:
                    return
                with os.fdopen(fd, "w") as f:
                    f.write('{"defaultMode":"off"}')
        except (self.merge.MergeError, OSError, ValueError):
            raise Falha("limit")

    def um(self, f):
        nome, pid = f["nome"], "%s@%s" % (f["nome"], f["nome"])
        tem, antes = self.instalado(nome), self.estado["installed"].get(nome)
        if tem and antes == "installing" and tem.get("id") == pid:  # left by a killed run, maybe not limited
            try:
                self.desfazer(f, "install")
            except Falha as e:
                if str(e) == "left":
                    raise
            tem = None
        ligados = self.config().get("enabledPlugins")
        if tem or isinstance(ligados, dict) and any(str(k).split("@")[0] == nome for k in ligados):
            if antes != "done":
                self.pulados[nome] = "present"
            return
        if antes == "done":
            self.pulados[nome] = "removed"  # the user took it out: never put it back
            return
        registrado = self.marketplace(f)
        if registrado is False:
            self.pulados[nome] = "marketplace"
            return
        if registrado is None:
            if self.claude("marketplace", "add", "%s#%s" % (f["repo"], f["ref"]), "--scope", "user")[0] != 0:
                raise Falha("add")
            if not self.marketplace(f):
                self.claude("marketplace", "remove", nome, limpeza=True)
                raise Falha("commit")
        self.limitar(nome)
        self.anotar(nome, "installing")
        extra = ["--config", f["config"]] if f["config"] else []
        if self.claude("install", pid, "--scope", "user", *extra)[0] != 0:
            self.desfazer(f, "install")
        if nome == "ecc":  # right away: nothing may fail between the install and this
            self.claude("disable", pid, "--scope", "user", limpeza=True)
        try:
            tem, certo = self.instalado(nome, limpeza=True), self.marketplace(f)  # an install may refresh the clone
        except Falha:
            tem = certo = None
        if nome == "ecc" and (not tem or tem.get("enabled") is not False):
            self.desfazer(f, "disable")
        if not tem:
            self.desfazer(f, "install")
        if not certo:
            try:
                self.desfazer(f, "commit")
            finally:
                if registrado is None:
                    self.claude("marketplace", "remove", nome, limpeza=True)
        self.anotar(nome, "done")
        self.mudou = True

    def catalogo(self):
        if os.path.lexists(_arq("skills-catalog.md")):
            return
        ecc = (self.instalado("ecc") or {}).get("installPath")
        if not isinstance(ecc, str) or not os.path.isdir(os.path.join(ecc, "skills")):
            return
        rc, _ = self.rodar([sys.executable, "-I", "-X", "utf8", os.path.join(SETUP, "ecc_catalog.py"),
                            "--source", ecc, "--out", os.path.dirname(_arq("x"))])
        if rc != 0 or not os.path.isfile(_arq("skills-catalog.md")):
            raise Falha("catalog")
        self.mudou = True

    def tudo(self):
        estado = _ler("preparo.json")
        if estado is None or not isinstance(estado.setdefault("installed", {}), dict):
            # without the record a plugin the user removed could come back: install nothing
            self.falhas = [["tune-up", "state"]]
            return
        self.estado = estado
        faltam = [x for x in ("claude", "git", "node") if not shutil.which(x)]
        if faltam:
            self.falhas = [[x, "missing"] for x in faltam]
            return
        passos = [(f["nome"], lambda f=f: self.um(f)) for f in FONTES] + [("ecc", self.catalogo)]
        for nome, passo in passos:
            try:
                passo()
            except Falha as e:
                self.falhas.append([nome, str(e)])
            except Perdeu:
                raise
            except Exception as e:
                self.falhas.append([nome, "error"])
                self.detalhe.append(["exception", None, repr(e)[:300]])


def principal(token):
    """Body of the detached process."""
    if not tranca_e_minha(token):
        return
    try:
        if pronto():
            return
        p = Preparo(token)
        try:
            p.tudo()
        except Perdeu:
            return
        if p.falhas or p.mudou or not _ler("pronto.json"):  # nothing new after an update: nothing to say
            _gravar("preparo.resultado.json", {"run": token, "ok": not p.falhas, "failed": p.falhas,
                                               "skipped": p.pulados, "detail": p.detalhe})
        if not p.falhas:
            _gravar("pronto.json", {"version": versao(), "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "installed": p.estado["installed"], "skipped": p.pulados})
    finally:
        soltar(token)
