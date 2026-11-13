"""tune-up: generic agent() calls (no explicit agentType) in a Workflow script."""
import bisect
import re

# Comments and string literals: the tokens of //[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|"(?:\\.|[^"\\\n])*"|
# `(?:\\.|[^`\\])*` (re.S), found in linear time: an unclosed quote or /* is remembered, never rescanned.
RE_WF_INICIO = re.compile(r"//|/\*|['\"`]")
RE_WF_CORPO = {"'": re.compile(r"'(?:\\.|[^'\\\n])*", re.S), '"': re.compile(r"\"(?:\\.|[^\"\\\n])*", re.S),
               "`": re.compile(r"`(?:\\.|[^`\\])*", re.S)}
RE_WF_SINAL = re.compile(r"[()\[\]{},]")
RE_WF_ESPACO = re.compile(r"\s*")
RE_WF_CHAMADA = re.compile(r"(?<![\w$.])agent\s*\(")
RE_WF_CHAMADA_ANTIGA = re.compile(r"\bagent\s*\(")  # the forbidden-session rule also counts obj.agent(
RE_WF_FUNCAO = re.compile(r"\bfunction\s*\*?\s*$")
RE_WF_LOCAL = re.compile(r"(?<![\w$.])agent\s*=>|[(,]\s*agent\s*[,)=]|\b(?:const|let|var)\s+agent\b|"
                         r"\bfunction\s*\*?\s*agent\b")
RE_WF_TIPO = re.compile(r"agentType\b")
RE_WF_MODELO = re.compile(r"\bmodel\s*[:=]")
RE_WF_PERDAO = re.compile(r"tune-up:\s*allow-generic[ \t]+([^\n]*)")
GENERICOS = ("general-purpose", "claude", "workflow-subagent")
PARES = {"(": ")", "[": "]", "{": "}"}


def tokens(script):
    """(start, end, text) of each comment and string literal, left to right."""
    toks, i, falha, fecha = [], 0, {}, -2
    while True:
        m = RE_WF_INICIO.search(script, i)
        if not m:
            return toks
        i, c = m.start(), m.group(0)
        if c == "//":
            e = script.find("\n", i)
            e = len(script) if e < 0 else e
        elif c == "/*":
            if fecha != -1 and fecha < i + 2:
                fecha = script.find("*/", i + 2)
            e = fecha + 2 if fecha >= 0 else -1
        elif i < falha.get(c, -1):
            e = -1  # an escaped quote inside a literal already known to be unclosed
        else:
            e = RE_WF_CORPO[c].match(script, i).end()
            if script.startswith(c, e):
                e += 1
            else:
                falha[c], e = e, -1
        if e < 0:
            i += 1
            continue
        toks.append((i, e, script[i:e]))
        i = e


def analisar(script):
    """Comments and strings blanked once (newlines kept); reused by every check on the script."""
    toks, partes, ult = tokens(script), [], 0
    for a, b, t in toks:
        partes += [script[ult:a], re.sub(r"[^\n]", " ", t)]
        ult = b
    partes.append(script[ult:])
    masc = "".join(partes)
    fecha, virgulas, pilha = {}, {}, []
    for m in RE_WF_SINAL.finditer(masc):  # one pass: opener -> closer, opener -> its level-1 commas
        c, i = m.group(0), m.start()
        if c == ",":
            if pilha:
                virgulas.setdefault(pilha[-1][0], []).append(i)
        elif c in PARES:
            pilha.append((i, PARES[c]))
        elif pilha and pilha[-1][1] == c:  # a stray closer is ignored
            fecha[pilha.pop()[0]] = i
    return {"script": script, "masc": masc, "toks": toks, "fecha": fecha, "virgulas": virgulas,
            "strings": {a: (b, t) for a, b, t in toks if not t.startswith("/")},
            "comentarios": {a: b for a, b, t in toks if t.startswith("/")}}


def _pula(masc, i):
    return RE_WF_ESPACO.match(masc, i).end()


def _inicio(an, i):
    """First position at or after i that is not whitespace or a comment (a string start stops it)."""
    while True:
        i = _pula(an["script"], i)
        if i not in an["comentarios"]:
            return i
        i = an["comentarios"][i]


def _chamadas(an, regex):
    """(start, paren) of each agent( call; `function agent(` and a method `agent() {` are definitions."""
    masc, fecha = an["masc"], an["fecha"]
    for m in regex.finditer(masc):
        p = m.end() - 1
        if RE_WF_FUNCAO.search(masc, max(0, m.start() - 20), m.start()):
            continue
        if p in fecha and masc.startswith("{", _pula(masc, fecha[p] + 1)):
            continue
        yield m.start(), p


