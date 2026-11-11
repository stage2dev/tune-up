"""Readers for descobrir_marca.py: each one turns one project file into brand candidates.

Candidates go into Achados with a source "arquivo:linha" and a confidence (alta, media, baixa).
Nothing is guessed: a value that does not parse is skipped. Python 3.9+, standard library only.
"""
import html.parser
import json
import os
import re

import cores

CAMPOS = ("nome", "descricao", "cores.bg", "cores.surface", "cores.primary", "cores.text",
          "cores.accent", "fontes.heading", "fontes.body", "logo")
RANK = {"alta": 0, "media": 1, "baixa": 2}
EXT_LOGO = (".svg", ".png", ".webp", ".jpg", ".jpeg")
ICONES_DE_MODELO = {"vite.svg", "react.svg", "next.svg", "vercel.svg", "nuxt.svg", "svelte.svg",
                    "angular.svg", "vue.svg", "file.svg", "globe.svg", "window.svg"}
APELIDOS_COR = {"bg": "bg", "background": "bg", "fundo": "bg", "page": "bg",
                "surface": "surface", "card": "surface", "superficie": "surface", "panel": "surface",
                "primary": "primary", "brand": "primary", "primaria": "primary", "marca": "primary",
                "text": "text", "foreground": "text", "fg": "text", "texto": "text", "ink": "text",
                "accent": "accent", "secondary": "accent", "destaque": "accent", "secundaria": "accent"}
APELIDOS_FONTE = {"heading": "heading", "headings": "heading", "display": "heading", "title": "heading",
                  "titulo": "heading", "body": "body", "sans": "body", "base": "body", "text": "body",
                  "texto": "body", "corpo": "body"}
# Library defaults (shadcn slate/neutral themes; Tailwind slate/gray/zinc/blue/indigo/violet 500-600).
# A partial list: a default not listed here keeps its confidence.
PADROES_DE_BIBLIOTECA = {cores.para_hex(v) for v in (
    "0 0% 100%", "222.2 84% 4.9%", "222.2 47.4% 11.2%", "210 40% 98%", "210 40% 96.1%",
    "215.4 16.3% 46.9%", "214.3 31.8% 91.4%", "0 84.2% 60.2%", "0 0% 3.9%", "0 0% 9%", "0 0% 98%",
    "0 0% 96.1%", "oklch(1 0 0)", "oklch(0.145 0 0)", "oklch(0.205 0 0)", "oklch(0.985 0 0)",
    "oklch(0.97 0 0)", "oklch(0.556 0 0)", "oklch(0.922 0 0)", "#64748b", "#475569", "#6b7280",
    "#4b5563", "#71717a", "#52525b", "#3b82f6", "#2563eb", "#6366f1", "#4f46e5", "#8b5cf6", "#7c3aed")}


def vazio():
    return {"valor": None, "fonte": None, "confianca": "faltando", "travado": False}


def dentro(caminho, raiz):
    c, r = os.path.realpath(caminho), os.path.realpath(raiz)
    return c == r or c.startswith(r.rstrip(os.sep) + os.sep)


def rel(caminho, raiz):
    return os.path.relpath(caminho, raiz).replace(os.sep, "/")


class Achados:
    """Candidates per field; the best confidence wins, then the first seen."""

    def __init__(self):
        self.c = {k: [] for k in CAMPOS}

    def add(self, campo, valor, fonte, confianca):
        if valor:
            self.c[campo].append((RANK[confianca], len(self.c[campo]), valor, fonte, confianca))

    def melhor(self, campo):
        if not self.c[campo]:
            return vazio()
        _, _, valor, fonte, conf = min(self.c[campo])
        return {"valor": valor, "fonte": fonte, "confianca": conf, "travado": False}


def _add_cor(ach, chave, texto, fonte, conf="alta"):
    alvo = APELIDOS_COR.get(chave)
    hexa = cores.para_hex(texto)
    if alvo and hexa:
        ach.add("cores." + alvo, hexa, fonte, "baixa" if hexa in PADROES_DE_BIBLIOTECA else conf)


def _chave_var(nome):
    """'--color-primary' -> ('cor', 'primary'); '--font-heading' -> ('fonte', 'heading')."""
    n = nome[2:].lower()
    for pre in ("font-family-", "fonts-", "font-"):
        if n.startswith(pre):
            return "fonte", n[len(pre):]
    for pre in ("colors-", "color-"):
        if n.startswith(pre):
            n = n[len(pre):]
    return "cor", n[:-6] if n.endswith("-color") else n


