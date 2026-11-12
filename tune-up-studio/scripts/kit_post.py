"""Post compositions of the kit (montar.py --tipo post): finished frames, drawn once and looked at, that take
the brand, the texts of `peca.json` and the hero drawing. Each composition keeps the same contract:
3 type levels (headline, offer stack, call), shapes running to the real edge, the hero big on a light stage,
the offer stack (name + giant value + proof) and a full call band. Python 3.9+, standard library only.
"""
import kit_base as kb

W = 1080
COMPOSICOES = ("oferta", "palco", "numero")
ARRANJO = {"oferta": "l-oferta", "palco": "l-titulo", "numero": "l-numero"}
QUADROS = ("unico", "capa", "ponto", "fecho")


def _titulo(texto, realce, linhas):
    """The h1 inner HTML: the fitted lines joined by <br>, the `realce` words wrapped in the highlight span."""
    partes = []
    alvo = kb.colar(realce) if realce else ""
    for linha in linhas:
        t = kb.esc(linha)
        partes.append(t)
    inteiro = "<br>".join(partes)
    if alvo:
        for pedaco in sorted({p for l in linhas for p in [_comum(l, alvo)] if p}, key=len, reverse=True):
            inteiro = inteiro.replace(kb.esc(pedaco), '<span class="r">%s</span>' % kb.esc(pedaco))
    return inteiro


def _comum(linha, alvo):
    """The part of `alvo` (the highlight) that sits in this line: whole, its start or its end."""
    if alvo in linha:
        return alvo
    palavras = alvo.replace(" ", " ").split(" ")
    norm = linha.replace(" ", " ")
    for i in range(len(palavras) - 1, 0, -1):
        ini, fim = " ".join(palavras[:i]), " ".join(palavras[i:])
        if norm.endswith(ini):
            return linha[len(linha) - len(ini):]
        if norm.startswith(fim):
            return linha[:len(fim)]
    return ""


def _tema(m, peca, semente):
    """Field color and the colors that follow from it, all brand pairs measured here."""
    c = m["cores"]
    v = peca.get("variante") if isinstance(peca.get("variante"), dict) else {}
    campo = kb.escolha(semente + "campo", ("primary", "text", "bg"), v.get("campo"))
    claro = "bg" if campo != "bg" else "surface"
    return {
        "campo": campo, "palco": claro,
        "titulo": kb.sobre(c, campo, True, ("bg", "text", "primary", "surface")),
        "chao": "text" if campo != "text" else "primary",
        "cartao": "accent" if campo != "accent" else "bg",
        "faixa": "bg" if campo != "bg" else "primary",
        "lado": kb.escolha(semente + "lado", ("direita", "esquerda"), v.get("lado")),
        "textura": kb.escolha(semente + "textura", ("pontos", "listras", "nenhuma"), v.get("textura")),
    }


def _arte_heroi(heroi, estado):
    corpo, ids = heroi
    some = [i for i in ids if (i.startswith("h_antes") if estado == "depois" else
                               i.startswith("h_depois") or i.startswith("h_traco"))]
    css = "".join("#%s { display: none; } " % i for i in sorted(some))
    return corpo, css


def _cabeca(m, css, classe, h, corpo, titulo_doc="post"):
    c = m["cores"]
    return """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <style>
    %s
    :root { --bg: %s; --surface: %s; --primary: %s; --text: %s; --accent: %s; }
    html, body { margin: 0; background: var(--bg); }
    #root { position: relative; width: 1080px; height: %dpx; overflow: hidden; box-sizing: border-box;
            padding: 80px; background: var(--bg); color: var(--text); font-family: "Brand Body", sans-serif;
            font-size: 40px; text-wrap: balance; }
    #root p, #root h1 { position: absolute; margin: 0; }
    .arte { position: absolute; left: 0; top: 0; width: 1080px; height: %dpx; }
    %s
%s  </style>
</head>
<body>
  <div id="root" class="%s" data-composition-id="%s" data-start="0" data-duration="5"
       data-width="1080" data-height="%d" data-no-timeline>
%s  </div>
</body>
</html>
""" % ("\n    ".join(m["linhas_fonte"]), c["bg"], c["surface"], c["primary"], c["text"], c["accent"], h, h,
       kb.HEROI_CSS, css, classe, titulo_doc, h, corpo)


