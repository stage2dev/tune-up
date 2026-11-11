"""Modos da IA por conversa e rascunhos. 'rascunho' (padrão): a IA escreve, nada sai; o dono aprova, edita ou descarta
na aba Conversas e a aprovação sai pelo portão com a origem fixa 'rascunho_aprovado' (chave = id do rascunho, então
aprovar duas vezes envia uma). 'automatico': a IA envia (origem 'ia'). O modo da conversa (conversas.modo_ia) vale
sobre o padrão do projeto (config ia_modo_padrao, 'rascunho' se faltar). Um rascunho novo substitui o pendente da
conversa; passa de 24 h e deixa de poder ser aprovado; opt-out depois do rascunho = negado no portão."""
import datetime
import json
import re
import sqlite3

from servico import banco, conversas, portao, saida

UTC = datetime.timezone.utc
MODOS_IA = ("rascunho", "automatico")
PADRAO = "ia_modo_padrao"
VALIDADE = datetime.timedelta(hours=24)
TEXTO_MAX = saida.CARACTERES_MAX
ROTA = re.compile(r"^/(?:rascunhos/(\d{1,12})/(aprovar|descartar)|conversas/(\d{1,12})/modo-ia)$")


def modo_padrao(con):
    valor = banco.ler_config(con, PADRAO)
    return valor if valor in MODOS_IA else "rascunho"


def modo_da_conversa(con, conversa_id):
    linha = con.execute("SELECT modo_ia FROM conversas WHERE id = ?", (conversa_id,)).fetchone()
    return modo_padrao(con) if linha is None or linha["modo_ia"] is None else linha["modo_ia"]


def definir_modo_padrao(con, modo):
    banco.gravar_config(con, PADRAO, modo)


def definir_modo_ia(con, conversa_id, modo):
    """modo: 'rascunho', 'automatico' ou 'padrao' (volta a seguir o projeto). False = conversa não existe."""
    cur = con.execute("UPDATE conversas SET modo_ia = ? WHERE id = ?", (None if modo == "padrao" else modo, conversa_id))
    return cur.rowcount == 1


def _expirado(criado_em, agora):
    try:
        return datetime.datetime.fromisoformat(criado_em) + VALIDADE <= agora
    except ValueError:
        return True   # data ilegível: fecha


def pendente(con, conversa_id, agora=None):
    """O rascunho pendente da conversa ({id, texto, criado_em, expirado}) ou None."""
    r = con.execute("SELECT id, texto, criado_em FROM rascunhos WHERE conversa_id = ? AND estado = 'pendente'",
                    (conversa_id,)).fetchone()
    if r is None:
        return None
    return {"id": r["id"], "texto": r["texto"], "criado_em": r["criado_em"],
            "expirado": _expirado(r["criado_em"], agora or datetime.datetime.now(UTC))}


def guardar(con, conversa_id, gatilho_id, texto, permitidos=(), segredos=(), reescrever=None):
    """Passa o texto da IA pelo mesmo sanitizador da saída e guarda como rascunho (nada é enviado). Barrado = a
    conversa fica 'precisa de você'. O rascunho novo troca o pendente; o mesmo gatilho não gera dois."""
    pronto, motivo = saida.preparar(texto, permitidos, segredos, reescrever)
    if pronto is None:
        return saida._barrar(con, conversa_id, motivo)
    quando = banco.agora()
    con.execute("BEGIN IMMEDIATE")
    try:
        con.execute("UPDATE rascunhos SET estado = 'substituido', decidido_em = ? WHERE conversa_id = ? "
                    "AND estado = 'pendente'", (quando, conversa_id))
        cur = con.execute("INSERT INTO rascunhos (conversa_id, mensagem_id, texto, criado_em) VALUES (?, ?, ?, ?)",
                          (conversa_id, gatilho_id, pronto, quando))
        banco._exigir(cur)
        banco.registrar_evento(con, "ia_rascunho", json.dumps({"conversa_id": conversa_id, "rascunho_id":
                                                               cur.lastrowid}))
        con.execute("COMMIT")
    except sqlite3.IntegrityError:
        con.execute("ROLLBACK")
        return {"estado": "duplicado", "motivo": "gatilho_ja_tem_rascunho", "baloes": []}
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return {"estado": "rascunho", "motivo": None, "rascunho_id": cur.lastrowid, "baloes": []}


