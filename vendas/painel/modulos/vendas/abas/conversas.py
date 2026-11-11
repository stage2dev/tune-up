"""Aba Conversas: lista (telefone mascarado), conversa aberta no bloco `conversa` (telefone inteiro só aqui), caixa
de envio, assumir/devolver e envios 'incerto' para o dono decidir. Só fala com o serviço por cliente.chamar (porta,
batimento e marca conferidos). Todo envio vai pelo portão do serviço; a tela nunca fala com a Evolution. Os blocos
não levam token nem chave. Python 3.9, só biblioteca padrão."""
import datetime
import hashlib
import re

ID_CLIENTE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_INCERTOS = 10   # botões na tela; o resto aparece depois que estes forem decididos
AVISO_LIBERAR = ("Este contato pediu para sair. Escrever mesmo assim vale para UMA mensagem e pode ir contra o "
                 "pedido dele. Liberar?")
MOTIVOS = {
    "optout_pede_confirmacao": "Este contato pediu para sair. Para escrever mesmo assim, use o botão \"Liberar uma "
                               "mensagem\" e envie de novo.",
    "optout": "Este contato pediu para sair; nada é enviado a ele.",
    "teto_minuto": "Muitas mensagens no último minuto (limite de 8). Espere um pouco e tente de novo.",
    "teto_hora": "Muitas mensagens na última hora. Espere um pouco e tente de novo.",
    "pausa_humana": "A conversa está com você; a IA não escreve nela.",
    "fora_da_janela": "Fora do horário permitido para esse tipo de envio.",
    "numero_invalido": "Este número não está no WhatsApp; a mensagem não saiu.",
    "fuso_invalido": "O fuso do projeto está inválido; corrija a configuração.",
    "nao_reenviavel": "Este envio não pode mais ser reenviado.",
    "nao_incerto": "Este envio já foi decidido.",
    "chave_ocupada": "Essa mensagem já foi registrada antes (clique repetido ignorado).",
    "descartado_pelo_dono": "Marcada por você como não enviada.",
    "pendente_na_subida": "O serviço reiniciou no meio do envio: não sei se saiu.",
    "sem_numero_do_dono": "O número do dono não está configurado.",
    "pedir_humano": "A IA pediu para você assumir esta conversa.",
    "erro_interno": "A IA falhou nesta conversa e foi desligada nela.",
    "rodadas": "A IA não chegou a uma resposta (voltou a chamar ferramentas) e foi desligada nesta conversa.",
    "anti_loop": "A IA repetiu a mesma resposta 3 vezes e foi desligada nesta conversa.",
    "campanha_parada": "A campanha deste envio está pausada. Retome-a na aba Disparos para reenviar.",
    "contato_fora_da_campanha": "Este contato já não espera este envio na campanha (respondeu ou saiu dela).",
    "sem_optout": "Essa confirmação só vai para quem pediu para sair.",
    "nao_e_o_dono": "O teste de áudio só vai para o número do dono.",
    "teto_teste_audio_dia": "Acabou o limite de testes de áudio de hoje.",
    "teto_audio_dia": "Acabou o limite de áudios da IA de hoje.",
    "teto_contatos_novos_dia": "Aquecimento: acabou o limite de contatos novos de hoje para este número.",
    "teto_diario": "A IA atingiu o teto de gasto do dia; responda você.",
    "sem_chave": "A IA está sem chave da OpenAI; configure na aba IA.",
    "sem_modelo": "A IA está sem modelo escolhido; configure na aba IA.",
    "sem_oferta": "A IA está sem oferta cadastrada; configure na aba IA.",
    "preco_desconhecido": "O preço do modelo da IA não está cadastrado; informe na aba IA.",
    "resposta_invalida": "A IA devolveu uma resposta inválida; responda você.",
    "resposta_cortada": "A resposta da IA veio cortada no meio e não foi enviada; responda você.",
    "sem_texto": "A IA não escreveu nada; responda você.",
    "reescrita_falhou": "A IA escreveu um comando em vez de texto e a correção falhou; nada saiu, responda você.",
    "ferramenta_como_texto": "A IA escreveu um comando em vez de texto; nada saiu, responda você.",
    "segredo": "A resposta da IA trazia algo parecido com uma chave e foi barrada.",
    "link_suspeito": "A resposta da IA trazia um link fora da lista e foi barrada.",
    "vazio": "A resposta da IA ficou vazia depois dos filtros e não saiu.",
    "rascunho_em_aprovacao": "Este rascunho já está sendo aprovado.",
    "gatilho_ja_respondido": "Essa mensagem do lead já foi respondida.",
    "gatilho_ja_tem_rascunho": "Essa mensagem do lead já tem um rascunho.",
    "envio_negado": "A resposta da IA não saiu; responda você.",
    "envio_parcial": "A resposta da IA saiu só em parte; complete você.",
    "sem_conector": "O WhatsApp não está conectado; a IA não respondeu.",
    "injecao_suspeita": "A mensagem do lead parece tentar mandar na IA; responda você.",
}
ESTADOS_NOTA = ("negado", "falhou", "incerto")
ACOES_RASCUNHO = ("aprovar_rascunho", "editar_rascunho", "descartar_rascunho")
AVISO_AUTOMATICO = ("Nesta conversa a IA vai ENVIAR as respostas sozinha, sem você aprovar. Mudar para automático?")


