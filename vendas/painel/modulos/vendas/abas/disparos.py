"""Aba Disparos: campanhas (progresso, motivos agrupados, pausa com motivo), aquecimento de hoje, janela, prévia de 3
mensagens, criar, ativar (com confirmação e aviso de contato frio), pausar e retomar. Tudo pelo serviço (cliente.chamar);
a tela só lê o que o serviço devolve, que nunca traz telefone. Falha do serviço volta como erro, nunca como sucesso."""
ACOES = ("disparos_empresa", "disparos_previa", "disparos_criar", "disparos_ativar", "disparos_pausar",
         "disparos_retomar")
BASES = [("", "Todas"), ("consentimento", "Consentimento do contato"), ("cliente_existente", "Já é cliente"),
         ("contato_publico_da_empresa", "Contato público da empresa"), ("outro", "Outro")]
QUALIFICACOES = [("", "Todas"), ("frio", "Frio"), ("morno", "Morno"), ("quente", "Quente"), ("sem", "Sem qualificação")]
ESTADOS = {"rascunho": "rascunho", "ativa": "ativa", "pausada": "pausada", "concluida": "concluída"}
MOTIVOS = {
    "optout": "saiu da lista (opt-out)", "numero_invalido": "número inexistente no WhatsApp",
    "fora_da_janela": "fora da janela 09:00-19:00 (espera abrir)", "teto_minuto": "teto de 8 por minuto (espera)",
    "teto_hora": "teto de 200 por hora (espera)", "teto_contatos_novos_dia": "aquecimento: teto de contatos novos do dia",
    "pausa_humana": "conversa com o dono ou pausada (espera)", "sem_nome": "contato sem nome",
    "sem_origem": "contato sem origem", "valor_invalido": "nome ou origem com chave { }",
    "mensagem_longa": "mensagem passa de 1000 caracteres", "link_fora_da_lista": "link fora do links.json",
    "pausada_pelo_dono": "você pausou", "sem_numero_descartavel": "sem número descartável conectado",
    "modelo_invalido": "modelo da mensagem inválido", "sem_empresa": "falta o nome da empresa",
    "sem_identificacao": "a mensagem não identifica a empresa ou a origem", "sem_sair": "a mensagem não ensina a sair",
    "fuso_invalido": "fuso do projeto inválido"}
AVISO_FRIO = ("Atenção: tem contato frio (nunca recebeu nada de você ou sem consentimento). Disparo a frio viola a "
              "Política do WhatsApp Business e pode banir o número; só use um número descartável. ")
CAMPANHAS_NA_TELA = 10
SUFIXO = {"disparos_ativar": "ativar", "disparos_pausar": "pausar", "disparos_retomar": "retomar"}


def _opcoes(pares):
    return [{"valor": v, "rotulo": r} for v, r in pares]


def motivo_texto(motivo):
    """Motivo em pt-BR; '5_falhas_seguidas:xxx' (pausa do agendador) e motivos novos viram texto legível."""
    if not isinstance(motivo, str):
        return ""
    if motivo.startswith("5_falhas_seguidas"):
        return "5 falhas seguidas do envio (%s)" % motivo.partition(":")[2]
    return MOTIVOS.get(motivo, motivo)


