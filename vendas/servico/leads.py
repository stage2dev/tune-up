"""Leads (aba Leads), do lado do serviço: lista com filtros e contagens (telefone mascarado) e importação de CSV.
Importar exige origem (por linha ou do arquivo todo) e base legal da lista fechada; telefone vira forma canônica;
repetido (qualquer variante do 9º dígito) é mesclado, nunca duplicado; o contato que já existe NÃO muda (nem origem,
nem base legal, nem opt-out). Nada do telefone vai para log, evento ou motivo de recusa."""
import csv
import io
import json
import re
from urllib.parse import parse_qs, urlsplit

from servico import banco, telefone

ARQUIVO_MAX = 2 * 1024 * 1024
LINHAS_MAX = 20000
MOTIVOS_MAX = 50
BASES_LEGAIS = ("consentimento", "cliente_existente", "contato_publico_da_empresa", "outro")
QUALIFICACOES = ("frio", "morno", "quente", "sem")
FILTRO = "leads_filtro"   # config: filtro escolhido na tela deste projeto
ROTA = re.compile(r"^/leads(?:/(filtro|importar-texto))?$")
CONTROLE = re.compile(r"[\x00-\x1f\x7f]")


class Recusa(ValueError):
    """Pedido de importação inválido (a mensagem, em pt-BR, vai para o dono)."""


def _limpo(valor, maximo):
    return CONTROLE.sub(" ", str(valor or "")).strip()[:maximo]


def base_legal(escolha, texto=None):
    """Valor gravado: um nome da lista fechada; 'outro' leva o texto livre ('outro: ...')."""
    if escolha not in BASES_LEGAIS:
        raise Recusa("Escolha a base legal da lista.")
    if escolha != "outro":
        return escolha
    livre = _limpo(texto, 200)
    if not livre:
        raise Recusa("Base legal \"outro\" precisa de um texto explicando.")
    return "outro: " + livre


def decodificar(bruto):
    """UTF-8 (com ou sem BOM); se não for UTF-8 válido, latin-1."""
    if isinstance(bruto, str):
        return bruto.lstrip("﻿")
    try:
        return bruto.decode("utf-8-sig")
    except UnicodeDecodeError:
        return bruto.decode("latin-1")


def _linhas(texto):
    primeira = texto.split("\n", 1)[0]
    separador = ";" if primeira.count(";") > primeira.count(",") else ","
    leitor = csv.reader(io.StringIO(texto, newline=""), delimiter=separador)
    cabecalho = next(leitor, None)
    nomes = [(c or "").strip().lower() for c in cabecalho or []]
    if "telefone" not in nomes:
        raise Recusa("O CSV precisa de uma coluna \"telefone\" na primeira linha (nome, telefone, origem).")
    pos = {n: nomes.index(n) for n in ("nome", "telefone", "origem") if n in nomes}
    for linha in leitor:
        if not any((c or "").strip() for c in linha):
            continue
        yield leitor.line_num, {n: (linha[i] if i < len(linha) else "") for n, i in pos.items()}


