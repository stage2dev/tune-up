"""tune-up: run side of the automatic preparation (see preparar.py): body of the detached process."""
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from .config import AQUI
from .preparar import FONTES, MATCHER, RECURSAO, _arq, _gravar, _ler, pronto, soltar, tranca_e_minha, versao
from .sessao import log_erro

PRAZO_CMD, PRAZO_LIMPEZA, PRAZO_TOTAL = 300, 60, 20 * 60
FORA = ("GIT_", "NODE_OPTIONS", "CLAUDE_CODE_PLUGIN_", "CLAUDE_PROJECT_DIR")  # would redirect claude or git
SETUP = os.path.join(os.path.dirname(AQUI), "skills", "setup", "scripts")


class Falha(Exception):
    """A step that failed; the text is a key of MOTIVOS."""


class Perdeu(Exception):
    """The lock belongs to another run now: stop and write nothing."""


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
        env = {k: v for k, v in os.environ.items() if not k.startswith(FORA)}
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
        """Of the user or the organization, any marketplace: `ecc@mine` is the user's ECC too. What a
        project or local scope has belongs to that folder only."""
        return next((p for p in self.lista(**kw) if p.get("scope") in ("user", "managed")
                     and str(p.get("id")).split("@")[0] == nome), None)

    def nosso(self, pid, **kw):
        return next((p for p in self.lista(**kw) if (p.get("id"), p.get("scope")) == (pid, "user")), None)

    def ligados(self):
        d = self.config().get("enabledPlugins")
        return d if isinstance(d, dict) else {}

    def ligado(self, pid):
        return self.ligados().get(pid, False) is not False

    def registro(self, f):
        """Marketplace of that name: None = not registered; False = another source; else its folder."""
        m = next((x for x in self.lista("marketplace") if x.get("name") == f["nome"]), None)
        if m is None:
            declarado = self.config().get("extraKnownMarketplaces", {})
            origem = declarado.get(f["nome"], {}).get("source") if isinstance(declarado, dict) else None
            if origem is None:
                return None
            return None if (origem.get("repo"), origem.get("ref")) == (f["repo"], f["ref"]) else False
        certo = (m.get("repo"), m.get("ref")) == (f["repo"], f["ref"]) and isinstance(m.get("installLocation"), str)
        return certo and m["installLocation"]

    def marketplace(self, f):
        """None = not registered; True = registered from the pin and its clone is at the commit; False."""
        pasta = self.registro(f)
        if not pasta:
            return pasta
        # --git-dir: never climbs to a parent repository
        rc, texto = self.rodar([shutil.which("git") or "git", "--git-dir", os.path.join(pasta, ".git"),
                                "rev-parse", "HEAD"])
        if rc != 0:
            raise Falha("error")
        return texto.strip() == f["commit"]

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
        pid = "%s@%s" % (f["nome"], f["nome"])
        try:
            self.claude("uninstall", pid, "--scope", "user", limpeza=True)
            # a killed install leaves the key with no record: uninstall refuses, Claude would install from it
            self.merge.drop_plugin(self.settings, pid)
            ficou = self.nosso(pid, limpeza=True) or self.ligado(pid)
        except (Falha, self.merge.MergeError, OSError, ValueError):
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
        antes = self.estado["installed"].get(nome)
        if antes == "installing":  # left by a killed run, maybe not limited
            ficou = self.nosso(pid)
            if ficou and self.registro(f) is False:
                self.anotar(nome, None)  # the user's own, installed since from another source
            elif ficou or pid in self.ligados():
                try:
                    self.desfazer(f, "install")
                except Falha as e:
                    if str(e) == "left":
                        raise
        if self.instalado(nome) or any(str(k).split("@")[0] == nome for k in self.ligados()):
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
            certo = False
            try:
                certo = self.marketplace(f)
            finally:
                if not certo:
                    self.claude("marketplace", "remove", nome, limpeza=True)
            if not certo:
                raise Falha("commit")
        self.limitar(nome)
        self.anotar(nome, "installing")
        extra = ["--config", f["config"]] if f["config"] else []
        if self.claude("install", pid, "--scope", "user", *extra)[0] != 0:
            self.desfazer(f, "install")
        if nome == "ecc":  # right away: nothing may fail between the install and this
            self.claude("disable", pid, "--scope", "user", limpeza=True)
        try:
            tem, certo = self.nosso(pid, limpeza=True), self.marketplace(f)  # an install may refresh the clone
            ligado = self.ligado(pid)
        except Falha:
            tem = certo = None
        if nome == "ecc" and (not tem or tem.get("enabled") is not False or ligado):
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
        ecc = (self.nosso("ecc@ecc") or {}).get("installPath")
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
    except Exception as e:  # stderr goes nowhere
        log_erro("preparar", "%s: %s" % (type(e).__name__, e))
    finally:
        soltar(token)
