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
  aqui só há leituras e escritas curtas em autocommit; o envio passa por servico/saida.py (sanitizador, anti-loop,
  balões) e sai pelo portão (origem 'ia'), que reconfere opt-out, pausa, modo humano e tetos NA HORA DE ENVIAR.
- Modo da conversa (servico/rascunhos.py): 'rascunho' (padrão) guarda o texto como rascunho e NADA sai; 'automatico'
  envia pelo portão. O sanitizador vale nos dois.
- Não responde: modo humano, pausada, opt-out, entrada confiável mais nova que o gatilho, rodada sem gatilho.
  Grupo, fromMe, mídia e mensagem velha nem chegam aqui (o recebimento não chama o gancho).
- parar(): as esperas acabam sem responder e as threads terminam (join com tempo limite).
- Áudio (servico/audio_ia.py): com `app` (voz) a rodada oferece responder_em_audio só quando o código decide; a IA
  usou = o texto vai como nota de voz (falha da voz = texto) ou fica como rascunho 'enviar como áudio'.
- Áudio e imagem do lead (servico/entender.py, chaves da aba IA): o gatilho pode ser um áudio ou uma imagem. Antes
  do modelo a rodada espera o download, transcreve o áudio e lê a imagem; a transcrição vai como DADO (mesmo
  delimitador e mesmo filtro de injeção do texto, rotulada como transcrição de áudio) e a imagem como parte
  image_url (detail low). Transcrição ou legenda que é um SAIR = opt-out e confirmação, sem modelo. Falha em
  qualquer passo = o modelo não é chamado, nada sai, "precisa de você" com o motivo. Documento nunca chega
  aqui (o recebimento marca documento_recebido). Imagem que a API recusou fica marcada (midias.falha_ia).