def motivo_pt(motivo):
    motivo = motivo or ""
    if motivo in MOTIVOS:
        return MOTIVOS[motivo]
    if motivo.startswith("incerto") or motivo.startswith("erro_inesperado") or motivo == "sem_id_externo":
        return "O WhatsApp não confirmou se a mensagem saiu."
    if motivo.startswith("nao_enviado"):
        return "O WhatsApp recusou a mensagem; ela não saiu."
    return "O envio foi recusado pelo portão (%s)." % motivo if motivo else ""


def _inteiro(valor):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    if isinstance(valor, str) and valor.isdigit() and len(valor) <= 12:
        return int(valor) or None
    return None


def _quando(iso):
    try:
        return datetime.datetime.fromisoformat(iso).astimezone().strftime("%d/%m %H:%M")
    except (TypeError, ValueError):
        return iso or ""


def _ler(ctx, cliente, caminho, base):
    """(dados, aviso). Serviço parado, recusa ou código diferente de 200 viram aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", caminho, base=base)
    except cliente.Recusa as e:
        return None, str(e)
    if codigo != 200 or not isinstance(r, dict):
        return None, str((r if isinstance(r, dict) else {}).get("erro") or "O serviço recusou (%d)." % codigo)
    return r, None


def _nome(c):
    return c.get("nome") or c.get("telefone_mascarado") or "Sem nome"


def _selos(c):
    achados = []
    if c.get("saiu"):
        achados.append(("saiu", "ruim"))
    if c.get("precisa_de_voce"):
        achados.append(("precisa de você", "atencao"))
    if c.get("ia_pausada"):
        achados.append(("IA pausada", "neutro"))
    return achados


def bloco_lista(r):
    itens = []
    for c in r["conversas"]:
        selos = _selos(c)
        item = {"titulo": "%s (%s)" % (_nome(c), c["telefone_mascarado"]) if c.get("nome") else _nome(c),
                "detalhe": " · ".join([c.get("ultima") or "sem mensagens"] + [t for t, _ in selos[1:]]
                                      + ([motivo_pt(c["motivo_humano"])] if c.get("motivo_humano") else []))}
        if selos:
            item["selo"] = {"texto": selos[0][0], "tom": selos[0][1]}
        itens.append(item)
    titulo = "Conversas (%d de %d)" % (len(itens), r.get("total", len(itens)))
    return {"tipo": "lista", "titulo": titulo, "itens": itens, "vazio": "Nenhuma conversa ainda."}


def bloco_abrir(r):
    return {"tipo": "formulario", "id": "abrir_conversa", "titulo": "Abrir uma conversa",
            "acao": "abrir_conversa", "botao": "Abrir", "campos": [
                {"id": "conversa_id", "rotulo": "Conversa", "tipo": "escolha", "obrigatorio": True,
                 "valor": str(r["aberta"]) if r.get("aberta") else "",
                 "opcoes": [{"valor": str(c["id"]), "rotulo": "%s (%s)" % (c.get("nome") or "Sem nome",
                                                                           c["telefone_mascarado"])}
                            for c in r["conversas"]]}]}


def bloco_conversa(r):
    c = r["conversa"]
    rascunho = r.get("rascunho")
    mensagens = []
    for m in r["mensagens"]:
        item = {"id": m["id"], "de": m["de"], "texto": m["texto"], "quando": _quando(m["quando"])}
        if m["de"] != "contato" and m.get("estado"):
            item["estado"] = m["estado"]
            if m["estado"] in ESTADOS_NOTA and m.get("motivo"):
                item["nota"] = motivo_pt(m["motivo"])
        mensagens.append(item)
    dados = {"conversa_id": c["id"]}
    botoes = [{"rotulo": "Devolver para a IA", "acao": "devolver_ia", "dados": dados} if c["modo"] == "humano"
              else {"rotulo": "Assumir a conversa", "acao": "assumir_conversa", "dados": dados}]
    if c["saiu"] and not c.get("liberado"):
        botoes.append({"rotulo": "Liberar uma mensagem", "acao": "liberar_saida", "dados": dados,
                       "confirmar": AVISO_LIBERAR})
    if rascunho:
        mensagens.append({"id": "rascunho%d" % rascunho["id"], "de": "ia", "texto": rascunho["texto"],
                          "quando": _quando(rascunho["criado_em"]),
                          "nota": "Rascunho da IA: ainda NÃO foi enviado." if not rascunho["expirado"] else
                          "Rascunho com mais de 24 horas: expirou e não pode mais ser aprovado."})
        if not rascunho["expirado"]:
            dados_r = {"rascunho_id": rascunho["id"]}
            botoes += [{"rotulo": "Aprovar e enviar", "acao": "aprovar_rascunho", "dados": dados_r},
                       {"rotulo": "Descartar rascunho", "acao": "descartar_rascunho", "dados": dados_r,
                        "confirmar": "Descartar este rascunho? Nada será enviado."}]
    if c.get("modo_ia_efetivo") == "automatico":
        botoes.append({"rotulo": "Voltar para rascunho nesta conversa", "acao": "ia_rascunho_conversa", "dados": dados})
    else:
        botoes.append({"rotulo": "IA em modo automático nesta conversa", "acao": "ia_automatico_conversa",
                       "dados": dados, "confirmar": AVISO_AUTOMATICO})
    estado = [t for t, _ in _selos(c)] + ["IA: " + ("automático" if c.get("modo_ia_efetivo") == "automatico"
                                                    else "rascunho")]
    estado = estado + (["envio liberado para uma mensagem"] if c.get("liberado") else [])
    if c.get("motivo_humano"):
        estado.append("IA desligada: " + motivo_pt(c["motivo_humano"]))
    return {"tipo": "conversa", "id": "conversa_%d" % c["id"],
            "titulo": "%s, %s%s" % (c.get("nome") or "Sem nome", c["telefone"],
                                    " (%s)" % ", ".join(estado) if estado else ""),
            "mensagens": mensagens, "vazio": "Nenhuma mensagem ainda.", "botoes": botoes,
            "enviar": {"acao": "enviar_mensagem", "dados_fixos": dados, "rotulo": "Enviar"}}


def bloco_incertos(r):
    """Cada envio incerto com DUAS ações do dono: reenviar a mesma linha ou marcar como não enviado."""
    itens = r["incertos"][:MAX_INCERTOS]
    mensagens = [{"id": "e%d" % e["id"], "de": "eu", "estado": "incerto", "quando": _quando(e["quando"]),
                  "texto": "Para %s: %s" % (e["telefone_mascarado"], e["previa"]), "nota": motivo_pt(e["motivo"])}
                 for e in itens]
    botoes = []
    for e in itens:
        dados = {"envio_id": e["id"]}
        botoes.append({"rotulo": "Reenviar #%d" % e["id"], "acao": "reenviar_envio", "dados": dados,
                       "confirmar": "Reenviar a MESMA mensagem? Se ela já tiver saído, o contato recebe duas vezes."})
        botoes.append({"rotulo": "Marcar #%d como não enviada" % e["id"], "acao": "descartar_envio",
                       "dados": dados, "confirmar": "Marcar como não enviada? Nada será enviado."})
    return {"tipo": "conversa", "id": "incertos",
            "titulo": "Envios incertos (%d): podem ou não ter saído; decida um a um" % r.get("total", len(itens)),
            "mensagens": mensagens, "botoes": botoes, "vazio": "Nenhum envio incerto."}


def blocos(ctx, cliente, base=None):
    lista, aviso = _ler(ctx, cliente, "/conversas?limite=50", base)
    if aviso:
        return [{"tipo": "texto", "titulo": "Conversas indisponíveis", "texto": aviso}]
    saida = [bloco_lista(lista)]
    if lista["conversas"]:
        saida.append(bloco_abrir(lista))
    if lista.get("aberta"):
        aberta, aviso = _ler(ctx, cliente, "/conversas/%d?limite=50" % lista["aberta"], base)
        saida.append(bloco_conversa(aberta) if aberta else {"tipo": "texto", "titulo": "Conversa indisponível",
                                                            "texto": aviso})
        rascunho = (aberta or {}).get("rascunho")
        if rascunho and not rascunho["expirado"]:
            saida.append({"tipo": "formulario", "id": "editar_rascunho", "titulo": "Editar o rascunho e enviar",
                          "acao": "editar_rascunho", "botao": "Enviar texto editado",
                          "dados_fixos": {"rascunho_id": rascunho["id"]},
                          "campos": [{"id": "texto", "rotulo": "Mensagem", "tipo": "texto_longo",
                                      "obrigatorio": True, "valor": rascunho["texto"]}]})
    incertos, aviso = _ler(ctx, cliente, "/incertos?limite=%d" % MAX_INCERTOS, base)
    if incertos and incertos["incertos"]:
        saida.append(bloco_incertos(incertos))
    elif aviso:
        saida.append({"tipo": "texto", "titulo": "Envios incertos indisponíveis", "texto": aviso})
    return saida


def _chamar(ctx, cliente, metodo, caminho, corpo, base, tempo=None):
    """(código, resposta) ou (None, mensagem) quando a tela não chega ao serviço certo."""
    try:
        codigo, r = cliente.chamar(ctx, metodo, caminho, corpo, base=base, tempo=tempo)
    except cliente.Recusa as e:
        return None, str(e)
    return codigo, r if isinstance(r, dict) else {}


def _resposta_envio(codigo, r, sucesso):
    """Resposta do portão em português simples. 'duplicado' = clique repetido: nada novo saiu."""
    if codigo != 200:
        return {"ok": False, "mensagem": str(r.get("erro") or "O serviço recusou (%d)." % codigo)}
    estado = r.get("estado")
    if estado == "enviado":
        return {"ok": True, "mensagem": sucesso}
    if estado == "duplicado":
        return {"ok": True, "mensagem": motivo_pt("chave_ocupada")}
    if estado == "enviando":
        return {"ok": False, "mensagem": "A mensagem ainda está saindo; não repita, confira em instantes."}
    if estado == "incerto":
        return {"ok": False, "mensagem": "Não sei se a mensagem saiu (o WhatsApp não confirmou). Ela aparece em "
                                         "\"Envios incertos\": decida lá, sem enviar de novo antes."}
    if estado == "falhou":
        return {"ok": False, "mensagem": motivo_pt(r.get("motivo")) or "A mensagem não saiu."}
    return {"ok": False, "mensagem": motivo_pt(r.get("motivo")) or "Não enviado."}


def id_do_servico(id_cliente):
    """O id da tela vira o id do serviço (letras, números, _ e -, até 64); fora disso vira um hash."""
    if ID_CLIENTE.match(id_cliente):
        return id_cliente
    return hashlib.sha256(id_cliente.encode("utf-8")).hexdigest()[:40]


def _agir_rascunho(ctx, cliente, acao, dados, base):
    """Aprovar, editar e enviar ou descartar o rascunho; a origem 'rascunho_aprovado' é fixada pelo serviço."""
    rascunho = _inteiro(dados.get("rascunho_id"))
    if rascunho is None:
        return {"ok": False, "mensagem": "Rascunho inválido."}
    if acao == "descartar_rascunho":
        codigo, r = _chamar(ctx, cliente, "POST", "/rascunhos/%d/descartar" % rascunho, {}, base)
        if codigo is None:
            return {"ok": False, "mensagem": r}
        return {"ok": codigo == 200, "mensagem": "Rascunho descartado: nada foi enviado." if codigo == 200 else
                str(r.get("erro") or "O serviço recusou (%d)." % codigo)}
    corpo = {}
    if acao == "editar_rascunho":
        texto = str(dados.get("texto") or "").strip()
        if not texto:
            return {"ok": False, "mensagem": "Escreva a mensagem."}
        corpo["texto"] = texto
    codigo, r = _chamar(ctx, cliente, "POST", "/rascunhos/%d/aprovar" % rascunho, corpo, base,
                        cliente.TEMPO_ENVIO_S)
    return {"ok": False, "mensagem": r} if codigo is None else _resposta_envio(codigo, r, "Mensagem enviada.")


def agir(ctx, cliente, acao, dados, base=None):
    dados = dados or {}
    if acao in ("reenviar_envio", "descartar_envio"):
        envio = _inteiro(dados.get("envio_id"))
        if envio is None:
            return {"ok": False, "mensagem": "Envio inválido."}
        reenviar = acao == "reenviar_envio"
        codigo, r = _chamar(ctx, cliente, "POST", "/incertos/%d/%s" % (envio, "reenviar" if reenviar else
                                                                      "descartar"), {}, base,
                            cliente.TEMPO_ENVIO_S if reenviar else None)
        if codigo is None:
            return {"ok": False, "mensagem": r}
        if not reenviar:
            return {"ok": codigo == 200, "mensagem": "Marcada como não enviada." if codigo == 200 else
                    str(r.get("erro") or "O serviço recusou (%d)." % codigo)}
        return _resposta_envio(codigo, r, "Mensagem reenviada (a mesma, sem duplicar).")
    if acao in ACOES_RASCUNHO:
        return _agir_rascunho(ctx, cliente, acao, dados, base)
    conversa = _inteiro(dados.get("conversa_id"))
    if conversa is None:
        return {"ok": False, "mensagem": "Escolha uma conversa."}
    if acao == "enviar_mensagem":
        texto, id_cliente = str(dados.get("texto") or "").strip(), dados.get("id_cliente")
        if not texto:
            return {"ok": False, "mensagem": "Escreva a mensagem."}
        if not isinstance(id_cliente, str) or not id_cliente:
            return {"ok": False, "mensagem": "A tela não mandou o identificador do envio. Recarregue a tela."}
        codigo, r = _chamar(ctx, cliente, "POST", "/enviar", {"conversa_id": conversa, "texto": texto,
                                                              "id_tela": id_do_servico(id_cliente)}, base,
                            cliente.TEMPO_ENVIO_S)
        return {"ok": False, "mensagem": r} if codigo is None else _resposta_envio(codigo, r, "Mensagem enviada.")
    rotas = {"abrir_conversa": ("/conversas/aberta", {"conversa_id": conversa}, "Conversa aberta."),
             "assumir_conversa": ("/conversas/%d/modo" % conversa, {"modo": "humano"},
                                  "Você assumiu a conversa: a IA não responde nela."),
             "devolver_ia": ("/conversas/%d/modo" % conversa, {"modo": "ia"}, "Conversa devolvida para a IA."),
             "ia_automatico_conversa": ("/conversas/%d/modo-ia" % conversa, {"modo_ia": "automatico"},
                                        "Nesta conversa a IA agora envia sozinha."),
             "ia_rascunho_conversa": ("/conversas/%d/modo-ia" % conversa, {"modo_ia": "rascunho"},
                                      "Nesta conversa a IA volta a escrever só rascunhos."),
             "liberar_saida": ("/conversas/%d/liberar" % conversa, {}, "Liberado: a próxima mensagem desta "
                                                                       "conversa pode sair.")}
    if acao not in rotas:
        return {"ok": False, "mensagem": "Ação desconhecida."}
    caminho, corpo, sucesso = rotas[acao]
    codigo, r = _chamar(ctx, cliente, "POST", caminho, corpo, base)
    if codigo is None:
        return {"ok": False, "mensagem": r}
    return {"ok": True, "mensagem": sucesso} if codigo == 200 else {
        "ok": False, "mensagem": str(r.get("erro") or "O serviço recusou (%d)." % codigo)}
