"""Catálogo de ações do painel (acoes/*.json) e validação dos parâmetros.

Parte do lançador, separada só para caber no limite de linhas. O cliente nunca
manda comando: aqui a ação é conferida, cada valor é validado e o prompt é
montado a partir do modelo do JSON. Python 3.9, só biblioteca padrão.
"""
import glob
import json
import os
import re

import teto
from travas import validar_travas

RE_ID_ACAO = re.compile(r"^[a-z0-9][a-z0-9.\-]{1,60}$")
RE_NOME_PARAM = re.compile(r"^[a-z_][a-z0-9_]{0,30}$")
RE_FASE = re.compile(r"^\d{1,4}$")
RE_PARTE = re.compile(r"^[A-Z0-9][A-Z0-9]{0,2}[a-z]?(?:-[A-Za-z0-9]+)*$")
# Controle C0/C1, separadores de linha e marcas invisíveis de direção.
RE_CONTROLE = re.compile("[\x00-\x1f\x7f-\x9f​-‏  ‪-‮⁦-⁩﻿]")
RE_CAMPO = re.compile(r"\{([a-z_][a-z0-9_]{0,30})\}")

RE_GRUPO = re.compile(r"^[a-z0-9_-]{1,40}$")
RISCOS = ("leitura", "rascunho", "codigo", "credito")
TIPOS = ("fase", "parte", "texto", "escolha", "texto_longo")
TEXTO_MAX, TEXTO_PADRAO = 2000, 500
TEXTO_LONGO_MAX = 6000  # texto com "linhas": pedido de chat, resposta numa conversa
ARQUIVO_MAX = 4000  # tipo texto_longo: vai para <trabalho>/entrada.md; o prompt leva só o caminho
TRABALHO = "trabalho"  # {trabalho} no prompt e nas travas = pasta de trabalho da execução (trabalho.py)
RE_MODELO = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,60}$")  # apelido do CLI (fable, opus, sonnet...) ou nome inteiro
ESFORCOS = ("low", "medium", "high", "xhigh", "max")
GRUPO_CHAT = "chat"  # cada ação deste grupo é um nível do chat da tela inicial
LIMITE_ACOES = 256 * 1024


class ErroAcao(Exception):
    """Erro com texto simples para a tela e o código HTTP certo."""

    def __init__(self, mensagem, codigo=400, execucao_id=None):
        Exception.__init__(self, mensagem)
        self.mensagem, self.codigo, self.execucao_id = mensagem, codigo, execucao_id


def _validar_param(p):
    if not isinstance(p, dict) or not RE_NOME_PARAM.match(str(p.get("nome", ""))):
        raise ValueError("parâmetro sem nome válido")
    if p["nome"] == TRABALHO:
        raise ValueError("parâmetro não pode se chamar %s (marcador reservado)" % TRABALHO)
    if p.get("tipo") not in TIPOS:
        raise ValueError("parâmetro %s com tipo inválido" % p["nome"])
    out = {"nome": p["nome"], "rotulo": str(p.get("rotulo") or p["nome"])[:80], "tipo": p["tipo"],
           "obrigatorio": bool(p.get("obrigatorio", True))}
    if p["tipo"] == "escolha":
        opcoes = p.get("opcoes")
        if not isinstance(opcoes, list) or not opcoes or not all(isinstance(o, str) and o for o in opcoes) \
                or any(RE_CONTROLE.search(o) or o.startswith("-") for o in opcoes):
            raise ValueError("parâmetro %s: opções inválidas" % p["nome"])
        out["opcoes"] = list(opcoes)
    if p["tipo"] == "texto":
        linhas = p.get("linhas") is True
        mx = p.get("max")
        ok = isinstance(mx, int) and not isinstance(mx, bool) and 1 <= mx <= (TEXTO_LONGO_MAX if linhas else TEXTO_MAX)
        out["max"] = mx if ok else TEXTO_PADRAO
        if linhas:
            out["linhas"] = True
    if p["tipo"] == "texto_longo":
        mx = p.get("max")
        out["max"] = mx if isinstance(mx, int) and not isinstance(mx, bool) and 1 <= mx <= ARQUIVO_MAX else ARQUIVO_MAX
        out["linhas"] = True
    if isinstance(p.get("ajuda"), str) and p["ajuda"]:
        out["ajuda"] = p["ajuda"][:300]
    return out


