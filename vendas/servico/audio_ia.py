"""Ferramenta responder_em_audio: a IA responde em nota de voz. O CÓDIGO decide se ela existe para o modelo: voz
ligada (chave, ffmpeg, voz escolhida, consentimento se clonada) E (a mensagem do lead logo antes do gatilho foi um
áudio, ou o próprio gatilho é um áudio transcrito (servico/entender.py), OU uma das últimas RECENTES mensagens de
texto dele pede áudio). Com 'IA entende áudios' desligado o áudio do lead não vai à IA e a ferramenta aparece na
próxima mensagem de texto dele.
O texto falado passa pelo MESMO sanitizador da saída de texto (saida.preparar); depois os links saem do áudio (vão
num balão de texto separado) e a fala fica em 4 frases e voz.LIMITE_TEXTO caracteres. Sobrou algo com cara de link
na fala = vai como texto.
Tetos: áudios da IA por contato por dia e áudios por dia no portão (origem audio_ia), caracteres por dia no voz.py.
Qualquer falha da voz (teto, ElevenLabs, ffmpeg, voz desligada, conector) = o texto sanitizado sai pelo caminho
normal, nunca silêncio, e o motivo fica no evento ia_audio_virou_texto. Opt-out ou pausa no portão = nada sai (o texto
seria negado pelo mesmo motivo). Áudio 'incerto' (pode ter saído) = sem texto de reserva; a conversa fica "precisa de
você". Modo rascunho: nada é gerado antes da aprovação (rascunhos.aprovar chama aprovar() daqui)."""
import json
import re
import sys

from servico import banco, cerebro, portao, saida, voz

RECENTES = 3   # mensagens de entrada do lead (até o gatilho) olhadas atrás de um pedido de áudio
PEDIDO = re.compile(r"\b(?:manda|mande|mandar|envia|envie|enviar|grava|grave|gravar|prefiro|quero|responde|responda"
                    r"|fala|fale|pode)(?: \w+){0,3} audios?\b|\b(?:por|em|via) audio\b")
NEGA = re.compile(r"\b(?:nao|sem)(?: \w+){0,2} audios?\b")
SAIU = ("enviado", "incerto", "duplicado")   # o áudio saiu ou pode ter saído: nada de texto de reserva


def pediu_audio(texto):
    """'manda áudio', 'pode mandar audio', 'prefiro áudio', 'responde por áudio'... e não 'não manda áudio'."""
    plano = saida._plano(texto or "")
    return bool(PEDIDO.search(plano)) and not NEGA.search(plano)


def voz_ligada(app, con):
    if app is None:
        return False
    try:
        return not voz.avisos(app, con)
    except Exception as e:   # na dúvida a ferramenta não aparece; só o tipo no log
        print("vendas: áudio da IA: prontidão da voz falhou: %s" % type(e).__name__, file=sys.stderr)
        return False


def oferecer(app, con, conversa_id, gatilho_id):
    """True = responder_em_audio vai na lista de ferramentas desta rodada."""
    linhas = con.execute("SELECT tipo, texto FROM mensagens WHERE conversa_id = ? AND id <= ? AND confiavel = 1 AND "
                         "direcao = 'entrada' ORDER BY id DESC LIMIT ?", (conversa_id, gatilho_id, RECENTES)).fetchall()
    quer = any(l["tipo"] == "audio" for l in linhas[:2]) or any(
        l["tipo"] == "texto" and pediu_audio(l["texto"]) for l in linhas)
    return quer and voz_ligada(app, con)


def separar(texto):
    """(fala sem links, em 4 frases e voz.LIMITE_TEXTO caracteres; links na ordem; True se o limite cortou a fala)."""
    links = list(dict.fromkeys(m.group(0).rstrip(".,;:!?…") for m in saida.URL.finditer(texto or "")))
    inteira = re.sub(r"\s+", " ", saida.URL.sub(" ", texto or "")).strip()
    fala = saida.limitar(inteira, caracteres=voz.LIMITE_TEXTO)
    return fala, links, fala != inteira


def para_rascunho(pronto):
    """Rascunho 'enviar como áudio': o dono vê a fala exata (já cortada) e os links nas linhas de baixo."""
    fala, links, _ = separar(pronto)
    return "\n".join([fala] + links).strip()


def _virou_texto(con, conversa_id, motivo, rascunho_id=None):
    dados = {"conversa_id": conversa_id, "motivo": motivo}
    if rascunho_id is not None:
        dados["rascunho_id"] = rascunho_id
    banco.registrar_evento(con, "ia_audio_virou_texto", json.dumps(dados))


def _motivo(r):
    return str(r.get("motivo") or r.get("codigo") or r.get("estado"))


def _chave(con, chave):
    linha = con.execute("SELECT id, estado FROM envios WHERE chave_dedupe = ? AND estado <> 'negado'",
                        (chave,)).fetchone()
    return None if linha is None else dict(linha)


