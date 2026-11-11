"""Atendente: liga o cérebro ao gancho recebimento.ao_receber_mensagem_de_lead.

- Debounce por conversa (ESPERA_S, 12 s): cada mensagem nova empurra o prazo; uma rajada vira UMA resposta.
- Trava por conversa: duas rodadas nunca respondem a mesma conversa ao mesmo tempo.
- Gatilho: o maior mensagem_id que o gancho entregou na espera (só texto de lead vindo de webhook com segredo).
  Uma saída gravada depois dele (o eco fromMe da resposta anterior) não apaga a vez dele; uma entrada confiável
  mais nova que ele (outra rodada vem, ou é mídia/velha que o dono vê) faz esta rodada não responder.
- Contexto: as últimas CONTEXTO (30) mensagens CONFIÁVEIS até o gatilho (linha de webhook sem segredo, entrada ou
  fromMe, nunca entra; o que veio depois do gatilho fica de fora). O texto do lead vai como DADO entre <dados_do_cliente> e
  </dados_do_cliente> (marcas de dentro do texto são neutralizadas), nunca junto das instruções.
- Filtro de injeção (regex): acerto grava evento e marca "precisa de você", mas a IA ainda responde a partir do dado.
  Limite: a regex só pega frases conhecidas; o que ela não pega depende do modelo respeitar o delimitador.
- Nenhuma transação de escrita fica aberta durante a rede: a mensagem já foi gravada e commitada pelo recebimento;
  aqui só há leituras e escritas curtas em autocommit; o envio sai pelo portão (origem 'ia'), que reconfere opt-out,
  pausa, modo humano e tetos NA HORA DE ENVIAR.
- Não responde: modo humano, pausada, opt-out, entrada confiável mais nova que o gatilho, rodada sem gatilho.
  Grupo, fromMe, mídia e mensagem velha nem chegam aqui (o recebimento não chama o gancho).
- parar(): as esperas acabam sem responder e as threads terminam (join com tempo limite)."""
import datetime
import json
import re
import sys
import threading
import time

from servico import banco, cerebro, portao

UTC = datetime.timezone.utc
ESPERA_S = 12
CONTEXTO = 30
ABRE, FECHA = "<dados_do_cliente>", "</dados_do_cliente>"
MARCA = re.compile(r"</?\s*dados_do_cliente\s*>", re.I)
INJECAO = re.compile(
    r"ignor\w*\s+(as\s+|all\s+|the\s+|todas\s+as\s+)?(previous|prior|above|instru|anteriores|regras)"
    r"|(previous|prior)\s+instructions|system\s*prompt|prompt\s+do\s+sistema|desconsider\w*\s+(as\s+)?instru"
    r"|(^|\n)\s*(system|assistant|developer|sistema)\s*:|<\|?\s*(system|im_start|im_end)|\[/?inst\]"
    r"|voc[eê]\s+agora\s+[eé]|you\s+are\s+now|act\s+as|aja\s+como|finja\s+que", re.I)


def suspeita(texto):
    return bool(INJECAO.search(texto or ""))


def como_dado(texto):
    """Texto do lead dentro do delimitador; marcas iguais dentro do texto viram [marca] (não fecham o dado)."""
    return "%s\n%s\n%s" % (ABRE, MARCA.sub("[marca]", texto or ""), FECHA)


def _avisar(onde, erro):
    print("vendas: atendente: %s falhou: %s" % (onde, type(erro).__name__), file=sys.stderr)


def _pausada(conversa, agora):
    if conversa["modo"] == "humano":
        return True
    if not conversa["pausada_ate"]:
        return False
    try:
        ate = datetime.datetime.fromisoformat(conversa["pausada_ate"])
    except ValueError:
        return True
    return (ate if ate.tzinfo else ate.replace(tzinfo=UTC)) > agora


def contexto(con, conversa_id, gatilho_id, limite=CONTEXTO):
    """(mensagens para o cérebro, linha do gatilho, suspeitas). Só linhas confiáveis até gatilho_id. Gatilho None
    (nada a responder) se gatilho_id não é texto confiável do lead ou se já há entrada confiável mais nova."""
    if gatilho_id is None or con.execute("SELECT 1 FROM mensagens WHERE conversa_id = ? AND id > ? AND confiavel = 1 "
                                         "AND direcao = 'entrada'", (conversa_id, gatilho_id)).fetchone():
        return [], None, []
    linhas = con.execute("SELECT id, id_externo, direcao, tipo, texto FROM mensagens WHERE conversa_id = ? "
                         "AND id <= ? AND confiavel = 1 ORDER BY id DESC LIMIT ?",
                         (conversa_id, gatilho_id, limite)).fetchall()[::-1]
    if not linhas or linhas[-1]["id"] != gatilho_id or linhas[-1]["direcao"] != "entrada" \
            or linhas[-1]["tipo"] != "texto" or not linhas[-1]["id_externo"]:
        return [], None, []
    mensagens, suspeitas = [], []
    for m in linhas:
        texto = m["texto"] if m["tipo"] == "texto" else "[%s]" % m["tipo"]
        if m["direcao"] == "saida":
            mensagens.append({"role": "assistant", "content": texto or ""})
            continue
        if suspeita(texto):
            suspeitas.append(m["id"])
        mensagens.append({"role": "user", "content": como_dado(texto)})
    return mensagens, linhas[-1], suspeitas


