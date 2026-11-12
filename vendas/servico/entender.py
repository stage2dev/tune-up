"""A IA entende áudio e imagem do lead (chaves 'IA entende áudios' e 'IA entende imagens' da aba IA: ligadas por
padrão quando há chave da OpenAI; desligada = como antes, "precisa de você" e nada vai à IA). Documento: nunca.

Na rodada do atendente, para cada áudio/imagem confiável do lead desde a última saída até o gatilho:
- espera o download (servico/midia.py) até ESPERA_MIDIA_S; pendente, falhou ou expirada = midia_indisponivel;
- áudio: transcreve (servico/transcricao.py); a transcrição vai ao modelo como DADO, rotulada como transcrição;
- transcrição e legenda passam pelas MESMAS triagens do texto (recebimento.e_saida / tem_sinal): SAIR = opt-out;
- imagem: só jpeg/png/webp (bytes mágicos conferidos no download), no máximo IMAGENS_MAX por rodada e
  IMAGENS_BYTES_MAX no total (as mais novas primeiro), como data URL com detail "low"; a que passar do limite não
  vai (imagens_demais; sozinha acima de 8 MB = imagem_grande); se for a do gatilho, falha.
- transcrição que falhou (GUARDA) e imagem que a API recusou ficam em midias.falha_ia: nenhuma rodada tenta de novo
  sozinha (nada pago duas vezes); numa mídia que não é o gatilho viram o aviso midia_nao_entendida e a IA responde.
- serviço parando durante a espera = parado (não é midia_indisponivel).
Resultado tipado: falha = {ok: False, motivo}; quem chama não chama o modelo, nada sai e a conversa fica "precisa de
você" com o motivo. Nenhuma transação fica aberta durante a espera ou a rede."""
import base64
import time

from servico import banco, chave, midia, transcricao

ESPERA_MIDIA_S = 20
IMAGENS_MAX = 4
IMAGENS_BYTES_MAX = 8 * 1024 * 1024
VISAO = ("image/jpeg", "image/png", "image/webp")
CONFIG = {"audio": "ia_entende_audio", "imagem": "ia_entende_imagem"}


def ligado(con, pasta_dados, tipo):
    """A IA entende este tipo agora? Só com chave da OpenAI e a chave da aba IA diferente de '0'."""
    return tipo in CONFIG and bool(chave.ler(pasta_dados)) and banco.ler_config(con, CONFIG[tipo]) != "0"


def _falha(motivo):
    return {"ok": False, "motivo": motivo, "sair": False, "parado": False, "tinha_midia": True, "imagens": {},
            "avisos": []}


def esperar(con, mensagem_id, parar, espera=ESPERA_MIDIA_S):
    """Estado da mídia da mensagem depois de no máximo `espera` s (None = sem linha). parar() encerra antes."""
    prazo = time.monotonic() + espera
    while True:
        linha = con.execute("SELECT estado FROM midias WHERE mensagem_id = ?", (mensagem_id,)).fetchone()
        if linha is None or linha["estado"] != "pendente":
            return None if linha is None else linha["estado"]
        falta = prazo - time.monotonic()
        if falta <= 0 or parar.wait(min(0.2, falta)):
            return "pendente"


def _imagem(con, pasta_dados, mensagem_id):
    """(data URL, bytes, motivo): motivo imagem_grande acima de IMAGENS_BYTES_MAX; (None, 0, None) = indisponível."""
    linha = con.execute("SELECT mimetype, arquivo FROM midias WHERE mensagem_id = ? AND estado = 'pronta'",
                        (mensagem_id,)).fetchone()
    if linha is None or linha["mimetype"] not in VISAO:
        return None, 0, None
    caminho = midia.caminho_do_arquivo(pasta_dados, linha["arquivo"])
    try:
        with open(caminho or "", "rb") as f:
            dados = f.read(IMAGENS_BYTES_MAX + 1)
    except OSError:
        return None, 0, None
    if not dados or midia.detectar("imagem", dados) != linha["mimetype"]:
        return None, 0, None
    if len(dados) > IMAGENS_BYTES_MAX:
        return None, 0, "imagem_grande"
    return "data:%s;base64,%s" % (linha["mimetype"], base64.b64encode(dados).decode("ascii")), len(dados), None


def _saida_ou_sinal(texto, r):
    """Transcrição ou legenda tratada como o texto do lead: SAIR inteiro = True (opt-out, o modelo não é chamado);
    frase com o sinal = aviso sinal_de_saida (o dono vê, a IA ainda responde, como no texto)."""
    from servico import recebimento   # aqui dentro: no topo fecharia um ciclo de import (rotas -> ... -> entender)
    if recebimento.e_saida(texto):
        return True
    if texto and recebimento.tem_sinal(texto):
        r["avisos"].append("sinal_de_saida")
    return False


def guardar_falha(con, mensagem_ids, motivo):
    """A IA falhou com estas mídias (transcrição, imagem recusada): não tenta sozinha de novo (só a ação do dono limpa)."""
    for mid in mensagem_ids:
        con.execute("UPDATE midias SET falha_ia = ? WHERE mensagem_id = ? AND estado = 'pronta'", (motivo, mid))


