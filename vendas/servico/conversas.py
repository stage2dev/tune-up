"""Leitura e ações da aba Conversas, do lado do serviço: lista (telefone mascarado), conversa aberta (últimas 50
mensagens + envios que ainda não voltaram como eco), envios 'incerto', modo humano/IA, seleção da conversa aberta e
liberação de UM envio a quem saiu. O envio em si é sempre do portão (portao.py); aqui nada chama o conector."""
import datetime
import re

from servico import banco, portao

LIMITE_PADRAO = 50
LIMITE_MAX = 100
PREVIA = 80
MODOS = ("ia", "humano")
LIBERADO = "liberado_contato"   # config: contato (um só) que o dono liberou para UMA mensagem apesar do opt-out
ABERTA = "conversa_aberta"      # config: conversa selecionada na tela deste projeto
ROTA = re.compile(r"^/(?:(conversas)(?:/(aberta|\d{1,12})(?:/(modo|liberar))?)?|(incertos)(?:/(\d{1,12})/"
                  r"(reenviar|descartar))?)$")


def mascarar(numero):
    """Só os 4 últimos dígitos; a lista nunca leva o telefone inteiro."""
    return "****" + str(numero or "")[-4:]


def _previa(texto, tipo):
    if not texto:
        return "[%s]" % (tipo or "mensagem")
    return texto if len(texto) <= PREVIA else texto[:PREVIA - 1] + "…"


def _limite(query):
    try:
        valor = int((query.get("limite") or [LIMITE_PADRAO])[0])
    except (TypeError, ValueError):
        valor = LIMITE_PADRAO
    return max(1, min(valor, LIMITE_MAX))


def _deslocamento(query):
    try:
        return max(0, min(int((query.get("deslocamento") or [0])[0]), 1000000))
    except (TypeError, ValueError):
        return 0


def listar(con, query, agora=None):
    momento = agora or datetime.datetime.now(datetime.timezone.utc)
    linhas = con.execute(
        "SELECT c.id, c.contato_id, c.modo, c.precisa_de_voce, k.nome, k.telefone, k.optout_em, "
        "(SELECT texto FROM mensagens m WHERE m.conversa_id = c.id ORDER BY m.id DESC LIMIT 1) AS ultima, "
        "(SELECT tipo FROM mensagens m WHERE m.conversa_id = c.id ORDER BY m.id DESC LIMIT 1) AS ultima_tipo, "
        "(SELECT criado_em FROM mensagens m WHERE m.conversa_id = c.id ORDER BY m.id DESC LIMIT 1) AS ultima_em "
        "FROM conversas c JOIN contatos k ON k.id = c.contato_id "
        "ORDER BY COALESCE(ultima_em, c.criado_em) DESC, c.id DESC LIMIT ? OFFSET ?",
        (_limite(query), _deslocamento(query))).fetchall()
    total = con.execute("SELECT COUNT(*) FROM conversas").fetchone()[0]
    return {"total": total, "aberta": aberta(con), "conversas": [
        {"id": r["id"], "nome": r["nome"], "telefone_mascarado": mascarar(r["telefone"]), "modo": r["modo"],
         "precisa_de_voce": bool(r["precisa_de_voce"]), "saiu": r["optout_em"] is not None,
         "ia_pausada": portao._pausada(con, r["contato_id"], momento),
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
    if con.execute("SELECT 1 FROM conversas WHERE id = ?", (conversa_id,)).fetchone() is None:
        return False
    banco.gravar_config(con, ABERTA, str(conversa_id))
    return True


def abrir(con, conversa_id, query, agora=None):
    """A conversa com o telefone inteiro e as últimas mensagens (no máximo 50 por padrão, 100 no teto)."""
    momento = agora or datetime.datetime.now(datetime.timezone.utc)
    c = con.execute("SELECT c.id, c.contato_id, c.modo, c.precisa_de_voce, k.nome, k.telefone, k.optout_em "
                    "FROM conversas c JOIN contatos k ON k.id = c.contato_id WHERE c.id = ?",
                    (conversa_id,)).fetchone()
    if c is None:
        return None
    limite = _limite(query)
    itens = []
    for m in con.execute("SELECT m.id, m.direcao, m.tipo, m.texto, m.criado_em, e.origem, e.estado, e.motivo "
                         "FROM mensagens m LEFT JOIN envios e ON e.id = m.envio_id WHERE m.conversa_id = ? "
                         "ORDER BY m.id DESC LIMIT ?", (conversa_id, limite)):
        de = "contato" if m["direcao"] == "entrada" else ("ia" if m["origem"] in ("ia", "audio_ia") else "eu")
        itens.append({"id": "m%d" % m["id"], "de": de, "texto": m["texto"] or "[%s]" % (m["tipo"] or "mensagem"),
                      "quando": m["criado_em"], "estado": m["estado"], "motivo": m["motivo"]})
    for e in con.execute("SELECT e.id, e.origem, e.estado, e.motivo, e.conteudo, e.tipo, e.tentado_em FROM envios e "
                         "WHERE e.contato_id = ? AND NOT EXISTS (SELECT 1 FROM mensagens m WHERE m.envio_id = e.id) "
                         "ORDER BY e.id DESC LIMIT ?", (c["contato_id"], limite)):
        itens.append({"id": "e%d" % e["id"], "de": "ia" if e["origem"] in ("ia", "audio_ia") else "eu",
                      "texto": e["conteudo"] if e["tipo"] == "texto" else "[áudio]", "quando": e["tentado_em"],
                      "estado": e["estado"], "motivo": e["motivo"]})
    itens.sort(key=lambda i: (i["quando"] or "", int(i["id"][1:])))
    return {"conversa": {"id": c["id"], "nome": c["nome"], "telefone": c["telefone"], "modo": c["modo"],
                         "precisa_de_voce": bool(c["precisa_de_voce"]), "saiu": c["optout_em"] is not None,
                         "ia_pausada": portao._pausada(con, c["contato_id"], momento),
                         "liberado": banco.ler_config(con, LIBERADO) == str(c["contato_id"])},
            "mensagens": itens[-limite:]}


def incertos(con, query):
    linhas = con.execute("SELECT id, origem, telefone, conteudo, motivo, tentado_em FROM envios "
                         "WHERE estado = 'incerto' ORDER BY id DESC LIMIT ? OFFSET ?",
                         (_limite(query), _deslocamento(query))).fetchall()
    total = con.execute("SELECT COUNT(*) FROM envios WHERE estado = 'incerto'").fetchone()[0]
    return {"total": total, "incertos": [
        {"id": r["id"], "origem": r["origem"], "telefone_mascarado": mascarar(r["telefone"]),
         "previa": _previa(r["conteudo"], "áudio"), "motivo": r["motivo"], "quando": r["tentado_em"]}
        for r in linhas]}


def definir_modo(con, conversa_id, modo):
    """Assumir (humano; a IA para e o aviso 'precisa de você' sai) ou devolver (IA; a pausa acaba). False = não existe."""
    if modo == "humano":
        cur = con.execute("UPDATE conversas SET modo = 'humano', precisa_de_voce = 0 WHERE id = ?", (conversa_id,))
    else:
        cur = con.execute("UPDATE conversas SET modo = 'ia', pausada_ate = NULL WHERE id = ?", (conversa_id,))
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
    continua incerto (o dono decide em Envios incertos). Só 'enviado'/'pendente' são clique repetido."""
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
