"""Conector falso, em memória, para os testes dos itens seguintes. Registra toda chamada.

modo_envio: "ok" (devolve id), "recusar" (NaoEnviado, nada entregue), "aceitar_e_cair" (entrega e levanta
EnvioIncerto, como a conexão que cai depois de o outro lado aceitar), "timeout" (EnvioIncerto, nada entregue)."""
import threading

from servico.conectores import base, evolution

MODOS = ("ok", "recusar", "aceitar_e_cair", "timeout")


class ConectorFalso(base.Conector):
    def __init__(self, modo_envio="ok", estado_atual="desconectado", qr_atual=None):
        self.modo_envio = modo_envio
        self.estado_atual = estado_atual
        self.qr_atual = qr_atual
        self.chamadas = []    # (nome, argumentos) de toda chamada, na ordem
        self.entregues = []   # {"id_externo", "instancia", "telefone", "tipo", "conteudo"} do que chegou "lá"
        self._trava = threading.Lock()
        self._contador = 0

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

    def traduzir_evento(self, corpo):
        self._anotar("traduzir_evento", corpo)
        return evolution.traduzir(corpo)

    def envios(self):
        """Quantas chamadas de envio chegaram ao conector (entregues ou não)."""
        with self._trava:
            return sum(1 for nome, _ in self.chamadas if nome.startswith("enviar_"))
