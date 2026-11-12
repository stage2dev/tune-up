"""Serviço de Vendas: processo próprio em 127.0.0.1, ligado SÓ por comando do dono num terminal (sem daemon).

    python3 -B <plugin>/servico/servico.py --projeto <raiz> [--porta 8791] [--painel http://127.0.0.1:8787]

Um processo por projeto (trava não bloqueante na pasta de dados); token de envio novo a cada subida (0600);
segredo do webhook fixo (0600); batimento no banco a cada BATIMENTO_S; SIGINT/SIGTERM param limpo."""
import os
import sys

if __name__ == "__main__":
    # rodando como script, sys.path[0] é esta pasta e "servico" seria este arquivo: troca pela pasta do plugin
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.dont_write_bytecode = True

import argparse  # noqa: E402
import itertools  # noqa: E402
import secrets  # noqa: E402
import signal  # noqa: E402
import threading  # noqa: E402

from servico import (agendador, banco, candidatos, cerebro, entender, evolution_local, midia, openai_cliente, pasta, places, portao, rascunhos,  # noqa: E402
                     revisao, recebimento, rotas, travas, voz_cliente)
from servico.atendente import Atendente  # noqa: E402
from servico.conectores import evolution  # noqa: E402

PORTA = 8791
PAINEL = "http://127.0.0.1:8787"
BATIMENTO_S = 3
ARQUIVO_TOKEN = "token_envio"
ARQUIVO_SEGREDO = "segredo_webhook"
ESPERAS_RECUPERAR = (5, 15, 30, 60)   # segundos entre tentativas de buscar o que chegou parado (a última repete)


def argumentos(argv):
    p = argparse.ArgumentParser(prog="servico.py", description="Serviço local do tune-up-vendas.")
    p.add_argument("--projeto", required=True, help="raiz do projeto")
    p.add_argument("--porta", type=int, default=PORTA, help="porta em 127.0.0.1 (0 = qualquer livre)")
    p.add_argument("--painel", default=PAINEL, help="origem exata do painel (esquema://host:porta)")
    p.add_argument("--base", default=None, help="pasta base dos dados (só para testes)")
    p.add_argument("--openai-url", default=os.environ.get(openai_cliente.VAR_URL) or openai_cliente.URL_PADRAO,
                   help="URL base da OpenAI (só para testes; padrão %s)" % openai_cliente.URL_PADRAO)
    p.add_argument("--places-url", default=os.environ.get(places.VAR_URL) or places.URL_PADRAO,
                   help="URL base do Google Places (só para testes; padrão %s)" % places.URL_PADRAO)
    p.add_argument("--elevenlabs-url", default=os.environ.get(voz_cliente.VAR_URL) or voz_cliente.URL_PADRAO,
                   help="URL base da ElevenLabs (só para testes; padrão %s)" % voz_cliente.URL_PADRAO)
    return p.parse_args(argv)


def bater_sempre(pasta_dados, parar):
    """Batimento numa conexão própria; uma falha avisa no stderr e tenta de novo na volta seguinte."""
    con = banco.abrir(pasta_dados)
    try:
        while True:
            try:
                banco.bater(con)
            except Exception as e:
                print("vendas: batimento falhou: %s" % type(e).__name__, file=sys.stderr)
            if parar.wait(BATIMENTO_S):
                return
    finally:
        con.close()


