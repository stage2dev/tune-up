"""Attention QA of a reel source (qa_atencao.checar_video): scenes, hook, words per scene, visual device of the
key scenes, legibility, type floor, brand colors, end card, layout variety, transitions, tics and numbers.
Imported, never run.

A scene is the clips `s<N>_<papel>` that share one data-start/data-duration; thresholds live in
qa_atencao.py. Python 3.9+, standard library plus qa_atencao.py and qa_css.py.
"""
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_atencao as qa  # noqa: E402
import qa_css  # noqa: E402
import qa_quadros  # noqa: E402
import qa_script  # noqa: E402

CLIP_RE = re.compile(r"s([1-9]\d*)_([a-z0-9]+)\Z")
TR_RE = re.compile(r"tr([1-9]\d*)\Z")
NUM_RE = re.compile(r"[\d.]+%?\Z")
# The cover and the end card are read from the feed thumbnail: their headline is big and fills the width.
TITULO_GRANDE_PX, TITULO_LARGURA, LARGURA_UTIL, LETRA_EM = 120, 0.7, 900, 0.55
FILTRO_RE = re.compile(r"(?<![\w-])(?:filter|backdrop-filter)\s*:\s*(?!\s)(?!none\b)[^;}]+", re.I)
COBRE_MAX = 0.15  # seconds a transition may cover the whole frame (one color) before it reads as a blink
CONECTORES = {"no", "na", "nos", "nas", "pelo", "pela", "pelos", "pelas", "em", "e", "ou", "via", "de", "do", "da"}
IDENTIDADE_RE = re.compile(r"(?:translate(?:x|y|z|3d)?|rotate(?:z)?)\(\s*0(?:px|%|deg)?\s*(?:,\s*0(?:px|%|deg)?\s*)*\)"
                           r"|scale\(\s*1(?:\.0+)?\s*\)|none")


def _tempo(el):
    try:
        return float(el["attrs"]["data-start"]), float(el["attrs"]["data-duration"])
    except (KeyError, ValueError):
        return None


def _papel(clip):
    m = CLIP_RE.match(clip["id"])
    return m.group(2) if m else ""


def cenas(clips, duracao):
    """({N: (start, duration, [clips])}, problems) by the scene rule of the convention."""
    out, grupos = [], {}
    for c in clips:
        m = CLIP_RE.match(c["id"])
        if m:
            grupos.setdefault(int(m.group(1)), []).append(c)
        elif qa_css.texto_de(c) and not c["id"].startswith("deco"):
            out.append("clip de texto sem id s<N>_<papel>: %s" % (c["id"] or qa_css.texto_de(c)[:30]))
    achadas, t = {}, 0.0
    for n in sorted(grupos):
        tempos = {_tempo(c) for c in grupos[n]}
        if None in tempos or len(tempos) != 1:
            out.append("cena %d: os clips não têm o mesmo data-start/data-duration" % n)
        ini, dur = min(tempos - {None}) if tempos - {None} else (t, 0.0)
        achadas[n] = (ini, dur, grupos[n])
        if abs(ini - t) > qa.FOLGA:
            out.append("cena %d começa em %g s (esperado %g s: cenas contíguas a partir de 0)" % (n, ini, t))
        if dur < qa.CENA_MIN:
            out.append("cena %d com %g s (mínimo %g)" % (n, dur, qa.CENA_MIN))
        t = ini + dur
    if not achadas:
        return achadas, out + ["nenhuma cena s<N>_*"]
    if sorted(achadas) != list(range(1, len(achadas) + 1)):
        out.append("cenas numeradas com buraco: %s" % sorted(achadas))
    if abs(t - duracao) > qa.FOLGA:
        out.append("cenas somam %g s (vídeo de %g s)" % (t, duracao))
    faixa = qa.CENAS.get(int(round(duracao)))
    if faixa and not faixa[0] <= len(achadas) <= faixa[1]:
        out.append("%d cenas (para %g s: de %d a %d)" % (len(achadas), duracao, faixa[0], faixa[1]))
    lista = [achadas[n] for n in sorted(achadas)]
    if lista[0][1] > qa.CENA1_MAX:
        out.append("cena 1 com %g s (máximo %g)" % (lista[0][1], qa.CENA1_MAX))
    if lista[-1][1] < qa.CENA_ULTIMA_MIN:
        out.append("última cena com %g s (mínimo %g)" % (lista[-1][1], qa.CENA_ULTIMA_MIN))
    return achadas, out


