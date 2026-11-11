"""Tela Vendas (plugin tune-up-vendas). Aba "Conexão": serviço rodando ou parado, pelo batimento no banco.
A tela só LÊ o banco (modo somente leitura) e nunca lê o arquivo do token. Python 3.9, só biblioteca padrão."""
import datetime
import importlib.util
import os
import shlex
import sqlite3

PORTA_EVOLUTION = 8080  # porta padrão da Evolution local (servico/evolution_local.py)
MODOS = {"registra_e_conta": "Registra e conta", "recusa": "Recusa segredo errado"}
VALIDOS_PARA_RECUSA = 20  # o mesmo de servico/rotas.py; quem decide é o serviço

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SERVICO = os.path.join(PLUGIN, "servico", "servico.py")
EVOLUTION_LOCAL = os.path.join(PLUGIN, "servico", "evolution_local.py")

_spec = importlib.util.spec_from_file_location("tune_up_vendas_cliente", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "cliente.py"))
cliente = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cliente)  # toda ação da tela fala com o serviço por cliente.chamar
_spec = importlib.util.spec_from_file_location("tune_up_vendas_conexao", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "conexao.py"))
conexao = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conexao)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_conversas", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "conversas.py"))
conversas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conversas)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_ia", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "ia.py"))
ia = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ia)
pasta = cliente.pasta
VIVO_S = cliente.VIVO_S
porta_do_painel = cliente.porta_do_painel

PORTA = 8791  # porta padrão do serviço (servico/servico.py); só para as regras de negar
# pasta de dados externa (servico/pasta.py) em macOS, Linux e Windows, no formato das regras do Claude Code
PASTAS_DE_DADOS = ("~/Library/Application Support/tune-up-vendas", "~/.local/share/tune-up-vendas",
                   "~/AppData/Local/tune-up-vendas")

INFO = {
    "id": "vendas",
    "titulo": "Vendas",
    "icone": "pessoas",
    "acoes": ["modo_webhook", "conectar_instancia", "abrir_conversa", "enviar_mensagem", "assumir_conversa",
              "devolver_ia", "liberar_saida", "reenviar_envio", "descartar_envio"] + list(conversas.ACOES_RASCUNHO)
             + ["ia_automatico_conversa", "ia_rascunho_conversa"] + list(ia.ACOES),
    "negar": [
        "Bash(*127.0.0.1:%d*)" % PORTA,
        "Bash(*localhost:%d*)" % PORTA,
        "Bash(*127.0.0.1:%d*)" % PORTA_EVOLUTION,
        "Bash(*localhost:%d*)" % PORTA_EVOLUTION,
        "Bash(*/api/modulos/*/acao*)",
        "Bash(*tune-up-vendas*)",
        "Bash(*docker exec*)",
        "Bash(*docker inspect*)",
        "Bash(*docker compose config*)",
        "Bash(*security find-generic-password*)",
    ] + ["%s(%s/**)" % (ferramenta, dados) for dados in PASTAS_DE_DADOS for ferramenta in ("Read", "Edit", "Write")],
}


_ler = cliente.ler


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


def comando(ctx):
    raiz = (ctx or {}).get("raiz") or "<raiz do projeto>"
    return "python3 -B %s --projeto %s --painel http://127.0.0.1:%s" % (
        shlex.quote(SERVICO), shlex.quote(raiz), porta_do_painel(ctx))


def comando_evolution(ctx):
    raiz = (ctx or {}).get("raiz") or "<raiz do projeto>"
    return "python3 -B %s preparar --projeto %s" % (shlex.quote(EVOLUTION_LOCAL), shlex.quote(raiz))


def agir(ctx, acao, dados, base=None):
    """modo_webhook: pede ao serviço DESTE projeto a troca do modo do segredo do webhook (cliente.chamar confere
    porta, batimento e marca antes do token). Quem confere os 20 válidos seguidos é o serviço. Repetir o mesmo
    modo não muda nada. O token de envio nunca volta no resultado."""
    if acao == "conectar_instancia":
        return conexao.agir_conectar(ctx, cliente, dados, base)
    if acao in ("abrir_conversa", "enviar_mensagem", "assumir_conversa", "devolver_ia", "liberar_saida",
                "reenviar_envio", "descartar_envio", "ia_automatico_conversa", "ia_rascunho_conversa") \
            or acao in conversas.ACOES_RASCUNHO:
        return conversas.agir(ctx, cliente, acao, dados, base)
    if acao in ia.ACOES:
        return ia.agir(ctx, cliente, acao, dados, base)
    if acao != "modo_webhook":
        return {"ok": False, "mensagem": "Ação desconhecida."}
    modo = (dados or {}).get("modo")
    if modo not in MODOS:
        return {"ok": False, "mensagem": "Escolha um modo válido."}
    try:
        codigo, r = cliente.chamar(ctx, "POST", "/modo-webhook", {"modo": modo}, base=base)
    except cliente.Recusa as e:
        return {"ok": False, "mensagem": str(e)}
    if codigo != 200:
        return {"ok": False, "mensagem": str((r if isinstance(r, dict) else {}).get("erro")
                                             or "O serviço recusou a troca (%d)." % codigo)}
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
    blocos = [bloco, conexao.bloco_evolution(ctx, cliente, comando_evolution(ctx), base)]
    if rodando:  # QR e estado lidos na hora, a cada montar: nada de cache aqui
        blocos += conexao.blocos_instancia(*conexao.ler_instancia(ctx, cliente, base))
        blocos += blocos_webhook(webhook) if webhook else []
    if rodando:
        aba, aba_ia = conversas.blocos(ctx, cliente, base), ia.blocos(*ia.ler(ctx, cliente, base))
    else:
        aba = [{"tipo": "texto", "titulo": "Serviço parado", "texto": "Ligue o serviço (veja a aba Conexão) para "
                                                                      "ver e responder as conversas."}]
        aba_ia = [{"tipo": "texto", "titulo": "Serviço parado", "texto": "Ligue o serviço (veja a aba Conexão) para "
                                                                         "configurar a IA."}]
    return {"avisos": avisos, "abas": [{"id": "conexao", "titulo": "Conexão", "blocos": blocos},
                                       {"id": "conversas", "titulo": "Conversas", "blocos": aba},
                                       {"id": "ia", "titulo": "IA", "blocos": aba_ia}]}
