"""Rotas da aba IA, do lado do serviço (sempre com token): estado, lista de modelos da conta, gravar/trocar/apagar
a chave da OpenAI e salvar modelo + teto diário. Nenhuma resposta leva a chave: só 'configurada' e os 4 últimos."""
import re

from servico import banco, chave, cerebro, openai_cliente, precos

ROTA = re.compile(r"^/ia(?:/(modelos|chave|chave/apagar|config))?$")
MODELO = re.compile(r"^[A-Za-z0-9._:/-]{1,100}$")
TETO_MAX_USD = 1000


def estado(app, con):
    modelo = banco.ler_config(con, "ia_modelo")
    tab = precos.tabela(app.pasta_dados)
    _, conhecido = precos.preco(tab, modelo) if modelo else (None, True)
    return {"chave": chave.estado(app.pasta_dados), "modelo": modelo, "sugestao": cerebro.SUGESTAO_MODELO,
            "teto_usd": precos.ler_teto(con), "gasto_hoje_usd": round(precos.gasto_hoje(con), 6),
            "preco_conhecido": conhecido}


def _config(con, corpo):
    modelo, teto = corpo.get("modelo"), corpo.get("teto_usd")
    if not isinstance(modelo, str) or not MODELO.match(modelo.strip()):
        return 400, {"erro": "Nome de modelo inválido."}
    if isinstance(teto, str):
        try:
            teto = float(teto.replace(",", ".").strip())
        except ValueError:
            teto = None
    if isinstance(teto, bool) or not isinstance(teto, (int, float)) or not 0 <= teto <= TETO_MAX_USD:
        return 400, {"erro": "Teto diário inválido (de 0 a %d dólares)." % TETO_MAX_USD}
    con.execute("BEGIN IMMEDIATE")
    try:
        banco.gravar_config(con, "ia_modelo", modelo.strip())
        banco.gravar_config(con, "ia_teto_usd", repr(float(teto)))
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return 200, {"modelo": modelo.strip(), "teto_usd": float(teto)}


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) de uma rota /ia; None = rota desconhecida."""
    achou = ROTA.match(caminho)
    if not achou:
        return None
    sub = achou.group(1)
    if metodo == "GET":
        if sub is None:
            return 200, estado(app, con)
        if sub == "modelos":
            segredo = chave.ler(app.pasta_dados)
            if not segredo:
                return 409, {"erro": "Cole a chave da OpenAI primeiro."}
            try:
                return 200, {"modelos": openai_cliente.listar_modelos(app.openai_url, segredo)}
            except openai_cliente.ErroOpenAI as e:
                return 502, {"erro": "A OpenAI não devolveu a lista de modelos.", "codigo": e.codigo}
        return None
    if metodo != "POST" or corpo is None:
        return None
    if sub == "chave":
        try:
            chave.gravar(app.pasta_dados, corpo.get("chave"))
        except chave.ChaveInvalida as e:
            return 400, {"erro": str(e)}
        return 200, {"chave": chave.estado(app.pasta_dados)}
    if sub == "chave/apagar":
        if corpo.get("confirmar") is not True:
            return 400, {"erro": "Confirme para apagar a chave."}
        return 200, {"apagada": chave.apagar(app.pasta_dados), "chave": chave.estado(app.pasta_dados)}
    if sub == "config":
        return _config(con, corpo)
    return None
