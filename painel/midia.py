"""Mídia de módulo: GET /api/modulos/<id>/arquivo?c=<caminho relativo>.

O módulo declara INFO["midia"] = "pasta" (relativa ao <dados> do módulo) ou uma lista de pastas, e então
`c` começa pelo nome da pasta (ex.: "aprovados/x.png"). Sem declaração, 404. Uma pasta da lista pode ser
{"pasta": "a/b", "base": "tune-up"}: relativa a <raiz>/.tune-up em vez de <dados> (ex.: a marca do estúdio).
- `c` é relativo a essa pasta; nada de '..', '.', segmento que começa com ponto, barra
  invertida, byte nulo, caminho absoluto ou letra de unidade;
- o caminho real (realpath) tem de ficar dentro da pasta real, que fica dentro de <dados> (ou da base declarada);
- abre com O_NOFOLLOW (onde existe) e confere com fstat que é arquivo comum;
- só png, jpg/jpeg, webp, mp4 e webm; .csv só dentro de uma pasta que o módulo lista em INFO["baixar"]
  (sempre um nome de INFO["midia"]) e sai como download (text/csv + Content-Disposition: attachment);
- Range: um intervalo dá 206 com Content-Range; fora do arquivo dá 416; sintaxe que não
  entendemos ou vários intervalos dão 200 com o arquivo inteiro (RFC 9110 deixa ignorar).
O arquivo vai em blocos, nunca inteiro na memória. Python 3.9, só biblioteca padrão.
"""
import os
import re
import stat

import modulos

TIPOS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
         ".mp4": "video/mp4", ".webm": "video/webm"}
BAIXAR = {".csv": "text/csv; charset=utf-8"}  # nunca mostrado no navegador: sai como anexo
RE_NOME_ANEXO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$")
BLOCO = 64 * 1024
MAX_C = 400
BASES = ("dados", "tune-up")
RE_RANGE = re.compile(r"^bytes=(\d{0,18})-(\d{0,18})$")


class Aberto:
    """Arquivo pronto para enviar: codigo (200/206), tipo, inicio, tamanho do trecho, total."""

    def __init__(self, f, codigo, tipo, inicio, tamanho, total, anexo=None):
        self.f, self.codigo, self.tipo = f, codigo, tipo
        self.inicio, self.tamanho, self.total, self.anexo = inicio, tamanho, total, anexo

    def cabecalhos(self):
        cab = {"Accept-Ranges": "bytes"}
        if self.anexo:
            cab["Content-Disposition"] = 'attachment; filename="%s"' % self.anexo
        if self.codigo == 206:
            cab["Content-Range"] = "bytes %d-%d/%d" % (self.inicio, self.inicio + self.tamanho - 1, self.total)
        return cab

    def blocos(self):
        self.f.seek(self.inicio)
        falta = self.tamanho
        while falta > 0:
            pedaco = self.f.read(min(BLOCO, falta))
            if not pedaco:
                return  # o arquivo encolheu no meio: o cliente vê a resposta curta
            falta -= len(pedaco)
            yield pedaco

    def fechar(self):
        self.f.close()


def _segmentos_ok(texto):
    if not isinstance(texto, str) or not texto or len(texto) > MAX_C:
        return None
    if "\x00" in texto or "\\" in texto or ":" in texto or texto.startswith("/"):
        return None
    partes = texto.split("/")
    if any(not p or p.startswith(".") for p in partes):
        return None  # vazio (//), '.', '..' e arquivo ou pasta oculta
    return partes


def entrada(d):
    """(partes, base) de uma pasta de INFO["midia"] ou INFO["envios"]; partes None se a declaração é ruim."""
    if isinstance(d, dict):
        base = d.get("base", "dados")
        return (_segmentos_ok(d.get("pasta")) if base in BASES else None), base
    return _segmentos_ok(d), "dados"


def base_real(cfg, base):
    """Pasta da base ("dados" = <dados> do módulo; "tune-up" = <raiz>/.tune-up), ou "" se não há."""
    ctx = modulos.contexto(cfg)
    if base == "tune-up":
        return os.path.join(ctx["raiz"], ".tune-up") if ctx.get("raiz") else ""
    return ctx["dados"] if base == "dados" else ""


def _dentro(real, base):
    return real.startswith(base.rstrip(os.sep) + os.sep)


