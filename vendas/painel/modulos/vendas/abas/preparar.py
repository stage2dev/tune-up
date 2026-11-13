"""Aba Conexão, preparo em um clique: "Preparar tudo" (os cinco passos de servico/preparo.py) e "Ligar o serviço" (só
o último passo). Lê o arquivo de estado do preparo direto da pasta de dados externa (o serviço pode estar parado) e
mostra só textos simples: nunca caminho de pasta, log, chave nem a saída crua de um comando. O preparo começa
destacado (lista de argumentos, o mesmo python, sem shell) e só para a raiz do projeto da página."""
import importlib.util
import json
import os
import socket
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
PREPARO = os.path.join(PLUGIN, "servico", "preparo.py")
_spec = importlib.util.spec_from_file_location("tune_up_vendas_preparo_sistema",
                                               os.path.join(PLUGIN, "servico", "preparo_sistema.py"))
sistema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sistema)   # só biblioteca padrão: Sistema.soltar e o estado de falha ao começar
_spec = importlib.util.spec_from_file_location("tune_up_vendas_preparo_travas", os.path.join(PLUGIN, "servico", "travas.py"))
travas = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(travas)   # só biblioteca padrão: preparo vivo = trava ocupada

ACOES = ("preparar_tudo", "ligar_servico")
ARQUIVO_ESTADO = "preparo.json"   # o mesmo de servico/preparo.py
ARQUIVO_LOG = "preparo.log"
ARQUIVO_TRAVA = "preparo.trava"
VAR_URL = "VENDAS_EVOLUTION_URL"   # Evolution de outro endereço: conta como pronta (servico/conectores/evolution.py)
PORTA_EVOLUTION = 8080
TITULOS = {"docker_instalado": "Instalar o programa que roda o WhatsApp",
           "docker_ligado": "Ligar esse programa",
           "evolution_preparada": "Preparar o WhatsApp",
           "evolution_no_ar": "Ligar o WhatsApp",
           "servico_ligado": "Ligar o serviço de Vendas"}
SELOS = {"feito": ("feito", "bom"), "rodando": ("fazendo...", "atencao"), "falhou": ("parou aqui", "ruim"),
         "precisa_do_dono": ("falta você", "atencao"), "pendente": ("falta", "neutro")}
PREPARAR = "Preparar o WhatsApp neste computador"
LIGAR = "O serviço de Vendas está parado"
EXPLICA = ("Um clique prepara tudo: instala um programa gratuito chamado Docker (se faltar), prepara o WhatsApp e "
           "liga o serviço de Vendas. Na primeira vez ele baixa arquivos grandes e leva alguns minutos. No Windows "
           "pode abrir uma janela pedindo sua confirmação: clique em Sim. Você acompanha cada passo aqui. "
           "Prefere fazer à mão? Veja \"Fazer à mão\" no README do plugin.")
_lancados = {}   # raiz -> processo solto por esta tela (um clique repetido não solta outro enquanto ele vive)


def _pasta(raiz, cliente, base):
    return cliente.pasta.caminho_da_pasta(raiz, base)


def ler_estado(raiz, cliente, base=None):
    """Estado do último preparo, ou None (sem arquivo, ilegível). "rodando" com a trava preparo.trava livre =
    "interrompido" (um pid vivo não basta: pode ter sido reaproveitado)."""
    pasta_dados = _pasta(raiz, cliente, base)
    try:
        with open(os.path.join(pasta_dados, ARQUIVO_ESTADO), encoding="utf-8") as f:
            estado = json.load(f)
        if isinstance(estado, dict) and estado.get("estado") == "rodando":
            if not travas.ocupada(pasta_dados, ARQUIVO_TRAVA):
                estado["estado"] = "interrompido"
    except (OSError, ValueError):
        return None
    if not isinstance(estado, dict) or not isinstance(estado.get("passos", []), list):
        return None
    if estado.get("estado") == "interrompido":
        for passo in estado.get("passos") or []:
            if isinstance(passo, dict) and passo.get("estado") == "rodando":
                passo.update(estado="falhou", mensagem="O preparo parou no meio deste passo. Clique de novo para "
                                                       "continuar daqui.")
    return estado


def vivo(raiz, estado):
    processo = _lancados.get(raiz)
    return (estado or {}).get("estado") == "rodando" or (processo is not None and processo.poll() is None)


def porta_aberta(porta, tempo=0.3):
    """Algo escuta na porta em 127.0.0.1 (só conecta e fecha; sem HTTP, sem chave)."""
    try:
        socket.create_connection(("127.0.0.1", porta), timeout=tempo).close()
        return True
    except (OSError, ValueError):
        return False


def evolution_ok(raiz, cliente, conexao, estado, base=None):
    """Arquivos da Evolution prontos e a porta dela atendendo."""
    porta = ((estado or {}).get("portas") or {}).get("evolution")
    porta = porta if isinstance(porta, int) and 1 <= porta <= 65535 else PORTA_EVOLUTION
    return conexao.evolution_preparada(raiz, cliente, base) and porta_aberta(porta)


def _texto(valor, pasta_dados):
    texto = str(valor or "")
    return texto.replace(pasta_dados, "(pasta de dados)") if pasta_dados else texto


def _passos(estado):
    return [p for p in (estado or {}).get("passos") or [] if isinstance(p, dict)]


def bloco_lista(estado):
    """Os passos como lista de conferir, o atual marcado "fazendo..."; sem detalhe técnico."""
    passos = _passos(estado) or [{"nome": n, "estado": "pendente"} for n in TITULOS]
    itens = []
    for p in passos:
        texto, tom = SELOS.get(p.get("estado"), SELOS["pendente"])
        itens.append({"titulo": TITULOS.get(p.get("nome"), "Passo"), "selo": {"texto": texto, "tom": tom}})
    return {"tipo": "lista", "titulo": "Preparando o WhatsApp neste computador", "itens": itens}