def _modelos(a):
    """`modelos` do JSON (texto ou lista em ordem de preferência) -> lista limpa.

    A chave é no plural porque "modelo" já é o nome antigo do modelo do prompt.
    """
    bruto = a.get("modelos")
    if bruto is None:
        return []
    lista = [bruto] if isinstance(bruto, str) else bruto
    if not isinstance(lista, list) or not 1 <= len(lista) <= 4 or len(set(map(str, lista))) != len(lista) \
            or not all(isinstance(m, str) and RE_MODELO.match(m) for m in lista):
        raise ValueError("ação %s: modelos inválido (apelido do CLI ou lista de até 4, sem repetir)" % a["id"])
    return list(lista)


def validar_acao(a):
    """Confere uma ação do JSON. Devolve a ação limpa ou levanta ValueError."""
    if not isinstance(a, dict) or not RE_ID_ACAO.match(str(a.get("id", ""))):
        raise ValueError("ação sem id válido")
    grupo = a.get("grupo", a.get("area"))  # "area" é o nome antigo
    if not isinstance(grupo, str) or not RE_GRUPO.match(grupo) or a.get("risco") not in RISCOS:
        raise ValueError("ação %s: grupo ou risco inválido" % a["id"])
    try:
        trv = validar_travas(a)
    except ValueError as e:
        raise ValueError("ação %s: travas: %s" % (a["id"], e))
    prompt = a.get("prompt") or a.get("modelo") or a.get("prompt_modelo")
    if not isinstance(prompt, str) or not prompt.strip() or prompt.lstrip().startswith("-") \
            or RE_CONTROLE.search(prompt.replace("\n", " ").replace("\t", " ")):
        raise ValueError("ação %s: prompt vazio, começando com '-' ou com caractere de controle" % a["id"])
    params = [_validar_param(p) for p in (a.get("params") or [])]
    nomes = [p["nome"] for p in params]
    if len(set(nomes)) != len(nomes):
        raise ValueError("ação %s: parâmetro repetido" % a["id"])
    nome_sessao = a.get("nome_sessao") if isinstance(a.get("nome_sessao"), str) else None
    for texto, aceitos in ((prompt, nomes + [TRABALHO]), (nome_sessao or "", nomes)):
        for campo in RE_CAMPO.findall(texto):
            if campo not in aceitos:
                raise ValueError("ação %s: {%s} no modelo sem parâmetro" % (a["id"], campo))
    tipos = [p["tipo"] for p in params]
    if tipos.count("texto_longo") > 1:
        raise ValueError("ação %s: no máximo um parâmetro texto_longo" % a["id"])
    if "parte" in tipos and "fase" not in tipos:
        raise ValueError("ação %s: parâmetro parte exige um parâmetro fase" % a["id"])
    if grupo == GRUPO_CHAT and (nomes != ["pedido"] or tipos != ["texto"] or not params[0]["obrigatorio"]):
        raise ValueError("ação %s: nível do chat precisa de um único parâmetro de texto obrigatório chamado pedido"
                         % a["id"])
    esforco = a.get("esforco")
    if esforco is not None and esforco not in ESFORCOS:
        raise ValueError("ação %s: esforco precisa ser um de %s" % (a["id"], ", ".join(ESFORCOS)))
    tetos = teto.validar(a)
    equipe = a.get("equipe") if isinstance(a.get("equipe"), str) else ""
    if RE_CONTROLE.search(equipe):
        raise ValueError("ação %s: equipe com caractere de controle" % a["id"])
    return {"id": a["id"], "grupo": grupo, "area": grupo, "titulo": str(a.get("titulo") or a["id"])[:80],
            "descricao": str(a.get("descricao") or "")[:500], "risco": a["risco"],
            # código e crédito sempre pedem confirmação, diga o JSON o que disser
            "confirmar": bool(a.get("confirmar")) or a["risco"] in ("codigo", "credito"),
            "params": params, "modelos": _modelos(a), "esforco": esforco, "equipe": equipe.strip()[:60],
            "_prompt": prompt.strip(), "_nome": nome_sessao, "_travas": trv, "_substitui": a.get("substitui") is True,
            **tetos}


