"""Google Places (API New), opcional, com a chave DO USUÁRIO. Busca por texto (nicho + cidade) e mostra o resultado SÓ NA TELA.
Os termos do Google proíbem guardar o conteúdo de Places: por isso nada de nome, telefone ou endereço vai para banco,
arquivo ou log. O que se guarda é o `place_id` (e o nicho e a cidade da busca) quando o dono clica em Guardar.
O resultado da última busca fica só na memória do processo (uma vaga, 10 min) para a tela poder desenhá-lo; reiniciar
o serviço apaga. A chave fica num arquivo 0600 da pasta de dados (como a da OpenAI) e nenhuma rota a devolve.
Telefone do Places NÃO vira contato nem candidato: o dono usa o buscador da web ou digita o telefone do site da empresa.
A URL base vem SÓ do argumento/ambiente de subida do serviço (testes), nunca de um pedido."""
import http.client
import json
import re
import socket
import threading
import time
import urllib.error
import urllib.request

from servico import banco, chave, openai_cliente

URL_PADRAO = "https://places.googleapis.com"
VAR_URL = "VENDAS_PLACES_URL"
ARQUIVO_CHAVE = "places_chave"
CAMINHO_API = "/v1/places:searchText"
CAMPOS = "places.id,places.displayName,places.formattedAddress,places.websiteUri,places.nationalPhoneNumber"
TEMPO_S = 15
POR_BUSCA = 10
TETO_PADRAO = 50
TETO_MAX = 1000
VALE_S = 600
ATRIBUICAO = "Dados do Google Maps (Google). Resultados mostrados na hora; o serviço não os guarda."
FORMATO_ID = re.compile(r"^[A-Za-z0-9_-]{1,300}$")
_trava = threading.Lock()


class ErroPlaces(RuntimeError):
    """`mensagem` é texto simples pt-BR para o dono; nunca leva a chave nem o corpo do erro do Google."""

    def __init__(self, mensagem):
        super().__init__(mensagem)
        self.mensagem = mensagem


def _texto(valor, limite):
    if not isinstance(valor, str):
        return ""
    return re.sub(r"[\x00-\x1f\x7f]", " ", valor).strip()[:limite]


def _mensagem_http(status):
    if status in (401, 403):
        return ("O Google recusou a chave (%d). Confira se a Places API (New) está ligada no seu projeto do Google, "
                "se a cobrança está ativa e se a chave pode usar essa API." % status)
    if status == 429:
        return "O Google recusou por limite de uso (429). Espere um pouco ou aumente a cota no seu projeto do Google."
    if status == 400:
        return "O Google não aceitou o pedido (400). Confira a chave e o texto da busca."
    return "O Google devolveu um erro (%d). Tente de novo mais tarde." % status


def consultar(url_base, segredo, consulta):
    """UMA chamada de busca por texto. Devolve a lista [{place_id, nome, endereco, site, telefone}] só para a tela.
    Sem nova tentativa (cada chamada conta no teto e pode ser cobrada). ErroPlaces em qualquer falha."""
    url = url_base.rstrip("/") + CAMINHO_API
    corpo = json.dumps({"textQuery": consulta, "languageCode": "pt-BR", "pageSize": POR_BUSCA}).encode("utf-8")
    pedido = urllib.request.Request(url, data=corpo, method="POST", headers={
        "Content-Type": "application/json", "X-Goog-Api-Key": segredo, "X-Goog-FieldMask": CAMPOS})
    try:
        with openai_cliente._abridor(url).open(pedido, timeout=TEMPO_S) as r:
            bruto = r.read().decode("utf-8")
        dados = json.loads(bruto)
    except urllib.error.HTTPError as e:
        e.close()
        raise ErroPlaces(_mensagem_http(e.code))
    except (socket.timeout, TimeoutError):
        raise ErroPlaces("O Google demorou demais para responder. Tente de novo.")
    except (urllib.error.URLError, http.client.HTTPException, OSError):
        raise ErroPlaces("Não consegui falar com o Google (rede). Tente de novo.")
    except ValueError:
        raise ErroPlaces("A resposta do Google veio ilegível.")
    lugares = dados.get("places") if isinstance(dados, dict) else None
    saida = []
    for lugar in (lugares if isinstance(lugares, list) else [])[:POR_BUSCA]:
        if not isinstance(lugar, dict) or not FORMATO_ID.match(str(lugar.get("id") or "")):
            continue
        nome = lugar.get("displayName")
        saida.append({"place_id": lugar["id"], "nome": _texto(nome.get("text") if isinstance(nome, dict) else None, 200),
                      "endereco": _texto(lugar.get("formattedAddress"), 300), "site": _texto(lugar.get("websiteUri"), 300),
                      "telefone": _texto(lugar.get("nationalPhoneNumber"), 40)})
    return saida


def teto(con):
    valor = banco.ler_config(con, "places_teto_dia")
    return int(valor) if valor and valor.isdigit() else TETO_PADRAO


def usados_hoje(con):
    linha = con.execute("SELECT n FROM places_uso WHERE dia = ?", (banco.agora()[:10],)).fetchone()
    return linha["n"] if linha else 0


