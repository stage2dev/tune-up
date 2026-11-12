"""Text width from the real font file, so the kit sizes a headline to its box without a browser.

`local("Name")` in an @font-face matches a face by its full name or PostScript name; this module finds that
face in the system font folders (TrueType, OpenType and collections), reads `cmap` and `hmtx` and returns the
advance of each character in em. Unknown font or character: an average letter (the same .55 em the QA uses),
so the kit still works, only less exactly. Python 3.9+, standard library only; reads files, never writes.
"""
import os
import struct
import sys

PASTAS = ("/System/Library/Fonts", "/System/Library/Fonts/Supplemental", "/Library/Fonts",
          os.path.expanduser("~/Library/Fonts"), "/usr/share/fonts", "/usr/local/share/fonts",
          os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts"), "C:\\Windows\\Fonts")
EXT = (".ttf", ".otf", ".ttc", ".otc")
MEDIA_EM = 0.55  # average letter when the face is not found (qa_cenas.LETRA_EM)
MAX_ARQUIVO = 64 * 1024 * 1024
_indice = None
_faces = {}


def _tabelas(dados, base):
    n = struct.unpack_from(">H", dados, base + 4)[0]
    out = {}
    for i in range(n):
        tag, _, off, tam = struct.unpack_from(">4sLLL", dados, base + 12 + 16 * i)
        out[tag] = (off, tam)
    return out


def _nomes(dados, tab):
    """Full names (id 4) and PostScript names (id 6) of a face, lower case."""
    if b"name" not in tab:
        return set()
    off = tab[b"name"][0]
    _, n, texto = struct.unpack_from(">HHH", dados, off)
    out = set()
    for i in range(n):
        plat, _, _, nid, tam, pos = struct.unpack_from(">HHHHHH", dados, off + 6 + 12 * i)
        if nid not in (4, 6):
            continue
        bruto = dados[off + texto + pos: off + texto + pos + tam]
        try:
            out.add(bruto.decode("utf-16-be" if plat in (0, 3) else "mac-roman").strip().lower())
        except UnicodeDecodeError:
            pass
    return out


def _bases(dados):
    if dados[:4] == b"ttcf":
        n = struct.unpack_from(">L", dados, 8)[0]
        return list(struct.unpack_from(">%dL" % n, dados, 12))
    return [0]


def _varrer():
    """{name: (file, face offset)} for every face in the font folders (first one wins)."""
    indice = {}
    for pasta in PASTAS:
        for raiz, _, arquivos in os.walk(pasta):
            for nome in sorted(arquivos):
                if not nome.lower().endswith(EXT):
                    continue
                caminho = os.path.join(raiz, nome)
                try:
                    if os.path.getsize(caminho) > MAX_ARQUIVO:
                        continue
                    with open(caminho, "rb") as f:
                        dados = f.read()
                    for base in _bases(dados):
                        for n in _nomes(dados, _tabelas(dados, base)):
                            indice.setdefault(n, (caminho, base))
                except (OSError, struct.error, IndexError):
                    continue
    return indice


def _cmap(dados, off):
    """Character code -> glyph id, from the best Unicode subtable (format 12, then 4)."""
    n = struct.unpack_from(">H", dados, off + 2)[0]
    subs = {}
    for i in range(n):
        plat, enc, pos = struct.unpack_from(">HHL", dados, off + 4 + 8 * i)
        fmt = struct.unpack_from(">H", dados, off + pos)[0]
        if plat in (0, 3) and fmt in (4, 12):
            subs.setdefault(fmt, off + pos)
    mapa = {}
    if 4 in subs:
        p = subs[4]
        seg = struct.unpack_from(">H", dados, p + 6)[0] // 2
        fins = struct.unpack_from(">%dH" % seg, dados, p + 14)
        inis = struct.unpack_from(">%dH" % seg, dados, p + 16 + 2 * seg)
        deltas = struct.unpack_from(">%dh" % seg, dados, p + 16 + 4 * seg)
        base_r = p + 16 + 6 * seg
        ranges = struct.unpack_from(">%dH" % seg, dados, base_r)
        for i in range(seg):
            for c in range(inis[i], min(fins[i], 0xFFFE) + 1):
                if c > 0x24FF:  # Latin, punctuation, currency and arrows are enough for a headline
                    break
                if ranges[i] == 0:
                    g = (c + deltas[i]) & 0xFFFF
                else:
                    g = struct.unpack_from(">H", dados, base_r + 2 * i + ranges[i] + 2 * (c - inis[i]))[0]
                    g = (g + deltas[i]) & 0xFFFF if g else 0
                if g:
                    mapa[c] = g
    if 12 in subs:
        p = subs[12]
        grupos = struct.unpack_from(">L", dados, p + 12)[0]
        for i in range(grupos):
            a, b, g = struct.unpack_from(">LLL", dados, p + 16 + 12 * i)
            if a > 0x24FF:
                break
            for c in range(a, min(b, 0x24FF) + 1):
                mapa.setdefault(c, g + c - a)
    return mapa


def _carregar(caminho, base):
    with open(caminho, "rb") as f:
        dados = f.read()
    tab = _tabelas(dados, base)
    upm = struct.unpack_from(">H", dados, tab[b"head"][0] + 18)[0]
    nh = struct.unpack_from(">H", dados, tab[b"hhea"][0] + 34)[0]
    hm = tab[b"hmtx"][0]
    avancos = [struct.unpack_from(">H", dados, hm + 4 * i)[0] for i in range(nh)]
    pesada = False
    if b"OS/2" in tab:  # a face that is already bold or black (Impact is "400" but its PANOSE weight is bold)
        os2 = tab[b"OS/2"][0]
        pesada = struct.unpack_from(">H", dados, os2 + 4)[0] >= 600 or dados[os2 + 34] >= 8
    return {"upm": float(upm), "avancos": avancos, "cmap": _cmap(dados, tab[b"cmap"][0]), "pesada": pesada}


def face(nomes):
    """First face of the list found on this machine, or None. `nomes` = the local() names, in order."""
    global _indice
    if _indice is None:
        _indice = _varrer()
    for nome in nomes:
        achado = _indice.get(str(nome).strip().lower())
        if not achado:
            continue
        if achado not in _faces:
            try:
                _faces[achado] = _carregar(*achado)
            except (OSError, struct.error, IndexError, KeyError):
                _faces[achado] = None
        if _faces[achado]:
            return _faces[achado]
    return None


def largura_em(texto, fonte=None, espaco=0.0):
    """Width of one line in em: the advances of the face (or the average letter) plus letter-spacing."""
    total = 0.0
    for ch in texto:
        c = 0x20 if ch == "\u00a0" else ord(ch)
        g = fonte["cmap"].get(c) if fonte else None
        if g is None:
            total += 0.28 if ch in " \u00a0.,:;!|'il" else MEDIA_EM
        else:
            av = fonte["avancos"]
            total += av[g if g < len(av) else -1] / fonte["upm"]
        total += espaco
    return total


if __name__ == "__main__":
    f = face(sys.argv[1:2])
    print("achada" if f else "não achada", round(largura_em(" ".join(sys.argv[2:]), f), 3))
