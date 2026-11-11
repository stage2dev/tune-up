"""Colors of a logo -> brand color roles. Deterministic: no network, no AI, same file = same answer.

SVG: fill, stroke and stop-color (attributes and CSS) counted by occurrence; colors that cores.para_hex
does not read (var(), url(), names other than white/black) are skipped, and an element with no fill is NOT
counted as black (nothing is guessed).
PNG: decoded with zlib only (color types 0, 2, 3, 4, 6; bit depth 1/2/4/8/16; 16 keeps the high byte;
tRNS honored); pixels with alpha under 50% are skipped; up to 40000 pixels of a regular grid are counted.
Interlaced PNG and JPEG/WebP are not read (no decoder in the standard library): the caller hides the button.
Similar colors (anti-aliasing) merge into the most frequent one.

Roles: primary = most frequent colorful color (else the most frequent); accent = the next colorful color
far from primary; text = darkest color if dark enough; bg = lightest color if light enough. A role with no
fitting color is left out. Python 3.9+, standard library only.
"""
import json
import os
import re
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import cores  # noqa: E402

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 2500 * 1000  # Paeth in pure Python: ~4 s at this size on a laptop
AMOSTRA = 200  # grid of up to 200 x 200 counted pixels
RE_SVG = re.compile(r"(?i)(?:fill|stroke|stop-color)\s*(?:=\s*[\"']|:\s*)([^\"';}>]+)")
CANAIS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class Ilegivel(Exception):
    pass


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def _hex(rgb):
    return "#%02X%02X%02X" % rgb


def luminancia(h):
    def canal(v):
        v /= 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * canal(r) + 0.7152 * canal(g) + 0.0722 * canal(b)


def colorida(h):
    r, g, b = _rgb(h)
    return max(r, g, b) - min(r, g, b) >= 40


def _distancia(a, b):
    return sum((x - y) ** 2 for x, y in zip(_rgb(a), _rgb(b))) ** 0.5


def do_svg(texto):
    contagem = {}
    for bruto in RE_SVG.findall(texto):
        h = cores.para_hex(bruto)
        if h:
            contagem[h] = contagem.get(h, 0) + 1
    return contagem


def _chunks(dados):
    if dados[:8] != b"\x89PNG\r\n\x1a\n":
        raise Ilegivel("não é PNG")
    pos = 8
    while pos + 12 <= len(dados):
        n = struct.unpack(">I", dados[pos:pos + 4])[0]
        yield dados[pos + 4:pos + 8], dados[pos + 8:pos + 8 + n]
        pos += 12 + n


