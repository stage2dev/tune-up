"""Aba Disparos, do lado do serviço (sempre com token): estado das campanhas (progresso por contato, motivos
agrupados, pausa com motivo), aquecimento de hoje, janela, prévia de 3 mensagens e criação da campanha a partir de
um filtro de leads. Ativar, pausar e retomar continuam em campanha.py (/campanhas/<id>/...). Nada aqui devolve
telefone: nem inteiro nem mascarado."""
import datetime
import re

from servico import banco, campanha, leads, modelo, portao

ROTA = re.compile(r"^/disparos(?:/(previa|criar))?$")
AMOSTRAS = 3
CAMPANHAS_MAX = 50


def _filtro(corpo):
    """Filtro de seleção validado, ou None. Quem saiu (opt-out) nunca entra na seleção."""
    f = {"origem": leads._limpo(corpo.get("origem"), 80), "qualificacao": corpo.get("qualificacao") or "",
         "base_legal": corpo.get("base_legal") or ""}
    if f["qualificacao"] not in ("",) + leads.QUALIFICACOES or f["base_legal"] not in ("",) + leads.BASES_LEGAIS:
        return None
    return f


def _selecionar(con, f):
    """Contatos que batem com o filtro (sem opt-out), do mais antigo ao mais novo: [(id, nome, origem)]."""
    onde, args = leads._onde(dict(f, optout="nao", conversa=""))
    if f["base_legal"] == "outro":
        onde += " AND k.base_legal LIKE 'outro:%'"
    elif f["base_legal"]:
        onde += " AND k.base_legal = ?"
        args = args + [f["base_legal"]]
    return con.execute("SELECT k.id, k.nome, k.origem FROM contatos k LEFT JOIN conversas c ON c.contato_id = k.id"
                       "%s ORDER BY k.id" % onde, args).fetchall()


def _novos(con, ids):
    """Quantos desses contatos nunca receberam nada desta instância (contam no aquecimento do dia)."""
    instancia = banco.ler_config(con, "instancia")
    if not ids or not instancia:
        return len(ids)
    marcas = ",".join("?" * len(campanha.ATIVOS))
    ja = {r[0] for r in con.execute("SELECT DISTINCT contato_id FROM envios WHERE instancia = ? AND estado IN (%s) "
                                    "AND contato_id IS NOT NULL" % marcas, (instancia,) + campanha.ATIVOS)}
    return sum(1 for i in ids if i not in ja)


def _amostras(app, con, texto, linhas):
    empresa = banco.ler_config(con, "empresa")
    saida = []
    for _, nome, origem in linhas[:AMOSTRAS]:
        r, motivo = modelo.renderizar(texto, nome, origem, empresa, campanha._permitidos(app))
        saida.append({"texto": r, "motivo": motivo})
    return saida


def previa(app, con, corpo):
    f = _filtro(corpo)
    if f is None:
        return 400, {"erro": "Filtro inválido."}
    linhas = _selecionar(con, f)
    ids = [r[0] for r in linhas]
    try:
        modelo.validar(corpo.get("modelo"), banco.ler_config(con, "empresa"), campanha._permitidos(app))
    except modelo.ModeloRecusado as e:
        return 400, {"erro": str(e)}
    return 200, {"total": len(ids), "novos": _novos(con, ids), "frios": sum(1 for i in ids if campanha.fria(con, i)),
                 "amostras": _amostras(app, con, corpo["modelo"], linhas)}


def criar(app, con, corpo):
    f = _filtro(corpo)
    if f is None:
        return 400, {"erro": "Filtro inválido."}
    ids = [r[0] for r in _selecionar(con, f)]
    if not ids:
        return 400, {"erro": "Nenhum contato bate com este filtro (quem saiu nunca entra)."}
    return campanha._criar_rota(app, con, {"nome": corpo.get("nome"), "modelo": corpo.get("modelo"),
                                           "contato_ids": ids})


def janela(con, agora=None):
    tz = portao.fuso(con)
    if tz is None:
        return {"fuso_ok": False, "dentro": False, "abre": portao.JANELA[0], "fecha": portao.JANELA[1]}
    local = (agora or datetime.datetime.now(datetime.timezone.utc)).astimezone(tz)
    return {"fuso_ok": True, "dentro": portao.JANELA[0] <= local.hour < portao.JANELA[1],
            "hora": local.strftime("%H:%M"), "abre": portao.JANELA[0], "fecha": portao.JANELA[1]}


def aquecimento(con, agora=None):
    """Teto de contatos NOVOS de hoje e quantos já foram usados (None sem instância ou fuso inválido)."""
    instancia, tz = banco.ler_config(con, "instancia"), portao.fuso(con)
    if not instancia or tz is None:
        return None
    local = (agora or datetime.datetime.now(datetime.timezone.utc)).astimezone(tz)
    inicio = portao._iso(local.replace(hour=0, minute=0, second=0, microsecond=0))
    return {"teto": portao.teto_contatos_novos(con, local.date(), instancia),
            "usados": portao.contatos_novos_no_dia(con, inicio, instancia)}


def _progresso(con, c, app):
    cid = c["id"]
    c["motivos"] = [{"motivo": r["motivo"], "estado": r["estado"], "n": r["n"]} for r in con.execute(
        "SELECT motivo, estado, COUNT(*) AS n FROM campanha_contatos WHERE campanha_id = ? AND motivo IS NOT NULL "
        "AND estado IN ('negado', 'pulado', 'pendente', 'falhou') GROUP BY motivo, estado ORDER BY n DESC", (cid,))]
    c["saiu"] = con.execute("SELECT COUNT(*) FROM campanha_contatos cc JOIN contatos k ON k.id = cc.contato_id "
                            "WHERE cc.campanha_id = ? AND k.optout_em IS NOT NULL", (cid,)).fetchone()[0]
    c["fria"] = any(campanha.fria(con, r[0]) for r in con.execute(
        "SELECT contato_id FROM campanha_contatos WHERE campanha_id = ?", (cid,))) if c["estado"] == "rascunho" \
        else False
    c["amostras"] = []
    if c["estado"] == "rascunho":
        linhas = con.execute("SELECT k.id, k.nome, k.origem FROM campanha_contatos cc JOIN contatos k ON "
                             "k.id = cc.contato_id WHERE cc.campanha_id = ? ORDER BY cc.ordem LIMIT ?",
                             (cid, AMOSTRAS)).fetchall()
        c["amostras"] = _amostras(app, con, con.execute("SELECT modelo FROM campanhas WHERE id = ?",
                                                        (cid,)).fetchone()[0], linhas)
    return c


def estado(app, con):
    campanhas = [_progresso(con, c, app) for c in campanha.listar(con)["campanhas"][:CAMPANHAS_MAX]]
    return {"campanhas": campanhas, "empresa": banco.ler_config(con, "empresa") or None,
            "numero_descartavel": banco.ler_config(con, "numero_descartavel") == "1",
            "janela": janela(con), "aquecimento": aquecimento(con),
            "origens": [r[0] for r in con.execute("SELECT DISTINCT origem FROM contatos WHERE origem IS NOT NULL "
                                                  "ORDER BY origem LIMIT 100")]}


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) de GET /disparos e POST /disparos/previa|criar; None = rota desconhecida."""
    sub = ROTA.match(caminho).group(1)
    if metodo == "GET" and sub is None:
        return 200, estado(app, con)
    if metodo != "POST" or sub is None:
        return None
    corpo = corpo if isinstance(corpo, dict) else {}
    return previa(app, con, corpo) if sub == "previa" else criar(app, con, corpo)