def contagem(an):
    """(agent( calls, `model` keys) outside comments and strings, for the forbidden-session rule.
    A call inside a template `${...}` still counts; a `model:` inside a comment or string does not."""
    chamadas = sum(1 for _ in _chamadas(an, RE_WF_CHAMADA_ANTIGA))
    chamadas += sum(len(RE_WF_CHAMADA_ANTIGA.findall(t)) for a, (b, t) in an["strings"].items()
                    if t.startswith("`") and "${" in t)
    modelos = len(RE_WF_MODELO.findall(an["masc"]))
    modelos += sum(1 for a, (b, t) in an["strings"].items()  # quoted key: "model": ...
                   if t[0] in "'\"" and t[1:-1] == "model" and _pula(an["masc"], b) < len(an["masc"])
                   and an["masc"][_pula(an["masc"], b)] in ":=")
    return chamadas, modelos


def _valor(an, v, b):
    """True unless the value at v (entry ends at b) is a lone generic or empty string literal."""
    if v not in an["strings"]:
        return True  # variable or expression: cannot know, no false positive
    e2, t = an["strings"][v]
    if (t.startswith("`") and "${" in t) or _pula(an["masc"], e2) < b:
        return True  # template with ${} or literal inside an expression
    s = t[1:-1].strip()
    return bool(s) and s.lower() not in GENERICOS


def _tipado(an, ab):
    """True when the options object opened at ab has a level-1 `agentType` that is not a generic
    literal; the last one wins. A spread or a non-literal computed key: cannot know, typed."""
    masc, strings, fecha = an["masc"], an["strings"], an["fecha"]
    lim = [ab] + an["virgulas"].get(ab, []) + [fecha[ab]]
    tipo = False
    for a, b in zip(lim, lim[1:]):
        a = _inicio(an, a + 1)
        chave = None
        if masc.startswith("...", a):
            return True
        if masc.startswith("[", a):
            d, k = fecha.get(a, b), _inicio(an, a + 1)
            if k not in strings or _pula(masc, strings[k][0]) != d:
                return True
            if strings[k][1][1:-1] == "agentType":
                chave = d + 1
        elif RE_WF_TIPO.match(masc, a):
            chave = a + len("agentType")
        elif a in strings and strings[a][1][1:-1] == "agentType":
            chave = strings[a][0]
        if chave is None:
            continue
        c = _pula(masc, chave)
        if c == b:
            tipo = True  # shorthand {agentType}: a variable
        elif masc.startswith(":", c):
            tipo = _valor(an, _inicio(an, c + 1), b)
    return tipo


def workflow_generico(script, an=None):
    """Line numbers of `agent(` calls without an explicit non-generic `agentType`, minus the ones
    marked `tune-up: allow-generic <reason>` on the same or the previous line."""
    an = an or analisar(script)
    masc, fecha = an["masc"], an["fecha"]
    if RE_WF_LOCAL.search(masc):
        return []  # `agent` is a local name somewhere: ambiguous, no false positive
    nl = [m.start() for m in re.finditer("\n", script)]
    perdoadas = set()
    for a, b, t in an["toks"]:
        p = RE_WF_PERDAO.search(t) if t.startswith("/") else None
        if p and p.group(1).replace("*/", "").strip():
            perdoadas.add(bisect.bisect_right(nl, a + p.start()) + 1)
    linhas = []
    for ini, o in _chamadas(an, RE_WF_CHAMADA):
        if o not in fecha:
            continue  # never closed: no finding for it
        lim = [o] + an["virgulas"].get(o, []) + [fecha[o]]
        args = [(_inicio(an, a + 1), b) for a, b in zip(lim, lim[1:])]
        if any(masc.startswith("...", a) for a, b in args):
            continue  # arguments from a spread: cannot know
        a, b = args[1] if len(args) > 1 else args[0]
        objeto = masc.startswith("{", a) and a in fecha and _pula(masc, fecha[a] + 1) == b
        if len(args) > 1 and a < b and not objeto:
            continue  # options from a variable or call: cannot know, no false positive
        n = bisect.bisect_right(nl, ini) + 1
        if n not in perdoadas and n - 1 not in perdoadas and not (objeto and _tipado(an, a)):
            linhas.append(n)
    return linhas