def _fechar(con, rascunho_id, estado):
    return con.execute("UPDATE rascunhos SET estado = ?, decidido_em = ? WHERE id = ? AND estado = 'pendente'",
                       (estado, banco.agora(), rascunho_id)).rowcount


def aprovar(app, con, rascunho_id, texto=None, agora=None):
    """(código, objeto). Texto novo = o dono editou. O portão decide e dedupa; o rascunho só vira 'aprovado' quando
    a mensagem saiu (ou pode ter saído); recusa passageira (teto) deixa pendente, opt-out o encerra."""
    agora = agora or datetime.datetime.now(UTC)
    r = con.execute("SELECT d.id, d.estado, d.texto, d.criado_em, k.telefone FROM rascunhos d JOIN conversas c ON "
                    "c.id = d.conversa_id JOIN contatos k ON k.id = c.contato_id WHERE d.id = ?",
                    (rascunho_id,)).fetchone()
    if r is None:
        return 404, {"erro": "Rascunho não encontrado."}
    if r["estado"] not in ("pendente", "aprovado"):
        return 409, {"erro": "Este rascunho já foi decidido (%s)." % r["estado"]}
    if r["estado"] == "pendente" and _expirado(r["criado_em"], agora):
        _fechar(con, rascunho_id, "expirado")
        return 409, {"erro": "Este rascunho tem mais de 24 horas e expirou. Escreva uma mensagem nova."}
    instancia = banco.ler_config(con, "instancia")
    if app.conector is None or not instancia:
        return 503, {"erro": "Conecte o WhatsApp primeiro."}
    final = r["texto"]
    if texto is not None:
        final = texto.strip()
        if not final or len(final) > TEXTO_MAX:
            return 400, {"erro": "Mensagem vazia ou longa demais."}
        if r["estado"] == "pendente":
            con.execute("UPDATE rascunhos SET texto = ? WHERE id = ? AND estado = 'pendente'", (final, rascunho_id))
    res = portao.enviar_rascunho_aprovado(con, app.conector, instancia, r["telefone"], final, rascunho_id,
                                          agora=agora)
    res = conversas.depois_de_duplicado(app, con, instancia, res, False)
    if res["estado"] in ("enviado", "incerto", "enviando", "duplicado"):
        _fechar(con, rascunho_id, "aprovado")
    elif res["estado"] == "negado" and res["motivo"] == "optout":
        _fechar(con, rascunho_id, "negado")
    return 200, {"estado": res["estado"], "motivo": res["motivo"], "envio_id": res.get("envio_id")}


def descartar(con, rascunho_id):
    if _fechar(con, rascunho_id, "descartado") == 1:
        return 200, {"estado": "descartado"}
    achou = con.execute("SELECT estado FROM rascunhos WHERE id = ?", (rascunho_id,)).fetchone()
    return (404, {"erro": "Rascunho não encontrado."}) if achou is None else (
        409, {"erro": "Este rascunho já foi decidido (%s)." % achou["estado"]})


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) das rotas de rascunho e do modo por conversa; None = rota desconhecida."""
    achou = ROTA.match(caminho)
    if not achou or metodo != "POST" or corpo is None:
        return None
    rid, acao, cid = achou.groups()
    if cid:
        modo = corpo.get("modo_ia")
        if modo not in MODOS_IA + ("padrao",):
            return 400, {"erro": "Modo desconhecido."}
        return (200, {"modo_ia": modo}) if definir_modo_ia(con, int(cid), modo) else (
            404, {"erro": "Conversa não encontrada."})
    if acao == "descartar":
        return descartar(con, int(rid))
    texto = corpo.get("texto")
    if texto is not None and not isinstance(texto, str):
        return 400, {"erro": "Mensagem inválida."}
    return aprovar(app, con, int(rid), texto)