def _blocos(texto):
    """(start offset, body) of each :root { } and @theme { } block (.dark and others are skipped)."""
    for m in re.finditer(r"(:root|@theme(?:\s+inline)?)\s*\{", texto):
        prof, i = 1, m.end()
        while i < len(texto) and prof:
            prof += {"{": 1, "}": -1}.get(texto[i], 0)
            i += 1
        yield m.end(), texto[m.end():i - 1]


def ler_css(ach, texto, arq, linha0=1):
    sem_coment = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), texto, flags=re.S)
    vars_ = {}
    for inicio, corpo in _blocos(sem_coment):
        for m in re.finditer(r"(--[\w-]+)\s*:\s*([^;{}]+)", corpo):
            linha = linha0 + sem_coment.count("\n", 0, inicio + m.start())
            vars_.setdefault(m.group(1), (m.group(2).strip(), "%s:%d" % (arq, linha)))
    for nome, (valor, fonte) in vars_.items():
        ref = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", valor)
        if ref and ref.group(1) in vars_:
            valor, fonte = vars_[ref.group(1)]
        tipo, chave = _chave_var(nome)
        if tipo == "fonte" and APELIDOS_FONTE.get(chave) and not valor.startswith("var("):
            ach.add("fontes." + APELIDOS_FONTE[chave], valor, fonte, "alta")
        elif tipo == "cor":
            _add_cor(ach, chave, valor, fonte)
    for seletor, alvo in ((r"(?:^|[\s,}])h1\b[^{]*", "heading"), (r"(?:^|[\s,}])body\b[^{]*", "body")):
        for m in re.finditer(seletor + r"\{[^}]*?font-family\s*:\s*([^;}]+)", sem_coment):
            valor = m.group(1).strip()
            if not valor.startswith("var("):
                linha = linha0 + sem_coment.count("\n", 0, m.start(1))
                ach.add("fontes." + alvo, valor, "%s:%d" % (arq, linha), "media")


def ler_tailwind(ach, texto, arq):
    aberto = None
    for i, linha in enumerate(texto.splitlines(), 1):
        fonte = "%s:%d" % (arq, i)
        m = re.search(r"['\"]?([\w-]+)['\"]?\s*:\s*\{", linha)
        if m:
            aberto = m.group(1).lower()
        for m in re.finditer(r"['\"]?([\w-]+)['\"]?\s*:\s*(['\"`])([^'\"`]+)\2", linha):
            chave = m.group(1).lower()
            _add_cor(ach, aberto if chave == "default" else chave, m.group(3), fonte)
        m = re.search(r"['\"]?([\w-]+)['\"]?\s*:\s*\[([^\]]*)\]", linha)
        if m and APELIDOS_FONTE.get(m.group(1).lower()):
            itens = [x.strip().strip("'\"`") for x in m.group(2).split(",") if x.strip()]
            itens = ['"%s"' % x if " " in x else x for x in itens]
            if itens:
                ach.add("fontes." + APELIDOS_FONTE[m.group(1).lower()], ", ".join(itens), fonte, "alta")


