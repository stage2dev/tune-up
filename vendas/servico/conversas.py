"""Leitura e ações da aba Conversas, do lado do serviço: lista (traz o telefone inteiro só para a tela do dono), conversa aberta (últimas 100
mensagens + envios que ainda não voltaram como eco), envios 'incerto', modo humano/IA, seleção da conversa aberta e
liberação de UM envio a quem saiu. O envio em si é sempre do portão (portao.py); aqui nada chama o conector."""
import datetime
import re

from servico import banco, portao

LIMITE_PADRAO = 50
LIMITE_CONVERSA = 100   # conversa aberta: as últimas 100 mensagens por padrão
LIMITE_MAX = 100
PREVIA = 80
ROTULOS = {"audio": "áudio", "imagem": "imagem", "documento": "documento", "outro": "mensagem"}
MODOS = ("ia", "humano")
LIBERADO = "liberado_contato"   # config: contato (um só) que o dono liberou para UMA mensagem apesar do opt-out
ABERTA = "conversa_aberta"      # config: conversa selecionada na tela deste projeto
ROTA = re.compile(r"^/(?:(conversas)(?:/(aberta|\d{1,12})(?:/(modo|liberar))?)?|(incertos)(?:/(\d{1,12})/"
                  r"(reenviar|descartar))?)$")


def mascarar(numero):
    """Só os 4 últimos dígitos; a lista nunca leva o telefone inteiro."""
    return "****" + str(numero or "")[-4:]


def _previa(texto, tipo):
    """Texto cortado em PREVIA; o que não é texto aparece pelo tipo ("[áudio]"), com a legenda se houver."""
    rotulo = None if tipo in (None, "texto") else "[%s]" % ROTULOS.get(tipo, "mensagem")
    if not texto:
        return rotulo or "[mensagem]"
    corte = texto if len(texto) <= PREVIA else texto[:PREVIA - 1] + "…"
    return corte if rotulo is None else "%s %s" % (rotulo, corte)


def _limite(query, padrao=LIMITE_PADRAO):
    try:
        valor = int((query.get("limite") or [padrao])[0])
    except (TypeError, ValueError):
        valor = padrao
    return max(1, min(valor, LIMITE_MAX))


def _deslocamento(query):
    try:
        return max(0, min(int((query.get("deslocamento") or [0])[0]), 1000000))
    except (TypeError, ValueError):
        return 0


NAO_LIDAS = ("(SELECT COUNT(*) FROM mensagens m WHERE m.conversa_id = c.id AND m.direcao = 'entrada' "
             "AND m.id > COALESCE(c.lida_ate, 0))")


def listar(con, query, agora=None):
    """Conversas pela última atividade, com não lidas (entradas depois da última abertura) e o total para o selo."""
    momento = agora or datetime.datetime.now(datetime.timezone.utc)
    linhas = con.execute(
        "SELECT c.id, c.contato_id, c.modo, c.precisa_de_voce, c.motivo_humano, k.nome, k.telefone, k.optout_em, "
        "k.nome_whatsapp, " + NAO_LIDAS + " AS nao_lidas, "
        "EXISTS (SELECT 1 FROM rascunhos d WHERE d.conversa_id = c.id AND d.estado = 'pendente') AS tem_rascunho, "
        "(SELECT texto FROM mensagens m WHERE m.conversa_id = c.id ORDER BY m.id DESC LIMIT 1) AS ultima, "
        "(SELECT tipo FROM mensagens m WHERE m.conversa_id = c.id ORDER BY m.id DESC LIMIT 1) AS ultima_tipo, "
        "(SELECT criado_em FROM mensagens m WHERE m.conversa_id = c.id ORDER BY m.id DESC LIMIT 1) AS ultima_em, "
        "(SELECT MAX(m.id) FROM mensagens m WHERE m.conversa_id = c.id) AS ultima_id "
        "FROM conversas c JOIN contatos k ON k.id = c.contato_id "
        "ORDER BY COALESCE(ultima_em, c.criado_em) DESC, ultima_id DESC, c.id DESC LIMIT ? OFFSET ?",
        (_limite(query), _deslocamento(query))).fetchall()
    total = con.execute("SELECT COUNT(*) FROM conversas").fetchone()[0]
    soma = con.execute("SELECT COALESCE(SUM(n), 0), COALESCE(SUM(n > 0), 0) FROM (SELECT " + NAO_LIDAS +
                       " AS n FROM conversas c)").fetchone()
    return {"total": total, "aberta": aberta(con), "nao_lidas_total": soma[0], "conversas_nao_lidas": soma[1],
            "conversas": [
        {"id": r["id"], "nome": r["nome"], "nome_exibido": r["nome"] or r["nome_whatsapp"],
         "telefone_mascarado": mascarar(r["telefone"]), "telefone": r["telefone"], "modo": r["modo"], "ia_desligada": r["modo"] == "humano",
         "nao_lidas": r["nao_lidas"], "ultima_tipo": r["ultima_tipo"], "precisa_de_voce": bool(r["precisa_de_voce"]),
         "motivo_humano": r["motivo_humano"], "saiu": r["optout_em"] is not None,
         "tem_rascunho": bool(r["tem_rascunho"]), "ia_pausada": portao._pausada(con, r["contato_id"], momento),
         "ultima": _previa(r["ultima"], r["ultima_tipo"]) if r["ultima_em"] else "", "quando": r["ultima_em"]}
        for r in linhas]}


