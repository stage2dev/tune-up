"""A IA entende áudio e imagem do lead (chaves 'IA entende áudios' e 'IA entende imagens' da aba IA: ligadas por
padrão quando há chave da OpenAI; desligada = como antes, "precisa de você" e nada vai à IA). Documento: nunca.

Na rodada do atendente, para cada áudio/imagem confiável do lead desde a última saída até o gatilho:
- espera o download (servico/midia.py) até ESPERA_MIDIA_S; pendente, falhou ou expirada = midia_indisponivel;
- áudio: transcreve (servico/transcricao.py); a transcrição vai ao modelo como DADO, rotulada como transcrição;
- imagem: só jpeg/png/webp (bytes mágicos conferidos no download), no máximo IMAGENS_MAX por rodada e
  IMAGENS_BYTES_MAX no total, como data URL com detail "low"; a que passar do limite não vai (imagens_demais).
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
    return {"ok": False, "motivo": motivo, "imagens": {}, "avisos": []}


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
    """(data URL, bytes) da imagem pronta, ou (None, 0)."""
    linha = con.execute("SELECT mimetype, arquivo FROM midias WHERE mensagem_id = ? AND estado = 'pronta'",
                        (mensagem_id,)).fetchone()
    if linha is None or linha["mimetype"] not in VISAO:
        return None, 0
    caminho = midia.caminho_do_arquivo(pasta_dados, linha["arquivo"])
    try:
        with open(caminho or "", "rb") as f:
            dados = f.read(IMAGENS_BYTES_MAX + 1)
    except OSError:
        return None, 0
    if not dados or midia.detectar("imagem", dados) != linha["mimetype"]:
        return None, 0
    return "data:%s;base64,%s" % (linha["mimetype"], base64.b64encode(dados).decode("ascii")), len(dados)


def preparar(cerebro_ia, con, conversa_id, gatilho_id, parar, entende, espera=ESPERA_MIDIA_S):
    """{ok, motivo, imagens: {mensagem_id: data URL}, avisos: [motivos que não impedem a resposta]}. A transcrição
    fica gravada na mensagem (o contexto a lê de lá). entende(con, tipo): a MESMA decisão que o recebimento usou
    (recebimento.registrar_entende); None = a IA não entende mídia (nada aqui)."""
    r = {"ok": True, "motivo": None, "imagens": {}, "avisos": []}
    if entende is None:
        return r
    pasta_dados = cerebro_ia.pasta_dados
    ultima = con.execute("SELECT COALESCE(MAX(id), 0) FROM mensagens WHERE conversa_id = ? AND direcao = 'saida' "
                         "AND id <= ?", (conversa_id, gatilho_id)).fetchone()[0]
    linhas = con.execute("SELECT id, tipo FROM mensagens WHERE conversa_id = ? AND id > ? AND id <= ? AND confiavel = 1 "
                         "AND direcao = 'entrada' AND tipo IN ('audio', 'imagem') ORDER BY id",
                         (conversa_id, ultima, gatilho_id)).fetchall()
    total = 0
    for m in linhas:
        if not entende(con, m["tipo"]):   # desligado: no contexto fica [audio]/[imagem] e o dono confere
            if m["id"] == gatilho_id:
                return _falha("midia_desligada")
            r["avisos"].append("midia_desligada")
            continue
        if esperar(con, m["id"], parar, espera) != "pronta":
            return _falha("midia_indisponivel")
        if m["tipo"] == "audio":
            t = transcricao.transcrever(con, pasta_dados, cerebro_ia.base, m["id"],
                                          getattr(cerebro_ia, "tempo_transcricao", transcricao.TEMPO_S))
            if not t["ok"]:
                return _falha(t["motivo"])
            continue
        if len(r["imagens"]) >= IMAGENS_MAX:
            r["avisos"].append("imagens_demais")
            continue
        url, tamanho = _imagem(con, pasta_dados, m["id"])
        if url is None:
            return _falha("midia_indisponivel")
        if total + tamanho > IMAGENS_BYTES_MAX:
            r["avisos"].append("imagens_demais")
            continue
        total += tamanho
        r["imagens"][m["id"]] = url
    r["avisos"] = sorted(set(r["avisos"]))
    return r
