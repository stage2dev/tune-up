"""Transcrição do áudio do lead: OpenAI `POST /v1/audio/transcriptions` (multipart montado à mão sobre urllib; campos
file, model, language=pt, response_format=json; resposta {"text": ...}). O arquivo vai como foi guardado (ogg/opus,
mp3, m4a, wav) com a extensão certa no nome. Tempo limite e UMA tentativa (nunca de novo depois de tempo esgotado).
Antes de chamar: duração <= 5 min (quando o ffprobe soube) e tamanho <= 16 MB, senão audio_longo; preço por minuto
do modelo (precos.preco_minuto) desconhecido = preco_desconhecido. O custo reserva no MESMO teto diário do chat
(precos.reservar, BEGIN IMMEDIATE) antes da chamada e acerta depois: erro com resposta HTTP ou conexão recusada
libera; tempo esgotado fica. Sem duração conhecida, o pior caso sai do tamanho (8 kbps, piso de nota de voz).
Resultado tipado {ok, texto, motivo}: falha nunca vira texto; transcrição com menos de 2 letras = falhou.
A transcrição fica em mensagens.transcricao (migração 19). Nenhuma chave, texto ou nome de arquivo vai para log."""
import http.client
import json
import math
import secrets
import socket
import sys
import urllib.error
import urllib.request

from servico import banco, chave, midia, openai_cliente, precos

SUGESTAO_MODELO = "gpt-4o-mini-transcribe"
TEMPO_S = 60
DURACAO_MAX_S = 300
BYTES_MAX = 16 * 1024 * 1024
BYTES_POR_S = 1000   # 8 kbps: pior caso de duração quando o ffprobe não soube
MINIMO = 2
EXTENSAO = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "m4a", "audio/wav": "wav"}


def modelo(con):
    return banco.ler_config(con, "ia_modelo_transcricao") or SUGESTAO_MODELO


def _falha(motivo):
    return {"ok": False, "texto": None, "motivo": motivo}


def corpo_multipart(campos, nome_arquivo, mimetype, dados):
    """(corpo em bytes, Content-Type). Fronteira aleatória que não aparece nos dados."""
    while True:
        fronteira = "----vendas" + secrets.token_hex(16)
        if fronteira.encode("ascii") not in dados:
            break
    partes = []
    for nome, valor in campos:
        partes.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                       % (fronteira, nome, valor)).encode("utf-8"))
    partes.append(("--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: %s"
                   "\r\n\r\n" % (fronteira, nome_arquivo, mimetype)).encode("utf-8"))
    partes.append(bytes(dados))
    partes.append(("\r\n--%s--\r\n" % fronteira).encode("ascii"))
    return b"".join(partes), "multipart/form-data; boundary=%s" % fronteira


def pedir(base, segredo, corpo, tipo, tempo=TEMPO_S):
    """UMA tentativa. JSON da resposta ou openai_cliente.ErroOpenAI (mesmos códigos do chat)."""
    url = base.rstrip("/") + "/v1/audio/transcriptions"
    pedido = urllib.request.Request(url, data=corpo, method="POST", headers={
        "Authorization": "Bearer " + segredo, "Content-Type": tipo})
    try:
        with openai_cliente._abridor(url).open(pedido, timeout=tempo) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            bruto = e.read()
        except OSError:
            bruto = b""
        finally:
            e.close()
        raise openai_cliente.ErroOpenAI(openai_cliente._codigo_do_corpo(bruto, e.code), e.code)
    except (socket.timeout, TimeoutError):
        raise openai_cliente.ErroOpenAI("tempo_esgotado")
    except http.client.HTTPException:
        raise openai_cliente.ErroOpenAI("rede")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise openai_cliente.ErroOpenAI("tempo_esgotado")
        raise openai_cliente.ErroOpenAI("rede", recusada=isinstance(e.reason, ConnectionRefusedError))
    except ConnectionRefusedError:
        raise openai_cliente.ErroOpenAI("rede", recusada=True)
    except OSError:
        raise openai_cliente.ErroOpenAI("rede")
    except (ValueError, UnicodeDecodeError):
        raise openai_cliente.ErroOpenAI("resposta_invalida")


