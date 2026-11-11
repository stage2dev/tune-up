"""Tela Vendas (plugin tune-up-vendas). Aba "Conexão": serviço rodando ou parado, pelo batimento no banco.
A tela só LÊ o banco (modo somente leitura) e nunca lê o arquivo do token. Python 3.9, só biblioteca padrão."""
import datetime
import importlib.util
import json
import os
import pathlib
import shlex
import sqlite3
import urllib.error
import urllib.request

PORTA = 8791  # porta padrão do serviço (servico/servico.py)
VIVO_S = 15  # batimento mais velho que isso = serviço parado (o serviço bate a cada 3 s)
TEMPO_REDE_S = 5  # toda chamada ao serviço tem tempo limite próprio (o painel não para a thread do agir)
MODOS = {"registra_e_conta": "Registra e conta", "recusa": "Recusa segredo errado"}
VALIDOS_PARA_RECUSA = 20  # o mesmo de servico/rotas.py; quem decide é o serviço

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SERVICO = os.path.join(PLUGIN, "servico", "servico.py")
EVOLUTION_LOCAL = os.path.join(PLUGIN, "servico", "evolution_local.py")

_spec = importlib.util.spec_from_file_location("tune_up_vendas_pasta", os.path.join(PLUGIN, "servico", "pasta.py"))
pasta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pasta)

INFO = {
    "id": "vendas",
    "titulo": "Vendas",
    "icone": "pessoas",
    "acoes": ["modo_webhook"],
    "negar": [
        "Bash(*127.0.0.1:%d*)" % PORTA,
        "Bash(*localhost:%d*)" % PORTA,
        "Bash(*/api/modulos/*/acao*)",
        "Bash(*tune-up-vendas*)",
        "Read(*tune-up-vendas*)",
        "Edit(*tune-up-vendas*)",
        "Write(*tune-up-vendas*)",
        "Bash(*security find-generic-password*)",
    ],
}


