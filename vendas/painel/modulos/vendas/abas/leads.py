"""Aba Leads: contagens, filtros, lista (telefone mascarado, nome sempre como texto) e importação de CSV colado.
CSV grande vai pelo comando de terminal (servico/importar.py): a tela não envia arquivo. Nada aqui lê o token."""
import os
import shlex

ACOES = ("leads_filtrar", "leads_importar")
TEXTO_MAX = 25000  # bytes: cabe no corpo de 32 KB da rota de ação do painel
BASES = [("consentimento", "Consentimento do contato"), ("cliente_existente", "Já é cliente"),
         ("contato_publico_da_empresa", "Contato público da empresa"), ("outro", "Outro (explique abaixo)")]
QUALIFICACOES = [("", "Todas"), ("frio", "Frio"), ("morno", "Morno"), ("quente", "Quente"), ("sem", "Sem qualificação")]
SIM_NAO = [("", "Tanto faz"), ("sim", "Sim"), ("nao", "Não")]
LIMITE_LISTA = 50
PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
IMPORTAR = os.path.join(PLUGIN, "servico", "importar.py")


def _opcoes(pares):
    return [{"valor": v, "rotulo": r} for v, r in pares]


def comando(ctx):
    raiz = (ctx or {}).get("raiz") or "<raiz do projeto>"
    return "python3 -B %s --projeto %s arquivo.csv --origem <origem> --base-legal <base>" % (
        shlex.quote(IMPORTAR), shlex.quote(raiz))


