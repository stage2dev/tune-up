"""Ponte do painel no Windows com a distro WSL2 `tune-up` (criada por scripts/wsl/instalar.ps1).

O wsl.exe recebe sempre uma lista com --exec (nunca uma string, nunca shell, nunca um `--` solto:
isso entregaria o resto ao shell do Linux). Tudo o que o painel roda lá dentro passa pelo portão
/usr/local/bin/tune-up-exec; só a sonda (que confere o próprio portão) usa argv_cru.
"""
import sys

if __name__ == "__main__":  # `python -I painel/wsl.py` leaves the script folder out of sys.path
    import os as _os
    sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))

import json  # noqa: E402
import ntpath  # noqa: E402
import os  # noqa: E402
import posixpath  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

from erros import ErroAcao  # noqa: E402

DISTRO = "tune-up"
PORTAO = "/usr/local/bin/tune-up-exec"
MARCA = "/etc/tune-up/pronto.json"
CLAUDE_BIN = "/home/tuneup/.local/bin/claude"
PREFIXO_PLUGIN = "/home/tuneup/.claude/plugins/cache/"
LIMITE_ARGV = 30000
CACHE_PRONTA, CACHE_NAO = 60, 15
CONFERINDO = "conferindo o WSL..."
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RE_CHAVE = re.compile(r"^[0-9a-f]{12}$")
RE_USUARIO = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def _rede_padrao(letra):
    if sys.platform != "win32":
        return False
    import ctypes
    return ctypes.windll.kernel32.GetDriveTypeW(letra + ":\\") == 4  # DRIVE_REMOTE


def para_wsl(caminho, unidade_de_rede=None):
    """`X:\\a\\b` ou `X:/a/b` => `/mnt/x/a/b`. Só texto (ntpath): não resolve nada no disco."""
    if not isinstance(caminho, str) or not caminho:
        raise ErroAcao("Caminho vazio.")
    if any(c in caminho for c in "\x00\n\r"):
        raise ErroAcao("O caminho tem um caractere inválido.")
    if caminho[:4].replace("/", "\\") in ("\\\\?\\", "\\\\.\\"):
        raise ErroAcao("Caminhos que começam com \\\\?\\ ou \\\\.\\ não são aceitos.")
    if caminho[:2] in ("\\\\", "//", "\\/", "/\\"):
        raise ErroAcao("Pastas de rede (\\\\servidor\\pasta) não são aceitas. Use uma pasta do próprio computador.")
    unidade, resto = ntpath.splitdrive(caminho)
    if not re.match(r"^[A-Za-z]:$", unidade) or resto[:1] not in ("\\", "/"):
        raise ErroAcao("Use o caminho completo da pasta, como C:\\Users\\voce\\projeto.")
    partes = [p for p in re.split(r"[\\/]", resto) if p]
    if ".." in partes:
        raise ErroAcao("O caminho não pode ter '..'.")
    letra = unidade[0]
    if (unidade_de_rede or _rede_padrao)(letra):
        raise ErroAcao("A unidade %s: é uma unidade de rede. Use uma pasta do próprio computador." % letra.upper())
    return "/".join(["/mnt", letra.lower()] + partes)


def exe_wsl(env=None):
    """Caminho completo do wsl.exe em %SystemRoot%\\System32 (nunca o do PATH)."""
    raiz = (os.environ if env is None else env).get("SystemRoot") or ""
    if not re.match(r"^[A-Za-z]:\\", raiz):
        raiz = "C:\\Windows"
    return ntpath.join(raiz, "System32", "wsl.exe")


def _validar(comando):
    if not isinstance(comando, list) or not comando or not all(isinstance(a, str) and a for a in comando):
        raise ErroAcao("Comando inválido para o WSL (erro interno).")
    for a in comando:
        if a == "--" or "\x00" in a:
            raise ErroAcao("Argumento proibido para o WSL (erro interno).")


def _limite(lista):
    if sum(len(a) for a in lista) + len(lista) - 1 > LIMITE_ARGV:
        raise ErroAcao("comando grande demais para o Windows")
    return lista


def argv(cwd_wsl, comando):
    """Lista para rodar `comando` na distro, em `cwd_wsl`, pelo portão tune-up-exec."""
    _validar(comando)
    if not isinstance(cwd_wsl, str) or not cwd_wsl.startswith("/") or "\x00" in cwd_wsl:
        raise ErroAcao("Pasta inválida no WSL (erro interno).")
    return _limite([exe_wsl(), "-d", DISTRO, "--cd", cwd_wsl, "--exec", PORTAO] + list(comando))


def argv_cru(comando, usuario=None):
    """Lista sem o portão: só para a sonda e as conferências que o portão não deixaria rodar."""
    _validar(comando)
    extra = []
    if usuario is not None:
        if not isinstance(usuario, str) or not RE_USUARIO.match(usuario):
            raise ErroAcao("Usuário inválido para o WSL (erro interno).")
        extra = ["-u", usuario]
    return _limite([exe_wsl(), "-d", DISTRO] + extra + ["--exec"] + list(comando))


