"""Campanha = modelo da mensagem + contatos (campanha_contatos). Estados: rascunho, ativa, pausada, concluida.

Contato da campanha: 'pendente' (na fila) -> 'enviado' | 'incerto' | 'falhou' (o que o portão devolveu; o agendador
nunca reenvia: só o dono, na aba Conversas) | 'negado' (opt-out ou número inválido: nunca mais) | 'respondeu' (o
lead falou: sai da campanha e a conversa fica com o recebimento/IA). Negado por janela ou teto continua 'pendente',
com o motivo guardado e `tentar_depois`. 5 falhas seguidas do conector pausam a campanha com o motivo."""
import re

from servico import banco

ESTADOS = ("rascunho", "ativa", "pausada", "concluida")
FALHAS_PARA_PAUSAR = 5
PERMANENTES = ("optout", "numero_invalido")   # negado assim = nunca mais, em nenhuma campanha
ATIVOS = ("pendente", "enviado", "incerto")     # envio que pode ter saído (o mesmo critério do portão)
ROTA = re.compile(r"^/campanhas(?:/(\d+)/(pausar|retomar))?$")


def _transacao(con, funcao):
    propria = not con.in_transaction
    if propria:
        con.execute("BEGIN IMMEDIATE")
    try:
        r = funcao()
        if propria:
            con.execute("COMMIT")
        return r
    except BaseException:
        if propria and con.in_transaction:
            con.execute("ROLLBACK")
        raise


def criar(con, nome, modelo, contato_ids):
    """Campanha em 'rascunho' com os contatos na ordem dada (repetido entra uma vez). Devolve o id."""
    if not isinstance(nome, str) or not nome.strip() or not isinstance(modelo, str) or not modelo.strip():
        raise ValueError("campanha precisa de nome e modelo")

    def fazer():
        cur = con.execute("INSERT INTO campanhas (nome, modelo, estado, criado_em) VALUES (?, ?, 'rascunho', ?)",
                          (nome.strip(), modelo, banco.agora()))
        banco._exigir(cur)
        for ordem, contato_id in enumerate(dict.fromkeys(contato_ids)):
            banco._exigir(con.execute("INSERT INTO campanha_contatos (campanha_id, contato_id, ordem) "
                                      "VALUES (?, ?, ?)", (cur.lastrowid, contato_id, ordem)))
        return cur.lastrowid
    return _transacao(con, fazer)


def _mudar(con, campanha_id, de, para, extra=""):
    """True se a campanha estava em `de` e foi para `para`; False se não estava (nada muda)."""
    cur = con.execute("UPDATE campanhas SET estado = ?%s WHERE id = ? AND estado = ?" % extra,
                      (para, campanha_id, de))
    return cur.rowcount == 1


def ativar(con, campanha_id):
    tem = con.execute("SELECT 1 FROM campanha_contatos WHERE campanha_id = ?", (campanha_id,)).fetchone()
    return tem is not None and _mudar(con, campanha_id, "rascunho", "ativa")


def pausar(con, campanha_id):
    return _mudar(con, campanha_id, "ativa", "pausada", ", motivo = 'pausada_pelo_dono'")


def retomar(con, campanha_id):
    """Volta a 'ativa' e zera as falhas seguidas (o dono viu o motivo)."""
    return _mudar(con, campanha_id, "pausada", "ativa", ", motivo = NULL, falhas_seguidas = 0")


def concluir_prontas(con):
    """Campanha ativa sem contato 'pendente' vira 'concluida'. Devolve quantas."""
    return con.execute("UPDATE campanhas SET estado = 'concluida' WHERE estado = 'ativa' AND NOT EXISTS (SELECT 1 "
                       "FROM campanha_contatos WHERE campanha_id = campanhas.id AND estado = 'pendente')").rowcount


def proximo(con, agora_iso, so_conhecidos=False):
    """Próximo contato vencido das campanhas ativas (campanha mais antiga, depois a ordem), ou None.
    so_conhecidos=True: só quem já recebeu algo deste número (o teto de NOVOS do dia acabou)."""
    extra = ""
    if so_conhecidos:
        extra = (" AND EXISTS (SELECT 1 FROM envios e WHERE e.contato_id = cc.contato_id AND e.estado IN (%s))"
                 % ",".join("?" * len(ATIVOS)))
    return con.execute(
        "SELECT cc.campanha_id, cc.contato_id, cc.passo, c.modelo, ct.telefone FROM campanha_contatos cc "
        "JOIN campanhas c ON c.id = cc.campanha_id JOIN contatos ct ON ct.id = cc.contato_id "
        "WHERE c.estado = 'ativa' AND cc.estado = 'pendente' AND (cc.tentar_depois IS NULL OR cc.tentar_depois <= ?)"
        + extra + " ORDER BY c.id, cc.ordem, cc.contato_id LIMIT 1",
        (agora_iso,) + (ATIVOS if so_conhecidos else ())).fetchone()


