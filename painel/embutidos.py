"""Módulos embutidos: o Estúdio, o Vendas e o Marketing vêm dentro do próprio tune-up e chegam desligados.

A lista é fixa (EMBUTIDOS): o id da URL nunca vira caminho. O arquivo de cada um fica sob a raiz do
plugin (a pasta acima de painel/) e passa pela checagem de caminho real. Ligado ou desligado mora em
<dados>/embutidos-ligados.json, que só o servidor grava (travas.DONO). true/false no arquivo vence; a
linha antiga do painel.json ("modulos_de_plugins": ["tune-up-studio@...:estudio"], do plugin separado de
antes) só conta como ligado enquanto o arquivo não fala daquele id. Arquivo ilegível = tudo desligado.
As regras de negar vêm da lista fixa daqui, sem importar o módulo (import quebrado travaria toda sessão).
O código deles (PASTAS_CODIGO, ligado ou não) é protegido nas sessões como painel/ (travas.argv_travas).
`{estudio_hf}` (prompt e travas da ação): o caminho do HyperFrames do Estúdio, calculado aqui (nunca lido do
ambiente.json, que uma sessão sem sandbox pode gravar). Python 3.9, só biblioteca padrão.
"""
import hashlib
import json
import os
import stat
import sys
import threading

import config
from catalogo import ESTUDIO_HF, RE_CONTROLE, ErroAcao, ler_sonda

ARQUIVO = "embutidos-ligados.json"
MAX_BYTES = 4096
_lock = threading.Lock()

# cópia fiel de INFO["negar"] de vendas/painel/modulos/vendas/modulo.py (test_embutidos confere as duas)
PASTAS_DADOS_VENDAS = ("~/Library/Application Support/tune-up-vendas", "~/.local/share/tune-up-vendas",
                       "~/AppData/Local/tune-up-vendas")
PORTAS_VENDAS = tuple(range(8791, 8796))  # = PORTAS em modulo.py:64
PORTAS_EVOLUTION = tuple(range(8080, 8085))  # = PORTAS_EVOLUTION em modulo.py:8
NEGAR_VENDAS = tuple("Bash(*%s:%d*)" % (h, p) for p in PORTAS_VENDAS + PORTAS_EVOLUTION
                     for h in ("127.0.0.1", "localhost")) \
    + ("Bash(*/api/modulos/*/acao*)", "Bash(*tune-up-vendas*)",
       "Bash(*docker exec*)", "Bash(*docker inspect*)", "Bash(*docker compose config*)",
       "Bash(*security find-generic-password*)",
       "Bash(*vendas*servico*preparo.py*)", "Bash(*vendas*servico*servico.py*)") \
    + tuple("%s(%s/**)" % (f, d) for d in PASTAS_DADOS_VENDAS for f in ("Read", "Edit", "Write"))

EMBUTIDOS = (
    {"id": "estudio", "titulo": "Estúdio", "plugin": "tune-up-studio",
     "descricao": "Cria posts, vídeos e anúncios com a marca do seu negócio, e você aprova antes de usar.",
     "modulo": "tune-up-studio/painel/modulos/estudio/modulo.py", "acoes": "tune-up-studio/painel/acoes",
     "negar": (), "dados": (), "aviso": None,
     "sem_windows": "o Studio precisa do sandbox do Claude Code, que não roda no Windows; use macOS, Linux ou WSL2"},
    {"id": "vendas", "titulo": "Vendas", "plugin": "tune-up-vendas",
     "descricao": "Responde e acompanha as conversas de venda do seu WhatsApp.",
     "modulo": "vendas/painel/modulos/vendas/modulo.py", "acoes": None,
     "negar": NEGAR_VENDAS, "dados": PASTAS_DADOS_VENDAS,
     "aviso": "primeira versão testada só no macOS; precisa de Docker", "sem_windows": None},
    {"id": "mkt", "titulo": "Marketing", "plugin": "tune-up-mkt",
     "descricao": "Mostra quais contas de marketing estão ligadas e confere de novo com um clique.",
     "modulo": "tune-up-mkt/painel/modulos/mkt/modulo.py", "acoes": None,
     "negar": (), "dados": (), "aviso": None, "sem_windows": None},
)
_POR_ID = {e["id"]: e for e in EMBUTIDOS}
# tudo o que os módulos importam ou rodam no servidor (irmãos, scripts/, node/, servico/) mora nestas pastas
# (tune-up-mkt: o módulo carrega scripts/contas_*.py e o servidor roda scripts/contas.py status)
PASTAS_CODIGO = ("tune-up-studio", "vendas", "tune-up-mkt")


