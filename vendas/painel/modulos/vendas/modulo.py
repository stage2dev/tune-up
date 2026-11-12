"""Tela Vendas (plugin tune-up-vendas). Aba "Conexão": serviço rodando ou parado, pelo batimento no banco.
A tela só LÊ o banco (modo somente leitura) e nunca lê o arquivo do token. Python 3.9, só biblioteca padrão."""
import datetime
import importlib.util
import os
import sqlite3

PORTA_EVOLUTION = 8080  # porta padrão da Evolution local (servico/evolution_local.py)
MODOS = {"registra_e_conta": "Só contar (recomendado)", "recusa": "Recusar os avisos falsos"}
VALIDOS_PARA_RECUSA = 20  # o mesmo de servico/rotas.py; quem decide é o serviço

_spec = importlib.util.spec_from_file_location("tune_up_vendas_cliente", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "cliente.py"))
cliente = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cliente)  # toda ação da tela fala com o serviço por cliente.chamar
_spec = importlib.util.spec_from_file_location("tune_up_vendas_conexao", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "conexao.py"))
conexao = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conexao)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_preparar", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "preparar.py"))
preparar = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preparar)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_conversas", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "conversas.py"))
conversas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(conversas)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_ia", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "ia.py"))
ia = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ia)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_leads", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "leads.py"))
leads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(leads)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_disparos", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "disparos.py"))
disparos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(disparos)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_candidatos", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "candidatos.py"))
candidatos = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(candidatos)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_buscador", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "buscador.py"))
buscador = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(buscador)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_places", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "places.py"))
places = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(places)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_voz", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "abas", "voz.py"))
voz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(voz)
_spec = importlib.util.spec_from_file_location("tune_up_vendas_arquivo", os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "arquivo.py"))
_arquivo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_arquivo)
pasta = cliente.pasta
VIVO_S = cliente.VIVO_S
porta_do_painel = cliente.porta_do_painel

PORTA = 8791  # porta padrão do serviço (servico/servico.py); só para as regras de negar
# pasta de dados externa (servico/pasta.py) em macOS, Linux e Windows, no formato das regras do Claude Code
PASTAS_DE_DADOS = ("~/Library/Application Support/tune-up-vendas", "~/.local/share/tune-up-vendas",
                   "~/AppData/Local/tune-up-vendas")

FORM_IMPORTAR = {"tipo": "formulario", "id": "importar_candidatos", "titulo": "Importar candidatos",
                 "descricao": "Traz para esta lista os arquivos que o buscador deixou na pasta (e apaga os arquivos).",
                 "acao": "importar_candidatos", "botao": "Importar candidatos", "campos": []}

