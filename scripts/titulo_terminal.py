#!/usr/bin/env python3
"""tune-up: make the terminal tab show the conversation topic, not the Claude Code version.

The integrated terminal of VS Code-family editors (VS Code, Cursor, Windsurf,
Antigravity, VSCodium...) names the tab after the process by default. The Claude
Code executable is named after its version (e.g. 2.1.304), so the tab becomes a
number. ${sequence} alone makes the tab show only the title Claude Code writes
(with ${process} after it the name repeated, e.g. "Claude Code - claude", until
the conversation got a topic); VS Code falls back to the process name when no
title was sent yet.

Usage: python3 titulo_terminal.py            list what would change (writes nothing)
       python3 titulo_terminal.py aplicar    write to every editor found
       python3 titulo_terminal.py desfazer   remove only the value tune-up added
Output: JSON on stdout. Stdlib only. Before writing, copies the file to
settings.json.bak-tune-up. A value the owner chose is never replaced.
"""
import json
import os
import re
import shutil
import sys

CHAVE = "terminal.integrated.tabs.title"
VALOR = "${sequence}"
ANTIGO = "${sequence}${separator}${process}"  # value written by tune-up up to 2.1.0
SUFIXO_BACKUP = ".bak-tune-up"


def _par(valor):
    return r'"%s"\s*:\s*"%s"' % (re.escape(CHAVE), re.escape(valor))


