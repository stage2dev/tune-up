"""Teto diário de gasto com a OpenAI, em US$, calculado pela `usage` de cada resposta.
Tabela de preço (US$ por 1 milhão de tokens): PADRAO mais o `precos.json` da pasta de dados (o dono informa o preço
de qualquer modelo na aba IA; confira em openai.com/api/pricing: os valores mudam). Modelo SEM preço = a IA não
chama a OpenAI. precos.json inválido = ignorado inteiro (vale só PADRAO) e a tela avisa.
Antes de cada chamada, reservar() guarda o pior caso dentro de BEGIN IMMEDIATE (conversas ao mesmo tempo não passam
juntas do teto); depois acertar() troca a reserva pelo custo real. O gasto fica no banco em micro-dólares por dia."""
import datetime
import json
import math
import os
import secrets
import threading

from servico import banco, travas

ARQUIVO = "precos.json"
TETO_PADRAO_USD = 2.0
PRECO_MAX_USD = 10000.0
PADRAO = {  # entrada, saída
    "gpt-4o-mini": [0.15, 0.60],
    "gpt-4o": [2.50, 10.00],
    "gpt-4.1": [2.00, 8.00],
    "gpt-4.1-mini": [0.40, 1.60],
    "gpt-4.1-nano": [0.10, 0.40],
}
_GRAVANDO = threading.Lock()


class PrecosInvalidos(ValueError):
    pass


def _valor_ok(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and 0 < v <= PRECO_MAX_USD


def _ler_arquivo(pasta_dados):
    """({modelo: [entrada, saída]} do precos.json, inválido?). Ausente = ({}, False). Uma entrada ruim invalida tudo."""
    try:
        with open(os.path.join(pasta_dados, ARQUIVO), encoding="utf-8") as f:
            dado = json.load(f)
    except FileNotFoundError:
        return {}, False
    except (OSError, ValueError):
        return {}, True
    if not isinstance(dado, dict):
        return {}, True
    limpa = {}
    for modelo, par in dado.items():
        if not (isinstance(par, list) and len(par) == 2 and all(_valor_ok(v) for v in par)):
            return {}, True
        limpa[str(modelo)] = [float(par[0]), float(par[1])]
    return limpa, False


def tabela(pasta_dados):
    """PADRAO mais o precos.json (o arquivo vence). Arquivo inválido = só PADRAO."""
    tab = dict(PADRAO)
    tab.update(_ler_arquivo(pasta_dados)[0])
    return tab


def arquivo_invalido(pasta_dados):
    return _ler_arquivo(pasta_dados)[1]


def gravar_preco(pasta_dados, modelo, entrada, saida):
    """Grava o preço do modelo no precos.json (temporário + travas.substituir). Arquivo inválido = PrecosInvalidos
    (não apaga o que o dono escreveu à mão)."""
    if not _valor_ok(entrada) or not _valor_ok(saida):
        raise PrecosInvalidos("Preço inválido (maior que 0 e até %d dólares por 1 milhão de tokens)."
                              % PRECO_MAX_USD)
    with _GRAVANDO:
        atual, invalido = _ler_arquivo(pasta_dados)
        if invalido:
            raise PrecosInvalidos("O precos.json da pasta de dados é inválido. Corrija ou apague o arquivo.")
        atual[modelo] = [float(entrada), float(saida)]
        destino = os.path.join(pasta_dados, ARQUIVO)
        temp = "%s.%s.tmp" % (destino, secrets.token_hex(6))
        try:
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(atual, f, indent=2, sort_keys=True)
            travas.substituir(temp, destino)   # no Windows tenta de novo se o arquivo está em uso
        finally:
            if os.path.exists(temp):
                os.remove(temp)


def preco(tab, modelo):
    """[entrada, saída] do modelo, ou None (sem preço = não chama)."""
    return tab.get(modelo)


def custo_usd(par, usage):
    """Custo de UMA resposta pela usage (prompt_tokens e completion_tokens), ou None sem usage legível: usage {} ou
    sem os dois inteiros = None (quem chama cobra o pior caso; 0 liberaria a reserva e furaria o teto)."""
    if not isinstance(usage, dict):
        return None
    entrada, saida = usage.get("prompt_tokens"), usage.get("completion_tokens")
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in (entrada, saida)):
        return None
    return (entrada * par[0] + saida * par[1]) / 1000000.0


def pior_caso_usd(par, corpo, saida_max):
    """Pior caso de UMA chamada: cada byte do pedido como 1 token de entrada + saida_max tokens de saída."""
    entrada = len(json.dumps(corpo, ensure_ascii=False).encode("utf-8"))
    return (entrada * par[0] + saida_max * par[1]) / 1000000.0


def hoje():
    return datetime.date.today().isoformat()


def ler_teto(con):
    try:
        valor = float(banco.ler_config(con, "ia_teto_usd") or TETO_PADRAO_USD)
    except ValueError:
        return TETO_PADRAO_USD
    return valor if valor >= 0 and math.isfinite(valor) else TETO_PADRAO_USD


def gasto_hoje(con, dia=None):
    """Gasto do dia em US$, reservas abertas incluídas (0 se o dia gravado é outro)."""
    if banco.ler_config(con, "ia_gasto_dia") != (dia or hoje()):
        return 0.0
    return int(banco.ler_config(con, "ia_gasto_micro_usd") or 0) / 1000000.0


def _transacao(con, corpo):
    con.execute("BEGIN IMMEDIATE")
    try:
        r = corpo()
        con.execute("COMMIT")
        return r
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise


def _virar_dia(con, dia):
    if banco.ler_config(con, "ia_gasto_dia") != dia:
        banco.gravar_config(con, "ia_gasto_dia", dia)
        banco.gravar_config(con, "ia_gasto_micro_usd", "0")


def somar(con, usd, dia=None):
    """Soma o gasto ao dia (vira o dia = começa do zero), numa transação. Devolve o total do dia em US$."""
    dia = dia or hoje()

    def corpo():
        _virar_dia(con, dia)
        return banco.somar_config(con, "ia_gasto_micro_usd", int(round(usd * 1000000)))
    return _transacao(con, corpo) / 1000000.0


def reservar(con, usd, dia=None):
    """Reserva o pior caso se cabe no teto do dia: (dia, micro-dólares) para acertar(); None = não cabe (nada
    muda). Gasto e reserva saem do mesmo contador, lido e somado dentro de BEGIN IMMEDIATE."""
    dia = dia or hoje()
    micro = int(math.ceil(usd * 1000000))

    def corpo():
        _virar_dia(con, dia)
        atual = int(banco.ler_config(con, "ia_gasto_micro_usd") or 0)
        if (atual + micro) / 1000000.0 > ler_teto(con):
            return None
        banco.somar_config(con, "ia_gasto_micro_usd", micro)
        return dia, micro
    return _transacao(con, corpo)


def acertar(con, reserva, usd_real):
    """Troca a reserva pelo custo real (usd_real=0 libera tudo). Se o dia já virou, a reserva ficou no dia velho."""
    dia, micro = reserva
    delta = int(round(usd_real * 1000000)) - micro

    def corpo():
        if banco.ler_config(con, "ia_gasto_dia") == dia and delta:
            banco.somar_config(con, "ia_gasto_micro_usd", delta)
    _transacao(con, corpo)