INFO = {
    "id": "vendas",
    "titulo": "Vendas",
    "icone": "pessoas",
    "acoes": ["modo_webhook", "conectar_instancia", "abrir_conversa", "enviar_mensagem", "assumir_conversa",
              "devolver_ia", "liberar_saida", "reenviar_envio", "descartar_envio", "midia_baixar_de_novo"] + list(conversas.ACOES_RASCUNHO)
             + ["ia_automatico_conversa", "ia_rascunho_conversa"] + list(ia.ACOES) + list(leads.ACOES) + list(disparos.ACOES)
             + list(candidatos.ACOES) + list(buscador.ACOES) + list(places.ACOES) + list(voz.ACOES)
             + list(preparar.ACOES),
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


def arquivo(ctx, ref, base=None):
    """Bytes de uma mídia de mensagem para o painel (ref 'm:<id>'); a lógica está em arquivo.py."""
    return _arquivo.ler(ctx, cliente, ref, base)


def agir(ctx, acao, dados, base=None):
    """modo_webhook: pede ao serviço DESTE projeto a troca do modo do segredo do webhook (cliente.chamar confere
    porta, batimento e marca antes do token). Quem confere os 20 válidos seguidos é o serviço. Repetir o mesmo
    modo não muda nada. O token de envio nunca volta no resultado."""
    if acao == "conectar_instancia":
        return conexao.agir_conectar(ctx, cliente, dados, base)
    if acao in preparar.ACOES:   # só a raiz da página; os dados da tela (ex. o comando copiado) são ignorados
        return preparar.agir(ctx, cliente, acao, base)
    if acao in ("abrir_conversa", "enviar_mensagem", "assumir_conversa", "devolver_ia", "liberar_saida",
                "reenviar_envio", "descartar_envio", "midia_baixar_de_novo", "ia_automatico_conversa", "ia_rascunho_conversa") \
            or acao in conversas.ACOES_RASCUNHO:
        return conversas.agir(ctx, cliente, acao, dados, base)
    if acao in ia.ACOES:
        return ia.agir(ctx, cliente, acao, dados, base)
    if acao in leads.ACOES:
        return leads.agir(ctx, cliente, acao, dados, base)
    if acao in disparos.ACOES:
        return disparos.agir(ctx, cliente, acao, dados, base)
    if acao in candidatos.ACOES:
        return candidatos.agir(ctx, cliente, acao, dados, base)
    if acao in buscador.ACOES:
        return buscador.agir(ctx, cliente, acao, dados, base)
    if acao in places.ACOES:
        return places.agir(ctx, cliente, acao, dados, base)
    if acao in voz.ACOES:
        return voz.agir(ctx, cliente, acao, dados, base)
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
    """Fim da aba Conexão: a senha que cada mensagem traz. Em palavras simples; o padrão já serve."""
    falta = max(0, VALIDOS_PARA_RECUSA - w["seguidos"])
    return [
        {"tipo": "texto", "titulo": "Avançado: segurança do recebimento",
         "texto": ("Cada mensagem que chega traz uma senha, para provar que veio mesmo do seu WhatsApp. Você não "
                   "precisa mexer aqui: o jeito que já está é o recomendado.")},
        {"tipo": "kpis", "itens": [
            {"rotulo": "Jeito atual", "valor": MODOS.get(w["modo"], w["modo"])},
            {"rotulo": "Com senha certa", "valor": w["validos"]},
            {"rotulo": "Com senha errada", "valor": w["invalidos"], "tom": "atencao" if w["invalidos"] else "neutro"},
            {"rotulo": "Certas em sequência", "valor": w["seguidos"],
             "detalhe": "já dá para recusar as erradas" if not falta
             else "faltam %d para poder recusar as erradas" % falta}]},
        {"tipo": "formulario", "id": "modo_webhook", "titulo": "Trocar o jeito de tratar senha errada",
         "descricao": ("\"Só contar\": a mensagem com senha errada entra e é contada. \"Recusar\": ela é barrada, "
                       "mas isso só liga depois de %d mensagens certas em sequência (uma errada zera a conta)."
                       % VALIDOS_PARA_RECUSA),
         "acao": "modo_webhook", "botao": "Trocar",
         "campos": [{"id": "modo", "rotulo": "Jeito", "tipo": "escolha", "valor": w["modo"], "obrigatorio": True,
                     "opcoes": [{"valor": k, "rotulo": v} for k, v in MODOS.items()]}]},
    ]


PARADO_CURTO = [{"tipo": "texto", "titulo": "Serviço parado", "texto": "Ligue o serviço (veja a aba Conexão)."}]


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
    if not rodando:  # UM bloco: preparar tudo, ligar o serviço ou os passos andando; as outras abas apontam para ele
        topo, vivo = preparar.topo(ctx, cliente, conexao, base)
        nomes = (("conexao", "Conexão"), ("conversas", "Conversas"), ("ia", "IA"), ("leads", "Leads"),
                 ("disparos", "Disparos"), ("buscador", "Buscador"), ("voz", "Voz"))
        return {"avisos": avisos, "atualizar_em": 3 if vivo else 15,
                "abas": [{"id": i, "titulo": t, "blocos": topo if i == "conexao" else PARADO_CURTO}
                         for i, t in nomes]}
    dados, aviso_instancia = conexao.ler_instancia(ctx, cliente, base)  # QR e estado lidos na hora, sem cache
    conectado = bool(dados) and not aviso_instancia and dados.get("estado") == "conectado"
    blocos = conexao.blocos_instancia(dados, aviso_instancia)
    # a Evolution não responde: "Preparar tudo" vem PRIMEIRO; com um preparo andando, a lista de passos
    topo, vivo = preparar.topo(ctx, cliente, conexao, base, servico_rodando=True,
                               precisa=bool(aviso_instancia or (dados or {}).get("aviso")))
    blocos = topo + blocos
    if webhook:
        blocos += blocos_webhook(webhook)
    aba, nao_lidas = conversas.aba(ctx, cliente, base)
    aba_ia = ia.blocos(*ia.ler(ctx, cliente, base))
    aba_leads = leads.blocos(ctx, *leads.ler(ctx, cliente, base), cliente)
    aba_disparos = disparos.blocos(ctx, *disparos.ler(ctx, cliente, base))
    aba_buscador = (buscador.blocos(ctx, *buscador.ler(ctx, cliente, base), FORM_IMPORTAR)
                    + places.blocos(*places.ler(ctx, cliente, base), buscador.endereco))
    aba_voz = voz.blocos(*voz.ler(ctx, cliente, base))
    aba_conversas = {"id": "conversas", "titulo": "Conversas", "blocos": aba}
    if nao_lidas >= 1:
        aba_conversas["alerta"] = nao_lidas
    return {"avisos": avisos, "atualizar_em": 3 if conectado or vivo else 15,
            "abas": [{"id": "conexao", "titulo": "Conexão", "blocos": blocos}, aba_conversas,
                     {"id": "ia", "titulo": "IA", "blocos": aba_ia},
                     {"id": "leads", "titulo": "Leads", "blocos": aba_leads},
                     {"id": "disparos", "titulo": "Disparos", "blocos": aba_disparos},
                     {"id": "buscador", "titulo": "Buscador", "blocos": aba_buscador},
                     {"id": "voz", "titulo": "Voz", "blocos": aba_voz}]}
