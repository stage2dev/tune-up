"""Módulos: telas extras declarativas que vêm do pacote do projeto.

Só carrega <pacote>/modulos/<id>/modulo.py de ids listados em painel.json
"modulos" (ou, de plugin instalado, "modulos_de_plugins": ver modulos_plugin.py). O id segue ^[a-z0-9_-]{1,40}$ e o caminho real do arquivo tem de
ficar dentro de <pacote>/modulos/<id>/ (atalho para fora é recusado). O módulo
expõe INFO = {"id","titulo","icone"} e montar(ctx) -> dict; ctx = {"raiz",
"pacote","dados","config","hoje"}. montar() roda com tempo limite, exceção vira
erro só daquele módulo e a resposta passa por uma conferência mínima de forma.
Opcional: INFO["acoes"] (lista de nomes) + agir(ctx, acao, dados) -> dict, e INFO["negar"]
(regras de permissão negadas em toda sessão que o painel dispara).
Os arquivos irmãos do módulo são importados isolados (ver _importar): nome igual a\num do núcleo ou de outro módulo não vaza.
Python 3.9, só biblioteca padrão.
"""
import datetime
import importlib.util
import json
import os
import re
import sys
import threading
import time

import modulos_plugin
import travas

RE_ID = re.compile(r"^[a-z0-9_-]{1,40}$")
NIVEIS = ("info", "atencao", "critico")
TEMPO_LIMITE = 20.0
TTL = 30.0
MAX_ABAS = 30
MAX_BLOCOS = 100
MAX_ALERTAS = 50

_lock = threading.Lock()
_lock_import = threading.Lock()  # um import de módulo por vez (mexe em sys.path/sys.modules)
_carregados = {}   # caminho -> (mtime, módulo)
_cache = {}        # id -> (quando, código, dado)
_rodando = {}      # id -> thread
_lock_agir = threading.Lock()  # trava das ações, separada da de montar
_agindo = {}       # id -> thread de agir()


class ErroModulo(Exception):
    def __init__(self, codigo, mensagem, avisos=None):
        Exception.__init__(self, mensagem)
        self.codigo, self.mensagem, self.avisos = codigo, mensagem, list(avisos or [])

    def corpo(self):
        return {"erro": self.mensagem, "avisos": self.avisos}


def _agora():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def caminho_do_modulo(cfg, mid):
    """Caminho real de modulo.py ou levanta ErroModulo(404)."""
    if not isinstance(mid, str) or not RE_ID.match(mid):
        raise ErroModulo(404, "Essa tela não existe neste projeto.")
    if mid not in (cfg.get("modulos") or []):
        chave = modulos_plugin.ligados(cfg)[0].get(mid)
        if not chave:
            raise ErroModulo(404, "Essa tela não existe neste projeto.")
        real, aviso = modulos_plugin.caminho(cfg, mid, chave)
        if not real:
            raise ErroModulo(404, "Essa tela não existe neste projeto.", [aviso])
        return real
    pacote = cfg.get("pacote_dir")
    if not pacote or not cfg.get("pacote_ok"):
        raise ErroModulo(404, "Essa tela não existe neste projeto.", ["sem pacote do projeto"])
    pasta = os.path.join(os.path.realpath(pacote), "modulos", mid)
    arq = os.path.join(pasta, "modulo.py")
    real = os.path.realpath(arq)
    if not real.startswith(os.path.realpath(pasta).rstrip(os.sep) + os.sep) \
            or os.path.realpath(pasta) != pasta or not os.path.isfile(real):
        raise ErroModulo(404, "Essa tela não existe neste projeto.",
                         ["modulos/%s/modulo.py não encontrado (ou é atalho para fora do pacote)" % mid])
    return real


def _irmaos(pasta):
    """Nomes que o módulo pode importar da própria pasta (arquivos .py e subpacotes)."""
    nomes = set()
    for n in os.listdir(pasta):
        if n.endswith(".py") and n != "modulo.py":
            nomes.add(n[:-3])
        elif os.path.isfile(os.path.join(pasta, n, "__init__.py")):
            nomes.add(n)
    return nomes


