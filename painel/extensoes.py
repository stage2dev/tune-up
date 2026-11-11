"""Extensões vindas de plugins instalados: ações (acoes_de_plugins) e a trava de versão.

painel.json "acoes_de_plugins": ["plugin@marketplace"] soma ao catálogo os <installPath>/painel/acoes/*.json
do plugin instalado (installed_plugins.json, nome@marketplace exato). Os módulos de tela de plugin
(modulos_de_plugins) passam pela mesma trava.

Trava: na primeira vez que um plugin é usado, a versão do registro e um sha256 da pasta instalada
(sem node_modules, .git e __pycache__) ficam em <dados>/extensoes.json. Se um dos dois mudar, nada
desse plugin carrega até a pessoa confirmar: python3 painel.py --aceitar-extensao plugin@marketplace.
Plugin com __pycache__, .pyc/.pyo ou .py atalho dentro de painel/ é recusado (a soma não cobre isso).
Python 3.9, só biblioteca padrão.
"""
import datetime
import hashlib
import json
import os
import re
import threading

import config

RE_NOME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
ARQUIVO = "extensoes.json"
PULAR = ("node_modules", ".git", "__pycache__")
MAX_ARQUIVOS, MAX_BYTES = 5000, 200 * 1024 * 1024
_lock = threading.Lock()
_somas = {}  # pasta -> (assinatura de nomes, tamanhos e mtimes, sha256)


def chave_ok(chave):
    plugin, sep, mkt = chave.partition("@") if isinstance(chave, str) else ("", "", "")
    return bool(sep and RE_NOME.match(plugin) and RE_NOME.match(mkt))


def _arquivos(base):
    """[(caminho relativo com /, caminho)] em ordem; atalho entra como atalho, sem seguir."""
    saida = []
    for pasta, dirs, nomes in os.walk(base):
        links = [d for d in dirs if d not in PULAR and os.path.islink(os.path.join(pasta, d))]
        dirs[:] = sorted(d for d in dirs if d not in PULAR and d not in links)
        for n in sorted(set(nomes) | set(links)):
            cam = os.path.join(pasta, n)
            saida.append((os.path.relpath(cam, base).replace(os.sep, "/"), cam))
            if len(saida) > MAX_ARQUIVOS:
                raise ValueError("mais de %d arquivos" % MAX_ARQUIVOS)
    return sorted(saida)


