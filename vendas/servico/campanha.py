"""Campanha = modelo da mensagem + contatos (campanha_contatos). Estados: rascunho, ativa, pausada, concluida.

Contato da campanha: 'pendente' (na fila) -> 'enviado' | 'incerto' (pode ter saído: o agendador nunca reenvia; só o
dono, na aba Conversas) | 'negado' (opt-out ou número inválido: nunca mais) | 'respondeu' (o lead falou: sai da
campanha e a conversa fica com o recebimento/IA). 'falhou' (prova de que não saiu) continua 'pendente' com o envio_id
e `tentar_depois`: o agendador tenta de novo a MESMA linha pelo portao.reenviar, depois dos contatos ainda não
tentados, até TENTATIVAS_FALHOU vezes; aí o contato fica 'falhou' (final, o dono vê na contagem). 'falhou' com
numero_invalido (o WhatsApp disse que o número não existe) vira 'negado' na hora e não conta como falha seguida.
Negado por janela ou teto continua 'pendente', com o motivo guardado e `tentar_depois`. 5 falhas seguidas do conector
pausam a campanha com o motivo. 'pulado' = o modelo não pôde ser preenchido para o contato (falta nome ou origem,
link fora da lista...): fica com o motivo e nunca sai. Ativar passa por `ativar_com_regras` (empresa, modelo, trava
de número descartável); a trava vem só da config da instância, nunca do corpo do pedido."""
import re

from servico import banco, cerebro, modelo

ESTADOS = ("rascunho", "ativa", "pausada", "concluida")
FALHAS_PARA_PAUSAR = 5
TENTATIVAS_FALHOU = 3   # 'falhou' de transporte: tentativas por contato antes de desistir dele
PERMANENTES = ("optout", "numero_invalido")   # negado assim = nunca mais, em nenhuma campanha
ATIVOS = ("pendente", "enviado", "incerto")     # envio que pode ter saído (o mesmo critério do portão)
ROTA = re.compile(r"^/campanhas(?:/(\d+)/(pausar|retomar|ativar)|/(empresa))?$")
EMPRESA_MAX = 100
SEM_DESCARTAVEL = ("Disparo a frio (contato que nunca recebeu nada de você ou sem consentimento) viola a Política do "
                   "WhatsApp Business e pode banir o número. Só liga com um número descartável: conecte um na aba "
                   "Conexão confirmando que é descartável.")


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


def criar(con, nome, modelo, contato_ids, id_cliente=None):
    """Campanha em 'rascunho' com os contatos na ordem dada (repetido entra uma vez). Devolve o id."""
    if not isinstance(nome, str) or not nome.strip() or not isinstance(modelo, str) or not modelo.strip():
        raise ValueError("campanha precisa de nome e modelo")

    def fazer():
        cur = con.execute("INSERT INTO campanhas (nome, modelo, estado, criado_em, id_cliente) "
                          "VALUES (?, ?, 'rascunho', ?, ?)", (nome.strip(), modelo, banco.agora(), id_cliente))
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


def fria(con, contato_id, instancia=None):
    """True se o contato é frio: base legal fora de modelo.FRIO_BASES ou nunca recebeu nada DESTA instância (sem
    `instancia`, a da config; envio de outro número não esquenta o contato para este)."""
    instancia = instancia or banco.ler_config(con, "instancia")
    return con.execute(
        "SELECT 1 FROM contatos ct WHERE ct.id = ? AND (ct.base_legal IS NULL OR ct.base_legal NOT IN (?, ?) OR NOT "
        "EXISTS (SELECT 1 FROM envios e WHERE e.contato_id = ct.id AND e.instancia = ? AND e.estado IN (%s)))"
        % ",".join("?" * len(ATIVOS)), (contato_id,) + modelo.FRIO_BASES + (instancia,) + ATIVOS).fetchone() is not None