def pastas_codigo():
    """As pastas de código dos embutidos, como o painel as vê e pelo caminho real (as duas formas)."""
    raiz = os.path.dirname(config.PAINEL)
    out = []
    for nome in PASTAS_CODIGO:
        for p in (os.path.join(raiz, nome), os.path.join(os.path.realpath(raiz), nome)):
            out += [p] if p not in out else []
    return out


def _pasta(rel):
    """Caminho real da pasta `rel` sob a raiz do plugin, ou None se ela (ou algo no meio) é atalho."""
    # normpath: no Windows o realpath troca / por \ e a pasta nunca casaria consigo mesma (embutido sumia)
    pasta = os.path.join(os.path.realpath(os.path.dirname(config.PAINEL)), os.path.normpath(rel))
    return pasta if os.path.realpath(pasta) == pasta and os.path.isdir(pasta) else None


def caminho(mid):
    """Caminho real do modulo.py do embutido `mid`, ou None (atalho ou fora da própria pasta: recusado)."""
    e = _POR_ID.get(mid)
    pasta = _pasta(os.path.dirname(e["modulo"])) if e else None
    arq = os.path.join(pasta, os.path.basename(e["modulo"])) if pasta else None
    if not arq or os.path.islink(arq) or os.path.realpath(arq) != arq or not os.path.isfile(arq):
        return None
    return arq


def _motivo(e, plataforma=None, sonda=None):
    """Por que o embutido não roda neste computador (lido na hora: o teste troca sys.platform), ou None.
    No Windows só vale quando a sonda do WSL2 (dict ou callable) não está pronta; aí o motivo dela vai junto."""
    if not e["sem_windows"] or (sys.platform if plataforma is None else plataforma) != "win32":
        return None
    pronta, porque = ler_sonda(sonda)
    return None if pronta else "%s. Rode scripts\\wsl\\instalar.ps1 (pasta do plugin) e recarregue (%s)" % (
        e["sem_windows"], porque)


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


def _situacao(cfg, plataforma=None, sonda=None):
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
        casa = cfg.get("home") or os.path.expanduser("~")  # pasta de dados em disco: sinal fora de dados_dir
        conhecido = (estado is None or mid in estado or mid in antigas
                     or any(os.path.isdir(os.path.join(casa, d[2:])) for d in e["dados"]))
        saida.append((e, bool(ligado) and not _motivo(e, plataforma, sonda), conhecido, avisos))
    return saida


def ligados(cfg, plataforma=None, sonda=None):
    """Ids dos embutidos ligados e disponíveis neste computador."""
    return [e["id"] for e, ligado, _, _ in _situacao(cfg, plataforma, sonda) if ligado]


def pastas_de_acoes(cfg, plataforma=None, sonda=None):
    """Pastas de ações dos embutidos ligados (código do núcleo: sem a trava das extensões)."""
    pastas = [_pasta(_POR_ID[mid]["acoes"]) for mid in ligados(cfg, plataforma, sonda) if _POR_ID[mid]["acoes"]]
    return [p for p in pastas if p]


def negar(cfg):
    """Regras de negar dos embutidos ligados ou que já foram ligados (no arquivo ou na linha antiga)."""
    regras = []
    for e, _, conhecido, _ in _situacao(cfg):
        regras += [r for r in e["negar"] if conhecido and r not in regras]
    return regras