def _pilha_oferta(oferta, fh, ft, larg_txt, teto, px_titulo, alto=600):
    """Sizes of the offer stack for a text column `larg_txt` wide: (label px, label lines, value px, value
    lines, proof px, proof lines, height)."""
    nome = kb.limpo(oferta.get("nome"), 28, "oferta.nome").upper()
    valor = " ".join(str(oferta.get("valor") or "").split())
    prova = " ".join(str(oferta.get("prova") or "").split())
    rpx, rlin, rl = kb.caber(nome, ft, larg_txt, 90, min(teto, 40), 32, (1,), 1.15, 0.05)
    if rl > larg_txt:
        rpx, rlin, _ = kb.caber(nome, ft, larg_txt, 90, min(teto, 40), 28, (2,), 1.15, 0.05)
    ppx, plin = 0, []
    if prova:
        kb.limpo(prova, 40, "oferta.prova")
        ppx, plin, _ = kb.caber(prova, ft, larg_txt, 110, min(teto, 40), 28, (1, 2), 1.25, 0)
    resto = alto - int(len(rlin) * rpx * 1.15) - (14 + int(len(plin) * ppx * 1.25) if plin else 0) - 12
    vpx, vlin = 0, []
    if valor:
        kb.limpo(valor, 16, "oferta.valor")
        pr = kb.preco(valor, fh, larg_txt, min(280, resto), min(300, int(px_titulo * 1.7)))
        if pr:
            vpx, vlin = pr[0], [pr[1]]
        else:
            vpx, vlin, _ = kb.caber(valor, fh, larg_txt, min(250, resto), min(260, int(px_titulo * 1.45)), 96, (1, 2),
                                    0.98, -0.02)
            vlin = [kb.esc(l) for l in vlin]
    alt = int(len(rlin) * rpx * 1.15) + (12 + int(len(vlin) * vpx * 0.98) if vlin else 0) \
        + (14 + int(len(plin) * ppx * 1.25) if plin else 0)
    return rpx, rlin, vpx, vlin, ppx, plin, alt, teto


def _textos_oferta(css, textos, cor, x, y, larg, alinhamento, cor_t, cor_v, pilha):
    rpx, rlin, vpx, vlin, ppx, plin = pilha[:6]
    comum = "left: %dpx; width: %dpx; text-align: %s; white-space: nowrap;" % (x, larg, alinhamento)
    css.append(".rotulo { %s top: %dpx; font-size: %dpx; font-weight: 700; line-height: 1.15; "
               "letter-spacing: .05em; color: %s; }" % (comum, y, rpx, cor(cor_t)))
    textos.append('<p class="rotulo">%s</p>' % "<br>".join(kb.esc(l) for l in rlin))
    y += int(len(rlin) * rpx * 1.15)
    if vlin:
        y += 12
        css.append('#oferta { %s top: %dpx; font-family: "Brand Heading", sans-serif; font-size: %dpx; '
                   'line-height: .98; letter-spacing: -0.02em; color: %s; }' % (comum, y, vpx, cor(cor_v)))
        css.append(kb.preco_css("#oferta", vpx, pilha[7]))
        textos.append('<p id="oferta">%s</p>' % "<br>".join(vlin))
        y += int(len(vlin) * vpx * 0.98)
    if plin:
        y += 14
        css.append(".prova { %s top: %dpx; font-size: %dpx; font-weight: 700; line-height: 1.25; color: %s; }"
                   % (comum, y, ppx, cor(cor_t)))
        textos.append('<p class="prova">%s</p>' % "<br>".join(kb.esc(l) for l in plin))


