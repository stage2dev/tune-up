"""Vagas do teto (`max_execucoes`): execuções ativas do painel mais as sessões ocupadas abertas fora dele.

Só recusa o pedido novo (409); nenhuma sessão é parada. Lista do CLI com falha: conta só o registro.
"""
import os

from erros import ErroAcao
from leitor import da_raiz


def _ocupada(linha):
    status = str(linha.get("status") or "").lower()
    return status == "busy" or (not status and str(linha.get("state") or "").lower()
                                in ("working", "running", "busy", "active"))


def _no_projeto(cwd, raiz):
    if not isinstance(cwd, str) or not os.path.isabs(cwd):
        return False
    try:
        return da_raiz(os.path.realpath(cwd), raiz)
    except (OSError, ValueError):
        return False


def externas(linhas, raiz, execs, ativas, propria=""):
    """Quantas linhas de `claude agents` são sessões ocupadas deste projeto que o painel ainda não contou.

    Linha com `id` no registro: o registro já decide. Linha interativa não tem `id`: sai da conta se a sessão
    é de uma execução ativa ou da que está sendo respondida (`propria`).
    """
    linhas = [x for x in linhas or [] if isinstance(x, dict)]
    raiz = os.path.realpath(raiz)
    registradas, contadas = {e["id"] for e in execs}, {e["id"] for e in ativas} | {propria}
    vistas = {e["sessao_id"] for e in execs if e["id"] in contadas}
    vistas |= {str(x.get("sessionId") or "") for x in linhas if x.get("id") and str(x["id"]) in contadas}
    total = 0
    for x in linhas:
        sid = str(x.get("sessionId") or "")
        if str(x.get("id") or "") in registradas or (sid and sid in vistas):
            continue
        if _ocupada(x) and _no_projeto(x.get("cwd"), raiz):
            vistas.add(sid)
            total += 1
    return total


def conferir(lanc, execs, ativas, propria=""):
    """Teto cheio = ErroAcao 409. Sem execucao_id: com id, a tela diria que este mesmo pedido já roda."""
    try:
        fora = externas(lanc.linhas, lanc.cfg["workspace"], execs, ativas, propria)
    except Exception:  # não deu para contar as de fora: vale só o registro
        fora = 0
    total, limite = len(ativas) + fora, lanc.cfg["max_execucoes"]
    if total >= limite:
        de_fora = " (%d %s fora do painel)" % (fora, "aberta" if fora == 1 else "abertas") if fora else ""
        raise ErroAcao("Já tem %d rodando ao mesmo tempo%s. O limite é %d. Espere uma acabar ou pare uma."
                       % (total, de_fora, limite), 409)
