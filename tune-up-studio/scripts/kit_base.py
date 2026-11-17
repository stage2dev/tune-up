"""Shared parts of the composition kit (montar.py): brand, color pairs, text fitted to a box, the hero drawing
and the channel icons. The kit turns `peca.json` (the texts) and `heroi.svg` (the one drawing the session
makes) into a finished `index.html`; nothing here invents a color, a font or a fact.
Python 3.9+, standard library only.
"""
import html
import json
import os
import re
import zlib

import fontes
import kit_medida
import qa_atencao

CORES = ("bg", "surface", "primary", "text", "accent")
CANAIS = {
    # channel icons, drawn in a 100x100 box; `.ic` takes the icon color, `.ic2` the color behind it
    "whatsapp": '<path class="ic" d="M50 10 C74 10 90 26 90 46 C90 66 74 80 50 80 L28 92 L32 74 C18 68 10 58 10 46 '
                'C10 26 26 10 50 10 Z"/><circle class="ic2" cx="34" cy="46" r="6"/><circle class="ic2" cx="50" '
                'cy="46" r="6"/><circle class="ic2" cx="66" cy="46" r="6"/>',
    "endereco": '<path class="ic" d="M50 6 C70 6 84 20 84 39 C84 62 50 94 50 94 C50 94 16 62 16 39 C16 20 30 6 50 6 '
                'Z"/><circle class="ic2" cx="50" cy="39" r="13"/>',
    "instagram": '<rect class="ic" x="12" y="12" width="76" height="76" rx="22"/><circle class="ic2" cx="50" cy="50" '
                 'r="19"/><circle class="ic" cx="50" cy="50" r="9"/><circle class="ic2" cx="72" cy="28" r="6"/>',
    "site": '<rect class="ic" x="8" y="16" width="84" height="68" rx="8"/><rect class="ic2" x="16" y="34" width="68" '
            'height="42"/><circle class="ic2" cx="20" cy="25" r="4"/><circle class="ic2" cx="32" cy="25" r="4"/>'
            '<path class="ic" d="M40 44 L64 56 L53 59 L59 71 L53 74 L47 62 L40 69 Z"/>',
    "telefone": '<path class="ic" d="M26 8 L42 8 L48 30 L37 38 C43 50 50 57 62 63 L70 52 L92 58 L92 74 C92 84 84 92 '
                '74 92 C40 90 10 60 8 26 C8 16 16 8 26 8 Z"/>',
}
HEROI_TAGS = {"g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}
HEROI_ATTRS = {"id", "class", "d", "x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "x1", "y1", "x2", "y2",
               "points", "transform", "stroke-width", "stroke-linecap", "stroke-linejoin", "stroke-dasharray",
               "pathlength", "fill", "opacity"}
HEROI_CLASSES = {"p", "a", "t", "b", "s", "lp", "la", "lt", "lb", "ls", "arred"}
HEROI_CSS = (".p { fill: var(--primary); } .a { fill: var(--accent); } .t { fill: var(--text); } "
             ".b { fill: var(--bg); } .s { fill: var(--surface); } "
             ".lp, .la, .lt, .lb, .ls { fill: none; stroke-linecap: round; stroke-linejoin: round; } "
             ".lp { stroke: var(--primary); } .la { stroke: var(--accent); } .lt { stroke: var(--text); } "
             ".lb { stroke: var(--bg); } .ls { stroke: var(--surface); }")
TAG_RE = re.compile(r"<\s*(/?)\s*([A-Za-z][\w:-]*)([^<>]*?)(/?)\s*>")
ATTR_RE = re.compile(r"""([A-Za-z_:][\w:.-]*)\s*=\s*("[^"]*"|'[^']*')""")
ID_HEROI = re.compile(r"h_[a-z0-9_]+\Z")
NUM_ATTR = re.compile(r"[\w\s.,()+\-%]*\Z")


class Erro(Exception):
    """A problem of the inputs the session can fix (a missing slot, a text too long, a hero tag not allowed)."""


def ler_json(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise Erro("%s ilegível: %s" % (os.path.basename(caminho), e))
    if not isinstance(d, dict):
        raise Erro("%s não é um objeto" % os.path.basename(caminho))
    return d


def marca(trabalho):
    """The approved brand of the project that holds the working folder: name, colors, font lines, faces, logo."""
    d, erro = qa_atencao._ler_marca(trabalho)
    if erro:
        raise Erro(erro)
    nomes, _, _ = qa_atencao._cores_nomeadas(trabalho)
    cores = {k: nomes.get("cores." + k) for k in CORES}
    faltam = [k for k, v in cores.items() if not v]
    if faltam:
        raise Erro("marca sem cor: %s" % ", ".join(faltam))
    campos = d.get("campos") if isinstance(d.get("campos"), dict) else {}

    def valor(k):
        c = campos.get(k)
        return c.get("valor") if isinstance(c, dict) else None
    heading, body = valor("fontes.heading") or fontes.NEUTRA, valor("fontes.body") or fontes.NEUTRA
    raiz = os.path.abspath(trabalho)
    raiz = raiz[:raiz.find(os.sep + ".tune-up" + os.sep)] if os.sep + ".tune-up" + os.sep in raiz + os.sep else raiz
    logo = valor("logo")
    logo = os.path.join(raiz, logo) if isinstance(logo, str) and logo.strip() else None
    if logo and not (logo.lower().endswith(".svg") and os.path.isfile(logo)
                     and os.path.dirname(os.path.abspath(logo)).endswith(os.path.join("marca", "assets"))):
        logo = None  # a raster logo comes from fotos.py --logo (assets/logo.<ext>)
    face_t = kit_medida.face(fontes.pilha(heading)[0] or fontes.pilha(fontes.NEUTRA)[0])
    return {"nome": (valor("nome") or "").strip(), "cores": cores, "linhas_fonte": fontes.linhas(heading, body),
            # a regular heading face is set bold (the browser thickens it); a face already bold or black stays 400
            "peso_titulo": 400 if face_t and face_t["pesada"] else 700, "face_titulo": face_t,
            "face_texto": kit_medida.face(fontes.pilha(body)[0] or fontes.pilha(fontes.NEUTRA)[0]), "logo": logo}


def sobre(cores, fundo, grande=False, ordem=("bg", "text", "accent", "primary", "surface"), fora=()):
    """The brand color to write on `fundo`: the first of `ordem` reaching 4.5:1 (3:1 for big text), else the best."""
    piso = 3.0 if grande else 4.5
    notas = [(qa_atencao.contraste(cores[c], cores[fundo]), c) for c in ordem if c != fundo and c not in fora]
    for razao, c in notas:
        if razao >= piso:
            return c
    return max(notas)[1]


def destaque(cores, fundo, base, grande=True):
    """A second color for the key word on `fundo`, different from `base`; `base` again when none reaches 3:1."""
    for c in ("accent", "primary", "bg", "text"):
        if c not in (fundo, base) and qa_atencao.contraste(cores[c], cores[fundo]) >= (3.0 if grande else 4.5):
            return c
    return base


def escolha(semente, opcoes, pedido=None):
    """`pedido` when it is one of `opcoes`; else a stable pick from the seed (two businesses differ by default)."""
    if pedido in opcoes:
        return pedido
    return opcoes[zlib.crc32(semente.encode("utf-8")) % len(opcoes)]


def limpo(texto, maximo, onde):
    t = " ".join(str(texto or "").split())
    if not t:
        raise Erro("falta o texto de %s" % onde)
    if len(t) > maximo:
        raise Erro("%s com %d caracteres (máximo %d): '%s'" % (onde, len(t), maximo, t))
    if "!" in t or "—" in t:
        raise Erro("%s com '!' ou travessão: '%s'" % (onde, t))
    return t


def colar(texto):
    """Glue every 1-2 letter word to the next one (no line ends in "o", "E", "de") and "R$" to its number."""
    palavras, out = texto.split(" "), []
    for i, p in enumerate(palavras):
        out.append(p)
        if i < len(palavras) - 1:
            curta = re.fullmatch(r"[^\W\d_]{1,2}", p) or p in ("R$", "às", "até") or \
                (re.fullmatch(r"\(?\d[\d()]*", p) and re.match(r"\d", palavras[i + 1]))
            out.append(" " if curta else " ")
    return "".join(out)


def esc(texto):
    return html.escape(texto, quote=True).replace(" ", "&nbsp;")


def quebrar(texto, face, n, espaco=-0.02):
    """(widest line in em, lines) of `texto` in `n` lines (fewer when it has fewer words), the widest line as
    narrow as possible. Words glued by nbsp never split."""
    partes = colar(texto).split(" ")
    larg = [kit_medida.largura_em(p, face, espaco) for p in partes]
    vao = kit_medida.largura_em(" ", face, espaco)
    memo = {}

    def corte(i, k):
        if (i, k) in memo:
            return memo[(i, k)]
        if k == 1:
            r = (sum(larg[i:]) + vao * (len(partes) - i - 1), [partes[i:]])
        else:
            r = None
            for j in range(i + 1, len(partes) - k + 2):
                w = sum(larg[i:j]) + vao * (j - i - 1)
                resto = corte(j, k - 1)
                cand = (max(w, resto[0]), [partes[i:j]] + resto[1])
                if r is None or cand[0] < r[0]:
                    r = cand
        memo[(i, k)] = r
        return r
    em, linhas = corte(0, min(n, len(partes)))
    return em, [" ".join(l) for l in linhas]


def cheio(linhas, face, px, largura, espaco=-0.02):
    """How full the lines are (0-1): the mean of each line's width over the column. A headline of full lines
    reads as a block; a bigger size that leaves "para" alone on a line does not."""
    return sum(min(1.0, kit_medida.largura_em(l, face, espaco) * px / largura) for l in linhas) / len(linhas)


def caber(texto, face, largura, alto, max_px, min_px, linhas=(1, 2, 3), entrelinha=1.0, espaco=-0.02, piso=0):
    """Font size (px) and line breaks that fill `largura` x `alto` best: size times the root of how full the
    lines are, over the allowed line counts; a break that reaches `piso` px with lines 60% full or more wins
    over one that does not. Returns (px, lines, width of the widest line in px); px never goes under `min_px`
    (the returned width then tells it does not fit)."""
    melhor = None
    for n in sorted(set(linhas)):
        em, quebra = quebrar(texto, face, n, espaco)
        px = min(max_px, largura / em, alto / (len(quebra) * entrelinha))
        fill = cheio(quebra, face, px, largura, espaco)
        nota = (1 if px >= piso and fill >= 0.6 else 0, px * fill ** 0.5)
        if melhor is None or nota[0] > melhor[0][0] or (nota[0] == melhor[0][0] and nota[1] > melhor[0][1] * 1.02):
            melhor = (nota, px, quebra, em)
    px = max(min_px, int(melhor[1]))
    return px, melhor[2], melhor[3] * px


PRECO_RE = re.compile(r"(R\$) ?(\d{1,3}(?:\.\d{3})*)(,\d{2})?\Z")


def preco(valor, face, largura, alto, max_px, espaco=-0.02):
    """A price set as a designer does: a small raised "R$", the number as big as the column allows, small raised
    cents. Returns (px of the number, inner HTML, width) or None when `valor` is not a plain price."""
    m = PRECO_RE.match(valor)
    if not m:
        return None
    rs, num, cent = m.group(1), m.group(2), m.group(3) or ""
    em = kit_medida.largura_em(num, face, espaco) + 0.42 * (kit_medida.largura_em(rs, face, 0) + 0.12) \
        + 0.42 * kit_medida.largura_em(cent, face, 0)
    px = int(min(max_px, largura / em, alto))
    marc = '<span class="rs">%s</span>%s' % (esc(rs), esc(num))
    if cent:
        marc += '<span class="ct">%s</span>' % esc(cent)
    return px, marc, em * px


def preco_css(sel, px, teto=10000):
    """The small raised "R$" and cents of `preco`, for a number of `px` (sizes in px: the QA reads them);
    `teto` keeps them under the size any text beside the headline may have."""
    return ("%s .rs, %s .ct { font-size: %dpx; letter-spacing: 0; vertical-align: top; position: relative; "
            "top: .16em; } %s .rs { margin-right: .1em; }" % (sel, sel, max(28, min(teto, int(px * 0.42))), sel))


def largura_px(texto, face, px, espaco=0.0):
    return kit_medida.largura_em(texto, face, espaco) * px


def heroi(caminho):
    """Inner markup of `heroi.svg`, checked: basic shapes only, colors only by class, ids `h_*`.
    Returns (markup, set of ids). The drawing lives in a 1000x1000 box standing on y = 900."""
    try:
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
    except OSError as e:
        raise Erro("heroi.svg ilegível: %s" % e)
    if len(texto) > 60000:
        raise Erro("heroi.svg grande demais (%d caracteres, máximo 60000)" % len(texto))
    texto = re.sub(r"<!--.*?-->", "", texto, flags=re.S)
    m = re.search(r"<svg\b([^>]*)>(.*)</svg\s*>", texto, re.S | re.I)
    if not m:
        raise Erro("heroi.svg sem <svg>...</svg>")
    if not re.search(r"""viewBox\s*=\s*["']0 0 1000 1000["']""", m.group(1)):
        raise Erro('heroi.svg: o <svg> precisa de viewBox="0 0 1000 1000"')
    corpo, ids, formas = m.group(2), set(), 0
    if re.search(r"<\s*(?:script|style|foreignObject|image|use|text|a)\b|\bon\w+\s*=|javascript:|url\(|@import|&#",
                 corpo, re.I):
        raise Erro("heroi.svg: só formas básicas (sem script, style, text, image, use, url() nem eventos)")
    for fecha, tag, attrs, _ in TAG_RE.findall(corpo):
        tag = tag.lower()
        if tag not in HEROI_TAGS:
            raise Erro("heroi.svg: <%s> não é permitido (use %s)" % (tag, ", ".join(sorted(HEROI_TAGS))))
        if fecha:
            continue
        formas += tag != "g"
        resto = ATTR_RE.sub("", attrs).strip()
        if resto:
            raise Erro("heroi.svg: atributo sem aspas em <%s>: %s" % (tag, resto[:40]))
        for nome, valor in ATTR_RE.findall(attrs):
            nome, valor = nome.lower(), valor[1:-1]
            if nome not in HEROI_ATTRS:
                raise Erro("heroi.svg: atributo %s não é permitido em <%s>" % (nome, tag))
            if nome == "id":
                if not ID_HEROI.match(valor) or valor in ids:
                    raise Erro("heroi.svg: id '%s' inválido ou repetido (ids começam com h_)" % valor)
                ids.add(valor)
            elif nome == "class":
                fora = set(valor.split()) - HEROI_CLASSES
                if fora:
                    raise Erro("heroi.svg: classe %s não existe (cores só por: %s)"
                               % (", ".join(sorted(fora)), " ".join(sorted(HEROI_CLASSES))))
            elif nome == "fill":
                if valor != "none":
                    raise Erro('heroi.svg: fill="%s": cor só por classe (p a t b s) ou fill="none"' % valor)
            elif not NUM_ATTR.match(valor):
                raise Erro("heroi.svg: valor estranho em %s: %s" % (nome, valor[:40]))
    if formas < 12:
        raise Erro("heroi.svg com %d formas: um herói próprio tem 12 ou mais (corpo, volume, detalhe do briefing); "
                   "menos que isso é pictograma" % formas)
    if "h_corpo" not in ids:
        raise Erro('heroi.svg: falta o grupo <g id="h_corpo"> (a figura que fica o tempo todo)')

    def traco(m):
        # a stroke with no width of its own gets 14 px: a class rule would beat every `stroke-width` attribute
        # (the browser lets any CSS rule win over a presentation attribute), flattening the drawing's line weights
        if m.group(1) or "stroke-width" in m.group(3) or not re.search(r"""class\s*=\s*["'][^"']*\bl[patbs]\b""",
                                                                    m.group(3)):
            return m.group(0)
        return "<%s%s stroke-width=\"14\"%s>" % (m.group(2), m.group(3).rstrip(), m.group(4))
    return TAG_RE.sub(traco, corpo).strip(), ids


def alto_heroi(peca, chave="heroi_topo"):
    """Height of the drawing over its box (0.4-0.9), from `heroi_topo` in peca.json: the y of its highest point
    in the 1000x1000 box (the ground is y = 900). Default 100: a drawing that fills the box. With
    `chave="heroi_topo_antes"`: the same for the problem state, when the reel's hook shows a shorter hero."""
    if peca.get("heroi") == "foto":
        return 0.92  # the photo's frame is 4:5: its height is 0.9 of the hero width
    try:
        topo = float(peca.get(chave, peca.get("heroi_topo", 100)))
    except (TypeError, ValueError):
        topo = 100.0
    return (900 - max(0.0, min(500.0, topo))) / 1000.0 + 0.02


def copiar_logo(m, destino):
    """Copy the brand's SVG logo to <destino>/assets/logo.svg; the name of the logo file in assets, or None."""
    pasta = os.path.join(destino, "assets")
    if m["logo"]:
        os.makedirs(pasta, exist_ok=True)
        with open(m["logo"], encoding="utf-8") as f:
            texto = f.read()
        with open(os.path.join(pasta, "logo.svg"), "w", encoding="utf-8") as f:
            f.write(texto)
        return "logo.svg"
    for nome in sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []:
        if re.fullmatch(r"logo\.(png|jpe?g|webp)", nome):
            return nome
    return None


def foto(destino):
    """The main photo fotos.py copied to <destino>/assets (foto1.<ext>), or None."""
    pasta = os.path.join(destino, "assets")
    for nome in sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []:
        if re.fullmatch(r"foto1\.(png|jpe?g|webp)", nome):
            return nome
    return None


def canal(nome):
    if nome not in CANAIS:
        raise Erro("canal '%s' não existe: use %s" % (nome, ", ".join(sorted(CANAIS))))
    return CANAIS[nome]


def pontos(x, y, colunas, linhas_, passo, raio, classe):
    """A dot grid (texture) as circles: flat brand color, the same in every render."""
    return "".join('<circle class="%s" cx="%d" cy="%d" r="%d"/>' % (classe, x + i * passo, y + j * passo, raio)
                   for j in range(linhas_) for i in range(colunas))
