"""tune-up: `guarda.py review-save` and `review-pending` (reviewer findings on disk; refuse ship).

Both always print one JSON line. Any doubt is "the lens did not run" / "a review is pending"; a wrong
review-save call (argument, folder, file name) is `usage`: it says nothing about the answer.
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
CAMPOS = ("sev", "file", "line", "introduced", "proof", "title")
# the only approved forms (agents/reviewer-*.md: `APPROVED | APPROVED WITH FIXES`, then the counts)
RE_APPROVED = re.compile(
    r"[\s*_`>\"']*(?:approved?(?:\s+with\s+(?:fixes|notes|comments|nits|suggestions))?"
    r"|aprovad[oa](?:\s+com\s+(?:correcoes|ressalvas|notas|ajustes))?)(?![^\W_])"
    r"(?:\d|(?:critical|high|medium|low|pre-?existing|pre-?existentes?|and|e)(?!\w)|[\s*_`\"',;:.()–—-])*")
RE_FENCE = re.compile(r"^[ \t>]*```(.*)$", re.M)
RE_VERDICT = re.compile(r"^[ \t>*_`#-]*verdict[ \t*_`]*:(.*)$", re.M | re.I)
RE_COUNT = re.compile(r"(?<!\d)(\d{1,6})[ *_`]*(critical|high)\b|\b(critical|high)[ *_`]*[:=][ *_`]*(\d{1,6})", re.I)
RE_LEAD = re.compile(r"^(?:[\s>*_#+•–—-]|\[ \]|\d+[.)])*")
PART = r"[^\W_]+(?:\.[^\W_]+)*"
RE_PARTS = re.compile(r"(?<![^\W_])part(?:e|s|es)?(?![^\W_])")
# only a label that stands alone ("Part A - since ...") can be left out; "Part A, B" always counts
RE_LABEL = re.compile(r"[\s*_:–—-]*parte?\s+(%s)[*_]*(?=$|\s+[–—-]+\s|\s+(?:since|desde)\b)" % PART)


class Invalid(Exception):
    """Refusal whose text is safe to print (never carries the content)."""


class Usage(Invalid):
    """The call is wrong, not the reviewer's answer."""


def ler_args(argv, obrigatorios, opcionais=()):
    out = {}
    for i in range(0, len(argv), 2):
        nome = argv[i][2:]
        if argv[i][:2] != "--" or nome not in obrigatorios + opcionais or nome in out:
            raise Usage("unknown or repeated argument")
        if i + 1 >= len(argv) or not argv[i + 1].strip() or argv[i + 1].startswith("--"):
            raise Usage("argument without a value")
        out[nome] = argv[i + 1]
    if any(n not in out for n in obrigatorios):
        raise Usage("missing argument")
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
    """(json, the text after it or None): bare json, or the LAST json-looking block, whose text goes
    from a ```json line (or one followed by `"findings"`) to the next fence line, that must close it.
    Never an earlier block: it can be quoted."""
    d = _objeto(texto)
    if d is not None:
        return d, None
    cercas = list(RE_FENCE.finditer(texto))
    for a, b in reversed(list(zip(cercas, cercas[1:] + [None]))):
        miolo = texto[a.end():b.start() if b else len(texto)]
        if a.group(1).strip().lower().startswith("json") or '"findings"' in miolo.lower():
            d = _objeto(miolo) if b and not b.group(1).strip() else None
            if d is not None:
                return d, texto[b.end():]
            break
    raise Invalid("no json with verdict and findings in the last block")


def aprovado(veredito):
    return bool(RE_APPROVED.fullmatch(dobra(veredito)))


def conferir(d, resto):
    """The `Verdict:` lines after the block say what the json says. A count may leave out the
    pre-existing findings."""
    linhas = RE_VERDICT.findall(resto)
    if not linhas:
        raise Invalid("no Verdict line after the json")
    for linha in linhas:
        if aprovado(linha) != aprovado(d["verdict"]):
            raise Invalid("the Verdict line and the json verdict differ")
        for n1, s1, s2, n2 in RE_COUNT.findall(linha):
            graves = [f["introduced"] for f in d["findings"] if f["sev"] == (s1 or s2).upper()]
            if int(n1 or n2) not in (len(graves), sum(graves)):
                raise Invalid("the Verdict line and the json count different findings")


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
    existe = "file already exists for this lens, chunk and round: use the next --round"
    # shortcut: Windows has no O_NOFOLLOW and O_EXCL follows a dangling link there; a link planted between
    # this check and the open still passes on Windows, use CreateFileW with FILE_FLAG_OPEN_REPARSE_POINT then
    if os.path.lexists(caminho):
        raise Usage(existe)
    try:
        fd = os.open(caminho, flags, 0o600)
    except FileExistsError:
        raise Usage(existe)
    except OSError as e:
        raise Usage("cannot write in dir (%s)" % type(e).__name__)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(dados)
    except BaseException:
        os.remove(caminho)
        raise


