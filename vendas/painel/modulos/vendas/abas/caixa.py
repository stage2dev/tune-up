"""Blocos da aba Conversas: a caixa de entrada (lista + conversa aberta), o rascunho da IA e os envios incertos.
Só monta blocos a partir do que o serviço devolveu; nada de token, chave ou segredo. Python 3.9, só biblioteca padrão."""
import datetime
import importlib.util
import os

_spec = importlib.util.spec_from_file_location("tune_up_vendas_motivos", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "motivos.py"))
motivos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(motivos)
motivo_pt = motivos.motivo_pt

MAX_INCERTOS = 10   # botões na tela; o resto aparece depois que estes forem decididos
ESTADOS_NOTA = ("negado", "falhou", "incerto")
AVISO_LIBERAR = ("Este contato pediu para sair. Escrever mesmo assim vale para UMA mensagem e pode ir contra o "
                 "pedido dele. Liberar?")
AVISO_AUTOMATICO = "Nesta conversa a IA vai ENVIAR as respostas sozinha, sem você aprovar. Mudar para automático?"
VAZIO = ("Nenhuma conversa ainda. As mensagens que chegarem a partir de agora aparecem aqui. Conversas antigas do "
         "WhatsApp não são importadas.")


def formatar_telefone(numero):
    """+55 (19) 9xxxx-0602 para número brasileiro; outro número vira +dígitos. Só para a tela do dono."""
    d = "".join(ch for ch in str(numero or "") if ch.isdigit())
    if d.startswith("55") and len(d) in (12, 13):
        resto = d[4:]
        return "+55 (%s) %s-%s" % (d[2:4], resto[:-4], resto[-4:])
    return "+" + d if d else "Sem número"


def _momento(iso):
    try:
        quando = datetime.datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return None
    return quando if quando.tzinfo else quando.replace(tzinfo=datetime.timezone.utc)


def _quando(iso):
    quando = _momento(iso)
    return iso or "" if quando is None else quando.astimezone().strftime("%d/%m %H:%M")