def importar(con, bruto, origem, escolha, texto_livre=None):
    """Importa o CSV numa transação só. Devolve {importados, mesclados, recusados, motivos[:50], ...} sem telefone."""
    legal = base_legal(escolha, texto_livre)
    padrao = _limpo(origem, 80)
    importados = mesclados = recusados = 0
    motivos = []

    def recusar(numero, motivo):
        nonlocal recusados
        recusados += 1
        if len(motivos) < MOTIVOS_MAX:
            motivos.append({"linha": numero, "motivo": motivo})

    con.execute("BEGIN IMMEDIATE")
    try:
        total = 0
        for numero, linha in _linhas(decodificar(bruto)):
            total += 1
            if total > LINHAS_MAX:
                raise Recusa("O CSV tem linhas demais (o máximo é %d). Divida o arquivo." % LINHAS_MAX)
            de_origem = _limpo(linha.get("origem"), 80) or padrao
            if not de_origem:
                recusar(numero, "sem origem")
                continue
            try:
                canonico = telefone.normalizar(linha["telefone"])
            except telefone.TelefoneInvalido:
                recusar(numero, "telefone inválido")
                continue
            if banco.buscar_contato(con, canonico) is not None:
                mesclados += 1  # já existia: nada muda (origem, base legal e opt-out ficam como estavam)
                continue
            banco.salvar_contato(con, canonico, _limpo(linha.get("nome"), 120) or None, de_origem, legal)
            importados += 1
        banco.registrar_evento(con, "leads_importados", json.dumps(
            {"importados": importados, "mesclados": mesclados, "recusados": recusados}))
        con.execute("COMMIT")
    except csv.Error:   # caractere nulo, campo grande demais, aspas quebradas: recusa limpa, nada entra
        con.execute("ROLLBACK")
        raise Recusa("O CSV está malformado (caractere nulo, campo grande demais ou aspas quebradas). Confira o "
                     "arquivo e tente de novo.")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return {"importados": importados, "mesclados": mesclados, "recusados": recusados, "motivos": motivos,
            "motivos_cortados": recusados > len(motivos)}


def _filtro(query, con):
    pedido = {k: (query.get(k) or [""])[0] for k in ("origem", "qualificacao", "optout", "conversa")}
    if any(pedido.values()):
        return pedido
    try:
        guardado = json.loads(banco.ler_config(con, FILTRO, "{}"))
    except ValueError:
        guardado = {}
    return {k: str(guardado.get(k) or "") for k in pedido}


def salvar_filtro(con, corpo):
    f = {"origem": _limpo(corpo.get("origem"), 80), "qualificacao": corpo.get("qualificacao") or "",
         "optout": corpo.get("optout") or "", "conversa": corpo.get("conversa") or ""}
    if f["qualificacao"] not in ("",) + QUALIFICACOES or f["optout"] not in ("", "sim", "nao") \
            or f["conversa"] not in ("", "sim", "nao"):
        return None
    banco.gravar_config(con, FILTRO, json.dumps(f, ensure_ascii=False))
    return f


def _onde(f):
    sql, args = [], []
    if f["origem"]:
        sql.append("k.origem = ?")
        args.append(f["origem"])
    if f["qualificacao"] in ("frio", "morno", "quente"):
        sql.append("c.estado = ?")
        args.append(f["qualificacao"])
    elif f["qualificacao"] == "sem":
        sql.append("(c.estado IS NULL OR c.estado NOT IN ('frio', 'morno', 'quente'))")
    if f["optout"]:
        sql.append("k.optout_em IS %sNULL" % ("NOT " if f["optout"] == "sim" else ""))
    if f["conversa"]:
        sql.append("c.id IS %sNULL" % ("NOT " if f["conversa"] == "sim" else ""))
    return (" WHERE " + " AND ".join(sql)) if sql else "", args


def _numero(query, nome, padrao, maximo):
    try:
        return max(0, min(int((query.get(nome) or [padrao])[0]), maximo))
    except (TypeError, ValueError):
        return padrao


