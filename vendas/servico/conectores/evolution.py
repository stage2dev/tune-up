"""Conector da Evolution API v2 por urllib. URL e chave vêm de variáveis de ambiente lidas pelo serviço, nunca da
árvore do projeto. Só cria instância, lê QR/estado, configura webhook e envia: nunca desconecta nem apaga a sessão.
Erros: NaoEnviado (recusa de conexão, 3xx/4xx) e EnvioIncerto (timeout ou queda depois de escrever o pedido, 5xx,
resposta sem id). No envio, 400 é EnvioIncerto: a Evolution também devolve 400 quando a mensagem já saiu e o passo
seguinte (gravar no banco, transcrever) falhou; só é NaoEnviado se o corpo provar número inexistente. Nenhuma mensagem de erro carrega a chave, o texto enviado ou o corpo da resposta."""
import base64
import datetime
import http.client
import json
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

from servico.conectores import base
from servico.conectores.base import EnvioIncerto, MidiaExpirada, MidiaGrandeDemais, MidiaIndisponivel, NaoEnviado
from servico.rotas import CAB_SEGREDO

VAR_URL = "VENDAS_EVOLUTION_URL"
VAR_CHAVE = "VENDAS_EVOLUTION_CHAVE"
TEMPO_LIMITE_S = 15
EVENTOS_WEBHOOK = ["MESSAGES_UPSERT", "SEND_MESSAGE", "CONNECTION_UPDATE", "QRCODE_UPDATED"]
ESTADO_EVOLUTION = {"open": "conectado", "connecting": "aguardando_qr"}  # close, refused e o resto: desconectado
PREFIXO_PNG = "data:image/png;base64,"
JA_EXISTE = (400, 403, 409)
POR_PAGINA = 100   # em /chat/findMessages, "offset" é o tamanho da página
PAGINAS_MAX = 50  # nome em uso; 401 (chave errada) e o resto sobem como erro
TEMPO_MIDIA_S = 30
ESPERA_NOVA_TENTATIVA_S = 1.0
MIDIA_MAX = 20 * 1024 * 1024   # o maior teto por tipo (documento); o base64 + JSON cabe em RESPOSTA_MIDIA_MAX
RESPOSTA_MIDIA_MAX = MIDIA_MAX * 4 // 3 + 1024 * 1024
MIDIA_EXPIRADA = (404, 410)
# A Evolution devolve TODA falha do getBase64FromMediaMessage como 400 (BadRequestException(error.toString())): só o
# corpo diz se é a mensagem que ela não tem ou a mídia que o CDN do WhatsApp já não serve. O resto do 400 é passageiro.
SINAIS_EXPIRADA = ("message not found", "status code 404", "status code 410", "failed to fetch stored media",
                   "reupload", "re-upload")


class PaginasDemais(base.ErroConector):
    """A janela tem mais de PAGINAS_MAX páginas: ler só parte perderia um SAIR das páginas puladas."""


class _SemRedirecionar(urllib.request.HTTPRedirectHandler):
    """Redirecionamento levaria a chave (header apikey) para outro destino: vira erro 3xx."""

    def redirect_request(self, *args, **kwargs):
        return None


