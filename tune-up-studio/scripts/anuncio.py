"""Ad pieces, texts and the import sheet for the studio action estudio.anuncio (deterministic, no network).

  anuncio.py --plano google|meta
      sizes of the pieces (a1 = the master, then the adaptations) and the text limits, read from formatos.json
  anuncio.py --exportar FOLDER --plataforma google|meta
      checks FOLDER/textos.json (written by the session) and writes FOLDER/export/google-ads-editor.csv
      or FOLDER/export/meta-experimental.csv; on any problem it writes no sheet and exits 1
  anuncio.py --final FOLDER --plataforma google|meta --out final.json
      re-checks every a<N>/ piece at its own size (qa_imagem), the texts and the sheet; PRONTO only if all pass

The script checks only sizes, counts and required fields. Promises of results and prices that are not in the
briefing are the skill's job: no script can tell them apart. Every campaign, ad group/ad set and ad in a sheet
is Paused. Nothing is published and no ad API is called. Python 3.9, standard library only.
"""
import argparse
import csv
import html.parser
import io
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qa_imagem  # noqa: E402

STUDIO = qa_imagem.STUDIO
# id in formatos.json, ratio inside the entry (None = the entry has one size). The first one is the master.
PLANOS = {
    "google": {"tamanhos": [("google-ads-pmax-imagem", "1.91:1"), ("google-ads-pmax-imagem", "1:1")],
               "export": "google-ads-editor.csv"},
    "meta": {"tamanhos": [("facebook-feed-anuncio-tamanho", None), ("meta-ads-stories-tamanho", None)],
             "export": "meta-experimental.csv"},
}
META_MAX = 5  # our own cap on Meta variations (no official number was read)
RE_URL = re.compile(r"^https://[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(?::[0-9]{1,5})?"
                    r"(?:[/?#][A-Za-z0-9._~%/?#&=+,:@!*-]*)?$")
RE_ID = re.compile(r"^[0-9a-f]{12}$")
FORMULA = ("=", "+", "-", "@")  # a cell starting with one of these is a formula in a spreadsheet
GOOGLE_COLS = (["Campaign", "Campaign Type", "Campaign Status", "Ad Group", "Ad Group Status", "Ad type", "Status"]
               + ["Headline %d" % i for i in range(1, 16)] + ["Description %d" % i for i in range(1, 5)]
               + ["Path 1", "Path 2", "Final URL"])
META_COLS = ["Campaign Name", "Campaign Status", "Ad Set Name", "Ad Set Run Status", "Ad Name", "Ad Status",
             "Title", "Body", "Link", "Image File Name"]
STATUS_COLS = {"google": ("Campaign Status", "Ad Group Status", "Status"),
               "meta": ("Campaign Status", "Ad Set Run Status", "Ad Status")}
PAUSADO = {"google": "Paused", "meta": "PAUSED"}
MAX_PROBLEMAS = 10
# Google Search image assets are rejected with overlaid text, logo or graphics: a Google piece is a clean picture.
# Inline <svg> shapes are the picture (HyperFrames counts a frame of plain boxes as empty); its <text> is text.
FIGURAS = ("img", "picture", "canvas", "object", "embed", "iframe", "video", "input", "image")
RE_CSS_TEXTO = re.compile(r"content\s*:\s*(?:\"[^\"]|'[^']|attr\(|counter)", re.I)
# A 9:16 piece keeps every text inside #safezone, which must be exactly this box (formatos.json, 14% and 20%).
RE_SAFEZONE = re.compile(r"#safezone\s*\{([^}]*)\}")
SAFEZONE = {"position:absolute", "top:14%", "bottom:20%", "overflow:hidden"}


def _entradas(path=None):
    with open(path or os.path.join(STUDIO, "formatos.json"), encoding="utf-8") as f:
        return {e["id"]: e["valores"] for e in json.load(f)["formatos"]}


def nome_peca(n, largura, altura):
    return "a%d_%dx%d.png" % (n, largura, altura)