def reservar(con):
    """Conta UMA busca de hoje se ainda cabe no teto (uma instrução só; sem corrida entre dois cliques).
    False = teto atingido: nenhuma chamada ao Google. Conta antes de chamar: a busca que falha também pode ser cobrada."""
    limite = teto(con)
    cur = con.execute("INSERT INTO places_uso (dia, n) VALUES (?, 1) ON CONFLICT(dia) DO UPDATE SET n = n + 1 "
                      "WHERE n < ?", (banco.agora()[:10], limite)) if limite > 0 else None
    return cur is not None and cur.rowcount == 1


def estado(app, con):
    with _trava:
        ultimo = getattr(app, "places_ultimo", None)
        if ultimo and time.monotonic() - ultimo["em"] > VALE_S:
            app.places_ultimo = ultimo = None
    guardados = con.execute("SELECT place_id, nicho, cidade FROM places_guardados ORDER BY criado_em DESC, rowid DESC "
                            "LIMIT 100").fetchall()
    return {"chave": chave.estado(app.pasta_dados, ARQUIVO_CHAVE), "teto_dia": teto(con), "usados_hoje": usados_hoje(con),
            "atribuicao": ATRIBUICAO,
            "ultima": None if ultimo is None else {k: ultimo[k] for k in ("nicho", "cidade", "lugares")},
            "guardados": [dict(g) for g in guardados]}


def _campo(corpo, nome):
    valor = _texto(corpo.get(nome), 80)
    return valor or None


def buscar(app, con, corpo):
    nicho, cidade = _campo(corpo, "nicho"), _campo(corpo, "cidade")
    if not nicho or not cidade:
        return 400, {"erro": "Informe o nicho e a cidade."}
    segredo = chave.ler(app.pasta_dados, ARQUIVO_CHAVE)
    if not segredo:
        return 409, {"erro": "Cole a chave do Google Places primeiro."}
    if not reservar(con):
        return 429, {"erro": "O teto de buscas do Google de hoje (%d) acabou. Ele volta amanhã (UTC) ou você pode "
                             "aumentá-lo abaixo." % teto(con)}
    try:
        lugares = consultar(getattr(app, "places_url", URL_PADRAO), segredo, "%s em %s" % (nicho, cidade))
    except ErroPlaces as e:
        return 502, {"erro": e.mensagem}
    with _trava:
        app.places_ultimo = {"em": time.monotonic(), "nicho": nicho, "cidade": cidade, "lugares": lugares}
    return 200, {"total": len(lugares)}


def guardar(con, corpo):
    """Só place_id + nicho + cidade (os da busca). Repetir o mesmo place_id não muda nada."""
    pid, nicho, cidade = corpo.get("place_id"), _campo(corpo, "nicho"), _campo(corpo, "cidade")
    if not isinstance(pid, str) or not FORMATO_ID.match(pid) or not nicho or not cidade:
        return 400, {"erro": "Lugar inválido."}
    cur = con.execute("INSERT OR IGNORE INTO places_guardados (place_id, nicho, cidade, criado_em) VALUES (?, ?, ?, ?)",
                      (pid, nicho, cidade, banco.agora()))
    return 200, {"guardado": True, "ja": cur.rowcount == 0}


def _definir_teto(con, corpo):
    valor = corpo.get("teto_dia")
    valor = valor.strip() if isinstance(valor, str) else valor
    if isinstance(valor, bool) or not (isinstance(valor, int) or (isinstance(valor, str) and valor.isdigit())) \
            or not 0 <= int(valor) <= TETO_MAX:
        return 400, {"erro": "Teto diário inválido (de 0 a %d buscas)." % TETO_MAX}
    banco.gravar_config(con, "places_teto_dia", str(int(valor)))
    return 200, {"teto_dia": int(valor)}


ROTA = re.compile(r"^/places(?:/(chave|chave/apagar|teto|buscar|guardar))?$")


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) de uma rota /places; None = rota desconhecida."""
    achou = ROTA.match(caminho)
    if not achou:
        return None
    sub = achou.group(1)
    if metodo == "GET":
        return (200, estado(app, con)) if sub is None else None
    if metodo != "POST" or corpo is None or sub is None:
        return None
    if sub == "chave":
        try:
            chave.gravar(app.pasta_dados, corpo.get("chave"), ARQUIVO_CHAVE)
        except chave.ChaveInvalida as e:
            return 400, {"erro": str(e)}
        return 200, {"chave": chave.estado(app.pasta_dados, ARQUIVO_CHAVE)}
    if sub == "chave/apagar":
        if corpo.get("confirmar") is not True:
            return 400, {"erro": "Confirme para apagar a chave."}
        with _trava:
            app.places_ultimo = None
        return 200, {"apagada": chave.apagar(app.pasta_dados, ARQUIVO_CHAVE),
                     "chave": chave.estado(app.pasta_dados, ARQUIVO_CHAVE)}
    if sub == "teto":
        return _definir_teto(con, corpo)
    if sub == "buscar":
        return buscar(app, con, corpo)
    return guardar(con, corpo)
