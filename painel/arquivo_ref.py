"""Arquivo de módulo por referência: GET /api/modulos/<id>/arquivo?ref=<ref>.

O módulo expõe arquivo(ctx, ref) -> {"mime": str, "dados": bytes, "nome"?: str, "baixar"?: bool} e levanta
LookupError (KeyError) ou FileNotFoundError quando não acha. Serve dado pessoal (áudio, foto, documento de
uma conversa), então:
- exige Sec-Fetch-Site same-origin (sem o cabeçalho ou de outro site = 403), além do Host já conferido;
- `ref` opaca, até 200 letras de [A-Za-z0-9._:-], sem '..' nem ponto no começo: recusada antes do módulo;
- mime só da lista MIMES (fora = 415), até 25 MB (acima = 413);
- arquivo() roda numa thread com tempo limite; no máximo VAGAS de uma vez (cheio = 503, sem chamar o módulo);
- resposta com nosniff, Cache-Control private max-age=300, CSP sandbox; anexo (Content-Disposition com nome
  ASCII e filename* RFC 5987) quando `baixar` ou o mime é pdf/octet-stream;
- nada vai para disco nem para o registro; o texto da exceção do módulo nunca sai (pode trazer a ref).
Range de um intervalo dá 206 (o Safari só toca áudio assim). Python 3.9, só biblioteca padrão.
"""
import json
import re
import threading
import unicodedata
import urllib.parse

import midia
import modulos
from modulos_forma import ref_ok

MIMES = ("audio/ogg", "audio/mpeg", "audio/mp4", "audio/wav", "image/jpeg", "image/png", "image/webp",
         "application/pdf", "application/octet-stream")
SEMPRE_ANEXO = ("application/pdf", "application/octet-stream")
MAX_BYTES = 25 * 1024 * 1024
TEMPO_LIMITE = 20.0
VAGAS = 4
CSP = "default-src 'none'; sandbox"
_vagas = threading.BoundedSemaphore(VAGAS)
RE_LOG_REF = re.compile(r"([?&]ref=)[^&\s\"]*")


def sem_ref(texto):
    """Linha de registro sem o valor de ?ref= (a ref pode apontar para uma conversa)."""
    return RE_LOG_REF.sub(r"\1*", texto)


def _erro(codigo, msg, extra=None):
    corpo = json.dumps({"erro": msg}, ensure_ascii=False).encode("utf-8")
    return {"codigo": codigo, "corpo": corpo, "tipo": "application/json; charset=utf-8", "csp": CSP,
            "extra": extra or {}}


def nome_anexo(nome, mime):
    """Valor de Content-Disposition: filename ASCII limpo + filename* UTF-8 (RFC 5987/6266)."""
    nome = nome if isinstance(nome, str) else ""
    nome = "".join(c for c in nome if unicodedata.category(c)[0] != "C" and c not in '/\\"').strip(" .")[:120]
    ascii_ = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode("ascii")
    ascii_ = re.sub(r"[^A-Za-z0-9._ -]", "_", ascii_).strip(" .")
    if not ascii_:
        ascii_ = "arquivo" + {"application/pdf": ".pdf"}.get(mime, "")
    valor = 'attachment; filename="%s"' % ascii_
    if nome and nome != ascii_:
        valor += "; filename*=UTF-8''%s" % urllib.parse.quote(nome, safe="")
    return valor


def _chamar(mod, ctx, ref, tempo):
    """arquivo(ctx, ref) numa thread; a vaga só volta quando a thread termina (mesmo depois do tempo)."""
    if not _vagas.acquire(blocking=False):
        raise modulos.ErroModulo(503, "Muitos arquivos sendo abertos agora. Tente de novo daqui a pouco.")
    caixa = {}

    def alvo():
        try:
            caixa["dado"] = mod.arquivo(ctx, ref)
        except BaseException as e:  # noqa: B902 - módulo quebrado não derruba o painel
            caixa["erro"] = e
        finally:
            _vagas.release()

    t = threading.Thread(target=alvo, name="modulo-arquivo", daemon=True)
    try:
        t.start()
    except BaseException:
        _vagas.release()
        raise
    t.join(tempo)
    if t.is_alive():
        raise modulos.ErroModulo(504, "O arquivo demorou demais para abrir.")
    if "erro" in caixa:
        if isinstance(caixa["erro"], (LookupError, FileNotFoundError)):
            raise modulos.ErroModulo(404, "Arquivo não encontrado.")
        raise modulos.ErroModulo(500, "Não consegui abrir este arquivo.")
    return caixa.get("dado")


def servir(cfg, mid, refs, cabecalhos, tempo=None):
    """Argumentos nomeados de _enviar() do painel para GET .../arquivo?ref=. `mid` ainda codificado (vem do
    caminho); `refs` é a lista do parse_qs."""
    mid = urllib.parse.unquote(mid)
    if cabecalhos.get("Sec-Fetch-Site") != "same-origin":
        return _erro(403, "Pedido de outro site recusado.")
    ref = refs[0] if isinstance(refs, list) and len(refs) == 1 else None
    if not ref_ok(ref):
        return _erro(400, "Referência de arquivo inválida.")
    try:
        mod = modulos.carregar(cfg, mid)
        if not callable(getattr(mod, "arquivo", None)):
            raise modulos.ErroModulo(404, "Esta tela não serve arquivos.")
        r = _chamar(mod, modulos.contexto(cfg), ref, TEMPO_LIMITE if tempo is None else tempo)
    except modulos.ErroModulo as e:
        return _erro(e.codigo, e.mensagem)
    if not isinstance(r, dict) or not isinstance(r.get("dados"), (bytes, bytearray)) \
            or not isinstance(r.get("mime"), str):
        return _erro(500, "Esta tela devolveu um arquivo estranho.")
    mime = r["mime"].split(";", 1)[0].strip().lower()
    if mime not in MIMES:
        return _erro(415, "Tipo de arquivo não permitido.")
    dados = bytes(r["dados"])
    if len(dados) > MAX_BYTES:
        return _erro(413, "Arquivo grande demais.")
    extra = {"Accept-Ranges": "bytes"}
    if r.get("baixar") is True or mime in SEMPRE_ANEXO:
        extra["Content-Disposition"] = nome_anexo(r.get("nome"), mime)
    codigo, total = 200, len(dados)
    faixa = midia._intervalo(cabecalhos.get("Range"), total)
    if faixa == "416":
        return _erro(416, "Trecho fora do arquivo.", {"Content-Range": "bytes */%d" % total})
    if faixa is not None:
        codigo, dados = 206, dados[faixa[0]:faixa[1] + 1]
        extra["Content-Range"] = "bytes %d-%d/%d" % (faixa[0], faixa[1], total)
    return {"codigo": codigo, "corpo": dados, "tipo": mime, "cache": "private, max-age=300", "csp": CSP,
            "extra": extra}