def plano(plataforma, path=None):
    """{"plataforma", "pecas": [{"id", "razao", "largura", "altura", "nome"}], "limites", "export"}."""
    if plataforma not in PLANOS:
        raise ValueError("plataforma must be google or meta")
    e = _entradas(path)
    pecas = []
    for i, (fid, razao) in enumerate(PLANOS[plataforma]["tamanhos"], 1):
        v = e[fid]
        if razao:
            v = next(t for t in v["tamanhos"] if t["razao"] == razao)
        largura, altura = int(v.get("largura") or v["largura_min"]), int(v.get("altura") or v["altura_min"])
        pecas.append({"id": "a%d" % i, "razao": v.get("razao") or razao, "largura": largura, "altura": altura,
                      "nome": nome_peca(i, largura, altura)})
    if plataforma == "google":
        r = e["google-ads-rsa-texto"]
        limites = {"titulos": [r["titulos_min"], r["titulos_max"], r["titulo_chars"]],
                   "descricoes": [r["descricoes_min"], r["descricoes_max"], r["descricao_chars"]],
                   "caminhos": [0, 2, r["caminho_chars"]]}
    else:  # the strictest of feed and stories, Facebook and Instagram
        fb, ig, st = e["facebook-feed-anuncio-texto"], e["instagram-feed-anuncio-texto"], e["meta-ads-stories-texto"]
        limites = {"titulos": [1, META_MAX, min(fb["titulo"], ig["titulo"])],
                   "textos_principais": [1, META_MAX, min(fb["texto_principal_recomendado_max"],
                                                          ig["texto_principal"], st["texto_principal"])]}
    return {"plataforma": plataforma, "pecas": pecas, "limites": limites, "export": PLANOS[plataforma]["export"]}


