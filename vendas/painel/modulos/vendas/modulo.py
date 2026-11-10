"""Tela Vendas (plugin tune-up-vendas). Aba "Conexão": serviço rodando ou parado, pelo batimento no banco.
A tela só LÊ o banco (modo somente leitura) e nunca lê o arquivo do token. Python 3.9, só biblioteca padrão."""
import datetime
import importlib.util
import os
import pathlib
import shlex
import sqlite3

PORTA = 8791  # porta padrão do serviço (servico/servico.py)
VIVO_S = 15  # batimento mais velho que isso = serviço parado (o serviço bate a cada 3 s)

PLUGIN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SERVICO = os.path.join(PLUGIN, "servico", "servico.py")

_spec = importlib.util.spec_from_file_location("tune_up_vendas_pasta", os.path.join(PLUGIN, "servico", "pasta.py"))
pasta = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pasta)

INFO = {
    "id": "vendas",
    "titulo": "Vendas",
    "icone": "pessoas",
    "acoes": [],
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


def ler_batimento(raiz, base=None):
    """Data UTC do último batimento do serviço deste projeto, ou None (sem pasta, sem banco, sem linha).
    Não cria nada: o banco abre em modo somente leitura."""
    arquivo = os.path.join(pasta.caminho_da_pasta(raiz, base), "vendas.db")
    if not os.path.isfile(arquivo) or not os.path.exists(arquivo + "-shm"):
        return None  # sem -shm não há conexão WAL aberta (e o modo ro não consegue criá-lo): serviço parado
    con = sqlite3.connect(pathlib.Path(os.path.abspath(arquivo)).as_uri() + "?mode=ro", uri=True, timeout=2)
    try:
        linha = con.execute("SELECT em FROM batimento WHERE id = 1").fetchone()
    finally:
        con.close()
    return datetime.datetime.fromisoformat(linha[0]) if linha else None


def comando(ctx):
    raiz = (ctx or {}).get("raiz") or "<raiz do projeto>"
    porta_painel = ((ctx or {}).get("config") or {}).get("porta")
    porta_painel = porta_painel if isinstance(porta_painel, int) and 1024 <= porta_painel <= 65535 else 8787
    return "python3 -B %s --projeto %s --painel http://127.0.0.1:%s" % (
        shlex.quote(SERVICO), shlex.quote(raiz), porta_painel)


def montar(ctx, base=None):
    agora = datetime.datetime.now(datetime.timezone.utc)
    avisos = []
    try:
        quando = ler_batimento(ctx.get("raiz") or "", base) if ctx.get("raiz") else None
    except (sqlite3.Error, ValueError) as e:
        quando = None
        avisos.append("não consegui ler o batimento do serviço (%s)" % type(e).__name__)
    rodando = quando is not None and abs((agora - quando).total_seconds()) <= VIVO_S
    if rodando:
        bloco = {"tipo": "texto", "titulo": "Serviço rodando",
                 "texto": "O serviço de Vendas está rodando (último sinal às %s UTC)." % quando.strftime("%H:%M:%S")}
    else:
        bloco = {"tipo": "texto", "titulo": "Serviço parado",
                 "texto": ("O serviço de Vendas está parado. Ele só liga por um comando seu, digitado num "
                           "terminal (nunca por uma sessão do Claude). Comando: %s" % comando(ctx))}
    return {"avisos": avisos, "abas": [{"id": "conexao", "titulo": "Conexão", "blocos": [bloco]}]}