def _fechado(v):
    """A clip-path that hides something: anything but none or an inset() of zeros."""
    m = re.fullmatch(r"inset\(([^)]*)\)", v)
    return v != "none" and not (m and all(qa_css.zero(x) for x in m.group(1).split(" round ")[0].split()))


def estado_inicial(doc, el):
    """Why a clip is not fully visible at its first frame: its own rules plus the 0%/from step of its animation."""
    decl = qa_css.decls(doc, el, qa_css.amplo(el))
    for nome in qa_css.nomes_animacao(decl):
        decl = decl + [d for passos, ds in doc["quadros"].get(nome, []) if "0%" in passos for d in ds]
    out = []
    for k, v in decl:
        low = " ".join(v.lower().split())
        if k == "opacity" and NUM_RE.match(low) and float(low.rstrip("%")) / (100 if "%" in low else 1) < 1:
            out.append("%s com opacity %s no início" % (el["id"], v))
        elif (k, low) in (("visibility", "hidden"), ("display", "none")) or (k == "clip-path" and _fechado(low)):
            out.append("%s com %s: %s no início" % (el["id"], k, v))
    return out


def _check_gancho(doc, achadas, clips, por_id):
    texto = lambda i: qa_css.texto_de(por_id[i]) if i in por_id else ""  # noqa: E731
    out = [] if texto("s1_titulo") else ["cena 1 sem s1_titulo com texto"]
    capa = " ".join(x for x in (texto("s1_titulo"), texto("s1_destaque")) if x)
    if len(capa) > qa.TITULO_CHARS:
        out.append("gancho com %d caracteres (máximo %d): %s" % (len(capa), qa.TITULO_CHARS, capa))
    for c in (achadas[1][2] if 1 in achadas else []):
        if qa_css.texto_de(c):
            out += estado_inicial(doc, c)
    for c in clips:
        if (c["id"] == "logo" or c["id"].endswith(("_logo", "_marca"))) and (_tempo(c) or (1, 0))[0] < 0.001:
            out.append("%s visível em t=0 (logo e nome da marca só da cena 2 em diante)" % c["id"])
    return qa.resultado("gancho", out)


def _check_cta(doc, achadas, por_id, pasta):
    if not achadas:
        return qa.resultado("cta_final", ["nenhuma cena"])
    ult, out = max(achadas), []
    for papel in ("titulo", "contato"):
        el = por_id.get("s%d_%s" % (ult, papel))
        if el is None or not qa_css.texto_de(el):
            out.append("última cena sem s%d_%s com texto" % (ult, papel))
            continue
        decl = qa_css.decls(doc, el, qa_css.amplo(el))
        if not qa_css.zero(qa_css.ultimo(decl, "border-radius")):
            out.append("%s com border-radius" % el["id"])
        fundo = [v for k, v in decl if k in ("background", "background-color", "background-image")]
        if fundo and fundo[-1].strip().lower() not in ("none", "transparent"):
            out.append("%s com fundo próprio" % el["id"])
    contato = por_id.get("s%d_contato" % ult)
    escrito = qa_css.texto_de(contato) if contato else ""
    erro = qa.briefing_ausente(pasta)
    if erro:
        out.append(erro)
    elif not contato_ok(escrito, qa.fatos(pasta)):
        out.append("contato '%s' não está no briefing nem na marca: use o canal como está escrito ('pelo WhatsApp', "
                   "o telefone, o @), com ou sem 'link na bio'" % escrito)
    return qa.resultado("cta_final", out + qa.faltam_prazos(doc["texto"], pasta))