def ler(ctx, cliente, base=None):
    """(dados, aviso). Recusa e falha viram aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", "/disparos", base=base)
    except cliente.Recusa as e:
        return None, str(e)
    if codigo != 200 or not isinstance(r, dict):
        return None, str((r if isinstance(r, dict) else {}).get("erro") or "O serviço recusou (%d)." % codigo)
    return r, None


def _id(dados):
    valor = (dados or {}).get("campanha_id")
    return valor if type(valor) is int and valor > 0 else None


def _chamar(ctx, cliente, metodo, caminho, corpo, base):
    """(resposta, None) ou (None, mensagem de erro)."""
    try:
        codigo, r = cliente.chamar(ctx, metodo, caminho, corpo, base=base)
    except cliente.Recusa as e:
        return None, str(e)
    r = r if isinstance(r, dict) else {}
    if codigo != 200:
        return None, str(r.get("erro") or "O serviço recusou (%d)." % codigo)
    return r, None


def _resumo_previa(r):
    texto = "%d contato(s) escolhido(s); %d novo(s) para o aquecimento; %d frio(s)." % (
        r.get("total", 0), r.get("novos", 0), r.get("frios", 0))
    for i, a in enumerate(r.get("amostras") or [], 1):
        texto += "\n%d) %s" % (i, a.get("texto") or "(não sairia: %s)" % motivo_texto(a.get("motivo")))
    return texto


def agir(ctx, cliente, acao, dados, base=None):
    dados = dados or {}
    if acao == "disparos_empresa":
        corpo, caminho = {"empresa": str(dados.get("empresa") or "")}, "/campanhas/empresa"
    elif acao in ("disparos_previa", "disparos_criar"):
        corpo = {k: str(dados.get(k) or "") for k in ("modelo", "origem", "qualificacao", "base_legal")}
        if acao == "disparos_criar":
            corpo["nome"] = str(dados.get("nome") or "")
        caminho = "/disparos/" + ("previa" if acao == "disparos_previa" else "criar")
    else:
        cid = _id(dados)
        if cid is None:
            return {"ok": False, "mensagem": "Campanha inválida."}
        if acao == "disparos_ativar" and dados.get("confirmar") is not True:
            return {"ok": False, "mensagem": "Confirme para ativar a campanha."}
        corpo, caminho = {}, "/campanhas/%d/%s" % (cid, SUFIXO[acao])
    r, erro = _chamar(ctx, cliente, "POST", caminho, corpo, base)
    if erro:
        return {"ok": False, "mensagem": erro}
    if acao == "disparos_previa":
        return {"ok": True, "mensagem": _resumo_previa(r)}
    if acao == "disparos_criar":
        return {"ok": True, "mensagem": "Campanha #%s criada como rascunho. Confira a prévia e ative." % r.get("id")}
    return {"ok": True, "mensagem": {"disparos_empresa": "Empresa gravada.", "disparos_ativar": "Campanha ativada.",
                                     "disparos_pausar": "Campanha pausada.",
                                     "disparos_retomar": "Campanha retomada."}[acao]}


def _hoje(d):
    j, a = d.get("janela") or {}, d.get("aquecimento")
    if not j.get("fuso_ok", True):
        janela = {"rotulo": "Janela 09-19", "valor": "fuso inválido", "tom": "ruim"}
    else:
        janela = {"rotulo": "Janela 09-19", "valor": "dentro" if j.get("dentro") else "fora",
                  "detalhe": "agora %s no fuso do projeto" % j.get("hora"), "tom": "bom" if j.get("dentro") else "atencao"}
    aquec = ({"rotulo": "Contatos novos hoje", "valor": "%d de %d" % (a["usados"], a["teto"]),
              "detalhe": "sobram %d" % max(a["teto"] - a["usados"], 0)} if a else
             {"rotulo": "Contatos novos hoje", "valor": "sem número conectado", "tom": "atencao"})
    return {"tipo": "kpis", "titulo": "Hoje", "itens": [
        janela, aquec, {"rotulo": "Empresa", "valor": d.get("empresa") or "falta informar",
                        "tom": "neutro" if d.get("empresa") else "ruim"},
        {"rotulo": "Número descartável", "valor": "sim" if d.get("numero_descartavel") else "não",
         "detalhe": "" if d.get("numero_descartavel") else "disparo a frio fica bloqueado"}]}


def _campos(com_nome):
    campos = ([{"id": "nome", "rotulo": "Nome da campanha", "tipo": "texto", "obrigatorio": True}] if com_nome else [])
    return campos + [
        {"id": "modelo", "rotulo": "Mensagem", "tipo": "texto_longo", "obrigatorio": True,
         "ajuda": "Use {nome}, {empresa}, {origem} e ensine a sair com \"responda SAIR\"."},
        {"id": "qualificacao", "rotulo": "Qualificação", "tipo": "escolha", "valor": "",
         "opcoes": _opcoes(QUALIFICACOES)},
        {"id": "base_legal", "rotulo": "Base legal", "tipo": "escolha", "valor": "", "opcoes": _opcoes(BASES)}]


def _campanha(c):
    cont = c.get("contatos") or {}
    n = lambda k: cont.get(k, 0)  # noqa: E731
    estado = ESTADOS.get(c.get("estado"), c.get("estado"))
    saida = [{"tipo": "kpis", "titulo": "#%s %s (%s)" % (c["id"], c.get("nome") or "", estado), "itens": [
        {"rotulo": "Enviadas", "valor": n("enviado"), "tom": "bom" if n("enviado") else "neutro"},
        {"rotulo": "Na fila", "valor": n("pendente")},
        {"rotulo": "Incertas", "valor": n("incerto"), "tom": "atencao" if n("incerto") else "neutro",
         "detalhe": "podem ter saído; veja na aba Conversas" if n("incerto") else ""},
        {"rotulo": "Responderam", "valor": n("respondeu")}, {"rotulo": "Saíram (opt-out)", "valor": c.get("saiu", 0)},
        {"rotulo": "Negadas", "valor": n("negado")}, {"rotulo": "Puladas", "valor": n("pulado")},
        {"rotulo": "Falharam", "valor": n("falhou"), "tom": "ruim" if n("falhou") else "neutro"}]}]
    if c.get("estado") == "pausada" and c.get("motivo"):
        saida.append({"tipo": "texto", "titulo": "Por que está pausada",
                      "texto": motivo_texto(c["motivo"]) + ". Resolva e retome."})
    if c.get("motivos"):
        saida.append({"tipo": "lista", "titulo": "Negadas e puladas, por motivo", "itens": [
            {"titulo": motivo_texto(m.get("motivo")), "detalhe": "%d contato(s), situação: %s" % (
                m.get("n", 0), m.get("estado"))} for m in c["motivos"]]})
    if c.get("amostras"):
        saida.append({"tipo": "texto", "titulo": "Prévia (3 contatos)", "texto": "\n".join(
            "%d) %s" % (i, a.get("texto") or "(não sairia: %s)" % motivo_texto(a.get("motivo")))
            for i, a in enumerate(c["amostras"], 1))})
    dados = {"campanha_id": c["id"]}
    botoes = []
    if c.get("estado") == "rascunho":
        aviso = (AVISO_FRIO if c.get("fria") else "") + "Ativar a campanha? As mensagens começam a sair na janela."
        botoes.append({"rotulo": "Ativar", "acao": "disparos_ativar", "dados": dict(dados, confirmar=True),
                       "confirmar": aviso})
    elif c.get("estado") == "ativa":
        botoes.append({"rotulo": "Pausar", "acao": "disparos_pausar", "dados": dados})
    elif c.get("estado") == "pausada":
        botoes.append({"rotulo": "Retomar", "acao": "disparos_retomar", "dados": dados,
                       "confirmar": "Retomar a campanha? As falhas seguidas voltam a zero."})
    if botoes:
        saida.append({"tipo": "conversa", "id": "campanha%s" % c["id"], "titulo": "Ações da campanha #%s" % c["id"],
                      "mensagens": [], "botoes": botoes})
    return saida


def blocos(ctx, dados, aviso):
    if dados is None:
        return [{"tipo": "texto", "titulo": "Disparos indisponíveis", "texto": aviso or "O serviço não respondeu."}]
    campanhas = dados.get("campanhas") or []
    saida = [_hoje(dados)]
    for c in campanhas[:CAMPANHAS_NA_TELA]:
        saida += _campanha(c)
    if not campanhas:
        saida.append({"tipo": "texto", "titulo": "Campanhas", "texto": "Nenhuma campanha ainda. Crie a primeira abaixo."})
    elif len(campanhas) > CAMPANHAS_NA_TELA:
        saida.append({"tipo": "texto", "titulo": "Campanhas",
                      "texto": "Mostrando as %d mais novas de %d." % (CAMPANHAS_NA_TELA, len(campanhas))})
    saida.append({"tipo": "formulario", "id": "disparos_empresa", "titulo": "Nome da empresa",
                  "descricao": "Vai em toda primeira mensagem. A campanha só ativa com ele.",
                  "acao": "disparos_empresa", "botao": "Gravar", "campos": [
                      {"id": "empresa", "rotulo": "Empresa", "tipo": "texto", "valor": dados.get("empresa") or "",
                       "obrigatorio": True}]})
    origens = [{"valor": "", "rotulo": "Todas"}] + [{"valor": o, "rotulo": o} for o in dados.get("origens") or []]
    for acao, titulo, botao, nome in (("disparos_previa", "Prévia da campanha", "Ver prévia", False),
                                      ("disparos_criar", "Nova campanha", "Criar rascunho", True)):
        campos = _campos(nome)
        campos.insert(len(campos) - 2, {"id": "origem", "rotulo": "Origem", "tipo": "escolha", "valor": "",
                                        "opcoes": origens})
        saida.append({"tipo": "formulario", "id": acao, "titulo": titulo, "acao": acao, "botao": botao,
                      "descricao": "Os contatos vêm dos filtros (quem saiu nunca entra). A prévia mostra quantos "
                                   "são e quantos são novos para o aquecimento." if not nome else
                                   "Cria como rascunho: nada sai até você ativar.", "campos": campos})
    return saida
