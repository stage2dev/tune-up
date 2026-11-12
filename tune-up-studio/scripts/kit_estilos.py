"""Style scenes of the reel kit (kit_video.py): the second scene of a reel, one builder per video style of
`referencias/estilos-video/`. Each one is a device that builds itself beat by beat (a chat, a list, a counter,
a screen with a cursor...) over the small stage where the hero keeps living. Shared rules, looked at frame by
frame (round 7): the first beat is whole at the cut, every later beat pops or draws whole (no text through a
mask, no half word on a sampled frame), a beat lands about every 0.6 s and the last one is done by 2 s.
Python 3.9+, standard library only.
"""
import re

import kit_base as kb
import kit_palco as kp
from kit_palco import n as _n

# file name in referencias/estilos-video/ -> the slot of peca.json that holds the scene (None: the kit's own)
ESTILOS = {"produto-em-destaque": None, "tipografia-cinetica": "tipografia", "conversa-de-whatsapp": "conversa",
           "lista-que-se-marca-sozinha": "lista", "contador-e-grafico": "contador", "antes-e-depois": "antes_depois",
           "tela-com-cursor-clicando": "tela", "cartaz-que-se-monta": "cartaz", "passo-a-passo": "passos",
           "mito-ou-verdade": "mito"}
CONTAGEM_RE = re.compile(r"\d{1,3}(?:\.\d{3})*\Z")


def _slot(d, chave, maximo, onde, obrig=True):
    v = " ".join(str(d.get(chave) or "").split())
    return "" if not v and not obrig else kb.limpo(v, maximo, onde)


def _varios(d, chave, minimo, maximo, letras, onde):
    itens = d.get(chave) if isinstance(d.get(chave), list) else []
    itens = [kb.limpo(i, letras, onde) for i in itens][:maximo]
    if len(itens) < minimo:
        raise kb.Erro("%s precisa de %d a %d textos" % (onde, minimo, maximo))
    return itens


def _conta(onde, dur, *textos):
    total, lim = kp.palavras(*textos), kp.limite(dur)
    if total > lim:
        raise kb.Erro("%s com %d palavras (máximo %d nesta cena): encurte; o que sobra vai para a legenda"
                      % (onde, total, lim))


def _titulo(p, num, t0, dur, cor, texto, classe, alto=300, max_px=170):
    px, lin, larg = kb.caber(texto, p.fh, 880, alto, max_px, 96, (1, 2, 3) if alto > 300 else (1, 2))
    cor_t = kb.sobre(p.c, cor, True, ("bg", "text", "primary", "surface"))
    p.texto("s%d_titulo" % num, t0, dur, texto, 90, 290, px, cor_t, int(larg * 1.04) + 8, True, classe)
    p.chama('M.palavras("s%d_titulo", 0.25, 0.07, "onda");' % num)
    return cor_t, 290 + len(lin) * px