def _estado_do_contato(con, r):
    """Estado do contato na campanha pelo resultado do portão; None = continua 'pendente'."""
    if r["estado"] in ("enviado", "incerto", "falhou"):
        return r["estado"]
    if r["estado"] == "duplicado":   # já reservado antes (reinício no meio): vale o que a linha do envio diz
        linha = con.execute("SELECT estado FROM envios WHERE id = ?", (r["envio_id"],)).fetchone()
        estado = linha["estado"] if linha else None
        return "incerto" if estado == "pendente" else estado if estado in ("enviado", "incerto", "falhou") else None
    if r["estado"] == "negado" and r["motivo"] in PERMANENTES:
        return "negado"
    return None


def registrar(con, linha, r, tentar_depois=None):
    """Grava o resultado do portão para o contato e conta as falhas seguidas da campanha, numa transação.
    Lead que respondeu enquanto o envio saía continua 'respondeu' (só ganha o envio_id). Devolve o estado gravado."""
    def fazer():
        estado = _estado_do_contato(con, r)
        banco._exigir(con.execute(
            "UPDATE campanha_contatos SET estado = CASE WHEN estado = 'pendente' THEN ? ELSE estado END, motivo = ?, "
            "tentar_depois = ?, envio_id = COALESCE(?, envio_id) WHERE campanha_id = ? AND contato_id = ?",
            (estado or "pendente", r.get("motivo"), None if estado else tentar_depois, r.get("envio_id"),
             linha["campanha_id"], linha["contato_id"])))
        if r["estado"] == "enviado":
            con.execute("UPDATE campanhas SET falhas_seguidas = 0 WHERE id = ?", (linha["campanha_id"],))
        elif r["estado"] in ("falhou", "incerto"):
            contar_falha(con, linha["campanha_id"], r.get("motivo") or r["estado"])
        return estado or "pendente"
    return _transacao(con, fazer)


def contar_falha(con, campanha_id, motivo):
    """+1 falha seguida; na 5ª a campanha ativa pausa sozinha com o motivo. Devolve True se pausou agora."""
    def fazer():
        banco._exigir(con.execute("UPDATE campanhas SET falhas_seguidas = falhas_seguidas + 1 WHERE id = ?",
                                  (campanha_id,)))
        return con.execute("UPDATE campanhas SET estado = 'pausada', motivo = ? WHERE id = ? AND estado = 'ativa' "
                           "AND falhas_seguidas >= ?", ("%d_falhas_seguidas:%s" % (FALHAS_PARA_PAUSAR, motivo),
                                                        campanha_id, FALHAS_PARA_PAUSAR)).rowcount == 1
    return _transacao(con, fazer)


def lead_respondeu(con, contato_id):
    """Recebimento: o lead falou; sai do fluxo de toda campanha em que ainda esperava a vez."""
    return con.execute("UPDATE campanha_contatos SET estado = 'respondeu', tentar_depois = NULL "
                       "WHERE contato_id = ? AND estado = 'pendente'", (contato_id,)).rowcount


def listar(con):
    """Campanhas com a contagem de contatos por estado (sem telefone)."""
    campanhas = [dict(c) for c in con.execute(
        "SELECT id, nome, estado, motivo, falhas_seguidas, criado_em FROM campanhas ORDER BY id DESC")]
    for c in campanhas:
        c["contatos"] = {r["estado"]: r["n"] for r in con.execute(
            "SELECT estado, COUNT(*) AS n FROM campanha_contatos WHERE campanha_id = ? GROUP BY estado", (c["id"],))}
    return {"campanhas": campanhas}


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) de GET /campanhas e POST /campanhas/<id>/pausar|retomar; None = rota desconhecida."""
    achou = ROTA.match(caminho)
    if not achou:
        return None
    if metodo == "GET" and achou.group(1) is None:
        return 200, listar(con)
    if metodo != "POST" or achou.group(1) is None:
        return None
    acao = pausar if achou.group(2) == "pausar" else retomar
    if not acao(con, int(achou.group(1))):
        return 409, {"erro": "A campanha não está num estado que permita isso."}
    return 200, listar(con)