class _Html(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.metas, self.imgs, self.icones, self.estilos = None, [], [], [], []
        self._em = None

    def handle_starttag(self, tag, attrs):
        a, linha = {k: (v or "") for k, v in attrs}, self.getpos()[0]
        if tag in ("title", "style"):
            self._em = (tag, linha, [])
        elif tag == "meta":
            self.metas.append(((a.get("name") or a.get("property") or "").lower(), a.get("content", ""), linha))
        elif tag == "img":
            self.imgs.append((a.get("src", ""), a.get("alt", ""), a.get("class", ""), a.get("id", ""), linha))
        elif tag == "link" and "icon" in a.get("rel", "").lower():
            self.icones.append((a.get("href", ""), linha))

    def handle_data(self, data):
        if self._em:
            self._em[2].append(data)

    def handle_endtag(self, tag):
        if self._em and self._em[0] == tag:
            texto = "".join(self._em[2])
            if tag == "title" and self.title is None:
                self.title = (" ".join(texto.split()), self._em[1])
            elif tag == "style":
                self.estilos.append((texto, self._em[1]))
            self._em = None


def arquivo_local(href, base, raiz):
    """A same-project image path from an href, or None (URL, '..', outside the project, missing)."""
    if not href or re.match(r"^([a-z][\w+.-]*:|//)", href, re.I):
        return None
    limpo = href.split("?")[0].split("#")[0]
    if ".." in limpo.replace("\\", "/").split("/") or not limpo.lower().endswith(EXT_LOGO):
        return None
    partes = limpo.replace("\\", "/").lstrip("/").split("/")
    for pasta in (base, raiz, os.path.join(raiz, "public")):
        c = os.path.join(pasta, *partes)
        if os.path.isfile(c) and not os.path.islink(c) and dentro(c, raiz):
            return c
    return None


def ler_html(ach, texto, arq, caminho, raiz):
    p = _Html()
    try:
        p.feed(texto)
        p.close()
    except Exception:  # html.parser rarely raises; a broken page just gives no candidate
        return
    base = os.path.dirname(caminho)
    for css, linha in p.estilos:
        ler_css(ach, css, arq, linha)
    for nome, conteudo, linha in p.metas:
        fonte = "%s:%d" % (arq, linha)
        if nome in ("og:site_name", "application-name"):
            ach.add("nome", conteudo.strip(), fonte, "alta")
        elif nome in ("description", "og:description"):
            ach.add("descricao", conteudo.strip(), fonte, "media")
        elif nome == "theme-color":
            _add_cor(ach, "primary", conteudo, fonte, "media")
    for src, alt, classe, ident, linha in p.imgs:
        if "logo" in (src + " " + classe + " " + ident).lower():
            achado = arquivo_local(src, base, raiz)
            if achado:
                ach.add("logo", rel(achado, raiz), "%s:%d" % (arq, linha), "alta")
            ach.add("nome", alt.strip(), "%s:%d" % (arq, linha), "media")
    for href, linha in p.icones:
        achado = arquivo_local(href, base, raiz)
        if achado and os.path.basename(achado).lower() not in ICONES_DE_MODELO:
            ach.add("logo", rel(achado, raiz), "%s:%d" % (arq, linha), "baixa")
    if p.title and p.title[0]:
        nome = re.split(r"\s+[-|–—·:]\s+", p.title[0])[0].strip()
        ach.add("nome", nome, "%s:%d" % (arq, p.title[1]), "media")


def _linha(texto, padrao):
    m = re.search(padrao, texto, re.M)
    return texto.count("\n", 0, m.start()) + 1 if m else 1


def ler_manifesto(ach, texto, arq, caminho, raiz):
    try:
        d = json.loads(texto)
    except ValueError:
        return
    if not isinstance(d, dict):
        return
    f = lambda k: "%s:%d" % (arq, _linha(texto, r'"%s"\s*:' % k))  # noqa: E731
    for k in ("name", "short_name"):
        if isinstance(d.get(k), str):
            ach.add("nome", d[k].strip(), f(k), "alta")
    if isinstance(d.get("description"), str):
        ach.add("descricao", d["description"].strip(), f("description"), "media")
    for k, chave in (("theme_color", "primary"), ("background_color", "bg")):
        if isinstance(d.get(k), str):
            _add_cor(ach, chave, d[k], f(k), "media")
    icones = d.get("icons") if isinstance(d.get("icons"), list) else []
    for icone in icones:
        src = icone.get("src") if isinstance(icone, dict) else None
        achado = arquivo_local(src, os.path.dirname(caminho), raiz) if isinstance(src, str) else None
        if achado:
            ach.add("logo", rel(achado, raiz), f("icons"), "baixa")


def ler_pacote(ach, texto, arq, nome_arq):
    """package.json, composer.json, go.mod, pyproject.toml, Cargo.toml: name (baixa), description."""
    if nome_arq in ("package.json", "composer.json"):
        try:
            d = json.loads(texto)
        except ValueError:
            return
        if not isinstance(d, dict):
            return
        if isinstance(d.get("name"), str):
            ach.add("nome", d["name"].split("/")[-1].strip(), "%s:%d" % (arq, _linha(texto, r'"name"\s*:')),
                    "baixa")
        if isinstance(d.get("description"), str):
            ach.add("descricao", d["description"].strip(),
                    "%s:%d" % (arq, _linha(texto, r'"description"\s*:')), "media")
        return
    if nome_arq == "go.mod":
        m = re.search(r"^module\s+(\S+)", texto, re.M)
        if m:
            ach.add("nome", m.group(1).rstrip("/").split("/")[-1], "%s:%d" % (arq, _linha(texto, r"^module\s")),
                    "baixa")
        return
    for chave, campo, conf in (("name", "nome", "baixa"), ("description", "descricao", "media")):
        m = re.search(r'^%s\s*=\s*"([^"\n]*)"' % chave, texto, re.M)
        if m:
            ach.add(campo, m.group(1).strip(), "%s:%d" % (arq, _linha(texto, r"^%s\s*=" % chave)), conf)