def _publico(cfg, plataforma=None, sonda=None):
    return [{"id": e["id"], "titulo": e["titulo"], "descricao": e["descricao"], "ligado": ligado,
             "disponivel": _motivo(e, plataforma, sonda) is None, "motivo": _motivo(e, plataforma, sonda),
             "avisos": avisos}
            for e, ligado, _, avisos in _situacao(cfg, plataforma, sonda)]


def listar(cfg, plataforma=None, sonda=None):
    """(200, corpo) de GET /api/embutidos."""
    return 200, {"embutidos": _publico(cfg, plataforma, sonda)}


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


def mudar(cfg, mid, corpo, depois=None, plataforma=None, sonda=None):
    """(código, corpo) de POST /api/embutidos/<id> {"ligado": bool}; `depois()` roda só se gravou."""
    e = _POR_ID.get(mid)
    if e is None:
        return 404, {"erro": "Esse módulo embutido não existe."}
    ligado = corpo.get("ligado")
    if not isinstance(ligado, bool):
        return 400, {"erro": "Mande \"ligado\" como true ou false."}
    motivo = _motivo(e, plataforma, sonda)
    if ligado and motivo:
        return 409, {"erro": "Este módulo não roda neste computador: %s." % motivo}
    try:
        _gravar(cfg, mid, ligado)
    except (OSError, KeyError) as ex:
        return 500, {"erro": "Não consegui guardar a escolha (%s); nada mudou." % type(ex).__name__}
    if depois:
        depois()
    return 200, {"ok": True, "embutidos": _publico(cfg, plataforma, sonda)}


MARCA_HF = "{" + ESTUDIO_HF + "}"
REL_HF = ("node", "node_modules", ".bin", "hyperframes")


def chave_do_ambiente(studio):
    """= preparar_estudio.chave_do_ambiente (test_estudio_hf confere): 12 hex do sha256 do package-lock.json."""
    with open(os.path.join(studio, "node", "package-lock.json"), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def _sob(caminho, pasta):
    c, p = os.path.realpath(caminho), os.path.realpath(pasta)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def estudio_hf(cfg):
    """Caminho exato do HyperFrames do Estúdio ou None. Sob ~/.claude (instalado do marketplace):
    <dados_dir real>/estudio-node/<chave>/node/...; fora (checkout, --plugin-dir): <raiz>/tune-up-studio/node/..."""
    studio = os.path.join(os.path.realpath(os.path.dirname(config.PAINEL)), "tune-up-studio")
    try:
        if not _sob(studio, os.path.join(cfg.get("home") or os.path.expanduser("~"), ".claude")):
            hf = os.path.join(studio, *REL_HF)
        elif cfg.get("dados_dir"):
            base = os.path.join(os.path.realpath(cfg["dados_dir"]), "estudio-node")
            hf = os.path.join(base, chave_do_ambiente(studio), *REL_HF)
            hf = hf if os.path.realpath(hf).startswith(base + os.sep) else None  # atalho para fora: não
        else:
            hf = None
    except OSError:
        return None
    return hf if hf and os.path.isabs(hf) and not RE_CONTROLE.search(hf) else None


def estudio_da_acao(cfg, acao):
    """{"hf", "py"} da ação que cita {estudio_hf} (prompt ou travas); None se não cita. Levanta ErroAcao 409
    se o Estúdio não está preparado para esta chave (o binário não existe no caminho calculado)."""
    if MARCA_HF not in acao["_prompt"] + json.dumps(acao.get("_travas") or {}, ensure_ascii=False):
        return None
    hf = estudio_hf(cfg)
    if not hf or not os.path.isfile(hf):
        raise ErroAcao("Prepare o Estúdio antes: abra a tela Estúdio, aba 1. Ambiente, e clique em Preparar.", 409)
    py = os.path.join(os.path.realpath(os.path.dirname(config.PAINEL)), "tune-up-studio", "scripts") + os.sep
    return {"hf": hf, "py": py}
