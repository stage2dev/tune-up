"""Conector falso, em memória, para os testes dos itens seguintes. Registra toda chamada.

modo_envio: "ok" (devolve id), "recusar" (NaoEnviado, nada entregue), "aceitar_e_cair" (entrega e levanta
EnvioIncerto, como a conexão que cai depois de o outro lado aceitar), "timeout" (EnvioIncerto, nada entregue)."""
import threading

from servico.conectores import base, evolution

MODOS = ("ok", "recusar", "aceitar_e_cair", "timeout")


class ConectorFalso(base.Conector):
    def __init__(self, modo_envio="ok", estado_atual="desconectado", qr_atual=None):
        self.modo_envio = modo_envio
        self.digitando_falha = False   # True: digitando() levanta (a presença nunca pode impedir o envio)
        self.estado_atual = estado_atual
        self.qr_atual = qr_atual
        self.chamadas = []    # (nome, argumentos) de toda chamada, na ordem
        self.entregues = []   # {"id_externo", "instancia", "telefone", "tipo", "conteudo"} do que chegou "lá"
        self._trava = threading.Lock()
        self._contador = 0
        self.perdidos = []    # corpos de webhook que "chegaram com o serviço parado" (mensagens_desde devolve)
        self.midias = {}      # id da mensagem -> (bytes, mimetype, nome) ou uma exceção (ErroMidia) a levantar
        self.segurar_midia = None   # threading.Event: baixar_midia espera por ele (teste de "não bloqueia")

    def _anotar(self, nome, *argumentos):
        with self._trava:
            self.chamadas.append((nome, argumentos))

    def criar(self, instancia):
        base.validar_instancia(instancia)
        self._anotar("criar", instancia)

    def qr(self, instancia):
        self._anotar("qr", instancia)
        return self.qr_atual

    def estado(self, instancia):
        self._anotar("estado", instancia)
        return self.estado_atual

    def _enviar(self, nome, instancia, telefone, tipo, conteudo):
        self._anotar(nome, instancia, telefone, conteudo)
        if self.modo_envio not in MODOS:
            raise ValueError("modo_envio desconhecido: %r" % self.modo_envio)
        if self.modo_envio == "recusar":
            raise base.NaoEnviado("recusado pelo falso", 400)
        if self.modo_envio == "timeout":
            raise base.EnvioIncerto("timeout do falso")
        with self._trava:
            self._contador += 1
            ident = "falso-%d" % self._contador
            self.entregues.append({"id_externo": ident, "instancia": instancia, "telefone": telefone,
                                   "tipo": tipo, "conteudo": conteudo})
        if self.modo_envio == "aceitar_e_cair":
            raise base.EnvioIncerto("conexão caiu depois de aceitar (falso)")
        return ident

    def enviar_texto(self, instancia, telefone, texto):
        return self._enviar("enviar_texto", instancia, telefone, "texto", texto)

    def enviar_audio(self, instancia, telefone, caminho_ogg):
        return self._enviar("enviar_audio", instancia, telefone, "audio", caminho_ogg)

    def digitando(self, instancia, telefone, ms):
        self._anotar("digitando", instancia, telefone, ms)
        if self.digitando_falha:
            raise base.NaoEnviado("presença recusada pelo falso", 500)
        return True

    def traduzir_evento(self, corpo):
        self._anotar("traduzir_evento", corpo)
        return evolution.traduzir(corpo)

    def baixar_midia(self, instancia, mensagem):
        self._anotar("baixar_midia", instancia, mensagem)
        if self.segurar_midia is not None:
            self.segurar_midia.wait(10)
        achada = self.midias.get((mensagem or {}).get("id"))
        if achada is None:
            raise base.MidiaExpirada("mensagem não achada no falso", 400)
        if isinstance(achada, Exception):
            raise achada
        return achada

    def mensagens_desde(self, instancia, desde, ate):
        self._anotar("mensagens_desde", instancia, desde, ate)
        inicio, fim = desde.timestamp(), ate.timestamp()
        eventos = [e for corpo in self.perdidos for e in evolution.traduzir(corpo) if e["tipo_evento"] == "mensagem"]
        return [e for e in eventos if e["timestamp"] is not None and inicio <= e["timestamp"] <= fim]

    def envios(self):
        """Quantas chamadas de envio chegaram ao conector (entregues ou não)."""
        with self._trava:
            return sum(1 for nome, _ in self.chamadas if nome.startswith("enviar_"))