def aberta(con):
    """Id da conversa selecionada, ou None (nunca selecionada ou já não existe)."""
    valor = banco.ler_config(con, ABERTA)
    if not valor or not valor.isdigit():
        return None
    achou = con.execute("SELECT id FROM conversas WHERE id = ?", (int(valor),)).fetchone()
    return None if achou is None else achou["id"]


def selecionar(con, conversa_id):
    """Abrir pela tela: guarda a conversa selecionada e marca lido até a última mensagem, numa transação."""
    con.execute("BEGIN IMMEDIATE")
    try:
        cur = con.execute("UPDATE conversas SET lida_ate = (SELECT MAX(id) FROM mensagens WHERE conversa_id = ?) "
                          "WHERE id = ?", (conversa_id, conversa_id))
        if cur.rowcount != 1:
            con.execute("ROLLBACK")
            return False
        banco.gravar_config(con, ABERTA, str(conversa_id))
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return True


def abrir(con, conversa_id, query, agora=None):
    """A conversa com o telefone inteiro e as últimas mensagens (no máximo 50 por padrão, 100 no teto)."""
    from servico import rascunhos   # aqui dentro: rascunhos.py importa este módulo
    momento = agora or datetime.datetime.now(datetime.timezone.utc)
    c = con.execute("SELECT c.id, c.contato_id, c.modo, c.modo_ia, c.precisa_de_voce, c.motivo_humano, k.nome, "
                    "k.nome_whatsapp, k.telefone, k.optout_em FROM conversas c JOIN contatos k ON k.id = c.contato_id WHERE c.id = ?",
                    (conversa_id,)).fetchone()
    if c is None:
        return None
    limite = _limite(query, LIMITE_CONVERSA)
    itens = []
    for m in con.execute("SELECT m.id, m.direcao, m.tipo, m.texto, m.criado_em, e.origem, e.estado, e.motivo "
                         "FROM mensagens m LEFT JOIN envios e ON e.id = m.envio_id WHERE m.conversa_id = ? "
                         "ORDER BY m.id DESC LIMIT ?", (conversa_id, limite)):
        de = "contato" if m["direcao"] == "entrada" else ("ia" if m["origem"] in ("ia", "audio_ia") else "eu")
        itens.append({"id": "m%d" % m["id"], "de": de, "tipo": m["tipo"] or "outro", "texto": m["texto"] or
                      _previa(None, m["tipo"]), "quando": m["criado_em"], "estado": m["estado"], "motivo": m["motivo"]})
    for e in con.execute("SELECT e.id, e.origem, e.estado, e.motivo, e.conteudo, e.tipo, e.tentado_em FROM envios e "
                         "WHERE e.contato_id = ? AND NOT EXISTS (SELECT 1 FROM mensagens m WHERE m.envio_id = e.id) "
                         "ORDER BY e.id DESC LIMIT ?", (c["contato_id"], limite)):
        itens.append({"id": "e%d" % e["id"], "de": "ia" if e["origem"] in ("ia", "audio_ia") else "eu",
                      "tipo": "audio" if e["tipo"] == "audio" else "texto", "texto": e["conteudo"] if e["tipo"] == "texto" else "[áudio]", "quando": e["tentado_em"],
                      "estado": e["estado"], "motivo": e["motivo"]})
    itens.sort(key=lambda i: (i["quando"] or "", int(i["id"][1:])))
    return {"conversa": {"id": c["id"], "nome": c["nome"], "nome_exibido": c["nome"] or c["nome_whatsapp"],
                         "telefone": c["telefone"], "modo": c["modo"],
                         "precisa_de_voce": bool(c["precisa_de_voce"]),
                         "motivo_humano": c["motivo_humano"], "saiu": c["optout_em"] is not None,
                         "ia_pausada": portao._pausada(con, c["contato_id"], momento),
                         "liberado": banco.ler_config(con, LIBERADO) == str(c["contato_id"]),
                         "modo_ia": c["modo_ia"] or "padrao", "modo_ia_efetivo": rascunhos.modo_da_conversa(
                             con, c["id"])},
            "mensagens": itens[-limite:], "rascunho": rascunhos.pendente(con, c["id"], momento)}