def _arquivos(pastas):
    for i, pasta in enumerate([pastas] if isinstance(pastas, str) else pastas):
        if pasta and os.path.isdir(pasta):
            for arq in sorted(glob.glob(os.path.join(pasta, "*.json"))):
                yield i, pasta, arq


def carregar_catalogo(pastas):
    """Ações de cada pasta (núcleo primeiro, depois o pacote). Arquivo ou ação ruim vira aviso.

    Id repetido é ignorado, menos num caso: ação do pacote com "substitui": true troca a do
    núcleo de mesmo id, no mesmo lugar da lista (ex.: um nível do chat com as travas do projeto).
    """
    acoes, avisos, vistos = [], [], {}
    for origem, pasta, arq in _arquivos(pastas):
        nome = os.path.basename(arq)
        try:
            real = os.path.realpath(arq)
            if os.path.islink(arq) or not real.startswith(os.path.realpath(pasta).rstrip(os.sep) + os.sep) \
                    or os.path.getsize(arq) > LIMITE_ACOES:
                raise ValueError("atalho ou grande demais")
            with open(arq, encoding="utf-8") as f:
                dado = json.load(f)
        except (OSError, ValueError) as e:
            avisos.append("%s ilegível: %s" % (nome, str(e)[:120]))
            continue
        lista = dado.get("acoes") if isinstance(dado, dict) else dado
        for a in lista if isinstance(lista, list) else []:
            try:
                limpa = validar_acao(a)
            except ValueError as e:
                avisos.append("%s: %s" % (nome, e))
                continue
            if limpa["id"] in vistos:
                if limpa["_substitui"] and origem > 0 and vistos[limpa["id"]] == 0:
                    acoes[[x["id"] for x in acoes].index(limpa["id"])] = limpa
                    vistos[limpa["id"]] = origem
                else:
                    avisos.append("%s: ação %s repetida; ignorei" % (nome, limpa["id"]))
                continue
            vistos[limpa["id"]] = origem
            acoes.append(limpa)
    return acoes, avisos


def publica(acao):
    """A ação como sai em /api/acoes: sem o modelo do prompt nem do nome."""
    return {k: v for k, v in acao.items() if not k.startswith("_")}


def _erro_valor(p, v):
    """Texto do erro do valor `v` (já sem espaços nas pontas) ou None se está bom."""
    rot = p["rotulo"]
    if p.get("linhas") and RE_CONTROLE.search(v.replace("\n", "")):
        return "O campo \"%s\" tem um caractere que não pode." % rot
    if not p.get("linhas") and RE_CONTROLE.search(v):
        return "O campo \"%s\" tem um caractere que não pode (como quebra de linha)." % rot
    if v.startswith("-") and p["tipo"] != "texto_longo":  # texto_longo vai para arquivo, nunca para o argv
        return "O campo \"%s\" não pode começar com \"-\"." % rot
    if p["tipo"] in ("texto", "texto_longo") and len(v) > p.get("max", TEXTO_PADRAO):
        return "O campo \"%s\" passou de %d letras." % (rot, p.get("max", TEXTO_PADRAO))
    if p["tipo"] == "escolha" and v not in p["opcoes"]:
        return "Escolha uma das opções do campo \"%s\"." % rot
    if p["tipo"] == "fase" and not RE_FASE.match(v):
        return "Fase inválida."
    if p["tipo"] == "parte" and not RE_PARTE.match(v):
        return "Parte inválida."
    return None


