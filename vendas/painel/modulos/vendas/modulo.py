"""Tela Vendas (plugin tune-up-vendas). Esqueleto: uma aba "Conexão" que avisa que o serviço
não está rodando. Python 3.9, só biblioteca padrão."""

PORTA = 8791  # provisória; o serviço de verdade define a porta

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

COMANDO = "python3 <pasta do plugin>/servico/iniciar.py"


def montar(ctx):
    texto = ("O serviço de Vendas não está rodando. Ele só liga por um comando seu, digitado num "
             "terminal (nunca por uma sessão do Claude). Comando: %s" % COMANDO)
    return {"abas": [{"id": "conexao", "titulo": "Conexão",
                      "blocos": [{"tipo": "texto", "titulo": "Serviço parado", "texto": texto}]}]}
