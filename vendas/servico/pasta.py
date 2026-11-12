"""Pasta de dados FORA do projeto: banco, logs e segredos nunca entram na árvore do projeto nem numa pasta sincronizada.
macOS: ~/Library/Application Support/tune-up-vendas/<hash>/; Linux: $XDG_DATA_HOME ou ~/.local/share; Windows: %LOCALAPPDATA%.
<hash> = sha256 do realpath da raiz do projeto (em minúsculas em disco que ignora maiúsculas).
A base só muda por argumento explícito (testes), nunca por pedido."""
import hashlib
import os
import sys

NOME = "tune-up-vendas"
MARCAS_SYNC = (".stfolder", ".stignore")


class PastaRecusada(RuntimeError):
    pass


def _real(caminho):
    return os.path.normcase(os.path.realpath(os.path.abspath(caminho)))


def pasta_base(plataforma=None, ambiente=None):
    plataforma = plataforma or sys.platform
    ambiente = os.environ if ambiente is None else ambiente
    casa = os.path.expanduser("~")
    if plataforma.startswith("win"):
        raiz = ambiente.get("LOCALAPPDATA") or os.path.join(casa, "AppData", "Local")
    elif plataforma == "darwin":
        raiz = os.path.join(casa, "Library", "Application Support")
    else:
        raiz = ambiente.get("XDG_DATA_HOME") or os.path.join(casa, ".local", "share")
    return os.path.join(raiz, NOME)


def validar(pasta, raiz_projeto):
    """Recusa a pasta se ficar dentro da raiz do projeto ou se ela ou um nível acima tiver .stfolder/.stignore."""
    alvo, raiz = _real(pasta), _real(raiz_projeto)
    if alvo == raiz or alvo.startswith(raiz.rstrip(os.sep) + os.sep):
        raise PastaRecusada("a pasta de dados %s fica dentro do projeto %s; use uma pasta fora dele" % (alvo, raiz))
    atual = alvo
    while True:
        for marca in MARCAS_SYNC:
            if os.path.exists(os.path.join(atual, marca)):
                raise PastaRecusada("a pasta de dados %s fica sob uma pasta sincronizada (%s em %s)"
                                    % (alvo, marca, atual))
        acima = os.path.dirname(atual)
        if acima == atual:
            return alvo
        atual = acima


def identidade(raiz_projeto):
    """realpath da raiz; em minúsculas quando o disco ignora maiúsculas (o mesmo projeto, a mesma pasta de dados)."""
    real = os.path.realpath(raiz_projeto)
    trocado = real.swapcase()
    if trocado != real:
        try:
            if os.path.samefile(real, trocado):  # o disco achou o mesmo arquivo com a caixa trocada
                return real.lower()
        except OSError:
            pass
    return real


def caminho_da_pasta(raiz_projeto, base=None):
    """Só o caminho da pasta de dados deste projeto: não cria nem valida (leitura pela tela)."""
    marca = hashlib.sha256(identidade(raiz_projeto).encode("utf-8")).hexdigest()[:16]
    return os.path.join(base or pasta_base(), marca)


def pasta_de_dados(raiz_projeto, base=None):
    """Cria (0700) e devolve a pasta de dados deste projeto. Recusa com PastaRecusada antes de criar qualquer coisa."""
    pasta = caminho_da_pasta(raiz_projeto, base)
    validar(pasta, raiz_projeto)
    os.makedirs(pasta, mode=0o700, exist_ok=True)
    if os.name != "nt":
        os.chmod(pasta, 0o700)
    return pasta


def arquivo_privado(caminho):
    """Garante o arquivo com modo 0600 (onde o sistema tem esse modo) e devolve o caminho."""
    fd = os.open(caminho, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    if os.name != "nt":
        os.chmod(caminho, 0o600)
    return caminho
