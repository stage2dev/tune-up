"""Pedidos à OpenAI por urllib: tempo limite por tentativa e UMA nova tentativa (rede, tempo, 5xx ou 429 que não
seja falta de crédito). O erro vem do corpo (`error.code`); a mensagem do corpo não é guardada (pode trazer parte
da chave). A URL base vem SÓ do argumento/ambiente de subida do serviço (testes), nunca de um pedido."""
import http.client
import json
import socket
import urllib.error
import urllib.request
from urllib.parse import urlsplit

URL_PADRAO = "https://api.openai.com"
VAR_URL = "VENDAS_OPENAI_URL"
TEMPO_S = 30
SEM_NOVA_TENTATIVA = ("insufficient_quota", "invalid_api_key")


class ErroOpenAI(RuntimeError):
    """codigo: `error.code` do corpo, 'tempo_esgotado', 'rede' ou 'http_<n>'. Nunca leva a chave."""

    def __init__(self, codigo, status=None):
        super().__init__(codigo)
        self.codigo = codigo
        self.status = status


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None  # 3xx vira erro: o cabeçalho com a chave nunca segue para outro endereço


def _abridor(url):
    extra = [_SemRedirecionar()]
    if urlsplit(url).hostname in ("127.0.0.1", "localhost"):
        extra.append(urllib.request.ProxyHandler({}))  # servidor falso local: sem proxy
    return urllib.request.build_opener(*extra)


def _codigo_do_corpo(bruto, status):
    try:
        erro = json.loads(bruto.decode("utf-8")).get("error") or {}
        codigo = erro.get("code") or erro.get("type")
    except (ValueError, AttributeError, UnicodeDecodeError):
        codigo = None
    return str(codigo) if isinstance(codigo, str) and codigo else "http_%d" % status


def _uma(url, chave, metodo, corpo, tempo):
    cab = {"Authorization": "Bearer " + chave}
    dados = None
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        cab["Content-Type"] = "application/json"
    pedido = urllib.request.Request(url, data=dados, method=metodo, headers=cab)
    try:
        with _abridor(url).open(pedido, timeout=tempo) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            bruto = e.read()
        except OSError:
            bruto = b""
        finally:
            e.close()
        raise ErroOpenAI(_codigo_do_corpo(bruto, e.code), e.code)
    except (socket.timeout, TimeoutError):
        raise ErroOpenAI("tempo_esgotado")
    except http.client.HTTPException:  # corpo cortado, linha de status ruim: não é OSError
        raise ErroOpenAI("rede")
    except urllib.error.URLError as e:
        raise ErroOpenAI("tempo_esgotado" if isinstance(e.reason, (socket.timeout, TimeoutError)) else "rede")
    except OSError:
        raise ErroOpenAI("rede")
    except (ValueError, UnicodeDecodeError):
        raise ErroOpenAI("resposta_invalida")


def pedir(base, chave, metodo, caminho, corpo=None, tempo=TEMPO_S):
    """JSON da resposta ou ErroOpenAI depois de no máximo 2 tentativas."""
    url = base.rstrip("/") + caminho
    try:
        return _uma(url, chave, metodo, corpo, tempo)
    except ErroOpenAI as e:
        de_novo = e.codigo in ("tempo_esgotado", "rede") or (e.status or 0) >= 500 or (
            e.status == 429 and e.codigo not in SEM_NOVA_TENTATIVA)
        if not de_novo:
            raise
    return _uma(url, chave, metodo, corpo, tempo)


def listar_modelos(base, chave, tempo=8):
    """Ids dos modelos da conta (GET /v1/models), em ordem alfabética."""
    r = pedir(base, chave, "GET", "/v1/models", tempo=tempo)
    itens = r.get("data") if isinstance(r, dict) else None
    if not isinstance(itens, list):
        raise ErroOpenAI("resposta_invalida")
    return sorted({i["id"] for i in itens if isinstance(i, dict) and isinstance(i.get("id"), str)})
