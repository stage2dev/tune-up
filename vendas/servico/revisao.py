"""Revisão humana dos candidatos do buscador (aba Buscador), do lado do serviço, sempre com token.
O candidato só vira lead (linha em `contatos`) quando o dono aprova: origem 'buscador: <nicho>/<cidade>', base legal
'contato_publico_da_empresa'. Telefone que já é contato é mesclado (nada muda nele, nem o opt-out). Descartado fica
30 dias como 'descartado' (não é sugerido de novo) e é apagado na subida do serviço. Nada devolve o telefone inteiro."""
import datetime
import json
import re

from servico import banco, candidatos

ROTA = re.compile(r"^/candidatos(?:/(filtro)|/(\d{1,12})/(aprovar|descartar))?$")
FILTRO = "candidatos_filtro"
ESTADOS = ("novo", "aprovado", "descartado")
BASE_LEGAL = "contato_publico_da_empresa"
DIAS_DESCARTADO = 30
LIMITE_LISTA = 20


def origem_de(c):
    return ("buscador: %s/%s" % (c["nicho"] or "sem nicho", c["cidade"] or "sem cidade"))[:80]


def _decidir(con, cid, fazer):
    """Roda `fazer(candidato)` numa transação só; (código, objeto)."""
    con.execute("BEGIN IMMEDIATE")
    try:
        c = con.execute("SELECT * FROM candidatos WHERE id = ?", (cid,)).fetchone()
        r = (404, {"erro": "Candidato não encontrado (talvez já tenha sido apagado)."}) if c is None else fazer(c)
        con.execute("COMMIT")
        return r
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def aprovar(con, cid):
    def fazer(c):
        if c["estado"] == "aprovado":
            return 200, {"ja": True, "contato_id": c["contato_id"]}  # duplo clique: nada de segundo contato
        if c["estado"] != "novo":
            return 409, {"erro": "Este candidato foi descartado."}
        if not c["telefone"]:
            return 409, {"erro": "Este candidato não tem telefone publicado: não dá para virar lead."}
        existente = banco.buscar_contato(con, c["telefone"])  # mescla: o contato que já existe não muda
        contato_id = existente["id"] if existente is not None else banco.salvar_contato(
            con, c["telefone"], c["nome"][:120], origem_de(c), BASE_LEGAL)
        banco._exigir(con.execute("UPDATE candidatos SET estado = 'aprovado', decidido_em = ?, contato_id = ? "
                                  "WHERE id = ? AND estado = 'novo'", (banco.agora(), contato_id, cid)))
        banco.registrar_evento(con, "candidato_aprovado", json.dumps(
            {"candidato_id": cid, "contato_id": contato_id, "mesclado": existente is not None}))
        return 200, {"ja": False, "contato_id": contato_id, "mesclado": existente is not None}
    return _decidir(con, cid, fazer)


def descartar(con, cid):
    def fazer(c):
        if c["estado"] == "descartado":
            return 200, {"ja": True}
        if c["estado"] != "novo":
            return 409, {"erro": "Este candidato já virou lead."}
        banco._exigir(con.execute("UPDATE candidatos SET estado = 'descartado', decidido_em = ? "
                                  "WHERE id = ? AND estado = 'novo'", (banco.agora(), cid)))
        return 200, {"ja": False}
    return _decidir(con, cid, fazer)


def purgar(con, dias=DIAS_DESCARTADO, agora=None):
    """Apaga os descartados há mais de `dias` dias. Devolve quantos."""
    limite = ((agora or datetime.datetime.now(datetime.timezone.utc)) - datetime.timedelta(days=dias)).isoformat(
        timespec="seconds")
    cur = con.execute("DELETE FROM candidatos WHERE estado = 'descartado' AND decidido_em < ?", (limite,))
    return cur.rowcount


def _filtro(con):
    try:
        g = json.loads(banco.ler_config(con, FILTRO, "{}"))
    except ValueError:
        g = {}
    f = {k: str(g.get(k) or "")[:100] for k in ("nicho", "cidade")}
    f["estado"] = g.get("estado") if g.get("estado") in ESTADOS else "novo"
    return f


def salvar_filtro(con, corpo):
    estado = corpo.get("estado") or "novo"
    if estado not in ESTADOS:
        return None
    f = {k: str(corpo.get(k) or "").strip()[:100] for k in ("nicho", "cidade")}
    f["estado"] = estado
    banco.gravar_config(con, FILTRO, json.dumps(f, ensure_ascii=False))
    return f


def listar(con):
    f = _filtro(con)
    onde, args = ["estado = ?"], [f["estado"]]
    for k in ("nicho", "cidade"):
        if f[k]:
            onde.append("%s = ?" % k)
            args.append(f[k])
    onde = " WHERE " + " AND ".join(onde)
    linhas = con.execute("SELECT id, nome, site, telefone, url_da_fonte, nicho, cidade FROM candidatos%s "
                         "ORDER BY id DESC LIMIT ?" % onde, args + [LIMITE_LISTA]).fetchall()
    distintos = lambda col: [r[0] for r in con.execute(  # noqa: E731
        "SELECT DISTINCT %s FROM candidatos WHERE %s IS NOT NULL ORDER BY %s LIMIT 100" % (col, col, col))]
    return {"filtro": f, "total_filtrado": con.execute("SELECT COUNT(*) FROM candidatos" + onde, args).fetchone()[0],
            "contagens": {e: con.execute("SELECT COUNT(*) FROM candidatos WHERE estado = ?", (e,)).fetchone()[0]
                          for e in ESTADOS},
            "nichos": distintos("nicho"), "cidades": distintos("cidade"),
            "candidatos": [{"id": r["id"], "nome": r["nome"], "site": r["site"], "url_da_fonte": r["url_da_fonte"],
                            "nicho": r["nicho"], "cidade": r["cidade"],
                            "telefone_mascarado": ("****" + r["telefone"][-4:]) if r["telefone"] else None}
                           for r in linhas]}


def executar(app, con, metodo, caminho, query, corpo):
    """GET /candidatos, POST /candidatos/filtro e POST /candidatos/<id>/aprovar|descartar; None = rota desconhecida."""
    achou = ROTA.match(caminho)
    if not achou:
        return None
    if metodo == "GET" and not (achou.group(1) or achou.group(2)):
        return 200, listar(con)
    if metodo != "POST" or corpo is None:
        return None
    if achou.group(1):
        f = salvar_filtro(con, corpo)
        return (200, {"filtro": f}) if f is not None else (400, {"erro": "Filtro inválido."})
    if achou.group(2):
        acao = aprovar if achou.group(3) == "aprovar" else descartar
        return acao(con, int(achou.group(2)))
    return None