def contato_ok(escrito, fatos):
    """The contact names only what the facts say: 'link na bio' plus channel words, @handles, sites and phone
    digits found in the briefing or the brand (connectors like 'pelo', 'no' are free)."""
    resto = " ".join(escrito.casefold().split()).replace("link na bio", " ")
    digitos = re.sub(r"\D", "", resto)
    if digitos and digitos not in fatos[0]:
        return False
    for w in re.findall(r"@[\w.]+|[^\W\d_]+", resto):
        if w not in CONECTORES and not re.search(r"(?<!\w)%s(?!\w)" % re.escape(w.rstrip(".")), fatos[1]):
            return False
    return True


def _check_layouts(doc, achadas, duracao):
    ns = sorted(achadas)
    layouts = [qa.layout(doc, "s%d_titulo" % n, qa.LAYOUTS_VIDEO) for n in ns]
    out = ["cena %d: s%d_titulo sem exatamente um l-* válido (%s)" % (n, n, " ".join(qa.LAYOUTS_VIDEO))
           for n, lay in zip(ns, layouts) if not lay]
    out += qa.sequencia(["cena %d" % n for n in ns], layouts)
    precisa, distintos = (2 if duracao <= 10 + qa.FOLGA else 3), len(set(layouts) - {None})
    if distintos < precisa:
        out.append("%d arranjos distintos (mínimo %d para %g s)" % (distintos, precisa, duracao))
    return qa.resultado("sequencia_layout", out)


def _cobre(decl, largura, altura):
    """True when a frame-sized transition step covers the whole frame: no move and no clip-path cut."""
    transf = qa_css.ultimo(decl, "transform")
    if transf and IDENTIDADE_RE.sub("", transf.lower()).strip():
        return False
    clip = (qa_css.ultimo(decl, "clip-path") or "none").strip().lower()
    m = re.fullmatch(r"circle\(\s*([\d.]+)%(?:\s+at\s+([\d.]+)%\s+([\d.]+)%)?\s*\)", clip)
    if m:
        raio = float(m.group(1)) / 100 * math.hypot(largura, altura) / math.sqrt(2)
        cx, cy = (float(m.group(2) or 50) / 100 * largura, float(m.group(3) or 50) / 100 * altura)
        return raio >= max(math.hypot(cx - x, cy - y) for x in (0, largura) for y in (0, altura))
    return clip == "none" or not _fechado(clip)


def tempo_coberto(doc, el, largura=1080.0, altura=1920.0):
    """Seconds a transition clip covers the whole frame (consecutive keyframe steps that both cover it)."""
    proprio = qa_css.decls(doc, el, qa_css.amplo(el))
    w = qa_css.medida(qa_css.ultimo(proprio, "width"), largura) or 0
    h = qa_css.medida(qa_css.ultimo(proprio, "height"), altura) or 0
    nomes, dur = qa_css.nomes_animacao(proprio), (_tempo(el) or (0, 0))[1]
    if w < largura or h < altura or not nomes:
        return 0.0
    passos = []
    for sels, ds in doc["quadros"].get(nomes[0], []):
        for sel in sels:
            try:
                passos.append((float(sel.rstrip("%")) / 100, _cobre(proprio + ds, largura, altura)))
            except ValueError:
                pass
    passos.sort()
    return sum((b[0] - a[0]) * dur for a, b in zip(passos, passos[1:]) if a[1] and b[1])


def _check_transicoes(doc, clips, cortes):
    trs = sorted((c for c in clips if TR_RE.match(c["id"])), key=lambda c: (_tempo(c) or (0, 0))[0])
    out, nomes = ([] if trs else ["nenhuma transição tr<N>"]), []
    for c in trs:
        ini, dur = _tempo(c) or (0.0, 0.0)
        if not qa.TRANSICAO[0] <= dur <= qa.TRANSICAO[1]:
            out.append("%s com %g s (de %g a %g)" % (c["id"], dur, qa.TRANSICAO[0], qa.TRANSICAO[1]))
        if not any(abs(ini + dur / 2 - t) <= qa.FOLGA for t in cortes):
            out.append("%s não está centrada num corte (%s)" % (c["id"], ", ".join("%g" % t for t in cortes)))
        nomes.append((qa_css.nomes_animacao(qa_css.decls(doc, c, qa_css.amplo(c))) or [""])[0])
        coberto = tempo_coberto(doc, c, *qa.tamanho_quadro(doc))
        if coberto > COBRE_MAX + 1e-9:
            out.append("%s cobre a tela inteira de uma cor por %.2f s (máximo %g s): parece uma piscada; use uma "
                       "transição que não cubra tudo (padroes-cena.md)" % (c["id"], coberto, COBRE_MAX))
    out += ["%s e %s com a mesma animação %s" % (trs[i - 1]["id"], trs[i]["id"], nomes[i])
            for i in range(1, len(trs)) if nomes[i] == nomes[i - 1]]
    if trs and len(set(nomes) - {""}) < 2:
        out.append("transições com menos de 2 animações diferentes")
    return qa.resultado("transicoes", out)


