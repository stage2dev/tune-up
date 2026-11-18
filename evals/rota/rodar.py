#!/usr/bin/env python3
"""tune-up: eval of the optional model router against evals/rota/casos.json.

Default mode: outside CI, costs one API call per case (to the Jev scorer, TypeSafe) and sends
only the case text, written to a `caso.rota.txt` file (the router reads no other name;
masked, cut to max_chars). It calls the router code (scripts/tuneup/rota.py)
with the router enabled in an in-memory config; the router reads the key, this script never does.
Prints accuracy, a 2x2 matrix (expected x got) and the `risk: true` cases that came out below
opus. Exit 1 when accuracy < 0.85, any risk case is below opus, or the scorer answered no case.

--seco: no network, no key. Validates the case file and runs every case through the FIXED rule
only (the globs); prints how many the globs alone get right. Exit 0 when the file is valid.
"""
import json
import os
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)), "scripts"))
from tuneup import rota  # noqa: E402

CASOS = os.path.join(AQUI, "casos.json")
CHAVES = {"id", "text", "files", "expect", "risk"}
MIN_CASOS, MIN_RISCO, MIN_ACERTO = 30, 12, 0.85
CFG_ROUTER = {"router": {"enabled": True, "max_chars": 6000,
                         "thresholds": {"mechanical": 0.6, "risk": 0.5, "hard": 0.6, "visual": 0.5}}}


def validar(casos):
    """List of problems; empty when the file is valid."""
    if not isinstance(casos, list):
        return ["top level is not a list"]
    erros, ids = [], set()
    for i, c in enumerate(casos):
        nome = "case %d" % i
        if not isinstance(c, dict) or set(c) != CHAVES:
            erros.append("%s: keys must be exactly %s" % (nome, sorted(CHAVES)))
            continue
        if not isinstance(c["id"], str) or not c["id"].strip():
            erros.append("%s: id must be a non-empty string" % nome)
        elif c["id"] in ids:
            erros.append("%s: duplicate id %s" % (nome, c["id"]))
        else:
            ids.add(c["id"])
        if not isinstance(c["text"], str) or not c["text"].strip():
            erros.append("%s: text must be a non-empty string" % nome)
        f = c["files"]
        if not isinstance(f, list) or not f or not all(isinstance(x, str) and x.strip() for x in f):
            erros.append("%s: files must be a non-empty list of strings" % nome)
        if c["expect"] not in ("sonnet", "opus"):
            erros.append("%s: expect must be sonnet or opus" % nome)
        if not isinstance(c["risk"], bool):
            erros.append("%s: risk must be true or false" % nome)
        elif c["risk"] and c["expect"] != "opus":
            erros.append("%s: a risk case must expect opus" % nome)
    if len(casos) < MIN_CASOS:
        erros.append("need at least %d cases, got %d" % (MIN_CASOS, len(casos)))
    n = sum(1 for c in casos if isinstance(c, dict) and c.get("risk") is True)
    if n < MIN_RISCO:
        erros.append("need at least %d risk cases, got %d" % (MIN_RISCO, n))
    return erros


def carregar():
    with open(CASOS, encoding="utf-8") as f:
        return json.load(f)


def rodar_caso(caso, cfg, texto_arq):
    return rota.rota(caso["files"], None, None, cfg, os.getcwd(), texto_arq)


def seco(casos):
    certos = sum(1 for c in casos if rota.rota(c["files"], None, None, {}, os.getcwd())["model"] == c["expect"])
    print("dry run: %d cases (%d risk), valid. Fixed rule (globs only) right on %d of %d."
          % (len(casos), sum(c["risk"] for c in casos), certos, len(casos)))


def real(casos):
    matriz = {(e, g): 0 for e in ("sonnet", "opus") for g in ("sonnet", "opus", "other")}
    certos = com_jev = 0
    baixos = []
    with tempfile.TemporaryDirectory() as pasta:
        for c in casos:
            arq = os.path.join(pasta, "caso.rota.txt")
            with open(arq, "w", encoding="utf-8") as f:
                f.write(c["text"])
            r = rodar_caso(c, CFG_ROUTER, arq)
            got = r["model"] if r["model"] in ("sonnet", "opus") else "other"
            matriz[(c["expect"], got)] += 1
            certos += got == c["expect"]
            com_jev += r["source"] == "jev"
            if c["risk"] and got != "opus":
                baixos.append(c["id"])
    acc = certos / len(casos)
    print("accuracy %.2f (%d of %d); scorer answered %d cases" % (acc, certos, len(casos), com_jev))
    print("expected\\got   sonnet  opus  other")
    for e in ("sonnet", "opus"):
        print("%-13s %6d %5d %6d" % (e, matriz[(e, "sonnet")], matriz[(e, "opus")], matriz[(e, "other")]))
    print("risk cases below opus: %s" % (", ".join(baixos) or "none"))
    if com_jev == 0:
        print("the scorer answered no case (key missing or service error): not a valid run")
    return 0 if acc >= MIN_ACERTO and not baixos and com_jev else 1


def main(argv):
    try:
        casos = carregar()
    except (OSError, ValueError) as e:
        print("cannot read casos.json: %s" % type(e).__name__)
        return 1
    erros = validar(casos)
    if erros:
        print("\n".join(erros))
        return 1
    if "--seco" in argv:
        seco(casos)
        return 0
    return real(casos)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