def bases():
    """Where editors keep the user settings, per OS."""
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        return [os.path.join(home, "Library", "Application Support")]
    if os.name == "nt":
        return [os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")]
    return [os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")]


def editores():
    """(editor, settings.json) of each VS Code-family editor: its User/ folder has globalStorage/.
    Profiles (User/profiles/<id>/settings.json) do not inherit the default one, so they are included."""
    achados = []
    for base in bases():
        try:
            nomes = sorted(os.listdir(base))
        except OSError:
            continue
        for nome in nomes:
            user = os.path.join(base, nome, "User")
            if not os.path.isdir(os.path.join(user, "globalStorage")):
                continue
            achados.append((nome, os.path.join(user, "settings.json")))
            perfis = os.path.join(user, "profiles")
            for p in sorted(os.listdir(perfis)) if os.path.isdir(perfis) else []:
                arq = os.path.join(perfis, p, "settings.json")
                if os.path.isfile(arq):
                    achados.append(("%s (profile %s)" % (nome, p), arq))
    return achados


def terminal_atual():
    e = os.environ
    if e.get("TERM_PROGRAM") == "vscode":
        return {"tipo": "vscode", "app": e.get("__CFBundleIdentifier", "")}
    if "JetBrains" in e.get("TERMINAL_EMULATOR", ""):
        return {"tipo": "jetbrains", "app": e.get("TERMINAL_EMULATOR", "")}
    return {"tipo": "outro", "app": e.get("TERM_PROGRAM") or e.get("TERM", "")}


def _varrer(texto):
    """settings.json allows // and /* */ comments and trailing commas. Returns (position of the '}'
    closing the root object, position of the last useful character before it), skipping strings and comments."""
    i, n, prof, ultimo = 0, len(texto), 0, -1
    while i < n:
        c = texto[i]
        if c == '"':
            j = i + 1
            while j < n and texto[j] != '"':
                j += 2 if texto[j] == "\\" else 1
            ultimo, i = j, j + 1
            continue
        if texto.startswith("//", i):
            j = texto.find("\n", i)
            i = n if j < 0 else j
            continue
        if texto.startswith("/*", i):
            j = texto.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "{[":
            prof += 1
        elif c in "}]":
            prof -= 1
            if prof == 0 and c == "}":
                return i, ultimo
        if not c.isspace():
            ultimo = i
        i += 1
    return -1, ultimo


def _pular_vazio(texto, i):
    """First position from i that is neither whitespace nor a comment."""
    n = len(texto)
    while i < n:
        if texto[i].isspace():
            i += 1
        elif texto.startswith("//", i):
            j = texto.find("\n", i)
            i = n if j < 0 else j
        elif texto.startswith("/*", i):
            j = texto.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            break
    return i


def _json_estrito(texto):
    """Strips comments and trailing commas (outside strings) so json.loads can read it."""
    saida, i, n = [], 0, len(texto)
    while i < n:
        c = texto[i]
        if c == '"':
            j = i + 1
            while j < n and texto[j] != '"':
                j += 2 if texto[j] == "\\" else 1
            saida.append(texto[i:j + 1])
            i = j + 1
        elif texto.startswith("//", i):
            j = texto.find("\n", i)
            i = n if j < 0 else j
        elif texto.startswith("/*", i):
            j = texto.find("*/", i + 2)
            i = n if j < 0 else j + 2
        elif c == ",":
            j = _pular_vazio(texto, i + 1)
            if j < n and texto[j] not in "}]":
                saida.append(c)
            i += 1
        else:
            saida.append(c)
            i += 1
    return "".join(saida)


def ler(texto):
    if not texto.strip():
        return {}
    d = json.loads(_json_estrito(texto))
    if not isinstance(d, dict):
        raise ValueError("root is not an object")
    return d


def _recuo(texto):
    m = re.search(r'^([ \t]+)"', texto, re.M)
    return m.group(1) if m else "    "


def inserir(texto):
    """Puts the key before the final '}', keeping comments and the file indentation."""
    if not texto.strip():
        return '{\n    "%s": "%s"\n}\n' % (CHAVE, VALOR)
    fecha, ultimo = _varrer(texto)
    if fecha < 0 or ultimo < 0:
        raise ValueError("root object does not close")
    linha = '%s"%s": "%s"' % (_recuo(texto), CHAVE, VALOR)
    corte = fecha
    while corte > 0 and texto[corte - 1] in " \t":
        corte -= 1
    if corte > 0 and texto[corte - 1] == "\n":
        novo = texto[:corte] + linha + "\n" + texto[corte:]
    else:
        novo = texto[:fecha] + "\n" + linha + "\n" + texto[fecha:]
    if texto[ultimo] not in "{,":
        novo = novo[:ultimo + 1] + "," + novo[ultimo + 1:]
    return novo


def remover(texto, valor):
    novo, n = re.subn(r",\s*" + _par(valor), "", texto, count=1)
    if not n:
        novo, n = re.subn(r"[ \t]*" + _par(valor) + r"[ \t]*,?[ \t]*\n?", "", texto, count=1)
    return novo


def trocar(texto):
    """Old tune-up value -> current one, in place."""
    return re.sub(_par(ANTIGO), lambda _m: '"%s": "%s"' % (CHAVE, VALOR), texto, count=1)


def estado(d):
    if CHAVE not in d:
        return "falta"
    if d[CHAVE] == VALOR:
        return "aplicado"
    return "antigo" if d[CHAVE] == ANTIGO else "valor_do_dono"


def tratar(arquivo, acao):
    item = {"arquivo": arquivo}
    try:
        with open(arquivo, encoding="utf-8") as f:
            texto = f.read()
    except FileNotFoundError:
        texto = None
    except OSError as e:
        item.update(antes="ilegivel", depois="ilegivel", erro=str(e))
        return item
    try:
        antes = ler(texto or "")
    except ValueError as e:  # json.JSONDecodeError is a ValueError
        item.update(antes="ilegivel", depois="ilegivel", erro=str(e))
        return item
    item["antes"] = "sem_arquivo" if texto is None else estado(antes)
    if item["antes"] == "valor_do_dono":
        item["valor"] = antes[CHAVE]
    item["depois"] = item["antes"]
    if acao == "aplicar" and item["antes"] in ("falta", "sem_arquivo"):
        novo = inserir(texto or "")
        esperado = dict(antes, **{CHAVE: VALOR})
    elif acao == "aplicar" and item["antes"] == "antigo":
        novo = trocar(texto)
        esperado = dict(antes, **{CHAVE: VALOR})
    elif acao == "desfazer" and item["antes"] in ("aplicado", "antigo"):
        novo = remover(texto, antes[CHAVE])
        esperado = {k: v for k, v in antes.items() if k != CHAVE}
    else:
        return item
    try:
        conferido = ler(novo) == esperado
    except ValueError:
        conferido = False
    if not conferido:  # the edit would touch something else: do not write
        item.update(depois="ilegivel", erro="edit did not verify, file left untouched")
        return item
    try:
        if texto is not None:
            shutil.copy2(arquivo, arquivo + SUFIXO_BACKUP)
        with open(arquivo, "w", encoding="utf-8") as f:
            f.write(novo)
    except OSError as e:
        item.update(depois="ilegivel", erro=str(e))
        return item
    item["depois"] = estado(esperado)
    if texto is not None:
        item["backup"] = arquivo + SUFIXO_BACKUP
    return item


def main(argv):
    acao = argv[1] if len(argv) > 1 else "listar"
    if acao not in ("listar", "aplicar", "desfazer"):
        print(json.dumps({"erro": "usage: titulo_terminal.py [aplicar|desfazer]"}))
        return 2
    lista = []
    for nome, arquivo in editores():
        item = tratar(arquivo, acao)
        item["editor"] = nome
        lista.append(item)
    print(json.dumps({
        "acao": acao,
        "valor": VALOR,
        "terminal_atual": terminal_atual(),
        "titulo_do_claude_desligado": os.environ.get("CLAUDE_CODE_DISABLE_TERMINAL_TITLE", "") not in ("", "0"),
        "editores": lista,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
