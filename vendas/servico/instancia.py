"""Instância do WhatsApp para a aba Conexão: criar/conectar e ler estado + QR pelo conector. O nome da instância e o
aviso `numero_descartavel` ficam na config. Nunca chama logout nem apaga instância (o conector nem tem esses métodos).
O QR é lido na hora, nunca guardado."""
from servico import banco
from servico.conectores import base

ERRO_CONECTOR = "O WhatsApp (Evolution) não respondeu. Confira se ela está ligada e tente de novo."


def ler(con, conector):
    """{instancia, numero_descartavel, estado, qr, aviso}. Sem instância gravada: estado desconectado, sem consulta.
    Falha do conector vira aviso (a tela continua), nunca texto do erro cru. O QR só é pedido fora de 'conectado'."""
    nome = banco.ler_config(con, "instancia")
    saida = {"instancia": nome, "numero_descartavel": banco.ler_config(con, "numero_descartavel") == "1",
             "estado": "desconectado", "qr": None, "aviso": None}
    if not nome or conector is None:
        saida["aviso"] = None if not nome else "WhatsApp não configurado no serviço."
        return saida
    try:
        saida["estado"] = conector.estado(nome)
        if saida["estado"] != "conectado":
            saida["qr"] = conector.qr(nome)
            if saida["qr"] and saida["estado"] == "desconectado":
                saida["estado"] = "aguardando_qr"
    except base.ErroConector:
        saida["aviso"] = ERRO_CONECTOR
    return saida


def conectar(con, conector, instancia, numero_descartavel):
    """Grava a config e cria a instância (já existindo, o conector só regrava o webhook). ValueError = nome inválido
    (nada gravado); ErroConector sobe para a rota. Gravar antes de criar deixa a tela pedir o QR de novo se a
    criação falhar no meio."""
    base.validar_instancia(instancia)
    banco.gravar_config(con, "instancia", instancia)
    banco.gravar_config(con, "numero_descartavel", "1" if numero_descartavel is True else "0")
    conector.criar(instancia)
    return ler(con, conector)
