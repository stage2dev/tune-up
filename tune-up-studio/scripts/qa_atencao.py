"""Attention QA (flag --atencao): hook, amount of text, type floor, brand colors, layout variety, CTA,
AI tics, invented numbers, a visual device that is not text and legibility (text-wrap, clipped letters). Imported by qa_imagem.py, qa_video.py and anuncio.py, never run on its own.

It reads text only (HTML, CSS, estrategia.md, copy.md, entrada.md, marca.json): no browser, no pixels.
Every check returns {"name", "ok", "details"} like qa_imagem.result. Thresholds are the constants below.
HTML/CSS reading is in qa_css.py (with the selector contract), the video checks in qa_cenas.py.
Python 3.9+, standard library plus cores.py and descobrir_marca.py (neutral palette).
"""
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cores  # noqa: E402
import qa_css  # noqa: E402
from descobrir_marca import CAMPOS, PALETA_NEUTRA  # noqa: E402

TIQUES = ("—", "nao e so", "nao e apenas", "mais do que um", "diga adeus", "proximo nivel", "descubra o poder",
          "no mundo corrido", "seja voce", "experiencia unica", "o resultado?", "o melhor:", "pare de rolar",
          "venha conhecer", "qualidade e tradicao", "imagine so")
TIQUES_ARTE = ("!",)
LAYOUTS_POST = ("l-titulo", "l-numero", "l-foto", "l-lista", "l-antes-depois", "l-citacao", "l-oferta", "l-cheia")
LAYOUTS_VIDEO = ("l-topo", "l-base", "l-cheia", "l-numero", "l-faixa", "l-foto", "l-lista")
POST_TITULO_MIN, POST_OUTRO_MIN, POST_RAZAO = 88, 28, 1.8
POST_PALAVRAS_CAPA, POST_PALAVRAS = 20, 30
VIDEO_TITULO_MIN, VIDEO_OUTRO_MIN = 96, 44
CENAS = {10: (4, 5), 15: (5, 6)}
CENA1_MAX, CENA_ULTIMA_MIN, CENA_MIN, FOLGA = 2.0, 2.5, 1.5, 0.05
TRANSICAO = (0.4, 0.8)
TITULO_CHARS = 40
LEGENDA_LINHA1, LEGENDA_MAX, HASHTAGS_MAX = 125, 1000, 5
ESTRATEGIA = ("objetivo", "publico", "promessa", "arquetipo", "gancho 1", "gancho 2", "gancho 3", "escolhido", "cta")
MAX_DETALHES = 20
QUADRO_RE = re.compile(r"q([1-9]\d*)\Z")
NUM_RE = re.compile(r"\d+(?:[.,]\d+)*")
CORRIDA_RE = re.compile(r"\d[\d\s().,/-]*\d")  # a phone or price written in pieces: "(11) 4002-8922", "12 ,90"
# Visual device (referencias/recursos-visuais.md): a shape or svg covering 2% to 85% of the frame; a band as
# wide or as tall as the frame (90%) only when rotated, round or cut; a text of 200 px or more.
RECURSO_MIN, RECURSO_MAX, FAIXA, GIGANTE_PX = 0.02, 0.85, 0.9, 200
SVG_PARTES = {"g", "defs", "rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "lineargradient",
              "radialgradient", "stop", "text", "tspan", "use", "symbol", "clippath", "mask"}
FOLGA_TOPO, FOLGA_BASE, LINHA_LIVRE = 0.1, 0.15, 1.2  # em of padding (or line-height) a clipped text needs
# A headline breaks by meaning: a sentence end followed by more text on the same line, and a 1-2 letter word
# (o, a, E, de, às) before a breakable space, which the browser may leave alone at the end of a line.
FRASE_RE = re.compile(r"[.?!\u2026](?=\s+\S)")
ABREVIACAO_RE = re.compile(r"(?:^|\s)(?:dr|dra|sr|sra|prof|profa|av|n)\.\Z", re.I)
CURTA_RE = re.compile(r"[^\W\d_]{1,2}\Z")
# A real deadline of the briefing (compared without accents): the art keeps it (the captured part).
MESES = "janeiro|fevereiro|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro"
DIAS = "domingo|segunda|terca|quarta|quinta|sexta|sabado"
PRAZO_RES = (
    re.compile(r"\b(?:so|somente|apenas)\s+(?:ate\s+)?(hoje|amanha|n?est[ae] (?:semana|mes|fim de semana)|"
               r"em (?:%s)|(?:o )?dia \d{1,2}(?:/\d{1,2})?|\d{1,2}/\d{1,2}|(?:%s))\b" % (MESES, DIAS)),
    re.compile(r"\bate\s+(?:o\s+)?(?:dia\s+)?(\d{1,2}/\d{1,2}|\d{1,2} de (?:%s))\b" % MESES),
    re.compile(r"\bate\s+(?:o\s+|a\s+)?(?:proxim[oa]\s+)?((?:%s)(?:-feira)?)\b" % DIAS),
    re.compile(r"\b(ultim[oa]s (?:dias|unidades|vagas|pecas)|ultima semana|ultimo dia)\b"),
)
# The offer word of the briefing (compared without accents): when the briefing has one, the art shows it big.
OFERTA_RE = re.compile(r"\b(gratis|gratuit[ao]s?|de graca|sem custo|desconto|promocao|brinde|cortesia|"
                       r"\d+ ?%(?: off)?|frete gratis|leve \d+ pague \d+)(?!\w)")