def rodar(args, avisar=print):
    """Sobe, serve até SIGINT/SIGTERM e para limpo. Devolve o código de saída."""
    if not 0 <= args.porta <= 65535:
        avisar("vendas: porta inválida: %d" % args.porta, file=sys.stderr)
        return 2
    try:
        painel = rotas.origem_do_painel(args.painel)
        raiz = os.path.realpath(args.projeto)
        if not os.path.isdir(raiz):
            raise ValueError("a raiz do projeto %s não existe" % raiz)
        pasta_dados = pasta.pasta_de_dados(raiz, base=args.base)
    except (ValueError, pasta.PastaRecusada) as e:
        avisar("vendas: não subi: %s" % e, file=sys.stderr)
        return 2
    trava = travas.TravaDoProcesso(pasta_dados)
    try:
        trava.pegar()
    except travas.TravaOcupada as e:
        avisar("vendas: não subi: %s" % e, file=sys.stderr)
        return 3
    caminho_token = os.path.join(pasta_dados, ARQUIVO_TOKEN)
    parar = threading.Event()
    try:
        con = banco.abrir(pasta_dados)
        try:
            recebimento.guardar_janela(con)  # antes do 1º batimento desta subida; só some quando a busca der certo
            incertos = portao.pendentes_para_incerto(con)  # caiu no meio de um envio: o dono decide, sem reenvio
            destravados = rascunhos.destravar_na_subida(con)  # caiu no meio de uma aprovação: depois do incerto
            banco.bater(con)
        finally:
            con.close()
        if incertos:
            avisar("vendas: %d envio(s) ficaram incertos na última parada; veja na tela" % incertos, file=sys.stderr)
        if destravados:
            avisar("vendas: %d rascunho(s) estavam sendo aprovados na última parada; quem saiu ficou aprovado, "
                   "o resto voltou para você decidir" % destravados, file=sys.stderr)
        token = secrets.token_urlsafe(32)
        travas.gravar_segredo(caminho_token, token)
        caminho_segredo = os.path.join(pasta_dados, ARQUIVO_SEGREDO)
        segredo_novo = travas.ler_segredo(caminho_segredo) is None
        segredo = travas.ler_ou_criar_segredo(caminho_segredo)
        app = rotas.App(pasta_dados, args.porta, painel, token, segredo)
        app.despachar = recebimento.Recebimento(lambda: app.conector)
        app.openai_url = args.openai_url
        app.places_url = args.places_url
        app.elevenlabs_url = args.elevenlabs_url
        app.raiz = raiz
        try:
            servidor = rotas.criar_servidor(app, args.porta)
        except OSError as e:
            avisar("vendas: não subi: a porta %d não abriu (%s)" % (args.porta, e.strerror or e), file=sys.stderr)
            return 4
        con = banco.abrir(pasta_dados)
        try:
            if rotas.conferir_segredo(con, segredo, segredo_novo):
                avisar("vendas: o segredo do webhook é novo; o modo voltou para 'Registra e conta' e a contagem de "
                       "válidos seguidos zerou (a Evolution ainda pode mandar o segredo antigo)", file=sys.stderr)
            banco.registrar_servico(con, app.porta, app.marca)  # a tela confere porta e projeto antes de agir
            midia.interrompidas(con)   # pendente de um processo anterior: o dono pede de novo, nada em laço
            importar_candidatos(con, raiz, avisar)
        finally:
            con.close()
        app.conector = conector(pasta_dados, app.porta, segredo, avisar)
        entende = lambda c, tipo: entender.ligado(c, pasta_dados, tipo)  # noqa: E731
        ia = Atendente(app.abrir, cerebro.Cerebro(pasta_dados, raiz, args.openai_url), lambda: app.conector,
                       app=app, entende=entende)
        recebimento.registrar_gancho(ia.receber)
        recebimento.registrar_entende(entende)
        baixador = midia.Baixador(app.abrir, lambda: app.conector, pasta_dados)
        midia.registrar_baixador(baixador)
        baixador.iniciar(parar)   # limpa a retenção na subida e uma vez por dia
        for sinal in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sinal, lambda *_: parar.set())
        batimento = threading.Thread(target=bater_sempre, args=(pasta_dados, parar), daemon=True)
        batimento.start()
        atendente = threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
        atendente.start()
        threading.Thread(target=recuperar, args=(app, parar), daemon=True).start()
        disparos = agendador.Agendador(app.abrir, lambda: app.conector,
                                       permitidos=lambda: list(cerebro.ler_links(raiz).values())).iniciar(parar)
        avisar("serviço de Vendas em http://127.0.0.1:%d (painel %s); Ctrl+C para parar" % (app.porta, painel),
               flush=True)
        while not parar.wait(0.5):
            pass
        servidor.shutdown()
        servidor.server_close()
        recebimento.registrar_gancho(None)
        recebimento.registrar_entende(None)
        midia.registrar_baixador(None)
        ia.parar()
        disparos.join(60)   # um envio no meio termina (o conector tem timeout) antes de sair
        batimento.join(BATIMENTO_S + 5)
        avisar("serviço de Vendas parado", flush=True)
        return 0
    finally:
        parar.set()
        _limpar(pasta_dados, caminho_token)
        trava.soltar()