def incertos(con, query):
    linhas = con.execute("SELECT id, origem, tipo, telefone, conteudo, motivo, tentado_em FROM envios "
                         "WHERE estado = 'incerto' ORDER BY id DESC LIMIT ? OFFSET ?",
                         (_limite(query), _deslocamento(query))).fetchall()
    total = con.execute("SELECT COUNT(*) FROM envios WHERE estado = 'incerto'").fetchone()[0]
    return {"total": total, "incertos": [
        {"id": r["id"], "origem": r["origem"], "tipo": r["tipo"], "telefone_mascarado": mascarar(r["telefone"]),
         "previa": "[áudio]" if r["tipo"] == "audio" else _previa(r["conteudo"], "texto"),
         "motivo": r["motivo"], "quando": r["tentado_em"]}
        for r in linhas]}


def definir_modo(con, conversa_id, modo):
    """Assumir (humano; a IA para e o aviso 'precisa de você' sai) ou devolver (IA; a pausa, o aviso e o motivo acabam). False = não existe."""
    if modo == "humano":
        cur = con.execute("UPDATE conversas SET modo = 'humano', precisa_de_voce = 0, motivo_humano = NULL "
                          "WHERE id = ?", (conversa_id,))
    else:
        cur = con.execute("UPDATE conversas SET modo = 'ia', pausada_ate = NULL, precisa_de_voce = 0, "
                          "motivo_humano = NULL WHERE id = ?", (conversa_id,))
    return cur.rowcount == 1


def liberar(con, conversa_id):
    """O dono confirmou, na tela, escrever a quem saiu: vale para UMA tentativa (gasta em liberado())."""
    c = con.execute("SELECT c.contato_id, k.optout_em FROM conversas c JOIN contatos k ON k.id = c.contato_id "
                    "WHERE c.id = ?", (conversa_id,)).fetchone()
    if c is None:
        return None
    if c["optout_em"] is None:
        return False
    banco.gravar_config(con, LIBERADO, str(c["contato_id"]))
    return True


def liberado(con, contato_id):
    """Gasta a liberação do contato (um DELETE só: dois pedidos juntos não gastam duas vezes)."""
    if contato_id is None:
        return False
    cur = con.execute("DELETE FROM config WHERE chave = ? AND valor = ?", (LIBERADO, str(contato_id)))
    return cur.rowcount == 1


def dados_do_envio(con, conversa_id):
    """(telefone, contato_id) da conversa, ou None."""
    c = con.execute("SELECT k.telefone, k.id FROM conversas c JOIN contatos k ON k.id = c.contato_id "
                    "WHERE c.id = ?", (conversa_id,)).fetchone()
    return None if c is None else (c["telefone"], c["id"])