def montar(m, peca, heroi, destino, h=1350, quadro="unico", logo=None, foto=None):
    """One frame. Returns (html, notes). `quadro`: unico (hook + offer + call), capa (hook + swipe cue),
    ponto (one point), fecho (offer + call)."""
    comp = peca.get("composicao")
    if comp not in COMPOSICOES:
        raise kb.Erro("composicao '%s' não existe no post: use %s" % (comp, ", ".join(COMPOSICOES)))
    if quadro not in QUADROS:
        raise kb.Erro("quadro '%s' não existe: use %s" % (quadro, ", ".join(QUADROS)))
    c = m["cores"]
    t = _tema(m, peca, m["nome"] + comp)
    notas = []
    oferta = peca.get("oferta") if isinstance(peca.get("oferta"), dict) else {}
    cta = peca.get("cta") if isinstance(peca.get("cta"), dict) else {}
    tem_cta = quadro in ("unico", "fecho")
    tem_oferta = bool(oferta) and quadro != "capa"
    titulo = kb.limpo(peca.get("titulo"), 40, "titulo")
    realce = " ".join(str(peca.get("realce") or "").split())
    if realce and realce not in titulo:
        raise kb.Erro("realce '%s' não está dentro do titulo" % realce)
    esq = t["lado"] == "esquerda"  # the hero's side; the offer takes the other one
    centro = comp == "palco"
    fh, ft = m["face_titulo"], m["face_texto"]
    banda = (250 if h >= 1300 else 200) if tem_cta else (110 if quadro == "capa" else 0)
    base = h - banda          # where the ground meets the call band
    chao = 96 if h >= 1300 else 64
    topo = 176                # under the brand row
    css, corpo, arte, textos = [], [], [], []
    cor = lambda k: "var(--%s)" % k  # noqa: E731
    css.append("#root { background: %s; }" % cor(t["campo"]))

    # ---- brand row (always the same corner) ----
    if logo:
        css.append(".prato { position: absolute; left: 72px; top: 56px; width: 100px; height: 100px; "
                   "border-radius: 50%%; background: %s; }" % cor("bg"))
        css.append(".logo { position: absolute; left: 80px; top: 64px; width: 84px; height: 84px; }")
        corpo.append('<div class="prato"></div>')
        corpo.append('<img class="logo" src="assets/%s" alt="">' % logo)
    css.append('.nome { left: %dpx; top: 84px; font-family: "Brand Heading", sans-serif; font-size: 34px; '
               'line-height: 1.3; letter-spacing: .01em; color: %s; white-space: nowrap; }'
               % (196 if logo else 80, cor(t["titulo"])))
    corpo.append('<p class="nome">%s</p>' % kb.esc(m["nome"]))

    # ---- headline: sized to fill the 920 px column ----
    numero = comp == "numero"
    curto = h < 1300                               # 1:1: less height, so the title and the support take less
    alto_tit = (base - topo) * ((0.38 if tem_oferta or centro else 0.42) - (0.06 if curto else 0))
    if numero:
        px, linhas, larg = kb.caber(titulo, fh, 920, alto_tit, 460, 120, (1,), 0.92, -0.03)
    else:
        px, linhas, larg = kb.caber(titulo, fh, 920, alto_tit, 250, 88, (1, 2, 3), 1.0, -0.02)
    lh = 0.92 if numero else 1.0
    alt_tit = int(len(linhas) * px * lh)
    css.append('h1 { left: 80px; top: %dpx; width: 920px; text-align: %s; font-family: "Brand Heading", sans-serif; '
               'font-size: %dpx; line-height: %s; letter-spacing: %sem; color: %s; '
               'white-space: nowrap; }' % (topo, "center" if centro else "left", px, lh,
                                           "-0.03" if numero else "-0.02", cor(t["titulo"])))
    css.append("h1 .r { color: %s; }" % cor(kb.destaque(c, t["campo"], t["titulo"])))
    css.append("h1, .nome, #oferta, #cta { font-weight: %d; }" % m["peso_titulo"])
    corpo.append("<h1>%s</h1>" % _titulo(titulo, realce, linhas))
    y = topo + alt_tit + 24
    notas.append("titulo: %d px em %d linha(s), %d px de largura" % (px, len(linhas), larg))
    teto = int(px / 1.8)

    apoio = " ".join(str(peca.get("apoio") or "").split())
    if apoio and (numero or not tem_oferta):
        kb.limpo(apoio, 60, "apoio")
        apx, alin, _ = kb.caber(apoio, ft, 920 if centro or curto else 560, 150, min(teto, 56), 32,
                                (1,) if curto else (1, 2), 1.2, 0)
        css.append(".apoio { left: 80px; top: %dpx; width: 920px; text-align: %s; font-size: %dpx; font-weight: 700; "
                   "line-height: 1.2; color: %s; white-space: nowrap; }"
                   % (y, "center" if centro else "left", apx, cor(t["titulo"])))
        corpo.append('<p class="apoio">%s</p>' % "<br>".join(kb.esc(l) for l in alin))
        y += int(len(alin) * apx * 1.2) + 20

    # ---- stage: ring + light disc + ground, to the real edge; the hero big on it ----
    solo = base - chao + 30                        # where the hero stands (30 px into the ground band)
    escala = min(0.9 if centro else 0.78, (solo - y) / (1000.0 * kb.alto_heroi(peca)))
    lado_h = int(1000 * escala)
    if tem_oferta and not centro:
        lado_h = min(lado_h, 570)                  # the card (524 px and its shadow) never covers the drawing
    if centro:
        cx = min(660, 1080 - lado_h // 2) if not esq else max(420, lado_h // 2)
        hx = cx - lado_h // 2
    else:
        hx = 0 if esq else 1080 - lado_h           # the drawing stays whole inside the frame (the check asks it)
        cx = hx + lado_h // 2
    hy = solo - int(900 * escala)
    cor_tx = kb.sobre(c, t["palco"], True, (t["campo"], "primary", "accent", "text"))[0]
    if centro:                                     # an arch: the hero's light stage, cut round on top
        r = min(int(lado_h * 0.54), solo - y - 16, 1080 - cx - 28, cx - 28)
        arte.append('<path class="%s" d="M%d %d L%d %d A%d %d 0 0 1 %d %d L%d %d Z"/>'
                    % ("a" if t["cartao"] != "accent" else t["chao"][0], cx - r - 26, base, cx - r - 26, y + r + 6,
                       r + 26, r + 26, cx + r + 26, y + r + 6, cx + r + 26, base))
        arte.append('<path class="%s" d="M%d %d L%d %d A%d %d 0 0 1 %d %d L%d %d Z"/>'
                    % (t["palco"][0], cx - r, base, cx - r, y + r + 32, r, r, cx + r, y + r + 32, cx + r, base))
        if t["textura"] == "pontos":
            arte.append(kb.pontos(724 if esq else 96, y + 44, 6, 4, 46, 7,
                                  kb.sobre(c, t["campo"], True, ("surface", "accent", "bg"), fora=(t["titulo"],))[0]))
    else:                                          # a slanted split: field above, light stage below
        alto_e, alto_d = (y + 8, y + 86) if esq else (y + 86, y + 8)
        arte.append('<polygon class="%s" points="0,%d 1080,%d 1080,%d 0,%d"/>'
                    % (t["palco"][0], alto_e, alto_d, base, base))
        rd = min(int(lado_h * 0.43), int((solo - max(alto_e, alto_d) - 40) / 1.82))
        arte.append('<circle class="l%s" stroke-width="30" cx="%d" cy="%d" r="%d"/>'
                    % ("s" if t["palco"] == "bg" else "b", cx, solo - int(rd * 0.82), rd))
        if t["textura"] == "pontos":
            arte.append(kb.pontos(640 if not esq else 60, min(alto_e, alto_d) + 60, 9, 3, 46, 7, cor_tx))
        elif t["textura"] == "listras":
            x0 = 30 if not esq else 690
            for i in range(6):
                arte.append('<path class="l%s" stroke-width="12" stroke-linecap="butt" d="M%d %d L%d %d"/>'
                            % (cor_tx, x0 + i * 60, max(alto_e, alto_d) + 150, x0 + 110 + i * 60,
                               max(alto_e, alto_d) + 30))
    arte.append('<rect class="%s" x="0" y="%d" width="1080" height="%d"/>' % (t["chao"][0], base - chao, chao + 2))
    if peca.get("chao") == "estrada":
        arte.append('<path class="l%s" stroke-width="12" stroke-linecap="butt" stroke-dasharray="90 70" '
                    'd="M0 %d L1080 %d"/>' % (t["palco"][0], base - chao // 3, base - chao // 3))
    estado = peca.get("estado") if peca.get("estado") in ("antes", "depois") else "depois"
    if foto:
        fw, fa = int(lado_h * 0.72), int(lado_h * 0.9)
        fx = (0 if esq else 1080 - fw) if not centro else cx - fw // 2
        fy = solo - 30 - fa
        css.append(".foto { position: absolute; left: %dpx; top: %dpx; width: %dpx; height: %dpx; object-fit: cover; }"
                   % (fx, fy, fw, fa))
        arte.append('<rect class="%s" x="%d" y="%d" width="%d" height="%d"/>'
                    % (t["chao"][0], max(0, fx + (26 if esq else -26)), fy - 26, fw, fa))
    else:
        marcacao, some = _arte_heroi(heroi, estado)
        css.append(some)
        arte.append('<g transform="translate(%d %d) scale(%s)">%s</g>' % (hx, hy, round(lado_h / 1000.0, 4), marcacao))
    notas.append("heroi: %d px de lado (%d%% da largura)" % (lado_h, lado_h * 100 // W))
    fundo = len(arte)                              # what comes after this sits over the photo

    # ---- offer stack: name + giant value + proof, on a card (oferta, numero) or a round sticker (palco) ----
    if tem_oferta and centro:
        larg_txt = 360
        pilha = _pilha_oferta(oferta, fh, ft, larg_txt, teto, px, base - chao - y - 150)
        tw, ta = larg_txt + 88, pilha[6] + 150      # a price tag: chamfered top, a hole, tilted
        tx0 = 40 if not esq else 1040 - tw
        ty0 = base - chao - ta + 46
        ang = -5 if not esq else 5
        cor_c = t["cartao"]
        cor_t = kb.sobre(c, cor_c, False, ("text", "primary", "bg"))
        forma = "M%d 0 L%d 0 L%d 70 L%d %d L0 %d L0 70 Z" % (70, tw - 70, tw, tw, ta, ta)
        arte.append('<g transform="translate(%d %d) rotate(%d %d %d)"><path class="%s" transform="translate(14 16)" '
                    'd="%s"/><path class="%s" d="%s"/><circle class="%s" cx="%d" cy="52" r="20"/>'
                    '<path class="l%s" stroke-width="6" d="M%d 52 Q%d -40 %d -90"/></g>'
                    % (tx0, ty0, ang, tw // 2, ta // 2, t["chao"][0], forma, cor_c[0], forma, t["palco"][0], tw // 2,
                       cor_t[0], tw // 2, tw // 2 + 30, tw // 2 - 10))
        css.append(".pilha { position: absolute; left: %dpx; top: %dpx; width: %dpx; height: %dpx; "
                   "transform: rotate(%ddeg); }" % (tx0, ty0, tw, ta, ang))
        dentro = []
        _textos_oferta(css, dentro, cor, 44, 104, larg_txt, "center", cor_t,
                       kb.sobre(c, cor_c, True, ("text", "primary", "bg")), pilha)
        textos.append('<div class="pilha">%s</div>' % "".join(dentro))
        notas.append("oferta: %d px na etiqueta" % pilha[2])
    elif tem_oferta:
        larg_txt = 400
        pilha = _pilha_oferta(oferta, fh, ft, larg_txt, teto, px, base - chao - y - 130)
        cw = larg_txt + 80 + 44                    # the card runs off the edge on the text side
        cx0 = 1080 - cw if esq else 0
        tx = cx0 + (44 if esq else 80)
        alt_cartao = pilha[6] + 84
        cy0 = max(y + 6, base - chao - alt_cartao - 40)
        cor_c = t["cartao"]
        d = -14 if esq else 14

        def pts(dx, dy):
            return "%d,%d %d,%d %d,%d %d,%d" % (cx0 + dx, cy0 + (0 if esq else 14) + dy, cx0 + cw + dx,
                                                cy0 + (14 if esq else 0) + dy, cx0 + cw + dx,
                                                cy0 + alt_cartao - (0 if esq else 14) + dy, cx0 + dx,
                                                cy0 + alt_cartao - (14 if esq else 0) + dy)
        arte.append('<polygon class="%s" points="%s"/>' % (t["chao"][0], pts(d, 18)))
        arte.append('<polygon class="%s" points="%s"/>' % (cor_c[0], pts(0, 0)))
        _textos_oferta(css, textos, cor, tx, cy0 + 44, larg_txt, "left",
                       kb.sobre(c, cor_c, False, ("text", "primary", "bg")),
                       kb.sobre(c, cor_c, True, ("text", "primary", "bg")), pilha)
        notas.append("oferta: %d px no cartão" % pilha[2])

    # ---- call band, edge to edge ----
    cor_f = t["faixa"]
    cor_ct = kb.sobre(c, cor_f, False, ("text", "primary", "bg"))
    if banda:
        arte.append('<rect class="%s" x="0" y="%d" width="1080" height="%d"/>' % (cor_f[0], base, banda))
    if tem_cta:
        chamada = kb.limpo(cta.get("chamada"), 44, "cta.chamada")
        cond = kb.limpo(cta.get("condicao"), 60, "cta.condicao")
        icone = kb.canal(cta.get("canal") or "whatsapp")
        ic = 124 if h >= 1300 else 104
        tx = 80 + ic + 36
        cpx, chlin, clarg = kb.caber(chamada, fh, 1000 - tx, 90, min(teto, 76), 44, (1,), 1.1, 0)
        if clarg > 1000 - tx:                      # a long call takes two lines instead of leaving the frame
            cpx, chlin, clarg = kb.caber(chamada, fh, 1000 - tx, 130, min(teto, 64), 44, (2,), 1.1, 0)
        cond_px, clin, cond_larg = kb.caber(cond, ft, 1000 - tx, 110 if len(chlin) == 1 else 50, min(teto, 44), 30,
                                            (1, 2) if len(chlin) == 1 else (1,), 1.25, 0)
        for nome, larg_l in (("cta.chamada", clarg), ("cta.condicao", cond_larg)):
            if larg_l > 1000 - tx:
                raise kb.Erro("%s não cabe na faixa (%d px de %d): encurte; o que sobra vai para a legenda"
                              % (nome, larg_l, 1000 - tx))
        bloco = int(len(chlin) * cpx * 1.1) + 8 + int(len(clin) * cond_px * 1.25)
        css.append(".canal { position: absolute; left: 80px; top: %dpx; width: %dpx; height: %dpx; } "
                   ".canal .ic { fill: %s; } .canal .ic2 { fill: %s; }"
                   % (base + (banda - ic) // 2, ic, ic, cor(cor_ct), cor(cor_f)))
        css.append('#cta { left: %dpx; top: %dpx; font-family: "Brand Heading", sans-serif; font-size: %dpx; '
                   'line-height: 1.1; color: %s; white-space: nowrap; }' % (tx, base + (banda - bloco) // 2, cpx,
                                                                           cor(cor_ct)))
        css.append('#cta .cond { display: block; margin-top: 8px; font-family: "Brand Body", sans-serif; '
                   'font-size: %dpx; font-weight: 700; line-height: 1.25; }' % cond_px)
        textos.append('<svg class="canal" viewBox="0 0 100 100" aria-hidden="true">%s</svg>' % icone)
        textos.append('<p id="cta">%s<span class="cond">%s</span></p>'
                      % ("<br>".join(kb.esc(l) for l in chlin), "<br>".join(kb.esc(l) for l in clin)))
        livre = 1080 - (tx + max(clarg, cond_larg)) - 40
        if livre >= 150:                          # the band never ends in a void: accent stripes off the edge
            n = min(4, int(livre // 62))
            for i in range(n):
                x0 = 1080 - i * 62
                arte.append('<polygon class="%s" points="%d,%d %d,%d %d,%d %d,%d"/>'
                            % ("a" if cor_f != "accent" else "p", x0 - 34, base, x0, base, x0 - 70, base + banda,
                               x0 - 104, base + banda))
    elif quadro == "capa":
        mid = base + banda // 2
        arte.append('<path class="l%s" stroke-width="10" d="M930 %d L1000 %d M972 %d L1000 %d L972 %d"/>'
                    % (cor_ct[0], mid, mid, mid - 26, mid, mid + 26))
        css.append(".arraste { left: 80px; top: %dpx; font-size: %dpx; font-weight: 700; line-height: 1.2; "
                   "color: %s; }" % (mid - 24, min(teto, 40), cor(cor_ct)))
        textos.append('<p class="arraste">%s</p>' % kb.esc(kb.limpo(peca.get("arraste") or "arraste para o lado",
                                                                    40, "arraste")))

    corpo_html = "    " + "\n    ".join(
        ['<svg class="arte" viewBox="0 0 1080 %d" aria-hidden="true">%s</svg>' % (h, "".join(arte[:fundo]))]
        + ([('<img class="foto" src="assets/%s" alt="">' % foto)] if foto else [])
        + ['<svg class="arte" viewBox="0 0 1080 %d" aria-hidden="true">%s</svg>' % (h, "".join(arte[fundo:]))]
        + corpo + textos) + "\n"
    css_txt = "".join("    %s\n" % l for l in css if l)
    return _cabeca(m, css_txt, ARRANJO[comp], h, corpo_html), notas
