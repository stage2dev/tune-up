"""Preparo, passos 3 a 5: arquivos da Evolution, Evolution no ar e serviço de Vendas ligado. Nunca troca a chave,
nunca mexe num .env que já existe, nunca faz `down`, nunca apaga volume, contêiner ou instância."""
import json
import os
import sys
import urllib.parse

from servico import evolution_local, pasta, travas
from servico.conectores.evolution import VAR_CHAVE, VAR_URL
from servico.preparo_docker import achar_docker
from servico.preparo_sistema import dono, esperar, falhou, feito, ultimas

SERVICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servico.py")
TEMPO_PULL = 1800
TEMPO_UP = 600
TEMPO_PS = 60
ESPERA_EVOLUTION = 300
ESPERA_SERVICO = 60
ESPERA_SONDA = 90   # --so-servico: depois de reiniciar, a porta abre antes de a Evolution responder


LISTAS = {"servico": evolution_local.PORTAS_SERVICO, "evolution": evolution_local.PORTAS_EVOLUTION}


def _porta(ex, desejada, nome):
    """A porta pedida, ou a primeira livre da lista fixa do `nome` (nunca uma aleatória); a escolhida fica no estado.
    None = nenhuma livre."""
    for porta in [desejada] + [p for p in LISTAS[nome] if p != desejada]:
        if ex.sistema.porta_livre(porta):
            if porta != desejada:
                ex.registrar("porta %d (%s) ocupada por outro programa; uso %d" % (desejada, nome, porta))
            ex.portas[nome] = porta
            return porta
    return None


def _sem_porta(ex, nome):
    lista = LISTAS[nome]
    o_que = "o WhatsApp" if nome == "evolution" else "o serviço de Vendas"
    return dono("As portas %d a %d, que %s usa, estão todas ocupadas por outros programas. Não liguei nada. Rode este "
                "comando num terminal para ver qual programa usa a primeira, feche esse programa e clique de novo."
                % (lista[0], lista[-1], o_que), _quem_usa(ex, lista[0]))


def evolution_preparada(ex):
    env = evolution_local.caminho_env(ex.pasta_dados)
    if os.path.exists(env):
        if not evolution_local.ler_ambiente(ex.pasta_dados):
            return dono("O arquivo de configuração do WhatsApp existe, mas está incompleto. Não mexi nele, para não "
                        "perder o que já está guardado. Peça ajuda a quem instalou o plugin (README, \"Fazer à mão\").")
        return feito("Os arquivos da Evolution já estavam prontos (não mexi neles).")
    porta_evolution = _porta(ex, ex.porta_evolution, "evolution")
    if porta_evolution is None:
        return _sem_porta(ex, "evolution")
    porta_servico = _porta(ex, ex.porta_servico(), "servico")
    if porta_servico is None:
        return _sem_porta(ex, "servico")
    try:
        evolution_local.preparar(ex.raiz, ex.base, porta_servico, porta_evolution)
    except evolution_local.JaPreparado:
        return feito("Os arquivos da Evolution já estavam prontos (não mexi neles).")
    except (ValueError, OSError, pasta.PastaRecusada) as e:
        return falhou("Não consegui preparar os arquivos da Evolution.", str(e))
    return feito("Preparei os arquivos da Evolution (porta %d em 127.0.0.1)." % porta_evolution)


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
    _, saida = ex.sistema.rodar(compose + ["-f", arquivo, "ps"], TEMPO_PS, pasta_ev)   # só leitura: o estado de cada
    ex.registrar("compose ps (fim):\n%s" % (ultimas(saida) or ""))                     # contêiner, mascarado no log
    return falhou("A Evolution não respondeu em %d minutos. Clique de novo; se repetir, veja o log do preparo."
                  % (ESPERA_EVOLUTION // 60), ultimas(saida))


def _reiniciar(ex):
    """O serviço rodando começou antes de o .env da Evolution existir (a trava marca a hora em que ele começou): ele
    não leu a chave e precisa ser reiniciado. Com a Evolution de outro endereço, não há .env para comparar."""
    if ex.externa:
        return False
    try:
        return os.path.getmtime(evolution_local.caminho_env(ex.pasta_dados)) > os.path.getmtime(
            os.path.join(ex.pasta_dados, travas.ARQUIVO_TRAVA))
    except OSError:
        return False


def _sondar_antes(ex):
    """--so-servico: confere (só leitura) se a Evolution responde antes de ligar o serviço, esperando até
    ESPERA_SONDA s (ela pode ainda estar subindo). None = responde. Os textos dizem só "clique de novo": a tela mostra
    "Ligar o serviço" (Evolution de outro endereço) ou "Tentar de novo" (o preparo completo)."""
    if ex.externa:
        url, chave = ex.sistema.var(VAR_URL), ex.sistema.var(VAR_CHAVE) or ""
    else:
        ambiente = evolution_local.ler_ambiente(ex.pasta_dados)
        url, chave = ambiente.get(VAR_URL), ambiente.get(VAR_CHAVE) or ""
    if url and esperar(ex, lambda: _sondar(ex, url, chave)[1], ESPERA_SONDA, "a Evolution responder"):
        return None
    if ex.externa:
        return falhou("A Evolution do endereço configurado (VENDAS_EVOLUTION_URL) não respondeu com a chave "
                      "configurada (VENDAS_EVOLUTION_CHAVE). Confira os dois e clique de novo.")
    return falhou("O WhatsApp deste computador não respondeu em %d s, então não liguei o serviço. Clique de novo: "
                  "o preparo completo liga o que faltar." % ESPERA_SONDA)


def servico_rodando(pasta_dados):
    """A trava do serviço ocupada = um serviço de Vendas está rodando para este projeto (só sonda: não a cria nem
    muda a hora dela, que marca quando o serviço começou)."""
    return travas.ocupada(pasta_dados)


def _ler_final(caminho, n=15):
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            return ultimas(f.read()[-20000:], n)
    except OSError:
        return None


def servico_ligado(ex):
    if ex.so_servico:
        r = _sondar_antes(ex)
        if r is not None:
            return r
    if servico_rodando(ex.pasta_dados):
        if _reiniciar(ex):
            return dono("O serviço de Vendas já estava ligado antes de o WhatsApp ficar pronto, então ainda não sabe "
                        "falar com ele. Reinicie o serviço de Vendas: feche a janela em que ele roda (ou reinicie o "
                        "computador) e depois clique em \"Ligar o serviço\".")
        return feito("O serviço de Vendas já está ligado.")
    s = ex.sistema
    porta = _porta(ex, ex.porta_servico(), "servico")
    if porta is None:
        return _sem_porta(ex, "servico")
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
