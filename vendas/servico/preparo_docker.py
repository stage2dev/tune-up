"""Preparo, passos 1 e 2: achar (ou instalar) o Docker e ligá-lo. Nunca roda sudo e nunca manda um script baixado
para um shell: o que pede senha ou o instalador do Homebrew vira um comando para o dono colar no terminal."""
import os

from servico.preparo_sistema import dono, esperar, falhou, feito, ultimas

HOMEBREW = '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
BREW_TUDO = ("install", "colima", "docker", "docker-compose")
WINGET = ("install", "-e", "--id", "Docker.DockerDesktop", "--accept-package-agreements",
          "--accept-source-agreements")
URL_WINDOWS = "https://docs.docker.com/desktop/setup/install/windows-install/"
URL_LINUX = "https://docs.docker.com/engine/install/"
AVISO_WINDOWS = ("O Windows pode pedir confirmação e pedir para reiniciar o computador. O Docker Desktop é pago "
                 "para empresas maiores (veja a licença no site da Docker).")
GRUPO = "sudo usermod -aG docker $USER"
LINUX = (  # (ids do /etc/os-release, comando de pacotes da distribuição)
    (("ubuntu",), "sudo apt-get update && sudo apt-get install -y docker.io docker-compose-v2"),
    (("debian",), "sudo apt-get update && sudo apt-get install -y docker.io docker-compose"),
    (("fedora",), "sudo dnf install -y moby-engine docker-compose"),
    (("arch",), "sudo pacman -S --needed docker docker-compose"),
)
TEMPO_CURTO = 60
TEMPO_INSTALAR = 1800
TEMPO_COLIMA = 900
ESPERA_LIGAR = 240


def achar_docker(ex):
    """(docker, comando do compose ou None), ou None sem docker. Compose: `docker compose`, senão docker-compose."""
    s = ex.sistema
    docker = s.achar("docker")
    if not docker:
        return None
    codigo, _ = s.rodar([docker, "compose", "version"], TEMPO_CURTO)
    if codigo == 0:
        return docker, [docker, "compose"]
    avulso = s.achar("docker-compose")
    return docker, ([avulso] if avulso else None)


def _guardar(ex, achado):
    ex.dados["docker"], ex.dados["compose"] = achado
    return feito("O Docker e o compose estão instalados.", " ".join(os.path.basename(p) for p in achado[1]))


def docker_instalado(ex):
    achado = achar_docker(ex)
    if achado and achado[1]:
        return _guardar(ex, achado)
    s = ex.sistema
    if s.mac:
        r = _instalar_mac(ex, achado)
    elif s.windows:
        r = _instalar_windows(ex)
    else:
        return _linux(ex, achado)
    if r is not None:
        return r
    achado = achar_docker(ex)
    if achado and achado[1]:
        _guardar(ex, achado)
        return feito("Instalei o Docker.", "agora: " + " ".join(os.path.basename(p) for p in achado[1]))
    if s.windows:
        return dono("Instalei o Docker Desktop, mas o Windows ainda não o encontra. Reinicie o computador, abra o "
                    "Docker Desktop uma vez e clique de novo. " + AVISO_WINDOWS)
    return falhou("A instalação terminou, mas o docker ou o compose ainda não aparecem.")


def _instalar_mac(ex, achado):
    s = ex.sistema
    brew = s.achar("brew")
    if not brew:
        return dono("Para instalar o Docker sem pedir senha, falta o Homebrew. Cole este comando num terminal, siga "
                    "o que ele pedir e depois clique de novo.", HOMEBREW)
    pacotes = list(BREW_TUDO) if achado is None else ["install", "docker-compose"]
    ex.progresso("Instalando com o Homebrew: %s (pode levar alguns minutos)." % " ".join(pacotes[1:]))
    codigo, saida = s.rodar([brew] + pacotes, TEMPO_INSTALAR)
    ex.registrar(saida)
    if codigo != 0:
        return falhou("O Homebrew não conseguiu instalar o Docker. Veja o detalhe e tente de novo.", ultimas(saida))
    return None


def _instalar_windows(ex):
    s = ex.sistema
    winget = s.achar("winget")
    if not winget:
        return dono("Baixe e instale o Docker Desktop pela página oficial e clique de novo. " + AVISO_WINDOWS,
                    URL_WINDOWS)
    ex.progresso("Instalando o Docker Desktop com o winget. " + AVISO_WINDOWS)
    codigo, saida = s.rodar([winget] + list(WINGET), TEMPO_INSTALAR)
    ex.registrar(saida)
    if codigo != 0:
        return falhou("O winget não conseguiu instalar o Docker Desktop. " + AVISO_WINDOWS, ultimas(saida))
    return None


