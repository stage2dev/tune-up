"""Small HTML/CSS reader for qa_atencao.py: elements, visible text, rules, keyframes, px values.

Also the color-value check used by `cores_marca`. Not a CSS engine: no cascade, no specificity, no inheritance. The studio skills write selectors
the QA can read (the "Seletores" contract): an h1 rule is one whose last compound starts with
`h1`, a clip rule is one whose selector is exactly `#<clip id>`. Imported, never run.
Python 3.9+, standard library plus cores.py.
"""
import html.parser
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cores  # noqa: E402

OCULTAS = {"head", "style", "script", "title"}  # text inside these is never on screen
VAZIAS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
COMENTARIO_RE = re.compile(r"/\*.*?\*/", re.S)
PX_RE = re.compile(r"([+-]?(?:\d+\.?\d*|\.\d+))px", re.I)
COMBINADOR_RE = re.compile(r"\s*[>+~]\s*|\s+")
AGRUPA = ("@media", "@supports", "@layer", "@container", "@document")


class _Leitor(html.parser.HTMLParser):
    """Every element (tag, attrs, id, classes, the text inside it) and each text run with its owner."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.elementos, self.pilha, self.trechos, self.css = [], [], [], []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        el = {"tag": tag, "attrs": a, "id": a.get("id", ""), "classes": a.get("class", "").split(), "texto": [],
              "bruto": [], "dentro": [e["tag"] for e in self.pilha]}  # tags of the open ancestors
        self.elementos.append(el)
        if tag == "br":  # a forced line break, kept in the raw text of every open ancestor
            for e in self.pilha:
                e["bruto"].append("\n")
        if tag not in VAZIAS:
            self.pilha.append(el)

    def handle_startendtag(self, tag, attrs):
        antes = len(self.pilha)
        self.handle_starttag(tag, attrs)
        del self.pilha[antes:]

    def handle_endtag(self, tag):
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i]["tag"] == tag:
                del self.pilha[i:]
                break

    def handle_data(self, data):
        tags = [e["tag"] for e in self.pilha]
        if tags and tags[-1] == "style":
            self.css.append(data)
            return
        texto = " ".join(data.split())
        if not texto or any(t in OCULTAS for t in tags):
            return
        self.trechos.append((self.pilha[-1] if self.pilha else None, texto))
        bruto = re.sub(r"[ \t\r\n\f\v]+", " ", data)  # HTML spaces collapse; a no-break space (&nbsp;) stays
        for e in self.pilha:
            e["texto"].append(texto)
            e["bruto"].append(bruto)


def ler_html(html):
    """{"elementos", "trechos", "css"} of an HTML text; a parser error keeps what was read so far."""
    p = _Leitor()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: B902 - the 3.9 parser can raise on a broken declaration
        pass
    return {"elementos": p.elementos, "trechos": p.trechos, "css": "\n".join(p.css)}


def texto_de(el):
    return " ".join(el["texto"]).strip()


def linhas_de(el):
    """The text of an element as typed: one item per forced line (<br>), no-break spaces (\\xa0) kept."""
    return [re.sub(" +", " ", x).strip(" ") for x in "".join(el.get("bruto", [])).split("\n")]


def texto_visivel(html):
    """[(tag, id, classes, text)] for each visible text run; head/style/script/title and alt do not count."""
    return [(d["tag"] if d else "", d["id"] if d else "", " ".join(d["classes"]) if d else "", t)
            for d, t in ler_html(html)["trechos"]]


def declaracoes(texto):
    """[(property lowercased, value)] of a declaration block or a style="" attribute; !important dropped."""
    out, buf, prof, aspas = [], [], 0, ""
    for c in (texto or "") + ";":
        if aspas:
            buf.append(c)
            aspas = "" if c == aspas else aspas
            continue
        if c in "\"'":
            aspas = c
        elif c == "(":
            prof += 1
        elif c == ")":
            prof = max(0, prof - 1)
        elif c == ";" and prof == 0:
            item, buf = "".join(buf), []
            if ":" in item:
                k, v = item.split(":", 1)
                v = re.sub(r"\s*!\s*important\s*$", "", v.strip(), flags=re.I)
                if k.strip():
                    out.append((k.strip().lower(), v.strip()))
            continue
        buf.append(c)
    return out


def _blocos(css):
    """[(prelude, body)] of the top-level blocks of a CSS text."""
    out, i, n = [], 0, len(css)
    while i < n:
        a = css.find("{", i)
        if a < 0:
            break
        pre, prof, j = css[i:a].split(";")[-1].strip(), 1, a + 1
        while j < n and prof:
            prof += {"{": 1, "}": -1}.get(css[j], 0)
            j += 1
        out.append((pre, css[a + 1:j - 1]))
        i = j
    return out


def _passo(sel):
    s = sel.strip().lower()
    return {"from": "0%", "to": "100%"}.get(s, s)


def folha(css):
    """(rules, keyframes) of a CSS text. rules: [{"seletores": [...], "decl": [(prop, value)]}];
    keyframes: {name: [([steps as "0%"...], decl)]}. @font-face and other at-rules are skipped."""
    regras, quadros = [], {}

    def ler(texto):
        for pre, corpo in _blocos(texto):
            low = pre.lower()
            if low.startswith("@") and "keyframes" in low.split()[0]:
                nome = pre.split(None, 1)[1].strip().strip("\"'") if len(pre.split()) > 1 else ""
                quadros[nome] = [([_passo(s) for s in p.split(",")], declaracoes(c)) for p, c in _blocos(corpo)]
            elif low.startswith(AGRUPA):
                ler(corpo)
            elif not low.startswith("@") and pre:
                regras.append({"seletores": [s.strip() for s in pre.split(",") if s.strip()],
                               "decl": declaracoes(corpo)})
    ler(COMENTARIO_RE.sub(" ", css or ""))
    return regras, quadros


def regras_css(html, extra=""):
    """Rules of every <style> in the HTML (plus `extra` CSS text)."""
    return folha(ler_html(html)["css"] + "\n" + extra)[0]


def keyframes(html, extra=""):
    """@keyframes of every <style> in the HTML (plus `extra`): {name: [(steps, decl)]}."""
    return folha(ler_html(html)["css"] + "\n" + extra)[1]


def valor_px(decl):
    """112.0 for "112px" (a declaration value); None for any other unit, keyword or expression."""
    m = PX_RE.fullmatch((decl or "").strip())
    return float(m.group(1)) if m else None


def medida(decl, total):
    """px of a length declaration: "300px" -> 300.0, "50%" -> half of `total`; None for anything else."""
    v = (decl or "").strip()
    m = re.fullmatch(r"([+-]?(?:\d+\.?\d*|\.\d+))%", v)
    return float(m.group(1)) * total / 100.0 if m else valor_px(v)


def ultimo_composto(seletor):
    """The compound after the last combinator: ".l-numero > h1.big" -> "h1.big"."""
    partes = [p for p in COMBINADOR_RE.split(seletor.strip()) if p]
    return partes[-1] if partes else ""


# ---------- a source folder and the declarations that reach one element ----------

MAX_BYTES = 1024 * 1024
ANIM_KW = frozenset("none infinite normal reverse alternate alternate-reverse forwards backwards both running paused "
                    "linear ease ease-in ease-out ease-in-out step-start step-end initial inherit unset".split())


def ler_arquivo(caminho):
    """Text of a small regular file (never a link), or None."""
    try:
        if not caminho or os.path.islink(caminho) or not os.path.isfile(caminho) or \
                os.path.getsize(caminho) > MAX_BYTES:
            return None
        with open(caminho, "rb") as f:
            return f.read().decode("utf-8", errors="replace")
    except OSError:
        return None


def ler_fonte(fonte):
    """index.html of a source folder (plus its top-level .css files) read: ler_html() + "regras", "quadros"
    (keyframes) and "texto" (all visible text). None without index.html."""
    html = ler_arquivo(os.path.join(fonte, "index.html"))
    if html is None:
        return None
    extra = [ler_arquivo(os.path.join(fonte, n)) or "" for n in sorted(os.listdir(fonte)) if n.lower().endswith(".css")]
    doc = ler_html(html)
    doc["regras"], doc["quadros"] = folha(doc["css"] + "\n" + "\n".join(extra))
    doc["texto"] = " ".join(t for _, t in doc["trechos"])
    return doc


def exato(el):
    """Contract matcher of a clip: the selector is exactly `#<id>`."""
    return lambda sel: bool(el["id"]) and sel.strip() == "#" + el["id"]


def amplo(el):
    """Selectors whose last compound names the element's id or one of its classes."""
    alvos = (["#" + el["id"]] if el["id"] else []) + ["." + c for c in el["classes"]]
    return lambda sel: any(re.search(r"%s(?![\w-])" % re.escape(a), ultimo_composto(sel)) for a in alvos)


