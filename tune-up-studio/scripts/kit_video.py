"""Reel composition of the kit (montar.py --tipo video): a finished 10 or 15 s vertical reel that takes the
brand, the texts of `peca.json` and the hero drawing. What the composition guarantees, because it was built
and looked at frame by frame instead of being redrawn each time:
- every scene opens whole (title and hero in place at the cut; no text enters through a mask or from outside);
- cuts sit off the 0.5 s grid, so a frame sampled every 0.5 s never lands on a transition;
- the hero is one drawing that lives the whole video on a light stage, reframed at every cut (wide, close-up,
  mid, end card at 60% of the width or more), always moving, and transformed in the offer scene;
- type sized from the real font to fill the safe width; the price stamped on an accent band; a full end card.
Python 3.9+, standard library only.
"""
import os

import kit_base as kb
import kit_estilos as ke
import kit_palco as kp
from kit_palco import n as _n

# Cuts on the 1/8 s offsets (1.875, 4.375...): a frame sampled every 0.5 s or 0.25 s never lands on a transition.
TEMPOS = {10: (1.875, 2.5, 2.5, 3.125), 15: (1.875, 3.0, 3.0, 3.0, 4.125)}
# With a style scene (kit_estilos.py) the hook gives it a quarter of a second: 2.75 s hold 8 words and 3 beats.
TEMPOS_ESTILO = {10: (1.625, 2.75, 2.5, 3.125), 15: TEMPOS[15]}
MOTOR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "referencias", "motor-motion.js")
PAGINA = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <style>
    %s
    html, body { margin: 0; background: %s; }
    #root { --bg: %s; --surface: %s; --primary: %s; --text: %s; --accent: %s;
            position: relative; width: 1080px; height: 1920px; overflow: hidden; text-wrap: balance;
            background: var(--bg); color: var(--text); font-family: "Brand Body", sans-serif; font-size: 48px; }
    .clip { position: absolute; margin: 0; z-index: 3; }
    .m-caixa { display: inline-block; padding: .12em 0 .2em; margin: -.12em 0 -.2em; vertical-align: top; }
    .m-palavra { display: inline-block; }
    %s
    %s
  </style>
</head>
<body>
  <div id="root" data-composition-id="video" data-start="0" data-duration="%d"
       data-width="1080" data-height="1920" data-fps="30" data-estilo="%s" data-no-timeline>
    %s
  </div>
  <script>
%s
    %s
    M.pronto();
  </script>