def listar(con, query):
    f = _filtro(query, con)
    onde, args = _onde(f)
    de = "FROM contatos k LEFT JOIN conversas c ON c.contato_id = k.id"
    limite = max(1, _numero(query, "limite", 50, 100))
    linhas = con.execute("SELECT k.id, k.nome, k.telefone, k.origem, k.base_legal, k.optout_em, c.id AS conversa, "
                         "c.estado %s%s ORDER BY k.id DESC LIMIT ? OFFSET ?" % (de, onde),
                         args + [limite, _numero(query, "deslocamento", 0, 1000000)]).fetchall()
    unico = lambda sql: con.execute(sql).fetchone()[0]  # noqa: E731
    por = {r[0]: r[1] for r in con.execute(
        "SELECT estado, COUNT(*) FROM conversas WHERE estado IN ('frio', 'morno', 'quente') GROUP BY estado")}
    return {
        "filtro": f, "total_filtrado": con.execute("SELECT COUNT(*) %s%s" % (de, onde), args).fetchone()[0],
        "contagens": {"total": unico("SELECT COUNT(*) FROM contatos"),
                      "optout": unico("SELECT COUNT(*) FROM contatos WHERE optout_em IS NOT NULL"),
                      "com_conversa": unico("SELECT COUNT(*) FROM conversas"),
                      "frio": por.get("frio", 0), "morno": por.get("morno", 0), "quente": por.get("quente", 0)},
        "origens": [r[0] for r in con.execute("SELECT DISTINCT origem FROM contatos WHERE origem IS NOT NULL "
                                              "ORDER BY origem LIMIT 100")],
        "leads": [{"id": r["id"], "nome": r["nome"], "telefone_mascarado": "****" + str(r["telefone"])[-4:],
                   "origem": r["origem"], "base_legal": r["base_legal"], "saiu": r["optout_em"] is not None,
                   "tem_conversa": r["conversa"] is not None,
                   "qualificacao": r["estado"] if r["estado"] in QUALIFICACOES else None} for r in linhas]}


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) de GET /leads, POST /leads/filtro e POST /leads/importar-texto; None = rota desconhecida."""
    achou = ROTA.match(caminho)
    if not achou:
        return None
    sub = achou.group(1)
    if metodo == "GET" and sub is None:
        return 200, listar(con, query)
    if metodo != "POST" or corpo is None:
        return None
    if sub == "filtro":
        f = salvar_filtro(con, corpo)
        return (200, {"filtro": f}) if f is not None else (400, {"erro": "Filtro inválido."})
    if sub == "importar-texto":
        texto = corpo.get("texto")
        if not isinstance(texto, str) or not texto.strip():
            return 400, {"erro": "Cole o CSV."}
        if len(texto.encode("utf-8")) > ARQUIVO_MAX:
            return 413, {"erro": "Arquivo grande demais (máximo 2 MB)."}
        try:
            return 200, importar(con, texto, corpo.get("origem"), corpo.get("base_legal"), corpo.get("base_legal_texto"))
        except Recusa as e:
            return 400, {"erro": str(e)}
    return None


def receber_csv(h, app, autorizado):
    """POST /leads/importar: corpo text/csv de até 2 MB; origem e base_legal pela query. Token obrigatório.
    `h` é o handler (rotas.py); aqui nada do pedido vai para log."""
    h.close_connection = True
    if not autorizado:
        return h._erro(403, "Token de envio errado.")
    if (h.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower() != "text/csv":
        return h._erro(415, "O corpo precisa ser text/csv.")
    if h.headers.get("Transfer-Encoding"):
        return h._erro(411, "Mande o tamanho do pedido.")
    try:
        tamanho = int(h.headers.get("Content-Length") or "0")
    except ValueError:
        tamanho = -1
    if tamanho <= 0:
        return h._erro(400, "Tamanho do pedido inválido.")
    if tamanho > ARQUIVO_MAX:
        restante = min(tamanho, 16 * ARQUIVO_MAX)  # escoa para o cliente receber o 413 (e não um reset)
        while restante > 0:
            lido = h.rfile.read(min(restante, 65536))
            if not lido:
                break
            restante -= len(lido)
        return h._erro(413, "Arquivo grande demais (máximo 2 MB).")
    query = parse_qs(urlsplit(h.path).query)
    pega = lambda nome: (query.get(nome) or [None])[0]  # noqa: E731
    bruto = h.rfile.read(tamanho)
    con = app.abrir()
    try:
        r = importar(con, bruto, pega("origem"), pega("base_legal"), pega("base_legal_texto"))
    except Recusa as e:
        return h._erro(400, str(e))
    finally:
        con.close()
    h._json(200, r)
