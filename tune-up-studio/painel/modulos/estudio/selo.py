"""Selo de uma peça do estúdio, recalculado pelo servidor.

Só checagens sem navegador, com as funções de scripts/qa_imagem.py e qa_video.py (importadas por
caminho de arquivo): tamanho do PNG, ffprobe do MP4, contagem de `data-layout-allow*`, ausência de
gsap, lint de rede e MP4/PNG não mais velho que a fonte. O servidor nunca abre no Chrome um HTML
escrito pela sessão, e o qa.json / final.json da sessão não decidem nada aqui. Atalho, FIFO ou
arquivo grande demais dentro da peça = vermelho (nada é seguido nem lido). O resultado fica em
cache pela assinatura (nome, tamanho e mtime de tudo na pasta). Python 3.9, só biblioteca padrão.
"""
import importlib.util
import json
import os
import re
import shutil
import stat
import sys
import threading

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))), "scripts")
STILL = os.path.join("snap", "frame-00-at-0s.png")
RE_QUADRO = re.compile(r"^q([1-9]\d{0,2})$")
PULAR = {".hyperframes", "node_modules", ".git"}  # o mesmo que o QA pula na fonte
MAX_FONTE = 20 * 1024 * 1024
MAX_PNG = 50 * 1024 * 1024  # o QA lê o PNG inteiro na memória
MAX_MP4 = 300 * 1024 * 1024
MAX_CACHE = 200
VIDEOS = {"estudio.video": "reserve", "estudio.video-motion": "hyperframes"}
_lock = threading.Lock()
_qa = {}
_cache = {}  # pasta -> (assinatura, selo)


def _scripts():
    """(qa_imagem, qa_video) carregados uma vez por caminho de arquivo; sys.path e sys.modules voltam."""
    with _lock:
        if not _qa:
            antes_path, antes_mod, achados = list(sys.path), set(sys.modules), {}
            try:
                sys.path.insert(0, SCRIPTS)  # qa_video importa qa_imagem e reserva_slides pelo nome
                for nome in ("qa_imagem", "qa_video"):
                    spec = importlib.util.spec_from_file_location("estudio_" + nome, os.path.join(SCRIPTS, nome + ".py"))
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    achados[nome] = mod
            finally:
                sys.path[:] = antes_path
                for n in [n for n in list(sys.modules) if n not in antes_mod]:
                    arq = getattr(sys.modules[n], "__file__", None)
                    if arq and os.path.realpath(arq).startswith(SCRIPTS + os.sep):
                        del sys.modules[n]
            _qa.update(achados)
        return _qa["qa_imagem"], _qa["qa_video"]


def assinatura(pasta):
    """Nome, tipo, tamanho e mtime de tudo na pasta (sem seguir atalho): muda quando algo muda."""
    itens = []
    for raiz, dirs, arqs in os.walk(pasta):
        dirs.sort()
        for n in sorted(dirs + arqs):
            try:
                st = os.lstat(os.path.join(raiz, n))
            except OSError:
                continue
            itens.append((os.path.relpath(os.path.join(raiz, n), pasta), stat.S_IFMT(st.st_mode), st.st_size,
                          st.st_mtime_ns))
    return tuple(itens)


def comum(caminho, limite):
    """Texto do problema, ou None se é arquivo comum (não atalho) de até `limite` bytes."""
    try:
        st = os.lstat(caminho)
    except OSError:
        return "falta %s" % os.path.basename(caminho)
    if not stat.S_ISREG(st.st_mode):
        return "%s não é arquivo comum" % os.path.basename(caminho)
    return "%s grande demais" % os.path.basename(caminho) if st.st_size > limite else None


def _fonte_ruim(fonte):
    """Texto do problema da pasta-fonte (atalho, arquivo especial, grande demais) ou None."""
    try:
        if not stat.S_ISDIR(os.lstat(fonte).st_mode):
            return "fonte não é pasta"
    except OSError:
        return "falta a pasta fonte"
    total = 0
    for raiz, dirs, arqs in os.walk(fonte):
        dirs[:] = [d for d in dirs if d not in PULAR]
        for n in dirs + arqs:
            try:
                st = os.lstat(os.path.join(raiz, n))
            except OSError:
                return "a fonte mudou durante a conferência"
            if stat.S_ISLNK(st.st_mode) or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                return "fonte tem atalho ou arquivo especial (%s)" % n
            total += st.st_size if stat.S_ISREG(st.st_mode) else 0
    return "fonte grande demais" if total > MAX_FONTE else None


def _fonte(qi, fonte, script):
    """Checagens de texto da fonte (as mesmas do QA), ou uma só vermelha se a pasta não é segura."""
    ruim = _fonte_ruim(fonte)
    if ruim:
        return [qi.result("fonte", False, [ruim])]
    allow = qi.scan(fonte, [("layout allow", qi.LAYOUT_ALLOW_RE)])
    out = [qi.result("layout_allow_count", not allow, ["count=%d" % len(allow)] + allow)]
    gsap = qi.scan(fonte, [("gsap", qi.GSAP_RE)])
    out.append(qi.result("no_gsap", not gsap, gsap or ["ok"]))
    rede = qi.scan(fonte, qi.NETWORK_PATTERNS, strip_xmlns=True)
    out.append(qi.result("network_lint", not rede, rede or ["ok"]))
    if script:  # o post é só CSS
        s = qi.scan(fonte, [("script", qi.SCRIPT_RE)])
        out.append(qi.result("no_script", not s, s or ["ok"]))
    return out