def ler_resposta(arquivo):
    if arquivo is None:
        bruto = sys.stdin.buffer.read(MAX_BYTES + 1)
    else:
        if not os.path.isabs(arquivo) or not os.path.isfile(arquivo):
            raise Usage("answer file is not an existing absolute regular file")
        try:
            with open(arquivo, "rb") as f:
                bruto = f.read(MAX_BYTES + 1)
        except OSError as e:
            raise Usage("answer file unreadable (%s)" % type(e).__name__)
    if len(bruto) > MAX_BYTES:
        raise Invalid("input too large")
    return bruto


def salvar(argv):
    a = ler_args(argv, ("dir", "lens", "chunk", "round"), ("answer-file",))
    a["chunk"] = re.sub(r"[._]", "-", a["chunk"].lower())  # goal ids: B1, 0.1
    if not os.path.isabs(a["dir"]) or not os.path.isdir(a["dir"]):
        raise Usage("dir is not an existing absolute directory")
    if a["lens"] not in LENSES:
        raise Usage("unknown lens")
    if not re.fullmatch(r"[a-z0-9-]{1,30}", a["chunk"]):
        raise Usage("bad chunk label")
    if not re.fullmatch(r"[1-9]", a["round"]):
        raise Usage("bad round")
    bruto = ler_resposta(a.get("answer-file"))
    try:
        d, resto = extrair(bruto.decode("utf-8-sig"))
        validar(d)
        if resto is not None:
            conferir(d, resto)
        d = {"verdict": d["verdict"], "findings": [{k: f[k] for k in CAMPOS} for f in d["findings"]],
             "lens": a["lens"], "chunk": a["chunk"], "round": int(a["round"])}
        dados = (json.dumps(d, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    except UnicodeError:
        raise Invalid("input is not UTF-8")
    caminho = os.path.join(a["dir"], "review-part-%s-%s-%s.json" % (a["lens"], a["chunk"], a["round"]))
    gravar(caminho, dados)
    achados = d["findings"]
    return {"ok": True, "lens_ran": True, "path": caminho,
            "counts": {s: sum(f["sev"] == s for f in achados) for s in SEVS},
            "blocking": sum(f["introduced"] and f["sev"] in SEVS[:2] for f in achados),
            "rejected": not aprovado(d["verdict"])}


# ---------------------------------------------------------------- review-pending

def dobra(texto):
    """Accents, case and repeated spaces do not matter when matching a marker."""
    s = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s.casefold())


def marcadores():
    with open(os.path.join(os.path.dirname(AQUI), "templates", "names.json"), encoding="utf-8") as f:
        todos = [nomes.get("review_pending") for nomes in json.load(f).values()]
    todos.append(ler_usuario()[0]["names_override"].get("review_pending"))  # what `info` hands the skill
    dobrados = [dobra(m.strip()) for m in todos + list(MARKERS) if _cheio(m)]
    return {RE_LEAD.sub("", m) or m for m in dobrados}


def linhas_pendentes(texto, part, marcas):
    """Lines with a marker anywhere. Left out: one whose every marker has the label of another Part
    right after it, when that label is the only one on the line."""
    out = []
    for linha in texto.splitlines():
        s = dobra(linha)
        rotulos = [RE_LABEL.match(s, o.end()) for m in marcas for o in re.finditer(re.escape(m), s)]
        outra = part and len(RE_PARTS.findall(s)) == 1 and all(r and r.group(1) != part for r in rotulos)
        if rotulos and not outra:
            out.append(linha.strip()[:200])
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
    if not texto.strip():
        raise Invalid("progress file is empty")
    linhas = linhas_pendentes(texto, part, marcadores())
    return {"pending": bool(linhas), "lines": linhas}


def revisao_erro(evento, texto, uso=False):
    if evento == "review-save" and uso:
        return {"ok": False, "usage": True, "lens_ran": None, "error": texto}
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
        saida = revisao_erro(evento, str(e), isinstance(e, Usage))
    except Exception as e:
        log_erro(evento, "%s: %s" % (type(e).__name__, e))
        saida = revisao_erro(evento, "error (%s)" % type(e).__name__)
    print(json.dumps(saida))