def arrumar_linhas(texto):
    """Quebra de linha de qualquer sistema vira \\n; tab vira espaço; 3+ linhas vazias viram uma."""
    texto = texto.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ")
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def texto_livre(valor, rotulo="mensagem", maximo=TEXTO_LONGO_MAX):
    """Texto digitado fora de uma ação (resposta numa conversa). Devolve limpo ou levanta ErroAcao."""
    if not isinstance(valor, str) or not valor.strip():
        raise ErroAcao("Escreva a %s." % rotulo)
    p = {"rotulo": rotulo, "tipo": "texto", "max": maximo, "linhas": True}
    v = arrumar_linhas(valor)
    erro = _erro_valor(p, v)
    if erro:
        raise ErroAcao(erro)
    return v


def validar_params(acao, params, estado):
    """Devolve {nome: valor} já limpo. Levanta ErroAcao(400) com texto simples."""
    params = {} if params is None else params
    if not isinstance(params, dict):
        raise ErroAcao("Os campos vieram num formato errado.")
    conhecidos = {p["nome"] for p in acao["params"]}
    sobra = [k for k in params if k not in conhecidos]
    if sobra:
        raise ErroAcao("Campo desconhecido: %s." % str(sobra[0])[:40])
    valores = {}
    for p in acao["params"]:
        v = params.get(p["nome"])
        if v is None or (isinstance(v, str) and not v.strip()):
            if p["obrigatorio"]:
                raise ErroAcao("Preencha o campo \"%s\"." % p["rotulo"])
            valores[p["nome"]] = ""
            continue
        if not isinstance(v, (str, int)) or isinstance(v, bool):
            raise ErroAcao("O campo \"%s\" precisa ser um texto." % p["rotulo"])
        v = str(v).strip()
        if p.get("linhas"):
            v = arrumar_linhas(v)
        erro = _erro_valor(p, v)
        if erro:
            raise ErroAcao(erro)
        valores[p["nome"]] = v
    _conferir_fase_parte(acao, valores, estado)
    return valores


def _conferir_fase_parte(acao, valores, estado):
    """A fase existe no estado atual e a Parte existe nela e não está fechada."""
    nome_fase = next((p["nome"] for p in acao["params"] if p["tipo"] == "fase"), None)
    if not nome_fase or not valores.get(nome_fase):
        return
    numero = valores[nome_fase]
    fase = next((f for f in (estado or {}).get("fases") or []
                 if isinstance(f, dict) and str(f.get("numero")) == numero), None)
    if fase is None:
        raise ErroAcao("Não achei a fase %s no plano." % numero)
    for p in acao["params"]:
        if p["tipo"] != "parte" or not valores.get(p["nome"]):
            continue
        parte = next((x for x in fase.get("partes") or [] if x.get("id") == valores[p["nome"]]), None)
        if parte is None:
            raise ErroAcao("A fase %s não tem a Parte %s." % (numero, valores[p["nome"]]))
        if parte.get("status") == "fechada":
            raise ErroAcao("A Parte %s da fase %s já está fechada." % (parte["id"], numero))


def montar(modelo, valores):
    """Troca {campo} pelo valor numa passada só (valor com chaves não é expandido de novo)."""
    texto = RE_CAMPO.sub(lambda m: valores.get(m.group(1), ""), modelo)
    return re.sub(r"[ \t]{2,}", " ", texto).strip()


def nome_da_sessao(acao, valores):
    """Nome do `claude --bg -n`. Para Parte fica 'Fase N Parte X' (o leitor liga a sessão à Parte)."""
    nome = re.sub(r"\s+", " ", montar(acao["_nome"], valores) if acao.get("_nome") else acao["titulo"]).strip()
    if len(nome) > 60:
        nome = nome[:59].rstrip() + "…"
    return nome if nome and not nome.startswith("-") else "painel " + acao["id"]
