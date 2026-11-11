"""Chave da OpenAI: só num arquivo 0600 da pasta de dados externa (nunca no banco, no projeto ou em log).
Nenhuma função daqui devolve a chave para fora do serviço: estado() dá só 'configurada' e os 4 últimos caracteres.
O Keychain do macOS NÃO é usado (só arquivo)."""
import os
import re

from servico import travas

ARQUIVO = "openai_chave"
FORMATO = re.compile(r"^[A-Za-z0-9_\-]{20,512}$")


class ChaveInvalida(ValueError):
    pass


def caminho(pasta_dados):
    return os.path.join(pasta_dados, ARQUIVO)


def ler(pasta_dados):
    """A chave gravada, ou None. Só para o pedido à OpenAI dentro do serviço."""
    try:
        with open(caminho(pasta_dados), encoding="utf-8") as f:
            valor = f.read().strip()
    except FileNotFoundError:
        return None
    return valor if FORMATO.match(valor) else None


def gravar(pasta_dados, valor):
    """Grava ou troca a chave (arquivo 0600, conteúdo inteiro). Recusa formato estranho sem ecoar o valor."""
    valor = (valor or "").strip() if isinstance(valor, str) else ""
    if not FORMATO.match(valor):
        raise ChaveInvalida("A chave tem de ter de 20 a 512 letras, números, _ ou -.")
    travas.gravar_segredo(caminho(pasta_dados), valor)


def apagar(pasta_dados):
    """Apaga a chave. Devolve True se havia arquivo."""
    try:
        os.remove(caminho(pasta_dados))
        return True
    except FileNotFoundError:
        return False


def estado(pasta_dados):
    valor = ler(pasta_dados)
    return {"configurada": valor is not None, "final": valor[-4:] if valor else None}
