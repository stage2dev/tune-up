"""Modelo da mensagem de campanha. Variáveis: {nome}, {empresa}, {origem} (lista fechada; qualquer outra chave ou chave
solta = modelo recusado). Toda primeira mensagem tem de trazer a identificação da empresa, de onde veio o contato e como
sair ("responda SAIR"): conferido ao salvar (no modelo) e de novo na hora do envio (no texto já preenchido). Valor que
falta para um contato = o contato é pulado com o motivo, nunca sai em branco nem com as chaves. No máximo 1000
caracteres; link só os do links.json do projeto (a mesma checagem da saída da IA)."""
import re

from servico import saida

VARIAVEIS = ("nome", "empresa", "origem")
MAXIMO = 1000
CHAVE = re.compile(r"\{([^{}]*)\}")
SAIR = re.compile(r"responda\s+sair(?![\w])", re.IGNORECASE)
CONTROLE = re.compile(r"[\x00-\x1f\x7f]+")
FRIO_BASES = ("consentimento", "cliente_existente")   # qualquer outra base legal = contato frio


class ModeloRecusado(ValueError):
    """Modelo inválido (a mensagem, em pt-BR, vai para o dono)."""


def _links(texto, permitidos):
    _, fora = saida.filtrar_links(texto, permitidos)
    fora = fora or saida.sobras_de_link(texto, permitidos)
    if fora:
        raise ModeloRecusado("A mensagem tem um link que não está no links.json do projeto. Tire o link ou "
                             "cadastre-o na lista.")


def validar(modelo, empresa, permitidos=()):
    """Confere o MODELO (com as chaves). Levanta ModeloRecusado com a explicação."""
    if not isinstance(modelo, str) or not modelo.strip():
        raise ModeloRecusado("Escreva o modelo da mensagem.")
    for chave in CHAVE.findall(modelo):
        if chave not in VARIAVEIS:
            raise ModeloRecusado("A variável {%s} não existe. Use só: %s." % (
                chave, ", ".join("{%s}" % v for v in VARIAVEIS)))
    if "{" in CHAVE.sub("", modelo) or "}" in CHAVE.sub("", modelo):
        raise ModeloRecusado("Tem uma chave { ou } solta no modelo. Use as variáveis inteiras, como {nome}.")
    if len(modelo.strip()) > MAXIMO:
        raise ModeloRecusado("A mensagem passa de %d caracteres." % MAXIMO)
    if "{empresa}" not in modelo and not (empresa and empresa.lower() in modelo.lower()):
        raise ModeloRecusado("A mensagem precisa dizer quem é a empresa: use {empresa}.")
    if "{origem}" not in modelo:
        raise ModeloRecusado("A mensagem precisa dizer de onde veio o contato: use {origem}.")
    if not SAIR.search(modelo):
        raise ModeloRecusado("A mensagem precisa ensinar a sair: escreva \"responda SAIR\".")
    _links(modelo, permitidos)


def _valor(bruto):
    return CONTROLE.sub(" ", str(bruto or "")).strip()


def renderizar(modelo, nome, origem, empresa, permitidos=()):
    """(texto, None) pronto para enviar, ou (None, motivo) para pular o contato. Confere o texto preenchido."""
    try:
        validar(modelo, empresa, permitidos)
    except ModeloRecusado:
        return None, "modelo_invalido"
    valores = {"nome": _valor(nome), "empresa": _valor(empresa), "origem": _valor(origem)}
    for chave in ("empresa", "origem") + (("nome",) if "{nome}" in modelo else ()):
        if not valores[chave]:
            return None, "sem_" + chave
    if any("{" in v or "}" in v for v in valores.values()):
        return None, "valor_invalido"
    texto = CHAVE.sub(lambda m: valores[m.group(1)], modelo).strip()
    if len(texto) > MAXIMO:
        return None, "mensagem_longa"
    if not SAIR.search(texto):
        return None, "sem_sair"
    if valores["empresa"].lower() not in texto.lower() or valores["origem"] not in texto:
        return None, "sem_identificacao"
    try:
        _links(texto, permitidos)
    except ModeloRecusado:
        return None, "link_fora_da_lista"
    return texto, None
