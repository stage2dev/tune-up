"""Brand fonts -> the two @font-face lines of a post frame, picked by rule, not by the model.

Reads fontes.heading and fontes.body from the approved marca.json of the project that holds the
working folder (path cut right before /.tune-up/) and prints, ready to paste in <style>:
  @font-face { font-family: "Brand Heading"; src: local("..."), ...; }
  @font-face { font-family: "Brand Body"; src: local("..."), ...; }
and one CSS comment per field that names a generic family (system-ui, sans-serif, ...).
Named families stay first, in the brand order. A generic family cannot go in local(), so it
becomes a fixed stack of fonts common on macOS and Linux; the frame still loads a real font.
A field with only named fonts gets no stack: a missing font stays a snapshot failure.
Usage: python3 -I fontes.py [--trabalho DIR]   (default: current folder). Exit 2: no marca.json.
Python 3.9+, standard library only.
"""
import json
import os
import re
import sys

SANS = ["Helvetica Neue", "Arial", "Liberation Sans", "DejaVu Sans"]
SERIF = ["Georgia", "Times New Roman", "Liberation Serif", "DejaVu Serif"]
MONO = ["Menlo", "Courier New", "Liberation Mono", "DejaVu Sans Mono"]
GENERICAS = {
    "system-ui": SANS, "ui-sans-serif": SANS, "sans-serif": SANS, "-apple-system": SANS,
    "blinkmacsystemfont": SANS, "ui-rounded": SANS, "cursive": SANS, "fantasy": SANS,
    "emoji": SANS, "math": SANS, "serif": SERIF, "ui-serif": SERIF, "fangsong": SERIF,
    "monospace": MONO, "ui-monospace": MONO,
}
NEUTRA = "system-ui, sans-serif"  # neutral font of MARCA.md for a missing field
NOME = re.compile(r"^\w[\w .&'+-]*$")


def pilha(valor):
    """CSS font-family text -> (local names in order, generic names found, named count)."""
    nomes, genericas, extra = [], [], []
    for parte in str(valor or "").split(","):
        nome = parte.strip().strip("\"'").strip()
        if not nome:
            continue
        if nome.lower() in GENERICAS:
            genericas.append(nome)
            extra += [n for n in GENERICAS[nome.lower()] if n not in extra]
        elif NOME.match(nome) and nome not in nomes:
            nomes.append(nome)
    return nomes + [n for n in extra if n not in nomes], genericas, len(nomes)


def linhas(heading, body):
    """Field values -> the lines to paste (two @font-face, then the generic notes)."""
    out, notas = [], []
    for campo, familia, valor in (("heading", "Brand Heading", heading), ("body", "Brand Body", body)):
        valor = valor if valor else NEUTRA
        nomes, genericas, marcados = pilha(valor)
        if not nomes:  # nothing usable: same as a missing field
            nomes, genericas, marcados = pilha(NEUTRA)
        src = ", ".join('local("%s")' % n for n in nomes)
        out.append('@font-face { font-family: "%s"; src: %s; }' % (familia, src))
        if genericas:
            tipo = "com generica" if marcados else "so generica"
            notas.append("/* fonte da marca %s: %s (%s), pilha local fixa */" % (campo, tipo, ", ".join(genericas)))
    return out + notas


def marca_de(trabalho):
    corte = trabalho.find("/.tune-up/")
    if corte < 0:
        raise ValueError("pasta de trabalho fora de um /.tune-up/: " + trabalho)
    with open(os.path.join(trabalho[:corte], ".tune-up", "estudio", "marca", "marca.json"), encoding="utf-8") as f:
        campos = json.load(f)["campos"]

    def valor(k):
        c = campos.get(k)
        return c.get("valor") if isinstance(c, dict) else None
    return valor("fontes.heading"), valor("fontes.body")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    trabalho = os.getcwd()
    if args[:1] == ["--trabalho"] and len(args) == 2:
        trabalho = os.path.abspath(args[1])
    elif args:
        print("uso: fontes.py [--trabalho DIR]", file=sys.stderr)
        return 2
    try:
        heading, body = marca_de(trabalho)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print("marca.json ilegivel: %s" % e, file=sys.stderr)
        return 2
    print("\n".join(linhas(heading, body)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
