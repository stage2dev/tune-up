"""Plugins do Claude Code (GET/POST /api/plugins, C15): lista o enabledPlugins do settings do usuário, do
projeto e do local (o último vence) e liga/desliga um plugin só no settings do USUÁRIO, trocando apenas o
booleano dele. Nunca cria chave, nunca grava projeto/local, nunca devolve o resto do arquivo (env etc.)."""
import collections
import datetime
import hashlib
import json
import os
import re
import secrets
import stat
import threading

import config
import habilidades
import mascara

LER_MAX = 1024 * 1024
BACKUPS = 3
BOM = b"\xef\xbb\xbf"
ROTULO = {"usuario": "settings do usuário", "projeto": "settings do projeto", "local": "settings.local do projeto"}
_lock = threading.Lock()


def _antes_de_trocar(real):
    """Ponto de teste: roda entre gravar o temporário e conferir o hash do arquivo."""


def _carimbo():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _usuario(cfg):
    return os.path.join(cfg["home"], ".claude", "settings.json")


def _arquivos(cfg):
    usuario, saida = _usuario(cfg), [("usuario", _usuario(cfg))]
    if cfg.get("raiz"):
        for origem, nome in (("projeto", "settings.json"), ("local", "settings.local.json")):
            arq = os.path.join(cfg["raiz"], ".claude", nome)
            if os.path.realpath(arq) != os.path.realpath(usuario):  # painel aberto no próprio home
                saida.append((origem, arq))
    return saida


def _sem_repetida(pares):
    d = collections.OrderedDict()
    for k, v in pares:
        if k in d:
            raise ValueError("chave repetida")  # regravar perderia uma delas
        d[k] = v
    return d


def _bytes(caminho, nofollow=False):
    """(bytes, modo) do arquivo comum; (None, None) se não existe. OSError se não lê."""
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | (getattr(os, "O_NOFOLLOW", 0) if nofollow else 0)
    try:
        fd = os.open(caminho, flags)
    except FileNotFoundError:
        return None, None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise OSError("não é arquivo comum")
        partes, total = [], 0
        while True:
            p = os.read(fd, 65536)
            if not p:
                break
            total += len(p)
            if total > LER_MAX:
                raise OSError("arquivo grande demais")
            partes.append(p)
        return b"".join(partes), stat.S_IMODE(st.st_mode)
    finally:
        os.close(fd)


def _objeto(bruto):
    dado = json.loads(bruto.decode("utf-8-sig"), object_pairs_hook=_sem_repetida)
    if not isinstance(dado, dict):
        raise ValueError("não é objeto")
    return dado


def _fixo(pid):
    return pid.split("@", 1)[0] == "tune-up"


def _medir(home, chave):
    """(skills, agentes, peso) do plugin pela pasta de instalação; zeros se ela é desconhecida."""
    e = config.entrada_do_plugin(chave, home)
    if e is None:
        return 0, 0, 0
    base = os.path.expanduser(e["installPath"])
    skills = peso = agentes = 0
    pasta = os.path.join(base, "skills")
    try:
        nomes = sorted(os.listdir(pasta))[:habilidades.TETO]
    except OSError:
        nomes = []
    for d in nomes:
        lido = habilidades.ler_skill(os.path.join(pasta, d, "SKILL.md")) if habilidades.RE_NOME.match(d) else None
        if lido is not None:  # mesma conta de habilidades.descobrir
            skills += 1
            peso += len(re.sub(r"\s+", " ", mascara.mascarar(lido[1])).strip()[:habilidades.DESCRICAO_MAX])
    try:
        agentes = sum(1 for n in os.listdir(os.path.join(base, "agents"))
                      if n.endswith(".md") and os.path.isfile(os.path.join(base, "agents", n)))
    except OSError:
        pass
    return skills, agentes, peso


def _publico(cfg):
    mapas, ruins = {}, []
    for origem, arq in _arquivos(cfg):
        try:
            bruto, _ = _bytes(arq)
            mapa = _objeto(bruto).get("enabledPlugins") if bruto is not None else None
        except (OSError, ValueError) as e:
            ruins.append("%s (%s)" % (ROTULO[origem], type(e).__name__))
            continue
        if isinstance(mapa, dict):
            mapas[origem] = {k: v for k, v in mapa.items() if isinstance(v, bool)}
    lista = []
    for pid in sorted({k for m in mapas.values() for k in m}):
        valores = {o: mapas[o][pid] for o in ("usuario", "projeto", "local") if pid in mapas.get(o, {})}
        origem = list(valores)[-1]
        skills, agentes, peso = _medir(cfg["home"], pid)
        lista.append({"id": pid, "ligado": valores[origem], "origem": origem, "valores": valores,
                      "sobreposto": "usuario" in valores and origem != "usuario", "fixo": _fixo(pid),
                      "skills": skills, "agentes": agentes, "peso": peso})
    aviso = "Não consegui ler: %s; esses valores ficaram de fora." % ", ".join(ruins) if ruins else None
    return lista, aviso


