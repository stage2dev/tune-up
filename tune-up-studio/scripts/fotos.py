"""Business photos (and a raster logo) -> <working folder>/<para>/assets/, copied by rule, not by the model.

The session never reads image bytes and never names a source path: this script reads the approved
marca.json of the project that holds the working folder (path cut right before /.tune-up/), takes the
`fotos` list in its order (the first is the main photo) and copies at most --quantas of them as
assets/foto1.<ext>, assets/foto2.<ext>. With --logo it also copies a PNG/JPEG/WebP logo copy
(`logo_copia`, assets/logo.<ext> of the brand folder) as assets/logo.<ext>; an SVG logo stays a Read.
A photo is copied only when its name is the one the panel gave it (16 hex of its sha256 + type) and
the bytes still match that name and type. Prints one line per copied file: `assets/<name> <role>`.
Usage: python3 -I fotos.py --trabalho DIR --para REL [--quantas 0-2] [--logo]
Exit 0 = done (maybe nothing to copy), 2 = bad arguments or unreadable marca.json.
Python 3.9+, standard library only.
"""
import argparse
import hashlib
import json
import os
import re
import sys

ENVIADO = re.compile(r"^fotos/([0-9a-f]{16})\.(png|jpg|webp)\Z")
LOGO = re.compile(r"^assets/logo\.(png|jpg|jpeg|webp)\Z")
PARA = re.compile(r"^[A-Za-z0-9_.]+(?:/[A-Za-z0-9_.]+)*\Z")
ASSINATURA = {"png": b"\x89PNG\r\n\x1a\n", "jpg": b"\xff\xd8\xff", "jpeg": b"\xff\xd8\xff", "webp": b"RIFF"}
MAX_BYTES = 8 * 1024 * 1024
MAX_FOTOS = 2


def pasta_da_marca(trabalho):
    t = trabalho.replace(os.sep, "/")
    corte = t.find("/.tune-up/")
    if corte < 0:
        raise ValueError("pasta de trabalho fora de um /.tune-up/: " + trabalho)
    return os.path.join(trabalho[:corte], ".tune-up", "estudio", "marca")


def ler_bytes(caminho, ext):
    """Bytes of a plain file (never a link) of the given type, or None."""
    try:
        if os.path.islink(caminho) or not os.path.isfile(caminho) or os.path.getsize(caminho) > MAX_BYTES:
            return None
        with open(caminho, "rb") as f:
            dados = f.read(MAX_BYTES + 1)
    except OSError:
        return None
    ok = dados.startswith(ASSINATURA[ext]) and (ext != "webp" or dados[8:12] == b"WEBP")
    return dados if ok and len(dados) <= MAX_BYTES else None


def escolher(marca, base, quantas, logo):
    """[(source bytes, target name, role)] from marca.json, main photo first."""
    out = []
    for f in (marca.get("fotos") or [])[:8]:
        m = ENVIADO.match(f.get("arquivo") or "") if isinstance(f, dict) else None
        if not m or len([o for o in out if o[2] != "logo"]) >= quantas:
            continue
        dados = ler_bytes(os.path.join(base, "fotos", m.group(1) + "." + m.group(2)), m.group(2))
        if dados is None or hashlib.sha256(dados).hexdigest()[:16] != m.group(1):
            continue
        n = len(out) + 1
        out.append((dados, "foto%d.%s" % (n, m.group(2)), "principal" if n == 1 else "foto"))
    copia = marca.get("logo_copia")
    m = LOGO.match(copia) if logo and isinstance(copia, str) else None
    dados = ler_bytes(os.path.join(base, "assets", "logo." + m.group(1)), m.group(1)) if m else None
    if dados is not None:
        out.append((dados, "logo." + m.group(1), "logo"))
    return out


def destino(trabalho, para):
    """<trabalho>/<para>/assets, created piece by piece, never through a link; or ValueError."""
    if not PARA.match(para) or ".." in para.split("/"):
        raise ValueError("--para precisa ser um caminho relativo simples (letras, numeros, _ . /)")
    atual = trabalho
    for parte in para.split("/") + ["assets"]:
        atual = os.path.join(atual, parte)
        if os.path.islink(atual) or (os.path.exists(atual) and not os.path.isdir(atual)):
            raise ValueError("%s nao e uma pasta comum" % parte)
        if not os.path.isdir(atual):
            os.mkdir(atual)
    return atual


def gravar(pasta, nome, dados):
    caminho = os.path.join(pasta, nome)
    if os.path.islink(caminho) or os.path.isdir(caminho):
        raise ValueError("%s ja existe e nao e um arquivo comum" % nome)
    if os.path.exists(caminho):
        os.remove(caminho)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(caminho, flags, 0o644)
    with os.fdopen(fd, "wb") as f:
        f.write(dados)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--trabalho", required=True, help="absolute working folder")
    p.add_argument("--para", required=True, help="composition folder inside it, e.g. q1/fonte")
    p.add_argument("--quantas", type=int, default=MAX_FOTOS, choices=range(0, MAX_FOTOS + 1))
    p.add_argument("--logo", action="store_true", help="also copy a PNG/JPEG/WebP logo")
    args = p.parse_args(argv)
    trabalho = os.path.abspath(args.trabalho)
    try:
        base = pasta_da_marca(trabalho)
        with open(os.path.join(base, "marca.json"), encoding="utf-8") as f:
            marca = json.load(f)
        if not isinstance(marca, dict):
            raise ValueError("marca.json nao e um objeto")
        escolhidos = escolher(marca, base, args.quantas, args.logo)
        pasta = destino(trabalho, args.para) if escolhidos else None
        for dados, nome, papel in escolhidos:
            gravar(pasta, nome, dados)
            print("assets/%s %s" % (nome, papel))
    except (OSError, ValueError) as e:
        print("fotos: %s" % e, file=sys.stderr)
        return 2
    if not escolhidos:
        print("sem fotos nem logo para copiar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
