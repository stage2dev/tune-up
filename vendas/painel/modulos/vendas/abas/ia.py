"""Aba IA: chave da OpenAI (campo segredo, vai ao serviço e fica só na pasta de dados externa), modelo escolhido
pelo dono (lista da conta; lista falhou = nome digitado), teto diário em US$ e gasto de hoje. A tela só vê
'configurada' e os 4 últimos caracteres; nenhuma mensagem de ação ecoa a chave."""

ACOES = ("ia_chave", "ia_config", "ia_apagar_chave", "ia_modo")
TEMPO_MODELOS_S = 12  # o serviço espera a OpenAI até 8 s por tentativa


def _erro(codigo, r, padrao):
    return str((r if isinstance(r, dict) else {}).get("erro") or padrao % codigo)


def ler(ctx, cliente, base=None):
    """(estado, modelos ou None, aviso). Recusa e falha viram aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", "/ia", base=base)
        if codigo != 200 or not isinstance(r, dict):
            return None, None, _erro(codigo, r, "O serviço recusou (%d).")
        if not (r.get("chave") or {}).get("configurada"):
            return r, None, None
        codigo, m = cliente.chamar(ctx, "GET", "/ia/modelos", base=base, tempo=TEMPO_MODELOS_S)
    except cliente.Recusa as e:
        return None, None, str(e)
    if codigo == 200 and isinstance(m, dict) and isinstance(m.get("modelos"), list) and m["modelos"]:
        return r, [str(x) for x in m["modelos"]], None
    motivo = (m or {}).get("codigo") if isinstance(m, dict) else None
    return r, None, "Não consegui a lista de modelos da conta%s. Digite o nome do modelo." % (
        " (%s)" % motivo if motivo else "")


def blocos(estado, modelos, aviso):
    if estado is None:
        return [{"tipo": "texto", "titulo": "IA indisponível", "texto": aviso or "O serviço não respondeu."}]
    k = estado.get("chave") or {}
    modelo, sugestao = estado.get("modelo"), estado.get("sugestao") or ""
    itens = [{"rotulo": "Chave da OpenAI", "valor": "configurada (****%s)" % k.get("final") if k.get("configurada")
              else "não configurada", "tom": "bom" if k.get("configurada") else "atencao"},
             {"rotulo": "Modelo", "valor": modelo or "não escolhido", "tom": "neutro" if modelo else "atencao"},
             {"rotulo": "Teto diário", "valor": "US$ %.2f" % float(estado.get("teto_usd") or 0)},
             {"rotulo": "Gasto hoje", "valor": "US$ %.4f" % float(estado.get("gasto_hoje_usd") or 0)}]
    saida = [{"tipo": "kpis", "titulo": "IA de vendas", "itens": itens}]
    if modelo and not estado.get("preco_conhecido", True):
        saida.append({"tipo": "texto", "titulo": "Preço do modelo desconhecido",
                      "texto": "O modelo %s não está na tabela de preços. O gasto é contado pelo preço da entrada "
                               "mais cara da tabela (precos.json na pasta de dados)." % modelo})
    saber = estado.get("conhecimento")
    if saber:
        sim = lambda ok, falta: ("ok" if ok else falta)  # noqa: E731
        saida.append({"tipo": "kpis", "titulo": "O que a IA sabe", "itens": [
            {"rotulo": "oferta.md", "valor": sim(saber.get("oferta"), "falta: a IA fica desligada"),
             "tom": "bom" if saber.get("oferta") else "atencao"},
            {"rotulo": "tom.md", "valor": sim(saber.get("tom"), "não tem: tom natural e direto")},
            {"rotulo": "links.json", "valor": "%d link(s)" % saber.get("links", 0) if saber.get("links")
             else "não tem: a IA não manda link"},
            {"rotulo": "Métodos de venda", "valor": sim(saber.get("metodos"), "não achei o arquivo do plugin")}]})
        if saber.get("avisos"):
            saida.append({"tipo": "texto", "titulo": "Atenção nos arquivos da IA",
                          "texto": "\n".join(saber["avisos"]) + "\nOs arquivos ficam em .tune-up/<pacote>/vendas/ "
                                   "(copie os exemplos da pasta conhecimento/exemplos do plugin)."})
    if aviso:
        saida.append({"tipo": "texto", "titulo": "Lista de modelos", "texto": aviso})
    saida.append({"tipo": "formulario", "id": "ia_chave", "titulo": "Trocar a chave da OpenAI" if k.get(
        "configurada") else "Colar a chave da OpenAI",
        "descricao": "A chave vai para o serviço e fica só num arquivo protegido na pasta de dados, fora do "
                     "projeto. Depois a tela mostra só os 4 últimos caracteres.",
        "acao": "ia_chave", "botao": "Trocar chave" if k.get("configurada") else "Salvar chave",
        "campos": [{"id": "chave", "rotulo": "Chave da OpenAI", "tipo": "segredo", "obrigatorio": True}]})
    saida.append({"tipo": "formulario", "id": "ia_modo", "titulo": "Modo da IA (padrão do projeto)",
                  "descricao": "Rascunho: a IA escreve e NADA sai até você aprovar na aba Conversas. Automático: a IA "
                               "envia sozinha. Cada conversa pode trocar o seu modo na aba Conversas.",
                  "acao": "ia_modo", "botao": "Salvar modo", "campos": [
                      {"id": "modo", "rotulo": "Modo", "tipo": "escolha", "obrigatorio": True,
                       "valor": estado.get("modo_padrao") or "rascunho",
                       "opcoes": [{"valor": "rascunho", "rotulo": "Rascunho (você aprova)"},
                                  {"valor": "automatico", "rotulo": "Automático (a IA envia)"}]}]})
    if modelos:
        opcoes = [{"valor": m, "rotulo": m} for m in modelos]
        campo = {"id": "modelo", "rotulo": "Modelo", "tipo": "escolha", "opcoes": opcoes, "obrigatorio": True,
                 "valor": modelo if modelo in modelos else (sugestao if sugestao in modelos else modelos[0]),
                 "ajuda": "Modelos da sua conta. Sugestão: %s." % sugestao}
    else:
        campo = {"id": "modelo", "rotulo": "Modelo", "tipo": "texto", "valor": modelo or sugestao,
                 "obrigatorio": True, "ajuda": "Nome do modelo da OpenAI. Sugestão: %s." % sugestao}
    saida.append({"tipo": "formulario", "id": "ia_config", "titulo": "Modelo e teto diário",
                  "descricao": "Ao chegar no teto do dia, a IA não chama a OpenAI e a conversa fica "
                               "\"precisa de você\".", "acao": "ia_config", "botao": "Salvar", "campos": [
                      campo, {"id": "teto_usd", "rotulo": "Teto diário (US$)", "tipo": "texto", "obrigatorio": True,
                              "valor": "%.2f" % float(estado.get("teto_usd") or 0)}]})
    if k.get("configurada"):
        saida.append({"tipo": "formulario", "id": "ia_apagar_chave", "titulo": "Apagar a chave",
                      "descricao": "Sem chave a IA para e as conversas ficam \"precisa de você\".",
                      "acao": "ia_apagar_chave", "botao": "Apagar chave", "campos": [
                          {"id": "confirmar", "rotulo": "Apagar mesmo a chave?", "tipo": "escolha", "valor": "nao",
                           "obrigatorio": True, "opcoes": [{"valor": "nao", "rotulo": "Não"},
                                                           {"valor": "sim", "rotulo": "Sim, apagar"}]}]})
    return saida


def agir(ctx, cliente, acao, dados, base=None):
    """A chave vai só no corpo do pedido ao serviço; nenhuma mensagem devolvida a contém."""
    dados = dados or {}
    if acao == "ia_chave":
        if not isinstance(dados.get("chave"), str) or not dados["chave"].strip():
            return {"ok": False, "mensagem": "Cole a chave."}
        caminho, corpo = "/ia/chave", {"chave": dados["chave"]}
    elif acao == "ia_apagar_chave":
        if dados.get("confirmar") != "sim":
            return {"ok": False, "mensagem": "Escolha \"Sim, apagar\" para apagar a chave."}
        caminho, corpo = "/ia/chave/apagar", {"confirmar": True}
    elif acao == "ia_modo":
        caminho, corpo = "/ia/modo", {"modo": dados.get("modo")}
    else:
        caminho, corpo = "/ia/config", {"modelo": dados.get("modelo"), "teto_usd": dados.get("teto_usd")}
    try:
        codigo, r = cliente.chamar(ctx, "POST", caminho, corpo, base=base)
    except cliente.Recusa as e:
        return {"ok": False, "mensagem": str(e)}
    if codigo != 200 or not isinstance(r, dict):
        return {"ok": False, "mensagem": _erro(codigo, r, "O serviço recusou (%d).")}
    if acao == "ia_chave":
        return {"ok": True, "mensagem": "Chave salva (final ****%s)." % ((r.get("chave") or {}).get("final") or "")}
    if acao == "ia_modo":
        return {"ok": True, "mensagem": "Modo padrão da IA: %s." % ("automático" if r.get("modo_padrao") ==
                                                                  "automatico" else "rascunho")}
    if acao == "ia_apagar_chave":
        return {"ok": True, "mensagem": "Chave apagada." if r.get("apagada") else "Não havia chave."}
    return {"ok": True, "mensagem": "Modelo %s e teto de US$ %.2f salvos." % (r.get("modelo"), r.get("teto_usd"))}
