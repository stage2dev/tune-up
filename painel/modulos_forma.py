"""Forma mínima da resposta de montar() de um módulo (ver modulos.py): peça ruim sai com aviso, o resto passa.
Bloco caixa, selo `alerta` da aba e `atualizar_em` (2..60 s) são conferidos aqui.
Python 3.9, só biblioteca padrão.
"""
import datetime
import json

NIVEIS = ("info", "atencao", "critico")
MAX_ABAS = 30
MAX_BLOCOS = 100
MAX_ALERTAS = 50


class ErroModulo(Exception):
    def __init__(self, codigo, mensagem, avisos=None):
        Exception.__init__(self, mensagem)
        self.codigo, self.mensagem, self.avisos = codigo, mensagem, list(avisos or [])

    def corpo(self):
        return {"erro": self.mensagem, "avisos": self.avisos}


def _agora():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _texto(v, n=500):
    return v[:n] if isinstance(v, str) else ""


def _caixa(b, avisos, aba):
    """Bloco caixa: sem lista ou sem abrir.acao sai inteiro; linha sem id/titulo sai; o resto passa."""
    abrir, conv = b.get("abrir"), b.get("conversas")
    if not isinstance(conv, list) or not isinstance(abrir, dict) or not _texto(abrir.get("acao")):
        avisos.append("aba %s: bloco caixa sem 'conversas' ou sem 'abrir.acao' ignorado" % aba)
        return None
    linhas = [c for c in conv if isinstance(c, dict) and _texto(c.get("id")) and isinstance(c.get("titulo"), str)]
    if len(linhas) != len(conv):
        avisos.append("aba %s: conversa sem 'id' ou 'titulo' ignorada" % aba)
    saida = dict(b, conversas=linhas)
    if "conversa" in saida and not isinstance(saida["conversa"], dict):
        del saida["conversa"]
    return saida


def _numero(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf"))


def conferir(dado, inf):
    """Forma mínima da resposta de montar(). Peça ruim sai com aviso; o resto passa."""
    if not isinstance(dado, dict):
        raise ErroModulo(500, "Esta tela devolveu algo estranho.", ["montar() não devolveu um objeto"])
    avisos = [_texto(a) for a in dado.get("avisos") or [] if isinstance(a, str)][:50]
    alertas = []
    for a in dado.get("alertas") or []:
        if isinstance(a, dict) and a.get("nivel") in NIVEIS and isinstance(a.get("texto"), str):
            alertas.append({"nivel": a["nivel"], "texto": _texto(a["texto"])})
        else:
            avisos.append("um alerta fora do formato foi ignorado")
    abas = []
    for aba in (dado.get("abas") or [])[:MAX_ABAS]:
        if not isinstance(aba, dict) or not isinstance(aba.get("id"), str) or not isinstance(aba.get("blocos"), list):
            avisos.append("uma aba fora do formato foi ignorada")
            continue
        blocos = [b for b in aba["blocos"][:MAX_BLOCOS] if isinstance(b, dict) and isinstance(b.get("tipo"), str)]
        if len(blocos) != len(aba["blocos"][:MAX_BLOCOS]):
            avisos.append("aba %s: bloco sem 'tipo' ignorado" % _texto(aba["id"], 40))
        nome = _texto(aba["id"], 40)
        blocos = [x for x in (_caixa(b, avisos, nome) if b["tipo"] == "caixa" else b for b in blocos) if x is not None]
        aba = dict(aba, id=nome, titulo=_texto(aba.get("titulo") or aba["id"], 80), blocos=blocos)
        if not (_numero(aba.get("alerta")) and aba["alerta"] >= 1):
            aba.pop("alerta", None)
        else:
            aba["alerta"] = int(aba["alerta"])
        abas.append(aba)
    gerado = dado.get("gerado_em") if isinstance(dado.get("gerado_em"), str) else _agora()
    saida = {"id": inf["id"], "titulo": _texto(dado.get("titulo"), 60) or inf["titulo"], "gerado_em": gerado,
             "alertas": alertas[:MAX_ALERTAS], "abas": abas, "avisos": avisos}
    if _numero(dado.get("atualizar_em")):
        saida["atualizar_em"] = min(60, max(2, dado["atualizar_em"]))
    try:
        json.dumps(saida, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise ErroModulo(500, "Esta tela devolveu algo estranho.", ["resposta não vira JSON: %s" % e])
    return saida
