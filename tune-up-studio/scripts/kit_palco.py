"""Stage parts of the reel kit (kit_video.py): the collector of clips, CSS and scene calls, the theme, the
light stage under the hero, and the hero's tracks (framing per scene, loops, the transformation).
Python 3.9+, standard library only.
"""
import kit_base as kb
import qa_atencao

TEMAS = ("noite", "tinta", "dia")
# Transitions: a 0.44 s clip whose wipe is only seen for 0.14 s around the cut (34%-66%), so a frame sampled on
# the 0.25 s grid never shows it (the cuts sit on the 1/8 s offsets, see kit_video.TEMPOS).
TR = {
    "faixa": ("clip-path: polygon(0 10%, 100% 0, 100% 90%, 0 100%); animation: tr_faixa .44s linear 0s 1 both;",
              "@keyframes tr_faixa { 0%, 34% { transform: translateY(1920px); } 46%, 54% { transform: translateY(0); } "
              "66%, 100% { transform: translateY(-1920px); } }"),
    "cortina": ("animation: tr_cortina .44s linear 0s 1 both;",
                "@keyframes tr_cortina { 0%, 34% { clip-path: inset(0 100% 0 0); } 46%, 54% { clip-path: inset(0 0 0 0); } "
                "66%, 100% { clip-path: inset(0 0 0 100%); } }"),
    "sobe": ("animation: tr_sobe .44s linear 0s 1 both;",
             "@keyframes tr_sobe { 0%, 34% { clip-path: inset(100% 0 0 0); } 46%, 54% { clip-path: inset(0 0 0 0); } "
             "66%, 100% { clip-path: inset(0 0 100% 0); } }"),
}
SVG = ' viewBox="0 0 1080 1920" aria-hidden="true"'
CHEIO = "left: 0; top: 0; width: 1080px; height: 1920px;"


def n(v):
    """A number as the scene script writes it (at most 3 decimals, no trailing zeros)."""
    return ("%.3f" % v).rstrip("0").rstrip(".") or "0"


class Peca:
    """Collects the clips, the CSS and the scene calls while the scenes are built."""

    def __init__(self, m):
        self.m, self.c = m, m["cores"]
        self.css, self.clips, self.js, self.notas = [], [], [], []
        self.fh, self.ft = m["face_titulo"], m["face_texto"]

    def cor(self, k):
        return "var(--%s)" % k

    def clip(self, cid, t0, dur, tag="div", conteudo="", classes="", attrs=""):
        cls = "clip" + ((" " + classes) if classes else "")
        if tag == "img":
            self.clips.append('<img id="%s" class="%s" data-start="%s" data-duration="%s"%s>'
                              % (cid, cls, n(t0), n(dur), attrs))
        else:
            self.clips.append('<%s id="%s" class="%s" data-start="%s" data-duration="%s"%s>%s</%s>'
                              % (tag, cid, cls, n(t0), n(dur), attrs, conteudo, tag))

    def regra(self, cid, decl):
        self.css.append("#%s { %s }" % (cid, decl))

    def texto(self, cid, t0, dur, texto, x, y, px, cor, largura=None, titulo=False, classes="", lh=None, extra=""):
        fam = '"Brand Heading", sans-serif' if titulo else '"Brand Body", sans-serif'
        lh = lh or (1.0 if titulo else 1.2)
        caixa = ("width: %dpx; " % largura) if largura else "white-space: nowrap; "
        self.regra(cid, 'left: %dpx; top: %dpx; %sfont-family: %s; font-size: %dpx; font-weight: %s; '
                        'line-height: %s; letter-spacing: %s; color: %s; %s'
                   % (x, y, caixa, fam, px, self.m["peso_titulo"] if titulo else 700, lh, "-0.02em" if titulo else "0",
                      self.cor(cor), extra))
        self.clip(cid, t0, dur, "p", kb.esc(kb.colar(texto)), classes)

    def chama(self, linha):
        self.js.append(linha)


def palavras(*textos):
    return sum(qa_atencao.palavras(t) for t in textos if t)