def bloco_preparar(estado, pasta_dados=""):
    """O cartão "Preparar tudo"; depois de um preparo que parou, o motivo em palavras simples e o botão de seguir."""
    passo = next((p for p in _passos(estado) if p.get("estado") in ("precisa_do_dono", "falhou")), None)
    bloco = {"tipo": "formulario", "id": "preparar_tudo", "titulo": PREPARAR, "descricao": EXPLICA,
             "acao": "preparar_tudo", "botao": "Preparar tudo", "campos": []}
    if passo is None:
        if (estado or {}).get("estado") == "falhou" and estado.get("mensagem"):   # nem começou
            bloco.update(descricao=_texto(estado["mensagem"], pasta_dados), botao="Tentar de novo")
        return bloco
    titulo = TITULOS.get(passo.get("nome"), "um passo")
    mensagem = _texto(passo.get("mensagem"), pasta_dados) or "O preparo parou neste passo."
    if passo["estado"] == "precisa_do_dono":
        bloco.update(descricao="Falta um passo seu em \"%s\". %s" % (titulo, mensagem), botao="Já fiz, continuar")
        if passo.get("comando"):
            bloco["campos"] = [{"id": "comando", "rotulo": "Comando para copiar e colar num terminal",
                                "tipo": "texto", "valor": sistema.sem_casa(str(passo["comando"]))}]
        return bloco
    bloco.update(descricao="O preparo parou em \"%s\". %s" % (titulo, mensagem), botao="Tentar de novo")
    return bloco


def bloco_ligar(estado, pasta_dados=""):
    descricao = ("O WhatsApp deste computador já está pronto; falta só ligar o serviço de Vendas (isso acontece depois "
                 "de reiniciar o computador). Um clique liga.")
    passo = next((p for p in _passos(estado) if p.get("estado") in ("precisa_do_dono", "falhou")), None)
    ultima = (passo or {}).get("mensagem") or ((estado or {}).get("mensagem") if passo is None else None)
    if ultima:
        descricao += " Da última vez: " + _texto(ultima, pasta_dados)
    return {"tipo": "formulario", "id": "ligar_servico", "titulo": LIGAR, "descricao": descricao,
            "acao": "ligar_servico", "botao": "Ligar o serviço", "campos": []}


def topo(ctx, cliente, conexao, base=None, servico_rodando=False, precisa=False):
    """(blocos do topo da aba Conexão, preparo vivo). Vivo: a lista de passos. Serviço parado: "Ligar o serviço" se a
    Evolution está bem, senão "Preparar tudo". Serviço rodando: "Preparar tudo" só se `precisa` (Evolution sem
    resposta); senão nada. Com VENDAS_EVOLUTION_URL no ambiente, só "Ligar o serviço" (ou nada)."""
    raiz = (ctx or {}).get("raiz") or ""
    if not raiz:
        return [bloco_preparar(None)], False
    estado = ler_estado(raiz, cliente, base)
    pasta_dados = _pasta(raiz, cliente, base)
    if vivo(raiz, estado):
        return [bloco_lista(estado if (estado or {}).get("estado") == "rodando" else None)], True
    externa = bool(os.environ.get(VAR_URL))
    if servico_rodando:
        return ([bloco_preparar(estado, pasta_dados)] if precisa and not externa else []), False
    if externa or evolution_ok(raiz, cliente, conexao, estado, base):
        return [bloco_ligar(estado, pasta_dados)], False
    return [bloco_preparar(estado, pasta_dados)], False


def soltar(argv, log):
    return sistema.Sistema().soltar(argv, log)


def agir(ctx, cliente, acao, base=None):
    """preparar_tudo / ligar_servico: solta `preparo.py iniciar` (com --so-servico no segundo) para a raiz DESTA página
    e volta na hora. Com um preparo vivo, não solta outro."""
    raiz = (ctx or {}).get("raiz")
    if not raiz:
        return {"ok": False, "mensagem": "Esta tela não sabe qual é o projeto."}
    if vivo(raiz, ler_estado(raiz, cliente, base)):
        return {"ok": True, "mensagem": "Já estou preparando. Acompanhe os passos aqui."}
    try:
        pasta_dados = cliente.pasta.pasta_de_dados(raiz, base)
    except (OSError, ValueError, cliente.pasta.PastaRecusada):
        return {"ok": False, "mensagem": "Não consegui usar a pasta de dados deste projeto. Rode o preparo pelo "
                                         "terminal para ver o motivo (README, \"Fazer à mão\")."}
    argv = [sys.executable, "-B", PREPARO, "iniciar", "--projeto", raiz,
            "--painel", "http://127.0.0.1:%d" % cliente.porta_do_painel(ctx)]
    if base:
        argv += ["--base", base]
    if acao == "ligar_servico":
        argv.append("--so-servico")
    try:
        _lancados[raiz] = soltar(argv, os.path.join(pasta_dados, ARQUIVO_LOG))
    except OSError:
        motivo = "O preparo não começou: este computador não deixou abrir o processo. Clique em Tentar de novo."
        try:
            travas.gravar_segredo(os.path.join(pasta_dados, ARQUIVO_ESTADO),
                                  json.dumps(sistema.falha_ao_comecar(motivo), ensure_ascii=False))
        except OSError:
            pass   # nem o estado dá para gravar; a mensagem abaixo diz o motivo
        return {"ok": False, "mensagem": motivo}
    if acao == "ligar_servico":
        return {"ok": True, "mensagem": "Ligando o serviço. Em instantes a tela muda."}
    return {"ok": True, "mensagem": "Comecei a preparar. Acompanhe os passos aqui."}
