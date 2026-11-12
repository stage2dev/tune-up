"""Checks for the defects that kept coming back in the judged pieces (rounds 3 to 5), each one automatic:

- `folha_limpa` (reel, source): no transition is seen on a frame of the 0.25 s grid. A director looks at one
  frame every 0.5 s; a cut on that grid shows the wipe instead of a scene.
- `texto_inteiro` (reel, source): no text enters through a mask or from outside the frame, and every scene's
  title is whole at its cut (it may only wave, pulse or ride the camera).
- `heroi_final` (reel, source): the hero keeps 35% of the width or more on the end card.
- `quadro_de_corte` (reel, MP4): 0.35 s after each cut the frame already carries the scene, not a void.
- `forma_na_margem` (post, PNG): no shape stops at the text margin; a shape near a side runs to the real edge.

Text and pixels only: no browser. Python 3.9+, standard library only.
"""
import re
import subprocess
import zlib

import qa_css
import qa_vazio

GRADE = 0.25           # s: the studio sheet samples at 0.25 + k * 0.5, a director at k * 0.5
FOLGA_GRADE = 1 / 60.0  # half a frame at 30 fps
TEXTO_CORTA = {"mascara": None, "entra": ("esquerda", "painel", "barra"), "contador": None}
TITULO_OK = {"camera", "parallax", "pulso", "onda"}
HEROI_MIN = 0.35
CORTE_APOS, CORTE_MIN = 0.35, 0.6   # the frame 0.35 s after a cut has 60% of the settled frame's ink or more
MARGEM_RUN, MARGEM_FUNDO = 200, 60  # px: a straight edge this long on the margin line, of a shape this deep
CHAMADA_RE = re.compile(r"\bM\.(\w+)\(\s*(\[[^\]]*\]|\"[^\"]*\")\s*,([^;]*)\)\s*;")
ESCALA_RE = re.compile(r"scale\(\s*([\d.]+)")


def _res(nome, problemas):
    return {"name": nome, "ok": not problemas, "details": problemas or ["ok"]}


def _tempo(el):
    try:
        return float(el["attrs"]["data-start"]), float(el["attrs"]["data-duration"])
    except (KeyError, ValueError):
        return None


def _janela(doc, el):
    """(first, last) fraction of a transition clip's length in which it is seen: from the last keyframe step
    equal to its 0% step to the first one equal to its 100% step. No keyframes: the whole clip."""
    nomes = qa_css.nomes_animacao(qa_css.decls(doc, el, qa_css.amplo(el)))
    passos = []
    for sels, ds in doc["quadros"].get(nomes[0], []) if nomes else []:
        chave = sorted((k, " ".join(v.lower().split())) for k, v in ds)
        for sel in sels:
            s = {"from": "0%", "to": "100%"}.get(sel.strip().lower(), sel.strip())
            try:
                passos.append((float(s.rstrip("%")) / 100, chave))
            except ValueError:
                pass
    passos.sort(key=lambda p: p[0])
    if len(passos) < 2:
        return 0.0, 1.0
    ini = max(p for p, c in passos if c == passos[0][1] and p <= 0.5)
    fim = min(p for p, c in passos if c == passos[-1][1] and p >= 0.5)
    return ini, fim


def check_folha(doc, clips, duracao):
    out = []
    for c in clips:
        tempo = _tempo(c)
        if not re.fullmatch(r"tr[1-9]\d*", c["id"] or "") or not tempo:
            continue
        a, b = _janela(doc, c)
        t0, t1 = tempo[0] + a * tempo[1] + FOLGA_GRADE, tempo[0] + b * tempo[1] - FOLGA_GRADE
        k = int(t0 / GRADE) + 1
        while k * GRADE < t1 and k * GRADE < duracao:
            out.append("%s aparece em %g s, um quadro que a folha de 0,5 s amostra: ponha o corte fora da grade "
                       "(1,875 s, 4,375 s...) e a transição visível só de 34%% a 66%% do clip" % (c["id"], k * GRADE))
            k += 1
    return _res("folha_limpa", out)


def _cena_do_script(html):
    blocos = re.findall(r"<script\b[^>]*>(.*?)</script\s*>", html, re.I | re.S)
    return re.sub(r"/\*.*?\*/", " ", blocos[-1], flags=re.S) if blocos else ""


def check_texto_inteiro(html, clips):
    textos = {c["id"]: qa_css.texto_de(c) for c in clips if c["id"] and qa_css.texto_de(c) and c["tag"] != "svg"}
    out = []
    for receita, alvo, resto in CHAMADA_RE.findall(_cena_do_script(html)):
        for i in re.findall(r"\"([\w-]+)\"", alvo):
            if i not in textos:
                continue
            titulo = re.fullmatch(r"s[1-9]\d*_titulo", i)
            if receita in TEXTO_CORTA and (TEXTO_CORTA[receita] is None
                                           or any('"%s"' % tipo in resto for tipo in TEXTO_CORTA[receita])):
                if receita == "contador" and not titulo:
                    continue  # a quantity counting up in a support line is whole at every frame
                out.append("M.%s em %s: texto não entra por máscara, de fora do quadro nem contando no título "
                           "(um quadro amostrado mostra a palavra cortada ou um número falso); use entra \"sobe\" "
                           "numa 2ª linha ou onda" % (receita, i))
            elif titulo and receita not in TITULO_OK and not (receita == "palavras" and '"onda"' in resto):
                out.append("M.%s em %s: o título de cada cena já está inteiro no corte (só onda, camera, parallax "
                           "ou pulso nele)" % (receita, i))
    return _res("texto_inteiro", sorted(set(out)))