</body>
</html>
"""


def _slot(d, chave, maximo, onde, obrig=True):
    v = " ".join(str(d.get(chave) or "").split())
    return "" if not v and not obrig else kb.limpo(v, maximo, onde)


def _conta(onde, lim, *textos):
    total = kp.palavras(*textos)
    if total > lim:
        raise kb.Erro("%s com %d palavras (máximo %d nesta cena): corte ou passe um fato para a legenda"
                      % (onde, total, lim))


def _gancho(p, t, num, t0, dur, cor, g, x):
    c = p.c
    titulo, dest = _slot(g, "titulo", 40, "gancho.titulo"), _slot(g, "destaque", 40, "gancho.destaque", False)
    if len(titulo) + len(dest) + 1 > 40:
        raise kb.Erro("gancho com %d caracteres (titulo + destaque, máximo 40)" % (len(titulo) + len(dest) + 1))
    _conta("gancho", kp.limite(dur), titulo, dest)
    numero = bool(g.get("numero"))
    px_t, px_d, lin_t, lin_d, larg_t, larg_d = kp.titulo_duplo(p, titulo, dest, 860, 560, 250, numero)
    lh = 0.92 if numero else 1.0
    cor_t = kb.sobre(c, cor, True, ("bg", "text", "primary", "surface"))
    kp.campo(p, num, t0, dur, cor)
    solo = 1750
    fim_t = 290 + int(len(lin_t) * px_t * lh + len(lin_d) * px_d)
    topo = fim_t + 120
    cx = 540 + (70 if not x["esq"] else -70)
    # the hero grows into what the title leaves
    # a hero whose problem state is shorter (`heroi_topo_antes`) may grow past the frame's width: it fills the hook
    larg_h = max(760 if x["foto"] else 900, min(1140 if x["alto_antes"] == x["alto"] else 1400,
                                               int((solo - topo - 30) / x["alto_antes"])))
    kp.arte(p, num, t0, dur, cor, t, solo, topo, cx, larg_h, x["estrada"], x["anda"], canto=True,
            textura=kp.claro(cor))
    p.texto("s1_titulo", t0, dur, titulo, 90, 290, px_t, cor_t, int(larg_t * 1.04) + 8, True,
            "l-numero" if numero else "l-topo", lh)
    ids = ["s1_titulo"]
    if dest:
        p.texto("s1_destaque", t0, dur, dest, 90, 290 + int(len(lin_t) * px_t * lh), px_d,
                kb.destaque(c, cor, cor_t), int(larg_d * 1.04) + 8, True)
        ids.append("s1_destaque")
        p.chama('M.palavras("s1_destaque", 0.55, 0.08, "onda");')
        # a marker draws itself under the key words: the hook changes on screen before the first second ends
        p.regra("s1_barra", "left: 90px; top: %dpx; width: %dpx; height: 20px; background: %s;"
                % (fim_t + 8, int(kb.largura_px(lin_d[-1], p.fh, px_d, -0.02)), p.cor(kb.destaque(c, cor, cor_t))))
        p.clip("s1_barra", t0, dur)
        p.chama('M.entra("s1_barra", 0.4, 0.5, "barra");')
    p.chama('M.palavras("s1_titulo", 0.15, 0.08, "onda");')
    p.chama('M.camera(%s, 1, 1.045, 90, 290);' % str(ids).replace("'", '"'))
    p.notas.append("cena 1 (gancho): titulo %d px, %d linha(s)" % (px_t, len(lin_t) + len(lin_d)))
    return (cx - 90 * x["passo"], solo, larg_h - 60), (cx + 70 * x["passo"], solo, larg_h + (30 if x["passo"] else 70))


def _rampa(p, t, num, t0, dur, cor, ra, x):
    c = p.c
    titulo, apoio = _slot(ra, "titulo", 36, "rampa.titulo"), _slot(ra, "apoio", 40, "rampa.apoio", False)
    _conta("rampa", kp.limite(dur), titulo, apoio)
    px, lin, larg = kb.caber(titulo, p.fh, 880, 390, 210, 96, (1, 2))
    faixa_y = 930
    kp.campo(p, num, t0, dur, "bg")
    arte = ['<circle class="ls" stroke-width="40" cx="%d" cy="520" r="340"/>' % (700 if not x["esq"] else 380)]
    if t["textura"] != "nenhuma":
        arte.append(kb.pontos(70 if not x["esq"] else 690, 60, 7, 4, 52, 8, t["forte"][0]))
    arte.append('<rect class="%s" x="0" y="%d" width="1080" height="%d"/>' % (cor[0], faixa_y, 1920 - faixa_y))
    for i in range(4):
        x0 = (1080 - i * 76) if not x["esq"] else (i * 76 + 150)
        arte.append('<polygon class="a" points="%d,1600 %d,1600 %d,1920 %d,1920"/>' % (x0 - 40, x0, x0 - 110, x0 - 150))
    p.regra("s%d_bloco2" % num, "%s z-index: 1;" % kp.CHEIO)
    p.clip("s%d_bloco2" % num, t0, dur, "svg", "".join(arte), attrs=kp.SVG)
    ty = faixa_y + 84
    cor_t = kb.sobre(c, cor, True, ("bg", "text", "primary", "surface"))
    p.texto("s%d_titulo" % num, t0, dur, titulo, 90, ty, px, cor_t, int(larg * 1.04) + 8, True, "l-base")
    p.chama('M.palavras("s%d_titulo", 0.3, 0.07, "onda");' % num)
    ry = ty + len(lin) * px + 22
    p.regra("s%d_barra" % num, "left: 90px; top: %dpx; width: %dpx; height: 18px; background: %s;"
            % (ry, int(kb.largura_px(lin[-1], p.fh, px, -0.02)), p.cor("accent")))
    p.clip("s%d_barra" % num, t0, dur)
    p.chama('M.entra("s%d_barra", 0.35, 0.45, "barra");' % num)
    if apoio:
        apx, _, _ = kb.caber(apoio, p.ft, 880, 100, 76, 48, (1,), 1.2, 0)
        p.texto("s%d_apoio" % num, t0, dur, apoio, 90, ry + 50, apx, kb.sobre(c, cor, False, ("bg", "text", "primary")))
        p.chama('M.entra("s%d_apoio", 0.55, 0.35, "sobe");' % num)
    p.notas.append("cena %d (rampa): titulo %d px" % (num, px))
    return (540 - 70 * x["passo"], faixa_y + 34, 1300), (540 + 70 * x["passo"], faixa_y + 34, 1380)


def _lista(p, t, num, t0, dur, cor, li, x):
    c = p.c
    titulo = _slot(li, "titulo", 30, "lista.titulo")
    itens = [kb.limpo(i, 26, "lista.itens") for i in (li.get("itens") if isinstance(li.get("itens"), list) else [])][:3]
    if len(itens) < 2:
        raise kb.Erro("lista.itens precisa de 2 ou 3 itens (vídeo de 15 s)")
    _conta("lista", kp.limite(dur), titulo, *itens)
    px, lin, larg = kb.caber(titulo, p.fh, 860, 300, 200, 96, (1, 2))
    kp.campo(p, num, t0, dur, cor)
    ipx = min(kb.caber(i, p.ft, 740, 100, 84, 56, (1,), 1.2, 0)[0] for i in itens)
    iy = 290 + len(lin) * px + 64
    passo_y = int(ipx * 1.75)
    solo, cx, larg_h = 1750, (700 if not x["esq"] else 380), 720
    topo = max(iy + len(itens) * passo_y + 30, solo - int(larg_h * x["alto"]) - 60)
    kp.arte(p, num, t0, dur, cor, t, solo, topo, cx, larg_h, x["estrada"], x["anda"], textura=False)
    p.texto("s%d_titulo" % num, t0, dur, titulo, 90, 290, px, kb.sobre(c, cor, True, ("bg", "text", "primary")),
            int(larg * 1.04) + 8, True, "l-lista")
    p.chama('M.palavras("s%d_titulo", 0.3, 0.07, "onda");' % num)
    marcas, cor_tq = [], kb.sobre(c, "accent", True, ("text", "primary", "bg"))[0]
    for k, item in enumerate(itens, 1):   # the items are there from the cut; the ticks draw themselves one by one
        y, atraso = iy + (k - 1) * passo_y, 0.5 + (k - 1) * 0.6
        marcas.append('<circle class="a" cx="%d" cy="%d" r="%d"/><path id="a%d_tique%d" class="l%s" stroke-width="14" '
                      'pathLength="1" d="M%d %d L%d %d L%d %d"/>'
                      % (90 + ipx // 2, y + ipx * 0.6, ipx // 2, num, k, cor_tq, 90 + ipx * 0.27, y + ipx * 0.62,
                         90 + ipx * 0.44, y + ipx * 0.8, 90 + ipx * 0.74, y + ipx * 0.42))
        p.texto("s%d_item%d" % (num, k), t0, dur, item, 90 + ipx + 30, y, ipx, kb.sobre(c, cor, False, ("bg", "text")))
        p.chama('M.traco("a%d_tique%d", %s, 0.3);' % (num, k, _n(t0 + atraso)))
        p.chama('M.palavras("s%d_item%d", %s, 0.06, "onda");' % (num, k, _n(atraso)))
    # one more beat once the last tick is drawn: the whole list answers in a wave
    p.chama('M.onda(%s, %s, 0.1, 1.05);' % (str(["s%d_item%d" % (num, k) for k in range(1, len(itens) + 1)]).replace("'", '"'),
                                           _n(t0 + 0.5 + len(itens) * 0.6)))
    p.css.append("#s%d_icone path { stroke-dasharray: 1; stroke-dashoffset: 1; }" % num)
    p.regra("s%d_icone" % num, kp.CHEIO)
    p.clip("s%d_icone" % num, t0, dur, "svg", "".join(marcas), attrs=kp.SVG)
    return (cx - 40 * x["passo"], solo, larg_h - 20), (cx + 40 * x["passo"], solo, larg_h + 30)


def _oferta(p, t, num, t0, dur, cor, of, x):
    c = p.c
    rotulo = _slot(of, "nome", 28, "oferta.nome").upper()
    valor, prova = _slot(of, "valor", 16, "oferta.valor"), _slot(of, "prova", 36, "oferta.prova", False)
    _conta("oferta (nome + valor + prova)", kp.limite(dur), rotulo, valor, prova)
    kp.campo(p, num, t0, dur, cor)
    rpx, _, rlarg = kb.caber(rotulo, p.ft, 820, 80, 60, 44, (1,), 1.2, 0.05)
    vpx, vlin, vlarg = kb.caber(valor, p.fh, 880, 400, 420, 150, (1, 2), 0.95, piso=220)
    if vlarg > 892:
        raise kb.Erro("oferta.valor não cabe grande na faixa ('%s'): só o preço ou a palavra da oferta, o resto "
                      "vai em oferta.nome e oferta.prova" % valor)
    by = 290 + int(rpx * 1.2) + 56
    balt = int(len(vlin) * vpx * 0.95) + 70
    solo, cx = 1750, 540 + (40 if not x["esq"] else -40)
    topo = by + balt + (150 if prova else 60)
    larg_h = max(820, min(1040, int((solo - topo - 50) / x["alto"])))
    kp.arte(p, num, t0, dur, cor, t, solo, topo, cx, larg_h, x["estrada"], x["anda"],
            forma="corte" if t["palco"] == "disco" else "disco")
    cor_tag = "bg" if not kp.claro(cor) else t["forte"]
    p.regra("s%d_bloco3" % num, "left: 0; top: 270px; width: %dpx; height: %dpx; z-index: 2; background: %s; "
            "clip-path: polygon(0 0, 100%% 0, calc(100%% - 34px) 100%%, 0 100%%);"
            % (int(rlarg) + 166, int(rpx * 1.2) + 40, p.cor(cor_tag)))
    p.clip("s%d_bloco3" % num, t0, dur)
    p.texto("s%d_selo" % num, t0, dur, rotulo, 90, 290, rpx, kb.sobre(c, cor_tag, False, ("text", "primary", "bg")),
            extra="letter-spacing: .05em;")
    p.regra("s%d_barra" % num, "left: 0; top: %dpx; width: 1080px; height: %dpx; z-index: 2; background: %s; "
            "clip-path: polygon(0 8%%, 100%% 0, 100%% 92%%, 0 100%%);" % (by, balt, p.cor("accent")))
    p.clip("s%d_barra" % num, t0, dur)
    p.texto("s%d_titulo" % num, t0, dur, valor, 90, by + 36, vpx, kb.sobre(c, "accent", True, ("text", "primary", "bg")),
            int(vlarg * 1.04) + 8, True, "l-numero", 0.95)
    p.chama('M.onda(["s%d_titulo"], %s, 0, 1.1);' % (num, _n(t0 + 0.18)))
    if prova:
        ppx, _, _ = kb.caber(prova, p.ft, 880, 100, 76, 48, (1,), 1.2, 0)
        p.texto("s%d_apoio" % num, t0, dur, prova, 90, by + balt + 34, ppx, kb.sobre(c, cor, False, ("bg", "text")))
        p.chama('M.entra("s%d_apoio", 0.7, 0.35, "sobe");' % num)
    p.notas.append("cena %d (oferta): valor %d px" % (num, vpx))
    return (cx - 36 * x["passo"], solo, larg_h - 30), (cx + 36 * x["passo"], solo, larg_h + 30)


def _final(p, t, num, t0, dur, cor, fi, x):
    c, m = p.c, p.m
    titulo, cond = _slot(fi, "titulo", 40, "final.titulo"), _slot(fi, "condicao", 30, "final.condicao", False)
    contato = _slot(fi, "contato", 34, "final.contato")
    _conta("cartão final (titulo + condicao + contato)", kp.limite(dur), titulo, cond, contato)
    icone = kb.canal(fi.get("canal") or "whatsapp")
    kp.campo(p, num, t0, dur, cor)
    px, lin, larg = kb.caber(titulo, p.fh, 860, 400, 230, 120, (1, 2, 3), piso=120)
    y, solo = 290 + len(lin) * px + 30, 1770
    cpx, clarg = (kb.caber(cond, p.ft, 800, 90, 64, 48, (1,), 1.2, 0)[::2] if cond else (0, 0))
    fim = y + (int(cpx * 1.2) + 70 if cond else 0) + 176 + 30 + 100      # where the brand row ends
    larg_h = max(486, min(900, int((solo - fim - 30) / x["alto"])))        # the hero takes what is left, 45% or more
    cx = (1080 - larg_h // 2 + 20) if not x["esq"] else (larg_h // 2 - 20)
    kp.arte(p, num, t0, dur, cor, t, solo, max(fim + 40, solo - int(larg_h * 0.86)), cx, larg_h, x["estrada"],
            x["anda"], canto=True, tx=(70 if not x["esq"] else 700, 1560))
    cor_t = kb.sobre(c, cor, True, ("bg", "text", "primary", "surface"))
    p.texto("s%d_titulo" % num, t0, dur, titulo, 90, 290, px, cor_t, int(larg * 1.04) + 8, True, "l-topo")
    p.chama('M.palavras("s%d_titulo", 0.3, 0.07, "onda");' % num)
    if cond:
        p.regra("s%d_barra" % num, "left: 0; top: %dpx; width: %dpx; height: %dpx; z-index: 2; background: %s; "
                "clip-path: polygon(0 0, 100%% 0, calc(100%% - 30px) 100%%, 0 100%%);"
                % (y, int(clarg) + 160, int(cpx * 1.2) + 36, p.cor("accent")))
        p.clip("s%d_barra" % num, t0, dur)
        p.texto("s%d_apoio" % num, t0, dur, cond, 90, y + 18, cpx, kb.sobre(c, "accent", False, ("text", "primary", "bg")))
        p.chama('M.palavras("s%d_apoio", 1.3, 0.08, "onda");' % num)
        y += int(cpx * 1.2) + 70
    anel, cor_anel = 176, (t["forte"] if kp.claro(cor) else "bg")
    p.regra("s%d_pulso" % num, "left: 90px; top: %dpx; width: %dpx; height: %dpx; z-index: 2; "
            "clip-path: circle(50%% at 50%% 50%%); background: %s;" % (y, anel, anel, p.cor(cor_anel)))
    p.clip("s%d_pulso" % num, t0, dur)
    p.css.append("#s%d_icone .ic { fill: %s; } #s%d_icone .ic2 { fill: %s; }"
                 % (num, p.cor(kb.sobre(c, cor_anel, True, ("bg", "accent", "text"))), num, p.cor(cor_anel)))
    p.regra("s%d_icone" % num, "left: %dpx; top: %dpx; width: 100px; height: 100px;" % (128, y + 38))
    p.clip("s%d_icone" % num, t0, dur, "svg", icone, attrs=' viewBox="0 0 100 100" aria-hidden="true"')
    kpx, klin, klarg = kb.caber(contato, p.fh, 900 - anel - 30, 170, 92, 56, (1, 2), 1.08, 0, piso=76)
    p.texto("s%d_contato" % num, t0, dur, contato, 90 + anel + 30, y + (anel - int(len(klin) * kpx * 1.08)) // 2,
            kpx, cor_t, int(klarg * 1.04) + 8, True, lh=1.08, extra="letter-spacing: 0;")
    # a cursor comes to the contact and presses it: the eye is led to the one thing to do
    kp.toque(p, num, t0, dur, (800, y + anel + 330), (90 + anel - 50, y + anel - 46), t0 + 1.3,
             "accent" if cor != "accent" else t["forte"])
    p.chama('M.palavras("s%d_contato", 1.4, 0.08, "onda");' % num)
    p.chama('M.pulso("s%d_pulso", 0.4, 0.6, 1.28);' % num)
    y += anel + 30
    mx = 90
    if x["logo"]:
        if not kp.claro(cor):
            p.regra("s%d_bloco3" % num, "left: 82px; top: %dpx; width: 116px; height: 116px; z-index: 2; "
                    "clip-path: circle(50%% at 50%% 50%%); background: %s;" % (y - 8, p.cor("bg")))
            p.clip("s%d_bloco3" % num, t0, dur)
        p.regra("s%d_logo" % num, "left: 90px; top: %dpx; width: 100px; height: 100px;" % y)
        p.clip("s%d_logo" % num, t0, dur, "img", attrs=' src="assets/%s" alt=""' % x["logo"])
        mx = 214
    mpx, _, _ = kb.caber(m["nome"], p.fh, 950 - mx, 80, 60, 44, (1,), 1.2, 0)
    p.texto("s%d_marca" % num, t0, dur, m["nome"], mx, y + (100 - int(mpx * 1.2)) // 2, mpx, cor_t, titulo=True,
            lh=1.2, extra="letter-spacing: 0;")
    p.notas.append("cena %d (cartão final): titulo %d px, contato %d px, herói %d%% da largura"
                   % (num, px, kpx, larg_h * 100 // 1080))
    return (cx - 36 * x["passo"], solo, larg_h - 20), (cx + 36 * x["passo"], solo, larg_h + 30)


CENAS = dict(ke.CENAS, gancho=_gancho, rampa=_rampa, lista=_lista, oferta=_oferta, final=_final)


def roteiro(peca, duracao):
    """(style, scene names, scene lengths): the style of `peca.json` decides the second scene."""
    estilo = peca.get("estilo") or "produto-em-destaque"
    if estilo not in ke.ESTILOS:
        raise kb.Erro('estilo "%s" não existe: use um de %s' % (estilo, ", ".join(sorted(ke.ESTILOS))))
    meio = ke.ESTILOS[estilo]
    if meio is None:
        return estilo, ["gancho", "rampa"] + (["lista"] if duracao == 15 else []) + ["oferta", "final"], TEMPOS[duracao]
    return estilo, ["gancho", meio] + (["rampa"] if duracao == 15 else []) + ["oferta", "final"], TEMPOS_ESTILO[duracao]


def montar(m, peca, heroi, destino, duracao=10, logo=None, foto=None):
    """The whole reel. Returns (html, notes)."""
    c = m["cores"]
    t = kp.tema(m, peca)
    p = kp.Peca(m)
    estilo, nomes, tempos = roteiro(peca, duracao)
    for nome in nomes:
        t["campos"].setdefault(nome, t["campos"]["rampa"])
    inicios = [sum(tempos[:i]) for i in range(len(tempos))]
    anda = peca.get("heroi_anda") if peca.get("heroi_anda") in ("direita", "esquerda") else "parado"
    x = {"esq": t["lado"] == "esquerda", "anda": anda, "passo": {"direita": 1, "esquerda": -1}.get(anda, 0),
         "estrada": peca.get("chao") == "estrada", "logo": logo, "alto": kb.alto_heroi(peca), "foto": bool(foto),
         "alto_antes": kb.alto_heroi(peca, "heroi_topo_antes"),
         "payoff": None}
    quadros, t_payoff = [], 0.0
    for num, (nome, t0, dur) in enumerate(zip(nomes, inicios, tempos), 1):
        d = peca.get(nome) if isinstance(peca.get(nome), dict) else {}
        ini, fim = CENAS[nome](p, t, num, t0, dur, t["campos"][nome], d, x)
        quadros.append((t0, t0 + dur, ini, fim))
        if nome == "oferta":
            t_payoff = x["payoff"] or t0 + 0.4   # done by the middle of the scene; a style may play it earlier
    kp.transicoes(p, t, nomes, inicios)
    kp.heroi(p, heroi, foto, quadros, float(duracao), anda, t_payoff)
    with open(MOTOR, encoding="utf-8") as f:
        motor = f.read().rstrip("\n")
    p.notas.append("estilo %s, tema %s, herói à %s, palco %s, textura %s, transições %s"
                   % (estilo, t["tema"], t["lado"], t["palco"], t["textura"], " > ".join(t["tr"][:len(inicios) - 1])))
    return PAGINA % ("\n    ".join(m["linhas_fonte"]), c["bg"], c["bg"], c["surface"], c["primary"], c["text"],
                     c["accent"], kb.HEROI_CSS, "\n    ".join(p.css), duracao, estilo, "\n    ".join(p.clips), motor,
                     "\n    ".join(p.js)), p.notas
