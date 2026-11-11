"""Telefone: só dígitos com o código do país (55 se faltar) e as variantes com e sem o 9º dígito do celular."""
import re

PAIS = "55"
SUFIXO_JID = "@s.whatsapp.net"


class TelefoneInvalido(ValueError):
    pass


def normalizar(valor):
    """Forma canônica: dígitos com país. Celular brasileiro sempre COM o 9º dígito. Recusa @lid e tamanho errado."""
    texto = str(valor or "").strip()
    if "@" in texto:
        if not texto.endswith(SUFIXO_JID):
            raise TelefoneInvalido("identificador não é telefone (ex.: @lid): %r" % texto)
        texto = texto[:-len(SUFIXO_JID)].split(":")[0]
    digitos = re.sub(r"\D", "", texto)
    internacional = texto.startswith("+")
    if not internacional and digitos.startswith("00"):  # 00 na frente = discagem internacional, igual ao +
        internacional, digitos = True, digitos[2:]
    if not internacional:
        if digitos.startswith("0") and len(digitos) in (11, 12):
            digitos = digitos[1:]  # 0 de discagem interurbana do Brasil (0 + DDD + número)
        if len(digitos) in (10, 11):
            digitos = PAIS + digitos
    if digitos.startswith("0"):
        raise TelefoneInvalido("código de país não começa com 0: %r" % texto)
    if not digitos.startswith(PAIS):
        if not 8 <= len(digitos) <= 15:
            raise TelefoneInvalido("tamanho inválido: %d dígitos" % len(digitos))
        return digitos
    nacional = digitos[len(PAIS):]
    if len(nacional) not in (10, 11) or nacional[0] == "0" or nacional[1] == "0":
        raise TelefoneInvalido("número brasileiro precisa de DDD + 8 ou 9 dígitos: %r" % texto)
    ddd, numero = nacional[:2], nacional[2:]
    if len(numero) == 9:
        if numero[0] != "9":
            raise TelefoneInvalido("número de 9 dígitos sem o 9 na frente: %r" % texto)
        return PAIS + ddd + numero
    if numero[0] in "6789":  # celular escrito sem o 9º dígito
        return PAIS + ddd + "9" + numero
    return PAIS + ddd + numero  # fixo: não tem 9º dígito


def variantes(valor):
    """[canônico, sem o 9º dígito] para celular brasileiro; [canônico] para o resto.

    Só gera a forma sem o 9 quando o dígito seguinte é 6 a 9 (celular antigo de 8 dígitos).
    Com 0 a 5, tirar o 9 daria o número de um fixo de outra pessoa."""
    canonico = normalizar(valor)
    if canonico.startswith(PAIS) and len(canonico) == 13 and canonico[4] == "9" and canonico[5] in "6789":
        return [canonico, canonico[:4] + canonico[5:]]
    return [canonico]
