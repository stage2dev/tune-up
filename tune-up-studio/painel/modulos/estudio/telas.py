"""Abas Novo e Marca do módulo estudio. Python 3.9, só biblioteca padrão."""
import json
import os
import re

import marca_acoes as ma

ACOES = os.path.join(os.path.dirname(os.path.dirname(os.path.realpath(__file__))), os.pardir, "acoes", "estudio.json")
RE_HEX = re.compile(r"^#([0-9A-Fa-f]{6})$")
TIPOS = {"texto_longo": "texto_longo", "escolha": "escolha"}


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


CONFIANCA = {"alta": "alta", "media": "média", "baixa": "baixa", "faltando": "não achamos"}
IMAGEM = (".png", ".jpg", ".jpeg", ".webp")  # o que a rota de mídia mostra (SVG nunca)
CONFIRMAR = "Está certo, usar esta marca"


def aba_novo(ctx, aprovada, pronto=True):
    """Um formulário por ação do estúdio (vídeo com movimento só se o projeto ligou a chave dele)."""
    if not pronto:
        return [{"tipo": "texto", "titulo": "Passo 1 de 3: preparar o estúdio",
                 "texto": "Antes de criar peças, prepare o estúdio. É só uma vez.",
                 "ir_para": {"aba": "ambiente", "rotulo": "Ir para 1. Ambiente"}}]
    if not aprovada:
        return [{"tipo": "texto", "titulo": "Passo 2 de 3: aprovar a marca",
                 "texto": "Antes de criar peças, confira a sua marca e clique em %s. Se você mudou algo na marca "
                          "(cor, letra, logo, foto ou texto), confirme de novo: as peças só usam a marca "
                          "confirmada." % CONFIRMAR,
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


def _valor(campos, k):
    v = campos.get(k)
    return v.get("valor") if isinstance(v, dict) else None


def _cor(campos, k):
    h = _valor(campos, k)
    return h.lower() if isinstance(h, str) and RE_HEX.match(h) else ma.NEUTRA[k]


def _logo(obj, campos):
    """Blocos da logo: envio de 1 arquivo (com a logo atual, se a tela consegue mostrar) e Não tenho logo."""
    copia = obj.get("logo_copia") if isinstance(obj.get("logo_copia"), str) else ""
    logo = _valor(campos, "logo")
    do_dono = (campos.get("logo") or {}).get("fonte") == "dono"
    if copia.lower().endswith(IMAGEM):
        texto = "Esta é a logo que você enviou." if do_dono else "Achamos esta logo no seu projeto. Se não for a certa, envie outra."
    elif copia:
        texto = ("Achamos uma logo em SVG no seu projeto (%s). Ela vai nas peças, mas esta tela não mostra SVG. "
                 "Se não for a certa, envie outra." % logo)
    elif do_dono and logo is None:
        texto = "Você disse que o negócio não tem logo: as peças usam o nome no lugar. Pode enviar uma quando quiser."
    else:
        texto = "Não achamos logo no seu projeto. Envie uma, ou diga que não tem."
    envio = {"tipo": "envio", "id": "marca-logo", "titulo": "Logo", "descricao": texto + " PNG, JPG ou WebP, até 5 MB.",
             "destino": "logo", "variante": "um", "alt": "Logo do negócio", "max_bytes": 5000000,
             "botao": "Enviar outra logo" if copia else "Enviar logo"}
    if copia.lower().endswith(IMAGEM):
        envio["atual"] = "estudio/marca/" + copia
    blocos = [envio]
    if not (do_dono and logo is None):
        blocos.append({"tipo": "formulario", "id": "marca-sem-logo", "acao": "marca.sem_logo", "botao": "Não tenho logo",
                       "campos": [], "dados_fixos": {"confirmar": True},
                       "descricao": "Sem logo, as peças mostram o nome do negócio no lugar."})
    return blocos, envio.get("atual"), copia.lower().endswith(ma.CORES_DA_LOGO)


def _fotos(obj):
    itens = [{"arquivo": "estudio/marca/" + f["arquivo"], "rotulo": "Foto principal" if i == 0 else "Foto %d" % (i + 1)}
             for i, f in enumerate(f for f in obj.get("fotos") or [] if isinstance(f, dict)
                                   and isinstance(f.get("arquivo"), str) and f["arquivo"].startswith("fotos/"))]
    return {"tipo": "envio", "id": "marca-fotos", "titulo": "Fotos do negócio",
            "descricao": "Fachada, produto, equipe. As peças usam estas fotos em vez de imagem inventada. "
                         "Até %d fotos; a primeira é a principal." % ma.MAX_FOTOS,
            "destino": "fotos", "variante": "grade", "itens": itens, "max_bytes": 8 * 1024 * 1024,
            "botao": "Adicionar foto", "vazio": "Nenhuma foto ainda.",
            "remover": {"acao": "marca.remover_foto", "confirmar": "Tirar esta foto da marca?"}}


def _letras(obj, campos, nome):
    atual = (_valor(campos, "fontes.heading"), _valor(campos, "fontes.body"))
    opcoes = [{"valor": k, "rotulo": r, "fontes": {"titulo": t, "texto": x}} for k, (r, t, x) in ma.PARES.items()]
    projeto = ma.par_do_projeto(obj)
    if projeto:
        opcoes.append({"valor": "projeto", "rotulo": "A do seu projeto", "detalhe": projeto[0],
                       "fontes": {"titulo": projeto[0], "texto": projeto[1]}})
    valor = next((o["valor"] for o in opcoes if (o["fontes"]["titulo"], o["fontes"]["texto"]) == atual), "")
    return {"tipo": "opcoes", "id": "marca-letras", "titulo": "Letras", "acao": "marca.letras", "campo": "letras",
            "modo": "um", "valor": valor, "opcoes": opcoes,
            "descricao": "Escolha o jeito das letras. Cada opção já aparece escrita com elas.",
            "exemplo": {"titulo": nome, "texto": "Um exemplo de frase das suas peças."}}


def _negocio(obj, campos):
    tom = obj.get("tom", {}).get("valor") if isinstance(obj.get("tom"), dict) else None
    tom = tom if isinstance(tom, list) else []
    blocos = [{"tipo": "formulario", "id": "marca-" + k, "acao": "marca.editar", "botao": "Salvar",
               "dados_fixos": {"campo": k}, "campos": [{"id": "valor", "rotulo": rotulo, "tipo": "texto",
                                                        "obrigatorio": True, "valor": str(_valor(campos, k) or ""),
                                                        "ajuda": ajuda}]}
              for k, rotulo, ajuda in (("nome", "Nome", "Como o negócio aparece nas peças."),
                                       ("descricao", "O que vocês fazem?",
                                        "Uma frase curta, do jeito que você contaria a um cliente."))]
    blocos[0]["titulo"] = "O negócio em poucas palavras"
    blocos.append({"tipo": "opcoes", "id": "marca-tom", "titulo": "Jeito de falar", "acao": "marca.tom", "campo": "tom",
                   "modo": "varios", "descricao": "Marque como as peças devem falar com o cliente.",
                   "opcoes": [{"valor": k, "rotulo": r, "ligado": k in tom} for k, r in ma.TONS]})
    return blocos


def _origem(campos):
    """Linhas da tabela recolhida: de onde veio cada dado."""
    linhas = []
    for k in [c for c, _, _ in ma.CORES] + ["nome", "descricao", "fontes.heading", "fontes.body", "logo"]:
        v = campos.get(k) if isinstance(campos.get(k), dict) else {}
        fonte = str(v.get("fonte") or "")
        linhas.append({"campo": ma.ROTULOS.get(k, k),
                       "valor": str(v["valor"]) if v.get("valor") is not None else "não achamos",
                       "fonte": "você mudou aqui" if fonte == "dono" else fonte or "-",
                       "confianca": CONFIANCA.get(v.get("confianca"), str(v.get("confianca") or "")),
                       "travado": "sim" if v.get("travado") else "não"})
    return {"tipo": "tabela", "titulo": "De onde veio cada dado", "recolhido": True, "linhas": linhas, "colunas": [
        {"id": "campo", "rotulo": "Dado"}, {"id": "valor", "rotulo": "Valor"},
        {"id": "fonte", "rotulo": "De onde veio"}, {"id": "confianca", "rotulo": "Certeza", "secundaria": True},
        {"id": "travado", "rotulo": "Fica igual se procurar de novo", "secundaria": True}]}


def aba_marca(m, sha, aprovada):
    """Logo, fotos, cores, letras, o negócio, prévia, um botão para confirmar (o sha256 vai escondido nele)."""
    if m is None:
        return [{"tipo": "texto", "titulo": "Passo 2 de 3: a cara do seu negócio",
                 "texto": "Ainda não procuramos a marca no seu projeto. Clique em Procurar de novo no meu projeto."},
                _redescobrir()]
    obj = m[2]
    campos = obj["campos"]
    nome = str(_valor(campos, "nome") or "Seu negócio")
    topo = {"tipo": "texto", "titulo": "Passo 2 de 3: como é a cara do seu negócio?",
            "texto": "Já preenchemos o que achamos no seu projeto. Troque o que estiver errado. Tudo o que você mexer "
                     "aparece na hora no exemplo em Como vai ficar."}
    logo, atual, le_cores = _logo(obj, campos)
    cores = {"tipo": "cores", "id": "marca-cores", "titulo": "Cores", "descricao": "Toque numa cor para trocar.",
             "acao": "marca.editar", "itens": [{"chave": k, "rotulo": r, "uso": u, "valor": _cor(campos, k)}
                                               for k, r, u in ma.CORES],
             "contraste": [{"a": "cores.text", "b": "cores.bg",
                            "aviso": "O texto fica difícil de ler em cima deste fundo. Escolha uma cor de texto mais "
                                     "escura ou um fundo mais claro."}]}
    if le_cores:
        cores["botao"] = {"rotulo": "Pegar as cores da logo", "acao": "marca.cores_da_logo", "dados": {}}
    previa = {"tipo": "previa", "titulo": "Como vai ficar", "nome": nome,
              "cores": {"fundo": _cor(campos, "cores.bg"), "texto": _cor(campos, "cores.text"),
                        "principal": _cor(campos, "cores.primary"), "destaque": _cor(campos, "cores.accent"),
                        "superficie": _cor(campos, "cores.surface")},
              "fontes": {"titulo": str(_valor(campos, "fontes.heading") or ""), "texto": str(_valor(campos, "fontes.body") or "")},
              "campos": {"fundo": "cores.bg", "texto": "cores.text", "principal": "cores.primary",
                         "destaque": "cores.accent", "superficie": "cores.surface", "letras": "letras"},
              "textos": {"chamada": str(_valor(campos, "descricao") or nome)[:80], "frase": "Um exemplo de frase das suas peças.",
                         "botao": "Fale com a gente"},
              "legenda": "Exemplo de post com a sua marca. As peças de verdade seguem estas cores, letras e fotos."}
    if atual:
        previa["logo"] = atual
    if aprovada:
        fim = {"tipo": "texto", "titulo": "Marca confirmada",
               "texto": "As peças usam esta marca. Se você mudar qualquer coisa aqui (cor, letra, logo, foto ou texto), "
                        "pedimos sua confirmação de novo antes de criar peças.",
               "ir_para": {"aba": "novo", "rotulo": "Ir para 3. Novo"}}
    else:  # o sha256 curto vai escondido: a marca trocada depois que a tela abriu não é confirmada às cegas
        fim = {"tipo": "formulario", "id": "marca-confirmar", "titulo": "Tudo certo?", "acao": "marca.aprovar",
               "botao": CONFIRMAR, "campos": [], "dados_fixos": {"confirmar": True, "sha256": sha[:12]},
               "descricao": "Você pode voltar aqui e mudar quando quiser. Se mudar, pedimos sua confirmação de novo "
                            "antes de criar peças."}
    return ([topo] + logo + [_fotos(obj), cores, _letras(obj, campos, nome)] + _negocio(obj, campos)
            + [previa, fim, _redescobrir(), _origem(campos)])


def _redescobrir():
    return {"tipo": "formulario", "id": "marca-procurar", "acao": "marca.redescobrir",
            "botao": "Procurar de novo no meu projeto", "campos": [], "dados_fixos": {"confirmar": True},
            "confirmar": "Ler o projeto de novo? O que você mudou aqui fica como está; a confirmação da marca cai."}