def importar_candidatos(con, raiz, avisar=print):
    """Subida: importa (e apaga) o que o buscador deixou na pasta de candidatos. Pasta fora do pacote ou erro = aviso."""
    try:
        revisao.purgar(con)  # descartados há mais de 30 dias saem (antes da importação: aí podem voltar)
    except Exception as e:
        avisar("vendas: não consegui limpar os candidatos descartados (%s)" % type(e).__name__, file=sys.stderr)
    try:
        r = candidatos.importar(con, raiz)
    except candidatos.PastaRecusada as e:
        avisar("vendas: candidatos não importados: %s" % e, file=sys.stderr)
    except Exception as e:
        avisar("vendas: candidatos não importados (%s); os arquivos ficaram na pasta" % type(e).__name__,
               file=sys.stderr)
    else:
        if r["arquivos"]:
            avisar("vendas: " + candidatos.resumo(r), file=sys.stderr)


def recuperar(app, parar, esperas=ESPERAS_RECUPERAR):
    """Subida: busca no conector o que chegou com o serviço parado (o webhook pode chegar junto; dedupe por id).
    Falhou ou falta conector/instância: evento + aviso (uma vez por motivo) e tenta de novo com espera crescente até
    dar certo ou o serviço parar. A janela continua guardada para a próxima subida. Devolve True se buscou."""
    avisados = set()
    for tentativa in itertools.count():
        con = app.abrir()
        try:
            app.despachar.recuperar(con)
            return True
        except Exception as e:
            pendente = isinstance(e, recebimento.RecuperacaoPendente)
            tipo, motivo = ("recuperacao_pendente", str(e)) if pendente else ("recuperacao_falhou", type(e).__name__)
            if (tipo, motivo) not in avisados:
                avisados.add((tipo, motivo))
                print("vendas: ainda não busquei as mensagens de quando o serviço estava parado (%s); tento de novo"
                      % motivo, file=sys.stderr)
                try:
                    banco.registrar_evento(con, tipo, motivo)
                except Exception:
                    pass
        finally:
            con.close()
        if parar.wait(esperas[min(tentativa, len(esperas) - 1)]):
            return False


def conector(pasta_dados, porta, segredo, avisar=print):
    """Conector da Evolution pelo .env do preparar (o ambiente do terminal manda), ou None com aviso no stderr:
    sem conector, POST /enviar responde 503 até o dono configurar a Evolution."""
    env = evolution_local.caminho_env(pasta_dados)
    try:
        ambiente = evolution_local.ler_ambiente(pasta_dados)
    except (OSError, ValueError) as e:
        ambiente = {}
        avisar("vendas: não consegui ler %s (%s); sigo sem ele" % (env, getattr(e, "strerror", None)
                                                                   or type(e).__name__), file=sys.stderr)
    else:
        if not ambiente and os.path.exists(env):
            avisar("vendas: %s está incompleto (falta SERVER_URL ou AUTHENTICATION_API_KEY); rode de novo "
                   "evolution_local.py preparar --refazer" % env, file=sys.stderr)
    ambiente.update({k: os.environ[k] for k in (evolution.VAR_URL, evolution.VAR_CHAVE) if os.environ.get(k)})
    try:
        return evolution.Evolution.do_ambiente("http://%s:%d" % (rotas.HOST_DOCKER, porta), segredo, ambiente)
    except ValueError as e:
        avisar("vendas: nenhum conector de WhatsApp configurado (%s); o envio fica desligado. Rode "
               "evolution_local.py preparar ou defina as variáveis." % e, file=sys.stderr)
        return None


def _limpar(pasta_dados, caminho_token):
    """Saída: apaga o token de envio e o batimento deste processo (a tela passa a mostrar 'parado')."""
    try:
        os.remove(caminho_token)
    except FileNotFoundError:
        pass
    con = banco.abrir(pasta_dados)
    try:
        banco.gravar_config(con, "parado_em", banco.agora())  # a próxima subida busca o que chegou depois disso
        banco.parar_batimento(con)
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(rodar(argumentos(sys.argv[1:])))