def limite(dur):
    return max(6, int(3 * dur + 1e-9))


def claro(campo):
    return campo in ("bg", "surface")


def tema(m, peca):
    """The field color of each scene and the variant picks (asked in `variante` or stable from the brand name)."""
    c = m["cores"]
    v = peca.get("variante") if isinstance(peca.get("variante"), dict) else {}
    semente = m["nome"] + "reel"
    nome = kb.escolha(semente + "tema", TEMAS, v.get("tema"))
    forte = "primary" if qa_atencao.contraste(c["primary"], c["bg"]) >= 3 else "text"
    outro = "text" if forte == "primary" else "primary"
    campos = {"noite": {"gancho": forte, "rampa": outro, "lista": outro, "oferta": forte, "final": "bg"},
              "tinta": {"gancho": outro, "rampa": forte, "lista": forte, "oferta": outro, "final": "bg"},
              "dia": {"gancho": "bg", "rampa": forte, "lista": outro, "oferta": "bg", "final": forte}}[nome]
    ordem = ("faixa", "cortina", "sobe")
    giro = ordem.index(kb.escolha(semente + "tr", ordem, v.get("transicao")))
    return {"campos": campos, "forte": forte, "outro": outro, "tema": nome,
            "lado": kb.escolha(semente + "lado", ("direita", "esquerda"), v.get("lado")),
            "palco": kb.escolha(semente + "palco", ("disco", "corte"), v.get("palco")),
            "textura": kb.escolha(semente + "textura", ("pontos", "listras", "nenhuma"), v.get("textura")),
            "tr": ordem[giro:] + ordem[:giro]}


def calota(cx, cy, r):
    """The part of a disc that shows inside the frame, as a path that never leaves it: the arc from the left
    edge (or the disc's own left end) to the right one, closed along the bottom edge."""
    x0, x1 = max(0, cx - r), min(1080, cx + r)
    y0 = cy - (r * r - (cx - x0) ** 2) ** 0.5
    y1 = cy - (r * r - (x1 - cx) ** 2) ** 0.5
    return "M%d %d A%d %d 0 0 1 %d %d L%d 1920 L%d 1920 Z" % (x0, y0, r, r, x1, y1, x1, x0)


def campo(p, num, t0, dur, cor):
    cid = "s%d_bloco" % num
    p.regra(cid, "%s z-index: 0; background: %s;" % (CHEIO, p.cor(cor)))
    p.clip(cid, t0, dur)


def chao_de(t, cor):
    """Ground color for a field: the other dark color on a dark field, the strong one on a light field."""
    if claro(cor):
        return t["forte"]
    return t["outro"] if cor == t["forte"] else t["forte"]