- Conversa pausada (dono ou modo humano) com mídia no lote: o modelo não é chamado, mas a triagem de SAIR roda nas
  transcrições e legendas (com 'IA entende' ligado) e a conversa fica "precisa de você" (pausa_humana). Em modo
  humano o áudio não é transcrito (só a legenda passa pela triagem)."""
import datetime
import json
import re
import sys
import threading
import time

from servico import audio_ia, banco, cerebro, chave, entender, rascunhos, recebimento, saida

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
ROTULO_AUDIO = "Transcrição automática de um áudio do lead (pode ter erros de transcrição):"
ROTULO_IMAGEM = "O lead mandou a imagem anexa. Legenda dele:"
GATILHOS = ("texto", "audio", "imagem")


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


def _conteudo(m, imagens):
    """(conteúdo da mensagem do lead para o modelo, texto que passa pelo filtro de injeção)."""
    if m["tipo"] == "audio" and m["transcricao"]:
        return "%s\n%s" % (ROTULO_AUDIO, como_dado(m["transcricao"])), m["transcricao"]
    if m["id"] in imagens:
        legenda = m["texto"] or ""
        return [{"type": "text", "text": "%s\n%s" % (ROTULO_IMAGEM, como_dado(legenda))},
                {"type": "image_url", "image_url": {"url": imagens[m["id"]], "detail": "low"}}], legenda
    texto = m["texto"] if m["tipo"] == "texto" else "[%s]" % m["tipo"]
    return como_dado(texto), texto


def contexto(con, conversa_id, gatilho_id, limite=CONTEXTO, imagens=None):
    """(mensagens para o cérebro, linha do gatilho, suspeitas). Só linhas confiáveis até gatilho_id. Gatilho None
    (nada a responder) se gatilho_id não é texto/áudio/imagem confiável do lead ou se já há entrada confiável mais nova
    que tem rodada própria ou já marcou 'precisa de você'. Tipo 'outro' (reação, figurinha, vídeo) não cala.
    imagens: {mensagem_id: data URL} desta rodada (entender.preparar); áudio com transcricao gravada vai como dado."""
    if gatilho_id is None or con.execute("SELECT 1 FROM mensagens WHERE conversa_id = ? AND id > ? AND confiavel = 1 "
                                         "AND direcao = 'entrada' AND tipo IN ('texto', 'audio', 'imagem', "
                                         "'documento')", (conversa_id, gatilho_id)).fetchone():
        return [], None, []
    linhas = con.execute("SELECT id, id_externo, direcao, tipo, texto, transcricao FROM mensagens WHERE conversa_id = ? "
                         "AND id <= ? AND confiavel = 1 ORDER BY id DESC LIMIT ?",
                         (conversa_id, gatilho_id, limite)).fetchall()[::-1]
    if not linhas or linhas[-1]["id"] != gatilho_id or linhas[-1]["direcao"] != "entrada" \
            or linhas[-1]["tipo"] not in GATILHOS or not linhas[-1]["id_externo"]:
        return [], None, []
    mensagens, suspeitas = [], []
    for m in linhas:
        if m["direcao"] == "saida":
            texto = m["texto"] if m["tipo"] == "texto" else "[%s]" % m["tipo"]
            mensagens.append({"role": "assistant", "content": texto or ""})
            continue
        conteudo, texto = _conteudo(m, imagens or {})
        if suspeita(texto):
            suspeitas.append(m["id"])
        mensagens.append({"role": "user", "content": conteudo})
    return mensagens, linhas[-1], suspeitas


class Atendente:
    """abrir() devolve uma conexão nova; obter_conector() o conector atual (ou None); app = o do serviço (voz:
    pasta_dados, conector, elevenlabs_url); sem app a IA nunca responde em áudio. entende(con, tipo) = a mesma função
    do recebimento.registrar_entende; None = a IA não entende áudio nem imagem."""

    def __init__(self, abrir, cerebro_ia, obter_conector, espera=ESPERA_S, app=None, entende=None):
        self.abrir, self.cerebro, self.obter_conector, self.espera = abrir, cerebro_ia, obter_conector, espera
        self.app, self.entende = app, entende
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
        """Uma rodada (com a trava da conversa já pega). Devolve o resultado de saida.entregar ou None."""
        con = self.abrir()
        try:
            return self._responder(con, conversa_id, gatilho_id, agora or datetime.datetime.now(UTC))
        finally:
            con.close()

    def _responder(self, con, conversa_id, gatilho_id, agora):
        conversa = con.execute("SELECT c.modo, c.pausada_ate, k.telefone, k.optout_em FROM conversas c JOIN contatos k "
                               "ON k.id = c.contato_id WHERE c.id = ?", (conversa_id,)).fetchone()
        if conversa is None or conversa["optout_em"]:
            return None   # economiza a chamada; o portão reconfere na hora de enviar
        pausada = _pausada(conversa, agora)
        mensagens, gatilho, suspeitas = contexto(con, conversa_id, gatilho_id)
        if gatilho is None:
            return None
        if pausada:
            return self._na_pausa(con, conversa_id, gatilho["id"], conversa, agora)
        conector, instancia = self.obter_conector(), banco.ler_config(con, "instancia")
        if conector is None or not instancia:
            cerebro.marcar_precisa_de_voce(con, conversa_id, "sem_conector")
            return None
        try:   # espera e rede, fora de transação
            ent = entender.preparar(self.cerebro, con, conversa_id, gatilho["id"], self._parar, self.entende)
        except Exception as e:   # como no cérebro: nada sai, IA fora da conversa, o dono vê
            if con.in_transaction:
                con.execute("ROLLBACK")
            _avisar("mídia", e)
            cerebro.marcar_precisa_de_voce(con, conversa_id, "erro_interno", True, type(e).__name__)
            return None
        if ent.get("sair"):   # SAIR falado ou na legenda: opt-out e confirmação pelo portão, como no texto
            return self._sair(con, conector, conversa, agora)
        if ent.get("parado"):
            return None
        for motivo in [ent["motivo"]] if not ent["ok"] else ent["avisos"]:
            cerebro.marcar_precisa_de_voce(con, conversa_id, motivo)
        if not ent["ok"] or self._parar.is_set():
            return None   # falha nunca chega ao modelo como fala do lead
        conversa = con.execute("SELECT c.modo, c.pausada_ate, k.telefone, k.optout_em FROM conversas c JOIN contatos k "
                               "ON k.id = c.contato_id WHERE c.id = ?", (conversa_id,)).fetchone()
        if conversa["optout_em"] or _pausada(conversa, agora):   # mudou durante a espera
            return None
        mensagens, gatilho, suspeitas = contexto(con, conversa_id, gatilho_id, imagens=ent["imagens"])
        if gatilho is None:
            return None
        if suspeitas:   # autocommit: nada fica travado
            cerebro.marcar_precisa_de_voce(con, conversa_id, "injecao_suspeita")
            banco.registrar_evento(con, "injecao_suspeita", json.dumps(
                {"conversa_id": conversa_id, "mensagens": suspeitas}))
        audio = audio_ia.oferecer(self.app, con, conversa_id, gatilho["id"])
        r = self.cerebro.responder(con, conversa_id, mensagens, audio=audio)   # rede, fora de transação
        if r.get("motivo") in ("modelo_sem_visao", "imagem_recusada") and ent["imagens"]:
            entender.guardar_falha(con, list(ent["imagens"]), r["motivo"])   # a mesma imagem não vai de novo
        if not r["texto"]:
            return None
        texto = "\n".join([r["texto"]] + [u for u in r["links"] if u not in r["texto"]])
        permitidos, segredos = list(cerebro.ler_links(self.cerebro.raiz).values()), [chave.ler(self.cerebro.pasta_dados)]
        reescrever = lambda t, pedido: self.cerebro.reescrever(con, t, pedido)  # noqa: E731
        if rascunhos.modo_da_conversa(con, conversa_id) == "rascunho":   # nada sai: o dono aprova na tela
            return rascunhos.guardar(con, conversa_id, gatilho["id"], texto, permitidos, segredos, reescrever,
                                     como_audio=audio and r.get("como_audio"))
        if audio and r.get("como_audio"):
            return audio_ia.entregar(self.app, con, conector, instancia, conversa["telefone"], conversa_id,
                                     gatilho["id_externo"], texto, permitidos, segredos, reescrever)
        return saida.entregar(con, conector, instancia, conversa["telefone"], conversa_id, gatilho["id_externo"],
                              texto, permitidos=permitidos, segredos=segredos, reescrever=reescrever)

    def _sair(self, con, conector, conversa, agora):
        banco.marcar_optout(con, conversa["telefone"], agora.astimezone(UTC).isoformat(timespec="seconds"))
        recebimento.executar_depois(con, conector, [("sair", conversa["telefone"])])

    def _na_pausa(self, con, conversa_id, gatilho_id, conversa, agora):
        """Pausada: nada vai ao modelo. SAIR falado ou na legenda ainda vale; mídia no lote = "precisa de você".
        Modo humano ('IA desligada' na conversa): o áudio NÃO é transcrito (nada da voz vai à OpenAI); só a legenda."""
        entende = self.entende
        if conversa["modo"] == "humano" and entende is not None:
            entende = lambda c, tipo: tipo != "audio" and self.entende(c, tipo)  # noqa: E731
        try:   # espera e rede, fora de transação
            ent = entender.preparar(self.cerebro, con, conversa_id, gatilho_id, self._parar, entende,
                                    so_triagem=True)
        except Exception as e:
            if con.in_transaction:
                con.execute("ROLLBACK")
            _avisar("mídia na pausa", e)
            ent = {"sair": False, "parado": False, "tinha_midia": True}
        if ent.get("sair"):
            return self._sair(con, self.obter_conector(), conversa, agora)
        if ent.get("tinha_midia") and not ent.get("parado"):
            cerebro.marcar_precisa_de_voce(con, conversa_id, "pausa_humana")
        return None
