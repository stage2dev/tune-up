"""Buscador, parte Google Places (opcional, chave do próprio dono). A busca é uma ação; o resultado da última busca é
lido do serviço (que só o tem na memória) e desenhado aqui, com a atribuição do Google. Guardar grava só o place_id
(+ nicho e cidade). A chave é um campo `segredo`: vai ao serviço e nunca volta (só 'configurada' e os 4 últimos)."""
ACOES = ("places_chave", "places_apagar_chave", "places_teto", "places_buscar", "places_guardar")
TEMPO_BUSCA_S = 18  # o serviço espera o Google 15 s; o agir do painel tem 20 s


def ler(ctx, cliente, base=None):
    """(dados, aviso). Falha vira aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", "/places", base=base)
    except cliente.Recusa as e:
        return None, str(e)
    if codigo != 200 or not isinstance(r, dict):
        return None, str((r if isinstance(r, dict) else {}).get("erro") or "O serviço recusou (%d)." % codigo)
    return r, None


def _texto(valor):
    return valor if isinstance(valor, str) else ""


def agir(ctx, cliente, acao, dados, base=None):
    dados = dados or {}
    tempo = None
    if acao == "places_chave":
        if not isinstance(dados.get("chave"), str) or not dados["chave"].strip():
            return {"ok": False, "mensagem": "Cole a chave."}
        caminho, corpo = "/places/chave", {"chave": dados["chave"]}
    elif acao == "places_apagar_chave":
        if dados.get("confirmar") != "sim":
            return {"ok": False, "mensagem": "Escolha \"Sim, apagar\" para apagar a chave."}
        caminho, corpo = "/places/chave/apagar", {"confirmar": True}
    elif acao == "places_teto":
        caminho, corpo = "/places/teto", {"teto_dia": dados.get("teto_dia")}
    elif acao == "places_buscar":
        caminho, corpo, tempo = "/places/buscar", {k: _texto(dados.get(k)) for k in ("nicho", "cidade")}, TEMPO_BUSCA_S
    else:
        caminho, corpo = "/places/guardar", {k: _texto(dados.get(k)) for k in ("place_id", "nicho", "cidade")}
    try:
        codigo, r = cliente.chamar(ctx, "POST", caminho, corpo, base=base, tempo=tempo)
    except cliente.Recusa as e:
        return {"ok": False, "mensagem": str(e)}
    if codigo != 200 or not isinstance(r, dict):
        return {"ok": False, "mensagem": str((r if isinstance(r, dict) else {}).get("erro")
                                             or "O serviço recusou (%d)." % codigo)}
    if acao == "places_chave":
        return {"ok": True, "mensagem": "Chave salva (final ****%s)." % ((r.get("chave") or {}).get("final") or "")}
    if acao == "places_apagar_chave":
        return {"ok": True, "mensagem": "Chave apagada." if r.get("apagada") else "Não havia chave."}
    if acao == "places_teto":
        return {"ok": True, "mensagem": "Teto diário: %s buscas." % r.get("teto_dia")}
    if acao == "places_buscar":
        return {"ok": True, "mensagem": "%s resultado(s) do Google, mostrados abaixo." % r.get("total", 0)}
    return {"ok": True, "mensagem": "Este lugar já estava guardado." if r.get("ja") else "Lugar guardado (só o código)."}


def _site(valor, endereco):
    return endereco(valor) if valor else "sem site"


def blocos(dados, aviso, endereco):
    """`endereco` é buscador.endereco (só http/https vira texto de endereço)."""
    if dados is None:
        return [{"tipo": "texto", "titulo": "Google Places indisponível", "texto": aviso or "O serviço não respondeu."}]
    k = dados.get("chave") or {}
    saida = [
        {"tipo": "texto", "titulo": "Google Places (opcional)", "texto": (
            "Busca por texto com a SUA chave da Places API (New) do Google. O resultado só aparece aqui, na hora: pelos "
            "termos do Google, nada além do código do lugar pode ser guardado. Para virar candidato, use o buscador "
            "da web ou digite o telefone que está no site da própria empresa. %s Chave: %s. Buscas hoje: %s de %s." % (
                dados.get("atribuicao") or "", "configurada (final ****%s)" % k.get("final") if k.get("configurada")
                else "não configurada", dados.get("usados_hoje", 0), dados.get("teto_dia", 0)))},
        {"tipo": "formulario", "id": "places_chave", "titulo": "Trocar a chave do Google" if k.get("configurada")
         else "Colar a chave do Google Places", "acao": "places_chave", "botao": "Salvar chave", "descricao": (
            "A chave vai para o serviço e fica só num arquivo protegido na pasta de dados, fora do projeto. Esta "
            "tela nunca a mostra de volta."), "campos": [
            {"id": "chave", "rotulo": "Chave do Google Places", "tipo": "segredo", "obrigatorio": True}]},
        {"tipo": "formulario", "id": "places_teto", "titulo": "Teto diário de buscas", "acao": "places_teto",
         "botao": "Salvar teto", "descricao": "Cada busca pode ser cobrada pelo Google; o serviço para no teto.",
         "campos": [{"id": "teto_dia", "rotulo": "Buscas por dia (0 a 1000)", "tipo": "texto",
                     "valor": str(dados.get("teto_dia", 50)), "obrigatorio": True}]}]
    if k.get("configurada"):
        saida.append({"tipo": "formulario", "id": "places_buscar", "titulo": "Buscar no Google", "acao": "places_buscar",
                      "botao": "Buscar", "campos": [
                          {"id": "nicho", "rotulo": "Nicho (ex.: clínica veterinária)", "tipo": "texto", "obrigatorio": True},
                          {"id": "cidade", "rotulo": "Cidade", "tipo": "texto", "obrigatorio": True}]})
    ultima = dados.get("ultima")
    if ultima:
        lugares = ultima.get("lugares") or []
        saida.append({"tipo": "tabela", "titulo": "Google Maps: %s em %s (só na tela, some em 10 min)" % (
            ultima.get("nicho"), ultima.get("cidade")), "colunas": [
            {"id": "nome", "rotulo": "Nome"}, {"id": "endereco", "rotulo": "Endereço"},
            {"id": "site", "rotulo": "Site"}, {"id": "telefone", "rotulo": "Telefone"}],
            "linhas": [{"nome": x.get("nome") or "(sem nome)", "endereco": x.get("endereco") or "",
                        "site": _site(x.get("site"), endereco), "telefone": x.get("telefone") or "sem telefone"}
                       for x in lugares], "vazio": "O Google não achou nada."})
        for x in lugares:
            saida.append({"tipo": "formulario", "id": "places_guardar_" + x["place_id"], "acao": "places_guardar",
                          "botao": "Guardar", "titulo": "Guardar: %s" % (x.get("nome") or "(sem nome)"), "campos": [],
                          "descricao": "Guarda só o código do lugar (para buscar de novo depois), com o nicho e a cidade.",
                          "dados_fixos": {"place_id": x["place_id"], "nicho": ultima.get("nicho"),
                                          "cidade": ultima.get("cidade")}})
    guardados = dados.get("guardados") or []
    saida.append({"tipo": "tabela", "titulo": "Lugares guardados (só o código)", "colunas": [
        {"id": "place_id", "rotulo": "Código do lugar"}, {"id": "nicho", "rotulo": "Nicho"},
        {"id": "cidade", "rotulo": "Cidade"}], "linhas": [
        {"place_id": g.get("place_id"), "nicho": g.get("nicho"), "cidade": g.get("cidade")} for g in guardados],
        "vazio": "Nenhum lugar guardado."})
    if k.get("configurada"):
        saida.append({"tipo": "formulario", "id": "places_apagar_chave", "titulo": "Apagar a chave do Google",
                      "acao": "places_apagar_chave", "botao": "Apagar chave", "campos": [
                          {"id": "confirmar", "rotulo": "Apagar mesmo a chave?", "tipo": "escolha", "valor": "nao",
                           "opcoes": [{"valor": "nao", "rotulo": "Não"}, {"valor": "sim", "rotulo": "Sim, apagar"}]}]})
    return saida
