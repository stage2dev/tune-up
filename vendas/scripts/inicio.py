"""SessionStart do tune-up-vendas: UMA linha quando o projeto liga a tela Vendas e o WhatsApp ainda não está
preparado; nada em qualquer outro caso. Só lê arquivos (painel.json do projeto, embutidos-ligados.json do painel, a pasta de dados externa e o estado do
preparo); sem rede, sem banco, sem ler o .env. Qualquer erro = silêncio e saída 0. Python 3.9, só biblioteca padrão."""
import importlib.util
import json
import os
import re
import stat
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINHA = ("tune-up: o WhatsApp deste projeto ainda não está preparado. No painel, tela Vendas, aba Conexão, o "
         "botão \"Preparar tudo\" faz isso (ou use /tune-up:instalar).")
PAINEL_MAX = 64 * 1024   # = config.LIMITE_JSON
ESTADO_MAX = 4096        # = embutidos.MAX_BYTES
EMBUTIDOS = ("estudio", "vendas")   # = ids de painel/embutidos.EMBUTIDOS (um valor não booleano desliga tudo)
RE_PACOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")   # = config.RE_PACOTE


def _carregar(nome):
    spec = importlib.util.spec_from_file_location("tune_up_vendas_inicio_" + nome,
                                                  os.path.join(PLUGIN, "servico", nome + ".py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def raiz_do_projeto(cwd):
    """Primeira pasta com a pasta .tune-up subindo a partir do cwd (= o passo "cwd" de config.achar_raiz;
    painel.json é opcional), ou None."""
    atual = os.path.realpath(cwd)
    while True:
        if os.path.isdir(os.path.join(atual, ".tune-up")):
            return atual
        acima = os.path.dirname(atual)
        if acima == atual:
            return None
        atual = acima


def _painel(raiz):
    """painel.json como o painel o lê (config._ler_arquivo): ilegível ou grande demais = {}."""
    try:
        with open(os.path.join(raiz, ".tune-up", "painel.json"), "rb") as f:
            bruto = f.read(PAINEL_MAX + 1)
        dado = json.loads(bruto.decode("utf-8-sig")) if len(bruto) <= PAINEL_MAX else {}
    except (OSError, ValueError):
        return {}
    return dado if isinstance(dado, dict) else {}


def _dados(raiz, conf):
    """A pasta de dados do painel para este projeto, com a regra de config.carregar (dados_dir)."""
    tune_up = os.path.join(raiz, ".tune-up")
    nome = conf.get("pacote", "painel-projeto")
    if not isinstance(nome, str) or not RE_PACOTE.match(nome):
        nome = "painel-projeto"
    pasta = os.path.join(tune_up, nome)
    if not os.path.lexists(pasta):
        return os.path.join(pasta, "dados")
    if os.path.isdir(pasta) and os.path.realpath(pasta).startswith(os.path.realpath(tune_up).rstrip(os.sep) + os.sep):
        return os.path.join(os.path.realpath(pasta), "dados")
    return os.path.join(tune_up, "painel-dados")


def _estado(dados):
    """embutidos-ligados.json como painel/embutidos._ler: {} sem arquivo; None (tudo desligado) se é atalho,
    não é arquivo comum, passa de 4 KB, não é JSON ou um id conhecido não é true/false."""
    try:
        fd = os.open(os.path.join(dados, "embutidos-ligados.json"),
                     os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return {}
    except OSError:
        return None
    try:
        with os.fdopen(fd, "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                return None
            bruto = f.read(ESTADO_MAX + 1)
        dado = json.loads(bruto.decode("utf-8")) if len(bruto) <= ESTADO_MAX else None
    except (OSError, ValueError):
        return None
    if not isinstance(dado, dict) or any(not isinstance(dado[i], bool) for i in EMBUTIDOS if i in dado):
        return None
    return dado


def modulo_ligado(raiz):
    """Vendas ligado pela tela Módulos (true/false no arquivo vence); a linha antiga do plugin separado
    ("tune-up-vendas@...:vendas" em modulos_de_plugins) conta enquanto o arquivo não fala de vendas."""
    conf = _painel(raiz)
    estado = _estado(_dados(raiz, conf))
    if estado is None:
        return False
    lista = conf.get("modulos_de_plugins")
    antiga = isinstance(lista, list) and any(
        isinstance(e, str) and e.rpartition(":")[2] == "vendas"
        and e.rpartition(":")[0].partition("@")[0] == "tune-up-vendas" for e in lista)
    return estado.get("vendas", antiga) is True


def preparado(raiz, base=None):
    """False se faltam os arquivos da Evolution ou se o último preparo parou (falhou, precisa do dono, interrompido).
    Um preparo rodando agora conta como preparado (não avisa no meio dele)."""
    pasta = _carregar("pasta").caminho_da_pasta(raiz, base)
    try:
        with open(os.path.join(pasta, "preparo.json"), encoding="utf-8") as f:
            estado = json.load(f)
    except (OSError, ValueError):
        estado = None
    final = estado.get("estado") if isinstance(estado, dict) else None
    if final == "rodando":   # vivo só com a trava ocupada (um pid vivo pode ter sido reaproveitado)
        return _carregar("travas").ocupada(pasta, "preparo.trava")
    if not all(os.path.isfile(os.path.join(pasta, "evolution", n)) for n in ("compose.yml", ".env")):
        return False
    return final not in ("falhou", "precisa_do_dono")


def linha(entrada, base=None):
    """O texto a mostrar ("" = nada) para a entrada JSON do gancho. Nunca levanta."""
    try:
        dados = json.loads(entrada or "{}")
        cwd = dados.get("cwd") if isinstance(dados, dict) else None
        raiz = raiz_do_projeto(cwd if isinstance(cwd, str) and cwd else os.getcwd())
        if os.environ.get("VENDAS_EVOLUTION_URL"):   # Evolution de outro endereço: nada a preparar aqui
            return ""
        if raiz is None or not modulo_ligado(raiz) or preparado(raiz, base):
            return ""
        return LINHA
    except Exception:   # o gancho nunca atrapalha a sessão
        return ""


def main():
    try:
        entrada = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read(1024 * 1024)
        texto = linha(entrada)
        if texto:
            print(texto)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