def _palco(p, t, num, t0, dur, cor, x, fim_y, maximo=940):
    """The hero's stage under the device (it takes what the device leaves). Returns the hero's two frames."""
    solo = 1760
    kp.campo(p, num, t0, dur, cor)
    larg_h = max(440, min(maximo, int((solo - fim_y - 150) / x["alto"])))
    lado = max(0, (1080 - larg_h) // 2 - 30)       # a small hero sits on its side, a big one near the middle
    cx = 540 + (lado if not x["esq"] else -lado)
    kp.arte(p, num, t0, dur, cor, t, solo, solo - int(larg_h * x["alto"]) - 44, cx, larg_h, x["estrada"], x["anda"],
            textura=False)
    return (cx - 44 * x["passo"], solo, larg_h - 16), (cx + 44 * x["passo"], solo, larg_h + 30)


def _salta(p, cid, a, t=0.36):
    p.chama('M.trilha("%s", "transform", [[%s, "scale(0)", "mola"], [%s, "scale(1)"]]);' % (cid, _n(a), _n(a + t)))


def _sombra(t, cor):
    return "var(--%s)" % kp.chao_de(t, cor)


def _tipografia(p, t, num, t0, dur, cor, d, x):
    """Bare giant lines, each one as wide as the column: all but the last are there at the cut, the last one (the
    gain, in the second color) rises word by word, a bar draws under it, then the stack pulses line by line."""
    linhas = _varios(d, "linhas", 2, 3, 14, "tipografia.linhas")
    _conta("tipografia", dur, *linhas)
    cor_t = kb.sobre(p.c, cor, True, ("bg", "text", "primary", "surface"))
    cor_d = kb.destaque(p.c, cor, cor_t)
    y, ids, larg = 290, [], 0
    for k, linha in enumerate(linhas):
        px, _, larg = kb.caber(linha, p.fh, 900, 300, 300, 110, (1,))
        cid = "s%d_titulo" % num if k == 0 else "s%d_linha%d" % (num, k + 1)
        p.texto(cid, t0, dur, linha, 90, y, px, cor_d if k == len(linhas) - 1 else cor_t, titulo=True,
                classes="l-cheia" if k == 0 else "")
        ultima = k == len(linhas) - 1
        p.chama('M.palavras("%s", %s, 0.09, "%s", 0.4);' % (cid, _n(0.7 if ultima else 0.2 + 0.12 * k),
                                                           "sobe" if ultima else "onda"))
        ids.append(cid)
        y += px + 14
    p.regra("s%d_barra" % num, "left: 90px; top: %dpx; width: %dpx; height: 24px; background: %s;"
            % (y + 4, int(larg), p.cor("accent" if cor_d != "accent" else cor_t)))
    p.clip("s%d_barra" % num, t0, dur)
    p.chama('M.entra("s%d_barra", 1.25, 0.4, "barra");' % num)
    p.chama('M.onda(%s, %s, 0.12, 1.05);' % (str(ids[1:]).replace("'", '"'), _n(t0 + 1.9)))
    p.chama('M.camera(%s, 1, 1.05, 90, 290);' % str(ids[:1]).replace("'", '"'))
    return _palco(p, t, num, t0, dur, cor, x, y + 30)


def _conversa(p, t, num, t0, dur, cor, d, x):
    """A chat: the customer's question big in its bubble at the cut, the typing dots, then the business's
    answers popping from their corner one by one."""
    c = p.c
    pergunta = _slot(d, "pergunta", 28, "conversa.pergunta")
    respostas = _varios(d, "respostas", 1, 2, 26, "conversa.respostas")
    _conta("conversa (pergunta + respostas)", dur, pergunta, *respostas)
    px, lin, larg = kb.caber(pergunta, p.fh, 760, 320, 160, 96, (1, 2))
    alt = int(len(lin) * px * 1.05) + 80
    topo = 290
    if x["logo"]:                                  # who answers: the brand's logo and name head the chat
        cor_m = kb.sobre(c, cor, False, ("bg", "text", "surface"))
        p.regra("s%d_bloco3" % num, "left: 82px; top: 274px; width: 116px; height: 116px; z-index: 2; "
                "clip-path: circle(50%% at 50%% 50%%); background: %s;" % p.cor("bg"))
        p.clip("s%d_bloco3" % num, t0, dur)
        p.regra("s%d_logo" % num, "left: 90px; top: 282px; width: 100px; height: 100px;")
        p.clip("s%d_logo" % num, t0, dur, "img", attrs=' src="assets/%s" alt=""' % x["logo"])
        p.texto("s%d_marca" % num, t0, dur, p.m["nome"], 222, 300, 54, cor_m, titulo=True, lh=1.2,
                extra="letter-spacing: 0;")
        topo = 430
    p.texto("s%d_titulo" % num, t0, dur, pergunta, 90, topo, px, kb.sobre(c, "bg", True, ("text", "primary")),
            int(larg * 1.04) + 8, True, "l-lista", 1.05,
            "padding: 36px 44px 44px; background: %s; border-radius: 60px 60px 60px 12px; box-shadow: 14px 14px 0 %s;"
            % (p.cor("bg"), _sombra(t, cor)))
    p.chama('M.palavras("s%d_titulo", 0.2, 0.07, "onda");' % num)
    y = topo + alt + 56
    fala = "accent" if cor != "accent" else "surface"
    cor_f = kb.sobre(c, fala, False, ("text", "primary", "bg"))
    # the typing dots sit where the next answer will pop
    p.css.append("#s%d_digita span { display: block; width: 26px; height: 26px; margin: 0 9px; "
                 "border-radius: 50%%; background: %s; }" % (num, p.cor(cor_f)))
    p.regra("s%d_digita" % num, "left: 780px; top: %dpx; width: 210px; height: 100px; box-sizing: border-box; "
            "display: flex; justify-content: center; align-items: center; background: %s; border-radius: 50px 50px 12px 50px;"
            % (y, p.cor(fala)))
    p.clip("s%d_digita" % num, t0, dur, "div", "".join('<span id="a%d_ponto%d"></span>' % (num, k) for k in (1, 2, 3)))
    visivel, desce, a = [[0, "1"]], [], t0
    rpx = min(kb.caber(r, p.ft, 720, 110, 88, 56, (1,), 1.2, 0)[0] for r in respostas)   # one size for the answers
    for k, r in enumerate(respostas, 1):
        a = t0 + (0.7 if k == 1 else 1.4)
        w = int(kb.largura_px(r, p.ft, rpx, 0) * 1.04) + 8
        cid = "s%d_fala%d" % (num, k)
        p.texto(cid, t0, dur, r, 990 - w - 88, y, rpx, cor_f, w,
                extra="padding: 26px 44px 30px; background: %s; border-radius: 50px 50px 12px 50px; "
                      "transform-origin: 100%% 100%%; box-shadow: 14px 14px 0 %s;" % (p.cor(fala), _sombra(t, cor)))
        _salta(p, cid, a)
        visivel += [[a - 0.02, "1", "reta"], [a, "0"]]
        y += int(rpx * 1.2) + 56 + 40
        if k < len(respostas):
            visivel += [[a + 0.3, "0", "reta"], [a + 0.32, "1"]]
            desce = [[a, "translateY(0px)", "reta"], [a + 0.02, "translateY(%dpx)" % (int(rpx * 1.2) + 96)]]
    p.chama('M.trilha("s%d_digita", "opacity", %s);' % (num, _js(visivel)))
    if desce:
        p.chama('M.trilha("s%d_digita", "transform", %s);' % (num, _js(desce)))
    for k in (1, 2, 3):
        p.chama('M.vaivem("a%d_ponto%d", %s, %s, "translateY(0px)", "translateY(-16px)", 0.42);'
                % (num, k, _n(t0 + 0.1 * k), _n(a)))
    p.chama('M.onda(["s%d_fala%d"], %s, 0, 1.07);' % (num, len(respostas), _n(a + 0.65)))
    return _palco(p, t, num, t0, dur, cor, x, y)


def _js(q):
    return "[%s]" % ", ".join("[%s]" % ", ".join(('"%s"' % v) if isinstance(v, str) else _n(v) for v in item)
                               for item in q)


def _contador(p, t, num, t0, dur, cor, d, x):
    """A count of the briefing (items, years, customers) running up inside a ring that closes with it."""
    c = p.c
    numero = _slot(d, "numero", 7, "contador.numero")
    rotulo, apoio = _slot(d, "rotulo", 28, "contador.rotulo"), _slot(d, "apoio", 32, "contador.apoio", False)
    if not CONTAGEM_RE.match(numero):
        raise kb.Erro("contador.numero é uma contagem do briefing, só algarismos ('%s'): preço, porcentagem e "
                      "nota não contam; o preço vai em oferta.valor" % numero)
    _conta("contador", dur, numero, rotulo, apoio)
    cx, cy, r = 540, 650, 300
    cor_t = kb.sobre(c, cor, True, ("bg", "text", "primary", "surface"))
    anel = "a" if cor != "accent" else "b"
    marca = kb.sobre(c, "accent" if anel == "a" else "bg", True, ("text", "primary", "bg"))[0]
    p.css.append("#a%d_anel { stroke-dasharray: 1; stroke-dashoffset: 1; }" % num)
    p.regra("s%d_icone" % num, kp.CHEIO)
    p.clip("s%d_icone" % num, t0, dur, "svg",
           '<circle class="l%s" stroke-width="44" cx="%d" cy="%d" r="%d"/>'
           '<circle id="a%d_anel" class="l%s" stroke-width="44" pathLength="1" cx="%d" cy="%d" r="%d" '
           'transform="rotate(-90 %d %d)"/>'
           '<g transform="translate(%d %d)"><g id="a%d_selo"><circle class="%s" cx="8" cy="8" r="84"/>'
           '<circle class="%s" r="84"/><path class="l%s" stroke-width="24" d="M-36 2 L-10 30 L40 -28"/></g></g>'
           % (kp.chao_de(t, cor)[0], cx, cy, r, num, anel, cx, cy, r, cx, cy, cx + 212, cy - 212, num,
              kp.chao_de(t, cor)[0], anel, marca), attrs=kp.SVG)
    px, _, _ = kb.caber(numero, p.fh, 400, 300, 300, 130, (1,))
    p.texto("s%d_numero" % num, t0, dur, numero, cx - 260, cy - px // 2, px, cor_t, 520, True,
            extra="text-align: center; letter-spacing: 0;")
    p.chama('M.contador("s%d_numero", 0.15, 0.95);' % num)
    p.chama('M.traco("a%d_anel", %s, 0.95);' % (num, _n(t0 + 0.15)))
    _salta(p, "a%d_selo" % num, t0 + 1.15)
    p.chama('M.onda(["s%d_numero"], %s, 0, 1.12);' % (num, _n(t0 + 1.15)))
    p.chama('M.onda(["s%d_numero"], %s, 0, 1.06);' % (num, _n(t0 + 1.95)))
    y = cy + r + 70
    tpx, lin, larg = kb.caber(rotulo, p.fh, 880, 250, 140, 96, (1, 2))
    p.texto("s%d_titulo" % num, t0, dur, rotulo, 90, y, tpx, cor_t, int(larg * 1.04) + 8, True, "l-faixa")
    p.chama('M.palavras("s%d_titulo", 1.2, 0.07, "onda");' % num)
    y += len(lin) * tpx
    if apoio:
        apx, _, _ = kb.caber(apoio, p.ft, 880, 90, 68, 48, (1,), 1.2, 0)
        p.texto("s%d_apoio" % num, t0, dur, apoio, 90, y + 16, apx, kb.sobre(c, cor, False, ("bg", "text", "surface")))
        p.chama('M.entra("s%d_apoio", 1.3, 0.35, "sobe");' % num)
        y += int(apx * 1.2) + 16
    return _palco(p, t, num, t0, dur, cor, x, y)


def _etiqueta(p, cid, t0, dur, texto, y, fundo):
    p.texto(cid, t0, dur, texto, 90, y, 50, kb.sobre(p.c, fundo, False, ("text", "primary", "bg")),
            extra="padding: 8px 26px 10px; letter-spacing: .08em; background: %s;" % p.cor(fundo))
    return y + 78 + 22


def _antes_depois(p, t, num, t0, dur, cor, d, x):
    """Before, struck through; after, highlighted; the hero changes at that beat."""
    c = p.c
    antes, depois = _slot(d, "antes", 22, "antes_depois.antes"), _slot(d, "depois", 24, "antes_depois.depois")
    _conta("antes e depois", dur, "antes", antes, "depois", depois)
    fraco = kb.sobre(c, cor, False, ("surface", "bg", "text"))
    y = _etiqueta(p, "s%d_selo" % num, t0, dur, "ANTES", 290, fraco)
    apx, _, alarg = kb.caber(antes, p.fh, 860, 130, 120, 64, (1,))
    p.texto("s%d_apoio" % num, t0, dur, antes, 90, y, apx, fraco, titulo=True)
    p.regra("s%d_risco" % num, "left: 78px; top: %dpx; width: %dpx; height: 16px; z-index: 4; background: %s;"
            % (y + int(apx * 0.56), int(alarg) + 24, p.cor("accent" if cor != "accent" else "text")))
    p.clip("s%d_risco" % num, t0, dur)
    p.chama('M.entra("s%d_risco", 0.5, 0.35, "barra");' % num)
    y += apx + 56
    fundo = "accent" if cor != "accent" else "bg"
    y2 = _etiqueta(p, "s%d_selo2" % num, t0, dur, "DEPOIS", y, fundo)
    p.regra("s%d_selo2" % num, "transform-origin: 0 50%;")
    p.chama('M.entra("s%d_selo2", 0.95, 0.4, "carimbo");' % num)
    px, lin, larg = kb.caber(depois, p.fh, 880, 300, 170, 96, (1, 2))
    cor_t = kb.sobre(c, cor, True, ("bg", "text", "primary", "surface"))
    p.texto("s%d_titulo" % num, t0, dur, depois, 90, y2, px, cor_t, int(larg * 1.04) + 8, True, "l-faixa")
    p.chama('M.onda(["s%d_titulo"], %s, 0, 1.06);' % (num, _n(t0 + 1.2)))
    fim = y2 + len(lin) * px
    p.regra("s%d_barra" % num, "left: 90px; top: %dpx; width: %dpx; height: 22px; background: %s;"
            % (fim + 10, int(kb.largura_px(lin[-1], p.fh, px, -0.02)), p.cor(fundo)))
    p.clip("s%d_barra" % num, t0, dur)
    p.chama('M.entra("s%d_barra", 1.1, 0.4, "barra");' % num)
    p.chama('M.onda(["s%d_selo2", "s%d_titulo"], %s, 0.1, 1.06);' % (num, num, _n(t0 + 1.9)))
    x["payoff"] = t0 + 0.95
    return _palco(p, t, num, t0, dur, cor, x, fim + 40)


def _tela(p, t, num, t0, dur, cor, d, x):
    """A product screen: the cursor travels to the button, clicks (a ring spreads) and the button answers."""
    c = p.c
    titulo, botao = _slot(d, "titulo", 28, "tela.titulo"), _slot(d, "botao", 18, "tela.botao")
    feito = _slot(d, "feito", 18, "tela.feito")
    _conta("tela", dur, titulo, botao, feito)
    _, y = _titulo(p, num, t0, dur, cor, titulo, "l-faixa")
    y += 64
    forte = t["forte"]
    alt, by = 500, y + 250
    p.css.append("#s%d_tela span { position: absolute; display: block; border-radius: 22px; background: %s; }"
                 % (num, p.cor("surface")))
    p.regra("s%d_tela" % num, "left: 90px; top: %dpx; width: 900px; height: %dpx; z-index: 2; background: %s; "
            "border-radius: 48px; box-shadow: 18px 18px 0 %s;" % (y, alt, p.cor("bg"), _sombra(t, cor)))
    p.clip("s%d_tela" % num, t0, dur, "div",
           '<span style="left: 56px; top: 50px; width: 44px; height: 44px; background: %s;"></span>'
           '<span style="left: 116px; top: 50px; width: 44px; height: 44px;"></span>'
           '<span style="left: 70px; top: 136px; width: 520px; height: 40px;"></span>'
           '<span style="left: 70px; top: 196px; width: 330px; height: 30px;"></span>' % p.cor("accent"))
    bpx, _, blarg = kb.caber(botao, p.fh, 640, 110, 96, 52, (1,))
    fpx, _, flarg = kb.caber(feito, p.fh, 640, 110, 96, 52, (1,))
    a = t0 + 1.05                                  # the click
    for cid, fundo, texto, tpx, vis in (("botao", forte, botao, bpx, ("1", "0")), ("feito", "accent", feito, fpx, ("0", "1"))):
        p.regra("s%d_%s2" % (num, cid), "left: 160px; top: %dpx; width: 760px; height: 170px; z-index: 2; "
                "background: %s; border-radius: 85px;" % (by, p.cor(fundo)))
        p.clip("s%d_%s2" % (num, cid), t0, dur)
        p.texto("s%d_%s" % (num, cid), t0, dur, texto, 160, by + (170 - tpx) // 2, tpx,
                kb.sobre(c, fundo, True, ("bg", "text", "primary")), 760, True, extra="text-align: center;")
        for alvo in ("s%d_%s2" % (num, cid), "s%d_%s" % (num, cid)):
            p.chama('M.trilha("%s", "opacity", [[%s, "%s", "reta"], [%s, "%s"]]);'
                    % (alvo, _n(a), vis[0], _n(a + 0.03), vis[1]))
    p.chama('M.onda(["s%d_feito2", "s%d_feito"], %s, 0, 1.08);' % (num, num, _n(a + 0.05)))
    p.chama('M.onda(["s%d_feito2", "s%d_feito"], %s, 0, 1.05);' % (num, num, _n(a + 0.9)))
    kp.toque(p, num, t0, dur, (860, y + alt + 150), (800, by + 128), a, "bg")
    return _palco(p, t, num, t0, dur, cor, x, y + alt + 18)


def _cartaz(p, t, num, t0, dur, cor, d, x):
    """A paste-up poster: color strips with one phrase each, stamped one over the other, slightly crooked."""
    c = p.c
    blocos = _varios(d, "blocos", 2, 3, 14, "cartaz.blocos")
    _conta("cartaz", dur, *blocos)
    fundos = [f for f in ("bg", "accent", "surface") if f != cor]
    giros = (-3, 2.5, -2)
    y, ids = 300, []
    for k, texto in enumerate(blocos):
        px, _, larg = kb.caber(texto, p.fh, 780, 230, 230, 110, (1,))
        w, fundo = int(larg * 1.04) + 8, fundos[k % len(fundos)]
        cid = "s%d_titulo" % num if k == 0 else "s%d_tira%d" % (num, k + 1)
        esq = 70 if k % 2 == 0 else 1010 - (w + 80)
        p.texto(cid, t0, dur, texto, esq, y, px, kb.sobre(c, fundo, True, ("text", "primary", "bg")), w, True,
                "l-cheia" if k == 0 else "",
                extra="padding: 22px 40px 30px; background: %s; box-shadow: 16px 16px 0 %s;%s"
                      % (p.cor(fundo), _sombra(t, cor),
                         " z-index: %d;" % (3 + k) if k else " transform: rotate(%sdeg);" % _n(giros[0])))
        a = t0 + 0.6 * k
        if k:
            p.chama('M.trilha("%s", "transform", [[%s, "scale(1.9) rotate(%sdeg)", "mola"], [%s, "scale(1) rotate(%sdeg)"]]);'
                    % (cid, _n(a), _n(giros[k] - 10), _n(a + 0.4), _n(giros[k])))
            p.chama('M.trilha("%s", "opacity", [[%s, "0", "reta"], [%s, "1"]]);' % (cid, _n(a), _n(a + 0.1)))
            ids.append(cid)                        # the first strip is whole and still at the cut
        y += px + 52 + 26
    p.chama('M.onda(%s, %s, 0.12, 1.07);' % (str(ids).replace("'", '"'), _n(t0 + 0.6 * len(blocos) + 0.25)))
    return _palco(p, t, num, t0, dur, cor, x, y + 10)


def _passos(p, t, num, t0, dur, cor, d, x):
    """Steps on a rail: the line draws down, each knot fills and its step rises in turn."""
    c = p.c
    titulo, itens = _slot(d, "titulo", 26, "passos.titulo"), _varios(d, "itens", 2, 3, 20, "passos.itens")
    _conta("passo a passo", dur, titulo, *itens)
    _, y = _titulo(p, num, t0, dur, cor, titulo, "l-lista", max_px=150)
    y += 70
    ipx = min(kb.caber(i, p.fh, 700, 110, 100, 60, (1,))[0] for i in itens)
    passo_y = ipx + 74
    trilho, cor_no = kp.chao_de(t, cor)[0], ("a" if cor != "accent" else "b")
    x0, ys = 140, [y + ipx // 2 + k * passo_y for k in range(len(itens))]
    partes = ['<path class="l%s" stroke-width="18" d="M%d %d L%d %d"/>' % (trilho, x0, ys[0], x0, ys[-1]),
              '<path id="a%d_fio" class="l%s" stroke-width="18" pathLength="1" d="M%d %d L%d %d"/>'
              % (num, cor_no, x0, ys[0], x0, ys[-1])]
    cor_i = kb.sobre(c, cor, True, ("bg", "text", "surface"))
    for k, (item, yk) in enumerate(zip(itens, ys), 1):
        a = t0 + 0.6 * (k - 1)
        partes.append('<circle class="%s" cx="%d" cy="%d" r="44"/><g transform="translate(%d %d)"><g id="a%d_no%d">'
                      '<circle class="%s" r="44"/><circle class="%s" r="16"/></g></g>'
                      % (trilho, x0, yk, x0, yk, num, k, cor_no, "t" if cor_no == "a" else "p"))
        p.texto("s%d_item%d" % (num, k), t0, dur, item, 224, yk - ipx // 2, ipx, cor_i, titulo=True)
        if k > 1:
            _salta(p, "a%d_no%d" % (num, k), a)
            p.chama('M.entra("s%d_item%d", %s, 0.35, "sobe");' % (num, k, _n(a - t0)))
        else:
            p.chama('M.palavras("s%d_item1", 0.2, 0.07, "onda");' % num)
    p.css.append("#a%d_fio { stroke-dasharray: 1; stroke-dashoffset: 1; }" % num)
    p.chama('M.traco("a%d_fio", %s, %s);' % (num, _n(t0 + 0.15), _n(0.6 * (len(itens) - 1))))
    p.regra("s%d_icone" % num, kp.CHEIO)
    p.clip("s%d_icone" % num, t0, dur, "svg", "".join(partes), attrs=kp.SVG)
    p.chama('M.onda(["s%d_item%d"], %s, 0, 1.06);' % (num, len(itens), _n(t0 + 0.6 * len(itens) + 0.2)))
    return _palco(p, t, num, t0, dur, cor, x, ys[-1] + ipx // 2 + 20)


def _mito(p, t, num, t0, dur, cor, d, x):
    """A sentence people repeat, the stamp that judges it, then the briefing's fact."""
    c = p.c
    frase, resposta = _slot(d, "frase", 34, "mito.frase"), _slot(d, "resposta", 34, "mito.resposta")
    selo = str(d.get("selo") or "").strip().lower()
    if selo not in ("mito", "verdade"):
        raise kb.Erro('mito.selo é "mito" ou "verdade"')
    _conta("mito ou verdade", dur, frase, selo, resposta)
    _, y = _titulo(p, num, t0, dur, cor, frase, "l-faixa", alto=400, max_px=150)
    cor_s = "accent" if cor != "accent" else "bg"
    spx = 150 if selo == "mito" else 120
    w = int(kb.largura_px(selo.upper(), p.fh, spx, 0.04) * 1.04) + 8
    p.texto("s%d_selo" % num, t0, dur, selo.upper(), 990 - w - 100, y + 24, spx, cor_s, w, True,
            extra="padding: 6px 30px 14px; letter-spacing: .04em; border: 16px solid %s; transform-origin: 50%% 50%%;"
                  % p.cor(cor_s))
    a = t0 + 0.7
    p.chama('M.trilha("s%d_selo", "transform", [[%s, "scale(2.2) rotate(-20deg)", "mola"], '
            '[%s, "scale(1) rotate(-7deg)"]]);' % (num, _n(a), _n(a + 0.4)))
    p.chama('M.trilha("s%d_selo", "opacity", [[%s, "0", "reta"], [%s, "1"]]);' % (num, _n(a), _n(a + 0.1)))
    y += spx + 52 + 90
    apx, lin, alarg = kb.caber(resposta, p.ft, 880, 230, 104, 60, (1, 2), 1.15, 0)
    p.texto("s%d_apoio" % num, t0, dur, resposta, 90, y, apx, kb.sobre(c, cor, False, ("bg", "text", "surface")),
            int(alarg * 1.04) + 8, lh=1.15)
    p.chama('M.entra("s%d_apoio", 1.3, 0.35, "sobe");' % num)
    y += int(len(lin) * apx * 1.15) + 14
    p.regra("s%d_barra" % num, "left: 90px; top: %dpx; width: %dpx; height: 18px; background: %s;"
            % (y, int(kb.largura_px(lin[-1], p.ft, apx, 0)), p.cor(cor_s)))
    p.clip("s%d_barra" % num, t0, dur)
    p.chama('M.entra("s%d_barra", 1.6, 0.4, "barra");' % num)
    return _palco(p, t, num, t0, dur, cor, x, y + 30)


CENAS = {"tipografia": _tipografia, "conversa": _conversa, "contador": _contador, "antes_depois": _antes_depois,
         "tela": _tela, "cartaz": _cartaz, "passos": _passos, "mito": _mito}
