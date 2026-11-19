"""Tela Marketing (tune-up-mkt). Aba "Contas": estado de cada serviço do catálogo, lido de .tune-up/mkt/contas.json,
e o botão "Conferir contas", que roda `contas.py status` em segundo plano (conferencia.py).

Nada daqui mostra o campo `conta`, marcas, config.json nem saída de comando: só textos fixos e textos do catálogo.
As datas e os caminhos seguem as mesmas regras do contas.py (contas_arquivos / contas_regras, carregados por caminho).
Python 3.9, só biblioteca padrão.
"""
import importlib.util
import json
import os
from datetime import timedelta

_spec = importlib.util.spec_from_file_location("tune_up_mkt_conferencia", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "conferencia.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)
A, R = C.A, C.R

CATALOGO = os.path.join(os.path.dirname(C.SCRIPTS), "servicos.json")
IDADE = timedelta(hours=24)       # = contas.IDADE_FALTA (o mesmo campo: conferido_em do topo)
AVISO_FIM = timedelta(seconds=15)  # janela do aviso "conferência terminada": some em até 15 s (sem estado em memória)
RITMO = 2                          # atualizar_em enquanto confere: resultado na tela até ~5 s depois do fim
PALAVRAS = {"ligado": "ligado", "falta_autenticar": "falta autenticar", "nao_instalado": "não instalado",
            "nao_sei": "não sei", "desligado": "desligado", "falhou": "falhou",
            "conferir_de_novo": "conferir de novo"}  # marca manual com mais de 7 dias (contas_regras._item)
NUNCA = "nunca conferido"

INFO = {"id": "mkt", "titulo": "Marketing", "icone": "grafico", "acoes": ["conferir"],
        "esquemas": {"conferir": {}}}   # a ação não aceita campo nenhum (o painel recusa com 400)

FORM = {"tipo": "formulario", "id": "conferir", "titulo": "Conferir contas",
        "descricao": "Roda a conferência grátis dos serviços (plugins, MCP e Composio) deste projeto.",
        "acao": "conferir", "botao": "Conferir contas", "campos": []}

# trocáveis nos testes
pid_vivo = C.pid_vivo
lancar = C.lancar
agora = C.agora


def _catalogo():
    with open(CATALOGO, encoding="utf-8") as f:
        return json.load(f)["servicos"]


def _quando(texto):
    return _hora(R.ler_iso(texto))


def _hora(t):
    try:
        return t.astimezone().strftime("%d/%m %H:%M") if t else ""
    except (OverflowError, ValueError, OSError):  # data no limite do calendário (ano 1 ou 9999)
        return ""


def _passo(s, estado):
    """Próximo passo em texto do catálogo (o mesmo critério de contas.passos)."""
    instalar = "Instalar: " + "; ".join([s["cadastro_url"]] + list(s["instalar"]))
    if estado == "ligado":
        return ""
    if estado == NUNCA:
        return "Clique em Conferir contas."
    if estado == "falta_autenticar":
        return s["autenticar"]["pt"]
    if estado == "conferir_de_novo":  # o texto da checagem manual do catálogo, como no skill connect
        return "Confirme de novo à mão (a marca vale 7 dias): " + "; ".join(
            c["alvo"] for c in s["conferir"] if c["tipo"] not in R.AUTOMATICOS)
    if estado in ("nao_instalado", "desligado"):
        return instalar
    return instalar + ". Depois: " + s["autenticar"]["pt"]


def _ler_contas(raiz):
    """(servicos dict or None, conferido_em datetime or None, aviso or None, topo ilegível)."""
    dados, ruim = C.ler_json(A.caminho(raiz, "contas.json"))
    if ruim or (dados is not None and not isinstance(dados.get("servicos"), dict)):
        return None, None, "O arquivo de contas não abre. Clique em Conferir contas para refazer.", False
    if dados is None:
        return None, None, None, False
    topo = dados.get("conferido_em")
    conferido = R.ler_iso(topo)
    return dados["servicos"], conferido, None, topo is not None and conferido is None


def _data_ruim(texto):
    return texto is not None and R.ler_iso(texto) is None


def _item(item):
    """(estado, datas, legível) de um item do contas.json. Qualquer forma ruim vira não sei / nunca conferido."""
    if item is None:
        return NUNCA, [], True
    if not isinstance(item, dict):
        return NUNCA, [], False
    estado = item.get("estado")
    ok = isinstance(estado, str) and estado in PALAVRAS
    checagens = item.get("checagens")
    checagens = [] if checagens is None else checagens  # null = lista vazia, como no contas.py
    if not isinstance(checagens, list):
        checagens, ok = [], False
    datas = []
    for c in checagens:
        if not isinstance(c, dict) or _data_ruim(c.get("conferido_em")):
            ok = False
        elif c.get("conferido_em") is not None:
            datas.append(R.ler_iso(c["conferido_em"]))
    return (estado if isinstance(estado, str) and estado in PALAVRAS else "nao_sei"), datas, ok


def _linha(s, item):
    estado, datas, ok = _item(item)
    return estado, ok, {"servico": s["nome"], "para_que": s["para_que"]["pt"], "estado": PALAVRAS.get(estado, NUNCA),
                    "conferido_em": _hora(max(datas)) if datas else "", "passo": _passo(s, estado)}


def _estado_conferencia(raiz, quando, alertas):
    """Alertas da conferência em segundo plano; devolve atualizar_em (ou None). Só lê arquivos."""
    m, res = C.ler_marcador(raiz), C.ler_resultado(raiz)
    if m is not None and C.vivo(m, quando, pid_vivo):
        alertas.append({"nivel": "info", "texto": "Conferindo as contas... a tela se atualiza sozinha."})
        return RITMO
    if m is not None and not (res and res.get("id") == m.get("id")):
        alertas.append({"nivel": "atencao", "texto": "A última conferência parou sem terminar. "
                                                     "Clique em Conferir contas de novo."})
        return None
    if not res:
        return None
    if res["codigo"] != 0:
        alertas.append({"nivel": "atencao", "texto": "A última conferência (%s) deu erro; os estados podem estar "
                                                     "velhos. Clique em Conferir contas de novo." % _quando(res["fim"])})
        return None
    if quando - AVISO_FIM <= R.ler_iso(res["fim"]) <= quando + R.FOLGA_FUTURO:
        alertas.append({"nivel": "info", "texto": "Conferência terminada."})
        return 15
    return None


def montar(ctx):
    quando = agora()
    raiz = ctx.get("raiz") or ""
    catalogo = _catalogo()
    alertas, servicos, conferido, ritmo, ruins = [], None, None, None, False
    try:
        servicos, conferido, aviso, ruins = _ler_contas(raiz)
        if aviso:
            alertas.append({"nivel": "atencao", "texto": aviso})
        ritmo = _estado_conferencia(raiz, quando, alertas)
    except A.Recusado:
        alertas.append({"nivel": "critico", "texto": "A pasta .tune-up/mkt (ou um arquivo dela) é um atalho ou "
                                                     "aponta para fora do projeto. Nada foi lido."})
    linhas = []
    for s in catalogo:
        estado, ok, linha = _linha(s, (servicos or {}).get(s["id"]) if servicos is not None else None)
        ruins = ruins or not ok
        linhas.append(linha)
        if servicos is not None and s["nivel"] == "base" and estado != "ligado":
            alertas.append({"nivel": "atencao", "texto": "%s está %s. Próximo passo: %s"
                                                          % (s["nome"], linha["estado"], linha["passo"])})
    if ruins:
        alertas.append({"nivel": "atencao", "texto": "O arquivo de contas tem itens que o painel não conseguiu ler. "
                                                     "Clique em Conferir contas: ele refaz o arquivo."})
    if servicos is None and not alertas:
        alertas.append({"nivel": "info", "texto": "Ainda não houve conferência. Clique em Conferir contas."})
    elif servicos is not None and conferido is None:  # só `marcar` rodou (ou o arquivo veio sem a data)
        alertas.append({"nivel": "atencao", "texto": "Nenhuma conferência automática rodou ainda. "
                                                     "Clique em Conferir contas."})
    elif servicos is not None and (quando - conferido > IDADE or conferido > quando + R.FOLGA_FUTURO):
        alertas.append({"nivel": "atencao", "texto": "A última conferência tem mais de 24 h. "
                                                     "Clique em Conferir contas de novo."})
    aba = {"id": "contas", "titulo": "Contas", "blocos": [FORM, {
        "tipo": "tabela", "titulo": "Serviços de marketing",
        "colunas": [{"id": "servico", "rotulo": "Serviço"}, {"id": "para_que", "rotulo": "Para que serve"},
                    {"id": "estado", "rotulo": "Estado"}, {"id": "conferido_em", "rotulo": "Conferido em"},
                    {"id": "passo", "rotulo": "Próximo passo"}],
        "linhas": linhas, "vazio": "O catálogo de serviços está vazio."}]}
    saida = {"alertas": alertas, "abas": [aba]}
    if ritmo:  # no topo: é onde o painel lê (modulos.py usa como validade do cache)
        saida["atualizar_em"] = ritmo
    return saida


def agir(ctx, acao, dados):
    if acao != "conferir":
        return {"ok": False, "mensagem": "Ação desconhecida."}
    if dados:
        return {"ok": False, "mensagem": "Esta ação não recebe campos."}
    raiz = ctx.get("raiz")
    if not isinstance(raiz, str) or not os.path.isabs(raiz) or not os.path.isdir(raiz):
        return {"ok": False, "mensagem": "Este painel não tem a pasta do projeto."}
    try:
        feito, msg = C.iniciar(raiz, agora(), lancar, pid_vivo)
    except A.Recusado:
        return {"ok": False, "mensagem": "A pasta .tune-up/mkt é um atalho ou aponta para fora do projeto. "
                                         "Nada foi rodado."}
    except OSError:
        return {"ok": False, "mensagem": "Não consegui começar a conferência. Tente de novo."}
    if not feito:
        return {"codigo": 409, "mensagem": msg}
    return {"ok": True, "mensagem": msg}