OFERTA_POST_PX = 64  # a post's offer word sits in the h1, the CTA band or a text of 64 px or more
# A price of the briefing ("R$ 89") is the second level: in the h1 or a text of PRECO_POST_PX or more (a post), in a
# `_titulo`/`_destaque` (a reel), never a 40-72 px sticker. The `#oferta` text (the price or offer) is the giant
# number of the offer stack: it may be up to 1.7 times the h1 (the h1 is POST_RAZAO_OFERTA of it or more); since
# round 6 (was 1.1x the other way: the judge asked for the price as a real second level, 160 px or more).
PRECO_RE = re.compile(r"(?<!acima de )(?<!compras de )r\$ ?(\d+(?:\.\d{3})*(?:,\d+)?)")  # a threshold is no price
PRECO_POST_PX, POST_RAZAO_OFERTA = 96, 0.58
REF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "referencias")
ESTILOS_VIDEO = "estilos-video"
MOLDE_RE = re.compile(r'"([^"\n]{8,80})"')


def resultado(nome, problemas):
    return {"name": nome, "ok": not problemas, "details": (problemas or ["ok"])[:MAX_DETALHES]}


def _norm(texto):
    """Lowercase, no accents, spaces collapsed: how tics are compared."""
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return " ".join("".join(c for c in t if not unicodedata.combining(c)).split())


def achar_tiques(texto, arte=True):
    """Tics in `texto`, whole words only (`nao e so` never matches `não é solução`); `!` only in art."""
    n, achados = _norm(texto), []
    for t in TIQUES + (TIQUES_ARTE if arte else ()):
        if len(t) == 1 and not t.isalnum():
            hit = t in n
        else:
            hit = re.search(r"(?<!\w)%s(?!\w)" % re.escape(t), n)
        if hit:
            achados.append(t)
    return achados


def numeros(texto):
    """Number tokens with 2+ digits, `.`/`,` between digits removed: "1.240" -> "1240"; "6h40" -> "40"."""
    return [n for n in (re.sub(r"[.,]", "", m) for m in NUM_RE.findall(texto or "")) if len(n) >= 2]


def palavras(texto):
    return sum(1 for t in (texto or "").split() if re.search(r"[^\W_]", t))


# ---------- brand and facts ----------

def _ler_marca(caminho):
    """(marca.json object, error) for a path inside <project>/.tune-up/."""
    p, marca = os.path.abspath(caminho) + os.sep, os.sep + ".tune-up" + os.sep
    i = p.find(marca)
    texto = qa_css.ler_arquivo(os.path.join(p[:i], ".tune-up", "estudio", "marca", "marca.json")) if i >= 0 else None
    if texto is None:
        return None, "marca.json não encontrado"
    try:
        d = json.loads(texto)
    except (ValueError, RecursionError) as exc:
        return None, "marca.json ilegível: %s" % exc
    return (d, None) if isinstance(d, dict) else (None, "marca.json não é um objeto")


def _cores_nomeadas(caminho):
    """({"cores.bg": "#FFF8EC", ...}, every allowed hex, error). A cores.X with no value takes the neutral one."""
    d, erro = _ler_marca(caminho)
    if erro:
        return {}, set(), erro
    campos = d.get("campos") if isinstance(d.get("campos"), dict) else {}
    nomes = {}
    for k in [c for c in CAMPOS if c.startswith("cores.")] + sorted(set(campos) - set(CAMPOS)):
        c = campos.get(k)
        h = cores.para_hex(c.get("valor")) if isinstance(c, dict) and k.startswith("cores.") else None
        h = h or (cores.para_hex(PALETA_NEUTRA[k]) if k in PALETA_NEUTRA else None)
        if h:
            nomes[k] = h
    neutra = d.get("paleta_neutra") if isinstance(d.get("paleta_neutra"), dict) else {}
    return nomes, set(nomes.values()) | ({cores.para_hex(v) for v in neutra.values()} - {None}), None


def cores_da_marca(caminho):
    """(set of "#RRGGBB" the piece may use, error)."""
    _, permitidas, erro = _cores_nomeadas(caminho)
    return permitidas, erro


