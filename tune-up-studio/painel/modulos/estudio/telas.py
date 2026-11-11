"""Abas Novo e Marca do módulo estudio. Python 3.9, só biblioteca padrão."""
import base64
import json
import os
import re
import struct
import zlib

ACOES = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), os.pardir, "acoes", "estudio.json")
RE_HEX = re.compile(r"^#([0-9A-Fa-f]{6})$")
TIPOS = {"texto_longo": "texto_longo", "escolha": "escolha"}


def amostra(cor, largura=96, altura=32):
    """data:image/png;base64 de um retângulo da cor (#RRGGBB), ou None."""
    m = RE_HEX.match(cor or "") if isinstance(cor, str) else None
    if not m:
        return None
    linha = b"\x00" + bytes.fromhex(m.group(1)) * largura

    def pedaco(tipo, corpo):
        return struct.pack(">I", len(corpo)) + tipo + corpo + struct.pack(">I", zlib.crc32(tipo + corpo))
    png = (b"\x89PNG\r\n\x1a\n" + pedaco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0))
           + pedaco(b"IDAT", zlib.compress(linha * altura)) + pedaco(b"IEND", b""))
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _ligada(config, chave):
    if isinstance(config, dict) and config.get(chave) is True:
        return True
    no = config
    for parte in chave.split("."):
        no = no.get(parte) if isinstance(no, dict) else None
    return no is True


def _acoes():
    try:
        with open(os.path.normpath(ACOES), encoding="utf-8") as f:
            return [a for a in json.load(f)["acoes"] if isinstance(a, dict)]
    except (OSError, ValueError, KeyError, TypeError):
        return []


def _campo(p):
    c = {"id": p["nome"], "rotulo": p.get("rotulo") or p["nome"], "tipo": TIPOS.get(p.get("tipo"), "texto"),
         "obrigatorio": bool(p.get("obrigatorio"))}
    if p.get("ajuda"):
        c["ajuda"] = p["ajuda"]
    if c["tipo"] == "escolha":
        c["opcoes"] = [{"valor": o, "rotulo": o} for o in p.get("opcoes") or []]
        c["valor"] = (p.get("opcoes") or [""])[0]
    return c


def aba_novo(ctx, aprovada):
    """Um formulário por ação do estúdio (vídeo com movimento só se o projeto ligou a chave dele)."""
    if not aprovada:
        return [{"tipo": "texto", "titulo": "Marca não aprovada",
                 "texto": "Antes de criar peças, confira e aprove a marca na aba Marca."}]
    blocos = []
    for a in _acoes():
        if a.get("so_com") and not _ligada(ctx.get("config"), a["so_com"]):
            continue
        blocos.append({"tipo": "formulario", "titulo": a.get("titulo") or a["id"], "descricao": a.get("descricao", ""),
                       "catalogo": a["id"], "botao": "Começar",
                       "campos": [_campo(p) for p in a.get("params") or [] if isinstance(p, dict) and p.get("nome")]})
    if not any(b["catalogo"] == "estudio.video-motion" for b in blocos):
        blocos.append({"tipo": "texto", "texto": "Vídeo com movimento: o projeto não ligou estudio.video_rede_local "
                       "no painel.json, então o vídeo sai pela reserva em slides."})
    return blocos


def aba_marca(m, sha, aprovada):
    """Campos do marca.json com fonte, amostra das cores, aprovar (com o sha mostrado), editar e redescobrir."""
    if m is None:
        return [{"tipo": "texto", "texto": "Ainda não há marca descoberta. Use Redescobrir a marca."}, _redescobrir()]
    campos = m[2]["campos"]
    curto = sha[:12]
    estado = "aprovada" if aprovada else "ainda não aprovada"
    linhas = [{"campo": k, "valor": str(v.get("valor")) if v.get("valor") is not None else "faltando",
               "fonte": str(v.get("fonte") or ""), "confianca": str(v.get("confianca") or ""),
               "travado": "sim" if v.get("travado") else "não"}
              for k, v in sorted(campos.items()) if isinstance(v, dict)]
    blocos = [{"tipo": "texto", "titulo": "Marca %s" % estado, "texto": "sha256 %s do marca.json." % curto},
              {"tipo": "tabela", "titulo": "Campos", "colunas": [
                  {"id": "campo", "rotulo": "Campo"}, {"id": "valor", "rotulo": "Valor"},
                  {"id": "fonte", "rotulo": "De onde veio"}, {"id": "confianca", "rotulo": "Confiança"},
                  {"id": "travado", "rotulo": "Travado"}], "linhas": linhas}]
    for k, v in sorted(campos.items()):
        uri = amostra(v.get("valor")) if k.startswith("cores.") and isinstance(v, dict) else None
        if uri:
            blocos.append({"tipo": "imagem", "titulo": k, "data_uri": uri, "alt": "Amostra de %s" % k,
                           "legenda": str(v.get("valor"))})
    if not aprovada:
        blocos.append({"tipo": "formulario", "titulo": "Aprovar a marca", "acao": "marca.aprovar", "botao": "Aprovar",
                       "campos": [], "dados_fixos": {"confirmar": True, "sha256": curto},
                       "confirmar": "Aprovar a marca com sha256 %s, como está na tabela?" % curto})
    blocos.append({"tipo": "formulario", "titulo": "Corrigir um campo", "acao": "marca.editar", "botao": "Salvar",
                   "campos": [{"id": "campo", "rotulo": "Campo", "tipo": "escolha", "obrigatorio": True,
                               "valor": sorted(campos)[0] if campos else "",
                               "opcoes": [{"valor": k, "rotulo": k} for k in sorted(campos)]},
                              {"id": "valor", "rotulo": "Valor novo", "tipo": "texto", "obrigatorio": True}]})
    return blocos + [_redescobrir()]


def _redescobrir():
    return {"tipo": "formulario", "titulo": "Redescobrir a marca", "acao": "marca.redescobrir", "botao": "Redescobrir",
            "campos": [], "dados_fixos": {"confirmar": True},
            "confirmar": "Ler o projeto de novo? Campos travados ficam como estão; a aprovação cai."}