def contar(texto):
    """Characters as the ad platforms count them: NFC, and a wide (CJK) character counts 2."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
               for c in unicodedata.normalize("NFC", texto))


def conferir(textos, plataforma, path=None):
    """Problems of the textos.json object (empty list = ok): fields, counts, length, URL."""
    if not isinstance(textos, dict):
        return ["textos.json is not a JSON object"]
    limites = plano(plataforma, path)["limites"]
    problemas = []
    sobra = sorted(set(textos) - set(limites) - {"plataforma", "url"})
    if sobra:
        problemas.append("unknown fields: %s" % ", ".join(sobra))
    if textos.get("plataforma") != plataforma:
        problemas.append("plataforma must be %r" % plataforma)
    url = textos.get("url")
    if not isinstance(url, str) or len(url) > 2000 or not RE_URL.match(url):
        problemas.append("url must start with https:// and have no space")
    for campo, (minimo, maximo, chars) in limites.items():
        lista = textos.get(campo, [] if campo == "caminhos" else None)
        if not isinstance(lista, list):
            problemas.append("%s: missing (a list of %d to %d)" % (campo, minimo, maximo))
            continue
        if not minimo <= len(lista) <= maximo:
            problemas.append("%s: %d items (need %d to %d)" % (campo, len(lista), minimo, maximo))
        vistos = set()
        for i, t in enumerate(lista, 1):
            if not isinstance(t, str) or not t.strip():
                problemas.append("%s %d: empty" % (campo, i))
                continue
            if t != t.strip() or any(unicodedata.category(c)[0] == "C" for c in t):
                problemas.append("%s %d: spaces at the ends or a control character" % (campo, i))
            if t.startswith(FORMULA):
                problemas.append("%s %d: starts with %s" % (campo, i, t[0]))
            if campo == "caminhos" and " " in t:
                problemas.append("caminhos %d: no spaces in a path" % i)
            if contar(t) > chars:
                problemas.append("%s %d: %d characters (max %d): %s" % (campo, i, contar(t), chars, t))
            if t.casefold() in vistos:
                problemas.append("%s %d: repeated" % (campo, i))
            vistos.add(t.casefold())
    return problemas


def _csv(cols, linhas):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(cols)
    for linha in linhas:
        w.writerow([linha.get(c, "") for c in cols])
    return buf.getvalue()


def planilha(textos, plataforma, trabalho_id, path=None):
    """Text of the sheet for already-checked texts. Names come from the work id, never from the session."""
    if not RE_ID.match(trabalho_id or ""):
        raise ValueError("work id must be 12 hex characters")
    campanha, grupo = "Estudio %s" % trabalho_id, "Grupo %s" % trabalho_id
    p = PAUSADO[plataforma]
    if plataforma == "google":
        anuncio = {"Campaign": campanha, "Campaign Status": p, "Ad Group": grupo, "Ad Group Status": p,
                   "Ad type": "Responsive search ad", "Status": p, "Final URL": textos["url"]}
        anuncio.update({"Headline %d" % i: t for i, t in enumerate(textos["titulos"], 1)})
        anuncio.update({"Description %d" % i: t for i, t in enumerate(textos["descricoes"], 1)})
        anuncio.update({"Path %d" % i: t for i, t in enumerate(textos.get("caminhos") or [], 1)})
        return _csv(GOOGLE_COLS, [{"Campaign": campanha, "Campaign Type": "Search", "Campaign Status": p},
                                  {"Campaign": campanha, "Campaign Status": p, "Ad Group": grupo, "Ad Group Status": p},
                                  anuncio])
    tit, corpo = textos["titulos"], textos["textos_principais"]
    imagem = plano(plataforma, path)["pecas"][0]["nome"]
    return _csv(META_COLS, [{"Campaign Name": campanha, "Campaign Status": p, "Ad Set Name": grupo,
                             "Ad Set Run Status": p, "Ad Name": "Anuncio %d" % (i + 1), "Ad Status": p,
                             "Title": tit[i % len(tit)], "Body": corpo[i % len(corpo)], "Link": textos["url"],
                             "Image File Name": imagem} for i in range(max(len(tit), len(corpo)))])


def ler_planilha(texto, plataforma, path=None):
    """Problems of a sheet read back (empty = ok): exact header, every status Paused, texts within limits."""
    linhas = list(csv.reader(io.StringIO(texto)))
    cols = GOOGLE_COLS if plataforma == "google" else META_COLS
    if not linhas or linhas[0] != cols:
        return ["header is not the expected one"]
    problemas = []
    limites = plano(plataforma, path)["limites"]
    textos = {"google": {"Headline": "titulos", "Description": "descricoes", "Path": "caminhos"},
              "meta": {"Title": "titulos", "Body": "textos_principais"}}[plataforma]
    for n, linha in enumerate(linhas[1:], 2):
        if len(linha) != len(cols):
            problemas.append("line %d: %d columns" % (n, len(linha)))
            continue
        d = dict(zip(cols, linha))
        for c in STATUS_COLS[plataforma]:
            if d[c] not in ("", PAUSADO[plataforma]) or (c == STATUS_COLS[plataforma][0] and d[c] == ""):
                problemas.append("line %d: %s is %r, not %s" % (n, c, d[c], PAUSADO[plataforma]))
        for c, v in d.items():
            campo = textos.get(c.rsplit(" ", 1)[0] if plataforma == "google" else c)
            if campo and v and contar(v) > limites[campo][2]:
                problemas.append("line %d: %s over %d characters" % (n, c, limites[campo][2]))
    for c in STATUS_COLS[plataforma]:  # campaign, ad group/ad set and ad: each one present and paused
        if not any(dict(zip(cols, x)).get(c) == PAUSADO[plataforma] for x in linhas[1:]):
            problemas.append("no row sets %s" % c)
    return problemas


class _Texto(html.parser.HTMLParser):
    """Visible text of a piece (and whether it sits inside #safezone) and its picture tags."""
    VAZIOS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pilha, self.textos, self.figuras = [], [], []

    def handle_starttag(self, tag, attrs):
        if tag in FIGURAS:
            self.figuras.append(tag)
        if tag not in self.VAZIOS:
            self.pilha.append((tag, dict(attrs).get("id")))

    def handle_endtag(self, tag):
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                del self.pilha[i:]
                break

    def handle_data(self, data):
        if data.strip() and not any(t in ("style", "head", "title", "script") for t, _ in self.pilha):
            self.textos.append((data.strip()[:40], any(i == "safezone" for _, i in self.pilha)))


def checar_peca(fonte, plataforma, largura, altura):
    """Problems the browser check cannot see (empty = ok): a Google piece has no text, logo, assets/ or <img>;
    a 9:16 piece keeps every text inside #safezone (top 14% and bottom 20% free, clipped)."""
    if plataforma != "google" and altura * 9 != largura * 16:
        return []
    caminho = os.path.join(fonte, "index.html")
    if os.path.islink(caminho) or not os.path.isfile(caminho) or os.path.getsize(caminho) > 1024 * 1024:
        return ["missing index.html"]
    texto = qa_imagem.read_text(caminho)
    p = _Texto()
    try:
        p.feed(texto)
        p.close()
    except Exception as exc:  # noqa: B902 - the 3.9 parser can raise on a broken declaration
        return ["cannot read index.html: %s" % type(exc).__name__]
    css = ["CSS content adds text"] if RE_CSS_TEXTO.search(texto) else []
    if plataforma == "google":
        logo = ["assets/ folder (no logo on a Google image)"] if os.path.lexists(os.path.join(fonte, "assets")) \
            else []
        return (["text on the image: %s" % t for t, _ in p.textos] + css + logo
                + ["<%s> on the image (no logo or picture)" % t for t in p.figuras])[:MAX_PROBLEMAS]
    problemas = ["text outside #safezone: %s" % t for t, dentro in p.textos if not dentro] + css
    regras = RE_SAFEZONE.findall(texto)
    decl = {d for d in re.sub(r"\s+", "", regras[0]).lower().split(";") if d} if len(regras) == 1 else set()
    if not SAFEZONE <= decl or len(re.findall(r"safezone", texto, re.I)) != 2:
        problemas.append("#safezone must be one rule with %s, and one element" % ";".join(sorted(SAFEZONE)))
    if re.search(r"position\s*:\s*fixed|!\s*important", texto, re.I):
        problemas.append("position:fixed or !important can move text out of #safezone")
    return problemas[:MAX_PROBLEMAS]


def ler_textos(pasta):
    """(object, problem) of <pasta>/textos.json: a small plain file, never a link."""
    caminho = os.path.join(pasta, "textos.json")
    if os.path.islink(caminho) or not os.path.isfile(caminho):
        return None, "missing textos.json"
    if os.path.getsize(caminho) > 64 * 1024:
        return None, "textos.json too big"
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f), None
    except (OSError, ValueError, RecursionError) as exc:
        return None, "cannot read textos.json: %s" % exc


