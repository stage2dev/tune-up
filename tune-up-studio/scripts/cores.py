"""Color converter: CSS color text -> "#RRGGBB" (uppercase), or None when it is not a plain color.

Accepted: #rgb, #rgba, #rrggbb, #rrggbbaa (alpha dropped), rgb()/rgba() (commas or spaces,
numbers or %), hsl()/hsla() (hue in deg/turn/rad or bare), a bare HSL trio as shadcn writes it
("222.2 47.4% 11.2%"), oklch() (L as 0-1 or %, out-of-gamut values clipped), white and black.
Anything else (var(), gradients, currentColor, color-mix) gives None: nothing is guessed.
Python 3.9+, standard library only.
"""
import math
import re

_NUM = r"[+-]?(?:\d+\.?\d*|\.\d+)"
_HEX = re.compile(r"#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")
_FUNC = re.compile(r"(rgba?|hsla?|oklch)\(\s*([^()]*)\)", re.I)
_TRIO = re.compile(r"(%s)(deg)?\s+(%s)%%\s+(%s)%%" % (_NUM, _NUM, _NUM))
NOMES = {"white": "#FFFFFF", "black": "#000000"}


def _hex(r, g, b):
    """0-1 floats -> #RRGGBB, clipped."""
    return "#" + "".join("%02X" % int(round(max(0.0, min(1.0, x)) * 255)) for x in (r, g, b))


def _partes(corpo):
    """'1 2 3 / .5' or '1, 2, 3, .5' -> ['1', '2', '3'] (alpha dropped); None if malformed."""
    corpo = corpo.split("/")[0]
    partes = [p for p in re.split(r"[\s,]+", corpo.strip()) if p]
    if len(partes) == 4 and "," in corpo:
        partes = partes[:3]
    return partes if len(partes) == 3 else None


def _numero(texto):
    if not re.fullmatch(_NUM + r"%?", texto):
        return None
    return float(texto.rstrip("%"))


def _matiz(texto):
    m = re.fullmatch(r"(%s)(deg|turn|rad|grad)?" % _NUM, texto)
    if not m:
        return None
    v = float(m.group(1))
    unidade = m.group(2) or "deg"
    return {"deg": v, "turn": v * 360, "rad": math.degrees(v), "grad": v * 0.9}[unidade]


def hsl_para_hex(h, s, l):
    """h in degrees, s and l in percent."""
    h, s, l = (h % 360) / 360.0, max(0.0, min(100.0, s)) / 100.0, max(0.0, min(100.0, l)) / 100.0

    def canal(n):
        k = (n + h * 12) % 12
        return l - s * min(l, 1 - l) * max(-1.0, min(k - 3, 9 - k, 1.0))
    return _hex(canal(0), canal(8), canal(4))


def oklch_para_hex(L, C, H):
    """L 0-1, C >= 0, H degrees. OKLab -> linear sRGB -> sRGB, clipped."""
    a, b = C * math.cos(math.radians(H)), C * math.sin(math.radians(H))
    l_ = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    lin = (4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
           -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
           -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_)

    def gama(x):
        x = max(0.0, min(1.0, x))
        return 12.92 * x if x <= 0.0031308 else 1.055 * x ** (1 / 2.4) - 0.055
    return _hex(*(gama(x) for x in lin))


def _funcao(nome, corpo):
    p = _partes(corpo)
    if not p:
        return None
    nome = nome.lower()
    if nome.startswith("rgb"):
        vals = []
        for t in p:
            v = _numero(t)
            if v is None:
                return None
            vals.append(v / 100.0 if t.endswith("%") else v / 255.0)
        return _hex(*vals)
    if nome.startswith("hsl"):
        h, s, l = _matiz(p[0]), _numero(p[1]), _numero(p[2])
        return None if None in (h, s, l) else hsl_para_hex(h, s, l)
    L, C, H = _numero(p[0]), _numero(p[1]), _matiz(p[2])
    if None in (L, C, H):
        return None
    if p[0].endswith("%"):
        L /= 100.0
    if p[1].endswith("%"):
        C = C / 100.0 * 0.4  # CSS: 100% chroma = 0.4
    return oklch_para_hex(L, C, H)


def para_hex(texto):
    """CSS color text -> '#RRGGBB' or None."""
    if not isinstance(texto, str):
        return None
    t = texto.strip().rstrip(";").strip()
    if t.lower().endswith("!important"):
        t = t[:-10].strip()
    if t.lower() in NOMES:
        return NOMES[t.lower()]
    m = _HEX.fullmatch(t)
    if m:
        d = m.group(1)
        if len(d) in (3, 4):
            d = "".join(c * 2 for c in d[:3])
        return "#" + d[:6].upper()
    m = _FUNC.fullmatch(t)
    if m:
        return _funcao(m.group(1), m.group(2))
    m = _TRIO.fullmatch(t)
    if m:
        return hsl_para_hex(float(m.group(1)), float(m.group(3)), float(m.group(4)))
    return None