def _post(qi, pasta, params):
    try:
        largura, altura = qi.format_size(params.get("formato"))
    except (OSError, ValueError, KeyError, StopIteration):
        return {"ok": False, "linha": "PRECISA DO SEU OLHO: formato desconhecido", "arquivos": []}
    nomes = sorted((int(m.group(1)), n) for n in os.listdir(pasta) for m in [RE_QUADRO.match(n)] if m)
    arquivos = []
    for _, n in nomes:
        png, fonte = os.path.join(pasta, n, STILL), os.path.join(pasta, n, "fonte")
        ruim = comum(png, MAX_PNG)
        checks = [qi.result("png", False, [ruim])] if ruim else [qi.check_png(png, largura, altura)]
        checks += _fonte(qi, fonte, True)
        if not ruim and not _fonte_ruim(fonte):
            checks.append(qi.result("png_fresh", os.path.getmtime(png) >= qi.newest_mtime(fonte),
                                    ["a fonte mudou depois do PNG"]))
        arquivos.append({"c": "/".join([n, "snap", "frame-00-at-0s.png"]), "nome": n + ".png",
                         "falhas": [c["name"] for c in checks if not c["ok"]]})
    verdes = sum(1 for a in arquivos if not a["falhas"])
    ok = bool(arquivos) and verdes == len(arquivos)
    if ok:
        linha = "PRONTO: %d de %d quadros verdes" % (verdes, verdes)
    else:
        linha = "PRECISA DO SEU OLHO: %d de %d verdes, %s" % (verdes, len(arquivos), "; ".join(
            "%s: %s" % (a["nome"][:-4], ", ".join(a["falhas"])) for a in arquivos if a["falhas"]) or "nenhum quadro")
    return {"ok": ok, "linha": linha, "arquivos": arquivos}


def _reels(qi):
    with open(os.path.join(qi.STUDIO, "formatos.json"), encoding="utf-8") as f:
        v = next(e["valores"] for e in json.load(f)["formatos"] if e.get("id") == "instagram-reels-tamanho")
    return int(v["largura"]), int(v["altura"])


def _video(qi, qv, pasta, acao, params):
    video, fonte = os.path.join(pasta, "video.mp4"), os.path.join(pasta, "fonte")
    ffprobe = shutil.which("ffprobe")
    checks = []
    try:
        duracao = float(params.get("duracao"))
        largura, altura = _reels(qi)
    except (TypeError, ValueError, OSError, KeyError, StopIteration):
        checks.append(qi.result("formato", False, ["duração ou tamanho desconhecido"]))
    ruim = comum(video, MAX_MP4)
    if ruim:
        checks.append(qi.result("video", False, [ruim]))
    elif not ffprobe:
        checks.append(qi.result("ffprobe", False, ["ffprobe não está instalado"]))
    elif not checks:
        try:
            dado = qv.probe(video, ffprobe)
            checks += qv.stream_checks(dado, video, largura, altura, duracao, 30.0)
        except (ValueError, OSError) as e:
            checks.append(qi.result("probe", False, [str(e)[:300]]))
        else:
            tag = qv.check_reserve_tag(dado)
            if VIDEOS[acao] == "reserve":
                checks.append(tag)
            elif tag["ok"]:
                checks.append(qi.result("engine_hyperframes", False, ["o MP4 é da reserva em slides"]))
    checks += _fonte(qi, fonte, False)
    if not ruim and not _fonte_ruim(fonte):
        checks.append(qv.check_fresh(video, fonte, None))
    falhas = [c["name"] for c in checks if not c["ok"]]
    linha = "PRECISA DO SEU OLHO: %s" % ", ".join(falhas) if falhas else "PRONTO: vídeo verde"
    return {"ok": not falhas, "linha": linha, "arquivos": [{"c": "video.mp4", "nome": "video.mp4", "falhas": falhas}]}


def tipo(acao):
    return "post" if acao == "estudio.post" else "video" if acao in VIDEOS else None


def calcular(pasta, acao, params):
    """{"ok", "linha", "arquivos": [{"c" (relativo à pasta), "nome", "falhas"}]}; em cache pela assinatura."""
    chave = (acao, json.dumps(params or {}, sort_keys=True, ensure_ascii=False), assinatura(pasta))
    with _lock:
        item = _cache.get(pasta)
        if item and item[0] == chave:
            return item[1]
    qi, qv = _scripts()
    if tipo(acao) == "post":
        selo = _post(qi, pasta, params or {})
    elif tipo(acao) == "video":
        selo = _video(qi, qv, pasta, acao, params or {})
    else:
        selo = {"ok": False, "linha": "PRECISA DO SEU OLHO: ação desconhecida", "arquivos": []}
    with _lock:
        if len(_cache) >= MAX_CACHE:
            _cache.clear()
        _cache[pasta] = (chave, selo)
    return selo


def esquecer():
    with _lock:
        _cache.clear()