def preparar(cerebro_ia, con, conversa_id, gatilho_id, parar, entende, espera=ESPERA_MIDIA_S, so_triagem=False):
    """{ok, motivo, sair, parado, tinha_midia, imagens: {mensagem_id: data URL}, avisos: [motivos que não impedem a
    resposta]}. A transcrição fica gravada na mensagem (o contexto a lê de lá). sair=True: uma transcrição ou legenda
    do lote é um SAIR (quem chama grava o opt-out e manda a confirmação; o modelo não é chamado); a triagem roda em
    TODA transcrição/legenda disponível, mesmo depois de uma mídia do lote falhar. parado=True: o serviço está parando
    (nada a marcar). entende(con, tipo): a MESMA decisão que o recebimento usou; None = a IA não entende mídia.
    Falha guardada (midias.falha_ia, de uma rodada anterior ou desta) não é tentada de novo: na mídia do gatilho é
    falha, nas outras é aviso (a IA responde ao texto e a conversa fica "precisa de você").
    so_triagem=True (conversa pausada): só a triagem de SAIR, sem ler imagens.
    Imagens: as MAIS NOVAS primeiro (a do gatilho sempre entra); gatilho que não cabe, ou nenhuma que caiba = falha."""
    r = {"ok": True, "motivo": None, "sair": False, "parado": False, "tinha_midia": False, "imagens": {}, "avisos": []}
    if entende is None:
        return r
    pasta_dados = cerebro_ia.pasta_dados
    ultima = con.execute("SELECT COALESCE(MAX(id), 0) FROM mensagens WHERE conversa_id = ? AND direcao = 'saida' "
                         "AND id <= ?", (conversa_id, gatilho_id)).fetchone()[0]
    linhas = con.execute("SELECT m.id, m.tipo, m.texto, d.falha_ia FROM mensagens m LEFT JOIN midias d ON "
                         "d.mensagem_id = m.id WHERE m.conversa_id = ? AND m.id > ? AND m.id <= ? AND m.confiavel = 1 "
                         "AND m.direcao = 'entrada' AND m.tipo IN ('audio', 'imagem') ORDER BY m.id",
                         (conversa_id, ultima, gatilho_id)).fetchall()
    r["tinha_midia"] = bool(linhas)
    imagens, falha = [], None

    def falhou(mid, motivo):   # a 1ª falha que impede a resposta fica; a triagem segue nas outras mídias
        nonlocal falha
        if mid == gatilho_id or motivo == "midia_indisponivel":
            falha = falha or motivo
        else:
            r["avisos"].append("midia_nao_entendida")

    for m in linhas:
        if not entende(con, m["tipo"]):   # desligado: no contexto fica [audio]/[imagem] e o dono confere
            if m["id"] == gatilho_id:
                falha = falha or "midia_desligada"
            else:
                r["avisos"].append("midia_desligada")
            continue
        if m["tipo"] == "imagem" and _saida_ou_sinal(m["texto"], r):   # legenda: opt-out antes de tudo
            return dict(_falha(None), sair=True)
        if m["falha_ia"]:   # já falhou antes: nada de pagar de novo nem calar a conversa
            falhou(m["id"], m["falha_ia"])
            continue
        if esperar(con, m["id"], parar, espera) != "pronta":
            if parar.is_set():   # serviço parando: não é falha da mídia
                return dict(_falha(None), parado=True)
            falhou(m["id"], "midia_indisponivel")
            continue
        if m["tipo"] == "audio":
            t = transcricao.transcrever(con, pasta_dados, cerebro_ia.base, m["id"],
                                          getattr(cerebro_ia, "tempo_transcricao", transcricao.TEMPO_S))
            if not t["ok"]:
                if t["motivo"] in transcricao.GUARDA:
                    guardar_falha(con, [m["id"]], t["motivo"])
                falhou(m["id"], t["motivo"])
                continue
            if _saida_ou_sinal(t["texto"], r):
                return dict(_falha(None), sair=True)
            continue
        imagens.append(m["id"])
    if falha is not None:
        return _falha(falha)
    if so_triagem:
        r["avisos"] = sorted(set(r["avisos"]))
        return r
    total = 0
    for mid in reversed(imagens):
        if len(r["imagens"]) >= IMAGENS_MAX:
            r["avisos"].append("imagens_demais")
            continue
        url, tamanho, motivo = _imagem(con, pasta_dados, mid)
        if motivo is None and url is None:
            return _falha("midia_indisponivel")
        if motivo is None and total + tamanho > IMAGENS_BYTES_MAX:
            motivo = "imagens_demais"
        if motivo is not None:
            if mid == gatilho_id:   # a imagem que o lead acabou de mandar não vai: nada de responder sem ela
                return _falha(motivo)
            r["avisos"].append(motivo)
            continue
        total += tamanho
        r["imagens"][mid] = url
    if imagens and not r["imagens"]:   # nenhuma imagem do lote coube: o modelo não responde sobre o que não viu
        if "imagem_grande" in r["avisos"]:
            return _falha("imagem_grande")
        return _falha("imagens_demais")
    r["avisos"] = sorted(set(r["avisos"]))
    return r
