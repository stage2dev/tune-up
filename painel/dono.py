"""Aprovações do dono: <dados>/<modulo>-dono.json, gravado só pelo servidor.

A função de gravar vai só no ctx de agir() (comando de módulo, POST /api/modulos/<id>/acao),
nunca no de montar(). A sessão do Claude não alcança o arquivo: o nome dele tem de estar em
sandbox.DONO, que entra no denyWrite do sandbox e nas travas de toda sessão. Módulo cujo arquivo
não está nessa lista não tem aprovação (hoje só `estudio`).
Campo `requer` de uma ação ("<modulo>.<chave>"): o lançador recusa disparar se a entrada
não tem "aprovado": true. Arquivo ausente, ilegível, atalho ou de outro módulo = sem aprovação.
Entrada com "sha256" e "arquivo" (relativo à raiz) só vale enquanto o arquivo tiver esses bytes.
Python 3.9, só biblioteca padrão.
"""
import datetime
import hashlib
import json
import os
import re
import threading

import sandbox

RE_REQUER = re.compile(r"^([a-z0-9_-]{1,40})\.([a-z0-9_-]{1,40})$")
MAX_REQUER = 8
MAX_BYTES = 64 * 1024
_lock = threading.Lock()


def arquivo(cfg, mid):
    """Caminho do arquivo de aprovações do módulo ou ValueError (módulo sem arquivo protegido)."""
    nome = "%s-dono.json" % mid
    if not isinstance(mid, str) or nome not in sandbox.DONO or not cfg.get("dados_dir"):
        raise ValueError("o módulo %s não guarda aprovação do dono" % mid)
    return os.path.join(cfg["dados_dir"], nome)


def ler(cfg, mid):
    """{chave: {...}}; {} se o arquivo não existe; None se é atalho, ilegível ou não é objeto."""
    caminho = arquivo(cfg, mid)
    if os.path.islink(caminho):
        return None
    try:
        with open(caminho, encoding="utf-8") as f:
            dado = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    return dado if isinstance(dado, dict) else None


def gravar(cfg, mid, chave, valor):
    """Grava `valor` (objeto JSON) em `chave`, mais `gravado_em`. ValueError se algo não confere;
    nunca sobrescreve um arquivo que não lê (o dono perderia as outras aprovações)."""
    if not isinstance(chave, str) or not RE_REQUER.match("x." + chave):
        raise ValueError("chave de aprovação inválida")
    if not isinstance(valor, dict):
        raise ValueError("a aprovação precisa ser um objeto")
    caminho = arquivo(cfg, mid)
    with _lock:
        atual = ler(cfg, mid)
        if atual is None:
            raise ValueError("o arquivo de aprovações não abre; corrija ou apague %s" % os.path.basename(caminho))
        atual[chave] = dict(valor, gravado_em=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
        texto = json.dumps(atual, ensure_ascii=False, allow_nan=False, indent=1, sort_keys=True)
        if len(texto.encode("utf-8")) > MAX_BYTES:
            raise ValueError("aprovações grandes demais")
        os.makedirs(cfg["dados_dir"], mode=0o700, exist_ok=True)
        tmp = caminho + ".gravando"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(tmp, caminho)  # troca o nome: um atalho plantado no lugar some, não é seguido
    return atual[chave]


def validar_requer(bruto):
    """`requer` do JSON da ação (texto ou lista) -> lista limpa; ValueError se inválido."""
    if bruto is None:
        return []
    lista = [bruto] if isinstance(bruto, str) else bruto
    if not isinstance(lista, list) or not 1 <= len(lista) <= MAX_REQUER \
            or not all(isinstance(r, str) and RE_REQUER.match(r) for r in lista):
        raise ValueError("requer inválido (\"<modulo>.<chave>\" ou lista de até %d)" % MAX_REQUER)
    return list(dict.fromkeys(lista))


def _mesmo_conteudo(cfg, v):
    """True se a aprovação não prende arquivo, ou se o arquivo aprovado ainda tem o mesmo sha256."""
    if "sha256" not in v and "arquivo" not in v:
        return True
    rel, raiz = v.get("arquivo"), cfg.get("raiz") or cfg.get("workspace")
    if not (isinstance(rel, str) and rel and raiz) or rel.startswith("/") or ".." in rel.split("/"):
        return False
    caminho = os.path.join(raiz, *rel.split("/"))
    try:
        if os.path.islink(caminho):
            return False
        with open(caminho, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest() == v.get("sha256")
    except OSError:
        return False


def faltando(cfg, requer):
    """Entradas de `requer` sem "aprovado": true no arquivo do módulo. Fecha na dúvida."""
    falta = []
    for r in requer or []:
        m = RE_REQUER.match(r) if isinstance(r, str) else None
        try:
            dado = ler(cfg, m.group(1)) if m else None
        except ValueError:
            dado = None
        v = dado.get(m.group(2)) if dado else None
        if not (isinstance(v, dict) and v.get("aprovado") is True and _mesmo_conteudo(cfg, v)):
            falta.append(r if isinstance(r, str) else repr(r))
    return falta
