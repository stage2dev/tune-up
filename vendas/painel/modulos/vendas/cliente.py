"""Cliente do serviço de Vendas para as ações da tela. Toda ação passa por chamar(): a porta vem do banco DESTE
projeto (somente leitura), o batimento tem de estar fresco e o /saude tem de devolver a marca deste projeto (hash da
pasta de dados) ANTES de pedir o token. Assim a tela nunca age no serviço de outro projeto. Só biblioteca padrão."""
import datetime
import importlib.util
import json
import os
import pathlib
import shlex
import socket
import sqlite3
import urllib.error
import urllib.request

VIVO_S = 15  # batimento mais velho que isso = serviço parado (o serviço bate a cada 3 s)
TEMPO_REDE_S = 5  # toda chamada ao serviço tem tempo limite próprio (o painel não para a thread do agir)
TEMPO_ENVIO_S = 18  # envio espera o conector (até 15 s) e cabe nos 20 s do agir do painel
WINDOWS = os.name == "nt"
PYTHON = "python" if WINDOWS else "python3"  # no Windows "python3" costuma abrir a loja da Microsoft
SEM_RESPOSTA = "O serviço de Vendas não respondeu. Ligue-o e tente de novo."
PROCESSANDO = ("O serviço de Vendas ainda está processando o pedido. Atualize a tela em alguns segundos para ver "
               "o resultado antes de tentar de novo.")

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_spec = importlib.util.spec_from_file_location("tune_up_vendas_pasta", os.path.join(PLUGIN, "servico", "pasta.py"))
pasta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pasta)


class Recusa(Exception):
    """A tela não fala com o serviço; a mensagem (pt-BR) vai direto para o dono."""