def exportar(pasta, plataforma):
    """(ok, problems). Writes export/<sheet> only when the texts pass; a stale sheet is removed first."""
    destino = os.path.join(pasta, "export", PLANOS[plataforma]["export"])
    if os.path.lexists(destino):
        os.remove(destino)
    textos, erro = ler_textos(pasta)
    problemas = [erro] if erro else conferir(textos, plataforma)
    if problemas:
        return False, problemas
    texto = planilha(textos, plataforma, os.path.basename(os.path.realpath(pasta)))
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    tmp = destino + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(texto)
    os.replace(tmp, destino)
    return True, []


def conferir_export(pasta, plataforma, textos):
    """Problems of the sheet on disk: it must be exactly what planilha() makes from textos.json."""
    caminho = os.path.join(pasta, "export", PLANOS[plataforma]["export"])
    if os.path.islink(caminho) or not os.path.isfile(caminho) or os.path.getsize(caminho) > 256 * 1024:
        return ["missing export/%s (run --exportar)" % PLANOS[plataforma]["export"]]
    with open(caminho, encoding="utf-8", newline="") as f:
        texto = f.read()
    if texto != planilha(textos, plataforma, os.path.basename(os.path.realpath(pasta))):
        return ["export/%s is not the one made from textos.json (run --exportar again)" % PLANOS[plataforma]["export"]]
    return ler_planilha(texto, plataforma)


def final(pasta, plataforma):
    """Every planned piece at its own size, then the texts and the sheet. PRONTO only if all pass."""
    pecas = []
    for p in plano(plataforma)["pecas"]:
        base = os.path.join(pasta, p["id"])
        rep = qa_imagem.run(os.path.join(base, "fonte"), os.path.join(base, "snap", qa_imagem.STILL), None,
                            p["largura"], p["altura"], snapshot=True)
        layout = checar_peca(os.path.join(base, "fonte"), plataforma, p["largura"], p["altura"])
        rep["checks"].append(qa_imagem.result("sem_texto" if plataforma == "google" else "zona_segura",
                                              not layout, layout or ["ok"]))
        rep["ok"] = all(c["ok"] for c in rep["checks"])
        pecas.append({"peca": p["id"], "tamanho": "%dx%d" % (p["largura"], p["altura"]), "ok": rep["ok"],
                      "failed": [c["name"] for c in rep["checks"] if not c["ok"]], "checks": rep["checks"]})
    textos, erro = ler_textos(pasta)
    problemas = [erro] if erro else conferir(textos, plataforma)
    export = [] if problemas else conferir_export(pasta, plataforma, textos)
    verdes = sum(1 for p in pecas if p["ok"])
    ok = verdes == len(pecas) and not problemas and not export
    if ok:
        linha = "PRONTO: %d de %d pecas verdes, textos e planilha ok" % (verdes, len(pecas))
    else:
        why = ["%s: %s" % (p["peca"], ", ".join(p["failed"])) for p in pecas if not p["ok"]]
        why += ["textos: %s" % "; ".join(problemas)] if problemas else []
        why += ["planilha: %s" % "; ".join(export)] if export else []
        linha = "PRECISA DO SEU OLHO: %d de %d verdes, %s" % (verdes, len(pecas), "; ".join(why))
    return {"ok": ok, "linha": linha[:2000], "plataforma": plataforma, "pecas": pecas, "textos": problemas,
            "planilha": export}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--plano", choices=sorted(PLANOS))
    p.add_argument("--exportar", metavar="FOLDER")
    p.add_argument("--final", metavar="FOLDER")
    p.add_argument("--plataforma", choices=sorted(PLANOS))
    p.add_argument("--out", help="--final: also write the report to this file")
    a = p.parse_args(argv)
    if a.plano:
        print(json.dumps(plano(a.plano), ensure_ascii=False, indent=1))
        return 0
    if not a.plataforma or not (a.exportar or a.final):
        p.error("use --plano, or --exportar/--final with --plataforma")
    if a.exportar:
        ok, problemas = exportar(a.exportar, a.plataforma)
        print(json.dumps({"ok": ok, "export": "export/" + PLANOS[a.plataforma]["export"] if ok else None,
                          "problemas": problemas}, ensure_ascii=False, indent=1))
        return 0 if ok else 1
    rep = final(a.final, a.plataforma)
    texto = json.dumps(rep, ensure_ascii=False, indent=1)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(texto + "\n")
    print(json.dumps({"ok": rep["ok"], "linha": rep["linha"]}, ensure_ascii=False))
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