def contraste(hex_a, hex_b):
    """WCAG contrast ratio of two colors, 2 decimals."""
    def lum(h):
        h = cores.para_hex(h)
        lin = [(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
               for c in (int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    a, b = sorted((lum(hex_a), lum(hex_b)))
    return round((b + 0.05) / (a + 0.05), 2)


def pares(trabalho):
    """Text x background pairs of the brand colors with ratio >= 3, best first; uso normal (>= 4.5) or so_titulo."""
    nomes, _, _ = _cores_nomeadas(trabalho)
    out = []
    for t, th in nomes.items():
        for f, fh in nomes.items():
            r = contraste(th, fh)
            if r >= 3.0:
                out.append({"texto": t, "texto_hex": th, "fundo": f, "fundo_hex": fh, "razao": r,
                            "uso": "normal" if r >= 4.5 else "so_titulo"})
    return sorted(out, key=lambda p: (-p["razao"], p["texto"], p["fundo"]))


def imprimir_pares(trabalho):
    """Print one line per pair; 0, or 2 when there is no brand."""
    _, _, erro = _cores_nomeadas(trabalho)
    if erro:
        print("%s (procurei a partir de %s)" % (erro, trabalho), file=sys.stderr)
        return 2
    lista = pares(trabalho)
    for p in lista:
        print("texto %s %s sobre %s %s: %.2f:1 %s" % (p["texto"], p["texto_hex"], p["fundo"], p["fundo_hex"],
                                                      p["razao"], p["uso"]))
    if not lista:
        print("nenhum par das cores da marca chega a 3:1")
    return 0


def briefing_ausente(trabalho):
    """Why the facts cannot be read (no or empty <trabalho>/entrada.md), or None. Every fact check says it out loud."""
    texto = qa_css.ler_arquivo(os.path.join(trabalho, "entrada.md"))
    if texto is None:
        return "entrada.md não encontrado em %s: o QA lê os fatos só desse arquivo (grave nele o briefing)" % trabalho
    return None if texto.strip() else "entrada.md vazio em %s: o QA lê os fatos só desse arquivo" % trabalho


def _pedacos(texto):
    """Every stretch of a run of digits and separators that starts and ends on a digit: "12 ,90, (11) 4002-8922"
    gives "12 ,90", "90, (11)", "(11) 4002-8922"... A number may be written in pieces; neighbors may be glued."""
    for m in CORRIDA_RE.finditer(texto or ""):
        grupos = list(re.finditer(r"\d+", m.group(0)))[:8]
        for i in range(len(grupos)):
            for j in range(i, len(grupos)):
                yield m.group(0)[grupos[i].start():grupos[j].end()]


def _digitos(texto):
    """Digits of every number written in pieces ("(11) 4002-8922" -> "1140028922"); ",00" also without cents."""
    out = set()
    for trecho in _pedacos(texto):
        if trecho.isdigit():  # a single group is already a token of numeros()
            continue
        d = re.sub(r"\D", "", trecho)
        out |= {d, d[:-2]} if re.search(r"[.,]00\Z", trecho) else {d}
    return out


def fatos(trabalho):
    """(number tokens plus the digits of numbers written in pieces, casefolded text) of entrada.md and the text
    values of marca.json (never colors or logo)."""
    textos = [qa_css.ler_arquivo(os.path.join(trabalho, "entrada.md")) or ""]
    d, _ = _ler_marca(trabalho)
    campos = d.get("campos") if d and isinstance(d.get("campos"), dict) else {}
    for k, c in sorted(campos.items()):
        if isinstance(c, dict) and isinstance(c.get("valor"), str) and not k.startswith("cores.") and k != "logo":
            textos.append(c["valor"])
    junto = "\n".join(textos)
    return set(numeros(junto)) | _digitos(junto), " ".join(junto.casefold().split())


def _numeros_fora(texto, conhecidos):
    """Number tokens of `texto` not in the facts; a token passes when the number written in pieces around it
    ("R$ 12<small>,90</small>", a phone with other separators) is a known one."""
    inteiros = set()
    for trecho in _pedacos(texto):
        if len(re.sub(r"\D", "", trecho)) >= 2 and re.sub(r"\D", "", trecho) in conhecidos[0]:
            inteiros.update(numeros(trecho))
    out = []
    for n in numeros(texto):
        if n not in conhecidos[0] and n not in inteiros and n not in out:
            out.append(n)
    return out


def prazos(texto):
    """Deadlines written in a text ("só esta semana" -> "esta semana", "até 15/12", "até sábado"), without accents."""
    out = []
    for rx in PRAZO_RES:
        for m in rx.finditer(_norm(texto)):
            if m.group(1) not in out:
                out.append(m.group(1))
    return out


def faltam_prazos(arte, trabalho):
    """Each deadline of entrada.md that the art does not show: the condition and the deadline sell, never cut."""
    feito = _norm(arte)
    return ["prazo do briefing '%s' não está na arte: condição e prazo reais vão junto do CTA (corte o apoio "
            "antes de cortar o prazo)" % p for p in prazos(qa_css.ler_arquivo(os.path.join(trabalho, "entrada.md"))
                                                         or "") if p not in feito]


def ofertas(trabalho):
    """The offer words of entrada.md ("gratuita", "20%", "desconto"), without accents."""
    return sorted({m.group(1) for m in OFERTA_RE.finditer(_norm(qa_css.ler_arquivo(
        os.path.join(trabalho, "entrada.md")) or ""))})


def _moldes():
    """The pt-BR molds quoted in referencias/*.md (3 words or more, &nbsp; as a space), without accents."""
    out = set()
    pastas = [REF, os.path.join(REF, ESTILOS_VIDEO)]   # the style files carry molds too
    for caminho in sorted(os.path.join(p, n) for p in pastas if os.path.isdir(p) for n in os.listdir(p)):
        if caminho.endswith(".md"):
            for m in MOLDE_RE.finditer(qa_css.ler_arquivo(caminho) or ""):
                t = _norm(m.group(1).replace("&nbsp;", " ").replace("<br>", " "))
                if len(t.split()) >= 3 and len(t) >= 12 and not re.search(r"[<>=|(){};_]", t):
                    out.add(" ".join(re.sub(r"[.,;:?]", " ", t).split()))
    return out


def check_molde(textos, trabalho):
    """`molde`: no headline copies a mold of the references word for word (the swap test); a mold the briefing
    itself writes is a fact and passes. Calls ("Peça pelo WhatsApp") are generic by nature and are not compared."""
    texto = qa_css.ler_arquivo(os.path.join(trabalho, "entrada.md"))
    if texto is None:  # without the briefing a mold cannot be told from a fact; other checks report it missing
        return resultado("molde", [])
    briefing, out = _norm(texto), []
    for t in textos:
        n = " %s " % " ".join(_norm(re.sub(r"[.,;:?]", " ", t)).split())
        for m in sorted(_moldes()):
            if " %s " % m in n and m not in briefing:
                out.append("'%s' copia o molde das referências ('%s'): escreva a partir do briefing" % (t.strip(), m))
    return resultado("molde", out)


def estilos_video():
    """The video styles: one file each in referencias/estilos-video/ (the file name without .md)."""
    pasta = os.path.join(REF, ESTILOS_VIDEO)
    return sorted(n[:-3] for n in os.listdir(pasta) if n.endswith(".md")) if os.path.isdir(pasta) else []


def check_estilo(pasta, montado):
    """`estilo` (reel): estrategia.md names the chosen style (`estilo: <file name> | why`), it is one of the
    style files, and it is the style the composition was assembled with (`data-estilo` on #root)."""
    texto = qa_css.ler_arquivo(os.path.join(pasta, "estrategia.md"))
    if texto is None:  # the `estrategia` check already says the file is missing
        return resultado("estilo", [])
    m = re.search(r"^[-* ]*estilo\s*:\s*([^|\n]+)", texto, re.M | re.I)
    escolhido = m.group(1).strip() if m else ""
    validos = estilos_video()
    if not escolhido:
        return resultado("estilo", ["estrategia.md sem estilo: escreva `estilo: <arquivo do estilo> | <por quê>` "
                                    "(um de: %s)" % ", ".join(validos)])
    if escolhido not in validos:
        return resultado("estilo", ["estilo '%s' não existe: use um de %s" % (escolhido, ", ".join(validos))])
    if montado and montado != escolhido:
        return resultado("estilo", ["estrategia.md diz estilo '%s' mas o vídeo foi montado com '%s': ponha o mesmo "
                                    "em peca.json e rode montar.py de novo" % (escolhido, montado)])
    return resultado("estilo", [])


def check_oferta(trechos, trabalho):
    """`oferta_destaque`: each offer word of the briefing is in one of `trechos` (the texts that sell big)."""
    feitos = _norm(" ".join(trechos))
    return resultado("oferta_destaque", ["a oferta '%s' do briefing não está em destaque (título, destaque ou "
                                         "texto grande): é a palavra que vende" % o
                                         for o in ofertas(trabalho) if o not in feitos])


def precos(trabalho):
    """The prices of entrada.md ("R$ 89" -> "89"), without accents."""
    return sorted({m.group(1) for m in PRECO_RE.finditer(_norm(qa_css.ler_arquivo(
        os.path.join(trabalho, "entrada.md")) or ""))})


def check_preco(trechos, trabalho, onde):
    """`preco_destaque`: each price of the briefing is written in one of `trechos` (the big texts)."""
    feitos = _norm(" ".join(trechos))
    return resultado("preco_destaque", ["o preço R$ %s do briefing não está grande (%s): é o segundo nível, com o "
                                        "nome da oferta junto" % (v, onde) for v in precos(trabalho)
                                        if not re.search(r"r\$ ?%s(?![\d,])" % re.escape(v), feitos)])


def nome_marca(trabalho):
    d, _ = _ler_marca(trabalho)
    campos = d.get("campos") if d and isinstance(d.get("campos"), dict) else {}
    v = (campos.get("nome") or {}).get("valor") if isinstance(campos.get("nome"), dict) else None
    return v.strip() if isinstance(v, str) and v.strip() else None


def check_marca(texto, trabalho, onde):
    """The brand name (campos.nome) written on the art: a logo that is only a symbol is recognized by nobody."""
    nome = nome_marca(trabalho)
    if not nome or _norm(nome) in _norm(texto):
        return resultado("marca", [])
    return resultado("marca", ["o nome da marca '%s' não está escrito %s: ponha-o junto do logo" % (nome, onde)])


def check_numeros(texto, trabalho):
    erro = briefing_ausente(trabalho)
    return resultado("numeros", ([erro] if erro else []) + ["número %s não está no briefing (entrada.md) nem na marca"
                                                          % n for n in _numeros_fora(texto, fatos(trabalho))])


def check_tiques(texto):
    return resultado("tiques", ["tique na arte: %s" % t for t in achar_tiques(texto)])


def check_estrategia(pasta):
    texto = qa_css.ler_arquivo(os.path.join(pasta, "estrategia.md"))
    if texto is None:
        return resultado("estrategia", ["estrategia.md não encontrado"])
    vals = {}
    for linha in texto.splitlines():
        k, sep, v = linha.strip().lstrip("-*").partition(":")
        if sep and v.strip():
            vals.setdefault(_norm(k), v.strip())
    return resultado("estrategia", ["estrategia.md sem %s" % k for k in ESTRATEGIA if k not in vals])


def check_cores(doc, caminho):
    permitidas, erro = cores_da_marca(caminho)
    return resultado("cores_marca", [erro] if erro else qa_css.problemas_cores(doc, permitidas))


def check_fonte_minima(doc, minimo, alvos):
    """Every font-size in px and >= minimo, no `font:` shorthand, #root with a px size; `alvos` are
    (label, element, matcher, own minimum) that must resolve to a px size by the selector contract."""
    out = []
    for onde, k, v in qa_css.todas_decls(doc):
        px = qa_css.valor_px(v)
        if k == "font":
            out.append("%s: use font-size, não font:" % onde)
        elif k == "font-size" and px is None:
            out.append("%s: font-size %s não está em px" % (onde, v))
        elif k == "font-size" and px < minimo:
            out.append("%s: %g px (mínimo %d)" % (onde, px, minimo))
    root = next((e for e in doc["elementos"] if e["id"] == "root"), None)
    casa_root = lambda s: re.search(r"#root(?![\w-])", qa_css.ultimo_composto(s))  # noqa: E731
    if root is None or qa_css.valor_px(qa_css.ultimo(qa_css.decls(doc, root, casa_root), "font-size")) is None:
        out.append("#root sem font-size em px")
    for rotulo, el, casa, piso in alvos:
        px = qa_css.valor_px(qa_css.ultimo(qa_css.decls(doc, el, casa), "font-size"))
        if px is None:
            out.append("%s sem font-size em px na própria regra" % rotulo)
        elif px < piso:
            out.append("%s: %g px (mínimo %d)" % (rotulo, px, piso))
    return resultado("fonte_minima", out)


def layout(doc, el_id, validos):
    """The one valid l-* class of the element with this id, or None."""
    el = next((e for e in doc["elementos"] if e["id"] == el_id), None) if doc else None
    ls = [c for c in (el["classes"] if el else []) if c.startswith("l-")]
    return ls[0] if len(ls) == 1 and ls[0] in validos else None


def sequencia(rotulos, layouts):
    return ["%s e %s com o mesmo %s" % (rotulos[i - 1], rotulos[i], layouts[i])
            for i in range(1, len(layouts)) if layouts[i] and layouts[i] == layouts[i - 1]]


# ---------- post ----------

PSEUDO_RE = re.compile(r"::|:(?:before|after|first-letter|first-line)(?![\w-])", re.I)


def _h1(sel):
    """A selector of the h1 itself; a pseudo-element (h1::before, a quote mark) is not the h1's text."""
    composto = qa_css.ultimo_composto(sel)
    return re.match(r"h1(?![\w-])", composto, re.I) and not PSEUDO_RE.search(composto)


def _casa_texto(el):
    """Selectors that size this element's own text: its id, a class or its tag, never a pseudo-element."""
    amplo = qa_css.amplo(el)
    tag = re.compile(r"%s(?![\w-])" % re.escape(el["tag"]), re.I)
    return lambda s: not PSEUDO_RE.search(qa_css.ultimo_composto(s)) and \
        bool(amplo(s) or tag.match(qa_css.ultimo_composto(s)))


def _check_titulo(doc, h1s):
    if len(h1s) != 1:
        return resultado("titulo", ["%d elementos <h1> (precisa de exatamente um)" % len(h1s)])
    out, texto = [], qa_css.texto_de(h1s[0])
    if len(texto) > TITULO_CHARS:
        out.append("título com %d caracteres (máximo %d): %s" % (len(texto), TITULO_CHARS, texto))
    tam = qa_css.valor_px(qa_css.ultimo(qa_css.decls(doc, h1s[0], _h1), "font-size"))
    # Only elements whose text has a letter or digit compete with the h1: a quote mark alone (l-citacao) or a
    # rule for an element that is not in the page never does.
    competem = [e for e in doc["elementos"] if e is not h1s[0] and re.search(r"[^\W_]", qa_css.texto_de(e))
                and not _decorativo(e) and "h1" not in e["dentro"]]
    px = lambda e: qa_css.valor_px(qa_css.ultimo(qa_css.decls(doc, e, _casa_texto(e)), "font-size"))  # noqa: E731
    outros = [px(e) for e in competem if e["id"] != "oferta"]
    oferta = [px(e) or 0 for e in competem if e["id"] == "oferta"]
    maior = max([x for x in outros if x is not None] or [0])
    if tam is None:
        out.append("h1 sem font-size em px (regra de h1 ou style do h1)")
    elif tam < POST_TITULO_MIN or tam < POST_RAZAO * maior:
        out.append("h1 com %g px: precisa de %d px ou mais e %.1fx o maior outro texto (%g px)"
                   % (tam, POST_TITULO_MIN, POST_RAZAO, maior))
    elif oferta and tam < POST_RAZAO_OFERTA * max(oferta):
        out.append("#oferta com %g px: no máximo 1,7 vezes o h1 (%g px), que continua a frase maior"
                   % (max(oferta), tam))
    return resultado("titulo", out)


def checar_quadro(fonte):
    """Checks of one post frame (q<N>/fonte): titulo, fonte_minima, palavras, cores_marca, tiques, numeros,
    layout_post."""
    doc = qa_css.ler_fonte(fonte)
    if doc is None:
        return [resultado(n, ["index.html não encontrado em %s" % fonte]) for n in
                ("titulo", "fonte_minima", "palavras", "cores_marca", "tiques", "numeros", "layout_post",
                 "recurso_visual", "legibilidade")]
    m = QUADRO_RE.match(os.path.basename(os.path.dirname(os.path.abspath(fonte))))
    trabalho = os.path.dirname(os.path.dirname(os.path.abspath(fonte)) if m else os.path.abspath(fonte))
    h1s = [e for e in doc["elementos"] if e["tag"] == "h1"]
    n = int(m.group(1)) if m else 1
    # A carousel cover only raises the question (20 words); a single post carries the whole piece: hook, offer
    # stack (name + value + proof) and the call with its condition and contact (30, as any other frame).
    capa = n == 1 and os.path.isdir(os.path.join(trabalho, "q2"))
    limite, total = POST_PALAVRAS_CAPA if capa else POST_PALAVRAS, palavras(doc["texto"])
    nome = nome_marca(trabalho)
    if nome:  # the brand name beside the logo is not read as copy (the reel does the same)
        total -= _norm(doc["texto"]).count(_norm(nome)) * palavras(nome)
    root = next((e for e in doc["elementos"] if e["id"] == "root"), None)
    ls = [c for c in (root["classes"] if root else []) if c.startswith("l-")]
    lay = [] if layout(doc, "root", LAYOUTS_POST) else \
        ["#root precisa de exatamente um de %s (achei: %s)" % (" ".join(LAYOUTS_POST), " ".join(ls) or "nenhum")]
    return [_check_titulo(doc, h1s),
            check_fonte_minima(doc, POST_OUTRO_MIN, [("h1", h1s[0], _h1, POST_TITULO_MIN)] if len(h1s) == 1 else []),
            resultado("palavras", [] if total <= limite else ["q%d com %d palavras (máximo %d)" % (n, total, limite)]),
            check_cores(doc, fonte), check_tiques(doc["texto"]), check_numeros(doc["texto"], trabalho),
            resultado("layout_post", lay), check_recurso_quadro(doc), check_legibilidade(doc, titulos=h1s)]


def _check_legenda(pasta):
    texto = qa_css.ler_arquivo(os.path.join(pasta, "copy.md"))
    m = re.search(r"^##\s*legenda\s*$", texto or "", re.I | re.M)
    if not m:
        return resultado("legenda", ["copy.md não encontrado" if texto is None else "copy.md sem ## Legenda"])
    corpo = texto[m.end():]
    prox = re.search(r"^##\s", corpo, re.M)
    corpo = (corpo[:prox.start()] if prox else corpo).strip()
    primeira = corpo.splitlines()[0].strip() if corpo else ""
    out = [] if primeira else ["legenda vazia"]
    if len(primeira) > LEGENDA_LINHA1:
        out.append("1ª linha com %d caracteres (máximo %d)" % (len(primeira), LEGENDA_LINHA1))
    if len(corpo) > LEGENDA_MAX:
        out.append("legenda com %d caracteres (máximo %d)" % (len(corpo), LEGENDA_MAX))
    tags = re.findall(r"(?<![\w&#])#\w+", corpo)
    if len(tags) > HASHTAGS_MAX:
        out.append("%d hashtags (máximo %d)" % (len(tags), HASHTAGS_MAX))
    out += ["tique na legenda: %s" % t for t in achar_tiques(corpo, arte=False)]
    # The caption is published text too: its numbers come from the briefing or the brand (hashtags excepted).
    sem_tags = re.sub(r"(?<![\w&#])#\w+", " ", corpo)
    out += ["legenda: %s" % d for d in check_numeros(sem_tags, pasta)["details"] if d != "ok"]
    return resultado("legenda", out)


def checar_peca_post(pasta, quadros):
    """Checks of the whole post (--final): estrategia, cta (with the briefing's deadline), sequencia_layout,
    arraste, legenda, marca (the brand name written in some frame).
    `quadros`: frame names ("q1"), numbers or q<N> paths."""
    nomes = sorted({"q%d" % q if isinstance(q, int) else os.path.basename(os.path.normpath(q)) for q in quadros},
                   key=lambda x: int(QUADRO_RE.match(x).group(1)) if QUADRO_RE.match(x) else 0)
    docs = [qa_css.ler_fonte(os.path.join(pasta, x, "fonte")) for x in nomes]
    cta = [] if nomes else ["nenhum quadro"]
    for i, (nome, doc) in enumerate(zip(nomes, docs)):
        els = [e for e in (doc["elementos"] if doc else []) if e["id"] == "cta"]
        if i < len(nomes) - 1 and els:
            cta.append("%s tem #cta (só o último quadro pede a ação)" % nome)
        if i == len(nomes) - 1 and not any(qa_css.texto_de(e) for e in els):
            cta.append("%s (último) sem #cta com texto" % nome)
        for e in els:
            if not qa_css.zero(qa_css.ultimo(qa_css.decls(doc, e, qa_css.amplo(e)), "border-radius")):
                cta.append("%s: #cta com border-radius (um post não é clicável)" % nome)
    arraste = []
    if len(nomes) >= 2 and "arraste" not in _norm(docs[0]["texto"] if docs[0] else ""):
        arraste.append("capa de carrossel sem 'arraste'")
    layouts = [layout(d, "root", LAYOUTS_POST) for d in docs]
    arte = " ".join(d["texto"] for d in docs if d)
    if nomes:
        cta += faltam_prazos(arte, pasta)
    grandes, titulos, enormes = [], [], []
    for d in docs:
        for e in (d["elementos"] if d else []):
            px = qa_css.valor_px(qa_css.ultimo(qa_css.decls(d, e, qa_css.amplo(e)), "font-size"))
            if e["tag"] == "h1" or e["id"] == "cta" or (px or 0) >= OFERTA_POST_PX:  # the CTA sits on its band
                grandes.append(qa_css.texto_de(e))
            if e["tag"] == "h1" or (px or 0) >= PRECO_POST_PX:
                enormes.append(qa_css.texto_de(e))
            if e["tag"] == "h1":
                titulos.append(qa_css.texto_de(e))
    return [check_estrategia(pasta), resultado("cta", cta), resultado("sequencia_layout", sequencia(nomes, layouts)),
            resultado("arraste", arraste), _check_legenda(pasta), check_marca(arte, pasta, "em nenhum quadro"),
            check_oferta(grandes, pasta), check_preco(enormes, pasta, "h1 ou texto de %d px ou mais" % PRECO_POST_PX),
            check_molde(titulos, pasta)]


def item_peca(pasta, quadros):
    """checar_peca_post as an item of qa_imagem.run_final: {"frame": "peca", "ok", "failed", "checks"}."""
    checks = checar_peca_post(pasta, quadros)
    return {"frame": "peca", "ok": all(c["ok"] for c in checks),
            "failed": [c["name"] for c in checks if not c["ok"]], "checks": checks}


# ---------- visual device and legibility (post, ad and reel) ----------

def _decorativo(el):
    """A text marked as texture (the giant bleeding word): aria-hidden, never the text to read."""
    return el["attrs"].get("aria-hidden", "").lower() == "true"


def _decls_el(doc, el):
    """(own declarations, own + the steps of its animations) of an element: id, classes, tag, style=""."""
    proprio = qa_css.decls(doc, el, _casa_texto(el))
    passos = [d for nome in qa_css.nomes_animacao(proprio) for _, ds in doc["quadros"].get(nome, []) for d in ds]
    return proprio, proprio + passos


def _tem_fundo(decl):
    fundos = [v for k, v in decl if k in ("background", "background-color")]
    return any(v.strip().lower() not in ("none", "transparent", "initial", "inherit", "unset", "") for v in fundos)


def _tem_forma(decl):
    """Rotated, skewed, round or cut by a clip-path shape: a band like that reads as a device, not a background."""
    for k, v in decl:
        low = v.lower()
        if (k == "transform" and re.search(r"rotate|skew", low)) or (k == "border-radius" and not qa_css.zero(low)) \
                or (k == "clip-path" and re.search(r"polygon|circle|ellipse|path", low)):
            return True
    return False


def tamanho_quadro(doc):
    """(width, height) of #root from its own rule, else its data-width/data-height, else 1080x1350."""
    root = next((e for e in doc["elementos"] if e["id"] == "root"), None)
    if root is None:
        return 1080.0, 1350.0
    decl = qa_css.decls(doc, root, qa_css.amplo(root))
    out = []
    for prop, attr, padrao in (("width", "data-width", 1080.0), ("height", "data-height", 1350.0)):
        v = qa_css.valor_px(qa_css.ultimo(decl, prop))
        try:
            v = v or float(root["attrs"].get(attr, ""))
        except ValueError:
            v = padrao
        out.append(v)
    return tuple(out)


def recurso(doc, el, largura, altura):
    """Which visual device this element is ("foto", "svg", "forma", "texto gigante", "marca-texto") or None."""
    if el["id"] == "root" or "svg" in el["dentro"] or el["tag"] in SVG_PARTES:
        return None
    proprio, tudo = _decls_el(doc, el)
    if el["tag"] == "img":
        nome = os.path.basename(el["attrs"].get("src", "")).lower()
        return "foto" if nome and not nome.startswith("logo") else None
    if qa_css.texto_de(el) and el["tag"] != "svg":
        px = qa_css.valor_px(qa_css.ultimo(proprio, "font-size"))
        if px is not None and px >= GIGANTE_PX:
            return "texto gigante"
        if el["tag"] in ("span", "mark", "em", "strong") and "h1" in el["dentro"] and _tem_fundo(tudo):
            return "marca-texto"
        return None
    medidas = []
    for prop in ("width", "height"):
        v = qa_css.medida(qa_css.ultimo(proprio, prop), largura if prop == "width" else altura)
        if v is None and el["tag"] == "svg":  # the width/height attributes: a plain number is px
            attr = el["attrs"].get(prop, "").strip()
            v = qa_css.medida(attr + "px" if re.fullmatch(r"\d+(?:\.\d+)?", attr) else attr,
                              largura if prop == "width" else altura)
        medidas.append(v)
    w, h = medidas
    if el["tag"] == "svg":  # a drawing is a device at any size from the minimum up: a full-frame stage counts
        return "svg" if w and h and w * h / (largura * altura) >= RECURSO_MIN else None
    if not (w and h) or not RECURSO_MIN <= w * h / (largura * altura) <= RECURSO_MAX:
        return None
    if not _tem_fundo(tudo) or ((w >= FAIXA * largura or h >= FAIXA * altura) and not _tem_forma(tudo)):
        return None
    return "forma"


def recursos(doc, elementos, largura, altura):
    return [(e["id"] or e["tag"], r) for e in elementos for r in [recurso(doc, e, largura, altura)] if r]


SEM_RECURSO = ("só texto: falta 1 recurso visual (foto, svg, forma vazia de 2% a 85% da área, número de 200 px ou "
               "mais, marca-texto no h1; veja recursos-visuais.md)")


def check_recurso_quadro(doc):
    largura, altura = tamanho_quadro(doc)
    achados = recursos(doc, doc["elementos"], largura, altura)
    return resultado("recurso_visual", [] if achados else ["quadro " + SEM_RECURSO])


def _em(valor, fonte_px):
    """A length in em (px divided by the font size); None when it cannot be known."""
    v = (valor or "").strip().lower()
    if v.endswith("em") and not v.endswith("rem"):
        try:
            return float(v[:-2])
        except ValueError:
            return None
    px = qa_css.valor_px(v)
    return px / fonte_px if px is not None and fonte_px else (0.0 if qa_css.zero(v) else None)


def _folga(decl):
    """True when a clipped text has room for accents and descenders: line-height >= 1.2 (or unset/normal), or
    padding of 0.1em on top and 0.15em at the bottom."""
    fonte = qa_css.valor_px(qa_css.ultimo(decl, "font-size"))
    lh = (qa_css.ultimo(decl, "line-height") or "normal").strip().lower()
    try:
        alto = float(lh)
    except ValueError:
        alto = None if lh != "normal" else LINHA_LIVRE
        if alto is None and lh.endswith("%"):
            alto = float(lh[:-1]) / 100
        elif alto is None and fonte:
            alto = (_em(lh, fonte) or 0)
    if alto is not None and alto >= LINHA_LIVRE:
        return True
    topo = base = 0.0
    for k, v in decl:
        partes = v.split()
        if k == "padding" and partes:
            vals = [_em(x, fonte) for x in partes]
            topo, base = vals[0], vals[2] if len(vals) > 2 else vals[0]
        elif k == "padding-top":
            topo = _em(v, fonte)
        elif k == "padding-bottom":
            base = _em(v, fonte)
    return (topo or 0) >= FOLGA_TOPO and (base or 0) >= FOLGA_BASE


def quebras_titulo(el):
    """A headline breaks by meaning: one sentence per line (<br> in a post, its own clip in a reel) and every 1-2
    letter word glued to the next one with &nbsp;, so text-wrap never leaves "o", "E" or "de" ending a line."""
    nome, out = el["id"] or el["tag"], []
    for linha in qa_css.linhas_de(el):
        for m in FRASE_RE.finditer(linha):
            if not ABREVIACAO_RE.search(linha[:m.end()]):
                out.append("%s: duas frases na mesma linha ('%s'): cada frase começa linha nova (<br> no post; no "
                           "vídeo, a 2ª frase vai no clip _destaque)" % (nome, linha.replace("\xa0", " ")))
                break
        for palavra in linha.split(" ")[:-1]:
            curta = palavra.split("\xa0")[-1]
            if CURTA_RE.match(curta):
                out.append("%s: '%s' pode ficar sozinha no fim de uma linha: cole na palavra seguinte com &nbsp; "
                           "(%s&nbsp;...)" % (nome, curta, curta))
    return out


def check_legibilidade(doc, elementos=None, titulos=()):
    """No word alone on the last line (text-wrap: balance or pretty on #root/body or the text's own rule), no
    letter cut by a clip-path or overflow of a text without room (see _folga), and headlines that break by
    meaning (quebras_titulo)."""
    base = any(re.fullmatch(r"#root|html|body|:root|\*", qa_css.ultimo_composto(sel))
               and any(k in ("text-wrap", "text-wrap-style") and re.search(r"balance|pretty", v) for k, v in r["decl"])
               for r in doc["regras"] for sel in r["seletores"])
    alvos = elementos if elementos is not None else doc["elementos"]
    donos = []
    for el, _ in doc["trechos"]:
        if el is not None and el in alvos and el not in donos and el["id"] != "root" and not _decorativo(el):
            donos.append(el)
    out = []
    for el in donos:
        proprio, tudo = _decls_el(doc, el)
        nome = el["id"] or el["tag"]
        if palavras(qa_css.texto_de(el)) >= 3 and not base and not any(
                k in ("text-wrap", "text-wrap-style") and re.search(r"balance|pretty", v) for k, v in proprio):
            out.append("%s sem text-wrap: balance ou pretty (palavra sozinha na última linha)" % nome)
        corta = any((k == "clip-path" and v.strip().lower() not in ("none", "initial", "unset")) or
                    (k.startswith("overflow") and re.search(r"hidden|clip", v.lower())) for k, v in tudo)
        if corta and not _folga(proprio):
            out.append("%s com clip-path/overflow e sem folga (padding .1em em cima e .15em embaixo, ou "
                       "line-height 1.2): corta acento e perna de g, j, p, q, y" % nome)
    for el in titulos:
        out += quebras_titulo(el)
    return resultado("legibilidade", out)


# ---------- video (qa_cenas.py) and ad texts ----------

def checar_video(fonte, duracao, engine):
    """Checks of a reel source (see qa_cenas.checar_video)."""
    import qa_cenas  # here: qa_cenas imports this module
    return qa_cenas.checar_video(fonte, duracao, engine)


def problemas_textos(textos, trabalho):
    """Tics (no `!`: it may stay in ad text) and numbers outside entrada.md and the brand, in every text field
    of textos.json except url and caminhos."""
    if not isinstance(textos, dict):
        return []
    erro = briefing_ausente(trabalho)
    conhecidos, out = fatos(trabalho), ([erro] if erro else [])
    for campo, valor in textos.items():
        if campo in ("url", "caminhos"):
            continue
        for i, t in enumerate(valor if isinstance(valor, list) else [valor], 1):
            if not isinstance(t, str):
                continue
            out += ["%s %d: tique '%s': %s" % (campo, i, tq, t) for tq in achar_tiques(t, arte=False)]
            out += ["%s %d: número %s não está no briefing (entrada.md) nem na marca: %s" % (campo, i, n, t)
                    for n in _numeros_fora(t, conhecidos)]
    return out
