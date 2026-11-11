"""Modos da IA por conversa e rascunhos. 'rascunho' (padrão): a IA escreve, nada sai; o dono aprova, edita ou descarta
na aba Conversas e a aprovação sai pelo portão com a origem fixa 'rascunho_aprovado' (chave = id do rascunho, então
aprovar duas vezes envia uma). 'automatico': a IA envia (origem 'ia'). O modo da conversa (conversas.modo_ia) vale
sobre o padrão do projeto (config ia_modo_padrao, 'rascunho' se faltar). Um rascunho novo substitui o pendente da
conversa; passa de 24 h e deixa de poder ser aprovado; opt-out depois do rascunho = negado no portão.
Rascunho 'enviar como áudio' (como_audio, a IA usou responder_em_audio): nada é gerado antes da aprovação; aprovar
gera e manda o áudio (origem audio_ia, chave audio_ia:rascunho:<id>) e os links em texto (rascunho_aprovado); falha
da voz = o texto inteiro sai como rascunho_aprovado (servico/audio_ia.py). Links que não saíram depois do áudio =
estado 'parcial', evento e "precisa de você"; aprovar de novo manda só os links (o áudio não é gerado de novo)."""
import datetime
import json
import logging
import re
import sqlite3

from servico import audio_ia, banco, cerebro, conversas, portao, saida

UTC = datetime.timezone.utc
MODOS_IA = ("rascunho", "automatico")
PADRAO = "ia_modo_padrao"
VALIDADE = datetime.timedelta(hours=24)
TEXTO_MAX = saida.CARACTERES_MAX
OCUPADO = "Este rascunho está sendo enviado agora. Aguarde e atualize a conversa."
LOG = logging.getLogger(__name__)
OK = ("enviado", "incerto", "enviando", "duplicado")   # saiu, pode ter saído ou já tinha saído
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
    """O rascunho pendente da conversa ({id, texto, criado_em, expirado, como_audio}) ou None."""
    r = con.execute("SELECT id, texto, criado_em, como_audio FROM rascunhos WHERE conversa_id = ? AND estado = 'pendente'",
                    (conversa_id,)).fetchone()
    if r is None:
        return None
    return {"id": r["id"], "texto": r["texto"], "criado_em": r["criado_em"], "como_audio": bool(r["como_audio"]),
            "expirado": _expirado(r["criado_em"], agora or datetime.datetime.now(UTC))}


def guardar(con, conversa_id, gatilho_id, texto, permitidos=(), segredos=(), reescrever=None, como_audio=False):
    """Passa o texto da IA pelo mesmo sanitizador da saída e guarda como rascunho (nada é enviado). Barrado = a
    conversa fica 'precisa de você'. O rascunho novo troca o pendente; o mesmo gatilho não gera dois."""
    pronto, motivo = saida.preparar(texto, permitidos, segredos, reescrever)
    if pronto is None:
        return saida._barrar(con, conversa_id, motivo)
    if como_audio:   # o dono vê a fala exata (já cortada) e os links embaixo
        pronto = audio_ia.para_rascunho(pronto)
    quando = banco.agora()
    con.execute("BEGIN IMMEDIATE")
    try:
        if con.execute("SELECT 1 FROM rascunhos WHERE conversa_id = ? AND estado = 'aprovando'",
                       (conversa_id,)).fetchone() is not None:
            con.execute("ROLLBACK")   # o dono está enviando o anterior: este texto não sabe disso, o dono decide
            return saida._barrar(con, conversa_id, "rascunho_em_aprovacao")
        con.execute("UPDATE rascunhos SET estado = 'substituido', decidido_em = ? WHERE conversa_id = ? "
                    "AND estado = 'pendente'", (quando, conversa_id))
        cur = con.execute("INSERT INTO rascunhos (conversa_id, mensagem_id, texto, criado_em, como_audio) VALUES "
                          "(?, ?, ?, ?, ?)", (conversa_id, gatilho_id, pronto, quando, 1 if como_audio else 0))
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