class Evolution(base.Conector):
    def __init__(self, url, chave, base_webhook, segredo, tempo_limite=TEMPO_LIMITE_S):
        if not isinstance(url, str) or not re.match(r"^https?://[^/\s]+", url):
            raise ValueError("URL da Evolution inválida (http:// ou https://)")
        if not chave:
            raise ValueError("chave da Evolution ausente")
        self.url = url.rstrip("/")
        self._chave = chave
        self.base_webhook = base_webhook.rstrip("/")
        self._segredo = segredo
        self.tempo_limite = tempo_limite
        self._abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SemRedirecionar())

    @classmethod
    def do_ambiente(cls, base_webhook, segredo, ambiente, tempo_limite=TEMPO_LIMITE_S):
        """`ambiente` = os.environ (ou um dict nos testes)."""
        url, chave = ambiente.get(VAR_URL, ""), ambiente.get(VAR_CHAVE, "")
        if not url or not chave:
            raise ValueError("defina %s e %s no ambiente do serviço" % (VAR_URL, VAR_CHAVE))
        return cls(url, chave, base_webhook, segredo, tempo_limite)

    def __repr__(self):
        return "Evolution(url=%r)" % self.url

    def _caminho(self, *partes):
        return "/" + "/".join(urllib.parse.quote(p, safe="") for p in partes)

    def _pedir(self, metodo, caminho, corpo=None, envio=False):
        dados = None if corpo is None else json.dumps(corpo).encode("utf-8")
        pedido = urllib.request.Request(self.url + caminho, data=dados, method=metodo, headers={
            "apikey": self._chave, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self._abridor.open(pedido, timeout=self.tempo_limite) as resposta:
                bruto = resposta.read()
        except urllib.error.HTTPError as erro:
            recusa_provada = envio and erro.code == 400 and _numero_inexistente(erro)
            erro.close()
            classe = NaoEnviado if erro.code < 500 else EnvioIncerto
            if envio and erro.code == 400:
                classe = base.NumeroInexistente if recusa_provada else EnvioIncerto
            raise classe("Evolution respondeu HTTP %d" % erro.code, erro.code)
        except urllib.error.URLError as erro:
            # urllib embrulha em URLError só o que falha ANTES da resposta: conectar ou escrever o pedido.
            # Pedido sem corpo inteiro não é processado do outro lado.
            raise NaoEnviado("Evolution inalcançável (%s)" % type(erro.reason).__name__)
        except (socket.timeout, TimeoutError, http.client.HTTPException, OSError) as erro:
            # Pedido já escrito; a resposta não veio inteira.
            raise EnvioIncerto("Evolution não respondeu (%s)" % type(erro).__name__)
        try:
            return json.loads(bruto.decode("utf-8")) if bruto else {}
        except ValueError:
            raise EnvioIncerto("Evolution respondeu algo que não é JSON")

    def _webhook(self, instancia):
        return {"url": "%s/webhook/%s" % (self.base_webhook, instancia), "byEvents": False, "base64": False,
                "headers": {CAB_SEGREDO: self._segredo, "Content-Type": "application/json"},
                "events": list(EVENTOS_WEBHOOK)}

    def criar(self, instancia):
        """Cria a instância com o webhook (URL + header do segredo). Já existindo (4xx), só regrava o webhook."""
        base.validar_instancia(instancia)
        try:
            self._pedir("POST", "/instance/create", {
                "instanceName": instancia, "integration": "WHATSAPP-BAILEYS", "qrcode": True,
                "syncFullHistory": False,   # nada do histórico antigo do celular (privacidade e carga)
                "webhook": self._webhook(instancia)})
        except NaoEnviado as erro:
            if erro.status not in JA_EXISTE:
                raise
            webhook = dict(self._webhook(instancia), enabled=True)
            self._pedir("POST", self._caminho("webhook", "set", instancia), {"webhook": webhook})

    def qr(self, instancia):
        base.validar_instancia(instancia)
        dados = self._pedir("GET", self._caminho("instance", "connect", instancia))
        if not isinstance(dados, dict) or dados.get("error"):
            raise NaoEnviado("Evolution não devolveu o QR")
        return _data_uri(dados.get("base64"))

    def estado(self, instancia):
        base.validar_instancia(instancia)
        try:
            dados = self._pedir("GET", self._caminho("instance", "connectionState", instancia))
        except NaoEnviado as erro:
            if erro.status == 404:
                return "desconectado"
            raise
        info = dados.get("instance") if isinstance(dados, dict) else None
        return ESTADO_EVOLUTION.get((info or {}).get("state"), "desconectado")

    def enviar_texto(self, instancia, telefone, texto):
        base.validar_instancia(instancia)
        return _id_externo(self._pedir("POST", self._caminho("message", "sendText", instancia),
                                       {"number": _numero(telefone), "text": texto}, envio=True))

    def enviar_audio(self, instancia, telefone, caminho_ogg):
        base.validar_instancia(instancia)
        numero = _numero(telefone)
        try:
            with open(caminho_ogg, "rb") as arquivo:
                audio = base64.b64encode(arquivo.read()).decode("ascii")
        except OSError as erro:
            raise NaoEnviado("áudio ilegível (%s)" % type(erro).__name__)
        return _id_externo(self._pedir("POST", self._caminho("message", "sendWhatsAppAudio", instancia),
                                       {"number": numero, "audio": audio}, envio=True))

    def digitando(self, instancia, telefone, ms):
        base.validar_instancia(instancia)
        self._pedir("POST", self._caminho("chat", "sendPresence", instancia),
                    {"number": _numero(telefone), "presence": "composing", "delay": int(ms)})
        return True

    def traduzir_evento(self, corpo):
        return traduzir(corpo)

    def baixar_midia(self, instancia, mensagem):
        """POST /chat/getBase64FromMediaMessage/<instancia> com {"message": {"key": ...}}: a Evolution acha a
        mensagem no banco dela pelo id da chave (DATABASE_SAVE_DATA_NEW_MESSAGE=true) e baixa do WhatsApp. Uma nova
        tentativa curta em rede/5xx e em 400 sem sinal de expirada; 404/410 ou 400 com SINAIS_EXPIRADA no corpo =
        expirada; resposta acima de RESPOSTA_MIDIA_MAX = grande_demais."""
        base.validar_instancia(instancia)
        chave = {k: mensagem.get(k) for k in ("id", "remoteJid", "fromMe")} if isinstance(mensagem, dict) else {}
        if not isinstance(chave.get("id"), str) or not chave["id"]:
            raise MidiaExpirada("mensagem sem id")
        corpo = json.dumps({"message": {"key": chave}, "convertToMp4": False}).encode("utf-8")
        caminho = self._caminho("chat", "getBase64FromMediaMessage", instancia)
        for tentativa in (1, 2):
            pedido = urllib.request.Request(self.url + caminho, data=corpo, method="POST", headers={
                "apikey": self._chave, "Content-Type": "application/json", "Accept": "application/json"})
            try:
                with self._abridor.open(pedido, timeout=TEMPO_MIDIA_S) as resposta:
                    bruto = resposta.read(RESPOSTA_MIDIA_MAX + 1)
                break
            except urllib.error.HTTPError as erro:
                expirada = erro.code in MIDIA_EXPIRADA or (erro.code == 400 and _sinal_de_expirada(erro))
                erro.close()
                if expirada:
                    raise MidiaExpirada("Evolution respondeu HTTP %d" % erro.code, erro.code)
                if (erro.code < 500 and erro.code != 400) or tentativa == 2:
                    raise MidiaIndisponivel("Evolution respondeu HTTP %d" % erro.code, erro.code)
            except (urllib.error.URLError, socket.timeout, TimeoutError, http.client.HTTPException, OSError) as erro:
                if tentativa == 2:
                    raise MidiaIndisponivel("Evolution não respondeu (%s)" % type(erro).__name__)
            time.sleep(ESPERA_NOVA_TENTATIVA_S)
        if len(bruto) > RESPOSTA_MIDIA_MAX:
            raise MidiaGrandeDemais("resposta da mídia acima do teto")
        return _midia(bruto)

    def mensagens_desde(self, instancia, desde, ate):
        """POST /chat/findMessages com where.messageTimestamp {gte, lte} (datas ISO), página a página. Só acha o
        que a Evolution gravou no banco dela (DATABASE_SAVE_DATA_NEW_MESSAGE=true). Mais de PAGINAS_MAX páginas levanta
        PaginasDemais (nada é devolvido pela metade)."""
        base.validar_instancia(instancia)
        filtro = {"messageTimestamp": {"gte": _iso_z(desde), "lte": _iso_z(ate)}}
        eventos, pagina = [], 1
        while True:
            dados = self._pedir("POST", self._caminho("chat", "findMessages", instancia),
                                {"where": filtro, "page": pagina, "offset": POR_PAGINA})
            bloco = dados.get("messages") if isinstance(dados, dict) else None
            registros = bloco.get("records") if isinstance(bloco, dict) else None
            if not isinstance(registros, list) or not registros:
                break
            eventos.extend(e for e in (_mensagem(r, False) for r in registros) if e)
            try:
                paginas = int(bloco.get("pages") or 0)
            except (TypeError, ValueError):
                paginas = 0
            if paginas > PAGINAS_MAX:
                raise PaginasDemais("findMessages: %d páginas (máximo %d)" % (paginas, PAGINAS_MAX))
            if pagina >= paginas:
                break
            pagina += 1
        return eventos


def _iso_z(momento):
    return momento.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _numero(telefone):
    digitos = re.sub(r"\D", "", telefone or "")
    if not 8 <= len(digitos) <= 15:
        raise NaoEnviado("telefone inválido")
    return digitos


def _numero_inexistente(erro):
    """400 do envio com `response.message` = [{"exists": false, ...}]: a checagem do número barrou antes de enviar."""
    try:
        dados = json.loads(erro.read(65536).decode("utf-8"))
    except (OSError, ValueError, http.client.HTTPException):
        return False
    resposta = dados.get("response") if isinstance(dados, dict) else None
    itens = resposta.get("message") if isinstance(resposta, dict) else None
    return isinstance(itens, list) and any(isinstance(i, dict) and i.get("exists") is False for i in itens)


def _sinal_de_expirada(erro):
    """Corpo do 400 com um dos SINAIS_EXPIRADA (minúsculas). O corpo não vai para log nem para o motivo."""
    try:
        corpo = erro.read(65536).decode("utf-8", "replace").lower()
    except (OSError, http.client.HTTPException):
        return False
    return any(s in corpo for s in SINAIS_EXPIRADA)


def _id_externo(dados):
    chave = dados.get("key") if isinstance(dados, dict) else None
    ident = chave.get("id") if isinstance(chave, dict) else None
    if not ident:
        raise EnvioIncerto("Evolution aceitou mas não devolveu o id da mensagem")
    return str(ident)


def _midia(bruto):
    try:
        dados = json.loads(bruto.decode("utf-8"))
        b64 = dados.get("base64") or dados.get("data")
        conteudo = base64.b64decode(b64.split(",")[-1], validate=True)
    except (ValueError, AttributeError, TypeError, UnicodeDecodeError):
        raise MidiaIndisponivel("Evolution respondeu algo que não é a mídia")
    if not conteudo:
        raise MidiaIndisponivel("mídia vazia")
    tipo, nome = dados.get("mimetype"), dados.get("fileName")
    return conteudo, tipo if isinstance(tipo, str) else None, nome if isinstance(nome, str) else None


def _data_uri(valor):
    if not isinstance(valor, str) or not valor:
        return None
    return valor if valor.startswith(PREFIXO_PNG) else PREFIXO_PNG + valor.split(",")[-1]


# --- tradução do webhook (corpo já decodificado de JSON) ---

def _digitos_jid(jid):
    if not isinstance(jid, str) or "@" not in jid:
        return None
    usuario = jid.split("@", 1)[0].split(":", 1)[0]
    return usuario if usuario.isdigit() else None


def _conteudo(mensagem):
    """(tipo, texto) a partir do objeto `message` do Baileys."""
    if not isinstance(mensagem, dict):
        return "outro", None
    for envoltorio in ("ephemeralMessage", "viewOnceMessage", "viewOnceMessageV2", "documentWithCaptionMessage"):
        dentro = mensagem.get(envoltorio)
        if isinstance(dentro, dict) and isinstance(dentro.get("message"), dict):
            mensagem = dentro["message"]
    if isinstance(mensagem.get("conversation"), str):
        return "texto", mensagem["conversation"]
    estendida = mensagem.get("extendedTextMessage")
    if isinstance(estendida, dict) and isinstance(estendida.get("text"), str):
        return "texto", estendida["text"]
    for campo, tipo in (("audioMessage", "audio"), ("imageMessage", "imagem"), ("documentMessage", "documento")):
        if isinstance(mensagem.get(campo), dict):
            legenda = mensagem[campo].get("caption")
            return tipo, legenda if isinstance(legenda, str) else None
    return "outro", None


def _mensagem(dados, enviada):
    chave = dados.get("key") if isinstance(dados, dict) else None
    if not isinstance(chave, dict) or not chave.get("id"):
        return None
    jid = chave.get("remoteJid") or ""
    from_me = bool(chave.get("fromMe")) or enviada
    grupo = jid.endswith("@g.us")
    lid = alternativa = None
    if grupo:
        quem = chave.get("participant") or dados.get("participant") or ""
        if quem.endswith("@lid"):
            lid, alternativa = quem, chave.get("participantAlt") or chave.get("participantPn")
            remetente = _digitos_jid(alternativa)
        else:
            remetente = _digitos_jid(quem)
    elif jid.endswith("@lid"):
        lid = jid
        alternativa = chave.get("remoteJidAlt") or chave.get("senderPn") or dados.get("senderPn") or None
        remetente = _digitos_jid(alternativa)
    else:
        remetente = _digitos_jid(jid)
    tipo, texto = _conteudo(dados.get("message"))
    try:
        momento = int(dados.get("messageTimestamp"))
    except (TypeError, ValueError):
        momento = None
    perfil = dados.get("pushName")   # em fromMe é o nome do DONO: nunca vai para o lead
    evento = {"tipo_evento": "mensagem", "direcao": "enviada" if from_me else "recebida",
                  "id_externo": str(chave["id"]), "remetente": remetente, "fromMe": from_me, "grupo": grupo,
                  "tipo": tipo, "texto": texto, "timestamp": momento, "lid": lid, "alternativa": alternativa,
                  "nome_perfil": perfil if isinstance(perfil, str) and not from_me else None}
    if tipo in ("audio", "imagem", "documento"):   # o que baixar_midia precisa depois
        evento["chave_midia"] = {"id": str(chave["id"]), "remoteJid": jid, "fromMe": from_me}
    return evento


def traduzir(corpo):
    """Corpo do webhook -> lista de eventos normalizados (ver base.Conector). Desconhecido ou malformado -> []."""
    if not isinstance(corpo, dict):
        return []
    nome = str(corpo.get("event") or "").lower().replace("_", ".")
    dados = corpo.get("data")
    if nome in ("messages.upsert", "send.message"):
        lista = dados if isinstance(dados, list) else (dados.get("messages") if isinstance(dados, dict)
                                                         and isinstance(dados.get("messages"), list) else [dados])
        eventos = [_mensagem(item, nome == "send.message") for item in lista]
        return [e for e in eventos if e]
    if nome == "connection.update" and isinstance(dados, dict):
        return [{"tipo_evento": "estado", "estado": ESTADO_EVOLUTION.get(dados.get("state"), "desconectado")}]
    if nome == "qrcode.updated" and isinstance(dados, dict):
        qr = _data_uri((dados.get("qrcode") or {}).get("base64") if isinstance(dados.get("qrcode"), dict) else None)
        return [{"tipo_evento": "qr", "qr": qr}] if qr else []
    return []