def _da_pasta(nome, mod, nomes, pasta):
    if nome.split(".", 1)[0] in nomes:
        return True
    arq = getattr(mod, "__file__", None)
    return bool(arq) and os.path.realpath(arq).startswith(pasta + os.sep)


def _importar(caminho, mid):
    """Importa modulo.py isolado: os irmãos dele não vazam para o painel nem para outro módulo.

    Durante o import a pasta do módulo fica na frente do sys.path e os nomes dos irmãos saem
    de sys.modules (um util.py ou config.py do módulo não pega o do núcleo nem o de outro
    módulo). No fim, sys.path e sys.modules voltam como estavam; o módulo guarda as suas
    próprias referências. Imports dentro de funções (tardios) não são suportados.
    """
    mtime = os.path.getmtime(caminho)
    with _lock:
        item = _carregados.get(caminho)
        if item and item[0] == mtime:
            return item[1]
    pasta = os.path.realpath(os.path.dirname(caminho))
    spec = importlib.util.spec_from_file_location("painel_modulo_%s" % mid.replace("-", "_"), caminho)
    mod = importlib.util.module_from_spec(spec)
    with _lock_import:
        nomes = _irmaos(pasta)
        guardados = {n: sys.modules.pop(n) for n in list(sys.modules)
                     if n.split(".", 1)[0] in nomes}
        caminho_antes = list(sys.path)
        antes = set(sys.modules)
        bytecode = sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        sys.path.insert(0, pasta)
        try:
            spec.loader.exec_module(mod)
        finally:
            sys.dont_write_bytecode = bytecode
            for n in [n for n in list(sys.modules) if n not in antes]:
                if _da_pasta(n, sys.modules[n], nomes, pasta):
                    del sys.modules[n]
            sys.modules.update(guardados)
            sys.path[:] = caminho_antes
    with _lock:
        _carregados[caminho] = (mtime, mod)
    return mod


def carregar(cfg, mid):
    """O módulo importado ou ErroModulo (404 sem arquivo, 500 se o import quebra)."""
    caminho = caminho_do_modulo(cfg, mid)
    try:
        mod = _importar(caminho, mid)
    except Exception as e:
        raise ErroModulo(500, "Não consegui abrir esta tela.",
                         ["modulo %s não carregou: %s: %s" % (mid, type(e).__name__, str(e)[:200])])
    if not callable(getattr(mod, "montar", None)):
        raise ErroModulo(500, "Esta tela está incompleta.", ["modulo %s não tem montar(ctx)" % mid])
    return mod


def info(mod, mid):
    i = getattr(mod, "INFO", None)
    i = i if isinstance(i, dict) else {}
    titulo = i.get("titulo") if isinstance(i.get("titulo"), str) and i["titulo"].strip() else mid
    icone = i.get("icone") if isinstance(i.get("icone"), str) else ""
    return {"id": mid, "titulo": titulo.strip()[:60], "icone": icone[:40]}


def contexto(cfg):
    pacote = cfg.get("pacote_dir") or ""
    return {"raiz": cfg.get("raiz") or cfg.get("workspace"), "pacote": pacote,
            "dados": os.path.join(pacote, "dados") if pacote else "",
            "config": dict(cfg.get("bruto") or {}), "hoje": datetime.date.today()}


def _texto(v, n=500):
    return v[:n] if isinstance(v, str) else ""


