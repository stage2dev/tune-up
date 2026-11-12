"""Aba Conversas: ações e leitura; os blocos (caixa, rascunho, incertos) vêm de caixa.py. Caixa de envio, assumir/devolver e envios 'incerto' para o dono decidir. Só fala com o serviço por cliente.chamar (porta,
batimento e marca conferidos). Todo envio vai pelo portão do serviço; a tela nunca fala com a Evolution. Os blocos
não levam token nem chave. Python 3.9, só biblioteca padrão."""
import hashlib
import importlib.util
import os
import re

ID_CLIENTE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_spec = importlib.util.spec_from_file_location("tune_up_vendas_motivos", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "motivos.py"))
motivos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(motivos)
MOTIVOS, motivo_pt = motivos.MOTIVOS, motivos.motivo_pt
_spec = importlib.util.spec_from_file_location("tune_up_vendas_caixa", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "caixa.py"))
caixa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(caixa)  # caixa.py carrega motivos.py sozinho; nada de ciclo
MAX_INCERTOS = caixa.MAX_INCERTOS
ACOES_RASCUNHO = ("aprovar_rascunho", "editar_rascunho", "descartar_rascunho")


def _inteiro(valor):
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor if valor > 0 else None
    if isinstance(valor, str) and valor.isdigit() and len(valor) <= 12:
        return int(valor) or None
    return None


def _ler(ctx, cliente, caminho, base):
    """(dados, aviso). Serviço parado, recusa ou código diferente de 200 viram aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", caminho, base=base)
    except cliente.Recusa as e:
        return None, str(e)
    if codigo != 200 or not isinstance(r, dict):
        return None, str((r if isinstance(r, dict) else {}).get("erro") or "O serviço recusou (%d)." % codigo)
    return r, None


def blocos(ctx, cliente, base=None):
    return aba(ctx, cliente, base)[0]


def aba(ctx, cliente, base=None):
    """(blocos, total de não lidas). Uma caixa (lista + conversa aberta), o rascunho da IA logo abaixo e os envios
    incertos."""
    lista, aviso = _ler(ctx, cliente, "/conversas?limite=50", base)
    if aviso:
        return [{"tipo": "texto", "titulo": "Conversas indisponíveis", "texto": aviso}], 0
    aberta, aviso_aberta = None, None
    if lista.get("aberta"):
        aberta, aviso_aberta = _ler(ctx, cliente, "/conversas/%d?limite=50" % lista["aberta"], base)
    saida = [caixa.bloco_caixa(lista, aberta, aviso_aberta)] + caixa.blocos_rascunho((aberta or {}).get("rascunho"))
    incertos, aviso = _ler(ctx, cliente, "/incertos?limite=%d" % MAX_INCERTOS, base)
    if incertos and incertos["incertos"]:
        saida.append(caixa.bloco_incertos(incertos))
    elif aviso:
        saida.append({"tipo": "texto", "titulo": "Mensagens em dúvida indisponíveis", "texto": aviso})
    return saida, int(lista.get("nao_lidas_total") or 0)


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
    if acao == "midia_baixar_de_novo":
        midia = _inteiro(dados.get("midia_id"))
        if midia is None:
            return {"ok": False, "mensagem": "Arquivo inválido."}
        codigo, r = _chamar(ctx, cliente, "POST", "/midia/%d/baixar-de-novo" % midia, {}, base)
        if codigo is None:
            return {"ok": False, "mensagem": r}
        if codigo == 202 and r.get("estado") == "pronta" and r.get("responde") is False:
            return {"ok": True, "mensagem": "Falha limpa. Já houve resposta depois deste arquivo, então a IA não "
                                            "responde a ele agora."}
        if codigo == 202 and r.get("estado") == "pronta":
            return {"ok": True, "mensagem": "A IA vai tentar de novo com este arquivo. Atualize a tela em alguns segundos."}
        return {"ok": True, "mensagem": "Baixando de novo. Atualize a tela em alguns segundos."} if codigo == 202 \
            else {"ok": False, "mensagem": str(r.get("erro") or "O serviço recusou (%d)." % codigo)}
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
