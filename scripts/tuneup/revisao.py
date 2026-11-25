"""tune-up: `guarda.py review-save` and `review-pending` (reviewer findings on disk; refuse ship).

Both always print one JSON line. Any doubt is "the lens did not run" / "a review is pending".
"""
import json
import os
import re
import sys
import unicodedata

from .config import AQUI, TESTE
from .sessao import log_erro
from .usuario import ler_usuario

MAX_BYTES = 1024 * 1024
LENSES = ("failures", "security", "database")
SEVS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
PROOFS = ("observed", "read", "suspected")
MARKERS = ("REVIEW PENDING", "REVISÃO PENDENTE")  # names.json without the key
# same rule as `rejects` in templates/workflow-template.js
RE_REJECTED = re.compile(r"^\s*reject|changes|rework", re.I)
RE_FENCE = re.compile(r"^[ \t>]*```.*$", re.M)
RE_LEAD = re.compile(r"^(?:[\s>*_#+•–—-]|\[ \]|\d+[.)])*")
PART = r"[^\W_]+(?:\.[^\W_]+)*"
# only a label that stands alone ("Part A - since ...") can be left out; "Part A, B" always counts
RE_LABEL = re.compile(r"[\s*_:–—-]*parte?\s+(%s)[*_]*(?=$|\s+[–—-]+\s|\s+(?:since|desde)\b)" % PART)


class Invalid(Exception):
    """Refusal whose text is safe to print (never carries the content)."""


def ler_args(argv, obrigatorios, opcionais=()):
    out = {}
    for i in range(0, len(argv), 2):
        nome = argv[i][2:]
        if argv[i][:2] != "--" or nome not in obrigatorios + opcionais or nome in out:
            raise Invalid("unknown or repeated argument")
        if i + 1 >= len(argv) or not argv[i + 1].strip() or argv[i + 1].startswith("--"):
            raise Invalid("argument without a value")
        out[nome] = argv[i + 1]
    if any(n not in out for n in obrigatorios):
        raise Invalid("missing argument")
    return out


# ---------------------------------------------------------------- review-save

def _objeto(texto):
    """Dict with `verdict` and `findings`, or None."""
    def constante(_nome):
        raise ValueError("NaN/Infinity is not JSON")
    try:
        d = json.loads(texto, parse_constant=constante)
    except (ValueError, RecursionError):
        return None
    return d if isinstance(d, dict) and "verdict" in d and "findings" in d else None


def extrair(texto):
    """Bare json, or the last fenced block that parses. Every pair of neighbor fence lines is tried,
    so an unbalanced fence earlier in the answer does not hide the block."""
    d = _objeto(texto)
    if d is not None:
        return d
    cercas = list(RE_FENCE.finditer(texto))
    for a, b in reversed(list(zip(cercas, cercas[1:]))):
        d = _objeto(texto[a.end():b.start()])
        if d is not None:
            return d
    raise Invalid("no json with verdict and findings")


def _cheio(v):
    return isinstance(v, str) and bool(v.strip())


def validar(d):
    """Validates in place: `sev` upper-cased, missing `introduced` = true (counts as blocking)."""
    if not _cheio(d["verdict"]):
        raise Invalid("verdict is not a non-empty string")
    if not isinstance(d["findings"], list):
        raise Invalid("findings is not a list")
    for n, f in enumerate(d["findings"]):
        if not isinstance(f, dict):
            raise Invalid("finding %d is not an object" % n)
        f.setdefault("introduced", True)
        linha = f.get("line", "")
        ok = {"sev": isinstance(f.get("sev"), str) and f["sev"].upper() in SEVS,
              "file": _cheio(f.get("file")),
              "line": linha is None or (isinstance(linha, int) and not isinstance(linha, bool)),
              "introduced": isinstance(f["introduced"], bool),
              "proof": isinstance(f.get("proof"), str) and f["proof"] in PROOFS,
              "title": _cheio(f.get("title"))}
        ruins = [k for k in ok if not ok[k]]
        if ruins:
            raise Invalid("finding %d: bad %s" % (n, ", ".join(ruins)))
        f["sev"] = f["sev"].upper()
    return d


