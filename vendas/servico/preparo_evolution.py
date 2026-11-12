"""Preparo, passos 3 a 5: arquivos da Evolution, Evolution no ar e serviço de Vendas ligado. Nunca usa --refazer,
nunca mexe num .env que já existe, nunca faz `down`, nunca apaga volume, contêiner ou instância."""
import json
import os
import shlex
import sys
import urllib.parse

from servico import evolution_local, pasta, travas
from servico.conectores.evolution import VAR_CHAVE, VAR_URL
from servico.preparo_docker import achar_docker
from servico.preparo_sistema import dono, esperar, falhou, feito, ultimas

SERVICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servico.py")
EVOLUTION_LOCAL = os.path.join(os.path.dirname(SERVICO), "evolution_local.py")
PYTHON = "python" if os.name == "nt" else "python3"
TEMPO_PULL = 1800
TEMPO_UP = 600
ESPERA_EVOLUTION = 300
ESPERA_SERVICO = 60


def _porta(ex, desejada, nome):
    """A porta pedida, ou uma livre quando outro programa já ocupa a pedida (a escolhida fica no estado)."""
    s = ex.sistema
    if s.porta_livre(desejada):
        porta = desejada
    else:
        porta = s.porta_qualquer()
        ex.registrar("porta %d (%s) ocupada por outro programa; uso %d" % (desejada, nome, porta))
    ex.portas[nome] = porta
    return porta


def evolution_preparada(ex):
    env = evolution_local.caminho_env(ex.pasta_dados)
    if os.path.exists(env):
        if not evolution_local.ler_ambiente(ex.pasta_dados):
            return dono("O arquivo de configuração da Evolution existe, mas está incompleto. Não mexi nele. Se quiser "
                        "gerar uma chave nova, rode este comando num terminal e clique de novo.",
                        "%s -B %s preparar --projeto %s --refazer" % (PYTHON, _citar(EVOLUTION_LOCAL), _citar(ex.raiz)))
        return feito("Os arquivos da Evolution já estavam prontos (não mexi neles).")
    porta_evolution = _porta(ex, ex.porta_evolution, "evolution")
    porta_servico = _porta(ex, ex.porta_servico(), "servico")
    try:
        evolution_local.preparar(ex.raiz, ex.base, porta_servico, porta_evolution)
    except evolution_local.JaPreparado:
        return feito("Os arquivos da Evolution já estavam prontos (não mexi neles).")
    except (ValueError, OSError, pasta.PastaRecusada) as e:
        return falhou("Não consegui preparar os arquivos da Evolution.", str(e))
    return feito("Preparei os arquivos da Evolution (porta %d em 127.0.0.1)." % porta_evolution)


def _citar(caminho):
    return '"%s"' % caminho if os.name == "nt" else shlex.quote(caminho)


def _sondar(ex, url, chave):
    """(código HTTP, é a nossa Evolution). Só é a nossa quando aceita a chave do .env (200) E devolve a lista JSON de
    instâncias ([] quando não há): um servidor "pega tudo" que responde 200 com HTML não é a Evolution."""
    codigo, corpo = ex.sistema.http(url.rstrip("/") + "/instance/fetchInstances", cabecalhos={"apikey": chave})
    if codigo != 200:
        return codigo, False
    try:
        return codigo, isinstance(json.loads((corpo or b"").decode("utf-8")), list)
    except ValueError:
        return codigo, False


def _quem_usa(ex, porta):
    if ex.sistema.windows:
        return "netstat -ano | findstr :%d" % porta
    return "lsof -nP -iTCP:%d -sTCP:LISTEN" % porta


