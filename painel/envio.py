"""Envio de imagem para um módulo: POST /api/modulos/<id>/envio?destino=<chave>, corpo = bytes crus da imagem.

O módulo declara INFO["envios"] = {chave: {"pasta": "relativa a <dados>", "tipos": ["png", "jpeg", "webp"],
"max_bytes": N, "max_arquivos": N, "gancho": bool, "base"?: "dados" | "tune-up"}}. Sem declaração (ou chave
fora dela), 404. "base": "tune-up" põe a pasta em <raiz>/.tune-up em vez de <dados> (ex.: a marca do estúdio).
- Content-Length obrigatório e conferido contra max_bytes (teto global TETO) antes de ler qualquer byte;
  a leitura vai em blocos e nunca passa do tamanho declarado.
- O tipo vem dos BYTES (assinatura + cabeçalho com largura e altura), nunca da extensão nem do Content-Type.
  PNG percorre os chunks até o IEND no fim; JPEG precisa de um SOF; WebP precisa do RIFF coerente.
  Lado acima de MAX_LADO ou mais de MAX_PIXELS pixels é recusado (bomba de descompressão).
- SVG é recusado: um validador estrito de XML/SVG não cabe pequeno, e a rota de mídia não serve SVG.
- Nome dado pelo servidor: 16 letras do sha256 + extensão. Mesmo conteúdo = mesmo nome: não duplica.
- Pasta: cada pedaço é criado ou conferido sem atalho (lstat), e o realpath final tem de ser exatamente
  <base real>/<pasta>. Escreve num temporário oculto com O_CREAT|O_EXCL|O_NOFOLLOW e troca com os.replace.
- Depois: com "gancho": true, chama agir(ctx, "envio.recebido", {"destino", "caminho"}) (falha vira aviso:
  o arquivo já está gravado) e sempre apaga o cache da tela.
Python 3.9, só biblioteca padrão.
"""
import hashlib
import os
import re
import secrets
import stat
import struct
import threading

import midia
import modulos

TETO = 8 * 1024 * 1024
MAX_LADO = 8192
MAX_PIXELS = 40 * 1000 * 1000
MAX_ARQUIVOS = 500
BLOCO = 64 * 1024
RE_CHAVE = re.compile(r"^[a-z0-9_-]{1,40}$")
EXT = {"png": ".png", "jpeg": ".jpg", "webp": ".webp"}
SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
_lock = threading.Lock()  # contagem + troca do arquivo: dois envios juntos não passam do limite


class Recusa(Exception):
    def __init__(self, codigo, mensagem):
        Exception.__init__(self, mensagem)
        self.codigo, self.mensagem = codigo, mensagem


def _png(b):
    if len(b) < 33 or b[12:16] != b"IHDR" or struct.unpack(">I", b[8:12])[0] != 13:
        return None
    w, h = struct.unpack(">II", b[16:24])
    pos = 8
    while pos + 12 <= len(b):  # cada chunk: tamanho, nome, dados, crc; o último é IEND e termina o arquivo
        n, nome = struct.unpack(">I", b[pos:pos + 4])[0], b[pos + 4:pos + 8]
        pos += 12 + n
        if nome == b"IEND":
            return (w, h) if pos == len(b) else None
    return None


def _jpeg(b):
    pos = 2
    while pos + 4 <= len(b):
        if b[pos] != 0xFF:
            return None
        m = b[pos + 1]
        if m == 0xFF:  # enchimento
            pos += 1
            continue
        if m in (0x01,) or 0xD0 <= m <= 0xD8:
            pos += 2
            continue
        if m in (0xD9, 0xDA):  # fim ou começo da imagem antes do tamanho
            return None
        n = struct.unpack(">H", b[pos + 2:pos + 4])[0]
        if n < 2:
            return None
        if m in SOF:
            if pos + 9 > len(b) or n < 7:
                return None
            h, w = struct.unpack(">HH", b[pos + 5:pos + 9])
            return w, h
        pos += 2 + n
    return None