def gravar(caminho, dados):
    """Exclusive create (never overwrites or follows a link), 0600; nothing left behind on error."""
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL
             | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
    try:
        fd = os.open(caminho, flags, 0o600)
    except FileExistsError:
        raise Invalid("file already exists for this lens, chunk and round")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
    except BaseException:
        os.remove(caminho)
        raise


def salvar(argv):
    a = ler_args(argv, ("dir", "lens", "chunk", "round"))
    if not os.path.isabs(a["dir"]) or not os.path.isdir(a["dir"]):
        raise Invalid("dir is not an existing absolute directory")
    if a["lens"] not in LENSES:
        raise Invalid("unknown lens")
    if not re.fullmatch(r"[a-z0-9-]{1,30}", a["chunk"]):
        raise Invalid("bad chunk label")
    if not re.fullmatch(r"[1-9]", a["round"]):
        raise Invalid("bad round")
    bruto = sys.stdin.buffer.read(MAX_BYTES + 1)
    if len(bruto) > MAX_BYTES:
        raise Invalid("input too large")
    try:
        d = validar(extrair(bruto.decode("utf-8-sig")))
        d.update(lens=a["lens"], chunk=a["chunk"], round=int(a["round"]))
        dados = (json.dumps(d, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    except UnicodeError:
        raise Invalid("input is not UTF-8")
    caminho = os.path.join(a["dir"], "review-part-%s-%s-%s.json" % (a["lens"], a["chunk"], a["round"]))
    gravar(caminho, dados)
    achados = d["findings"]
    return {"ok": True, "lens_ran": True, "path": caminho,
            "counts": {s: sum(f["sev"] == s for f in achados) for s in SEVS},
            "blocking": sum(f["introduced"] and f["sev"] in SEVS[:2] for f in achados),
            "rejected": bool(RE_REJECTED.search(d["verdict"]))}


# ---------------------------------------------------------------- review-pending

def dobra(texto):
    """Accents, case and repeated spaces do not matter when matching a marker."""
    s = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold())


def marcadores():
    with open(os.path.join(os.path.dirname(AQUI), "templates", "names.json"), encoding="utf-8") as f:
        todos = [nomes.get("review_pending") for nomes in json.load(f).values()]
    todos.append(ler_usuario()[0]["names_override"].get("review_pending"))  # what `info` hands the skill
    return {dobra(m.strip()) for m in todos + list(MARKERS) if _cheio(m)}


def linhas_pendentes(texto, part, marcas):
    out = []
    for linha in texto.splitlines():
        s = RE_LEAD.sub("", dobra(linha))
        for m in marcas:
            if s.startswith(m):
                rotulo = RE_LABEL.match(s[len(m):])
                if not (part and rotulo and rotulo.group(1) != part):
                    out.append(linha.strip()[:200])
                break
    return out


def pendente(argv):
    a = ler_args(argv, ("file",), ("part",))
    part = None
    if "part" in a:
        part = re.sub(r"^parte?\s+", "", dobra(a["part"].strip()))
        if not re.fullmatch(r"[^\W_]+(?:[.-][^\W_]+)*", part):
            raise Invalid("bad part")
    if not os.path.isfile(a["file"]):
        raise Invalid("progress file not found")
    with open(a["file"], "rb") as f:
        texto = f.read().decode("utf-8-sig")
    if "\0" in texto:  # UTF-16 without a BOM would hide the marker
        raise Invalid("progress file is not UTF-8 text")
    linhas = linhas_pendentes(texto, part, marcadores())
    return {"pending": bool(linhas), "lines": linhas}


def revisao_erro(evento, texto):
    if evento == "review-save":
        return {"ok": False, "lens_ran": False, "error": texto}
    return {"pending": True, "lines": [], "error": texto}


def roda_revisao(evento, argv):
    """Always prints one JSON line; any error is fail-closed."""
    try:
        if TESTE and os.environ.get("TUNEUP_FAKE_EXCECAO") == "1":
            raise RuntimeError("simulated exception")
        saida = salvar(argv) if evento == "review-save" else pendente(argv)
    except Invalid as e:
        saida = revisao_erro(evento, str(e))
    except Exception as e:
        log_erro(evento, "%s: %s" % (type(e).__name__, e))
        saida = revisao_erro(evento, "error (%s)" % type(e).__name__)
    print(json.dumps(saida))