def ativar_com_regras(con, campanha_id, permitidos=()):
    """(codigo, erro) -- (200, None) ativou. Exige empresa na config, modelo válido e, para contato frio, instância
    criada com numero_descartavel (lida da config, não de pedido). Nada é ativado se algo falha."""
    def fazer():
        linha = con.execute("SELECT modelo, estado FROM campanhas WHERE id = ?", (campanha_id,)).fetchone()
        if linha is None or linha["estado"] != "rascunho":
            return 409, "A campanha não está num estado que permita isso."
        empresa = banco.ler_config(con, "empresa")
        if not empresa:
            return 409, "Antes de ativar, diga o nome da empresa: ele vai em toda primeira mensagem."
        try:
            modelo.validar(linha["modelo"], empresa, permitidos)
        except modelo.ModeloRecusado as e:
            return 400, str(e)
        if banco.ler_config(con, "numero_descartavel") != "1" and any(
                fria(con, r["contato_id"]) for r in con.execute(
                    "SELECT contato_id FROM campanha_contatos WHERE campanha_id = ?", (campanha_id,))):
            return 403, SEM_DESCARTAVEL
        if not ativar(con, campanha_id):
            return 409, "A campanha precisa de ao menos um contato."
        return 200, None
    return _transacao(con, fazer)


def pausar_por(con, campanha_id, motivo):
    return con.execute("UPDATE campanhas SET estado = 'pausada', motivo = ? WHERE id = ? AND estado = 'ativa'",
                       (motivo, campanha_id)).rowcount == 1


def pular(con, linha, motivo):
    """O contato não recebe esta mensagem (modelo sem como preencher): 'pulado' com o motivo."""
    banco._exigir(con.execute(
        "UPDATE campanha_contatos SET estado = 'pulado', motivo = ?, tentar_depois = NULL "
        "WHERE campanha_id = ? AND contato_id = ? AND estado = 'pendente'",
        (motivo, linha["campanha_id"], linha["contato_id"])))


def pausar(con, campanha_id):
    return _mudar(con, campanha_id, "ativa", "pausada", ", motivo = 'pausada_pelo_dono'")


def retomar(con, campanha_id):
    """Volta a 'ativa' e zera as falhas seguidas (o dono viu o motivo)."""
    return _mudar(con, campanha_id, "pausada", "ativa", ", motivo = NULL, falhas_seguidas = 0")


def concluir_prontas(con):
    """Campanha ativa sem contato 'pendente' vira 'concluida'. Devolve quantas."""
    return con.execute("UPDATE campanhas SET estado = 'concluida' WHERE estado = 'ativa' AND NOT EXISTS (SELECT 1 "
                       "FROM campanha_contatos WHERE campanha_id = campanhas.id AND estado = 'pendente')").rowcount


def proximo(con, agora_iso, so_conhecidos=False, instancia=None):
    """Próximo contato vencido das campanhas ativas (campanha mais antiga; quem nunca foi adiado antes de quem volta
    de uma falha ou de um teto; depois a ordem), ou None.
    so_conhecidos=True: só quem já recebeu algo desta instância (o teto de NOVOS do dia acabou)."""
    extra = ""
    if so_conhecidos:
        extra = (" AND EXISTS (SELECT 1 FROM envios e WHERE e.contato_id = cc.contato_id AND e.instancia = ? "
                 "AND e.estado IN (%s))" % ",".join("?" * len(ATIVOS)))
    return con.execute(
        "SELECT cc.campanha_id, cc.contato_id, cc.passo, cc.envio_id, c.modelo, ct.telefone, ct.nome, ct.origem FROM campanha_contatos cc "
        "JOIN campanhas c ON c.id = cc.campanha_id JOIN contatos ct ON ct.id = cc.contato_id "
        "WHERE c.estado = 'ativa' AND cc.estado = 'pendente' AND (cc.tentar_depois IS NULL OR cc.tentar_depois <= ?)"
        + extra + " ORDER BY c.id, cc.tentar_depois IS NOT NULL, cc.ordem, cc.contato_id LIMIT 1",
        (agora_iso,) + (((instancia,) + ATIVOS) if so_conhecidos else ())).fetchone()