def _minutos(linha):
    if linha["duracao_s"] is not None:
        return max(float(linha["duracao_s"]), 1.0) / 60.0
    return math.ceil((linha["bytes"] or 0) / float(BYTES_POR_S)) / 60.0


def transcrever(con, pasta_dados, base, mensagem_id, tempo=TEMPO_S):
    """Transcreve o áudio (pronto) da mensagem e grava em mensagens.transcricao. Já transcrito = devolve o guardado
    sem chamar. Nenhuma transação fica aberta durante a rede."""
    linha = con.execute("SELECT m.transcricao, d.estado, d.mimetype, d.bytes, d.duracao_s, d.arquivo FROM mensagens m "
                        "JOIN midias d ON d.mensagem_id = m.id WHERE m.id = ? AND d.tipo = 'audio'",
                        (mensagem_id,)).fetchone()
    if linha is None or linha["estado"] != "pronta":
        return _falha("midia_indisponivel")
    if linha["transcricao"]:
        return {"ok": True, "texto": linha["transcricao"], "motivo": None}
    if (linha["bytes"] or 0) > BYTES_MAX or (linha["duracao_s"] is not None and linha["duracao_s"] > DURACAO_MAX_S):
        return _falha("audio_longo")
    extensao = EXTENSAO.get(linha["mimetype"])
    if extensao is None:
        return _falha("audio_formato")
    segredo, nome_modelo = chave.ler(pasta_dados), modelo(con)
    if not segredo:
        return _falha("sem_chave")
    por_minuto = precos.preco_minuto(pasta_dados, nome_modelo)
    if por_minuto is None:
        return _falha("preco_desconhecido")
    caminho = midia.caminho_do_arquivo(pasta_dados, linha["arquivo"])
    try:
        with open(caminho or "", "rb") as f:
            dados = f.read(BYTES_MAX + 1)
    except OSError:
        return _falha("midia_indisponivel")
    if not dados or len(dados) > BYTES_MAX:
        return _falha("midia_indisponivel" if not dados else "audio_longo")
    corpo, tipo = corpo_multipart([("model", nome_modelo), ("language", "pt"), ("response_format", "json")],
                                  "audio.%s" % extensao, linha["mimetype"], dados)
    pior = _minutos(linha) * por_minuto
    reserva = precos.reservar(con, pior)
    if reserva is None:
        return _falha("teto_diario")
    try:
        resposta = pedir(base, segredo, corpo, tipo, tempo)
    except openai_cliente.ErroOpenAI as e:
        if e.status is not None or e.recusada:   # não cobrado
            precos.acertar(con, reserva, 0)
        print("vendas: transcrição: falhou: %s" % e.codigo, file=sys.stderr)
        return _falha("transcricao_falhou")
    texto = resposta.get("text") if isinstance(resposta, dict) else None
    real = pior if linha["duracao_s"] is None else float(linha["duracao_s"]) / 60.0 * por_minuto
    precos.acertar(con, reserva, real)
    if not isinstance(texto, str) or len(texto.strip()) < MINIMO:
        return _falha("transcricao_falhou")
    texto = texto.strip()
    con.execute("UPDATE mensagens SET transcricao = ? WHERE id = ? AND transcricao IS NULL", (texto, mensagem_id))
    guardada = con.execute("SELECT transcricao FROM mensagens WHERE id = ?", (mensagem_id,)).fetchone()
    if guardada is None or not guardada["transcricao"]:
        raise banco.EscritaSemEfeito("transcrição da mensagem %r não gravou" % mensagem_id)
    return {"ok": True, "texto": guardada["transcricao"], "motivo": None}
