"""Preparo: tudo o que toca o sistema (comandos, processos soltos, relógio, HTTP local, portas) num objeto só, para
os testes trocarem por falsos. Comando = lista de argumentos com caminho absoluto, sem shell, com tempo limite."""
import http.client
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

EXTRAS_POSIX = ("/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin", "/usr/sbin", "/sbin",
                "/Applications/Docker.app/Contents/Resources/bin")  # CLI do Docker Desktop no Mac, sem link
INTERVALO_S = 3
LINHAS_FINAIS = 15


def resultado(estado, mensagem, comando=None, detalhe=None):
    return {"estado": estado, "mensagem": mensagem, "comando": comando, "detalhe": detalhe}


def feito(mensagem, detalhe=None):
    return resultado("feito", mensagem, detalhe=detalhe)


def falhou(mensagem, detalhe=None):
    return resultado("falhou", mensagem, detalhe=detalhe)


def dono(mensagem, comando=None, detalhe=None):
    return resultado("precisa_do_dono", mensagem, comando, detalhe)


def ultimas(saida, n=LINHAS_FINAIS):
    """Últimas linhas da saída de um comando (cada uma cortada), para o detalhe de uma falha."""
    linhas = [linha[:300] for linha in (saida or "").strip().splitlines() if linha.strip()]
    return "\n".join(linhas[-n:]) or None


def falha_ao_comecar(motivo, momento=None):
    """Estado de um preparo que nem começou (processo não saiu, pasta sem permissão): "falhou" com um motivo simples,
    sem passos. A tela mostra o motivo e "Tentar de novo"."""
    return {"id": os.urandom(6).hex(), "pid": None, "estado": "falhou", "inicio": momento, "atualizado": momento,
            "fim": momento, "mensagem": motivo, "portas": {}, "passos": []}


def mascarar(texto, segredos):
    for segredo in segredos:
        if segredo and len(segredo) >= 8:
            texto = texto.replace(segredo, "***")
    return texto


def _texto(dado):
    if dado is None:
        return ""
    return dado.decode("utf-8", "replace") if isinstance(dado, bytes) else dado


def extras_windows(ambiente):
    arquivos = ambiente.get("ProgramFiles") or r"C:\Program Files"
    local = ambiente.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return (os.path.join(arquivos, "Docker", "Docker", "resources", "bin"),
            os.path.join(local, "Microsoft", "WindowsApps"))


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


class Sistema:
    """O sistema de verdade. Os testes herdam e trocam achar/rodar/soltar/relogio/dormir/http/porta_livre."""

    def __init__(self, plataforma=None, caminho=None, ambiente=None):
        self.plataforma = plataforma or sys.platform
        amb = dict(os.environ if ambiente is None else ambiente)
        if caminho is None:
            atuais = [p for p in amb.get("PATH", "").split(os.pathsep) if p]
            extras = extras_windows(amb) if self.windows else EXTRAS_POSIX
            caminho = os.pathsep.join(atuais + [e for e in extras if e not in atuais])
        self.caminho = caminho
        amb["PATH"] = caminho
        self.ambiente = amb

    @property
    def windows(self):
        return self.plataforma.startswith("win")

    @property
    def mac(self):
        return self.plataforma == "darwin"

    def achar(self, nome):
        return shutil.which(nome, path=self.caminho)

    def rodar(self, args, tempo, pasta=None):
        """(código, saída) do comando; código None = não rodou ou passou do tempo limite."""
        try:
            r = subprocess.run(list(args), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, timeout=tempo, cwd=pasta, env=self.ambiente)
        except subprocess.TimeoutExpired as e:
            return None, _texto(e.output) + "\n(passou do tempo limite de %d s)" % tempo
        except OSError as e:
            return None, "não consegui rodar %s (%s)" % (os.path.basename(args[0]), e.strerror or e)
        return r.returncode, _texto(r.stdout)

    def soltar(self, args, caminho_log, pasta=None):
        """Processo destacado (sessão nova / grupo novo), stdin fechado, saída no log 0600. Devolve o Popen."""
        fd = os.open(caminho_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        if os.name != "nt":
            os.chmod(caminho_log, 0o600)
        opcoes = {}
        if os.name == "nt":
            opcoes["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            opcoes["start_new_session"] = True
        try:
            return subprocess.Popen(list(args), stdin=subprocess.DEVNULL, stdout=fd, stderr=subprocess.STDOUT,
                                    close_fds=True, cwd=pasta, env=self.ambiente, **opcoes)
        finally:
            os.close(fd)

    def relogio(self):
        return time.monotonic()

    def dormir(self, segundos):
        time.sleep(segundos)

    def http(self, url, tempo=5, cabecalhos=None):
        """(código, corpo até 64 KB) de um GET local sem proxy e sem redirecionar; (None, b"") sem resposta."""
        abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SemRedirecionar())
        try:
            with abridor.open(urllib.request.Request(url, headers=cabecalhos or {}), timeout=tempo) as r:
                return r.status, r.read(65536)
        except urllib.error.HTTPError as e:
            e.close()
            return e.code, b""
        except (OSError, ValueError, http.client.HTTPException):
            return None, b""

    def porta_livre(self, porta):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", porta))
            return True
        except OSError:
            return False
        finally:
            s.close()

    def existe(self, caminho):
        return os.path.exists(caminho)

    def ler_texto(self, caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                return f.read()
        except (OSError, UnicodeDecodeError):
            return None


def esperar(ex, teste, limite, o_que):
    """Repete teste() a cada INTERVALO_S até ele devolver algo diferente de False ou passar `limite` segundos.
    Devolve o último valor (False = o tempo acabou). Mostra o progresso no passo atual."""
    s = ex.sistema
    inicio = s.relogio()
    while True:
        valor = teste()
        if valor is not False:
            return valor
        passou = s.relogio() - inicio
        if passou >= limite:
            return False
        ex.progresso("Esperando %s (%d s de até %d s)." % (o_que, passou, limite))
        s.dormir(INTERVALO_S)