def pasta_do_modulo(cfg, mid, c=None):
    """(caminho real da pasta de mídia, partes de `c` dentro dela) ou ErroModulo(404). INFO["midia"] é uma
    pasta (`c` relativo a ela) ou uma lista de pastas (`c` começa pelo nome de uma delas). Partes None: `c` ruim."""
    mod = modulos.carregar(cfg, mid)
    decl = getattr(mod, "INFO", None)
    decl = decl.get("midia") if isinstance(decl, dict) else None
    partes_c = _segmentos_ok(c)
    if isinstance(decl, list):  # a primeira pasta da lista que é começo de `c` (e sobra um nome de arquivo)
        lista = [e for e in (entrada(d) for d in decl) if e[0]]
        achada = next((e for e in lista if partes_c and len(partes_c) > len(e[0]) and partes_c[:len(e[0])] == e[0]),
                      None)
        partes_c = partes_c[len(achada[0]):] if achada else None
        partes, base = achada or (lista[0] if lista else (None, None))
    else:
        partes, base = entrada(decl)
    dados = base_real(cfg, base) if partes else ""
    if not partes or not dados:
        raise modulos.ErroModulo(404, "Esta tela não mostra arquivos.")
    base_dados = os.path.realpath(dados)
    pasta = os.path.realpath(os.path.join(base_dados, *partes))
    if not _dentro(pasta, base_dados) or not os.path.isdir(pasta):
        raise modulos.ErroModulo(404, "Esta tela não mostra arquivos.")
    return pasta, partes_c


def _baixavel(cfg, mid, c):
    """True se `c` começa por uma pasta de INFO["baixar"] (lista de nomes de pasta de mídia)."""
    decl = getattr(modulos.carregar(cfg, mid), "INFO", None)
    decl = decl.get("baixar") if isinstance(decl, dict) else None
    partes_c = _segmentos_ok(c) or []
    for d in decl if isinstance(decl, list) else []:
        p = _segmentos_ok(d)
        if p and len(partes_c) > len(p) and partes_c[:len(p)] == p:
            return True
    return False


def _intervalo(valor, total):
    """(inicio, fim) inclusivo, None = arquivo inteiro, ou "416"."""
    if not valor:
        return None
    m = RE_RANGE.match(valor.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None  # outra unidade, vários intervalos ou lixo: ignora o Range
    if not m.group(1):  # bytes=-N: os N últimos
        n = int(m.group(2))
        if n == 0 or total == 0:
            return "416"
        return max(0, total - n), total - 1
    inicio = int(m.group(1))
    fim = int(m.group(2)) if m.group(2) else total - 1
    if m.group(2) and fim < inicio:
        return None
    if inicio >= total:
        return "416"
    return inicio, min(fim, total - 1)


def abrir(cfg, mid, c, cab_range):
    """Aberto ou (codigo, corpo de erro, extra) com os cabeçalhos extras do erro."""
    try:
        pasta, partes = pasta_do_modulo(cfg, mid, c)
    except modulos.ErroModulo as e:
        return e.codigo, {"erro": e.mensagem}, {}
    ext = os.path.splitext(partes[-1])[1].lower() if partes else ""
    tipos = dict(TIPOS, **BAIXAR) if ext in BAIXAR and _baixavel(cfg, mid, c) else TIPOS
    if not partes or ext not in tipos:
        return 404, {"erro": "Arquivo não encontrado."}, {}
    anexo = (partes[-1] if RE_NOME_ANEXO.match(partes[-1]) else "arquivo" + ext) if ext in BAIXAR else None
    real = os.path.realpath(os.path.join(pasta, *partes))
    if not _dentro(real, pasta):
        return 404, {"erro": "Arquivo não encontrado."}, {}
    try:  # O_NOFOLLOW fecha a troca do último nome por atalho entre o realpath e o open;
        # O_NONBLOCK: FIFO com nome de mídia não prende a thread no open (o fstat abaixo recusa)
        fd = os.open(real, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
                     | getattr(os, "O_NONBLOCK", 0))
    except OSError:
        return 404, {"erro": "Arquivo não encontrado."}, {}
    f = os.fdopen(fd, "rb")
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            f.close()
            return 404, {"erro": "Arquivo não encontrado."}, {}
        total = st.st_size
        r = _intervalo(cab_range, total)
        if r == "416":
            f.close()
            return 416, {"erro": "Trecho fora do arquivo."}, {"Content-Range": "bytes */%d" % total}
        if r is None:
            return Aberto(f, 200, tipos[ext], 0, total, total, anexo)
        return Aberto(f, 206, tipos[ext], r[0], r[1] - r[0] + 1, total, anexo)
    except BaseException:
        f.close()
        raise