def ler(ctx, cliente, base=None):
    """(dados, aviso). Recusa e falha viram aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", "/leads", base=base)
    except cliente.Recusa as e:
        return None, str(e)
    if codigo != 200 or not isinstance(r, dict):
        return None, str((r if isinstance(r, dict) else {}).get("erro") or "O serviço recusou (%d)." % codigo)
    return r, None


def _resumo(r):
    texto = "Importados: %d. Já existiam ou repetidos no arquivo (mesclados, nada mudou neles): %d. Recusados: %d." % (
        r.get("importados", 0), r.get("mesclados", 0), r.get("recusados", 0))
    motivos = r.get("motivos") or []
    if motivos:
        texto += "\nRecusadas: " + "; ".join("linha %s (%s)" % (m.get("linha"), m.get("motivo")) for m in motivos)
        if r.get("motivos_cortados"):
            texto += "; ... (só as primeiras %d)" % len(motivos)
    return texto


def agir(ctx, cliente, acao, dados, base=None):
    dados = dados or {}
    if acao == "leads_filtrar":
        corpo = {k: str(dados.get(k) or "") for k in ("origem", "qualificacao", "optout", "conversa")}
        caminho = "/leads/filtro"
    else:
        texto = dados.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            return {"ok": False, "mensagem": "Cole o CSV (com a linha de títulos: nome, telefone, origem)."}
        if len(texto.encode("utf-8")) > TEXTO_MAX:
            return {"ok": False, "mensagem": "CSV grande demais para colar (máximo ~25 KB). Use o comando de terminal."}
        corpo = {"texto": texto, "origem": str(dados.get("origem") or ""), "base_legal": dados.get("base_legal"),
                 "base_legal_texto": str(dados.get("base_legal_texto") or "")}
        caminho = "/leads/importar-texto"
    try:
        codigo, r = cliente.chamar(ctx, "POST", caminho, corpo, base=base)
    except cliente.Recusa as e:
        return {"ok": False, "mensagem": str(e)}
    if codigo != 200 or not isinstance(r, dict):
        return {"ok": False, "mensagem": str((r if isinstance(r, dict) else {}).get("erro")
                                             or "O serviço recusou (%d)." % codigo)}
    if acao == "leads_filtrar":
        return {"ok": True, "mensagem": "Filtro aplicado."}
    return {"ok": True, "mensagem": _resumo(r)}


def _linha(lead):
    nome = lead.get("nome") or "(sem nome)"
    return {"nome": nome, "telefone": lead.get("telefone_mascarado") or "", "origem": lead.get("origem") or "",
            "base_legal": lead.get("base_legal") or "", "qualificacao": lead.get("qualificacao") or "sem",
            "saiu": "saiu (opt-out)" if lead.get("saiu") else "", "conversa": "sim" if lead.get("tem_conversa") else ""}


def blocos(ctx, dados, aviso):
    if dados is None:
        return [{"tipo": "texto", "titulo": "Leads indisponíveis", "texto": aviso or "O serviço não respondeu."}]
    c, f = dados.get("contagens") or {}, dados.get("filtro") or {}
    saida = [{"tipo": "kpis", "titulo": "Leads", "itens": [
        {"rotulo": "Contatos", "valor": c.get("total", 0)}, {"rotulo": "Com conversa", "valor": c.get("com_conversa", 0)},
        {"rotulo": "Saíram (opt-out)", "valor": c.get("optout", 0)},
        {"rotulo": "Frio", "valor": c.get("frio", 0)}, {"rotulo": "Morno", "valor": c.get("morno", 0)},
        {"rotulo": "Quente", "valor": c.get("quente", 0), "tom": "bom" if c.get("quente") else "neutro"}]}]
    origens = [{"valor": "", "rotulo": "Todas"}] + [{"valor": o, "rotulo": o} for o in dados.get("origens") or []]
    saida.append({"tipo": "formulario", "id": "leads_filtrar", "titulo": "Filtros", "acao": "leads_filtrar",
                  "botao": "Filtrar", "campos": [
        {"id": "origem", "rotulo": "Origem", "tipo": "escolha", "valor": f.get("origem") or "", "opcoes": origens},
        {"id": "qualificacao", "rotulo": "Qualificação", "tipo": "escolha", "valor": f.get("qualificacao") or "",
         "opcoes": _opcoes(QUALIFICACOES)},
        {"id": "optout", "rotulo": "Saiu (opt-out)", "tipo": "escolha", "valor": f.get("optout") or "",
         "opcoes": _opcoes(SIM_NAO)},
        {"id": "conversa", "rotulo": "Tem conversa", "tipo": "escolha", "valor": f.get("conversa") or "",
         "opcoes": _opcoes(SIM_NAO)}]})
    leads = dados.get("leads") or []
    saida.append({"tipo": "tabela", "titulo": "Contatos (%d de %d com este filtro; telefone mascarado)" % (
        len(leads), dados.get("total_filtrado", 0)), "colunas": [
        {"id": "nome", "rotulo": "Nome"}, {"id": "telefone", "rotulo": "Telefone"},
        {"id": "origem", "rotulo": "Origem"}, {"id": "base_legal", "rotulo": "Base legal"},
        {"id": "qualificacao", "rotulo": "Qualificação"}, {"id": "saiu", "rotulo": "Saída"},
        {"id": "conversa", "rotulo": "Conversa"}], "linhas": [_linha(x) for x in leads[:LIMITE_LISTA]],
        "vazio": "Nenhum contato com este filtro."})
    saida.append({"tipo": "formulario", "id": "leads_importar", "titulo": "Importar CSV (listas pequenas)",
                  "descricao": ("Cole o CSV com a linha de títulos nome, telefone e origem (separador , ou ;), até "
                                "~25 KB. Cada linha precisa de origem: da coluna origem ou da origem padrão "
                                "abaixo; linha sem origem é recusada. Quem já existe não muda e quem saiu "
                                "continua fora. Para arquivos maiores (até 2 MB) rode no terminal: %s" % comando(ctx)),
                  "acao": "leads_importar", "botao": "Importar", "campos": [
        {"id": "texto", "rotulo": "CSV", "tipo": "texto_longo", "obrigatorio": True},
        {"id": "origem", "rotulo": "Origem padrão (para linhas sem origem)", "tipo": "texto"},
        {"id": "base_legal", "rotulo": "Base legal", "tipo": "escolha", "obrigatorio": True,
         "opcoes": _opcoes(BASES)},
        {"id": "base_legal_texto", "rotulo": "Se \"Outro\": explique", "tipo": "texto"}]})
    return saida
