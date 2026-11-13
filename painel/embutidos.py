"""Módulos embutidos: o Estúdio e o Vendas vêm dentro do próprio tune-up e chegam desligados.

A lista é fixa (EMBUTIDOS): o id da URL nunca vira caminho. O arquivo de cada um fica sob a raiz do
plugin (a pasta acima de painel/) e passa pela checagem de caminho real. Ligado ou desligado mora em
<dados>/embutidos-ligados.json, que só o servidor grava (travas.DONO). true/false no arquivo vence; a
linha antiga do painel.json ("modulos_de_plugins": ["tune-up-studio@...:estudio"], do plugin separado de
antes) só conta como ligado enquanto o arquivo não fala daquele id. Arquivo ilegível = tudo desligado.
As regras de negar vêm da lista fixa daqui, sem importar o módulo (import quebrado travaria toda sessão).
Python 3.9, só biblioteca padrão.
"""
import json
import os
import stat
import sys
import threading

import config

ARQUIVO = "embutidos-ligados.json"
MAX_BYTES = 4096
_lock = threading.Lock()

# cópia fiel de INFO["negar"] de vendas/painel/modulos/vendas/modulo.py (test_embutidos confere as duas)
PASTAS_DADOS_VENDAS = ("~/Library/Application Support/tune-up-vendas", "~/.local/share/tune-up-vendas",
                       "~/AppData/Local/tune-up-vendas")
NEGAR_VENDAS = ("Bash(*127.0.0.1:8791*)", "Bash(*localhost:8791*)", "Bash(*127.0.0.1:8080*)",
                "Bash(*localhost:8080*)", "Bash(*/api/modulos/*/acao*)", "Bash(*tune-up-vendas*)",
                "Bash(*docker exec*)", "Bash(*docker inspect*)", "Bash(*docker compose config*)",
                "Bash(*security find-generic-password*)") \
    + tuple("%s(%s/**)" % (f, d) for d in PASTAS_DADOS_VENDAS for f in ("Read", "Edit", "Write"))

EMBUTIDOS = (
    {"id": "estudio", "titulo": "Estúdio", "plugin": "tune-up-studio",
     "descricao": "Cria posts, vídeos e anúncios com a marca do seu negócio, e você aprova antes de usar.",
     "modulo": "tune-up-studio/painel/modulos/estudio/modulo.py", "acoes": "tune-up-studio/painel/acoes",
     "negar": (), "aviso": None,
     "sem_windows": "o Studio precisa do sandbox do Claude Code, que não roda no Windows; use macOS, Linux ou WSL2"},
    {"id": "vendas", "titulo": "Vendas", "plugin": "tune-up-vendas",
     "descricao": "Responde e acompanha as conversas de venda do seu WhatsApp.",
     "modulo": "vendas/painel/modulos/vendas/modulo.py", "acoes": None,
     "negar": NEGAR_VENDAS, "aviso": "primeira versão testada só no macOS; precisa de Docker", "sem_windows": None},
)
_POR_ID = {e["id"]: e for e in EMBUTIDOS}


def _dentro(rel):
    """Caminho real de `rel` sob a raiz do plugin, ou None se escapa dela."""
    base = os.path.realpath(os.path.dirname(config.PAINEL))
    real = os.path.realpath(os.path.join(base, rel))
    return real if real.startswith(base.rstrip(os.sep) + os.sep) else None


def caminho(mid):
    """Caminho real do modulo.py do embutido `mid`, ou None."""
    e = _POR_ID.get(mid)
    real = _dentro(e["modulo"]) if e else None
    return real if real and os.path.isfile(real) else None


def _motivo(e):
    """Por que o embutido não roda neste computador (lido na hora: o teste troca sys.platform), ou None."""
    return e["sem_windows"] if e["sem_windows"] and sys.platform == "win32" else None


def _arquivo(cfg):
    return os.path.join(cfg.get("dados_dir") or "", ARQUIVO)