def soma(base):
    """sha256 da pasta instalada (nomes e conteúdo). Levanta ValueError se passa dos limites."""
    lista = _arquivos(base)
    assin = []
    for rel, cam in lista:
        st = os.lstat(cam)
        assin.append((rel, st.st_size, st.st_mtime_ns, st.st_ctime_ns, st.st_ino, os.path.islink(cam)))
    assin = tuple(assin)
    with _lock:
        if _somas.get(base, (None,))[0] == assin:
            return _somas[base][1]
    if sum(a[1] for a in assin) > MAX_BYTES:
        raise ValueError("mais de %d MB" % (MAX_BYTES // (1024 * 1024)))
    h = hashlib.sha256()
    for rel, cam in lista:
        h.update(rel.encode("utf-8", "surrogateescape") + b"\0")
        if os.path.islink(cam):
            h.update(b"L" + os.readlink(cam).encode("utf-8", "surrogateescape") + b"\0")
            continue
        with open(cam, "rb") as f:
            for bloco in iter(lambda: f.read(1024 * 1024), b""):
                h.update(bloco)
        h.update(b"\0")
    valor = h.hexdigest()
    with _lock:
        _somas[base] = (assin, valor)
    return valor


def _codigo_fora_da_soma(base):
    """Caminho relativo de um __pycache__, .pyc/.pyo ou .py atalho em <base>/painel/ (a soma não os cobre:
    o import do servidor rodaria esse código sem confirmação); None se não há."""
    for pasta, dirs, nomes in os.walk(os.path.join(base, "painel")):
        for n in sorted(dirs + nomes):
            cam = os.path.join(pasta, n)
            if n == "__pycache__" or n.lower().endswith((".pyc", ".pyo")) \
                    or n.lower().endswith(".py") and os.path.islink(cam):
                return os.path.relpath(cam, base).replace(os.sep, "/")
    return None


def _registro(cfg):
    return os.path.join(cfg.get("dados_dir") or "", ARQUIVO)


def _ler(cfg):
    """{chave: {...}} aceitas; {} se o arquivo não existe; None se existe e não lê."""
    try:
        with open(_registro(cfg), encoding="utf-8") as f:
            dado = json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    return dado if isinstance(dado, dict) else None


def _gravar(cfg, dado):
    destino = cfg.get("dados_dir")
    os.makedirs(destino, mode=0o700, exist_ok=True)
    tmp = _registro(cfg) + ".gravando"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(dado, f, ensure_ascii=False, indent=1, sort_keys=True)
    os.replace(tmp, _registro(cfg))


def _atual(cfg, chave):
    """(installPath, {"versao", "sha256"}) do plugin instalado; levanta ValueError com o motivo."""
    entrada = config.entrada_do_plugin(chave, cfg.get("home"))
    if not entrada:
        raise ValueError("plugin %s não está instalado" % chave)
    base = os.path.realpath(os.path.expanduser(entrada["installPath"]))
    if not os.path.isdir(base):
        raise ValueError("plugin %s: pasta instalada não existe" % chave)
    ruim = _codigo_fora_da_soma(base)
    if ruim:
        raise ValueError("plugin %s: código compilado ou atalho em %s; apague e reinstale" % (chave, ruim[:120]))
    try:
        sha = soma(base)
    except (OSError, ValueError) as e:
        raise ValueError("plugin %s: não consegui conferir a pasta (%s)" % (chave, str(e)[:120]))
    return base, {"versao": str(entrada.get("version") or ""), "sha256": sha}


def conferir(cfg, chave):
    """(installPath, None) se o plugin está instalado e bate com o aceito (a 1ª vez grava);
    (None, aviso) se não."""
    try:
        base, atual = _atual(cfg, chave)
    except ValueError as e:
        return None, str(e)
    with _lock:
        aceitas = _ler(cfg)
        if aceitas is None:
            return None, ("%s ilegível; nenhuma extensão de plugin carrega até apagar o arquivo"
                          % _registro(cfg))
        antes = aceitas.get(chave)
        if isinstance(antes, dict) and antes.get("versao") == atual["versao"] \
                and antes.get("sha256") == atual["sha256"]:
            return base, None
        if antes is not None:
            velha = (antes.get("versao") if isinstance(antes, dict) else "") or "?"
            o_que = ("versão %s -> %s" % (velha, atual["versao"] or "?") if velha != (atual["versao"] or "?")
                     else "mesma versão %s, conteúdo diferente" % velha)
            return None, ("plugin %s mudou desde que foi aceito (%s); não carreguei. Confira e "
                          "confirme com: python3 painel.py --aceitar-extensao %s" % (chave, o_que, chave))
        aceitas[chave] = dict(atual, aceito_em=_agora())
        try:
            _gravar(cfg, aceitas)
        except OSError as e:
            return None, "plugin %s: não consegui gravar a aceitação (%s)" % (chave, type(e).__name__)
    return base, None


def aceitar(cfg, chave):
    """Grava a versão e o sha256 de agora para `chave`. Devolve o texto do resultado; ValueError se não dá."""
    if not chave_ok(chave):
        raise ValueError("use plugin@marketplace")
    _, atual = _atual(cfg, chave)
    with _lock:
        aceitas = _ler(cfg)
        if aceitas is None:
            raise ValueError("%s ilegível; apague o arquivo e rode de novo" % _registro(cfg))
        aceitas[chave] = dict(atual, aceito_em=_agora())
        _gravar(cfg, aceitas)
    return "aceito %s versão %s sha256 %s" % (chave, atual["versao"] or "?", atual["sha256"][:12])


def _agora():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def pastas_de_acoes(cfg):
    """([pasta de ações], avisos) dos plugins em acoes_de_plugins que passam na trava."""
    lista = (cfg.get("bruto") or {}).get("acoes_de_plugins")
    if lista is None or lista == []:
        return [], []
    if not isinstance(lista, list):
        return [], ["painel.json: acoes_de_plugins precisa ser uma lista; ignorei"]
    pastas, avisos, vistos = [], [], set()
    for chave in lista:
        if not chave_ok(chave):
            avisos.append("painel.json: ações de plugin %r ignoradas (use plugin@marketplace)" % str(chave)[:80])
            continue
        if chave in vistos:
            continue
        vistos.add(chave)
        base, aviso = conferir(cfg, chave)
        if not base:
            avisos.append("ações de %s recusadas: %s" % (chave, aviso))
            continue
        pasta = os.path.join(base, "painel", "acoes")
        if os.path.realpath(pasta) != pasta or not os.path.isdir(pasta):
            avisos.append("plugin %s: painel/acoes não existe (ou é atalho); nenhuma ação dele" % chave)
            continue
        pastas.append(pasta)
    return pastas, avisos