def depois_de_duplicado(app, con, instancia, r, confirmar):
    """Envio manual com a chave já ocupada: vale o estado real da linha. 'falhou' (não saiu) é o dono tentando de
    novo com o mesmo id da tela: sai outra vez na MESMA linha pelo reenviar do portão (sem chave nova). 'incerto'
    continua incerto (o dono decide em Envios incertos). 'pendente' = o 1º pedido ainda está saindo ('enviando':
    ainda pode terminar incerto ou falhou, então não vale como sucesso). Só 'enviado' é clique repetido."""
    if r["estado"] != "duplicado":
        return r
    linha = con.execute("SELECT estado, motivo FROM envios WHERE id = ?", (r["envio_id"],)).fetchone()
    if linha["estado"] == "falhou":
        novo = portao.reenviar(con, app.conector, instancia, r["envio_id"], confirmar_optout=confirmar)
        if novo["motivo"] != "nao_reenviavel":
            return novo
        linha = novo   # outro pedido reenviou antes: o estado de agora decide
    if linha["estado"] == "incerto":
        return {"estado": "incerto", "motivo": linha["motivo"], "envio_id": r["envio_id"]}
    if linha["estado"] == "pendente":
        return {"estado": "enviando", "motivo": None, "envio_id": r["envio_id"]}
    return r


def _corpo_id(corpo, chave="conversa_id"):
    valor = corpo.get(chave)
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and valor > 0 else None


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) de uma rota de /conversas ou /incertos; None = rota desconhecida."""
    achou = ROTA.match(caminho)
    if not achou:
        return None
    grupo, ident, sub, grupo_i, envio, acao = achou.groups()
    if metodo == "GET":
        if grupo and ident is None:
            return 200, listar(con, query)
        if grupo and ident not in ("aberta", None) and sub is None:
            r = abrir(con, int(ident), query)
            return (200, r) if r else (404, {"erro": "Conversa não encontrada."})
        if grupo_i and envio is None:
            return 200, incertos(con, query)
        return None
    if metodo != "POST" or corpo is None:
        return None
    if grupo and ident == "aberta" and sub is None:
        cid = _corpo_id(corpo)
        return (200, {"aberta": cid}) if cid and selecionar(con, cid) else (404, {"erro": "Conversa não encontrada."})
    if grupo and sub == "modo":
        if corpo.get("modo") not in MODOS:
            return 400, {"erro": "Modo desconhecido."}
        ok = definir_modo(con, int(ident), corpo["modo"])
        return (200, {"modo": corpo["modo"]}) if ok else (404, {"erro": "Conversa não encontrada."})
    if grupo and sub == "liberar":
        r = liberar(con, int(ident))
        if r is None:
            return 404, {"erro": "Conversa não encontrada."}
        return (200, {"liberado": True}) if r else (409, {"erro": "Este contato não pediu para sair."})
    if grupo_i and acao:
        return _decidir(app, con, int(envio), acao, corpo)
    return None


def _decidir(app, con, envio_id, acao, corpo):
    """reenviar: a MESMA linha volta a pendente pelo portão (sem chave nova). descartar: o dono diz que não saiu."""
    linha = con.execute("SELECT estado, contato_id FROM envios WHERE id = ?", (envio_id,)).fetchone()
    if linha is None:
        return 404, {"erro": "Envio não encontrado."}
    if linha["estado"] != "incerto":
        return 409, {"erro": "Este envio não está mais incerto."}
    if acao == "descartar":
        r = portao.descartar(con, envio_id)
        return 200, {"estado": r["estado"], "motivo": r["motivo"], "envio_id": envio_id}
    instancia = banco.ler_config(con, "instancia")
    if app.conector is None or not instancia:
        return 503, {"erro": "Conecte o WhatsApp primeiro."}
    confirmar = corpo.get("confirmar_optout") is True
    if not confirmar and liberado(con, linha["contato_id"]):
        confirmar = True
    r = portao.reenviar(con, app.conector, instancia, envio_id, confirmar_optout=confirmar)
    return 200, {"estado": r["estado"], "motivo": r["motivo"], "envio_id": r["envio_id"]}