def _falar(app, con, numero, fala, mandar, chave):
    """voz._gerar_e_enviar com o arquivo pelo portão. Exceção inesperada: se a linha do áudio no portão já existe
    (pendente, enviado ou incerto) o áudio pode ter saído = 'incerto' (sem texto de reserva); sem linha = 'erro' (o
    texto sai)."""
    try:
        return voz._gerar_e_enviar(app, con, "audio_ia", numero, fala, mandar)
    except Exception as e:
        if con.in_transaction:
            con.execute("ROLLBACK")
        print("vendas: áudio da IA: falhou: %s" % type(e).__name__, file=sys.stderr)
        codigo = "erro_interno:%s" % type(e).__name__
        linha = _chave(con, chave)
        if linha is not None and linha["estado"] in ("pendente", "enviado", "incerto"):
            return {"estado": "incerto", "motivo": codigo, "envio_id": linha["id"]}
        return {"estado": "erro", "codigo": codigo}


def _so_texto(con, conector, instancia, numero, conversa_id, id_gatilho, pronto, permitidos, segredos, motivo):
    _virou_texto(con, conversa_id, motivo)
    r = saida.entregar(con, conector, instancia, numero, conversa_id, id_gatilho, pronto, permitidos=permitidos,
                       segredos=segredos)
    r["audio_motivo"] = motivo
    return r


def entregar(app, con, conector, instancia, numero, conversa_id, id_gatilho, texto, permitidos=(), segredos=(),
             reescrever=None):
    """Modo automático. Áudio pelo portão (origem audio_ia, chave da IA + sufixo de áudio) e os links num balão de
    texto (origem ia); falha da voz = o texto inteiro pelo saida.entregar."""
    if _chave(con, "audio_ia:%s:%s:1:audio" % (conversa_id, id_gatilho)) or \
            saida._ja_respondido(con, conversa_id, id_gatilho):
        return {"estado": "duplicado", "motivo": "gatilho_ja_respondido", "baloes": []}
    pronto, motivo = saida.preparar(texto, permitidos, segredos, reescrever)
    if pronto is None:
        return saida._barrar(con, conversa_id, motivo)
    fala, links, _ = separar(pronto)
    if not fala or saida.sobras_de_link(fala, ()):
        return _so_texto(con, conector, instancia, numero, conversa_id, id_gatilho, pronto, permitidos, segredos,
                         "fala_vazia" if not fala else "link_na_fala")
    r = _falar(app, con, numero, fala, lambda conector_, inst, ogg: portao.enviar_audio_ia(
        con, conector_, inst, numero, ogg, conversa_id, id_gatilho, 1), "audio_ia:%s:%s:1:audio" % (conversa_id,
                                                                                                 id_gatilho))
    if r["estado"] in SAIU:
        res = {"estado": r["estado"], "motivo": r.get("motivo"), "audio": r, "baloes": []}
        if r["estado"] == "incerto":
            cerebro.marcar_precisa_de_voce(con, conversa_id, "audio_incerto")
        elif r["estado"] == "enviado" and links:
            res["baloes"] = saida.entregar(con, conector, instancia, numero, conversa_id, id_gatilho, "\n".join(links),
                                           permitidos=permitidos, segredos=segredos)["baloes"]
        return res
    if r["estado"] == "negado" and r.get("motivo") in saida.NAO_CHAMA_O_DONO:
        return {"estado": "negado", "motivo": r["motivo"], "audio": r, "baloes": []}
    return _so_texto(con, conector, instancia, numero, conversa_id, id_gatilho, pronto, permitidos, segredos, _motivo(r))


def aprovar(app, con, instancia, numero, final, rascunho_id):
    """Rascunho 'enviar como áudio' aprovado. (resultado do áudio ou None, texto a mandar como rascunho_aprovado ou
    None). Áudio saiu = só os links vão em texto; falha da voz = o texto inteiro vai; opt-out/pausa = nada."""
    chave = "audio_ia:rascunho:%d" % rascunho_id
    antes = _chave(con, chave)
    if antes is not None and antes["estado"] != "falhou":   # já saiu (ou pode ter saído): nada é gerado de novo
        links = separar(final)[1] if antes["estado"] == "enviado" else []   # links que falharam/caíram: de novo
        return {"estado": "duplicado", "motivo": "chave_ocupada", "envio_id": antes["id"]}, "\n".join(links) or None
    if antes is not None or _chave(con, "rascunho_aprovado:%d" % rascunho_id):   # já foi como texto: segue texto
        return None, final
    fala, links, cortou = separar(final)
    if not fala or cortou or saida.sobras_de_link(fala, ()):   # o dono aprovou um texto que não cabe no áudio
        _virou_texto(con, None, "rascunho_nao_cabe_no_audio", rascunho_id)
        return None, final
    r = _falar(app, con, numero, fala, lambda conector, inst, ogg: portao.enviar_audio_rascunho(
        con, conector, inst, numero, ogg, rascunho_id), chave)
    if r["estado"] in SAIU:
        return r, ("\n".join(links) if links and r["estado"] == "enviado" else None)
    if r["estado"] == "negado" and r.get("motivo") == "optout":
        return r, None
    _virou_texto(con, None, _motivo(r), rascunho_id)   # pausa_humana não barra o rascunho aprovado: o dono aprovou
    return None, final

