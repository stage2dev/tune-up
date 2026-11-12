"""Rotas da mídia, sempre com token: GET /midia/<id> entrega o arquivo (mimetype guardado, Content-Length, Range de
uma faixa, documento como anexo, áudio/imagem inline, nosniff) e POST /midia/<id>/baixar-de-novo pede outra tentativa
(do download que falhou ou, numa pronta, da IA que falhou com ela).
O id é um inteiro procurado no banco; o caminho do arquivo vem só da linha, nunca do pedido."""
import os
import re
import urllib.parse

from servico import midia

ROTA = re.compile(r"^/midia/(\d{1,12})(/baixar-de-novo)?$")
FAIXA = re.compile(r"^bytes=(\d{0,18})-(\d{0,18})$")
BLOCO = 64 * 1024


def faixa(valor, tamanho):
    """Cabeçalho Range -> (inicio, fim) inclusivos; None = arquivo inteiro (ausente ou formato que não seguimos,
    como várias faixas); False = fora do arquivo (416)."""
    achou = FAIXA.match((valor or "").strip())
    if not achou or not (achou.group(1) or achou.group(2)):
        return None
    if achou.group(1):
        inicio = int(achou.group(1))
        fim = min(int(achou.group(2)) if achou.group(2) else tamanho - 1, tamanho - 1)
        return (inicio, fim) if inicio < tamanho and fim >= inicio else False
    n = int(achou.group(2))
    return (max(0, tamanho - n), tamanho - 1) if n > 0 and tamanho > 0 else False


def _disposicao(linha):
    if linha["tipo"] != "documento":
        return "inline"
    nome = linha["nome_arquivo"] or "documento"
    ascii_ = "".join(c if 32 <= ord(c) < 127 and c not in '"\\;' else "_" for c in nome)
    return "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_, urllib.parse.quote(nome, safe=""))


def atender(handler, app, token_ok):
    if not token_ok:
        handler.close_connection = True
        return handler._erro(403, "Token de envio errado. Recarregue a tela.")
    achou = ROTA.match(handler._caminho())
    if not achou or bool(achou.group(2)) != (handler.command == "POST"):
        return handler._erro(404, "Mídia não encontrada.")
    midia_id = int(achou.group(1))
    con = app.abrir()
    try:
        if handler.command == "POST":
            handler.close_connection = True
            if midia.pedir_de_novo(con, midia_id):
                return handler._json(202, {"id": midia_id, "estado": "pendente"})
            alvo = midia.entender_de_novo(con, midia_id)   # pronta em que a IA falhou: a IA tenta de novo agora
            if alvo is not None:
                if alvo[1] is not None:
                    from servico import recebimento   # aqui dentro: no topo fecharia um ciclo de import (rotas)
                    recebimento.ao_receber_mensagem_de_lead(alvo[0], alvo[1])
                return handler._json(202, {"id": midia_id, "estado": "pronta", "responde": alvo[1] is not None})
            return handler._erro(409, "Esta mídia não pode ser tentada de novo (não falhou, já está sendo baixada ou "
                                      "a falha se repetiria).")
        linha = con.execute("SELECT tipo, mimetype, nome_arquivo, arquivo FROM midias WHERE id = ? AND estado = "
                            "'pronta'", (midia_id,)).fetchone()
    finally:
        con.close()
    caminho = midia.caminho_do_arquivo(app.pasta_dados, linha["arquivo"]) if linha else None
    try:
        arquivo = open(caminho, "rb") if caminho else None
    except OSError:
        arquivo = None
    if arquivo is None:
        return handler._erro(404, "Mídia não encontrada.")
    with arquivo:
        _entregar(handler, linha, arquivo, os.fstat(arquivo.fileno()).st_size)


def _entregar(handler, linha, arquivo, tamanho):
    pedida = faixa(handler.headers.get("Range"), tamanho)
    if pedida is False:
        handler.send_response(416)
        handler.send_header("Content-Range", "bytes */%d" % tamanho)
        handler.send_header("Content-Length", "0")
        handler._cors()
        return handler.end_headers()
    inicio, fim = pedida or (0, tamanho - 1)
    handler.send_response(206 if pedida else 200)
    handler.send_header("Content-Type", linha["mimetype"])
    handler.send_header("Content-Length", str(max(0, fim - inicio + 1)))
    if pedida:
        handler.send_header("Content-Range", "bytes %d-%d/%d" % (inicio, fim, tamanho))
    handler.send_header("Accept-Ranges", "bytes")
    handler.send_header("Content-Disposition", _disposicao(linha))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
    handler.send_header("Cache-Control", "no-store")
    handler._cors()
    handler.end_headers()
    if handler.command == "HEAD":
        return
    arquivo.seek(inicio)
    falta = fim - inicio + 1
    while falta > 0:
        bloco = arquivo.read(min(BLOCO, falta))
        if not bloco:
            break
        handler.wfile.write(bloco)
        falta -= len(bloco)
