"""tune-up: generic agent() calls (no explicit agentType) in a Workflow script."""
import re

# comments are skipped; every string literal (any length, any character) is checked whole
RE_WF_TOKEN = re.compile(r"//[^\n]*|/\*.*?\*/|'(?:\\.|[^'\\\n])*'|\"(?:\\.|[^\"\\\n])*\"|`(?:\\.|[^`\\])*`", re.S)

RE_WF_CHAMADA = re.compile(r"(?<![\w$.])agent\s*\(")
RE_WF_FUNCAO = re.compile(r"\bfunction\s*\*?\s*$")
RE_WF_TIPO = re.compile(r"(?<![\w$.])agentType\s*(?=[:,}])")
RE_WF_TIPO_ASPAS = re.compile(r"['\"`]agentType['\"`]\s*:")
RE_WF_PERDAO = re.compile(r"tune-up:\s*allow-generic[ \t]+([^\n]*)")
GENERICOS = ("general-purpose", "claude", "workflow-subagent")
PARES = {"(": ")", "[": "]", "{": "}"}


def _tipado(script, masc, strings, ini, fim):
    """True when the args script[ini:fim] carry an `agentType` that is not a generic literal."""
    chaves = [m.end() for m in RE_WF_TIPO.finditer(masc, ini, fim)]
    chaves += [strings[m.start()][0] for m in RE_WF_TIPO_ASPAS.finditer(script, ini, fim)
               if m.start() in strings]  # quoted key: "agentType": ...
    for e in chaves:
        resto = masc[e:fim].lstrip()
        if not resto.startswith(":"):
            return True  # shorthand {agentType}: a variable
        v = e + masc[e:fim].index(":") + 1
        v += len(script[v:fim]) - len(script[v:fim].lstrip())  # masc blanks strings: skip in script
        if v not in strings:
            return True  # variable or expression: cannot know, no false positive
        e2, t = strings[v]
        if (t.startswith("`") and "${" in t) or masc[e2:fim].lstrip()[:1] not in (",", "}", ")", ""):
            return True  # template with ${} or literal inside an expression
        if t[1:-1].strip() and t[1:-1].strip().lower() not in GENERICOS:
            return True
    return False


def workflow_generico(script):
    """Line numbers of `agent(` calls without an explicit non-generic `agentType`, minus the ones
    marked `tune-up: allow-generic <reason>` on the same or the previous line."""
    masc, strings, perdoadas = list(script), {}, set()
    for m in RE_WF_TOKEN.finditer(script):
        t = m.group(0)
        if t.startswith("/"):
            p = RE_WF_PERDAO.search(t)
            if p and p.group(1).replace("*/", "").strip():
                perdoadas.add(script.count("\n", 0, m.start() + p.start()) + 1)
        else:
            strings[m.start()] = (m.end(), t)
        for i in range(m.start(), m.end()):
            if masc[i] != "\n":
                masc[i] = " "
    masc = "".join(masc)
    linhas = []
    for m in RE_WF_CHAMADA.finditer(masc):
        if RE_WF_FUNCAO.search(masc, max(0, m.start() - 20), m.start()):
            continue
        pilha, fim, virgula = [")"], len(masc), None
        for i in range(m.end(), len(masc)):
            c = masc[i]
            if c == "," and len(pilha) == 1 and virgula is None:
                virgula = i
            elif c in PARES:
                pilha.append(PARES[c])
            elif c in ")]}" and pilha[-1] == c:  # a stray closer is ignored
                pilha.pop()
                if not pilha:
                    fim = i
                    break
        n = masc.count("\n", 0, m.start()) + 1
        opcoes = script[virgula + 1:fim].strip() if virgula is not None else ""
        if "..." in masc[m.end():fim] or (opcoes and not opcoes.startswith("{")):
            continue  # options from a spread, variable or call: cannot know, no false positive
        if n not in perdoadas and n - 1 not in perdoadas and not _tipado(script, masc, strings, m.end(), fim):
            linhas.append(n)
    return linhas