def rodar_padrao(cmd, timeout, env=None):
    """subprocess com lista, sem shell, sem janela. Devolve (codigo, stdout, stderr)."""
    if not isinstance(cmd, list):
        raise TypeError("cmd precisa ser lista")
    extra = {"creationflags": CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    ambiente = dict(os.environ, **env) if env else None
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
                           shell=False, env=ambiente, **extra)
    except FileNotFoundError:
        return 127, "", "comando não encontrado"
    except subprocess.TimeoutExpired:
        return 124, "", "demorou demais"
    except OSError as e:
        return 126, "", str(e)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


def versao_padrao():
    """Versão do plugin no .claude-plugin/plugin.json deste repositório; None se não der para ler."""
    try:
        with open(os.path.join(RAIZ, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            v = json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        return None
    return v if isinstance(v, str) else None


def plugin_dir_valido(p):
    """plugin_dir da marca: já normalizado, dentro do cache do tuneup, sem `..` nem controle."""
    return (isinstance(p, str) and posixpath.normpath(p) == p and p.startswith(PREFIXO_PLUGIN)
            and ".." not in p.split("/") and not any(ord(c) < 32 for c in p))


def _nao(motivo):
    return {"pronta": False, "motivo": motivo, "marcador": {}}


def _falha(cod, err, o_que):
    if cod == 124:
        return "o WSL demorou demais para responder (%s)." % o_que
    if cod == 127:
        return "não achei o wsl.exe."
    return "%s falhou (código %s)." % (o_que, cod)


def _marca_ok(m, versao):
    if not isinstance(m, dict) or m.get("versao") != 1:
        return "a marca de preparação está num formato desconhecido."
    if versao is None:
        return "não consegui ler a versão do plugin do painel."
    if m.get("plugin") != versao:
        return "o WSL foi preparado para o plugin %s; o painel é %s." % (m.get("plugin"), versao)
    if m.get("usuario") != "tuneup" or m.get("claude_bin") != CLAUDE_BIN:
        return "a marca de preparação tem usuário ou claude inesperados."
    if not plugin_dir_valido(m.get("plugin_dir")):
        return "a marca de preparação aponta para uma pasta do plugin inválida."
    return None


class Sonda:
    """Confere se a distro `tune-up` existe, está marcada como pronta e roda sem interop."""

    def __init__(self, rodar=rodar_padrao, relogio=time.monotonic, versao_plugin=versao_padrao, plataforma=None):
        self.rodar, self.relogio, self.versao_plugin = rodar, relogio, versao_plugin
        self.plataforma = plataforma or sys.platform
        self._trava, self._rodando = threading.Lock(), threading.Lock()
        self._valor, self._quando, self._geracao, self._fio = None, 0, 0, None
        self._zeradas = 0  # bumped by zerar(); a probe that started before it must not store its result

    def _fresco(self):
        if self._valor is None:
            return None
        prazo = CACHE_PRONTA if self._valor["pronta"] else CACHE_NAO
        return self._valor if self.relogio() - self._quando < prazo else None

    def ler(self, forcar=False):
        if self.plataforma != "win32":
            return _nao("só no Windows")
        with self._trava:
            v = self._fresco()
            if v is not None and not forcar:
                return v
            geracao = self._geracao
        with self._rodando:  # never two probes at once; whoever waited takes the value just read
            with self._trava:
                if self._geracao != geracao and self._valor is not None:
                    return self._valor
                zerada = self._zeradas
            v = self._sondar()
            with self._trava:
                if self._zeradas != zerada:  # zerar() ran while probing: the answer may be stale, never store it
                    return _nao("conferindo de novo...")
                self._valor, self._quando, self._geracao = v, self.relogio(), self._geracao + 1
            return v

    def zerar(self):
        with self._trava:
            self._valor = None
            self._zeradas += 1

    def valor_atual(self):
        """Nunca espera: devolve o que tem e, se estiver velho, confere em segundo plano."""
        if self.plataforma != "win32":
            return _nao("só no Windows")
        with self._trava:
            atual, fresco = self._valor, self._fresco()
            if fresco is None and (self._fio is None or not self._fio.is_alive()):
                self._fio = threading.Thread(target=self.ler, name="wsl-sonda", daemon=True)
                self._fio.start()
        return atual if atual is not None else _nao(CONFERINDO)

    def _sondar(self):
        try:
            return self._passos()
        except Exception as e:  # noqa: BLE001 - a broken probe is "not ready", never a crash
            return _nao("não consegui conferir o WSL (%s)." % type(e).__name__)

    def _passos(self):
        cod, out, err = self.rodar([exe_wsl(), "-l", "-q"], 5, env={"WSL_UTF8": "1"})
        if cod != 0:
            return _nao(_falha(cod, err, "a lista de distros do WSL"))
        linhas = [ln.strip().strip("\ufeff") for ln in out.replace("\x00", "").splitlines()]
        if DISTRO not in linhas:
            return _nao("a distro tune-up não está instalada no WSL.")
        cod, out, err = self.rodar(argv_cru(["/usr/bin/cat", MARCA]), 20)
        if cod != 0:
            return _nao(_falha(cod, err, "a leitura da marca de preparação") if cod in (124, 127)
                        else "a preparação do WSL não terminou (falta a marca).")
        try:
            marca = json.loads(out)
        except ValueError:
            return _nao("a marca de preparação não é um JSON válido.")
        motivo = _marca_ok(marca, self.versao_plugin())
        if motivo:
            return _nao(motivo)
        cod, out, err = self.rodar(argv_cru(["/usr/bin/printenv", "WSL_INTEROP"]), 20)
        if cod == 0:
            return _nao("a ponte com o Windows (interop) está ligada no WSL.")
        if cod != 1:
            return _nao(_falha(cod, err, "a conferência do interop"))
        cod, out, err = self.rodar(argv_cru(["/usr/bin/find", "/run/WSL", "-maxdepth", "1", "-name", "*_interop"]), 20)
        # GNU find: 0 = searched (stdout lists matches); 1 = an error. A missing /run/WSL means no
        # interop socket at all (the gate's glob matches nothing either); any other error is not ready.
        sem_pasta = cod == 1 and not out.strip() and "/run/WSL" in err and "No such file or directory" in err
        if not ((cod == 0 and not out.strip()) or sem_pasta):
            if cod == 0:
                return _nao("a ponte com o Windows (interop) está ligada no WSL.")
            return _nao(_falha(cod, err, "a conferência do interop"))
        return {"pronta": True, "motivo": "pronta", "marcador": marca}


def caminho_hf(chave):
    """Caminho do hyperframes do Estúdio dentro da distro, para esta chave do ambiente."""
    if not isinstance(chave, str) or not RE_CHAVE.match(chave):
        raise ErroAcao("Chave do Estúdio inválida.")
    return posixpath.join("/home/tuneup/.local/share/tune-up/estudio-node", chave, "node", "node_modules", ".bin",
                          "hyperframes")


_HF, _HF_TRAVA = {}, threading.Lock()


def hf_pronto(rodar, chave, relogio=time.monotonic, cache=None):
    """True se o hyperframes da chave existe e é executável na distro (cache 60 s sim / 15 s não)."""
    cmd = argv_cru(["/usr/bin/test", "-x", caminho_hf(chave)], usuario="tuneup")
    cache = _HF if cache is None else cache
    with _HF_TRAVA:
        visto = cache.get(chave)
        if visto and relogio() - visto[1] < (CACHE_PRONTA if visto[0] else CACHE_NAO):
            return visto[0]
    cod, _, _ = rodar(cmd, 20)
    with _HF_TRAVA:
        cache[chave] = (cod == 0, relogio())
    return cod == 0


def projects_dir_wsl(existe=os.path.isdir):
    """Pasta de sessões do claude na distro vista pelo Windows; None se nenhuma das formas existe."""
    for raiz in ("\\\\wsl.localhost\\", "\\\\wsl$\\"):
        p = raiz + "tune-up\\home\\tuneup\\.claude\\projects"
        if existe(p):
            return p
    return None


def agora_wsl(rodar):
    """Relógio da distro em segundos desde 1970; None em qualquer falha."""
    try:
        cod, out, _ = rodar(argv_cru(["/usr/bin/date", "+%s"]), 20)
        return int(out.strip()) if cod == 0 else None
    except (ValueError, TypeError, AttributeError):
        return None


AMOSTRAS = [("R$99", "R$99"), ("$(id)", "$(id)"), ("crase", "a`id`b"), ("aspas simples", "it's"),
            ("aspas duplas", 'diz "oi"'), ("barra invertida", "C:\\pasta\\"), ("%PATH%", "%PATH%"),
            ("ação", "ação"), ("settings", json.dumps({"permissions": {"allow": ["Bash(git log:*)"]},
                                                       "caminho": "C:\\Users\\Jo\u00e3o\\x", "t": 'a "b" \\ c'}))]
HEX_PY = "import os,sys;print(os.fsencode(sys.argv[1]).hex())"


def medir_argv(rodar_lista=None):
    """M9a: cada amostra chega byte a byte ao python3 da distro. 0 = ok, 1 = diferente, 2 = não medido."""
    if sys.platform != "win32":
        print("--medir-argv só roda no Windows.")
        return 2
    rodar_lista = rodar_lista or (lambda c: subprocess.run(c, capture_output=True, timeout=60, shell=False,
                                                           stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW))
    falhou = False
    for nome, amostra in AMOSTRAS:
        try:
            r = rodar_lista(argv_cru(["/usr/bin/python3", "-I", "-c", HEX_PY, amostra]))
        except (OSError, subprocess.TimeoutExpired):
            print("NAO MEDIDO")
            return 2
        if r.returncode != 0:
            print("NAO MEDIDO")
            return 2
        if r.stdout.decode("ascii", "replace").strip() == amostra.encode("utf-8").hex():
            print("M9a: OK %s" % nome)
        else:
            print("M9a: FALHOU %s" % nome)
            falhou = True
    return 1 if falhou else 0


if __name__ == "__main__":
    if sys.argv[1:] != ["--medir-argv"]:
        print("uso: python -I painel/wsl.py --medir-argv")
        sys.exit(2)
    sys.exit(medir_argv())
