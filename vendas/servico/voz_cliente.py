"""ElevenLabs (texto -> fala) por urllib e conversão com ffmpeg para Ogg/Opus mono 48 kHz 32 kbps (nota de voz do
WhatsApp). O texto vai SÓ no corpo JSON do pedido; a chave SÓ no cabeçalho xi-api-key; nenhum dos dois vai para
log, linha de comando ou mensagem de erro. Sem nova tentativa: cada chamada pode ser cobrada.
A URL base vem SÓ do argumento/ambiente de subida do serviço (testes), nunca de um pedido."""
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import urllib.error
import urllib.request
from urllib.parse import quote

from servico import openai_cliente

URL_PADRAO = "https://api.elevenlabs.io"
VAR_URL = "VENDAS_ELEVENLABS_URL"
TEMPO_S = 30
TEMPO_FFMPEG_S = 60
TEMPO_VOZES_S = 6   # o painel espera 12 s pela rota /voz/vozes
MAX_AUDIO = 20 * 1024 * 1024   # resposta maior que isso não é um áudio curto: recusa
FORMATO_ID = re.compile(r"^[A-Za-z0-9]{8,64}$")
FORMATO_NOME = re.compile(r"^[a-z0-9_]{1,64}$")   # modelo e formato de saída


class ErroVoz(RuntimeError):
    """`mensagem` em pt-BR para o dono, sem chave nem texto. sem_cobranca=True: a ElevenLabs respondeu com erro
    (nada foi gerado), então a reserva de caracteres pode ser devolvida."""

    def __init__(self, mensagem, codigo=None, sem_cobranca=False):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.codigo = codigo
        self.sem_cobranca = sem_cobranca


def _status_do_corpo(bruto):
    """`detail.status` do corpo de erro da ElevenLabs (ex.: quota_exceeded), ou None. A mensagem não é guardada."""
    try:
        detalhe = json.loads(bruto.decode("utf-8")).get("detail")
    except (ValueError, AttributeError, UnicodeDecodeError):
        return None
    status = detalhe.get("status") if isinstance(detalhe, dict) else None
    return status if isinstance(status, str) and re.match(r"^[a-z_]{1,64}$", status) else None


def _mensagem_http(status, codigo):
    if codigo == "quota_exceeded":
        return "Os créditos da sua conta ElevenLabs acabaram. Nada foi enviado."
    if status == 401:
        return "A ElevenLabs recusou a chave (401). Confira a chave colada. Nada foi enviado."
    if status == 429:
        return "A ElevenLabs recusou por limite de uso (429). Espere um pouco. Nada foi enviado."
    if status == 404:
        return "A ElevenLabs não achou essa voz (404). Confira o voice_id. Nada foi enviado."
    return "A ElevenLabs devolveu um erro (%d). Nada foi enviado." % status


def sintetizar(url_base, segredo, voz_id, modelo, formato, texto, tempo=TEMPO_S):
    """UMA chamada POST /v1/text-to-speech/{voice_id}?output_format=...: devolve os bytes do áudio. ErroVoz se falha."""
    if not FORMATO_ID.match(voz_id or "") or not FORMATO_NOME.match(modelo or "") or not FORMATO_NOME.match(
            formato or ""):
        raise ErroVoz("Voz, modelo ou formato inválido.", "config_invalida", sem_cobranca=True)
    url = "%s/v1/text-to-speech/%s?output_format=%s" % (url_base.rstrip("/"), quote(voz_id, safe=""),
                                                         quote(formato, safe=""))
    corpo = json.dumps({"text": texto, "model_id": modelo}).encode("utf-8")
    pedido = urllib.request.Request(url, data=corpo, method="POST", headers={
        "Content-Type": "application/json", "Accept": "audio/mpeg", "xi-api-key": segredo})
    try:
        with openai_cliente._abridor(url).open(pedido, timeout=tempo) as r:
            audio = r.read(MAX_AUDIO + 1)
    except urllib.error.HTTPError as e:
        try:
            bruto = e.read(4096)
        except OSError:
            bruto = b""
        finally:
            e.close()
        codigo = _status_do_corpo(bruto)
        raise ErroVoz(_mensagem_http(e.code, codigo), codigo or "http_%d" % e.code, sem_cobranca=True)
    except (socket.timeout, TimeoutError):
        raise ErroVoz("A ElevenLabs demorou demais para responder. Nada foi enviado.", "tempo_esgotado")
    except urllib.error.URLError as e:
        recusada = isinstance(e.reason, ConnectionRefusedError)
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise ErroVoz("A ElevenLabs demorou demais para responder. Nada foi enviado.", "tempo_esgotado")
        raise ErroVoz("Não consegui falar com a ElevenLabs (rede). Nada foi enviado.", "rede", sem_cobranca=recusada)
    except (http.client.HTTPException, OSError):
        raise ErroVoz("Não consegui falar com a ElevenLabs (rede). Nada foi enviado.", "rede")
    if not audio or len(audio) > MAX_AUDIO:
        raise ErroVoz("A ElevenLabs devolveu um áudio vazio ou grande demais. Nada foi enviado.", "resposta_invalida")
    return audio


