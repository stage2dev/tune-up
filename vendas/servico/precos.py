"""Teto diário de gasto com a OpenAI, em US$, calculado pela `usage` de cada resposta.
Tabela de preço (US$ por 1 milhão de tokens) configurável em `precos.json` na pasta de dados; sem o arquivo vale
PADRAO (confira em openai.com/api/pricing: os valores mudam). Modelo fora da tabela = a entrada mais cara (e a tela
avisa). O gasto fica no banco em micro-dólares inteiros por dia local."""
import datetime
import json
import os

from servico import banco

ARQUIVO = "precos.json"
TETO_PADRAO_USD = 2.0
PADRAO = {  # entrada, saída
    "gpt-4o-mini": [0.15, 0.60],
    "gpt-4o": [2.50, 10.00],
    "gpt-4.1": [2.00, 8.00],
    "gpt-4.1-mini": [0.40, 1.60],
    "gpt-4.1-nano": [0.10, 0.40],
}


def tabela(pasta_dados):
    """PADRAO ou o precos.json da pasta de dados ({"modelo": [entrada, saída]}); arquivo inválido = PADRAO."""
    try:
        with open(os.path.join(pasta_dados, ARQUIVO), encoding="utf-8") as f:
            dado = json.load(f)
    except (OSError, ValueError):
        return dict(PADRAO)
    limpa = {}
    if isinstance(dado, dict):
        for modelo, par in dado.items():
            if isinstance(par, list) and len(par) == 2 and all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in par):
                limpa[str(modelo)] = [float(par[0]), float(par[1])]
    return limpa or dict(PADRAO)


def preco(tab, modelo):
    """([entrada, saída], conhecido). Desconhecido = a entrada mais cara (soma dos dois)."""
    if modelo in tab:
        return tab[modelo], True
    return max(tab.values(), key=lambda par: par[0] + par[1]), False


def custo_usd(tab, modelo, usage):
    """Custo de UMA resposta pela usage (prompt_tokens e completion_tokens). Sem usage = custo do pior caso não
    existe: devolve None e quem chama trata como erro."""
    if not isinstance(usage, dict):
        return None
    try:
        entrada, saida = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    except (TypeError, ValueError):
        return None
    par, _ = preco(tab, modelo)
    return (entrada * par[0] + saida * par[1]) / 1000000.0


def hoje():
    return datetime.date.today().isoformat()


def ler_teto(con):
    try:
        valor = float(banco.ler_config(con, "ia_teto_usd") or TETO_PADRAO_USD)
    except ValueError:
        return TETO_PADRAO_USD
    return valor if valor >= 0 else TETO_PADRAO_USD


def gasto_hoje(con, dia=None):
    """Gasto do dia em US$ (0 se o dia gravado é outro)."""
    if banco.ler_config(con, "ia_gasto_dia") != (dia or hoje()):
        return 0.0
    return int(banco.ler_config(con, "ia_gasto_micro_usd") or 0) / 1000000.0


def somar(con, usd, dia=None):
    """Soma o gasto ao dia (vira o dia = começa do zero), numa transação. Devolve o total do dia em US$."""
    dia = dia or hoje()
    micro = int(round(usd * 1000000))
    con.execute("BEGIN IMMEDIATE")
    try:
        if banco.ler_config(con, "ia_gasto_dia") != dia:
            banco.gravar_config(con, "ia_gasto_dia", dia)
            banco.gravar_config(con, "ia_gasto_micro_usd", "0")
        total = banco.somar_config(con, "ia_gasto_micro_usd", micro)
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return total / 1000000.0


def no_teto(con, dia=None):
    return gasto_hoje(con, dia) >= ler_teto(con)
