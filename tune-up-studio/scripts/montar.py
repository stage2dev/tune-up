#!/usr/bin/env python3
"""Assemble a finished composition from the kit: the session writes the texts (`peca.json`) and one drawing
(`heroi.svg`); this script writes `<out>/index.html` with the brand, the layout, the type fitted to its box
and, for a reel, the motion script (the studio engine pasted whole plus the scene calls).

  python3 -I montar.py --tipo post  --peca peca.json --heroi heroi.svg --out q1/fonte [--formato 4:5|1:1]
                       [--quadro unico|capa|ponto|fecho]
  python3 -I montar.py --tipo video --peca peca.json --heroi heroi.svg --out fonte [--duracao 10|15]

Run from the working folder (inside <project>/.tune-up/): the brand comes from the approved marca.json, the
logo is copied to <out>/assets, a photo is used when fotos.py already copied `foto1.*` there and `peca.json`
says `"heroi": "foto"`. Prints one note per line (sizes it chose); exit 1 with the reason when an input is
missing or too long. Never touches the network. Python 3.9+, standard library only.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kit_base as kb  # noqa: E402
import kit_post  # noqa: E402
import kit_video  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--tipo", required=True, choices=("post", "video"))
    ap.add_argument("--peca", required=True)
    ap.add_argument("--heroi", default="heroi.svg")
    ap.add_argument("--out", required=True)
    ap.add_argument("--formato", default="4:5", choices=("4:5", "1:1"))
    ap.add_argument("--quadro", default="unico", choices=kit_post.QUADROS)
    ap.add_argument("--duracao", type=int, default=10, choices=(10, 15))
    ap.add_argument("--trabalho", default=None)
    args = ap.parse_args(argv)
    trabalho = os.path.abspath(args.trabalho or os.getcwd())
    try:
        m = kb.marca(trabalho)
        peca = kb.ler_json(args.peca)
        destino = os.path.realpath(args.out)
        if os.path.commonpath([destino, os.path.realpath(trabalho)]) != os.path.realpath(trabalho):
            raise kb.Erro("--out fora da pasta de trabalho: %s" % args.out)
        for nome in (args.peca, args.heroi):
            if os.path.isfile(nome) and os.path.getsize(nome) > 200000:
                raise kb.Erro("%s grande demais (máximo 200 kB)" % os.path.basename(nome))
        os.makedirs(destino, exist_ok=True)
        logo = kb.copiar_logo(m, destino)
        foto = kb.foto(destino) if peca.get("heroi") == "foto" else None
        if peca.get("heroi") == "foto" and not foto:
            raise kb.Erro('"heroi": "foto" mas não há assets/foto1.* em %s: rode fotos.py antes ou desenhe o '
                          'heroi.svg' % args.out)
        heroi = None if foto else kb.heroi(args.heroi)
        if args.tipo == "post":
            html, notas = kit_post.montar(m, peca, heroi, destino, 1350 if args.formato == "4:5" else 1080,
                                          args.quadro, logo, foto)
        else:
            html, notas = kit_video.montar(m, peca, heroi, destino, args.duracao, logo, foto)
    except kb.Erro as e:
        print("montar: %s" % e, file=sys.stderr)
        return 1
    with open(os.path.join(destino, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("\n".join(notas + ["escrito: %s" % os.path.join(args.out, "index.html")]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