def decls(doc, el, casa):
    """Declarations of the rules whose selector (any item of the list) `casa` accepts, then style=""."""
    out = [d for r in doc["regras"] if any(casa(s) for s in r["seletores"]) for d in r["decl"]]
    return out + declaracoes(el["attrs"].get("style", ""))


def ultimo(lista, prop):
    """Value of the last declaration of `prop` (no specificity: the later one wins), or None."""
    v = None
    for k, val in lista:
        if k == prop:
            v = val
    return v


def todas_decls(doc):
    """(where, prop, value) of every declaration: rules, keyframes, style="" attributes."""
    for r in doc["regras"]:
        for k, v in r["decl"]:
            yield ", ".join(r["seletores"])[:60], k, v
    for nome, passos in doc["quadros"].items():
        for _, decl in passos:
            for k, v in decl:
                yield "@keyframes " + nome, k, v
    for el in doc["elementos"]:
        for k, v in declaracoes(el["attrs"].get("style", "")):
            yield "<%s%s style>" % (el["tag"], " id=" + el["id"] if el["id"] else ""), k, v


def nomes_animacao(lista):
    """Animation names of the last animation / animation-name declaration."""
    nomes = []
    for k, v in lista:
        if k == "animation-name":
            nomes = [x.strip() for x in v.split(",") if x.strip()]
        elif k == "animation":
            nomes = []
            for parte in v.split(","):
                toks = re.sub(r"[\w-]+\([^)]*\)", " ", parte).split()
                nome = next((t for t in toks if t.lower() not in ANIM_KW and not re.match(r"[\d.+-]", t)), None)
                if nome:
                    nomes.append(nome.strip("\"'"))
    return nomes


