"""Pasta de trabalho de uma execução: <dados>/trabalhos/<id>/, criada pelo servidor.

Só existe para ação que cita `{trabalho}` (no prompt ou nas travas), tem parâmetro
`texto_longo` ou liga `sandbox` (essa dispara com cwd = pasta de trabalho). Dentro:
`entrada.json` (ação e valores) e `entrada.md` (o texto longo; o prompt recebe o caminho, assim o argv nunca leva quebra de linha). O marcador `{trabalho}`
vira o caminho real (realpath): no prompt como está; em regra de permissão em texto com `//`
na frente (caminho absoluto do Claude Code) e curinga escapado; em regex do gancho com
re.escape. `{estudio_hf}` (o HyperFrames do Estúdio, `est` de embutidos.estudio_da_acao) do mesmo jeito,
na forma que o shell lê (shlex.quote); sem `est` a ação que o cita é recusada, nunca vira caminho vazio.
Python 3.9, só biblioteca padrão.
"""
import json
import os
import re
import secrets
import shlex
import shutil

from catalogo import ESTUDIO_HF, RE_CONTROLE, TRABALHO, ErroAcao, montar

MARCA = "{" + TRABALHO + "}"
MARCA_HF = "{" + ESTUDIO_HF + "}"
ARQ_ENTRADA, ARQ_TEXTO = "entrada.json", "entrada.md"
RE_CURINGA = re.compile(r"([*?\[\]])")
_SINAL = "\x00trabalho\x00"  # valor de parâmetro nunca tem \x00 (RE_CONTROLE): montar não mexe no caminho


def _longos(acao):
    return [p["nome"] for p in acao["params"] if p["tipo"] == "texto_longo"]


def usa(acao):
    trv = json.dumps(acao.get("_travas") or {}, ensure_ascii=False)
    return (MARCA in acao["_prompt"] or MARCA in trv or MARCA_HF in acao["_prompt"] or MARCA_HF in trv
            or bool(_longos(acao)) or bool(acao.get("sandbox")))


def nova_pasta(dados_dir, acao):
    """Caminho real da pasta nova (ainda não criada) ou None se a ação não usa pasta de trabalho."""
    if not usa(acao):
        return None
    pasta = os.path.join(os.path.realpath(dados_dir), "trabalhos", secrets.token_hex(6))
    if RE_CONTROLE.search(pasta):
        raise ErroAcao("A pasta do painel tem um caractere que não pode.", 500)
    return pasta


def _hf(acao, est):
    """O caminho do HyperFrames como o shell lê; ação que cita {estudio_hf} sem caminho calculado: recusa."""
    if est and est.get("hf"):
        return shlex.quote(est["hf"])
    if MARCA_HF in acao["_prompt"] + json.dumps(acao.get("_travas") or {}, ensure_ascii=False):
        raise ErroAcao("Prepare o Estúdio antes: abra a tela Estúdio, aba 1. Ambiente, e clique em Preparar.", 409)
    return None


def montar_prompt(acao, valores, pasta, est=None):
    """Prompt com `{trabalho}` = pasta, cada texto_longo = caminho do entrada.md e `{estudio_hf}` = o HyperFrames."""
    hf = _hf(acao, est)
    trocas = {ESTUDIO_HF: hf} if hf else {}
    if pasta is not None:
        trocas[TRABALHO] = pasta
        trocas.update({n: os.path.join(pasta, ARQ_TEXTO) for n in _longos(acao)})
    if not trocas:
        return montar(acao["_prompt"], valores)
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


def resolver_travas(acao, pasta, est=None):
    """Cópia da ação com `{trabalho}` trocado nas regras de negar/permitir (texto e regex do gancho) e
    `{estudio_hf}` nas regex do gancho; com `est`, leva o binário exato e a pasta dos scripts do Estúdio (_estudio)."""
    trv = acao.get("_travas") or {}
    hf = _hf(acao, est)
    regra_txt, regra_re = caminho_de_regra(pasta), re.escape(pasta)
    novo = dict(trv)
    for campo in ("negar", "permitir"):  # {estudio_hf} só vale em regex do gancho
        novo[campo] = [r.replace(MARCA, regra_txt) for r in trv.get(campo) or []]
    for campo in ("regras_negar", "regras_permitir"):
        novo[campo] = [dict(r, entrada=r["entrada"].replace(MARCA, regra_re).replace(MARCA_HF, re.escape(hf or "")))
                       if "entrada" in r else r for r in trv.get(campo) or []]
    extra = {"_estudio": {"exe": [hf], "py": est.get("py")}} if hf else {}
    return dict(acao, _travas=novo, **extra)


def criar(pasta, acao, valores):
    """Cria a pasta (0700) com entrada.json e, se houver, entrada.md. pasta None = nada."""
    if pasta is None:
        return
    os.makedirs(os.path.dirname(pasta), mode=0o700, exist_ok=True)
    if os.path.realpath(os.path.dirname(pasta)) != os.path.dirname(pasta):  # `trabalhos` virou link: recusa
        raise ErroAcao("A pasta de trabalhos do painel aponta para outro lugar (link). Apague o link e tente de novo.", 500)
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
