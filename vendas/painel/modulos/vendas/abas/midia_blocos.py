"""Mídia na aba Conversas: o `midia` de cada mensagem (ref, tipo, nome, tamanho, duração, estado, aviso em português
simples e o botão de tentar de novo) e a prévia de uma linha da lista. Só usa o que o serviço devolveu: nenhum
token, caminho ou pasta do disco vai para a tela. Python 3.9, só biblioteca padrão."""

ACAO_DE_NOVO = "midia_baixar_de_novo"
PALAVRAS = 6   # palavras da transcrição na prévia da lista
FALHAS = {
    "grande_demais": "O arquivo é grande demais e não foi guardado.",
    "tipo_recusado": "O tipo do arquivo não é aceito e ele não foi guardado.",
    "disco": "Não consegui guardar o arquivo no disco. Libere espaço e tente de novo.",
    "expirada": "O WhatsApp não tem mais este arquivo para baixar.",
    "interrompida": "O download foi interrompido (o serviço foi desligado). Tente de novo.",
    "sem_segredo": "A mensagem veio sem a senha certa do webhook, então o arquivo não foi baixado.",
}
PADRAO_FALHA = "Não consegui baixar o arquivo. Tente de novo."
EXPIRADAS = {"retencao": "O arquivo foi apagado do computador pelo prazo de guarda (30 dias, por padrão).",
             "espaco": "O arquivo foi apagado do computador para liberar espaço."}
PADRAO_EXPIRADA = "O arquivo já foi apagado do computador."
ROTULOS = {"audio": "Áudio", "imagem": "Foto", "documento": "Documento"}


def duracao(segundos):
    """0:12 para 12 s; None se o serviço não sabe a duração."""
    if not isinstance(segundos, (int, float)) or isinstance(segundos, bool) or segundos < 0:
        return None
    total = int(round(segundos))
    return "%d:%02d" % (total // 60, total % 60)


def da_mensagem(m):
    """O `midia` do contrato para uma mensagem, ou None se ela não tem arquivo."""
    d = m.get("midia")
    ident = d.get("id") if isinstance(d, dict) else None
    if not isinstance(ident, int) or isinstance(ident, bool) or d.get("tipo") not in ROTULOS:
        return None
    estado = d.get("estado") if d.get("estado") in ("pronta", "pendente", "falhou", "expirada") else "pendente"
    saida = {"ref": "m:%d" % ident, "tipo": d["tipo"], "estado": estado}
    if isinstance(d.get("nome_arquivo"), str) and d["nome_arquivo"]:
        saida["nome"] = d["nome_arquivo"]
    if isinstance(d.get("bytes"), int) and d["bytes"] >= 0:
        saida["tamanho"] = d["bytes"]
    if isinstance(d.get("duracao_s"), (int, float)) and d["duracao_s"] >= 0:
        saida["duracao"] = round(d["duracao_s"])
    if estado == "pendente":
        saida["aviso"] = "Baixando o arquivo..."
    elif estado == "falhou":
        saida["aviso"] = FALHAS.get(d.get("motivo"), PADRAO_FALHA)
        saida["acao"] = {"acao": ACAO_DE_NOVO, "dados": {"midia_id": ident}}
    elif estado == "expirada":
        saida["aviso"] = EXPIRADAS.get(d.get("motivo"), PADRAO_EXPIRADA)
    return saida


def previa(c):
    """Uma linha da lista para a última mensagem de mídia; None = usa o texto que o serviço mandou."""
    tipo = c.get("ultima_tipo")
    if tipo not in ROTULOS:
        return None
    if tipo == "imagem":
        return "Foto"
    if tipo == "documento":
        return "Documento: %s" % c["ultima_nome"] if c.get("ultima_nome") else "Documento"
    tempo = duracao(c.get("ultima_duracao_s"))
    rotulo = "Áudio (%s)" % tempo if tempo else "Áudio"
    palavras = str(c.get("ultima_transcricao") or "").split()
    if not palavras:
        return rotulo
    return "%s: %s%s" % (rotulo, " ".join(palavras[:PALAVRAS]), "…" if len(palavras) > PALAVRAS else "")