def _webp(b):
    if len(b) < 30 or struct.unpack("<I", b[4:8])[0] + 8 > len(b):
        return None
    chunk = b[12:16]
    if chunk == b"VP8 " and b[23:26] == b"\x9d\x01\x2a":
        w, h = struct.unpack("<HH", b[26:30])
        return w & 0x3FFF, h & 0x3FFF
    if chunk == b"VP8L" and b[20] == 0x2F:
        v = struct.unpack("<I", b[21:25])[0]
        return (v & 0x3FFF) + 1, ((v >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":
        return (int.from_bytes(b[24:27], "little") + 1, int.from_bytes(b[27:30], "little") + 1)
    return None


def tipo_dos_bytes(b):
    """(tipo, largura, altura) lido do cabeçalho, ou None. Nunca olha nome nem Content-Type."""
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        tipo, wh = "png", _png(b)
    elif b[:3] == b"\xff\xd8\xff":
        tipo, wh = "jpeg", _jpeg(b)
    elif b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        tipo, wh = "webp", _webp(b)
    else:
        return None
    return (tipo,) + wh if wh and wh[0] > 0 and wh[1] > 0 else None


def declaracao(mod, chave):
    """A entrada de INFO["envios"][chave] já conferida, ou Recusa(404/500)."""
    i = getattr(mod, "INFO", None)
    envios = i.get("envios") if isinstance(i, dict) else None
    if not isinstance(chave, str) or not RE_CHAVE.match(chave) or not isinstance(envios, dict) \
            or not isinstance(envios.get(chave), dict):
        raise Recusa(404, "Esta tela não recebe esse arquivo.")
    d = envios[chave]
    partes, base = midia.entrada(d)
    tipos = d.get("tipos")
    num = [d.get(k) for k in ("max_bytes", "max_arquivos")]
    if not partes or not isinstance(tipos, list) or not tipos or any(t not in EXT for t in tipos) \
            or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in num):
        raise Recusa(500, "Esta tela está incompleta (INFO[\"envios\"] inválido).")
    return {"partes": partes, "base": base, "tipos": set(tipos), "max_bytes": min(num[0], TETO),
            "max_arquivos": min(num[1], MAX_ARQUIVOS), "gancho": d.get("gancho") is True}


def tamanho_declarado(headers, teto):
    if headers.get("Transfer-Encoding"):
        raise Recusa(411, "Mande o tamanho do arquivo.")
    valor = (headers.get("Content-Length") or "").strip()
    if not valor:
        raise Recusa(411, "Mande o tamanho do arquivo.")
    if not valor.isdigit() or len(valor) > 12 or int(valor) == 0:
        raise Recusa(400, "Tamanho do arquivo inválido.")
    if int(valor) > teto:
        raise Recusa(413, "Arquivo grande demais (até %d MB)." % max(1, teto // (1024 * 1024)))
    return int(valor)


def ler(rfile, tamanho):
    buf = bytearray()
    while len(buf) < tamanho:
        pedaco = rfile.read(min(BLOCO, tamanho - len(buf)))
        if not pedaco:
            raise Recusa(400, "O arquivo chegou pela metade.")
        buf += pedaco
    return bytes(buf)


def pasta_segura(dados, partes):
    """Cria ou confere cada pedaço sem seguir atalho; o realpath final tem de ser <dados>/<partes>."""
    atual = os.path.realpath(dados)
    if not os.path.isdir(atual):
        raise Recusa(404, "Esta tela não recebe esse arquivo.")
    for p in partes:
        atual = os.path.join(atual, p)
        try:
            os.mkdir(atual, 0o755)
        except FileExistsError:
            pass
        st = os.lstat(atual)
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise Recusa(409, "A pasta de destino não é uma pasta comum.")
    if os.path.normcase(os.path.realpath(atual)) != os.path.normcase(atual):
        raise Recusa(409, "A pasta de destino não é uma pasta comum.")
    return atual


def _contar(pasta, tipos):
    exts = {EXT[t] for t in tipos}
    return sum(1 for n in os.listdir(pasta) if not n.startswith(".")
               and os.path.splitext(n)[1] in exts and os.path.isfile(os.path.join(pasta, n)))


def gravar(pasta, nome, corpo, decl):
    """True se gravou, False se já existia igual. Limite de arquivos conferido na mesma trava."""
    final = os.path.join(pasta, nome)
    with _lock:
        try:
            st = os.lstat(final)
        except FileNotFoundError:
            st = None
        if st is not None:
            if not stat.S_ISREG(st.st_mode):
                raise Recusa(409, "Já existe outra coisa com esse nome no destino.")
            return False
        if _contar(pasta, decl["tipos"]) >= decl["max_arquivos"]:
            raise Recusa(409, "Limite de %d arquivos neste destino. Apague algum antes." % decl["max_arquivos"])
        tmp = os.path.join(pasta, ".envio-%s.tmp" % secrets.token_hex(8))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
                     | getattr(os, "O_BINARY", 0), 0o644)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(corpo)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, final)
        finally:
            if os.path.lexists(tmp):
                os.unlink(tmp)
    return True


def _c_da_midia(mod, partes, base):
    """`c` para GET .../arquivo, ou None se a pasta não está em INFO["midia"] (com a mesma base)."""
    decl = getattr(mod, "INFO", {}).get("midia")
    for d in decl if isinstance(decl, list) else [decl]:
        p, b = midia.entrada(d)
        if p and b == base and partes[:len(p)] == p:
            return "/".join(partes if isinstance(decl, list) else partes[len(p):])
    return None


def _limpar_cache(mid):
    with modulos._lock:  # mesma regra do agir(): montar() em voo não grava o cache velho
        modulos._geracao[mid] = modulos._geracao.get(mid, 0) + 1
        modulos._cache.pop(mid, None)


def receber(cfg, mid, chave, headers, rfile, tempo=modulos.TEMPO_LIMITE):
    """(código, corpo). Antes de ler o corpo: módulo, declaração e tamanho. Recusa sem ler = feche a conexão."""
    try:
        mod = modulos.carregar(cfg, mid)
    except modulos.ErroModulo as e:
        return e.codigo, {"erro": e.mensagem}
    try:
        decl = declaracao(mod, chave)
        dados = midia.base_real(cfg, decl["base"])
        if not dados:
            raise Recusa(404, "Esta tela não recebe esse arquivo.")
        corpo = ler(rfile, tamanho_declarado(headers, decl["max_bytes"]))
        achado = tipo_dos_bytes(corpo)
        if achado is None or achado[0] not in decl["tipos"]:
            raise Recusa(415, "Tipo de arquivo não aceito aqui (%s)." % ", ".join(sorted(decl["tipos"])))
        tipo, w, h = achado
        if w > MAX_LADO or h > MAX_LADO or w * h > MAX_PIXELS:
            raise Recusa(415, "Imagem grande demais (até %d pixels de lado)." % MAX_LADO)
        nome = hashlib.sha256(corpo).hexdigest()[:16] + EXT[tipo]
        novo = gravar(pasta_segura(dados, decl["partes"]), nome, corpo, decl)
    except Recusa as e:
        return e.codigo, {"erro": e.mensagem}
    partes = decl["partes"] + [nome]
    caminho, avisos = "/".join(partes), []
    if novo and decl["gancho"] and callable(getattr(mod, "agir", None)):
        try:
            modulos._rodar_agir(mod, modulos.contexto(cfg), mid, "envio.recebido",
                                {"destino": chave, "caminho": caminho}, tempo)
        except modulos.ErroModulo as e:
            avisos.append("O arquivo foi guardado, mas a tela não terminou de registrá-lo (%s)." % e.mensagem)
    _limpar_cache(mid)
    return (201 if novo else 200), {"ok": True, "caminho": caminho, "c": _c_da_midia(mod, partes, decl["base"]), "tipo": tipo,
                                    "largura": w, "altura": h, "repetido": not novo, "avisos": avisos}