def arte(p, num, t0, dur, cor, t, solo, topo, cx, largura_heroi, estrada, anda, canto=False, tx=None, forma=None,
         textura=True):
    """The scene's stage as one SVG clip under the hero: a light stage on a dark field (a ring on a light one),
    the ground running to the bottom edge, a texture, the road dashes scrolling."""
    partes = []
    chao = chao_de(t, cor)
    if not claro(cor):
        if (forma or t["palco"]) == "corte":      # a slanted split: the light stage rises toward the hero's side
            e, d = (topo + 110, topo) if t["lado"] == "direita" else (topo, topo + 110)
            partes.append('<polygon class="a" points="0,%d 1080,%d 1080,1920 0,1920"/>' % (e - 30, d - 30))
            partes.append('<polygon class="b" points="0,%d 1080,%d 1080,1920 0,1920"/>' % (e, d))
        else:                                      # a disc rising from the bottom, wider than the frame
            r = int((solo - topo) / 0.74)
            for classe, raio in (("a", r + 30), ("b", r)):
                partes.append('<path class="%s" d="%s"/>' % (classe, calota(cx, topo + r + 30, raio)))
        cor_tx = kb.sobre(p.c, cor, True, ("surface", "accent", "bg"))[0]
    else:
        r = min(int(largura_heroi * 0.46), cx - 40, 1040 - cx)
        partes.append('<circle class="l%s" stroke-width="34" cx="%d" cy="%d" r="%d"/>'
                      % ("s" if cor == "bg" else "b", cx, solo - int(r * 0.7), r))
        cor_tx = t["forte"][0]
    lado_tx, ty = tx if tx else ((700 if t["lado"] == "direita" else 70), topo - 30)
    if claro(cor) and not tx:                      # on a light field the texture stays in the top band, off the hero
        lado_tx, ty = (70 if t["lado"] == "direita" else 700) if canto else lado_tx, 56
    if textura and t["textura"] == "pontos":
        partes.insert(0, kb.pontos(lado_tx, ty, 7, 4, 52, 8, cor_tx))
    elif textura and t["textura"] == "listras":
        for i in range(5):
            partes.insert(0, '<path class="l%s" stroke-width="14" stroke-linecap="butt" d="M%d %d L%d %d"/>'
                          % (cor_tx, lado_tx + i * 64, ty + 160, lado_tx + 120 + i * 64, ty))
    if canto:                                      # the brand motif (slanted stripes) in the top corner, off the text
        for i in range(4):
            x0 = (1080 - i * 76) if t["lado"] == "direita" else (i * 76 + 150)
            partes.append('<polygon class="%s" points="%d,0 %d,0 %d,200 %d,200"/>'
                          % ("a" if cor != "accent" else "p", x0 - 40, x0, x0 - 70, x0 - 110))
    partes.append('<rect class="%s" x="0" y="%d" width="1080" height="%d"/>' % (chao[0], solo - 30, 1950 - solo))
    if estrada:
        cid = "a%d_chao" % num
        partes.append('<path id="%s" class="l%s" stroke-width="16" stroke-linecap="butt" stroke-dasharray="120 100" '
                      'd="M-40 %d L1120 %d"/>' % (cid, "b", solo + 84, solo + 84))
        sentido = -1 if anda == "esquerda" else 1
        p.chama('M.trilha("%s", "strokeDashoffset", [[%s, "0", "reta"], [%s, "%d"]]);'
                % (cid, n(t0), n(t0 + dur), sentido * 220 * max(2, int(round(dur * 1.6)))))
    cid = "s%d_bloco2" % num
    p.regra(cid, "%s z-index: 1;" % CHEIO)
    p.clip(cid, t0, dur, "svg", "".join(partes), attrs=SVG)


CURSOR = ('<path class="ct" d="M14 6 L14 122 L46 94 L68 144 L96 132 L74 84 L118 84 Z"/>'
          '<path class="cb" d="M26 32 L26 96 L48 77 L74 128 L82 124 L58 72 L90 72 Z"/>')


def toque(p, num, t0, dur, de, alvo, a, cor_onda):
    """`s<N>_cursor` and `s<N>_onda`: a cursor travels from `de` to `alvo` (x, y of its tip), presses at `a`
    (absolute seconds) while a ring spreads from that point, then drifts off. Shows where to click or tap."""
    p.regra("s%d_onda" % num, "left: %dpx; top: %dpx; width: 240px; height: 240px; z-index: 5;"
            % (alvo[0] - 120, alvo[1] - 120))
    p.clip("s%d_onda" % num, t0, dur, "svg", '<circle class="l%s" stroke-width="16" cx="120" cy="120" r="110"/>'
           % cor_onda[0], attrs=' viewBox="0 0 240 240" aria-hidden="true"')
    p.chama('M.trilha("s%d_onda", "transform", [[%s, "scale(.15)", "sai"], [%s, "scale(1.5)"]]);'
            % (num, n(a), n(a + 0.5)))
    p.chama('M.trilha("s%d_onda", "opacity", [[%s, "0", "reta"], [%s, "1", "reta"], [%s, "0"]]);'
            % (num, n(a - 0.01), n(a), n(a + 0.5)))
    p.css.append("#s%d_cursor .ct { fill: %s; } #s%d_cursor .cb { fill: %s; }" % (num, p.cor("text"), num, p.cor("bg")))
    p.regra("s%d_cursor" % num, "left: 0; top: 0; width: 150px; height: 150px; z-index: 6;")
    p.clip("s%d_cursor" % num, t0, dur, "svg", CURSOR, attrs=' viewBox="0 0 150 150" aria-hidden="true"')
    passos = ((t0, de, 1), (a - 0.15, alvo, 1), (a, alvo, 0.8), (a + 0.18, alvo, 1),
              (a + 0.75, (alvo[0] + 0.3 * (de[0] - alvo[0]), alvo[1] + 0.3 * (de[1] - alvo[1])), 1))
    # it leaves once it has pressed: the text under it is covered for half a second, not for the rest of the scene
    p.chama('M.trilha("s%d_cursor", "opacity", [[%s, "1", "reta"], [%s, "0"]]);' % (num, n(a + 0.45), n(a + 0.75)))
    p.chama('M.trilha("s%d_cursor", "transform", [%s]);' % (num, ", ".join(
        '[%s, "translate(%dpx, %dpx) scale(%s)", "meio"]' % (n(tt), xy[0], xy[1], n(e)) for tt, xy, e in passos)))