def _fechar(con, rascunho_id, estado, de="pendente"):
    return con.execute("UPDATE rascunhos SET estado = ?, decidido_em = ? WHERE id = ? AND estado = ?",
                       (estado, banco.agora(), rascunho_id, de)).rowcount


def _decidir(con, rascunho_id, estado):
    """Fecha o rascunho travado ('aprovando'); a trava é desta aprovação, então 0 linhas é defeito e vai para o log."""
    if estado == "pendente":   # não saiu (teto, recusa): volta para o dono decidir de novo
        n = con.execute("UPDATE rascunhos SET estado = 'pendente' WHERE id = ? AND estado = 'aprovando'",
                        (rascunho_id,)).rowcount
    else:
        n = _fechar(con, rascunho_id, estado, "aprovando")
    if n != 1:
        banco.registrar_evento(con, "rascunho_sem_trava", json.dumps({"rascunho_id": rascunho_id, "estado": estado}))
        LOG.error("rascunho %d: a trava sumiu ao fechar como %s", rascunho_id, estado)


def _travar(con, rascunho_id, final, chave):
    """Numa transação: confere a tentativa anterior e passa o rascunho de pendente a 'aprovando' com o texto final.
    None = travou; senão (código, objeto) da recusa."""
    con.execute("BEGIN IMMEDIATE")
    try:
        antes = con.execute("SELECT conteudo FROM envios WHERE chave_dedupe = ? AND estado <> 'negado'",
                            (chave,)).fetchone()
        if antes is not None and antes["conteudo"] != final:
            con.execute("ROLLBACK")
            return 409, {"erro": "Este rascunho já foi tentado com o texto anterior. Aprove sem editar para tentar de "
                                 "novo, ou descarte e escreva uma mensagem nova."}
        n = con.execute("UPDATE rascunhos SET estado = 'aprovando', texto = ? WHERE id = ? AND estado = 'pendente'",
                        (final, rascunho_id)).rowcount
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return None if n == 1 else (409, {"erro": OCUPADO})


def aprovar(app, con, rascunho_id, texto=None, agora=None):
    """(código, objeto). Texto novo = o dono editou. Antes do portão o rascunho é travado ('aprovando'): descartar,
    outra aprovação e um rascunho novo da IA esperam por ela. O portão decide e dedupa; o rascunho só vira 'aprovado'
    quando a mensagem saiu (ou pode ter saído); recusa passageira (teto) devolve a pendente, opt-out o encerra.
    Tentativa anterior com outro texto (falhou) não é reenviada com o texto velho: 409."""
    agora = agora or datetime.datetime.now(UTC)
    r = con.execute("SELECT d.id, d.conversa_id, d.estado, d.texto, d.criado_em, d.como_audio, k.telefone FROM "
                    "rascunhos d JOIN conversas c ON c.id = d.conversa_id JOIN contatos k ON k.id = c.contato_id "
                    "WHERE d.id = ?",
                    (rascunho_id,)).fetchone()
    if r is None:
        return 404, {"erro": "Rascunho não encontrado."}
    if r["estado"] == "aprovando":
        return 409, {"erro": OCUPADO}
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
    travou = r["estado"] == "pendente"
    if travou:
        recusa = _travar(con, rascunho_id, final, "rascunho_aprovado:%d" % rascunho_id)
        if recusa is not None:
            return recusa
    elif final != r["texto"]:   # já aprovado: o portão só dedupa, um texto diferente nunca sai por aqui
        return 409, {"erro": "Este rascunho já foi enviado com outro texto."}
    try:
        res, texto_envio = audio_ia.aprovar(app, con, instancia, r["telefone"], final, rascunho_id) \
            if r["como_audio"] else (None, final)
        if texto_envio:   # o texto, ou só os links depois do áudio
            res_texto = portao.enviar_rascunho_aprovado(con, app.conector, instancia, r["telefone"], texto_envio,
                                                        rascunho_id, agora=agora)
            res_texto = conversas.depois_de_duplicado(app, con, instancia, res_texto, False)
            if res is None:
                res = res_texto
            elif res_texto["estado"] not in OK:   # o áudio saiu (ou já tinha saído) e os links não
                res = _links_perdidos(con, r["conversa_id"], rascunho_id, res_texto)
            elif res["estado"] == "duplicado":   # áudio de antes: vale o que os links fizeram agora
                res = res_texto
    except BaseException:
        if travou:
            _decidir(con, rascunho_id, "pendente")
        raise
    if travou:
        if res["estado"] in OK + ("parcial",):
            _decidir(con, rascunho_id, "aprovado")
        elif res["estado"] == "negado" and res["motivo"] == "optout":
            _decidir(con, rascunho_id, "negado")
        else:
            _decidir(con, rascunho_id, "pendente")
    return 200, {"estado": res["estado"], "motivo": res["motivo"], "envio_id": res.get("envio_id")}