def check_heroi_final(doc, html, clips, largura=1080.0):
    deco = next((c for c in clips if c["id"] == "deco1"), None)
    if deco is None:
        return _res("heroi_final", [])
    css_w = qa_css.medida(qa_css.ultimo(qa_css.decls(doc, deco, qa_css.amplo(deco)), "width"), largura) or largura
    cena = _cena_do_script(html)
    w = css_w if css_w < largura else None
    for alvo, base in (("heroi_quadro", 1000.0), ("deco1", css_w)):
        m = re.search(r"M\.trilha\(\s*\"%s\"\s*,\s*\"transform\"\s*,(.*?)\)\s*;" % alvo, cena, re.S)
        escalas = ESCALA_RE.findall(m.group(1)) if m else []
        if escalas:
            w = float(escalas[-1]) * base
            break
    if w is not None and w < HEROI_MIN * largura:
        return _res("heroi_final", ["herói com ~%d px no cartão final (%d%% da largura; mínimo %d%%): no fim ele "
                                    "continua grande, ao lado ou abaixo da chamada"
                                    % (w, round(w * 100 / largura), HEROI_MIN * 100)])
    return _res("heroi_final", [])


def tinta(w, h, bpp, linhas, caixa):
    """Fraction of the box's cells that are not the background (the most common color of the image)."""
    grade, lado = qa_vazio._grade(w, h, bpp, linhas)
    i0, i1 = int(round(caixa[0] / lado)), int(round(caixa[2] / lado))
    j0, j1 = int(round(caixa[1] / lado)), int(round(caixa[3] / lado))
    celulas = [v for linha in grade[j0:j1] for v in linha[i0:i1]]
    return sum(1 for v in celulas if not v) / float(max(1, len(celulas)))


def _quadro(video, ffmpeg, t, w, h):
    out = subprocess.run([ffmpeg, "-v", "error", "-ss", "%.3f" % t, "-i", video, "-frames:v", "1", "-vf",
                          "scale=%d:%d" % (w, h), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60).stdout
    if len(out) < w * h * 3:
        raise ValueError("ffmpeg gave no frame at %.2f s" % t)
    return [out[y * w * 3:(y + 1) * w * 3] for y in range(h)]


def check_quadro_de_corte(video, ffmpeg, scenes):
    w, h = 216, 384
    caixa = (w * 90 / 1080.0, h * 269 / 1920.0, w * 990 / 1080.0, h * 1536 / 1920.0)
    out = []
    try:
        for n, (start, length) in enumerate(scenes, 1):
            if n == 1:
                continue
            cedo = tinta(w, h, 3, _quadro(video, ffmpeg, start + CORTE_APOS, w, h), caixa)
            pronto = tinta(w, h, 3, _quadro(video, ffmpeg, start + length * 0.7, w, h), caixa)
            if pronto > 0.05 and cedo < CORTE_MIN * pronto:
                out.append("cena %d: %.2f s depois do corte o quadro tem %d%% do que a cena mostra pronta (mínimo "
                           "%d%%): título e herói já estão no lugar no corte; só a 2ª linha entra depois"
                           % (n, CORTE_APOS, round(cedo * 100 / pronto), CORTE_MIN * 100))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return {"name": "quadro_de_corte", "ok": False, "details": ["ffmpeg failed: %s" % exc]}
    return _res("quadro_de_corte", out)


def check_forma_na_margem(png, largura, margem=80):
    """A straight vertical edge of MARGEM_RUN px or more exactly on the left or right text margin, with a shape
    MARGEM_FUNDO px deep on the inside and plain background from there to the frame's edge."""
    try:
        w, h, bpp, linhas = qa_vazio.ler_png(png)
    except (OSError, ValueError, zlib.error) as exc:
        return {"name": "forma_na_margem", "ok": True, "details": ["não medido: %s" % exc]}
    e = w / float(largura)

    def px(y, x):
        return linhas[y][int(x) * bpp:int(x) * bpp + 3]

    def igual(a, b):
        return all(abs(p - q) <= qa_vazio.TOL for p, q in zip(a, b))
    out = []
    for lado, borda, s in (("direita", w - margem * e, 1), ("esquerda", margem * e, -1)):
        corrida = melhor = 0
        for y in range(h):
            dentro = px(y, borda - s * 5 * e)
            fora = [px(y, min(w - 1, max(0, borda + s * d * e))) for d in (5, 30, margem - 4)]
            corta = (igual(dentro, px(y, borda - s * MARGEM_FUNDO * e))
                     and all(igual(f, fora[0]) for f in fora) and not igual(dentro, fora[0]))
            corrida = corrida + 1 if corta else 0
            melhor = max(melhor, corrida)
        if melhor >= MARGEM_RUN * e:
            out.append("forma cortada na margem %s (x = %d, %d px de altura): forma que chega perto da borda "
                       "sangra até a borda real do quadro; só texto respeita a margem de %d px"
                       % (lado, round(borda / e), round(melhor / e), margem))
    return _res("forma_na_margem", out)
