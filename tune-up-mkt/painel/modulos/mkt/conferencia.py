"""Background `contas.py status` for the Marketing tab: one run at a time per project, state kept in files.

<raiz>/.tune-up/mkt/conferindo.json  {"inicio", "pid", "id"}  created with O_EXCL; removed by the runner at the end
<raiz>/.tune-up/mkt/conferencia.json {"id", "inicio", "fim", "codigo"}  written by the runner when contas.py ends
<raiz>/.tune-up/mkt/conferencia.log  contas.py output (0600), never shown on screen
Paths go through contas_arquivos.caminho (no symlink, nothing outside the project). Stdlib only.
"""
import importlib.util
import json
import os
import secrets
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(AQUI))), "scripts")
CONTAS = os.path.join(SCRIPTS, "contas.py")
RUNNER = os.path.join(AQUI, "rodar_conferencia.py")


def _carregar(nome, arquivo):
    """Loads a stdlib-only file of tune-up-mkt/scripts by path; nothing goes to sys.path or sys.modules."""
    spec = importlib.util.spec_from_file_location(nome, os.path.join(SCRIPTS, arquivo))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A = _carregar("tune_up_mkt_painel_contas_arquivos", "contas_arquivos.py")
R = _carregar("tune_up_mkt_painel_contas_regras", "contas_regras.py")

MARCADOR = "conferindo.json"
RESULTADO = "conferencia.json"
LOG = "conferencia.log"
VELHO = timedelta(minutes=5)   # a marker older than this is stale whatever its pid says
TEMPO_CONTAS = 240             # seconds the runner lets contas.py run (below VELHO)
JA = "Já está conferindo. Espere terminar; a tela se atualiza sozinha."


def agora():
    return datetime.now(timezone.utc)


def pid_vivo(pid):
    """True while process `pid` exists. POSIX: signal 0. Windows: OpenProcess + exit code STILL_ACTIVE."""
    if not isinstance(pid, int) or isinstance(pid, bool) or not 0 < pid <= 0x7FFFFFFF:  # file content: any int
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except OSError:
            return False
        return True
    import ctypes  # Windows only: os.kill(pid, 0) would terminate the process there
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ctypes.get_last_error() == 5  # access denied = it exists
    try:
        codigo = wintypes.DWORD()
        return bool(k.GetExitCodeProcess(h, ctypes.byref(codigo))) and codigo.value == 259  # STILL_ACTIVE
    finally:
        k.CloseHandle(h)


def lancar(argv, log_fd, cwd):
    """Starts argv detached (own session / process group), stdin closed, output to log_fd. Returns the pid."""
    extra = {"start_new_session": True} if os.name != "nt" else {
        "creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)}
    p = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log_fd, stderr=log_fd, cwd=cwd, close_fds=True,
                         **extra)
    threading.Thread(target=p.wait, daemon=True).start()  # reaps it: a zombie would look alive to pid_vivo
    return p.pid


def ler_json(arquivo):
    """A.ler_json that also treats JSON nested too deep (RecursionError) as unreadable: file content never raises."""
    try:
        return A.ler_json(arquivo)
    except RecursionError:
        return None, True


def ler_marcador(raiz):
    """dict or None (no marker). Unreadable content -> {} (stale)."""
    d, ruim = ler_json(A.caminho(raiz, MARCADOR))
    return {} if ruim else d


def ler_resultado(raiz):
    d, _ = ler_json(A.caminho(raiz, RESULTADO))
    return d if d and isinstance(d.get("codigo"), int) and R.ler_iso(d.get("fim")) else None


def vivo(m, quando, vivo_pid=pid_vivo):
    """A marker counts while its pid runs and it is younger than VELHO (a reused pid stops counting then)."""
    inicio = R.ler_iso(m.get("inicio")) if isinstance(m, dict) else None
    return inicio is not None and quando - VELHO <= inicio <= quando + R.FOLGA_FUTURO and vivo_pid(m.get("pid"))


def _criar(arquivo, dados):
    """O_CREAT|O_EXCL: fails with FileExistsError when the marker (or any link in its place) exists."""
    fd = os.open(arquivo, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dados, f)


def iniciar(raiz, quando=None, lancar_fn=lancar, vivo_pid=pid_vivo):
    """(True, message) when a run started; (False, JA) when one runs. Raises A.Recusado / OSError."""
    quando = quando or agora()
    marcador = A.caminho(raiz, MARCADOR)
    os.makedirs(os.path.dirname(marcador), exist_ok=True)
    with A.trava(marcador):
        marcador = A.caminho(raiz, MARCADOR)  # checked again under the lock
        m = ler_marcador(raiz)
        if m is not None:
            if vivo(m, quando, vivo_pid):
                return False, JA
            os.remove(marcador)  # stale: pid gone, too old or unreadable
        ident = secrets.token_hex(8)
        dados = {"inicio": R.iso(quando), "pid": os.getpid(), "id": ident}
        _criar(marcador, dados)
        try:
            log = A.caminho(raiz, LOG)
            fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
            try:
                if os.name != "nt":
                    os.fchmod(fd, 0o600)
                pid = lancar_fn([sys.executable, "-I", RUNNER, "--raiz", os.path.realpath(raiz), "--id", ident],
                                fd, os.path.realpath(raiz))
            finally:
                os.close(fd)
        except BaseException:
            os.remove(marcador)  # nothing runs: free the next click
            raise
        try:  # the process runs: whatever happens to this pid update, the answer is "started"
            if ler_json(marcador)[0] == dados:  # the runner may already have ended and removed it
                A.gravar_json(marcador, dict(dados, pid=pid))
        except Exception:  # noqa: BLE001 - the marker keeps our own pid; it goes stale after VELHO at most
            pass
    return True, "Conferindo as contas. Leva até um minuto; a tela se atualiza sozinha."


def encerrar(raiz, ident, inicio, codigo, quando=None):
    """Runner side: writes the result, then removes the marker if it is still ours. Never raises."""
    try:
        A.gravar_json(A.caminho(raiz, RESULTADO), {"id": ident, "inicio": inicio, "fim": R.iso(quando or agora()),
                                                   "codigo": codigo})
    except Exception:  # noqa: BLE001 - the marker must go even if the result cannot be written
        pass
    try:
        marcador = A.caminho(raiz, MARCADOR)
        try:
            with A.trava(marcador):
                _remover_se_meu(marcador, ident)
        except OSError:  # lock busy past its wait: remove anyway, still only our own marker
            _remover_se_meu(marcador, ident)
    except Exception:  # noqa: BLE001
        pass


def _remover_se_meu(marcador, ident):
    m, _ = A.ler_json(marcador)
    if isinstance(m, dict) and m.get("id") == ident:
        os.remove(marcador)
