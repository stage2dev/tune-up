"""Pasta de trabalho de uma execução: <dados>/trabalhos/<id>/, criada pelo servidor.

Só existe para ação que cita `{trabalho}` (no prompt ou nas travas) ou tem parâmetro
`texto_longo`. Dentro: `entrada.json` (ação e valores) e `entrada.md` (o texto longo; o
prompt recebe o caminho, assim o argv nunca leva quebra de linha). O marcador `{trabalho}`
vira o caminho real (realpath): no prompt como está; em regra de permissão em texto com `//`
na frente (caminho absoluto do Claude Code) e curinga escapado; em regex do gancho com
re.escape. Python 3.9, só biblioteca padrão.
"""
import json
import os
import re
import secrets
import shutil

from catalogo import RE_CONTROLE, TRABALHO, ErroAcao, montar

MARCA = "{" + TRABALHO + "}"
ARQ_ENTRADA, ARQ_TEXTO = "entrada.json", "entrada.md"
RE_CURINGA = re.compile(r"([*?\[\]])")
_SINAL = "\x00trabalho\x00"  # valor de parâmetro nunca tem \x00 (RE_CONTROLE): montar não mexe no caminho


def _longos(acao):
    return [p["nome"] for p in acao["params"] if p["tipo"] == "texto_longo"]


def usa(acao):
    trv = json.dumps(acao.get("_travas") or {}, ensure_ascii=False)
    return MARCA in acao["_prompt"] or MARCA in trv or bool(_longos(acao))


def nova_pasta(dados_dir, acao):
    """Caminho real da pasta nova (ainda não criada) ou None se a ação não usa pasta de trabalho."""
    if not usa(acao):
        return None
    pasta = os.path.join(os.path.realpath(dados_dir), "trabalhos", secrets.token_hex(6))
    if RE_CONTROLE.search(pasta):
        raise ErroAcao("A pasta do painel tem um caractere que não pode.", 500)
    return pasta


def montar_prompt(acao, valores, pasta):
    """Prompt com `{trabalho}` = pasta e cada texto_longo = caminho do entrada.md."""
    if pasta is None:
        return montar(acao["_prompt"], valores)
    trocas = {TRABALHO: pasta}
    trocas.update({n: os.path.join(pasta, ARQ_TEXTO) for n in _longos(acao)})
    sinais = {k: _SINAL + k + _SINAL for k in trocas}
    texto = montar(acao["_prompt"], dict(valores, **sinais))
    for k, v in trocas.items():
        texto = texto.replace(sinais[k], v)
    return texto


def caminho_de_regra(pasta):
    """`//` + caminho em barras (C:\\x -> //c/x), com curinga de glob escapado."""
    p = pasta.replace("\\", "/")
    if re.match(r"^[A-Za-z]:", p):
        p = "/" + p[0].lower() + p[2:]
    return "/" + RE_CURINGA.sub(r"\\\1", p)


def resolver_travas(acao, pasta):
    """Cópia da ação com `{trabalho}` trocado nas regras de negar/permitir (texto e regex do gancho)."""
    trv = acao.get("_travas") or {}
    regra_txt, regra_re = caminho_de_regra(pasta), re.escape(pasta)
    novo = dict(trv)
    for campo in ("negar", "permitir"):
        novo[campo] = [r.replace(MARCA, regra_txt) for r in trv.get(campo) or []]
    for campo in ("regras_negar", "regras_permitir"):
        novo[campo] = [dict(r, entrada=r["entrada"].replace(MARCA, regra_re)) if "entrada" in r else r
                       for r in trv.get(campo) or []]
    return dict(acao, _travas=novo)


def criar(pasta, acao, valores):
    """Cria a pasta (0700) com entrada.json e, se houver, entrada.md. pasta None = nada."""
    if pasta is None:
        return
    os.makedirs(os.path.dirname(pasta), mode=0o700, exist_ok=True)
    os.mkdir(pasta, 0o700)  # id novo: se já existir, falha em vez de misturar
    longos = _longos(acao)
    if longos:
        with open(os.path.join(pasta, ARQ_TEXTO), "w", encoding="utf-8", newline="\n") as f:
            f.write(valores.get(longos[0]) or "")
    dado = {"acao": acao["id"], "trabalho": os.path.basename(pasta),
            "params": {k: (ARQ_TEXTO if k in longos else v) for k, v in valores.items()}}
    with open(os.path.join(pasta, ARQ_ENTRADA), "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False, indent=1)


def apagar(pasta):
    if pasta:
        shutil.rmtree(pasta, ignore_errors=True)