def evolution_no_ar(ex):
    ambiente = evolution_local.ler_ambiente(ex.pasta_dados)
    url, chave = ambiente.get(VAR_URL), ambiente.get(VAR_CHAVE)
    if not url or not chave:
        return falhou("Falta a configuração da Evolution; rode o preparo de novo.")
    codigo, nossa = _sondar(ex, url, chave)
    if nossa:
        return feito("A Evolution já está no ar em %s." % url)
    porta = urllib.parse.urlsplit(url).port
    if codigo is not None and porta:   # alguém respondeu HTTP nessa porta, mas não é a nossa Evolution
        return dono("A porta %d da Evolution já é usada por outro programa (respondeu HTTP %d e não respondeu como a "
                    "Evolution). Não liguei nada. Rode este comando num terminal para ver qual programa é, feche "
                    "esse programa e clique de novo." % (porta, codigo), _quem_usa(ex, porta))
    compose = ex.dados.get("compose")
    if not compose:
        achado = achar_docker(ex)
        compose = achado[1] if achado else None
    if not compose:
        return falhou("Não achei o compose do Docker; rode o preparo de novo desde o começo.")
    arquivo = os.path.join(evolution_local.pasta_evolution(ex.pasta_dados), evolution_local.ARQUIVO_COMPOSE)
    pasta_ev = os.path.dirname(arquivo)
    ex.progresso("Baixando a Evolution, o Postgres e o Redis (na primeira vez leva vários minutos).")
    codigo, saida = ex.sistema.rodar(compose + ["-f", arquivo, "pull"], TEMPO_PULL, pasta_ev)
    ex.registrar(saida)
    if codigo != 0:
        return falhou("Não consegui baixar a Evolution. Confira a internet e o Docker ligado e clique de novo.",
                      ultimas(saida))
    ex.progresso("Ligando a Evolution.")
    codigo, saida = ex.sistema.rodar(compose + ["-f", arquivo, "up", "-d"], TEMPO_UP, pasta_ev)
    ex.registrar(saida)
    if codigo != 0:
        return falhou("O Docker não conseguiu ligar a Evolution. Veja o detalhe e clique de novo.", ultimas(saida))
    if esperar(ex, lambda: _sondar(ex, url, chave)[1], ESPERA_EVOLUTION, "a Evolution responder"):
        return feito("A Evolution está no ar em %s." % url)
    return falhou("A Evolution não respondeu em %d minutos. Clique de novo; se repetir, veja o log do preparo."
                  % (ESPERA_EVOLUTION // 60), ultimas(saida))


def servico_rodando(pasta_dados):
    """A trava do serviço ocupada = um serviço de Vendas está rodando para este projeto."""
    trava = travas.TravaDoProcesso(pasta_dados)
    try:
        trava.pegar()
    except travas.TravaOcupada:
        return True
    trava.soltar()
    return False


def _ler_final(caminho, n=15):
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            return ultimas(f.read()[-20000:], n)
    except OSError:
        return None


def servico_ligado(ex):
    if servico_rodando(ex.pasta_dados):
        return feito("O serviço de Vendas já está ligado.")
    s = ex.sistema
    porta = _porta(ex, ex.porta_servico(), "servico")
    args = [sys.executable, "-B", SERVICO, "--projeto", ex.raiz, "--porta", str(porta), "--painel", ex.painel]
    if ex.base:
        args += ["--base", ex.base]
    log = ex.caminho_log_servico
    ex.progresso("Ligando o serviço de Vendas na porta %d." % porta)
    try:
        processo = s.soltar(args, log)
    except OSError as e:
        return falhou("Não consegui ligar o serviço de Vendas.", str(e.strerror or e))
    marca = os.path.basename(ex.pasta_dados)

    def pronto():
        if processo.poll() is not None:
            return "saiu"
        codigo, corpo = s.http("http://127.0.0.1:%d/saude" % porta)
        try:
            return codigo == 200 and json.loads(corpo.decode("utf-8")).get("marca") == marca
        except (ValueError, AttributeError):
            return False

    r = esperar(ex, pronto, ESPERA_SERVICO, "o serviço de Vendas responder")
    if r is True:
        return feito("O serviço de Vendas está ligado na porta %d." % porta)
    if r == "saiu":
        return falhou("O serviço de Vendas parou logo ao ligar. Veja o detalhe.", _ler_final(log))
    return falhou("O serviço de Vendas não respondeu em %d s. Ele pode continuar subindo; clique de novo em "
                  "seguida." % ESPERA_SERVICO, _ler_final(log))