class Atendente:
    """abrir() devolve uma conexão nova; obter_conector() o conector atual (ou None)."""

    def __init__(self, abrir, cerebro_ia, obter_conector, espera=ESPERA_S):
        self.abrir, self.cerebro, self.obter_conector, self.espera = abrir, cerebro_ia, obter_conector, espera
        self._mutex = threading.Lock()
        self._prazos = {}      # conversa -> prazo (monotonic) do debounce
        self._gatilhos = {}    # conversa -> maior mensagem_id entregue pelo gancho nesta espera
        self._travas = {}      # conversa -> Lock da rodada
        self._threads = set()
        self._parar = threading.Event()

    def receber(self, conversa_id, mensagem_id=None):
        """O gancho: empurra o prazo da conversa; só abre uma thread se ainda não houver uma esperando."""
        if self._parar.is_set():
            return
        with self._mutex:
            esperando = conversa_id in self._prazos
            self._prazos[conversa_id] = time.monotonic() + self.espera
            if mensagem_id is not None:
                self._gatilhos[conversa_id] = max(mensagem_id, self._gatilhos.get(conversa_id, mensagem_id))
            if esperando:
                return
            t = threading.Thread(target=self._rodar, args=(conversa_id,), daemon=True)
            self._threads.add(t)
        t.start()

    def parar(self, tempo=10):
        self._parar.set()
        with self._mutex:
            threads = list(self._threads)
        for t in threads:
            t.join(tempo)

    def _rodar(self, conversa_id):
        try:
            while True:
                with self._mutex:
                    falta = self._prazos[conversa_id] - time.monotonic()
                    if falta <= 0:
                        del self._prazos[conversa_id]   # mensagem nova daqui em diante abre outra espera
                        gatilho_id = self._gatilhos.pop(conversa_id, None)
                        trava = self._travas.setdefault(conversa_id, threading.Lock())
                        break
                if self._parar.wait(falta):
                    with self._mutex:
                        self._prazos.pop(conversa_id, None)
                        self._gatilhos.pop(conversa_id, None)
                    return
            with trava:
                if not self._parar.is_set():
                    self.responder(conversa_id, gatilho_id)
        except Exception as e:
            _avisar("rodada", e)
        finally:
            with self._mutex:
                self._threads.discard(threading.current_thread())

    def responder(self, conversa_id, gatilho_id, agora=None):
        """Uma rodada (com a trava da conversa já pega). Devolve o resultado do portão ou None."""
        con = self.abrir()
        try:
            return self._responder(con, conversa_id, gatilho_id, agora or datetime.datetime.now(UTC))
        finally:
            con.close()

    def _responder(self, con, conversa_id, gatilho_id, agora):
        conversa = con.execute("SELECT c.modo, c.pausada_ate, k.telefone, k.optout_em FROM conversas c JOIN contatos k "
                               "ON k.id = c.contato_id WHERE c.id = ?", (conversa_id,)).fetchone()
        if conversa is None or conversa["optout_em"] or _pausada(conversa, agora):
            return None   # economiza a chamada; o portão reconfere na hora de enviar
        mensagens, gatilho, suspeitas = contexto(con, conversa_id, gatilho_id)
        if gatilho is None:
            return None
        conector, instancia = self.obter_conector(), banco.ler_config(con, "instancia")
        if conector is None or not instancia:
            cerebro.marcar_precisa_de_voce(con, conversa_id, "sem_conector")
            return None
        if suspeitas:   # autocommit: nada fica travado
            cerebro.marcar_precisa_de_voce(con, conversa_id, "injecao_suspeita")
            banco.registrar_evento(con, "injecao_suspeita", json.dumps(
                {"conversa_id": conversa_id, "mensagens": suspeitas}))
        r = self.cerebro.responder(con, conversa_id, mensagens)   # rede, fora de transação
        if not r["texto"]:
            return None
        texto = "\n".join([r["texto"]] + [u for u in r["links"] if u not in r["texto"]])
        return portao.enviar_ia(con, conector, instancia, conversa["telefone"], texto, conversa_id,
                                gatilho["id_externo"], 1)
