"""Rotas da aba IA, do lado do serviço (sempre com token): estado, lista de modelos da conta, gravar/trocar/apagar
a chave da OpenAI, salvar modelo + teto diário + preço do modelo e as chaves 'IA entende áudios/imagens' com o modelo
de transcrição e o preço dele por minuto (/ia/entender). Nenhuma resposta leva a chave: só 'configurada'
e os 4 últimos. A lista de modelos fica 10 min em memória (por chave), só quando a OpenAI respondeu."""
import hashlib
import re
import threading
import time

from servico import banco, chave, cerebro, conhecimento, entender, openai_cliente, precos, rascunhos, transcricao

ROTA = re.compile(r"^/ia(?:/(modelos|chave|chave/apagar|config|modo|entender))?$")
MODELO = re.compile(r"^[A-Za-z0-9._:/-]{1,100}$")
TETO_MAX_USD = 1000
CACHE_MODELOS_S = 600
_cache_trava = threading.Lock()


def estado(app, con):
    modelo = banco.ler_config(con, "ia_modelo")
    par = precos.preco(precos.tabela(app.pasta_dados), modelo) if modelo else None
    saber = conhecimento.ler(app.raiz) if app.raiz else None
    return {"chave": chave.estado(app.pasta_dados), "modelo": modelo, "sugestao": cerebro.SUGESTAO_MODELO,
            "teto_usd": precos.ler_teto(con), "gasto_hoje_usd": round(precos.gasto_hoje(con), 6),
            "preco_conhecido": par is not None or not modelo, "preco": par,
            "precos_invalido": precos.arquivo_invalido(app.pasta_dados), "modo_padrao": rascunhos.modo_padrao(con),
            "conhecimento": None if saber is None else {
                "oferta": bool(saber["oferta"]), "tom": bool(saber["tom"]), "metodos": bool(saber["metodos"]),
                "links": len(cerebro.ler_links(app.raiz)), "avisos": saber["avisos"]},
            "entende": _entende(app, con)}


def _entende(app, con):
    modelo_t = transcricao.modelo(con)
    """A escolha do dono (sem chave da OpenAI a IA não entende nada, mas a escolha fica)."""
    return {"audio": banco.ler_config(con, entender.CONFIG["audio"]) != "0",
            "imagem": banco.ler_config(con, entender.CONFIG["imagem"]) != "0",
            "modelo_transcricao": modelo_t, "sugestao_transcricao": transcricao.SUGESTAO_MODELO,
            "preco_minuto": precos.preco_minuto(app.pasta_dados, modelo_t)}


def _gravar_entende(app, con, corpo):
    audio, imagem, modelo_t = corpo.get("audio"), corpo.get("imagem"), corpo.get("modelo_transcricao")
    if not isinstance(audio, bool) or not isinstance(imagem, bool):
        return 400, {"erro": "Escolha sim ou não para áudios e imagens."}
    if not isinstance(modelo_t, str) or not MODELO.match(modelo_t.strip()):
        return 400, {"erro": "Nome de modelo de transcrição inválido."}
    minuto = corpo.get("preco_minuto")
    if not (minuto is None or (isinstance(minuto, str) and not minuto.strip())):
        if not precos._valor_ok(_numero(minuto)):
            return 400, {"erro": "Preço por minuto inválido (maior que 0, em dólares)."}
        try:
            precos.gravar_preco(app.pasta_dados, modelo_t.strip(), _numero(minuto), None, por_minuto=True)
        except precos.PrecosInvalidos as e:
            return 400, {"erro": str(e)}
    con.execute("BEGIN IMMEDIATE")
    try:
        banco.gravar_config(con, entender.CONFIG["audio"], "1" if audio else "0")
        banco.gravar_config(con, entender.CONFIG["imagem"], "1" if imagem else "0")
        banco.gravar_config(con, "ia_modelo_transcricao", modelo_t.strip())
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return 200, {"entende": _entende(app, con)}


def _numero(valor):
    """Número do formulário ('3,50' vale), ou None."""
    if isinstance(valor, str):
        try:
            valor = float(valor.replace(",", ".").strip())
        except ValueError:
            return None
    return None if isinstance(valor, bool) or not isinstance(valor, (int, float)) else valor


def _config(app, con, corpo):
    modelo, teto = corpo.get("modelo"), _numero(corpo.get("teto_usd"))
    if not isinstance(modelo, str) or not MODELO.match(modelo.strip()):
        return 400, {"erro": "Nome de modelo inválido."}
    if teto is None or not 0 <= teto <= TETO_MAX_USD:
        return 400, {"erro": "Teto diário inválido (de 0 a %d dólares)." % TETO_MAX_USD}
    vazio = lambda v: v is None or (isinstance(v, str) and not v.strip())  # noqa: E731
    entrada, saida = corpo.get("preco_entrada"), corpo.get("preco_saida")
    if not (vazio(entrada) and vazio(saida)):   # preço é opcional, mas vem em par
        try:
            precos.gravar_preco(app.pasta_dados, modelo.strip(), _numero(entrada), _numero(saida))
        except precos.PrecosInvalidos as e:
            return 400, {"erro": str(e)}
    con.execute("BEGIN IMMEDIATE")
    try:
        banco.gravar_config(con, "ia_modelo", modelo.strip())
        banco.gravar_config(con, "ia_teto_usd", repr(float(teto)))
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return 200, {"modelo": modelo.strip(), "teto_usd": float(teto),
                 "preco": precos.preco(precos.tabela(app.pasta_dados), modelo.strip())}


def modelos(app, segredo):
    """Lista da conta: do cache (10 min, mesma chave) ou de UMA consulta à OpenAI. ErroOpenAI sobe."""
    marca = hashlib.sha256(segredo.encode("utf-8")).hexdigest()
    with _cache_trava:
        cache = getattr(app, "cache_modelos", None)   # por serviço: (marca da chave, instante, lista)
        if cache and cache[0] == marca and time.monotonic() - cache[1] < CACHE_MODELOS_S:
            return list(cache[2])
    lista = openai_cliente.listar_modelos(app.openai_url, segredo)
    with _cache_trava:
        app.cache_modelos = (marca, time.monotonic(), list(lista))
    return lista


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
                return 200, {"modelos": modelos(app, segredo)}
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
        return _config(app, con, corpo)
    if sub == "entender":
        return _gravar_entende(app, con, corpo)
    if sub == "modo":
        if corpo.get("modo") not in rascunhos.MODOS_IA:
            return 400, {"erro": "Modo desconhecido."}
        rascunhos.definir_modo_padrao(con, corpo["modo"])
        return 200, {"modo_padrao": corpo["modo"]}
    return None