def relativo(iso, agora=None):
    """Tempo curto para a lista: agora, há 5 min, há 3 h, ontem, ou a data."""
    quando = _momento(iso)
    if quando is None:
        return ""
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    seg = (agora - quando).total_seconds()
    if seg < 60:
        return "agora"
    if seg < 3600:
        return "há %d min" % (seg // 60)
    local, hoje = quando.astimezone(), agora.astimezone()
    if local.date() == hoje.date():
        return "há %d h" % (seg // 3600)
    if (hoje.date() - local.date()).days == 1:
        return "ontem"
    return local.strftime("%d/%m")


def selo(c):
    """Um selo só, pela prioridade: saiu > precisa de você > IA pausada > rascunho esperando."""
    if c.get("saiu"):
        return {"texto": "saiu", "tom": "ruim"}
    if c.get("precisa_de_voce"):
        return {"texto": "precisa de você", "tom": "atencao"}
    if c.get("ia_pausada"):
        return {"texto": "IA pausada", "tom": "neutro"}
    if c.get("tem_rascunho"):
        return {"texto": "rascunho esperando", "tom": "bom"}
    return None


def _nome(c):
    return c.get("nome_exibido") or c.get("nome") or formatar_telefone(c.get("telefone"))


def _linha(c, aberta_id):
    item = {"id": str(c["id"]), "titulo": _nome(c), "detalhe": c.get("ultima") or "Sem mensagens",
            "quando": relativo(c.get("quando")), "ativa": c["id"] == aberta_id}
    if c.get("nao_lidas"):
        item["nao_lidas"] = c["nao_lidas"]
    if selo(c):
        item["selo"] = selo(c)
    return item


def _mensagens(r):
    saida = []
    for m in r["mensagens"]:
        item = {"id": m["id"], "de": m["de"], "texto": m["texto"], "quando": _quando(m["quando"])}
        if m.get("tipo") and m["tipo"] != "texto":
            item["tipo"] = m["tipo"]
        if m["de"] != "contato" and m.get("estado"):
            item["estado"] = m["estado"]
            if m["estado"] in ESTADOS_NOTA and m.get("motivo"):
                item["nota"] = motivo_pt(m["motivo"])
        saida.append(item)
    return saida


def _conversa(r):
    c = r["conversa"]
    dados = {"conversa_id": c["id"]}
    botoes = [{"rotulo": "Devolver para a IA", "acao": "devolver_ia", "dados": dados} if c["modo"] == "humano"
              else {"rotulo": "Assumir a conversa", "acao": "assumir_conversa", "dados": dados}]
    if c["saiu"] and not c.get("liberado"):
        botoes.append({"rotulo": "Liberar uma mensagem", "acao": "liberar_saida", "dados": dados,
                       "confirmar": AVISO_LIBERAR})
    if c.get("modo_ia_efetivo") == "automatico":
        botoes.append({"rotulo": "Voltar a só escrever rascunhos", "acao": "ia_rascunho_conversa", "dados": dados})
    else:
        botoes.append({"rotulo": "Deixar a IA enviar sozinha", "acao": "ia_automatico_conversa", "dados": dados,
                       "confirmar": AVISO_AUTOMATICO})
    estado = [s for s in [(selo(c) or {}).get("texto")] if s]
    estado.append("IA envia sozinha" if c.get("modo_ia_efetivo") == "automatico" else "IA só escreve rascunhos")
    if c.get("liberado"):
        estado.append("uma mensagem liberada")
    if c.get("motivo_humano"):
        estado.append(motivo_pt(c["motivo_humano"]))
    return {"id": "conversa_%d" % c["id"],
            "titulo": "%s, %s (%s)" % (_nome(c), formatar_telefone(c["telefone"]), "; ".join(estado)),
            "mensagens": _mensagens(r), "vazio": "Nenhuma mensagem ainda.", "botoes": botoes,
            "enviar": {"acao": "enviar_mensagem", "dados_fixos": dados, "rotulo": "Enviar"}}


def bloco_caixa(lista, aberta=None, aviso_aberta=None):
    """Uma caixa: as conversas à esquerda, a aberta ao lado. Se a aberta falhar, o aviso vai no lugar dela."""
    bloco = {"tipo": "caixa", "id": "caixa", "titulo": "Conversas (%d)" % lista.get("total", len(lista["conversas"])),
             "conversas": [_linha(c, lista.get("aberta")) for c in lista["conversas"]],
             "abrir": {"acao": "abrir_conversa"}, "vazio": VAZIO, "vazio_conversa": "Escolha uma conversa na lista."}
    if aberta:
        bloco["conversa"] = _conversa(aberta)
    elif aviso_aberta:
        bloco["conversa"] = {"id": "indisponivel", "titulo": "Esta conversa não abriu", "mensagens": [],
                             "vazio": aviso_aberta}
    return bloco


def blocos_rascunho(rascunho):
    """O rascunho da IA vira bloco próprio logo abaixo: Aprovar, Descartar e o formulário Editar e enviar."""
    if not rascunho:
        return []
    texto = {"id": "rascunho%d" % rascunho["id"], "de": "ia", "texto": rascunho["texto"],
             "quando": _quando(rascunho["criado_em"])}
    if rascunho["expirado"]:
        texto["nota"] = "Este rascunho tem mais de 24 horas: venceu e não pode mais ser enviado."
        return [{"tipo": "conversa", "id": "rascunho_%d" % rascunho["id"], "titulo": "Rascunho da IA (venceu)",
                 "mensagens": [texto]}]
    texto["nota"] = "Ainda NÃO foi enviado." + (" Ao aprovar, vai como áudio (os links vão em texto, separados)."
                                                  if rascunho.get("como_audio") else "")
    dados = {"rascunho_id": rascunho["id"]}
    return [{"tipo": "conversa", "id": "rascunho_%d" % rascunho["id"],
             "titulo": "A IA escreveu uma resposta. Você decide se envia",
             "mensagens": [texto],
             "botoes": [{"rotulo": "Aprovar e enviar", "acao": "aprovar_rascunho", "dados": dados},
                        {"rotulo": "Descartar", "acao": "descartar_rascunho", "dados": dados,
                         "confirmar": "Descartar esta resposta? Nada será enviado."}]},
            {"tipo": "formulario", "id": "editar_rascunho_%d" % rascunho["id"],
             "titulo": "Mudar o texto antes de enviar",
             "acao": "editar_rascunho", "botao": "Editar e enviar", "dados_fixos": dados,
             "campos": [{"id": "texto", "rotulo": "Mensagem", "tipo": "texto_longo", "obrigatorio": True,
                         "valor": rascunho["texto"]}]}]


def bloco_incertos(r):
    """Cada envio incerto com DUAS ações do dono: reenviar a mesma linha ou marcar como não enviado."""
    itens = r["incertos"][:MAX_INCERTOS]
    mensagens = [{"id": "e%d" % e["id"], "de": "eu", "estado": "incerto", "quando": _quando(e["quando"]),
                  "texto": "Para %s: %s" % (e["telefone_mascarado"], e["previa"]), "nota": motivo_pt(e["motivo"])}
                 for e in itens]
    botoes = []
    for e in itens:
        dados = {"envio_id": e["id"]}
        if e.get("tipo") != "audio":   # áudio não se reenvia: o arquivo já foi apagado; gere um áudio novo
            botoes.append({"rotulo": "Reenviar #%d" % e["id"], "acao": "reenviar_envio", "dados": dados,
                           "confirmar":
                               "Reenviar a MESMA mensagem? Se ela já tiver saído, o contato recebe duas vezes."})
        botoes.append({"rotulo": "Marcar #%d como não enviada" % e["id"], "acao": "descartar_envio",
                       "dados": dados, "confirmar": "Marcar como não enviada? Nada será enviado."})
    return {"tipo": "conversa", "id": "incertos",
            "titulo": "Mensagens que talvez não tenham saído (%d). Decida uma a uma" % r.get("total", len(itens)),
            "mensagens": mensagens, "botoes": botoes, "vazio": "Nenhuma."}