def listar(cfg):
    """(200, corpo) de GET /api/plugins."""
    lista, aviso = _publico(cfg)
    return 200, {"plugins": lista, "aviso": aviso}


def _temp(pasta, base, dados):
    """Grava `dados` num temporário novo (O_EXCL, sem seguir atalho, 0600) ao lado do arquivo; devolve o nome."""
    tmp = os.path.join(pasta, ".%s.%s.tmp" % (base, secrets.token_hex(6)))
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
            f.flush()
            os.fsync(f.fileno())
    except BaseException:
        _tirar(tmp)
        raise
    return tmp


def _tirar(caminho):
    try:
        os.remove(caminho)
    except OSError:
        pass


def _podar(pasta, base):
    """Deixa só os BACKUPS mais novos de <base>.bak-AAAAMMDD-HHMMSS; não toca em mais nada."""
    rx = re.compile(re.escape(base) + r"\.bak-\d{8}-\d{6}\Z")
    try:
        velhos = sorted((n for n in os.listdir(pasta) if rx.match(n)), reverse=True)[BACKUPS:]
    except OSError:
        return
    for n in velhos:
        _tirar(os.path.join(pasta, n))  # falhar aqui só deixa um backup a mais


def _gravar(cfg, pid, ligar):
    """(código, erro ou None, gravou). Troca só enabledPlugins[pid] no settings do usuário (o arquivo real
    por trás de um atalho). OSError sobe: quem chamou responde 500."""
    real = os.path.realpath(_usuario(cfg))
    try:
        bruto, modo = _bytes(real, nofollow=True)
        dado = _objeto(bruto) if bruto is not None else None
    except (OSError, ValueError):
        return 409, "Não consegui ler seu settings do Claude (JSON inválido ou com comentário); não mexi nele.", False
    mapa = (dado or {}).get("enabledPlugins")
    if not isinstance(mapa, dict) or not isinstance(mapa.get(pid), bool):
        return 404, "Esse plugin não está no seu settings do Claude.", False
    if _fixo(pid):
        return 409, "O tune-up não se desliga por aqui.", False
    if mapa[pid] is ligar:
        return 200, None, False
    mapa[pid] = ligar
    texto = bruto.decode("utf-8-sig")
    m = re.search(r'\n([ \t]+)"', texto)
    novo = json.dumps(dado, indent=m.group(1) if m else 2, ensure_ascii=False) + ("\n" if texto.endswith("\n") else "")
    if "\r\n" in texto:
        novo = novo.replace("\n", "\r\n")
    novo = (BOM if bruto.startswith(BOM) else b"") + novo.encode("utf-8")
    pasta, base = os.path.split(real)
    tmp = _temp(pasta, base, novo)
    try:
        _antes_de_trocar(real)
        agora, _ = _bytes(real, nofollow=True)
        if agora is None or hashlib.sha256(agora).digest() != hashlib.sha256(bruto).digest():
            return 409, "Seu settings do Claude mudou enquanto eu gravava; nada mudou. Tente de novo.", False
        bak = _temp(pasta, base, bruto)
        try:
            os.replace(bak, os.path.join(pasta, "%s.bak-%s" % (base, _carimbo())))  # mesmo segundo: fica o último
        except OSError:
            _tirar(bak)
            raise
        if os.name != "nt":
            os.chmod(tmp, modo if modo & ~0o644 == 0 else 0o600)  # mantém o modo; nunca abre mais
        os.replace(tmp, real)
        tmp = None
    finally:
        if tmp:
            _tirar(tmp)
    _podar(pasta, base)
    return 200, None, True


def mudar(cfg, corpo, depois=None):
    """(código, corpo) de POST /api/plugins {"id": str, "enabled": bool}; `depois()` roda só se gravou."""
    if not isinstance(corpo, dict) or set(corpo) != {"id", "enabled"} or not isinstance(corpo["id"], str) \
            or not isinstance(corpo["enabled"], bool):
        return 400, {"erro": "Mande só {\"id\": \"<plugin>\", \"enabled\": true ou false}."}
    try:
        with _lock:
            codigo, erro, gravou = _gravar(cfg, corpo["id"], corpo["enabled"])
    except OSError as ex:
        return 500, {"erro": "Não consegui gravar seu settings do Claude (%s); nada mudou." % type(ex).__name__}
    if erro:
        return codigo, {"erro": erro}
    if gravou:
        with habilidades._trava:  # a lista de skills lê enabledPlugins com cache
            habilidades._cache.clear()
        if depois:
            depois()
    return 200, {"ok": True, "plugins": _publico(cfg)[0], "aviso": "vale na próxima sessão"}