def listar_vozes(url_base, segredo, tempo=None):
    """GET /v1/voices: [{voice_id, nome, categoria}] da conta, em ordem de nome. UMA tentativa. ErroVoz se falha."""
    pedido = urllib.request.Request(url_base.rstrip("/") + "/v1/voices", method="GET", headers={"xi-api-key": segredo})
    try:
        with openai_cliente._abridor(url_base).open(pedido, timeout=tempo or TEMPO_VOZES_S) as r:
            dados = json.loads(r.read(MAX_AUDIO).decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            bruto = e.read(4096)
        except OSError:
            bruto = b""
        finally:
            e.close()
        codigo = _status_do_corpo(bruto)
        raise ErroVoz(_mensagem_http(e.code, codigo), codigo or "http_%d" % e.code)
    except (socket.timeout, TimeoutError):
        raise ErroVoz("A ElevenLabs demorou demais para listar as vozes.", "tempo_esgotado")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise ErroVoz("A ElevenLabs demorou demais para listar as vozes.", "tempo_esgotado")
        raise ErroVoz("Não consegui falar com a ElevenLabs (rede).", "rede")
    except (http.client.HTTPException, OSError):
        raise ErroVoz("Não consegui falar com a ElevenLabs (rede).", "rede")
    except (ValueError, UnicodeDecodeError):
        raise ErroVoz("A ElevenLabs devolveu uma lista de vozes ilegível.", "resposta_invalida")
    itens = dados.get("voices") if isinstance(dados, dict) else None
    if not isinstance(itens, list):
        raise ErroVoz("A ElevenLabs devolveu uma lista de vozes ilegível.", "resposta_invalida")
    vozes = [{"voice_id": i["voice_id"], "nome": str(i.get("name") or i["voice_id"])[:80],
              "categoria": str(i.get("category") or "")[:30]}
             for i in itens if isinstance(i, dict) and isinstance(i.get("voice_id"), str)
             and FORMATO_ID.match(i["voice_id"])]
    return sorted(vozes, key=lambda v: v["nome"].lower())


def achar_ffmpeg():
    """Caminho do ffmpeg no PATH, ou None (voz desligada)."""
    return shutil.which("ffmpeg")


def arquivo_temporario(pasta_dados, sufixo):
    """Cria um arquivo vazio 0600 com nome aleatório na pasta de dados externa e devolve o caminho."""
    caminho = os.path.join(pasta_dados, "voz-%s%s" % (secrets.token_hex(8), sufixo))
    os.close(os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    if os.name != "nt":
        os.chmod(caminho, 0o600)
    return caminho


def apagar(*caminhos):
    for caminho in caminhos:
        if caminho:
            try:
                os.remove(caminho)
            except FileNotFoundError:
                pass


def converter(ffmpeg, entrada, saida, tempo=TEMPO_FFMPEG_S):
    """ffmpeg com LISTA de argumentos (sem shell): entrada -> Ogg/Opus mono 48 kHz 32 kbps em `saida`. ErroVoz se
    falha, demora mais que `tempo` ou a saída não começa com OggS. A saída de erro do ffmpeg não é guardada."""
    comando = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", entrada, "-vn", "-ac", "1",
               "-ar", "48000", "-c:a", "libopus", "-b:a", "32k", "-application", "voip", "-f", "ogg", saida]
    try:
        r = subprocess.run(comando, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=tempo, check=False)
    except subprocess.TimeoutExpired:
        raise ErroVoz("A conversão do áudio demorou demais. Nada foi enviado.", "ffmpeg_tempo")
    except OSError:
        raise ErroVoz("Não consegui rodar o ffmpeg. Nada foi enviado.", "ffmpeg_ausente")
    if r.returncode != 0:
        raise ErroVoz("O ffmpeg não converteu o áudio (código %d). Nada foi enviado." % r.returncode, "ffmpeg_falhou")
    with open(saida, "rb") as f:
        if f.read(4) != b"OggS":
            raise ErroVoz("O ffmpeg não gerou um Ogg válido. Nada foi enviado.", "ffmpeg_falhou")