def _ler(raiz, base, sql):
    """Linhas de uma consulta no banco do serviço, ou None sem banco aberto. Não cria nada: modo somente leitura."""
    arquivo = os.path.join(pasta.caminho_da_pasta(raiz, base), "vendas.db")
    if not os.path.isfile(arquivo) or not os.path.exists(arquivo + "-shm"):
        return None  # sem -shm não há conexão WAL aberta (e o modo ro não consegue criá-lo): serviço parado
    con = sqlite3.connect(pathlib.Path(os.path.abspath(arquivo)).as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def ler_batimento(raiz, base=None):
    """Data UTC do último batimento do serviço deste projeto, ou None (sem pasta, sem banco, sem linha)."""
    linhas = _ler(raiz, base, "SELECT em FROM batimento WHERE id = 1")
    return datetime.datetime.fromisoformat(linhas[0][0]) if linhas else None


def ler_webhook(raiz, base=None):
    """Modo e contadores do segredo do webhook (config do banco); padrão sem banco ou sem linha."""
    linhas = _ler(raiz, base, "SELECT chave, valor FROM config WHERE chave IN ('webhook_modo', "
                           "'webhook_validos', 'webhook_invalidos', 'webhook_validos_seguidos')") or []
    conf = dict(linhas)
    numero = lambda chave: int(conf.get(chave) or 0)  # noqa: E731
    return {"modo": conf.get("webhook_modo") or "registra_e_conta", "validos": numero("webhook_validos"),
            "invalidos": numero("webhook_invalidos"), "seguidos": numero("webhook_validos_seguidos")}


def porta_do_painel(ctx):
    porta = ((ctx or {}).get("config") or {}).get("porta")
    return porta if isinstance(porta, int) and 1024 <= porta <= 65535 else 8787


def comando(ctx):
    raiz = (ctx or {}).get("raiz") or "<raiz do projeto>"
    return "python3 -B %s --projeto %s --painel http://127.0.0.1:%s" % (
        shlex.quote(SERVICO), shlex.quote(raiz), porta_do_painel(ctx))


def comando_evolution(ctx):
    raiz = (ctx or {}).get("raiz") or "<raiz do projeto>"
    return "python3 -B %s preparar --projeto %s" % (shlex.quote(EVOLUTION_LOCAL), shlex.quote(raiz))


def _pedir(metodo, url, cab, corpo=None):
    """Pedido ao serviço local com tempo limite e sem proxy. Devolve (código, objeto JSON)."""
    dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
    pedido = urllib.request.Request(url, data=dados, method=metodo, headers=cab)
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with abridor.open(pedido, timeout=TEMPO_REDE_S) as r:
            return r.status, json.loads(r.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except ValueError:
            return e.code, {}
        finally:
            e.close()


def agir(ctx, acao, dados, porta=PORTA):
    """modo_webhook: pede ao serviço a troca do modo do segredo do webhook. Quem confere os 20 válidos seguidos
    é o serviço. Repetir o mesmo modo não muda nada. O token de envio nunca volta no resultado."""
    if acao != "modo_webhook":
        return {"ok": False, "mensagem": "Ação desconhecida."}
    modo = (dados or {}).get("modo")
    if modo not in MODOS:
        return {"ok": False, "mensagem": "Escolha um modo válido."}
    base = "http://127.0.0.1:%d" % porta
    try:
        codigo, r = _pedir("GET", base + "/token-de-envio",
                           {"Origin": "http://127.0.0.1:%d" % porta_do_painel(ctx)})
        if codigo != 200 or not isinstance(r.get("token"), str):
            return {"ok": False, "mensagem": "O serviço não liberou a troca (%d). Confira se ele foi ligado com "
                                             "--painel deste painel." % codigo}
        codigo, r = _pedir("POST", base + "/modo-webhook",
                           {"X-Vendas-Token": r["token"], "Content-Type": "application/json"}, {"modo": modo})
    except (OSError, ValueError):
        return {"ok": False, "mensagem": "O serviço de Vendas não respondeu. Ligue-o e tente de novo."}
    if codigo != 200:
        return {"ok": False, "mensagem": str(r.get("erro") or "O serviço recusou a troca (%d)." % codigo)}
    return {"ok": True, "mensagem": "Modo do webhook: %s." % MODOS[modo]}


def blocos_webhook(w):
    falta = max(0, VALIDOS_PARA_RECUSA - w["seguidos"])
    return [
        {"tipo": "kpis", "titulo": "Segredo do webhook", "itens": [
            {"rotulo": "Modo", "valor": MODOS.get(w["modo"], w["modo"])},
            {"rotulo": "Válidos", "valor": w["validos"]},
            {"rotulo": "Inválidos", "valor": w["invalidos"], "tom": "atencao" if w["invalidos"] else "neutro"},
            {"rotulo": "Válidos seguidos", "valor": w["seguidos"],
             "detalhe": "pronto para recusar" if not falta else "faltam %d para poder recusar" % falta}]},
        {"tipo": "formulario", "id": "modo_webhook", "titulo": "Modo do segredo do webhook",
         "descricao": ("Em \"Registra e conta\" o webhook com segredo errado entra e é contado. \"Recusa\" "
                       "responde 401 a ele e só liga depois de %d webhooks válidos seguidos (um inválido zera "
                       "a contagem)." % VALIDOS_PARA_RECUSA),
         "acao": "modo_webhook", "botao": "Trocar modo",
         "campos": [{"id": "modo", "rotulo": "Modo", "tipo": "escolha", "valor": w["modo"], "obrigatorio": True,
                     "opcoes": [{"valor": k, "rotulo": v} for k, v in MODOS.items()]}]},
    ]


def montar(ctx, base=None):
    agora = datetime.datetime.now(datetime.timezone.utc)
    avisos = []
    try:
        quando = ler_batimento(ctx.get("raiz") or "", base) if ctx.get("raiz") else None
        webhook = ler_webhook(ctx.get("raiz") or "", base) if ctx.get("raiz") else None
    except (sqlite3.Error, ValueError) as e:
        quando = webhook = None
        avisos.append("não consegui ler o banco do serviço (%s)" % type(e).__name__)
    rodando = quando is not None and abs((agora - quando).total_seconds()) <= VIVO_S
    if rodando:
        bloco = {"tipo": "texto", "titulo": "Serviço rodando",
                 "texto": "O serviço de Vendas está rodando (último sinal às %s UTC)." % quando.strftime("%H:%M:%S")}
    else:
        bloco = {"tipo": "texto", "titulo": "Serviço parado",
                 "texto": ("O serviço de Vendas está parado. Ele só liga por um comando seu, digitado num "
                           "terminal (nunca por uma sessão do Claude). Comando: %s . Para a Evolution local "
                           "(Docker), prepare antes os arquivos com: %s" % (comando(ctx), comando_evolution(ctx)))}
    blocos = [bloco] + (blocos_webhook(webhook) if rodando and webhook else [])
    return {"avisos": avisos, "abas": [{"id": "conexao", "titulo": "Conexão", "blocos": blocos}]}
