"""arquivo(ctx, ref) do módulo Vendas: entrega ao painel os bytes de uma mídia de mensagem. A ref é só 'm:<id>'
(o id da mídia no serviço); o serviço é o DESTE projeto (cliente.baixar confere porta, batimento e marca) e o token
nunca aparece. Serviço parado, mídia que não está pronta ou recusa = não encontrado (o painel responde 404). Python 3.9."""
import re
import urllib.parse

REF = re.compile(r"^m:(\d{1,12})$")
LIMITE = 25 * 1024 * 1024   # o teto do painel (arquivo_ref.MAX_BYTES); passou dele o painel responde 413
NOME = re.compile(r"filename\*=UTF-8''([^;]+)", re.I)
NOME_SIMPLES = re.compile(r'filename="([^"]*)"', re.I)


def _nome(disposicao):
    achou = NOME.search(disposicao)
    if achou:
        return urllib.parse.unquote(achou.group(1))
    achou = NOME_SIMPLES.search(disposicao)
    return achou.group(1) if achou else None


def ler(ctx, cliente, ref, base=None):
    """{"mime", "dados", "nome"?, "baixar"?} ou FileNotFoundError."""
    achou = REF.fullmatch(ref) if isinstance(ref, str) else None
    if not achou:
        raise FileNotFoundError("ref")
    try:
        codigo, cab, dados = cliente.baixar(ctx, "/midia/%d" % int(achou.group(1)), LIMITE, base)
    except cliente.Recusa:
        raise FileNotFoundError("servico")
    if codigo != 200:
        raise FileNotFoundError("midia")
    mime = (cab.get("content-type") or "application/octet-stream").split(";")[0].strip().lower()
    disposicao = cab.get("content-disposition") or ""
    saida = {"mime": mime, "dados": dados}
    if _nome(disposicao):
        saida["nome"] = _nome(disposicao)
    if disposicao.lower().startswith("attachment"):
        saida["baixar"] = True
    return saida
