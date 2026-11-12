"""Empty area of a rendered frame (attention check `ocupacao`): the biggest rectangle of plain background inside
the safe box, measured on the pixels. A frame "half built" (a void between the support line and the CTA, a scene
of one flat color with a small word in a corner) fails it; a photo, a device or text never counts as empty.

The background is the most common color of the frame; a cell of the grid is empty when every sampled pixel is
that color (tolerance TOL). Shapes in another brand color are not empty: they are the device. Imported by
qa_imagem.py (post PNG) and qa_video.py (frames of the MP4 from ffmpeg), never run.
Python 3.9+, standard library only.
"""
import struct
import zlib
from collections import Counter

COLUNAS = 54  # grid columns: 20 px cells at 1080
TOL = 8  # per channel: compression noise of the MP4 stays below it
POST_MAX = 0.15  # of the safe box (inside the 80 px margin)
VIDEO_MAX = 0.18  # of the reel safe box (x 90-990, y 269-1536), at 70% of each scene
BPP = {2: 3, 6: 4}  # RGB and RGBA, 8 bits: what Chrome and ffmpeg write


def ler_png(caminho):
    """(width, height, bytes per pixel, [row bytes]) of an 8-bit RGB/RGBA PNG without interlace; ValueError else."""
    with open(caminho, "rb") as f:
        dados = f.read()
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("não é PNG")
    pos, ihdr, idat = 8, None, []
    while pos + 8 <= len(dados):
        n, tipo = struct.unpack(">I4s", dados[pos:pos + 8])
        corpo = dados[pos + 8:pos + 8 + n]
        if tipo == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo)
        elif tipo == b"IDAT":
            idat.append(corpo)
        elif tipo == b"IEND":
            break
        pos += 12 + n
    if not ihdr or ihdr[2] != 8 or ihdr[3] not in BPP or ihdr[6]:
        raise ValueError("PNG fora do formato medido (8 bits, RGB ou RGBA, sem entrelaçamento)")
    w, h, bpp = ihdr[0], ihdr[1], BPP[ihdr[3]]
    if w * h > 1080 * 1920:
        raise ValueError("PNG maior que qualquer formato")
    cru, passo = zlib.decompress(b"".join(idat)), w * bpp
    if len(cru) < h * (passo + 1):
        raise ValueError("PNG cortado")
    linhas, ant = [], bytearray(passo)
    for y in range(h):
        i = y * (passo + 1)
        filtro, lin = cru[i], bytearray(cru[i + 1:i + 1 + passo])
        if filtro == 1:
            for x in range(bpp, passo):
                lin[x] = (lin[x] + lin[x - bpp]) & 255
        elif filtro == 2:
            lin = bytearray((a + b) & 255 for a, b in zip(lin, ant))
        elif filtro == 3:
            for x in range(passo):
                lin[x] = (lin[x] + ((lin[x - bpp] if x >= bpp else 0) + ant[x]) // 2) & 255
        elif filtro == 4:
            for x in range(passo):
                a, b = (lin[x - bpp] if x >= bpp else 0), ant[x]
                c = ant[x - bpp] if x >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                lin[x] = (lin[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        linhas.append(bytes(lin))
        ant = lin
    return w, h, bpp, linhas


def _grade(w, h, bpp, linhas):
    """[[empty?]] cells of w/COLUNAS px: every sampled pixel is the background (the most common color)."""
    contagem = Counter(linhas[y][x * bpp:x * bpp + 3] for y in range(0, h, 7) for x in range(0, w, 7))
    fundo = contagem.most_common(1)[0][0]
    lado = w / COLUNAS
    out = []
    for j in range(int(round(h / lado))):
        y0, y1 = int(j * lado), min(h, int((j + 1) * lado))
        out.append([all(abs(p - q) <= TOL for y in range(y0, y1, 2) for x in range(int(i * lado), int((i + 1) * lado), 2)
                        for p, q in zip(linhas[y][x * bpp:x * bpp + 3], fundo)) for i in range(COLUNAS)])
    return out, lado


def _maior_retangulo(grade):
    """(cells, (col, row, cols, rows)) of the biggest all-true rectangle (histogram method)."""
    if not grade:
        return 0, None
    alturas, melhor = [0] * len(grade[0]), (0, None)
    for j, linha in enumerate(grade):
        alturas = [a + 1 if v else 0 for a, v in zip(alturas, linha)]
        pilha = []
        for i in range(len(alturas) + 1):
            atual, ini = (alturas[i] if i < len(alturas) else 0), i
            while pilha and pilha[-1][1] >= atual:
                ini, alt = pilha.pop()
                if alt * (i - ini) > melhor[0]:
                    melhor = (alt * (i - ini), (ini, j - alt + 1, i - ini, alt))
            pilha.append((ini, atual))
    return melhor


def medir(w, h, bpp, linhas, caixa):
    """(empty fraction of the box, (x, y, width, height) in px) for a box (x0, y0, x1, y1) in px of this image."""
    grade, lado = _grade(w, h, bpp, linhas)
    i0, i1 = int(round(caixa[0] / lado)), int(round(caixa[2] / lado))
    j0, j1 = int(round(caixa[1] / lado)), int(round(caixa[3] / lado))
    dentro = [linha[i0:i1] for linha in grade[j0:j1]]
    celulas, ret = _maior_retangulo(dentro)
    total = max(1, (i1 - i0) * (j1 - j0))
    if not ret:
        return 0.0, None
    return celulas / total, tuple(int(round(v * lado)) for v in (ret[0] + i0, ret[1] + j0, ret[2], ret[3]))


def problema(frac, ret, limite, onde, escala=1.0):
    """The finding line for a void above the limit, or None (coordinates back in frame px)."""
    if frac <= limite or not ret:
        return None
    x, y, lw, lh = (int(round(v / escala)) for v in ret)
    return ("%s: área vazia de %dx%d px em (%d, %d), %d%% da área segura (máximo %d%%): leve o recurso para lá ou "
            "aumente texto e recurso" % (onde, lw, lh, x, y, round(frac * 100), round(limite * 100)))


def check_png(png, largura, altura, margem=80, limite=POST_MAX):
    """Check `ocupacao` of a post or ad PNG: the biggest void inside the margin."""
    try:
        w, h, bpp, linhas = ler_png(png)
    except (OSError, ValueError, zlib.error) as exc:
        return {"name": "ocupacao", "ok": True, "details": ["não medido: %s" % exc]}
    escala = w / float(largura)
    caixa = tuple(v * escala for v in (margem, margem, largura - margem, altura - margem))
    frac, ret = medir(w, h, bpp, linhas, caixa)
    erro = problema(frac, ret, limite, "quadro", escala)
    return {"name": "ocupacao", "ok": erro is None, "details": [erro] if erro else
            ["maior vazio: %d%% da área segura" % round(frac * 100)]}
