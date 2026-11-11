"""Discover the project's brand and write <raiz>/.tune-up/estudio/marca/ (marca.json, MARCA.md, assets/).

Deterministic, no network, no AI. Reads what the project already declares: CSS custom properties
in :root and @theme (also inside <style> of index.html), tailwind.config.*, index.html (title,
meta, logo <img>, icon), web manifest, a logo-named image file, and the name/description of
package.json, pyproject.toml, go.mod, Cargo.toml, composer.json (readers in marca_leitores.py).
Bounded walk (depth 4, 4000 entries) that skips node_modules, dist, vendor, build, .git and
friends; symlinks are not followed.

Every field is {valor, fonte: "arquivo:linha", confianca, travado}. confianca: alta (declared
under a brand name), media (inferred: meta, manifest, a plain CSS rule, a logo-named file whose
fonte is the file itself), baixa (library default such as shadcn/Tailwind, a package slug, an
icon), faltando (valor null, fonte null). Nothing is invented. A field with "travado": true in the
existing marca.json is kept as is on a new run. No brand color, font or logo at alta/media ->
"modo": "sem_marca" plus a declared neutral palette (paleta_neutra), which fills no field.

Usage: python3 -I scripts/descobrir_marca.py --projeto <pasta> [--saida <pasta>]
Exit code: 0 written, 2 refused (bad folder, unreadable marca.json: nothing overwritten).
Python 3.9+, standard library only. MARCA.md in Brazilian Portuguese.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import marca_leitores as ml  # noqa: E402

CAMPOS = ml.CAMPOS
IGNORAR = {"node_modules", "dist", "vendor", "build", "out", "coverage", "target", "__pycache__",
           ".git", ".tune-up", ".hyperframes", ".next", ".nuxt", ".svelte-kit", ".venv", "venv",
           ".cache", ".turbo", ".output"}
PROFUNDIDADE, MAX_ENTRADAS, MAX_BYTES, MAX_LOGO = 4, 4000, 1_000_000, 5_000_000
TAILWIND = {"tailwind.config.js", "tailwind.config.cjs", "tailwind.config.mjs", "tailwind.config.ts"}
MANIFESTOS = {"manifest.json", "site.webmanifest", "manifest.webmanifest"}
PACOTES = {"package.json", "pyproject.toml", "go.mod", "Cargo.toml", "composer.json"}
RE_LOGO = re.compile(r"^(logo|brand|marca)[\w.-]*\.(svg|png|webp|jpe?g)$", re.I)
PALETA_NEUTRA = {"cores.bg": "#FFFFFF", "cores.surface": "#F4F4F5", "cores.primary": "#18181B",
                 "cores.text": "#18181B", "cores.accent": "#52525B",
                 "fontes.heading": "system-ui, sans-serif", "fontes.body": "system-ui, sans-serif"}


def _ler(caminho):
    try:
        if os.path.getsize(caminho) > MAX_BYTES:
            return None
        with open(caminho, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def arquivos(raiz):
    """(depth, relative path, path) of files under raiz, shallow first then by path; bounded; no symlinks."""
    achados, entradas = [], 0
    for pasta, dirs, nomes in os.walk(raiz):
        prof = 0 if pasta == raiz else ml.rel(pasta, raiz).count("/") + 1
        dirs[:] = sorted(d for d in dirs if d not in IGNORAR and prof + 1 < PROFUNDIDADE
                         and not os.path.islink(os.path.join(pasta, d)))
        for n in sorted(nomes):
            entradas += 1
            if entradas > MAX_ENTRADAS:
                return sorted(achados)
            c = os.path.join(pasta, n)
            if not os.path.islink(c):
                achados.append((prof, ml.rel(c, raiz), c))
    return sorted(achados)


def descobrir(raiz):
    """{campo: {valor, fonte, confianca, travado}} for every CAMPOS key."""
    ach = ml.Achados()
    lista = arquivos(raiz)
    for _, arq, c in lista:
        nome = os.path.basename(c)
        baixo = nome.lower()
        if not (baixo.endswith(".css") or baixo == "index.html" or nome in TAILWIND | MANIFESTOS | PACOTES):
            continue
        texto = _ler(c)
        if texto is None:
            continue
        if baixo.endswith(".css"):
            ml.ler_css(ach, texto, arq)
        elif baixo == "index.html":
            ml.ler_html(ach, texto, arq, c, raiz)
        elif nome in TAILWIND:
            ml.ler_tailwind(ach, texto, arq)
        elif nome in MANIFESTOS:
            ml.ler_manifesto(ach, texto, arq, c, raiz)
        else:
            ml.ler_pacote(ach, texto, arq, nome)
    for _, arq, c in lista:
        if RE_LOGO.match(os.path.basename(c)) and ml.dentro(c, raiz):
            ach.add("logo", arq, arq, "media")
    return {k: ach.melhor(k) for k in CAMPOS}


DO_DONO = ("fotos", "tom", "letras_do_projeto")  # written by the studio screen; a new discovery keeps them


def ler_existente(saida, tudo=False):
    """Fields of an existing marca.json ({} if there is none), or the whole object with tudo=True.
    Raises ValueError if present but unreadable."""
    alvo = os.path.join(saida, "marca.json")
    if not os.path.lexists(alvo):
        return {}
    if os.path.islink(alvo):
        raise ValueError("marca.json é um atalho")
    try:
        with open(alvo, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError("marca.json ilegível (%s)" % e.__class__.__name__)
    campos = d.get("campos") if isinstance(d, dict) else None
    if not isinstance(campos, dict):
        raise ValueError("marca.json sem 'campos'")
    return d if tudo else campos


def mesclar(novos, existentes):
    """Locked fields (travado true, with valor/fonte/confianca) win over the new discovery."""
    saida = dict(novos)
    for k, v in existentes.items():
        if k in CAMPOS and isinstance(v, dict) and v.get("travado") is True and \
                {"valor", "fonte", "confianca"} <= set(v):
            saida[k] = {"valor": v["valor"], "fonte": v["fonte"], "confianca": v["confianca"], "travado": True}
    return saida


def modo(campos):
    marca = [k for k in CAMPOS if k.startswith(("cores.", "fontes.")) or k == "logo"]
    tem = any(campos[k]["valor"] is not None and (campos[k]["travado"] or campos[k]["confianca"] in ("alta", "media"))
              for k in marca)
    return "marca" if tem else "sem_marca"


def _gravar(caminho, texto):
    if os.path.islink(caminho):
        raise OSError("%s é um atalho; não gravei" % os.path.basename(caminho))
    tmp = caminho + ".tmp"
    if os.path.lexists(tmp):
        os.remove(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)
    os.replace(tmp, caminho)


def copiar_logo(raiz, saida, logo):
    """assets/logo.<ext> mirrors the logo field; stale copies go. Returns the asset path or None.

    A locked logo whose file is gone keeps its old copy (the lock is the owner's word)."""
    assets = os.path.join(saida, "assets")
    if os.path.islink(assets):
        raise OSError("assets é um atalho; não gravei")
    os.makedirs(assets, exist_ok=True)
    valor = logo["valor"] if isinstance(logo["valor"], str) else None
    origem = os.path.join(raiz, *valor.split("/")) if valor and ".." not in valor.split("/") else None
    ok = bool(origem) and os.path.isfile(origem) and not os.path.islink(origem) and ml.dentro(origem, raiz) \
        and origem.lower().endswith(ml.EXT_LOGO) and os.path.getsize(origem) <= MAX_LOGO
    if not ok and logo["travado"]:
        velhas = sorted(n for n in os.listdir(assets) if n.lower().startswith("logo."))
        return "assets/" + velhas[0] if velhas else None
    for n in os.listdir(assets):
        if n.lower().startswith("logo."):
            os.remove(os.path.join(assets, n))
    if not ok:
        return None
    destino = os.path.join(assets, "logo" + os.path.splitext(origem)[1].lower())
    shutil.copyfile(origem, destino)
    return "assets/" + os.path.basename(destino)


def marca_md(d):
    linhas = ["# Marca do projeto", "", "Gerado por `descobrir_marca.py` em %s. Nada aqui foi inventado: "
              "cada valor cita o arquivo e a linha de onde saiu." % d["gerado_em"], ""]
    if d["modo"] == "sem_marca":
        linhas += ["**Modo sem marca.** Não achei cor, fonte nem logo da marca neste projeto. As peças usam a "
                   "paleta neutra abaixo até o dono informar a marca. A paleta neutra NÃO é a marca.", ""]
    linhas += ["| Campo | Valor | Confiança | Fonte | Travado |", "| --- | --- | --- | --- | --- |"]
    for k in CAMPOS:
        c = d["campos"][k]
        valor = "-" if c["valor"] is None else str(c["valor"]).replace("|", "\\|").replace("\n", " ")
        linhas.append("| %s | %s | %s | %s | %s |" % (k, valor, c["confianca"], c["fonte"] or "-",
                                                      "sim" if c["travado"] else "não"))
    if d.get("logo_copia"):
        linhas += ["", "Cópia do logo: `%s`." % d["logo_copia"]]
    if d["modo"] == "sem_marca":
        linhas += ["", "## Paleta neutra (declarada, não descoberta)", ""]
        linhas += ["- %s: %s" % (k, v) for k, v in PALETA_NEUTRA.items()]
    linhas += ["", "Confiança: alta = declarado com nome de marca; media = deduzido (meta, manifest, regra CSS, "
               "arquivo chamado logo); baixa = padrão de biblioteca, nome de pacote ou ícone; faltando = não achei.",
               "Campo com `\"travado\": true` no marca.json não muda quando a descoberta roda de novo.", ""]
    return "\n".join(linhas)


def rodar(raiz, saida=None):
    raiz = os.path.abspath(raiz)
    if not os.path.isdir(raiz):
        raise ValueError("pasta do projeto não existe")
    saida = os.path.abspath(saida or os.path.join(raiz, ".tune-up", "estudio", "marca"))
    antes = ler_existente(saida, tudo=True)
    campos = mesclar(descobrir(raiz), antes.get("campos") or {})
    os.makedirs(saida, exist_ok=True)
    d = {"versao": 1, "gerado_em": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "modo": modo(campos), "campos": campos}
    d.update((k, antes[k]) for k in DO_DONO if k in antes)
    d["logo_copia"] = copiar_logo(raiz, saida, campos["logo"])
    if d["modo"] == "sem_marca":
        d["paleta_neutra"] = dict(PALETA_NEUTRA)
    _gravar(os.path.join(saida, "marca.json"), json.dumps(d, ensure_ascii=False, indent=2) + "\n")
    _gravar(os.path.join(saida, "MARCA.md"), marca_md(d))
    return d


def main(argv=None):
    ap = argparse.ArgumentParser(description="Descobre a marca do projeto (sem rede, sem IA).")
    ap.add_argument("--projeto", required=True)
    ap.add_argument("--saida")
    a = ap.parse_args(argv)
    try:
        d = rodar(a.projeto, a.saida)
    except (ValueError, OSError) as e:
        print("recusado: %s (nada sobrescrito)" % e, file=sys.stderr)
        return 2
    faltando = [k for k in CAMPOS if d["campos"][k]["confianca"] == "faltando"]
    print("modo: %s; faltando: %s" % (d["modo"], ", ".join(faltando) or "nada"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