def zero(v):
    """True when a value has no nonzero digit (None, "0", "0px 0"): no radius, a closed-to-zero inset."""
    return not re.search(r"[1-9]", v or "")


# ---------- color values ----------

HEX_RE = re.compile(r"#([0-9a-fA-F]+)(?![\w-])")
FUNC_RE = re.compile(r"\b(rgba?|hsla?|oklch|oklab|lab|lch|hwb|color)\(([^()]*)\)", re.I)
PROPS_COR = re.compile(r"(?:--.*|color|background(?:-color)?|border(?:-[a-z]+)*|outline(?:-color)?|fill|stroke|"
                       r"stop-color|flood-color|lighting-color|[a-z-]*shadow|caret-color|accent-color|"
                       r"text-decoration(?:-color)?|text-emphasis(?:-color)?|column-rule(?:-color)?)\Z")
ATRIBUTOS_COR = ("fill", "stroke", "stop-color", "color")
# CSS named colors: a brand color is always written as its value, so any of these is off-brand.
NOMES_COR = frozenset("""aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue
blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk crimson cyan darkblue
darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki darkmagenta darkolivegreen darkorange darkorchid
darkred darksalmon darkseagreen darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink
deepskyblue dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite gold
goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki lavender lavenderblush
lawngreen lemonchiffon lightblue lightcoral lightcyan lightgoldenrodyellow lightgray lightgreen lightgrey
lightpink lightsalmon lightseagreen lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime
limegreen linen magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream mistyrose moccasin
navajowhite navy oldlace olive olivedrab orange orangered orchid palegoldenrod palegreen paleturquoise
palevioletred papayawhip peachpuff peru pink plum powderblue purple rebeccapurple red rosybrown royalblue
saddlebrown salmon sandybrown seagreen seashell sienna silver skyblue slateblue slategray slategrey snow
springgreen steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen""".split())


def _alfa(corpo):
    parte = corpo.split("/")[1] if "/" in corpo else (corpo.split(",")[3] if corpo.count(",") == 3 else None)
    if parte is None:
        return None
    t = parte.strip()
    try:
        return float(t[:-1]) / 100 if t.endswith("%") else float(t)
    except ValueError:
        return None


def problemas_cor(valor, permitidas, onde, nomes=True):
    """Why the colors in a CSS value are off-brand: not in `permitidas` ("#RRGGBB"), any transparency,
    color-mix(), and (with `nomes`, for color properties) named colors. var() and keywords pass."""
    v = re.sub(r"url\([^)]*\)|\"[^\"]*\"|'[^']*'", " ", valor)
    out = ["%s: color-mix() não é cor da marca" % onde] if "color-mix(" in v.lower() else []
    for m in FUNC_RE.finditer(v):
        alfa = _alfa(m.group(2))
        if alfa is not None and alfa < 1:
            out.append("%s: %s tem transparência" % (onde, m.group(0)))
        elif cores.para_hex(m.group(0)) not in permitidas:
            out.append("%s: %s fora das cores da marca" % (onde, m.group(0)))
    resto = FUNC_RE.sub(" ", v)
    for m in HEX_RE.finditer(resto):
        d = m.group(1)
        if len(d) not in (3, 4, 6, 8):
            out.append("%s: #%s não é uma cor" % (onde, d))
        elif len(d) in (4, 8) and d[len(d) * 3 // 4:].lower() not in ("f", "ff"):
            out.append("%s: #%s tem transparência" % (onde, d))
        elif cores.para_hex("#" + d) not in permitidas:
            out.append("%s: #%s fora das cores da marca" % (onde, d))
    if nomes:
        sem = re.sub(r"var\([^)]*\)", " ", HEX_RE.sub(" ", resto))
        out += ["%s: nome de cor %s (use o valor da marca)" % (onde, w) for w in re.findall(r"[A-Za-z]+", sem)
                if w.lower() in NOMES_COR]
    return out


def problemas_cores(doc, permitidas):
    """problemas_cor over every declaration and every fill/stroke/stop-color/color attribute."""
    out = []
    for onde, k, v in todas_decls(doc):
        out += problemas_cor(v, permitidas, "%s { %s }" % (onde, k), nomes=bool(PROPS_COR.match(k)))
    for el in doc["elementos"]:
        for a in ATRIBUTOS_COR:
            if a in el["attrs"]:
                out += problemas_cor(el["attrs"][a], permitidas, "<%s %s>" % (el["tag"], a))
    return out