def ler(raiz, base, sql):
    """Linhas de uma consulta no banco do serviço, ou None sem banco aberto. Não cria nada: modo somente leitura."""
    arquivo = os.path.join(pasta.caminho_da_pasta(raiz, base), "vendas.db")
    if not os.path.isfile(arquivo) or not os.path.exists(arquivo + "-shm"):
        return None  # sem -shm não há conexão WAL aberta (e o modo ro não consegue criá-lo): serviço parado
    con = sqlite3.connect(pathlib.Path(os.path.abspath(arquivo)).as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def pedir(metodo, url, cab, corpo=None, tempo=None):
    """Pedido ao serviço local com tempo limite e sem proxy. Devolve (código, objeto JSON)."""
    dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
    pedido = urllib.request.Request(url, data=dados, method=metodo, headers=cab)
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with abridor.open(pedido, timeout=tempo or TEMPO_REDE_S) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            return e.code, {}
        finally:
            e.close()


def citar(caminho):
    """Caminho pronto para colar no terminal: aspas simples no macOS/Linux, duplas no Windows (cmd e PowerShell)."""
    return '"%s"' % caminho if WINDOWS else shlex.quote(caminho)


def porta_do_painel(ctx):
    porta = ((ctx or {}).get("config") or {}).get("porta")
    return porta if isinstance(porta, int) and 1024 <= porta <= 65535 else 8787


def _batimento_fresco(raiz, base, agora=None):
    try:
        bate = ler(raiz, base, "SELECT em FROM batimento WHERE id = 1")
        quando = datetime.datetime.fromisoformat(bate[0][0]) if bate else None
    except (sqlite3.Error, ValueError, TypeError):
        return False
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    return quando is not None and abs((agora - quando).total_seconds()) <= VIVO_S


def _tempo_esgotado(erro):
    """Tempo limite na leitura (socket.timeout) ou na conexão (URLError com socket.timeout dentro)."""
    return isinstance(erro, socket.timeout) or (isinstance(erro, urllib.error.URLError)
                                                and isinstance(erro.reason, socket.timeout))


def endereco(ctx, base=None, agora=None):
    """URL base do serviço DESTE projeto, conferida. Recusa sem raiz, sem banco, batimento velho, porta inválida
    ou marca diferente (outro projeto naquela porta)."""
    raiz = (ctx or {}).get("raiz")
    if not raiz:
        raise Recusa("Esta tela não sabe qual é o projeto.")
    marca = os.path.basename(pasta.caminho_da_pasta(raiz, base))
    try:
        bate = ler(raiz, base, "SELECT em FROM batimento WHERE id = 1")
        conf = dict(ler(raiz, base, "SELECT chave, valor FROM config WHERE chave IN "
                                    "('servico_porta', 'servico_marca')") or [])
        quando = datetime.datetime.fromisoformat(bate[0][0]) if bate else None
    except (sqlite3.Error, ValueError, TypeError):
        raise Recusa("Não consegui ler o banco do serviço de Vendas deste projeto.")
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    if quando is None or abs((agora - quando).total_seconds()) > VIVO_S:
        raise Recusa("O serviço de Vendas deste projeto está parado. Ligue-o no terminal e tente de novo.")
    porta = conf.get("servico_porta") or ""
    if conf.get("servico_marca") != marca or not porta.isdigit() or not 1 <= int(porta) <= 65535:
        raise Recusa("O serviço de Vendas deste projeto não registrou a porta. Reinicie-o e tente de novo.")
    url = "http://127.0.0.1:%d" % int(porta)
    try:
        codigo, saude = pedir("GET", url + "/saude", {})
    except (OSError, ValueError):
        raise Recusa(SEM_RESPOSTA)
    if codigo != 200 or not isinstance(saude, dict) or saude.get("marca") != marca:
        raise Recusa("A porta %d responde por OUTRO projeto. Nada foi feito; reinicie o serviço deste projeto."
                     % int(porta))
    return url


def _acesso(ctx, base=None):
    """(url do serviço deste projeto, cabeçalho com o token). Confere projeto, batimento e marca antes de pedir o
    token; o token nunca sai daqui."""
    url = endereco(ctx, base)
    try:
        codigo, r = pedir("GET", url + "/token-de-envio", {"Origin": "http://127.0.0.1:%d" % porta_do_painel(ctx)})
        if codigo != 200 or not isinstance(r, dict) or not isinstance(r.get("token"), str):
            raise Recusa("O serviço não liberou o pedido (%d). Confira se ele foi ligado com --painel deste "
                         "painel." % codigo)
    except (OSError, ValueError):
        raise Recusa(SEM_RESPOSTA)
    return url, {"X-Vendas-Token": r["token"]}


def chamar(ctx, metodo, caminho, corpo=None, base=None, tempo=None):
    """Confere o serviço deste projeto, pega o token pela origem do painel e faz o pedido. Devolve (código, JSON).
    Recusa com mensagem clara em qualquer falha antes do pedido. O token nunca sai daqui."""
    url, cab = _acesso(ctx, base)
    if corpo is not None:
        cab["Content-Type"] = "application/json"
    try:
        return pedir(metodo, url + caminho, cab, corpo, tempo)
    except (OSError, ValueError) as e:
        # tempo esgotado com o serviço vivo: o pedido pode estar no meio (envio esperando o conector), não parado
        if _tempo_esgotado(e) and _batimento_fresco(ctx["raiz"], base):
            raise Recusa(PROCESSANDO)
        raise Recusa(SEM_RESPOSTA)


def baixar(ctx, caminho, limite, base=None):
    """GET de um arquivo do serviço, lido em blocos e parado em limite + 1 bytes (quem recebe vê que passou do
    teto). Devolve (código, cabeçalhos em minúsculas, bytes); em erro os bytes vêm vazios."""
    url, cab = _acesso(ctx, base)
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with abridor.open(urllib.request.Request(url + caminho, headers=cab), timeout=TEMPO_REDE_S) as r:
            partes, lidos = [], 0
            while lidos <= limite:
                bloco = r.read(min(64 * 1024, limite + 1 - lidos))
                if not bloco:
                    break
                partes.append(bloco)
                lidos += len(bloco)
            return r.status, {k.lower(): v for k, v in r.getheaders()}, b"".join(partes)
    except urllib.error.HTTPError as e:
        e.close()
        return e.code, {}, b""
    except (OSError, ValueError):
        raise Recusa(SEM_RESPOSTA)