def comando_linux(os_release):
    """Comando de pacotes da distribuição (pelo ID/ID_LIKE do /etc/os-release), ou None se não conheço a distro."""
    campos = {}
    for linha in (os_release or "").splitlines():
        chave, igual, valor = linha.partition("=")
        if igual:
            campos[chave.strip()] = valor.strip().strip('"').lower()
    ids = [campos.get("ID", "")] + campos.get("ID_LIKE", "").split()
    for conhecidos, comando in LINUX:
        for i in ids:
            if i in conhecidos:
                return "%s && sudo systemctl enable --now docker && %s" % (comando, GRUPO)
    return None


def _linux(ex, achado):
    comando = comando_linux(ex.sistema.ler_texto("/etc/os-release"))
    o_que = "o compose do Docker" if achado else "o Docker"
    if comando is None:
        return dono("Falta %s. Instale pelo guia oficial da sua distribuição, saia e entre de novo na sessão e "
                    "clique de novo." % o_que, URL_LINUX)
    return dono("Falta %s. Instalar no Linux pede senha (sudo): cole este comando num terminal, saia e entre de novo "
                "na sessão (para o grupo docker valer) e clique de novo." % o_que, comando)


def _responde(ex, docker):
    codigo, saida = ex.sistema.rodar([docker, "info"], TEMPO_CURTO)
    if codigo == 0:
        return True
    ex.dados["docker_info"] = saida
    return False


def docker_ligado(ex):
    s = ex.sistema
    docker = ex.dados.get("docker") or s.achar("docker")
    if not docker:
        return falhou("Não achei o docker; rode o preparo de novo desde o começo.")
    if _responde(ex, docker):
        return feito("O Docker já está ligado.")
    if s.mac:
        r = _ligar_mac(ex)
    elif s.windows:
        r = _ligar_windows(ex)
    elif "permission denied" in (ex.dados.get("docker_info") or "").lower():
        return dono("O Docker está ligado, mas este usuário não pode usá-lo. Cole este comando num terminal, saia e "
                    "entre de novo na sessão e clique de novo.", GRUPO)
    else:
        return dono("O Docker está instalado, mas desligado. Ligá-lo no Linux pede senha (sudo): cole este comando "
                    "num terminal e clique de novo.", "sudo systemctl start docker")
    if r is not None:
        return r
    if esperar(ex, lambda: _responde(ex, docker), ESPERA_LIGAR, "o Docker ligar"):
        return feito("Liguei o Docker.")
    return falhou("O Docker não ligou em %d minutos. Abra-o, espere ele terminar de ligar e clique de novo."
                  % (ESPERA_LIGAR // 60), ultimas(ex.dados.get("docker_info")))


def _ligar_mac(ex):
    s = ex.sistema
    colima = s.achar("colima")
    if colima:
        ex.progresso("Ligando o colima (na primeira vez ele baixa uma máquina virtual e demora alguns minutos).")
        codigo, saida = s.rodar([colima, "start"], TEMPO_COLIMA)
        ex.registrar(saida)
        if codigo != 0:
            return falhou("O colima não ligou. Veja o detalhe e tente de novo.", ultimas(saida))
        return None
    if s.existe("/Applications/Docker.app"):
        ex.progresso("Abrindo o Docker Desktop.")
        codigo, saida = s.rodar(["/usr/bin/open", "-a", "Docker"], TEMPO_CURTO)
        ex.registrar(saida)
        if codigo != 0:
            return falhou("Não consegui abrir o Docker Desktop.", ultimas(saida))
        return None
    return dono("O docker está instalado, mas não achei como ligá-lo (nem colima nem Docker Desktop). Cole este "
                "comando num terminal e clique de novo.", "brew install colima")


def _ligar_windows(ex):
    s = ex.sistema
    arquivos = s.var("ProgramFiles") or r"C:\Program Files"
    exe = os.path.join(arquivos, "Docker", "Docker", "Docker Desktop.exe")
    if not s.existe(exe):
        return dono("Abra o Docker Desktop pelo menu Iniciar, espere ele ligar e clique de novo.")
    ex.progresso("Abrindo o Docker Desktop.")
    try:
        s.soltar([exe], ex.caminho_log)
    except OSError as e:
        return falhou("Não consegui abrir o Docker Desktop.", str(e.strerror or e))
    return None
