"""Interface do conector de WhatsApp e os dois erros que o portão distingue.

NaoEnviado: com certeza não saiu (conexão recusada, 4xx, arquivo ilegível) -> pode virar `falhou`.
NumeroInexistente (um NaoEnviado): o número não está no WhatsApp -> `falhou` com motivo numero_invalido.
EnvioIncerto: o pedido pode ter sido entregue (timeout ou conexão caída depois de escrever o pedido, 5xx,
resposta sem id) -> vira `incerto`, nunca reenvio automático."""
import re

ESTADOS = ("desconectado", "aguardando_qr", "conectado")
TIPOS = ("texto", "audio", "imagem", "documento", "outro")
INSTANCIA = re.compile(r"^[A-Za-z0-9_-]{1,64}$")  # mesmo formato da rota /webhook/<instancia>


class ErroConector(RuntimeError):
    """Base dos erros do conector. `status` = código HTTP quando houve resposta."""

    def __init__(self, mensagem, status=None):
        super().__init__(mensagem)
        self.status = status


class NaoEnviado(ErroConector):
    """Com certeza o pedido não teve efeito do outro lado."""


class NumeroInexistente(NaoEnviado):
    """O WhatsApp provou que o número não existe (nada saiu): o portão fecha como numero_invalido, nunca reenviar."""


class EnvioIncerto(ErroConector):
    """O pedido pode ter tido efeito; o resultado não é conhecido."""


def validar_instancia(instancia):
    if not isinstance(instancia, str) or not INSTANCIA.match(instancia):
        raise ValueError("nome de instância inválido (letras, números, _ e -, até 64)")
    return instancia


class Conector:
    """Contrato que o serviço usa. Só o portão chama enviar_*.

    traduzir_evento(corpo) devolve uma lista de eventos normalizados:
      {"tipo_evento": "mensagem", "direcao": "recebida"|"enviada", "id_externo", "remetente" (dígitos do
       contato da conversa, ou do participante no grupo; None se só houver @lid), "fromMe", "grupo",
       "tipo" (texto|audio|imagem|documento|outro), "texto", "timestamp" (segundos), "lid", "alternativa"}
      {"tipo_evento": "estado", "estado": um de ESTADOS}
      {"tipo_evento": "qr", "qr": data URI png}
    """

    def criar(self, instancia):
        raise NotImplementedError

    def qr(self, instancia):
        """Data URI `data:image/png;base64,...` ou None (já conectado ou sem QR ainda)."""
        raise NotImplementedError

    def estado(self, instancia):
        raise NotImplementedError

    def enviar_texto(self, instancia, telefone, texto):
        """Devolve o id externo da mensagem. Erros: NaoEnviado ou EnvioIncerto."""
        raise NotImplementedError

    def enviar_audio(self, instancia, telefone, caminho_ogg):
        """Devolve o id externo da mensagem. Erros: NaoEnviado ou EnvioIncerto."""
        raise NotImplementedError

    def digitando(self, instancia, telefone, ms):
        """Opcional: presença "digitando" por ms antes de um balão. False = o conector não suporta. Erro aqui
        nunca impede o envio (quem chama ignora)."""
        return False

    def traduzir_evento(self, corpo):
        raise NotImplementedError

    def mensagens_desde(self, instancia, desde, ate):
        """Eventos de mensagem (mesmo formato de traduzir_evento) com momento entre desde e ate (datetime UTC):
        o que chegou com o serviço parado. Erros: ErroConector."""
        raise NotImplementedError
