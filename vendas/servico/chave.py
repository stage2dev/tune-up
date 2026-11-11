"""Chave da OpenAI (e, com `arquivo=`, a do Google Places): só num arquivo 0600 da pasta de dados externa (nunca no banco, no projeto ou em log).
Nenhuma função daqui devolve a chave para fora do serviço: estado() dá só 'configurada' e os 4 últimos caracteres.
O Keychain do macOS NÃO é usado (só arquivo)."""
import os
import re

from servico import travas

ARQUIVO = "openai_chave"
FORMATO = re.compile(r"^[A-Za-z0-9_\-]{20,512}$")


class ChaveInvalida(ValueError):
    pass


def caminho(pasta_dados, arquivo=ARQUIVO):
    return os.path.join(pasta_dados, arquivo)


def ler(pasta_dados, arquivo=ARQUIVO):
    """A chave gravada, ou None. Só para o pedido à OpenAI dentro do serviço."""
    try:
        with open(caminho(pasta_dados, arquivo), encoding="utf-8") as f:
            valor = f.read().strip()
    except FileNotFoundError:
        return None
    return valor if FORMATO.match(valor) else None


def gravar(pasta_dados, valor, arquivo=ARQUIVO):
    """Grava ou troca a chave (arquivo 0600, conteúdo inteiro). Recusa formato estranho sem ecoar o valor."""
    valor = (valor or "").strip() if isinstance(valor, str) else ""
    if not FORMATO.match(valor):
        raise ChaveInvalida("A chave tem de ter de 20 a 512 letras, números, _ ou -.")
    travas.gravar_segredo(caminho(pasta_dados, arquivo), valor)


def apagar(pasta_dados, arquivo=ARQUIVO):
    """Apaga a chave. Devolve True se havia arquivo."""
    try:
        os.remove(caminho(pasta_dados, arquivo))
        return True
    except FileNotFoundError:
        return False


def estado(pasta_dados, arquivo=ARQUIVO):
    valor = ler(pasta_dados, arquivo)
    return {"configurada": valor is not None, "final": valor[-4:] if valor else None}
