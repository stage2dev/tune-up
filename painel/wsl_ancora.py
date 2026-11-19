"""Âncora da distro `tune-up`: um filho `wsl.exe ... sleep infinity` mantém a VM ligada enquanto o painel roda.

Só sobe depois de uma sonda nova dizer "pronta"; entre tentativas espera 5 s, 30 s e depois 120 s
(volta ao começo quando o filho viveu 300 s). No Windows o filho entra num Job object que o
mata quando o painel fecha; se o Job falhar, o filho fica e sai um aviso (o painel não cai).
"""
import atexit
import subprocess
import sys
import threading
import time

import wsl

ESPERAS = (5, 30, 120)
VIDA_BOA = 300
JOB_LIMIT_KILL_ON_JOB_CLOSE = 0x2000


def popen_padrao(cmd):
    extra = {"creationflags": wsl.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            close_fds=True, shell=False, **extra)


def job_padrao(processo):
    """Põe o processo num Job com KILL_ON_JOB_CLOSE e devolve o handle (guardar: fechar mata o filho)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class Basico(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class Estendido(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", Basico), ("IoInfo", ctypes.c_uint64 * 6),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    k32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    k32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    job = k32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
    info = Estendido()
    info.BasicLimitInformation.LimitFlags = JOB_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):  # 9 = Extended
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
    if not k32.AssignProcessToJobObject(job, int(processo._handle)):
        raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
    return job


class Ancora:
    def __init__(self, sonda, popen=popen_padrao, relogio=time.monotonic, job=job_padrao, avisar=None):
        self.sonda, self.popen, self.relogio, self.job = sonda, popen, relogio, job
        self.avisar = avisar or (lambda m: sys.stderr.write("painel: %s\n" % m))
        self._trava = threading.Lock()
        self._filho, self._job, self._inicio, self._tentativas, self._proxima = None, None, 0, 0, None
        self._atexit = False

    def _adiar(self, agora):
        self._proxima = agora + ESPERAS[min(self._tentativas, len(ESPERAS) - 1)]
        self._tentativas += 1

    def garantir(self):
        """True se o filho está vivo (agora ou depois desta chamada)."""
        with self._trava:
            agora = self.relogio()
            if self._filho is not None:
                vivo = self._filho.poll() is None
                if agora - self._inicio >= VIDA_BOA:
                    self._tentativas = 0
                    if not vivo:
                        self._proxima = None
                if vivo:
                    return True
                self._filho = None
            if self._proxima is not None and agora < self._proxima:
                return False
            self._adiar(agora)
            if not self.sonda.ler(forcar=True).get("pronta"):
                return False
            try:
                self._filho = self.popen(wsl.argv_cru(["/usr/bin/sleep", "infinity"]))
            except OSError as e:
                self.avisar("não consegui manter o WSL ligado (%s)." % e)
                return False
            self._inicio = agora
            if not self._atexit:
                atexit.register(self.parar)
                self._atexit = True
            try:
                self._job = self.job(self._filho)
            except Exception as e:  # noqa: BLE001 - without the job the child stays; parar() still ends it
                self._job = None
                self.avisar("aviso: a âncora do WSL ficou sem Job object (%s)." % e)
            return True

    def parar(self):
        with self._trava:
            filho, self._filho = self._filho, None
        if filho is None or filho.poll() is not None:
            return
        filho.terminate()
        try:
            filho.wait(timeout=5)
        except subprocess.TimeoutExpired:
            filho.kill()