def _desfiltrar(cru, altura, linha, bpp):
    """Rows without the PNG filters (None, Sub, Up, Average, Paeth)."""
    linhas, anterior = [], bytearray(linha)
    for y in range(altura):
        ini = y * (linha + 1)
        f, atual = cru[ini], bytearray(cru[ini + 1:ini + 1 + linha])
        if f == 1:
            for i in range(bpp, linha):
                atual[i] = (atual[i] + atual[i - bpp]) & 255
        elif f == 2:
            atual = bytearray((a + b) & 255 for a, b in zip(atual, anterior))
        elif f == 3:
            for i in range(linha):
                atual[i] = (atual[i] + ((atual[i - bpp] if i >= bpp else 0) + anterior[i]) // 2) & 255
        elif f == 4:
            for i in range(linha):
                a = atual[i - bpp] if i >= bpp else 0
                b, c = anterior[i], (anterior[i - bpp] if i >= bpp else 0)
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                atual[i] = (atual[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif f != 0:
            raise Ilegivel("filtro desconhecido")
        linhas.append(atual)
        anterior = atual
    return linhas


def do_png(dados):
    ihdr, idat, paleta, trns = None, [], None, None
    for nome, corpo in _chunks(dados):
        if nome == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo[:13])
        elif nome == b"PLTE":
            paleta = [tuple(corpo[i:i + 3]) for i in range(0, len(corpo) - 2, 3)]
        elif nome == b"tRNS":
            trns = corpo
        elif nome == b"IDAT":
            idat.append(corpo)
        elif nome == b"IEND":
            break
    if not ihdr or not idat:
        raise Ilegivel("PNG incompleto")
    w, h, prof, tipo, _, _, entrelacado = ihdr
    if tipo not in CANAIS or prof not in (1, 2, 4, 8, 16) or entrelacado or w < 1 or h < 1:
        raise Ilegivel("PNG de um tipo que não leio (entrelaçado ou formato raro)")
    if w * h > MAX_PIXELS:
        raise Ilegivel("a logo é grande demais para eu ler as cores; escolha as cores à mão")
    bits = CANAIS[tipo] * prof
    linha, bpp = (w * bits + 7) // 8, max(1, bits // 8)
    esperado = (linha + 1) * h
    z = zlib.decompressobj()
    try:
        cru = z.decompress(b"".join(idat), esperado + 1)
    except zlib.error:
        raise Ilegivel("PNG corrompido")
    if len(cru) < esperado:
        raise Ilegivel("PNG corrompido")
    linhas = _desfiltrar(cru, h, linha, bpp)
    passo_y, passo_x = max(1, h // AMOSTRA), max(1, w // AMOSTRA)
    contagem = {}
    for y in range(0, h, passo_y):
        r = linhas[y]
        for x in range(0, w, passo_x):
            cor = _pixel(r, x, tipo, prof, paleta, trns)
            if cor:
                contagem[cor] = contagem.get(cor, 0) + 1
    return contagem


def _amostra(r, x, prof, n, k):
    """Channel k of pixel x with n channels, as 0-255."""
    if prof == 16:
        return r[(x * n + k) * 2]
    if prof == 8:
        return r[x * n + k]
    bit = x * prof
    v = (r[bit // 8] >> (8 - prof - bit % 8)) & ((1 << prof) - 1)
    return v


def _pixel(r, x, tipo, prof, paleta, trns):
    n = CANAIS[tipo]
    if tipo == 3:
        i = _amostra(r, x, prof, 1, 0)
        if not paleta or i >= len(paleta) or (trns and i < len(trns) and trns[i] < 128):
            return None
        return _hex(paleta[i])
    v = [_amostra(r, x, prof, n, k) for k in range(n)]
    if prof < 8:
        v = [c * 255 // ((1 << prof) - 1) for c in v]
    if tipo in (4, 6) and v[-1] < 128:
        return None
    if tipo in (0, 4):
        rgb = (v[0],) * 3
    else:
        rgb = tuple(v[:3])
    if trns and tipo in (0, 2) and len(trns) >= 2 * (1 if tipo == 0 else 3):
        alvo = struct.unpack(">%dH" % (1 if tipo == 0 else 3), trns[:2 * (1 if tipo == 0 else 3)])
        cru = ([(r[(x * n + k) * 2] << 8) | r[(x * n + k) * 2 + 1] for k in range(n)] if prof == 16
               else [_amostra(r, x, prof, n, k) for k in range(n)])
        if tuple(cru[:len(alvo)]) == alvo:
            return None
    return _hex(rgb)


def agrupar(contagem):
    """[(hex, peso)] most frequent first; colors closer than 48 merge into the earlier one."""
    grupos = []
    for h, n in sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0])):
        for g in grupos:
            if _distancia(g[0], h) < 48:
                g[1] += n
                break
        else:
            grupos.append([h, n])
    return sorted(((g[0], g[1]) for g in grupos), key=lambda g: (-g[1], g[0]))


def papeis(lista):
    """{primary, accent, text, bg} from the grouped colors; a role with no fitting color is left out."""
    cores_ = [h for h, _ in lista]
    if not cores_:
        return {}
    vivas = [h for h in cores_ if colorida(h)]
    saida = {"primary": vivas[0] if vivas else cores_[0]}
    outra = next((h for h in vivas[1:] if _distancia(h, saida["primary"]) >= 60), None)
    if outra:
        saida["accent"] = outra
    escura = min(cores_, key=luminancia)
    if luminancia(escura) < 0.2:
        saida["text"] = escura
    clara = max(cores_, key=luminancia)
    if luminancia(clara) > 0.85:
        saida["bg"] = clara
    return saida


def ler(caminho):
    """{"cores": [[hex, peso]...], "papeis": {...}} or Ilegivel with a sentence for the screen."""
    ext = os.path.splitext(caminho)[1].lower()
    if ext not in (".svg", ".png"):
        raise Ilegivel("só leio as cores de logo em PNG ou SVG")
    if os.path.islink(caminho) or not os.path.isfile(caminho) or os.path.getsize(caminho) > MAX_BYTES:
        raise Ilegivel("não achei o arquivo da logo")
    with open(caminho, "rb") as f:
        dados = f.read()
    contagem = do_svg(dados.decode("utf-8", "replace")) if ext == ".svg" else do_png(dados)
    lista = agrupar(contagem)
    if not lista:
        raise Ilegivel("não achei nenhuma cor escrita na logo")
    return {"cores": [[h, n] for h, n in lista[:8]], "papeis": papeis(lista)}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: cores_da_logo.py <logo.png|logo.svg>", file=sys.stderr)
        return 2
    try:
        print(json.dumps(ler(argv[0]), ensure_ascii=False))
    except Ilegivel as e:
        print("recusado: %s" % e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