def _check_recurso(doc, achadas, clips):
    """Scene 1, the payoff (second to last) and the end card each show one visual device (qa.recurso); a
    persistent `deco<N>` shape counts for every scene."""
    largura, altura = qa.tamanho_quadro(doc)
    deco = [c for c in clips if c["id"].startswith("deco")]
    ns = sorted(achadas)
    out = []
    for n in sorted({ns[0], ns[-2], ns[-1]} if len(ns) >= 3 else set(ns)):  # no scene: `cenas` already fails
        if not qa.recursos(doc, achadas[n][2] + deco, largura, altura):
            out.append("cena %d %s" % (n, qa.SEM_RECURSO))
    return qa.resultado("recurso_visual", out)


def _check_titulos_grandes(doc, achadas, por_id):
    """`titulo_largura`: the cover's and the end card's `_titulo` are 120 px or more and their text, at an
    average letter of .55 em, fills 70% or more of the 900 px safe width (the declared width caps it)."""
    out = []
    for n in sorted({min(achadas), max(achadas)}) if achadas else []:
        el = por_id.get("s%d_titulo" % n)
        if el is None or "l-numero" in el["classes"]:
            continue
        decl = qa_css.decls(doc, el, qa_css.exato(el))
        px = qa_css.valor_px(qa_css.ultimo(decl, "font-size")) or 0
        largura = 0
        for linha in (el, por_id.get("s%d_destaque" % n)):  # the highlight line is part of the same headline
            if linha is None:
                continue
            d = qa_css.decls(doc, linha, qa_css.exato(linha))
            caixa = qa_css.medida(qa_css.ultimo(d, "width"), 1080) or LARGURA_UTIL
            largura = max(largura, min(caixa, len(qa_css.texto_de(linha)) * LETRA_EM
                                       * (qa_css.valor_px(qa_css.ultimo(d, "font-size")) or 0)))
        if px < TITULO_GRANDE_PX:
            out.append("s%d_titulo com %g px (capa e cartão final: %d px ou mais)" % (n, px, TITULO_GRANDE_PX))
        elif largura < TITULO_LARGURA * LARGURA_UTIL:
            out.append("s%d_titulo ocupa ~%d px de %d (mínimo %d%%): letra maior ou mais texto do briefing"
                       % (n, largura, LARGURA_UTIL, TITULO_LARGURA * 100))
    return qa.resultado("titulo_largura", out)


def _check_script(fonte, clips, achadas):
    html = qa_css.ler_arquivo(os.path.join(fonte, "index.html")) or ""
    gancho = {c["id"] for c in (achadas[1][2] if 1 in achadas else []) if qa_css.texto_de(c)}
    ids = re.findall(r"""\bid\s*=\s*["']([\w-]+)["']""", html)
    out = qa_script.checar(html, ids, gancho, {c["id"]: qa_css.texto_de(c) for c in clips if c["id"]})
    filtros = FILTRO_RE.findall(qa_css.COMENTARIO_RE.sub("", " ".join(re.findall(r"<style[^>]*>(.*?)</style>", html,
                                                                                   re.S | re.I))))
    filtros += re.findall(r"""style\s*=\s*["'][^"']*\bfilter\s*:[^"']*""", html, re.I)
    out += ["filtro CSS no reel (%s): o desfoque e a sombra por filtro não saem iguais em dois renders; sombra = "
            "uma forma deslocada" % f.strip()[:40] for f in filtros]
    return qa.resultado("script_seguro", out)