def titulo_duplo(p, titulo, destaque, largura, alto, max_px, numero=False):
    """One size for the title and its highlight line(s): the biggest that fits `largura` x `alto`. With `numero`
    the title is a giant number and the highlight is its line. Returns (px title, px highlight, lines, lines,
    width, width)."""
    melhor = None
    for lt in (1, 2, 3):
        for ld in ((0,) if not destaque else (1, 2)):
            em_t, lin_t = kb.quebrar(titulo, p.fh, lt)
            em_d, lin_d = kb.quebrar(destaque, p.fh, ld) if destaque else (0.01, [])
            if len(lin_t) + len(lin_d) > 4:
                continue
            if numero:
                px_t = min(480, largura / em_t, alto * 0.62)
                px_d = min(max_px, largura / em_d, (alto - px_t * 0.92) / max(1, len(lin_d))) if destaque else 0
            else:
                px_t = px_d = min(max_px, largura / max(em_t, em_d), alto / (len(lin_t) + len(lin_d)))
            todas = len(lin_t) + len(lin_d)
            fill = (kb.cheio(lin_t, p.fh, px_t, largura) * len(lin_t)
                    + (kb.cheio(lin_d, p.fh, px_d, largura) * len(lin_d) if destaque else 0)) / todas
            nota = (1 if px_t >= 120 and fill >= 0.6 else 0, (px_t * len(lin_t) + px_d * len(lin_d)) / todas * fill ** 0.5)
            if melhor is None or nota[0] > melhor[0][0] or (nota[0] == melhor[0][0] and nota[1] > melhor[0][1] * 1.02):
                melhor = (nota, px_t, px_d, lin_t, lin_d, em_t, em_d)
    _, px_t, px_d, lin_t, lin_d, em_t, em_d = melhor
    return int(px_t), int(px_d), lin_t, lin_d, em_t * int(px_t), em_d * int(px_d)


def transicoes(p, t, nomes, inicios):
    """`tr<N>`: 0.44 s centered on each cut, in the color of the next scene, never the same kind twice in a row."""
    usados = []
    for i, corte in enumerate(inicios[1:], 1):
        tipo = t["tr"][(i - 1) % 3]
        prox = t["campos"][nomes[i]] if nomes[i] != "rampa" else "bg"
        p.regra("tr%d" % i, "%s z-index: 9; background: %s; %s" % (CHEIO, p.cor(prox), TR[tipo][0]))
        p.clip("tr%d" % i, corte - 0.22, 0.44)
        if tipo not in usados:
            usados.append(tipo)
            p.css.append(TR[tipo][1])