def _falhou(con, envio_id, motivo):
    """'falhou': número inexistente = 'negado' na hora; senão volta à fila (None) até TENTATIVAS_FALHOU vezes."""
    if motivo in PERMANENTES:
        return "negado"
    feitas = con.execute("SELECT COUNT(*) FROM tentativas WHERE envio_id = ?", (envio_id,)).fetchone()[0]
    return "falhou" if feitas >= TENTATIVAS_FALHOU else None


def _estado_do_contato(con, r):
    """Estado do contato na campanha pelo resultado do portão; None = continua 'pendente'."""
    if r["estado"] in ("enviado", "incerto"):
        return r["estado"]
    if r["estado"] == "falhou":
        return _falhou(con, r["envio_id"], r.get("motivo"))
    if r["estado"] == "duplicado":   # já reservado antes (reinício no meio): vale o que a linha do envio diz
        linha = con.execute("SELECT estado, motivo FROM envios WHERE id = ?", (r["envio_id"],)).fetchone()
        estado = linha["estado"] if linha else None
        if estado == "falhou":
            return _falhou(con, r["envio_id"], linha["motivo"])
        return "incerto" if estado == "pendente" else estado if estado in ("enviado", "incerto") else None
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
        elif r["estado"] == "incerto" or (r["estado"] == "falhou" and r.get("motivo") not in PERMANENTES):
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


def _permitidos(app):
    return list(cerebro.ler_links(app.raiz).values()) if app is not None and app.raiz else []


def _criar_rota(app, con, corpo, id_cliente=None):
    ids = corpo.get("contato_ids")
    if not isinstance(ids, list) or not ids or not all(type(i) is int for i in ids):
        return 400, {"erro": "Escolha os contatos da campanha."}
    if not isinstance(corpo.get("nome"), str) or not corpo["nome"].strip():
        return 400, {"erro": "Dê um nome à campanha."}
    try:
        modelo.validar(corpo.get("modelo"), banco.ler_config(con, "empresa"), _permitidos(app))
    except modelo.ModeloRecusado as e:
        return 400, {"erro": str(e)}
    if len(set(ids)) != con.execute("SELECT COUNT(*) FROM contatos WHERE id IN (%s)" % ",".join("?" * len(set(ids))),
                                    tuple(set(ids))).fetchone()[0]:
        return 400, {"erro": "Algum contato escolhido não existe."}
    return 200, dict(listar(con), id=criar(con, corpo["nome"], corpo["modelo"], ids, id_cliente))


def _empresa_rota(con, corpo):
    nome = modelo.CONTROLE.sub(" ", corpo.get("empresa") if isinstance(corpo.get("empresa"), str) else "").strip()
    if not nome or len(nome) > EMPRESA_MAX or "{" in nome or "}" in nome:
        return 400, {"erro": "Informe o nome da empresa (até %d caracteres, sem chaves)." % EMPRESA_MAX}
    banco.gravar_config(con, "empresa", nome)
    return 200, {"empresa": nome}


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) de GET /campanhas e POST /campanhas, /campanhas/empresa e /campanhas/<id>/pausar|retomar|ativar;
    None = rota desconhecida. O corpo nunca muda a trava de número descartável."""
    achou = ROTA.match(caminho)
    if not achou:
        return None
    if metodo == "GET" and achou.group(1) is None and achou.group(3) is None:
        return 200, listar(con)
    if metodo != "POST":
        return None
    corpo = corpo if isinstance(corpo, dict) else {}
    if achou.group(3):
        return _empresa_rota(con, corpo)
    if achou.group(1) is None:
        return _criar_rota(app, con, corpo)
    if achou.group(2) == "ativar":
        codigo, erro = ativar_com_regras(con, int(achou.group(1)), _permitidos(app))
        return (200, listar(con)) if codigo == 200 else (codigo, {"erro": erro})
    acao = pausar if achou.group(2) == "pausar" else retomar
    if not acao(con, int(achou.group(1))):
        return 409, {"erro": "A campanha não está num estado que permita isso."}
    return 200, listar(con)