def checar_video(fonte, duracao, engine):
    """estrategia, estilo, cenas, gancho, palavras_cena, recurso_visual, legibilidade, fonte_minima, cores_marca,
    cta_final, sequencia_layout, transicoes (only with engine "hyperframes"), tiques, numeros, marca,
    titulo_largura, oferta_destaque, preco_destaque, molde, script_seguro (the motion script and no CSS filter),
    folha_limpa, texto_inteiro, heroi_final (qa_quadros.py)."""
    pasta = os.path.dirname(os.path.abspath(fonte))
    doc = qa_css.ler_fonte(fonte)
    if doc is None:
        return [qa.check_estrategia(pasta), qa.resultado("cenas", ["index.html não encontrado em %s" % fonte])]
    clips = [e for e in doc["elementos"] if "clip" in e["classes"]]
    achadas, prob_cenas = cenas(clips, duracao)
    por_id = {c["id"]: c for c in clips if c["id"]}
    excesso, alvos = [], []
    for n in sorted(achadas):
        _, dur, cs = achadas[n]
        total = sum(qa.palavras(qa_css.texto_de(c)) for c in cs if _papel(c) != "marca")  # the name is not read
        limite = max(6, int(math.floor(3 * dur + 1e-9)))
        if total > limite:
            excesso.append("cena %d: %d palavras em %g s (máximo %d)" % (n, total, dur, limite))
    for c in clips:
        if qa_css.texto_de(c):
            piso = qa.VIDEO_TITULO_MIN if _papel(c) in ("titulo", "destaque") else qa.VIDEO_OUTRO_MIN
            alvos.append((c["id"] or "clip sem id", c, qa_css.exato(c), piso))
    checks = [qa.check_estrategia(pasta), qa.resultado("cenas", prob_cenas),
              _check_gancho(doc, achadas, clips, por_id), qa.resultado("palavras_cena", excesso),
              _check_recurso(doc, achadas, clips),
              qa.check_legibilidade(doc, clips, [c for c in clips if _papel(c) in ("titulo", "destaque")]),
              qa.check_fonte_minima(doc, qa.VIDEO_OUTRO_MIN, alvos), qa.check_cores(doc, fonte),
              _check_cta(doc, achadas, por_id, pasta), _check_layouts(doc, achadas, duracao)]
    if engine == "hyperframes":
        cortes = [achadas[n][0] for n in sorted(achadas)][1:]
        checks.append(_check_transicoes(doc, clips, cortes))
    ultima = " ".join(qa_css.texto_de(c) for c in achadas[max(achadas)][2]) if achadas else ""
    vendem = [qa_css.texto_de(c) for c in clips if _papel(c) in ("titulo", "destaque", "selo")]
    falados = [qa_css.texto_de(c) for c in clips if _papel(c) in ("titulo", "destaque")]
    raiz = next((e for e in doc["elementos"] if e["id"] == "root"), None)
    checks.append(qa.check_estilo(pasta, (raiz or {"attrs": {}})["attrs"].get("data-estilo", "")))
    return checks + [qa.check_tiques(doc["texto"]), qa.check_numeros(doc["texto"], pasta),
                     qa.check_marca(ultima, pasta, "na última cena (clip s<N>_marca)"),
                     _check_titulos_grandes(doc, achadas, por_id), qa.check_oferta(vendem, pasta),
                     qa.check_preco(falados, pasta, "um _titulo ou _destaque, carimbado"),
                     qa.check_molde(falados, pasta), _check_script(fonte, clips, achadas)] + _quadros(fonte, doc, clips,
                                                                                                    duracao)


def _quadros(fonte, doc, clips, duracao):
    """folha_limpa, texto_inteiro, heroi_final (qa_quadros.py): the defects that kept coming back."""
    html = qa_css.ler_arquivo(os.path.join(fonte, "index.html")) or ""
    return [qa_quadros.check_folha(doc, clips, duracao), qa_quadros.check_texto_inteiro(html, clips),
            qa_quadros.check_heroi_final(doc, html, clips)]