def heroi(p, desenho, foto, quadros, total, anda, t_payoff):
    """`deco1`: the hero for the whole video. `quadros`: per scene (t0, t1, (ax, ay, width) at the start, the
    same at the end): the bottom-center of the drawing's 1000x1000 box (its ground line, y = 900) and its
    width in px. Loops, the bob of a hero that stands still, and the transformation at `t_payoff`."""
    passo = {"direita": 1, "esquerda": -1}.get(anda, 0)
    chaves = []
    if foto:
        fw, fa = 800, 1000                         # a 4:5 frame: 0.72 of the hero width, 0.9 of it tall
        p.regra("deco1", "left: 0; top: 0; width: %dpx; height: %dpx; z-index: 2; object-fit: cover; "
                "transform-origin: 0 0;" % (fw, fa))
        p.clip("deco1", 0, total, "img", attrs=' src="assets/%s" alt=""' % foto)
        for a, b, ini, fim in quadros:
            for tt, (ax, ay, lw) in ((a, ini), (b - 0.001, fim)):
                s = lw * 0.72 / fw
                chaves.append('[%s, "translate(%spx, %spx) scale(%s)", "reta"]'
                              % (n(tt), n(ax - fw * s / 2), n(ay - fa * s - 20), n(s)))
        p.chama('M.trilha("deco1", "transform", [%s]);' % ", ".join(chaves))
        return
    marcacao, ids = desenho
    p.regra("deco1", "%s z-index: 2;" % CHEIO)
    p.clip("deco1", 0, total, "svg", '<g id="heroi_quadro"><g id="heroi_vida">%s</g></g>' % marcacao, attrs=SVG)
    for a, b, ini, fim in quadros:
        for tt, (ax, ay, lw) in ((a, ini), (b - 0.001, fim)):
            s = lw / 1000.0
            chaves.append('[%s, "translate(%spx, %spx) scale(%s)", "reta"]'
                          % (n(tt), n(ax - 500 * s), n(ay - 900 * s), n(s)))
    p.chama('M.trilha("heroi_quadro", "transform", [%s]);' % ", ".join(chaves))
    if not passo:
        p.chama('M.vaivem("heroi_vida", 0, %s, "translate(0px, 0px)", "translate(0px, -16px)", 1.4);' % n(total))
    for i in sorted(ids):
        if i.startswith("h_gira"):
            p.chama('M.trilha("%s", "transform", [[0, "rotate(0deg)", "reta"], [%s, "rotate(%ddeg)"]]);'
                    % (i, n(total), (passo or 1) * 360 * int(total * 0.75)))
        elif i.startswith("h_balanca"):
            p.chama('M.vaivem("%s", 0, %s, "translate(0px, 0px)", "translate(0px, -34px)", 1.1);' % (i, n(total)))
    depois = sorted(i for i in ids if i.startswith("h_depois"))
    tracos = sorted(i for i in ids if i.startswith("h_traco"))
    if not (depois or tracos):
        raise kb.Erro('heroi.svg sem transformação: desenhe ao menos um <g id="h_depois1"> (o que a oferta muda no '
                      'herói, em torno de 0,0, dentro de um <g transform="translate(x y)">)')
    for k, i in enumerate(sorted(i for i in ids if i.startswith("h_antes"))):
        # the problem state hovers until the offer removes it
        p.chama('M.vaivem("%s", 0, %s, "translate(0px, 0px)", "translate(0px, %dpx)", %s);'
                % (i, n(t_payoff), -22 if k % 2 == 0 else 20, n(0.9 + 0.2 * k)))
        p.chama('M.trilha("%s", "opacity", [[0, "1"], [%s, "1", "reta"], [%s, "0"]]);'
                % (i, n(t_payoff), n(t_payoff + 0.25)))
    for k, i in enumerate(depois):
        ti = t_payoff + 0.12 + k * 0.12
        p.chama('M.trilha("%s", "transform", [[0, "scale(0)"], [%s, "scale(0)", "mola"], [%s, "scale(1)"]]);'
                % (i, n(ti), n(ti + 0.36)))
    for k, i in enumerate(tracos):
        p.css.append("#%s { stroke-dasharray: 1; stroke-dashoffset: 1; }" % i)
        p.chama('M.traco("%s", %s, 0.35);' % (i, n(t_payoff + 0.2 + k * 0.15)))
