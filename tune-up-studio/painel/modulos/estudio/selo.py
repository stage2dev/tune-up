"""Selo de uma peça do estúdio, recalculado pelo servidor.

Só checagens sem navegador, com as funções de scripts/qa_imagem.py e qa_video.py (importadas por
caminho de arquivo): tamanho do PNG, ffprobe do MP4, contagem de `data-layout-allow*`, ausência de
gsap, lint de rede e MP4/PNG não mais velho que a fonte. O servidor nunca abre no Chrome um HTML
escrito pela sessão. O final.json (post) / qa.json (vídeo) da sessão só baixa o selo: vermelho ou
ausente = vermelho; verde não sobe nada (é o único lugar onde o check com Chrome rodou). Post: 1 quadro;
carrossel: de 2 até os quadros pedidos; legenda (copy.md) obrigatória. Anúncio: cada peça a<N> do plano de
scripts/anuncio.py no tamanho dela, textos.json nos limites com a URL pedida e a planilha de export/ igual à
que o script monta dos textos (tudo Paused). Atalho, FIFO ou arquivo grande
demais dentro da peça = vermelho (nada é seguido nem lido). O resultado fica em cache pela assinatura
(nome, tamanho e mtime de tudo na pasta). Python 3.9, só biblioteca padrão.
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
MAX_JSON = 1024 * 1024
MAX_LEGENDA = 20000
MAX_CACHE = 200
TEMPO_FFPROBE = 8  # a tela tem 20 s para montar; um MP4 que trava o ffprobe fica vermelho
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
                for nome in ("qa_imagem", "qa_video", "anuncio"):
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


def script_anuncio():
    _scripts()
    return _qa["anuncio"]


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


def _pasta_real(caminho):
    try:
        return stat.S_ISDIR(os.lstat(caminho).st_mode)
    except OSError:
        return False


def legenda(pasta):
    """Texto do copy.md da peça (arquivo comum pequeno, não vazio) ou None."""
    caminho = os.path.join(pasta, "copy.md")
    if comum(caminho, MAX_LEGENDA):
        return None
    with open(caminho, encoding="utf-8", errors="replace") as f:
        return f.read().strip() or None


def _sessao(qi, caminho):
    """A conferência que a sessão gravou só derruba: verde só se existe e diz PRONTO."""
    ruim = comum(caminho, MAX_JSON)
    d, erro = (None, ruim) if ruim else qi.load_json(caminho)
    linha = str((d or {}).get("linha") or "")
    ok = d is not None and d.get("ok") is True and linha.startswith("PRONTO")
    return qi.result("conferencia_da_sessao", ok, [erro or linha[:300] or "sem linha final"])


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
        return {"ok": False, "linha": "PRECISA DO SEU OLHO: formato desconhecido", "arquivos": [], "falhas": ["formato"]}
    nomes = sorted((int(m.group(1)), n) for n in os.listdir(pasta) for m in [RE_QUADRO.match(n)] if m)
    arquivos = [_quadro(qi, pasta, n, n + ".png", largura, altura) for _, n in nomes]
    extra = [_sessao(qi, os.path.join(pasta, "final.json"))]
    try:
        maximo = max(2, int(params.get("quadros") or 10))
    except (TypeError, ValueError):
        maximo = 10
    carrossel = str(params.get("formato") or "").startswith("carrossel")
    if not (2 <= len(arquivos) <= maximo if carrossel else len(arquivos) == 1):
        extra.append(qi.result("quadros", False, ["%d quadros" % len(arquivos)]))
    if legenda(pasta) is None:
        extra.append(qi.result("legenda", False, ["falta o copy.md"]))
    extra = [c["name"] for c in extra if not c["ok"]]
    verdes = sum(1 for a in arquivos if not a["falhas"])
    ok = bool(arquivos) and verdes == len(arquivos) and not extra
    if ok:
        linha = "PRONTO: %d de %d quadros verdes" % (verdes, verdes)
    else:
        linha = "PRECISA DO SEU OLHO: %d de %d verdes, %s" % (verdes, len(arquivos), "; ".join(
            ["%s: %s" % (a["nome"][:-4], ", ".join(a["falhas"])) for a in arquivos if a["falhas"]] + extra)
            or "nenhum quadro")
    falhas = [f for a in arquivos for f in a["falhas"]] + extra + ([] if arquivos else ["quadros"])
    return {"ok": ok, "linha": linha, "arquivos": arquivos, "falhas": list(dict.fromkeys(falhas))}


def _quadro(qi, pasta, n, nome, largura, altura):
    """{"c", "nome", "falhas"} do PNG <n>/snap/... no tamanho pedido, com as checagens de texto da fonte."""
    png, fonte = os.path.join(pasta, n, STILL), os.path.join(pasta, n, "fonte")
    rel = "/".join([n, "snap", "frame-00-at-0s.png"])
    if not (_pasta_real(os.path.join(pasta, n)) and _pasta_real(os.path.join(pasta, n, "snap"))):
        return {"c": rel, "nome": nome, "falhas": ["atalho"]}  # atalho no meio do caminho: nada é lido
    ruim = comum(png, MAX_PNG)
    checks = [qi.result("png", False, [ruim])] if ruim else [qi.check_png(png, largura, altura)]
    checks += _fonte(qi, fonte, True)
    if not ruim and not _fonte_ruim(fonte):
        checks.append(qi.result("png_fresh", os.path.getmtime(png) >= qi.newest_mtime(fonte),
                                ["a fonte mudou depois do PNG"]))
    return {"c": rel, "nome": nome, "falhas": [c["name"] for c in checks if not c["ok"]]}


def textos(pasta, params):
    """(textos.json conferido, None) ou (None, nome da falha); a URL tem de ser a pedida no formulário."""
    an = script_anuncio()
    plataforma = (params or {}).get("plataforma")
    if plataforma not in an.PLANOS or comum(os.path.join(pasta, "textos.json"), MAX_JSON):
        return None, "plataforma" if plataforma not in an.PLANOS else "textos"
    t, erro = an.ler_textos(pasta)
    if erro or an.conferir(t, plataforma):
        return None, "textos"
    return (t, None) if t.get("url") == (params or {}).get("url") else (None, "url")


def _anuncio(qi, pasta, params):
    an = script_anuncio()
    try:
        plano = an.plano(params.get("plataforma"))
    except (OSError, ValueError, KeyError, StopIteration):
        return {"ok": False, "linha": "PRECISA DO SEU OLHO: plataforma desconhecida", "arquivos": [],
                "export": [], "falhas": ["plataforma"]}
    arquivos = [_quadro(qi, pasta, p["id"], p["nome"], p["largura"], p["altura"]) for p in plano["pecas"]]
    for a, p in zip(arquivos, plano["pecas"]):  # Google: imagem limpa; 9:16: texto só na zona segura
        fonte = os.path.join(pasta, p["id"], "fonte")
        if "atalho" not in a["falhas"] and not _fonte_ruim(fonte) and an.checar_peca(
                fonte, plano["plataforma"], p["largura"], p["altura"]):
            a["falhas"].append("sem_texto" if plano["plataforma"] == "google" else "zona_segura")
    extra = [] if _sessao(qi, os.path.join(pasta, "final.json"))["ok"] else ["conferencia_da_sessao"]
    t, falha = textos(pasta, params)
    planilha = "/".join(["export", plano["export"]])
    if falha:
        extra.append(falha)
    elif comum(os.path.join(pasta, "export", plano["export"]), MAX_JSON) or not _pasta_real(
            os.path.join(pasta, "export")) or an.conferir_export(pasta, plano["plataforma"], t):
        extra.append("export")  # falta, é atalho, ou não é exatamente a que o script monta dos textos
    verdes = sum(1 for a in arquivos if not a["falhas"])
    ok = verdes == len(arquivos) and not extra
    linha = "PRONTO: %d de %d peças verdes, textos e planilha ok" % (verdes, verdes) if ok else \
        "PRECISA DO SEU OLHO: %d de %d verdes, %s" % (verdes, len(arquivos), "; ".join(
            ["%s: %s" % (a["nome"], ", ".join(a["falhas"])) for a in arquivos if a["falhas"]] + extra))
    falhas = [f for a in arquivos for f in a["falhas"]] + extra
    return {"ok": ok, "linha": linha, "arquivos": arquivos, "falhas": list(dict.fromkeys(falhas)),
            "export": [{"c": planilha, "nome": plano["export"]}], "textos": t}


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
            dado = qv.probe(video, ffprobe, TEMPO_FFPROBE)
            checks += qv.stream_checks(dado, video, largura, altura, duracao, 30.0)
        except (ValueError, OSError) as e:
            checks.append(qi.result("probe", False, [str(e)[:300]]))
        else:
            tag = qv.check_reserve_tag(dado)
            if VIDEOS[acao] == "reserve":
                checks.append(tag)
            elif tag["ok"]:
                checks.append(qi.result("engine_hyperframes", False, ["o MP4 é da reserva em slides"]))
    checks += _fonte(qi, fonte, False) + [_sessao(qi, os.path.join(pasta, "qa.json"))]
    if not ruim and not _fonte_ruim(fonte):
        checks.append(qv.check_fresh(video, fonte, None))
    falhas = [c["name"] for c in checks if not c["ok"]]
    linha = "PRECISA DO SEU OLHO: %s" % ", ".join(falhas) if falhas else "PRONTO: vídeo verde"
    return {"ok": not falhas, "linha": linha, "falhas": falhas,
            "arquivos": [{"c": "video.mp4", "nome": "video.mp4", "falhas": falhas}]}


def tipo(acao):
    return "post" if acao == "estudio.post" else "video" if acao in VIDEOS else \
        "anuncio" if acao == "estudio.anuncio" else None


def calcular(pasta, acao, params):
    """{"ok", "linha", "falhas" (nomes das checagens vermelhas), "arquivos": [{"c" (relativo à pasta), "nome", "falhas"}]};
    em cache pela assinatura."""
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
    elif tipo(acao) == "anuncio":
        selo = _anuncio(qi, pasta, params or {})
    else:
        selo = {"ok": False, "linha": "PRECISA DO SEU OLHO: ação desconhecida", "arquivos": [], "falhas": ["acao"]}
    with _lock:
        if len(_cache) >= MAX_CACHE:
            _cache.clear()
        _cache[pasta] = (chave, selo)
    return selo


def esquecer():
    with _lock:
        _cache.clear()
