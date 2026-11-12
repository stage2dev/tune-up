"""Aba Buscador: candidatos do buscador de leads para o dono revisar. Aprovar (vira lead) e Descartar são por candidato
(o contrato de blocos não tem seleção múltipla). Telefone mascarado; endereços só como texto e só http/https."""
from urllib.parse import urlsplit

ACOES = ("candidato_filtrar", "candidato_aprovar", "candidato_descartar")
ESTADOS = [("novo", "Para revisar"), ("aprovado", "Aprovados"), ("descartado", "Descartados (somem em 30 dias)")]


def _opcoes(pares):
    return [{"valor": v, "rotulo": r} for v, r in pares]


def endereco(valor):
    """O endereço como texto, se for http ou https; qualquer outra coisa (javascript:, data:, ...) não é mostrada."""
    if not isinstance(valor, str) or not valor:
        return ""
    partes = urlsplit(valor)
    return valor if partes.scheme in ("http", "https") and partes.hostname else "(endereço não exibido)"


def ler(ctx, cliente, base=None):
    """(dados, aviso). Recusa e falha viram aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", "/candidatos", base=base)
    except cliente.Recusa as e:
        return None, str(e)
    if codigo != 200 or not isinstance(r, dict):
        return None, str((r if isinstance(r, dict) else {}).get("erro") or "O serviço recusou (%d)." % codigo)
    return r, None


def agir(ctx, cliente, acao, dados, base=None):
    dados = dados or {}
    if acao == "candidato_filtrar":
        corpo = {k: str(dados.get(k) or "") for k in ("nicho", "cidade", "estado")}
        caminho, feito = "/candidatos/filtro", "Filtro aplicado."
    else:
        cid = dados.get("id")
        if type(cid) is not int or cid <= 0:
            return {"ok": False, "mensagem": "Candidato inválido."}
        aprovar = acao == "candidato_aprovar"
        corpo, caminho = {}, "/candidatos/%d/%s" % (cid, "aprovar" if aprovar else "descartar")
    try:
        codigo, r = cliente.chamar(ctx, "POST", caminho, corpo, base=base)
    except cliente.Recusa as e:
        return {"ok": False, "mensagem": str(e)}
    if codigo != 200 or not isinstance(r, dict):
        return {"ok": False, "mensagem": str((r if isinstance(r, dict) else {}).get("erro")
                                             or "O serviço recusou (%d)." % codigo)}
    if acao == "candidato_filtrar":
        return {"ok": True, "mensagem": feito}
    if not aprovar:
        return {"ok": True, "mensagem": "Candidato descartado."}
    if r.get("ja"):
        return {"ok": True, "mensagem": "Este candidato já tinha sido aprovado."}
    return {"ok": True, "mensagem": "Aprovado: já era contato (nada mudou nele)." if r.get("mesclado")
            else "Aprovado: virou lead na aba Leads."}


def _linha(c):
    return {"nome": c.get("nome") or "(sem nome)", "site": endereco(c.get("site")),
            "telefone": c.get("telefone_mascarado") or "sem telefone", "fonte": endereco(c.get("url_da_fonte")),
            "nicho": c.get("nicho") or "", "cidade": c.get("cidade") or ""}


def blocos(ctx, dados, aviso, importar_form):
    if dados is None:
        return [{"tipo": "texto", "titulo": "Buscador indisponível", "texto": aviso or "O serviço não respondeu."}]
    f, c = dados.get("filtro") or {}, dados.get("contagens") or {}
    lista = dados.get("candidatos") or []
    saida = [
        {"tipo": "texto", "titulo": "Como buscar", "texto": (
            "Na tela de Ações, rode \"Buscar leads\" (vendas.buscar-leads) com o nicho e a cidade; a sessão deixa os "
            "dados públicos das empresas numa pasta. Depois clique em \"Importar candidatos\" abaixo (o serviço "
            "também importa ao ligar). Nenhum candidato vira lead nem recebe mensagem sem a sua aprovação.")},
        importar_form,
        {"tipo": "kpis", "titulo": "Candidatos", "itens": [
            {"rotulo": "Para revisar", "valor": c.get("novo", 0), "tom": "atencao" if c.get("novo") else "neutro"},
            {"rotulo": "Aprovados", "valor": c.get("aprovado", 0)},
            {"rotulo": "Descartados", "valor": c.get("descartado", 0)}]},
        {"tipo": "formulario", "id": "candidato_filtrar", "titulo": "Filtros", "acao": "candidato_filtrar",
         "botao": "Filtrar", "campos": [
            {"id": "estado", "rotulo": "Estado", "tipo": "escolha", "valor": f.get("estado") or "novo",
             "opcoes": _opcoes(ESTADOS)},
            {"id": "nicho", "rotulo": "Nicho", "tipo": "escolha", "valor": f.get("nicho") or "",
             "opcoes": _opcoes([("", "Todos")] + [(n, n) for n in dados.get("nichos") or []])},
            {"id": "cidade", "rotulo": "Cidade", "tipo": "escolha", "valor": f.get("cidade") or "",
             "opcoes": _opcoes([("", "Todas")] + [(n, n) for n in dados.get("cidades") or []])}]},
        {"tipo": "tabela", "titulo": "Candidatos (%d de %d com este filtro; telefone mascarado, endereços só como "
                                     "texto)" % (len(lista), dados.get("total_filtrado", 0)), "colunas": [
            {"id": "nome", "rotulo": "Nome"}, {"id": "site", "rotulo": "Site"}, {"id": "telefone", "rotulo": "Telefone"},
            {"id": "fonte", "rotulo": "Fonte do telefone"}, {"id": "nicho", "rotulo": "Nicho"},
            {"id": "cidade", "rotulo": "Cidade"}], "linhas": [_linha(x) for x in lista],
         "vazio": "Nenhum candidato com este filtro."}]
    if f.get("estado", "novo") == "novo":
        for x in lista:
            for acao, botao in (("candidato_aprovar", "Aprovar"), ("candidato_descartar", "Descartar")):
                saida.append({"tipo": "formulario", "id": "%s_%s" % (acao, x["id"]), "acao": acao, "botao": botao,
                              "titulo": "%s: %s" % (botao, x.get("nome") or "(sem nome)"), "campos": [],
                              "descricao": ("Vira lead (origem do buscador, base: contato público da empresa)."
                                            if acao == "candidato_aprovar" else
                                            "Some da lista; a empresa não é sugerida de novo por 30 dias."),
                              "dados_fixos": {"id": x["id"]}})
    return saida
