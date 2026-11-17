"""The reel's motion script (referencias/motion-js.md): static checks. Imported, never run.

A reel may carry exactly one inline script: the studio engine pasted verbatim from referencias/motor-motion.js
(trusted, compared after collapsing whitespace) followed by the scene part the session writes. The scene part is
checked against a positive list (identifiers and property names it may use) and a deny list (network, code from
text, clocks, randomness, storage, browser globals, HTML injection), plus the hook rule: a scene 1 text clip is
never hidden by its motion. Static only: the real guarantee is a render without network; this blocks the plain
cases and every way the engine itself does not need. Python 3.9+, standard library.
"""
import os
import re

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOTOR = os.path.join(STUDIO, "referencias", "motor-motion.js")
SCRIPT_RE = re.compile(r"<script\b([^>]*)>(.*?)</script\s*>", re.I | re.S)
ABRE_RE = re.compile(r"<script\b", re.I)
EVENTO_RE = re.compile(r"""<[a-z][^>]*\son[a-z]+\s*=""", re.I)  # onload=, onerror=...: script outside the tag
JS_URL_RE = re.compile(r"javascript:", re.I)
NUMERO_RE = re.compile(r"(?<![\w$.])(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?")
ID_RE = re.compile(r"[A-Za-z_$][\w$]*")

# What the scene part may never contain (each one is a test case, green and red).
NEGADOS = [
    ("rede: fetch", re.compile(r"\bfetch\b")),
    ("rede: XMLHttpRequest", re.compile(r"XMLHttpRequest")),
    ("rede: WebSocket", re.compile(r"WebSocket")),
    ("rede: EventSource", re.compile(r"EventSource")),
    ("rede: sendBeacon", re.compile(r"sendBeacon")),
    ("rede: import", re.compile(r"\bimport\b")),
    ("rede: require", re.compile(r"\brequire\b")),
    ("código de texto: eval", re.compile(r"\beval\b")),
    ("código de texto: Function", re.compile(r"\bFunction\b")),
    ("relógio: Date", re.compile(r"\bDate\b")),
    ("relógio: performance", re.compile(r"\bperformance\b")),
    ("acaso: Math.random", re.compile(r"\brandom\b")),
    ("relógio: setTimeout", re.compile(r"\bsetTimeout\b")),
    ("relógio: setInterval", re.compile(r"\bsetInterval\b")),
    ("relógio: requestAnimationFrame", re.compile(r"\brequestAnimationFrame\b")),
    ("WAAPI fora do motor: animate", re.compile(r"\banimate\b|\bAnimation\b|\bKeyframeEffect\b")),
    ("promessa: then/async/await", re.compile(r"\b(?:then|async|await|Promise)\b")),
    ("navegador: document", re.compile(r"\bdocument\b")),
    ("navegador: window", re.compile(r"\b(?:window|globalThis|self|top|parent|frames|opener)\b")),
    ("navegador: cookie", re.compile(r"\bcookie\b")),
    ("navegador: storage", re.compile(r"Storage\b|\bindexedDB\b|\bcaches\b")),
    ("navegador: navigator/location", re.compile(r"\b(?:navigator|location|history)\b")),
    ("injeção: innerHTML/write", re.compile(r"\b(?:innerHTML|outerHTML|insertAdjacentHTML|write|writeln)\b")),
    ("escape: constructor/prototype", re.compile(r"\b(?:constructor|prototype|__proto__|__defineGetter__)\b")),
    ("evento: addEventListener", re.compile(r"\baddEventListener\b")),
    ("acesso por texto: [\"...\"]", re.compile(r"[\w$\])]\s*\[\s*[\"'`]")),
]
# The positive list of the scene part: keywords, the engine's recipes, a few safe globals and array helpers.
PALAVRAS = {"var", "let", "const", "for", "function", "return", "if", "else", "true", "false", "null", "new",
            "typeof", "in", "of", "break", "continue"}
RECEITAS = {"trilha", "entra", "palavras", "contador", "mascara", "camera", "parallax", "pulso", "onda", "traco",
            "vaivem", "pronto"}
GLOBAIS = {"M", "Math", "Number", "String", "Array"}
PROPRIEDADES = RECEITAS | {"floor", "round", "min", "max", "abs", "sqrt", "pow", "sin", "cos", "PI", "length", "push",
                           "forEach", "map", "concat", "join", "slice", "indexOf", "toFixed"}
# Recipes that never hide a scene 1 text clip (the cover is readable in frame 0).
GANCHO_OK = {"camera", "parallax", "pulso", "onda"}
CHAMADA_RE = re.compile(r"\bM\.(\w+)\(([^;]*)\)\s*;")
ALVO_RE = re.compile(r"\s*(\[[^\]]*\]|\"[^\"]*\"|'[^']*')\s*(?:,|\Z)")


def _plano(texto):
    return " ".join(texto.split())


def motor():
    """The engine text (whitespace collapsed), or None when referencias/motor-motion.js is missing."""
    try:
        with open(MOTOR, encoding="utf-8") as f:
            return _plano(f.read())
    except OSError:
        return None


def separar(codigo):
    """(code without comments and with every string literal emptied to "", [string literals]) in one pass, so a
    `//` inside a string is never taken for a comment. A template literal (backquote) stays as a lone `."""
    limpo, textos, i, n = [], [], 0, len(codigo)
    while i < n:
        c = codigo[i]
        if codigo.startswith("/*", i):
            j = codigo.find("*/", i + 2)
            i = n if j < 0 else j + 2
            limpo.append(" ")
        elif codigo.startswith("//", i):
            j = codigo.find("\n", i)
            i = n if j < 0 else j
        elif c in "\"'":
            j = i + 1
            while j < n and codigo[j] != c and codigo[j] != "\n":
                j += 2 if codigo[j] == "\\" else 1
            textos.append(codigo[i + 1:j])
            limpo.append('""')
            i = j + 1
        else:
            limpo.append(c)
            i += 1
    return "".join(limpo), textos