def _ler(cfg):
    """({id: bool}, None); ({}, None) sem arquivo; (None, aviso) se é atalho, ilegível ou inválido."""
    aviso = ("o arquivo %s não abre; deixei os módulos embutidos desligados (ligue de novo pela tela ou "
             "apague o arquivo)" % ARQUIVO)
    if not cfg.get("dados_dir"):  # sem pasta de dados o nome solto cairia na pasta atual
        return None, aviso
    try:
        fd = os.open(_arquivo(cfg), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    except FileNotFoundError:
        return {}, None
    except OSError:
        return None, aviso
    try:
        with os.fdopen(fd, "rb") as f:
            if not stat.S_ISREG(os.fstat(f.fileno()).st_mode):
                return None, aviso
            bruto = f.read(MAX_BYTES + 1)
        dado = json.loads(bruto.decode("utf-8")) if len(bruto) <= MAX_BYTES else None
    except (OSError, ValueError):
        return None, aviso
    if not isinstance(dado, dict) or any(not isinstance(dado[i], bool) for i in _POR_ID if i in dado):
        return None, aviso
    return {i: dado[i] for i in _POR_ID if i in dado}, None


def antiga(entrada):
    """Id do embutido se `entrada` de modulos_de_plugins é a do plugin separado de antes, senão None."""
    if not isinstance(entrada, str):
        return None
    chave, _, mid = entrada.rpartition(":")
    e = _POR_ID.get(mid)
    return mid if e and chave.partition("@")[0] == e["plugin"] else None


def _antigas(cfg):
    lista = (cfg.get("bruto") or {}).get("modulos_de_plugins")
    return {antiga(x): x for x in (lista if isinstance(lista, list) else []) if antiga(x)}


def _situacao(cfg):
    """[(embutido, ligado, conhecido, avisos)]; conhecido = já foi ligado alguma vez (vale para as regras de negar)."""
    estado, aviso = _ler(cfg)
    antigas, projeto = _antigas(cfg), cfg.get("modulos") or []
    saida = []
    for e in EMBUTIDOS:
        mid = e["id"]
        avisos = [aviso] if aviso else []
        if mid in antigas:
            avisos.append("O %s agora faz parte do tune-up; pode tirar essa linha do painel.json: %s"
                          % (e["titulo"], antigas[mid]))
        if mid in projeto:
            avisos.append("o projeto tem um módulo próprio com o id %s; a tela dele vale no lugar desta" % mid)
        if e["aviso"]:
            avisos.append(e["aviso"])
        ligado = False if estado is None else estado.get(mid, mid in antigas)
        conhecido = estado is None or mid in estado or mid in antigas
        saida.append((e, bool(ligado) and not _motivo(e), conhecido, avisos))
    return saida


def ligados(cfg):
    """Ids dos embutidos ligados e disponíveis neste computador."""
    return [e["id"] for e, ligado, _, _ in _situacao(cfg) if ligado]


def pastas_de_acoes(cfg):
    """Pastas de ações dos embutidos ligados (código do núcleo: sem a trava das extensões)."""
    pastas = [_dentro(_POR_ID[mid]["acoes"]) for mid in ligados(cfg) if _POR_ID[mid]["acoes"]]
    return [p for p in pastas if p and os.path.isdir(p)]


def negar(cfg):
    """Regras de negar dos embutidos ligados ou que já foram ligados (no arquivo ou na linha antiga)."""
    regras = []
    for e, _, conhecido, _ in _situacao(cfg):
        regras += [r for r in e["negar"] if conhecido and r not in regras]
    return regras


def _publico(cfg):
    return [{"id": e["id"], "titulo": e["titulo"], "descricao": e["descricao"], "ligado": ligado,
             "disponivel": _motivo(e) is None, "motivo": _motivo(e), "avisos": avisos}
            for e, ligado, _, avisos in _situacao(cfg)]


def listar(cfg):
    """(200, corpo) de GET /api/embutidos."""
    return 200, {"embutidos": _publico(cfg)}


def _gravar(cfg, mid, ligado):
    """Grava a escolha. Arquivo ilegível vira tudo false + a escolha (as regras de negar seguem valendo).
    Levanta OSError se não grava: quem chamou responde erro, nunca sucesso."""
    with _lock:
        atual, _ = _ler(cfg)
        novo = dict({i: False for i in _POR_ID} if atual is None else atual)
        novo[mid] = ligado
        texto = json.dumps(novo, ensure_ascii=False, indent=1, sort_keys=True)
        caminho_arq = _arquivo(cfg)
        os.makedirs(cfg["dados_dir"], mode=0o700, exist_ok=True)
        tmp = caminho_arq + ".gravando"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(tmp, caminho_arq)  # troca o nome: um atalho plantado no lugar some, não é seguido


def mudar(cfg, mid, corpo, depois=None):
    """(código, corpo) de POST /api/embutidos/<id> {"ligado": bool}; `depois()` roda só se gravou."""
    e = _POR_ID.get(mid)
    if e is None:
        return 404, {"erro": "Esse módulo embutido não existe."}
    ligado = corpo.get("ligado")
    if not isinstance(ligado, bool):
        return 400, {"erro": "Mande \"ligado\" como true ou false."}
    if ligado and _motivo(e):
        return 409, {"erro": "Este módulo não roda neste computador: %s." % _motivo(e)}
    try:
        _gravar(cfg, mid, ligado)
    except (OSError, KeyError) as ex:
        return 500, {"erro": "Não consegui guardar a escolha (%s); nada mudou." % type(ex).__name__}
    if depois:
        depois()
    return 200, {"ok": True, "embutidos": _publico(cfg)}