def _links_perdidos(con, conversa_id, rascunho_id, res_texto):
    """O áudio saiu e o balão de links não: o dono fica sabendo (evento e "precisa de você"); aprovar de novo reenvia
    os links na mesma linha do portão."""
    banco.registrar_evento(con, "rascunho_links_nao_sairam", json.dumps(
        {"conversa_id": conversa_id, "rascunho_id": rascunho_id, "estado": res_texto["estado"],
         "motivo": res_texto.get("motivo")}))
    cerebro.marcar_precisa_de_voce(con, conversa_id, "rascunho_links_nao_sairam")
    return {"estado": "parcial", "motivo": "rascunho_links_nao_sairam", "envio_id": res_texto.get("envio_id")}


def destravar_na_subida(con):
    """Subida do serviço (depois de portao.pendentes_para_incerto): nenhuma aprovação está em curso, então todo
    'aprovando' é de um processo que caiu. Envio que saiu ou pode ter saído = 'aprovado' (sem reenvio); sem envio, ou
    envio que falhou ou foi negado = volta a 'pendente' para o dono decidir. Devolve quantos destravou."""
    con.execute("BEGIN IMMEDIATE")
    try:
        travados = [l["id"] for l in con.execute("SELECT id FROM rascunhos WHERE estado = 'aprovando'")]
        for rid in travados:
            envio = con.execute("SELECT estado FROM envios WHERE chave_dedupe IN (?, ?) AND estado <> 'negado' ORDER BY "
                                "estado IN ('enviado', 'incerto', 'pendente') DESC LIMIT 1", ("rascunho_aprovado:%d" % rid,
                                                                                            "audio_ia:rascunho:%d" % rid)
                                ).fetchone()   # o texto ou o áudio do rascunho
            estado = "aprovado" if envio is not None and envio["estado"] in ("enviado", "incerto", "pendente") \
                else "pendente"
            if estado == "aprovado":
                n = _fechar(con, rid, "aprovado", "aprovando")
            else:
                n = con.execute("UPDATE rascunhos SET estado = 'pendente' WHERE id = ? AND estado = 'aprovando'",
                                (rid,)).rowcount
            if n != 1:
                raise RuntimeError("rascunho %d: não destravou" % rid)
            banco.registrar_evento(con, "rascunho_destravado_na_subida", json.dumps(
                {"rascunho_id": rid, "estado": estado, "envio": None if envio is None else envio["estado"]}))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    return len(travados)


def descartar(con, rascunho_id):
    if _fechar(con, rascunho_id, "descartado") == 1:
        return 200, {"estado": "descartado"}
    achou = con.execute("SELECT estado FROM rascunhos WHERE id = ?", (rascunho_id,)).fetchone()
    if achou is None:
        return 404, {"erro": "Rascunho não encontrado."}
    return 409, {"erro": OCUPADO if achou["estado"] == "aprovando" else
                 "Este rascunho já foi decidido (%s)." % achou["estado"]}


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