def conferir(dado, inf):
    """Forma mínima da resposta de montar(). Peça ruim sai com aviso; o resto passa."""
    if not isinstance(dado, dict):
        raise ErroModulo(500, "Esta tela devolveu algo estranho.", ["montar() não devolveu um objeto"])
    avisos = [_texto(a) for a in dado.get("avisos") or [] if isinstance(a, str)][:50]
    alertas = []
    for a in dado.get("alertas") or []:
        if isinstance(a, dict) and a.get("nivel") in NIVEIS and isinstance(a.get("texto"), str):
            alertas.append({"nivel": a["nivel"], "texto": _texto(a["texto"])})
        else:
            avisos.append("um alerta fora do formato foi ignorado")
    abas = []
    for aba in (dado.get("abas") or [])[:MAX_ABAS]:
        if not isinstance(aba, dict) or not isinstance(aba.get("id"), str) or not isinstance(aba.get("blocos"), list):
            avisos.append("uma aba fora do formato foi ignorada")
            continue
        blocos = [b for b in aba["blocos"][:MAX_BLOCOS] if isinstance(b, dict) and isinstance(b.get("tipo"), str)]
        if len(blocos) != len(aba["blocos"][:MAX_BLOCOS]):
            avisos.append("aba %s: bloco sem 'tipo' ignorado" % _texto(aba["id"], 40))
        abas.append(dict(aba, id=_texto(aba["id"], 40), titulo=_texto(aba.get("titulo") or aba["id"], 80),
                         blocos=blocos))
    gerado = dado.get("gerado_em") if isinstance(dado.get("gerado_em"), str) else _agora()
    saida = {"id": inf["id"], "titulo": _texto(dado.get("titulo"), 60) or inf["titulo"], "gerado_em": gerado,
             "alertas": alertas[:MAX_ALERTAS], "abas": abas, "avisos": avisos}
    try:
        json.dumps(saida, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as e:
        raise ErroModulo(500, "Esta tela devolveu algo estranho.", ["resposta não vira JSON: %s" % e])
    return saida


def _rodar_montar(mod, ctx, mid, tempo):
    caixa = {}

    def alvo():
        try:
            caixa["dado"] = mod.montar(ctx)
        except BaseException as e:  # noqa: B902 - um módulo quebrado não derruba o painel
            caixa["erro"] = e

    with _lock:
        t = _rodando.get(mid)
        if t is not None and t.is_alive():
            raise ErroModulo(503, "Esta tela ainda está sendo montada. Tente de novo daqui a pouco.")
        t = threading.Thread(target=alvo, name="modulo-%s" % mid, daemon=True)
        _rodando[mid] = t
    t.start()
    t.join(tempo)
    if t.is_alive():
        raise ErroModulo(500, "Esta tela demorou demais para montar.",
                         ["montar() de %s passou de %d s" % (mid, int(tempo))])
    with _lock:
        _rodando.pop(mid, None)
    if "erro" in caixa:
        e = caixa["erro"]
        raise ErroModulo(500, "Não consegui montar esta tela.",
                         ["%s.montar quebrou: %s: %s" % (mid, type(e).__name__, str(e)[:200])])
    return caixa.get("dado")


def montar(cfg, mid, usar_cache=True, tempo=TEMPO_LIMITE):
    """(código, corpo) de GET /api/modulos/<id>."""
    agora = time.monotonic()
    if usar_cache:
        with _lock:
            item = _cache.get(mid)
        if item and agora - item[0] < TTL:
            return item[1], item[2]
    try:
        mod = carregar(cfg, mid)
        saida = conferir(_rodar_montar(mod, contexto(cfg), mid, tempo), info(mod, mid))
        codigo, corpo = 200, saida
    except ErroModulo as e:
        codigo, corpo = e.codigo, e.corpo()
    if codigo in (200, 500):
        with _lock:
            _cache[mid] = (time.monotonic(), codigo, corpo)
    return codigo, corpo


def listar(cfg, tempo=TEMPO_LIMITE):
    """Corpo de GET /api/modulos: cada módulo habilitado com o número de alertas."""
    saida, avisos = [], []
    if cfg.get("modulos") and not cfg.get("pacote_ok"):
        avisos.append("painel.json lista módulos, mas não achei o pacote do projeto")
    de_plugins, av_plugins = modulos_plugin.ligados(cfg)
    avisos.extend(av_plugins)
    for mid in list(cfg.get("modulos") or []) + list(de_plugins):
        item = {"id": mid, "titulo": mid, "icone": "", "alertas": 0}
        try:
            item.update(info(carregar(cfg, mid), mid))
        except ErroModulo as e:
            avisos.extend(e.avisos or [e.mensagem])
            if e.codigo == 404:
                continue
            saida.append(item)
            continue
        codigo, corpo = montar(cfg, mid, tempo=tempo)
        if codigo == 200:
            item["alertas"] = len(corpo.get("alertas") or [])
        else:
            avisos.append("%s: %s" % (item["titulo"], corpo.get("erro")))
        saida.append(item)
    return {"modulos": saida, "avisos": avisos}


def _rodar_agir(mod, ctx, mid, acao, dados, tempo):
    """agir() numa thread com tempo limite. Trava própria: montar rodando não bloqueia uma ação,
    mas duas ações do mesmo módulo ao mesmo tempo dão 409. O texto da exceção não sai (pode
    trazer o que foi digitado em `dados`); só o nome do tipo."""
    caixa = {}

    def alvo():
        try:
            caixa["dado"] = mod.agir(ctx, acao, dados)
        except BaseException as e:  # noqa: B902 - um módulo quebrado não derruba o painel
            caixa["erro"] = e

    with _lock_agir:
        t = _agindo.get(mid)
        if t is not None and t.is_alive():
            raise ErroModulo(409, "Esta tela ainda está fazendo a ação anterior. Espere terminar.")
        t = threading.Thread(target=alvo, name="modulo-agir-%s" % mid, daemon=True)
        _agindo[mid] = t
    t.start()
    t.join(tempo)
    if t.is_alive():
        raise ErroModulo(503, "Esta ação demorou demais.", ["agir() de %s passou de %d s" % (mid, int(tempo))])
    with _lock_agir:
        _agindo.pop(mid, None)
    if "erro" in caixa:
        raise ErroModulo(500, "Não consegui fazer esta ação.",
                         ["%s.agir quebrou: %s" % (mid, type(caixa["erro"]).__name__)])
    return caixa.get("dado")


def agir(cfg, mid, acao, dados, tempo=TEMPO_LIMITE):
    """(código, corpo) de POST /api/modulos/<id>/acao. `dados` vai intacto para agir()."""
    try:
        mod = carregar(cfg, mid)
        if not callable(getattr(mod, "agir", None)):
            raise ErroModulo(404, "Esta tela não tem ações.")
        i = getattr(mod, "INFO", None)
        acoes = i.get("acoes") if isinstance(i, dict) else None
        acoes = [a for a in acoes if isinstance(a, str)] if isinstance(acoes, list) else []
        if not isinstance(acao, str) or acao not in acoes:
            raise ErroModulo(400, "Esta tela não tem essa ação.")
        if not isinstance(dados, dict):
            raise ErroModulo(400, "Os dados da ação precisam ser um objeto.")
        resultado = _rodar_agir(mod, contexto(cfg), mid, acao, dados, tempo)
        if not isinstance(resultado, dict):
            raise ErroModulo(500, "Esta ação devolveu algo estranho.", ["agir() não devolveu um objeto"])
        try:
            json.dumps(resultado, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError):
            raise ErroModulo(500, "Esta ação devolveu algo estranho.", ["resposta de agir() não vira JSON"])
    except ErroModulo as e:
        return e.codigo, e.corpo()
    with _lock:
        _cache.pop(mid, None)  # a próxima leitura já mostra o efeito da ação
    return 200, {"ok": True, "resultado": resultado}


def negar_dos_modulos(cfg):
    """(regras, avisos): INFO["negar"] de todos os módulos habilitados, para toda sessão disparada.

    Só importa o módulo e lê INFO (montar() não roda). Lista de textos no formato do "negar" das
    ações; forma errada é ignorada com aviso. O núcleo só junta os textos declarados.
    """
    regras = []
    de_plugins, avisos = modulos_plugin.ligados(cfg)
    for mid in list(cfg.get("modulos") or []) + list(de_plugins):
        try:
            mod = carregar(cfg, mid)
        except ErroModulo as e:
            avisos.append("módulo %s não carregou; as regras de negar dele não valem: %s"
                          % (mid, "; ".join(e.avisos) or e.mensagem))
            continue
        i = getattr(mod, "INFO", None)
        if not isinstance(i, dict) or "negar" not in i:
            continue
        try:
            trv = travas.validar_travas({"negar": i["negar"]})
            if trv["regras_negar"]:
                raise ValueError("só regras de permissão em texto")
        except ValueError as e:
            avisos.append("módulo %s: INFO['negar'] ignorado (%s)" % (mid, e))
            continue
        regras += [r for r in trv["negar"] if r not in regras]
    return regras, avisos


def esquecer():
    with _lock:
        _cache.clear()
