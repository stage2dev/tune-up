"""Validação de `negar`/`permitir` do JSON de uma ação (usada pelo catálogo e pelos módulos).

Só o painel usa: o gancho (travas.py rodando com -I) não importa este arquivo. Saiu de travas.py (tamanho).
"""
import json
import re

from travas import DECISOES

MAX_REGRAS = 200
MAX_TEXTO = 300
MAX_REGEX = 1000  # lista do que pode (lookahead negativo) precisa de espaço
MAX_CONF = 48 * 1024
RE_CAMPO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,40}$")
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")


def _regra(obj, onde):
    if not isinstance(obj.get("ferramenta"), str) or not obj["ferramenta"] or len(obj["ferramenta"]) > MAX_REGEX:
        raise ValueError("%s: regra sem 'ferramenta'" % onde)
    out = {"ferramenta": obj["ferramenta"]}
    for chave in ("ferramenta", "entrada"):
        if chave in obj:
            if not isinstance(obj[chave], str) or len(obj[chave]) > MAX_REGEX:
                raise ValueError("%s: '%s' precisa ser texto curto" % (onde, chave))
            try:
                re.compile(obj[chave])
            except re.error:
                raise ValueError("%s: regex '%s' inválida" % (onde, chave))
            out[chave] = obj[chave]
    if "campo" in obj:
        if not isinstance(obj["campo"], str) or not RE_CAMPO.match(obj["campo"]):
            raise ValueError("%s: 'campo' inválido" % onde)
        out["campo"] = obj["campo"]
    decisao = obj.get("decisao", "deny")
    if decisao not in DECISOES:
        raise ValueError("%s: 'decisao' precisa ser deny ou ask" % onde)
    out["decisao"] = decisao
    motivo = obj.get("motivo")
    out["motivo"] = (motivo if isinstance(motivo, str) and motivo.strip() else "regra da ação")[:160]
    return out


def validar_travas(acao):
    """Lê negar/permitir do JSON da ação. Devolve dict limpo ou levanta ValueError."""
    out = {"negar": [], "permitir": [], "regras_negar": [], "regras_permitir": []}
    for campo in ("negar", "permitir"):
        lista = acao.get(campo, [])
        if not isinstance(lista, list) or len(lista) > MAX_REGRAS:
            raise ValueError("'%s' precisa ser uma lista de até %d regras" % (campo, MAX_REGRAS))
        for i, item in enumerate(lista):
            onde = "%s[%d]" % (campo, i)
            if isinstance(item, str):
                if not item.strip() or len(item) > MAX_TEXTO or RE_CONTROLE.search(item):
                    raise ValueError("%s: regra de permissão inválida" % onde)
                out[campo].append(item.strip())
            elif isinstance(item, dict):
                out["regras_" + campo].append(_regra(item, onde))
            else:
                raise ValueError("%s: precisa ser texto ou objeto" % onde)
    if len(json.dumps(out, ensure_ascii=False)) > MAX_CONF:
        raise ValueError("travas grandes demais")
    return out
