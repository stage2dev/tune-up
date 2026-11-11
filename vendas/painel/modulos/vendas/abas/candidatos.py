"""Ação 'importar_candidatos': pede ao serviço DESTE projeto que importe (e apague) os arquivos do buscador de leads.
Só fala com o serviço por cliente.chamar; não lê a pasta de candidatos."""

ACOES = ("importar_candidatos",)


def _resumo(r):
    texto = "%d arquivo(s): %d candidato(s) novo(s), %d repetido(s)." % (
        r.get("arquivos", 0), r.get("novos", 0), r.get("repetidos", 0))
    if r.get("recusados") or r.get("linhas_recusadas"):
        texto += " Recusado(s): %d arquivo(s), %d linha(s)." % (r.get("recusados", 0), r.get("linhas_recusadas", 0))
    if r.get("nao_apagados"):
        texto += " %d arquivo(s) não puderam ser apagados; apague à mão." % r["nao_apagados"]
    return texto


def agir(ctx, cliente, acao, dados, base=None):
    try:
        codigo, r = cliente.chamar(ctx, "POST", "/candidatos/importar", {}, base=base)
    except cliente.Recusa as e:
        return {"ok": False, "mensagem": str(e)}
    if codigo != 200 or not isinstance(r, dict):
        return {"ok": False, "mensagem": str((r if isinstance(r, dict) else {}).get("erro")
                                             or "O serviço recusou (%d)." % codigo)}
    return {"ok": True, "mensagem": _resumo(r)}
