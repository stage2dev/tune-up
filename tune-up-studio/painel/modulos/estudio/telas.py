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


ROTULOS = {"nome": "Nome", "descricao": "Descrição", "cores.bg": "Cor de fundo", "cores.surface": "Cor dos cartões",
           "cores.primary": "Cor principal", "cores.text": "Cor do texto", "cores.accent": "Cor de destaque",
           "fontes.heading": "Fonte dos títulos", "fontes.body": "Fonte do texto", "logo": "Logo"}
CONFIANCA = {"alta": "alta", "media": "média", "baixa": "baixa"}


def aba_novo(ctx, aprovada, pronto=True):
    """Um formulário por ação do estúdio (vídeo com movimento só se o projeto ligou a chave dele)."""
    if not pronto:
        return [{"tipo": "texto", "titulo": "Passo 1 de 3: preparar o estúdio",
                 "texto": "Antes de criar peças, prepare o estúdio. É só uma vez.",
                 "ir_para": {"aba": "ambiente", "rotulo": "Ir para 1. Ambiente"}}]
    if not aprovada:
        return [{"tipo": "texto", "titulo": "Passo 2 de 3: aprovar a marca",
                 "texto": "Antes de criar peças, confira as cores e as fontes da sua marca e aprove.",
                 "ir_para": {"aba": "marca", "rotulo": "Ir para 2. Marca"}}]
    blocos = [{"tipo": "texto", "titulo": "Passo 3 de 3: pedir uma peça",
               "texto": "Escreva o que a peça precisa dizer e clique em Começar. Quando ficar pronta, ela aparece "
                        "na aba Aprovação."}]
    for a in _acoes():
        if a.get("so_com") and not _ligada(ctx.get("config"), a["so_com"]):
            continue
        blocos.append({"tipo": "formulario", "titulo": a.get("titulo") or a["id"], "descricao": a.get("descricao", ""),
                       "catalogo": a["id"], "botao": "Começar",
                       "campos": [_campo(p) for p in a.get("params") or [] if isinstance(p, dict) and p.get("nome")]})
    if not any(b.get("catalogo") == "estudio.video-motion" for b in blocos):
        blocos.append({"tipo": "texto", "texto": "Vídeo com movimento está desligado neste projeto: o vídeo sai em "
                       "slides, sem movimento dentro das cenas."})
    return blocos


def aba_marca(m, sha, aprovada):
    """Campos do marca.json com fonte, amostra das cores, aprovar (com o sha mostrado), editar e redescobrir."""
    if m is None:
        return [{"tipo": "texto", "texto": "Ainda não há marca descoberta. Use Redescobrir a marca."}, _redescobrir()]
    campos = m[2]["campos"]
    curto = sha[:12]
    estado = "aprovada" if aprovada else "ainda não aprovada"
    linhas = [{"campo": ROTULOS.get(k, k), "valor": str(v.get("valor")) if v.get("valor") is not None else "faltando",
               "fonte": str(v.get("fonte") or ""),
               "confianca": CONFIANCA.get(v.get("confianca"), str(v.get("confianca") or "")),
               "travado": "sim" if v.get("travado") else "não"}
              for k, v in sorted(campos.items()) if isinstance(v, dict)]
    blocos = [{"tipo": "texto", "titulo": "Marca %s" % estado,
               "texto": "Confira os campos abaixo." if aprovada else "Passo 2 de 3: confira os campos abaixo e aprove."}
              | ({"ir_para": {"aba": "novo", "rotulo": "Ir para 3. Novo"}} if aprovada else {}),
              {"tipo": "tabela", "titulo": "Campos", "colunas": [
                  {"id": "campo", "rotulo": "Campo"}, {"id": "valor", "rotulo": "Valor"},
                  {"id": "fonte", "rotulo": "De onde veio", "secundaria": True},
                  {"id": "confianca", "rotulo": "Confiança", "secundaria": True},
                  {"id": "travado", "rotulo": "Travado"}], "linhas": linhas}]
    for k, v in sorted(campos.items()):
        uri = amostra(v.get("valor")) if k.startswith("cores.") and isinstance(v, dict) else None
        if uri:
            blocos.append({"tipo": "imagem", "titulo": ROTULOS.get(k, k), "data_uri": uri, "alt": "Amostra de %s" % ROTULOS.get(k, k),
                           "legenda": str(v.get("valor"))})
    if not aprovada:
        blocos.append({"tipo": "formulario", "titulo": "Aprovar a marca", "acao": "marca.aprovar", "botao": "Aprovar",
                       "campos": [], "dados_fixos": {"confirmar": True, "sha256": curto},
                       "confirmar": "Aprovar a marca como está na tabela?"})
    blocos.append({"tipo": "formulario", "titulo": "Corrigir um campo", "acao": "marca.editar", "botao": "Salvar",
                   "campos": [{"id": "campo", "rotulo": "Campo", "tipo": "escolha", "obrigatorio": True,
                               "valor": sorted(campos)[0] if campos else "",
                               "opcoes": [{"valor": k, "rotulo": ROTULOS.get(k, k)} for k in sorted(campos)]},
                              {"id": "valor", "rotulo": "Valor novo", "tipo": "texto", "obrigatorio": True}]})
    return blocos + [_redescobrir()]


def _redescobrir():
    return {"tipo": "formulario", "titulo": "Redescobrir a marca", "acao": "marca.redescobrir", "botao": "Redescobrir",
            "campos": [], "dados_fixos": {"confirmar": True},
            "confirmar": "Ler o projeto de novo? Campos travados ficam como estão; a aprovação cai."}