def _declarados(codigo):
    nomes = set(re.findall(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)", codigo))
    nomes |= set(re.findall(r"\bfunction\s+([A-Za-z_$][\w$]*)", codigo))
    for params in re.findall(r"\bfunction\b[^(]*\(([^)]*)\)", codigo):
        nomes |= set(ID_RE.findall(params))
    return nomes


def _contadores(codigo):
    return set(re.findall(r"\bfor\s*\(\s*(?:var|let)\s+([A-Za-z_$][\w$]*)\s*=\s*\d", codigo))


def checar_cena(codigo):
    """Problems of the scene part (the script after the engine)."""
    out = []
    if "`" in codigo:
        out.append("crase (template literal) no script: use aspas")
    limpo, textos = separar(codigo)
    for rotulo, rx in NEGADOS:
        for m in rx.finditer(limpo if rotulo != "acesso por texto: [\"...\"]" else limpo.replace('""', '"')):
            out.append("%s: %s" % (rotulo, m.group(0)))
    for t in textos:
        for rotulo, rx in NEGADOS[:-1]:
            if rx.search(t) and not rotulo.startswith(("relógio: Date", "navegador: window")):
                out.append("texto suspeito (%s): %s" % (rotulo, t[:40]))
        if re.search(r"https?:|//|\\x|\\u", t):
            out.append("texto suspeito (URL ou escape): %s" % t[:40])
    locais, contadores = _declarados(limpo), _contadores(limpo)
    sem_num = NUMERO_RE.sub(" 0 ", limpo)
    for m in re.finditer(r"(\.\s*)?([A-Za-z_$][\w$]*)", sem_num):
        nome, membro = m.group(2), bool(m.group(1))
        if membro:
            if nome not in PROPRIEDADES:
                out.append("propriedade fora da lista: .%s" % nome)
        elif nome not in PALAVRAS | GLOBAIS | locais:
            out.append("nome fora da lista: %s" % nome)
    for idx in re.findall(r"[\w$\])]\s*\[([^\[\]]*)\]", sem_num):
        if not all(n in contadores for n in ID_RE.findall(idx)):
            out.append("acesso [ ] só com número ou contador de for: [%s]" % idx.strip())
    if "M.pronto()" not in limpo.replace(" ", ""):
        out.append("falta M.pronto(); na última linha")
    return sorted(set(out))


def chamadas(codigo):
    """[(receita, [ids], resto dos argumentos)] of the M.<receita>("id" | ["id", ...], ...) calls."""
    out = []
    for nome, args in CHAMADA_RE.findall(re.sub(r"/\*.*?\*/", " ", codigo, flags=re.S)):
        m = ALVO_RE.match(args)  # a literal id or list of ids; a computed one ("v" + i) is not checked here
        out.append((nome, re.findall(r"[\"']([\w-]+)[\"']", m.group(1)) if m else [], args))
    return out


PRECO_RE = re.compile(r"R\$|\$|%|€")  # a price counted up from 0 shows a false price on screen


def checar(html, ids_existentes=(), gancho=(), textos=None):
    """Problems of the reel's scripts: count, engine verbatim, the scene part, ids that exist, the hook rule and
    the counter rule (`textos`: {id: clip text}; `contador` only counts quantities, never a price)."""
    out = []
    if EVENTO_RE.search(html):
        out.append("atributo de evento (on...=) numa tag")
    if JS_URL_RE.search(html):
        out.append("URL javascript:")
    blocos = SCRIPT_RE.findall(html)
    if len(ABRE_RE.findall(html)) != len(blocos):
        out.append("tag script sem fechamento")
    if not blocos:
        return out
    if len(blocos) > 1:
        out.append("%d scripts: só um, inline, no fim do body" % len(blocos))
    attrs, corpo = blocos[-1]
    if attrs.strip():
        out.append("script com atributos (%s): só <script> inline, sem src" % attrs.strip()[:40])
    base = motor()
    plano = _plano(corpo)
    if base is None:
        return out + ["referencias/motor-motion.js não encontrado"]
    if not plano.startswith(base):
        return out + ["o script não começa pelo motor de referencias/motor-motion.js colado sem mudanças"]
    cena = plano[len(base):]
    out += checar_cena(cena)
    existentes = set(ids_existentes)
    for receita, ids, resto in chamadas(cena):
        if receita not in RECEITAS:
            out.append("receita desconhecida: M.%s" % receita)
        for i in ids:
            if existentes and i not in existentes:
                out.append("M.%s(\"%s\"): id que não existe no HTML" % (receita, i))
            if receita == "contador" and PRECO_RE.search((textos or {}).get(i, "")):
                out.append("M.contador em %s: preço entra carimbado (entra ..., \"carimbo\"), nunca contando de 0; o "
                           "contador é só para quantidades (itens, anos, clientes)" % i)
            if i in gancho and receita not in GANCHO_OK and not (receita == "palavras" and "onda" in resto):
                out.append("M.%s em %s: na cena 1 o texto fica legível no quadro 0 (use onda, camera, parallax "
                           "ou pulso)" % (receita, i))
    return sorted(set(out))
