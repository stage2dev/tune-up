"""Arquivos da tela: web/dist (build do React) ou um aviso simples sem a build.

- /assets/* com cache longo (o nome já traz o hash do build);
- arquivo que existe em web/dist é servido; qualquer outra rota cai no index.html
  (o roteador do React resolve);
- sem web/dist, a raiz mostra uma página curta pedindo `npm run build` (sem script);
- nada de '..', barra invertida, byte nulo ou atalho (symlink) que saia da pasta.
"""
import os
import posixpath
import urllib.parse

TIPOS = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8", ".map": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".ico": "image/x-icon", ".woff2": "font/woff2",
    ".woff": "font/woff", ".ttf": "font/ttf", ".txt": "text/plain; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}
CACHE_LONGO = "public, max-age=31536000, immutable"
SEM_CACHE = "no-store"
LIMITE = 16 * 1024 * 1024
SEM_BUILD = ("<!doctype html><html lang=\"pt-BR\"><meta charset=\"utf-8\"><title>Painel</title>"
             "<body style=\"font-family:system-ui;margin:2rem;max-width:40rem\"><h1>Painel</h1>"
             "<p>A tela ainda não foi gerada. Na pasta <code>web</code> do painel rode "
             "<code>npm install</code> e <code>npm run build</code>, depois recarregue.</p>"
             "<p>A API já responde em <code>/api/estado</code>.</p></body></html>").encode("utf-8")


def _dentro(caminho, raiz):
    real, base = os.path.realpath(caminho), os.path.realpath(raiz)
    return real.startswith(base.rstrip(os.sep) + os.sep)


def _ler(caminho):
    with open(caminho, "rb") as f:
        return f.read(LIMITE)


def resolver(caminho_url, web_dir):
    """(codigo, corpo, tipo, cache). 404 quando o pedido é inválido ou sai da pasta."""
    bruto = urllib.parse.unquote(caminho_url.split("?", 1)[0].split("#", 1)[0])
    if "\x00" in bruto or "\\" in bruto or not bruto.startswith("/"):
        return 404, None, None, None
    partes = [p for p in bruto.split("/") if p]
    if any(p in ("..", ".") or p.startswith(".") for p in partes):
        return 404, None, None, None
    index = os.path.join(web_dir, "index.html")
    if not os.path.isfile(index):  # sem build: aviso só na raiz
        if bruto not in ("/", "/index.html"):
            return 404, None, None, None
        return 200, SEM_BUILD, TIPOS[".html"], SEM_CACHE
    relativo = posixpath.normpath("/".join(partes)) if partes else ""
    if relativo:
        alvo = os.path.join(web_dir, *relativo.split("/"))
        if os.path.lexists(alvo):
            if not _dentro(alvo, web_dir) or not os.path.isfile(alvo):
                return 404, None, None, None
            ext = os.path.splitext(alvo)[1].lower()
            if ext not in TIPOS:
                return 404, None, None, None
            cache = CACHE_LONGO if partes[0] == "assets" else SEM_CACHE
            try:
                return 200, _ler(alvo), TIPOS[ext], cache
            except OSError:
                return 404, None, None, None
        if partes[0] == "assets" or os.path.splitext(partes[-1])[1]:
            return 404, None, None, None  # arquivo que não existe não vira página
    if not _dentro(index, web_dir):
        return 404, None, None, None
    try:
        return 200, _ler(index), TIPOS[".html"], SEM_CACHE
    except OSError:
        return 500, None, None, None
