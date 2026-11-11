"""Recebimento: webhook -> conector.traduzir_evento -> dedupe por id_externo -> descarta grupo -> grava contato,
conversa e mensagem. Tudo numa transação; o que fala para fora (confirmação de SAIR pelo portão, gancho da IA) roda
DEPOIS do commit, fora da transação.

- SAIR (sair, parar, stop, cancelar, descadastrar): só com a mensagem INTEIRA normalizada igual à palavra. Grava
  optout_em e manda UMA confirmação (portão, origem confirmacao_sair); a IA não é chamada. Frase que só contém a
  palavra (ou "não quero") marca "precisa de você".
- @lid: usa remoteJidAlt/senderPn (e aprende o mapa lid -> telefone); sem alternativa nem mapa, linha em eventos.
- Nome do perfil (pushName) do lead vira nome_whatsapp só se o contato não tem nome do CSV/dono; o de fromMe é do
  dono e é ignorado; webhook sem segredo não grava nome.
- Áudio, imagem e documento do lead: grava o tipo e a linha em `midias`, marca "precisa de você", sem IA; o
  download (midia.py) entra na fila depois do commit, só com segredo válido.
- Mensagem com mais de 30 min: sem IA, marca "precisa de você" (a subida busca o que chegou com o serviço parado).
- fromMe: eco de envio nosso (pelo id devolvido ou texto igual em até 5 s) nunca pausa a IA; fromMe que não casa é o
  dono respondendo do celular: grava e pausa a IA da conversa por 15 min.
- Webhook com segredo errado (modo "registra e conta"): grava, marca "precisa de você" e grava optout_em do SAIR, mas
  sem efeito para fora: sem confirmação, sem gancho, sem pausa e sem escrever no mapa de @lid. A linha fica com
  confiavel = 0 e a IA não a lê.
- Subida: a janela a buscar (recuperar_desde) fica guardada até a busca dar certo; só a mais antiga vale.
Nenhum telefone ou texto vai para log."""
import datetime
import json
import re
import sys
import unicodedata

from servico import banco, campanha, midia, portao, telefone
from servico.conectores import evolution

UTC = datetime.timezone.utc
PALAVRAS_SAIR = ("sair", "parar", "stop", "cancelar", "descadastrar")
SINAIS = PALAVRAS_SAIR + ("nao quero",)   # dentro de frase: não é opt-out, mas o dono precisa ver
MIDIA = ("audio", "imagem", "documento")
VELHA = datetime.timedelta(minutes=30)
ECO = datetime.timedelta(seconds=5)
PAUSA_DONO = datetime.timedelta(minutes=15)
FOLGA_SUBIDA = datetime.timedelta(minutes=2)
CONFIRMACAO_SAIR = "Pronto, você não vai mais receber mensagens deste número."
JANELA = "recuperar_desde"   # config: início do que ainda falta buscar no conector (some só depois da busca)

_gancho = None


def registrar_gancho(funcao):
    """A IA (parte seguinte) registra aqui quem responde. None volta ao padrão (não faz nada)."""
    global _gancho
    _gancho = funcao


def ao_receber_mensagem_de_lead(conversa_id, mensagem_id):
    """Único gancho: chamado depois do commit, só para texto de lead que a IA pode responder."""
    if _gancho is not None:
        _gancho(conversa_id, mensagem_id)


def normalizar_texto(texto):
    """Minúsculas, sem acento, sem pontuação, espaços simples."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto or "") if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^\w\s]|_", " ", sem_acento.lower()).split())


def e_saida(texto):
    return normalizar_texto(texto) in PALAVRAS_SAIR


def tem_sinal(texto):
    normal = " %s " % normalizar_texto(texto)
    return any(" %s " % s in normal for s in SINAIS)


def _iso(momento):
    return momento.astimezone(UTC).isoformat(timespec="seconds")


def _momento(ev, agora):
    try:
        return datetime.datetime.fromtimestamp(int(ev["timestamp"]), UTC)
    except (TypeError, ValueError, KeyError, OverflowError, OSError):
        return agora


def _evento(con, motivo, ev):
    banco.registrar_evento(con, "mensagem_descartada", json.dumps(
        {"motivo": motivo, "id_externo": ev.get("id_externo")}))


def _resolver(con, ev, confiavel):
    """Telefone do contato da conversa: direto, pela alternativa do @lid ou pelo mapa aprendido. None = sem como.
    Só evento confiável ensina o mapa (um forjado trocaria o contato das próximas mensagens desse @lid)."""
    lid, numero = ev.get("lid"), ev.get("remetente")
    if lid and numero and confiavel:
        banco._exigir(con.execute("INSERT INTO lids (lid, telefone, criado_em) VALUES (?, ?, ?) ON CONFLICT(lid) "
                                  "DO UPDATE SET telefone = excluded.telefone", (lid, numero, banco.agora())))
    if not numero and lid:
        linha = con.execute("SELECT telefone FROM lids WHERE lid = ?", (lid,)).fetchone()
        numero = linha["telefone"] if linha else None
    return numero


def _marcar(con, conversa_id, coluna, valor):
    banco._exigir(con.execute("UPDATE conversas SET %s = ? WHERE id = ?" % coluna, (valor, conversa_id)))


def _envio_ecoado(con, ev, numero, momento):
    """Envio nosso que este fromMe ecoa (ainda sem mensagem ligada), ou None."""
    livre = "AND id NOT IN (SELECT envio_id FROM mensagens WHERE envio_id IS NOT NULL)"
    linha = con.execute("SELECT id FROM envios WHERE id_externo = ? %s" % livre, (ev["id_externo"],)).fetchone()
    if linha is not None:
        return linha["id"]
    v = telefone.variantes(numero)
    sql = ("SELECT id FROM envios WHERE telefone IN (%s) AND estado IN ('pendente', 'enviado', 'incerto') "
           "AND tentado_em BETWEEN ? AND ? %s" % (",".join("?" * len(v)), livre))
    args = list(v) + [_iso(momento - ECO), _iso(momento + ECO)]
    if ev["tipo"] == "audio":   # áudio não tem texto: casa pelo tipo
        sql += " AND tipo = 'audio'"
    else:
        sql += " AND tipo = 'texto' AND conteudo = ?"
        args.append(ev.get("texto"))
    linha = con.execute(sql + " ORDER BY id LIMIT 1", args).fetchone()
    return linha["id"] if linha else None


def _de_mim(con, ev, numero, conversa_id, momento, confiavel):
    envio_id = _envio_ecoado(con, ev, numero, momento) if confiavel else None
    banco.registrar_mensagem(con, conversa_id, "saida", ev.get("texto"), ev["id_externo"], ev["tipo"], envio_id,
                             confiavel)
    if envio_id is None and confiavel:   # o dono respondeu do celular: a IA desta conversa espera
        # nova fala do dono estende; uma mais velha (busca na subida) nunca encurta a pausa que já vale
        con.execute("UPDATE conversas SET pausada_ate = ? WHERE id = ? AND (pausada_ate IS NULL OR pausada_ate < ?)",
                    (_iso(momento + PAUSA_DONO), conversa_id, _iso(momento + PAUSA_DONO)))


def processar(con, ev, agora, depois, confiavel=True):
    """Uma mensagem traduzida, dentro da transação do chamador. Acrescenta em `depois` o que roda após o commit.
    confiavel=False (webhook com segredo errado): grava, mas nada vai para `depois` e nada pausa nem ensina o mapa."""
    if ev.get("grupo") or not ev.get("id_externo"):
        return
    if con.execute("SELECT 1 FROM mensagens WHERE id_externo = ?", (ev["id_externo"],)).fetchone():
        return   # webhook repetido (ou já buscado na subida)
    numero = _resolver(con, ev, confiavel)
    if not numero:
        return _evento(con, "lid_sem_alternativa" if ev.get("lid") else "sem_remetente", ev)
    try:
        numero = telefone.normalizar(numero)
    except telefone.TelefoneInvalido:
        return _evento(con, "telefone_invalido", ev)
    contato_id = banco.salvar_contato(con, numero)
    conversa_id = banco.abrir_conversa(con, contato_id)
    momento = _momento(ev, agora)
    if ev.get("fromMe"):
        return _de_mim(con, ev, numero, conversa_id, momento, confiavel)
    if confiavel:   # webhook forjado não renomeia o lead
        banco.guardar_nome_whatsapp(con, contato_id, ev.get("nome_perfil"))
    tipo = ev.get("tipo") or "outro"
    mensagem_id = banco.registrar_mensagem(con, conversa_id, "entrada", ev.get("texto"), ev["id_externo"], tipo,
                                           confiavel=confiavel)
    if mensagem_id is None:
        return
    if tipo in MIDIA:
        midia_id = midia.registrar(con, mensagem_id, tipo, ev.get("chave_midia"), confiavel)
        if confiavel:
            depois.append(("midia", midia_id))
    campanha.lead_respondeu(con, contato_id)   # o lead falou: sai da fila das campanhas (até sem segredo: só para)
    if not confiavel:   # o dono confere; opt-out é conservador e vale, mas sem confirmação para fora
        if tipo == "texto" and e_saida(ev.get("texto")):
            banco.marcar_optout(con, numero, _iso(momento))
        return _marcar(con, conversa_id, "precisa_de_voce", 1)
    if tipo == "texto" and e_saida(ev.get("texto")):   # antes de tudo: vale até para mensagem velha
        banco.marcar_optout(con, numero, _iso(momento))
        depois.append(("sair", numero))
        return
    if tipo in MIDIA or agora - momento > VELHA or (tipo == "texto" and tem_sinal(ev.get("texto"))):
        _marcar(con, conversa_id, "precisa_de_voce", 1)
        if tipo != "texto" or agora - momento > VELHA:
            return
    if tipo != "texto" or banco.em_optout(con, numero):
        return
    depois.append(("gancho", conversa_id, mensagem_id))


def _avisar(onde, erro):
    print("vendas: recebimento: %s falhou: %s" % (onde, type(erro).__name__), file=sys.stderr)


def executar_depois(con, conector, depois):
    """Fora da transação: confirmação de SAIR pelo portão e o gancho da IA. Uma falha não derruba as outras."""
    for acao in depois:
        try:
            if acao[0] == "sair":
                instancia = banco.ler_config(con, "instancia")
                if conector is None or not instancia:
                    banco.registrar_evento(con, "confirmacao_sair_sem_conector")
                    continue
                texto = banco.ler_config(con, "texto_confirmacao_sair") or CONFIRMACAO_SAIR
                portao.enviar_confirmacao_sair(con, conector, instancia, acao[1], texto)
            elif acao[0] == "midia":   # só põe na fila: o webhook responde sem esperar o download
                midia.enfileirar(con, acao[1])
            else:
                ao_receber_mensagem_de_lead(acao[1], acao[2])
        except Exception as e:
            _avisar(acao[0], e)


def gravar(con, eventos, agora=None, confiavel=True):
    """Grava os eventos de mensagem numa transação própria (ou na do chamador). Devolve a lista `depois`."""
    agora = agora or datetime.datetime.now(UTC)
    depois = []
    propria = not con.in_transaction
    if propria:
        con.execute("BEGIN IMMEDIATE")
    try:
        for ev in sorted((e for e in eventos if e.get("tipo_evento") == "mensagem"),
                         key=lambda e: e.get("timestamp") or 0):
            processar(con, ev, agora, depois, confiavel)
        if propria:
            con.execute("COMMIT")
    except BaseException:
        if propria and con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return depois


class Recebimento:
    """Despachante do webhook (rotas.App.despachar). `obter_conector` devolve o conector atual (ou None)."""

    def __init__(self, obter_conector):
        self.obter_conector = obter_conector

    def __call__(self, con, instancia, corpo, segredo_ok):
        configurada = banco.ler_config(con, "instancia")
        if configurada and configurada != instancia:
            banco.registrar_evento(con, "webhook_outra_instancia")
            return None
        conector = self.obter_conector()
        eventos = conector.traduzir_evento(corpo) if conector is not None else evolution.traduzir(corpo)
        depois = gravar(con, eventos, confiavel=bool(segredo_ok))
        return lambda c: executar_depois(c, conector, depois)

    def recuperar(self, con, agora=None):
        """Subida: busca no conector o que chegou desde a janela guardada e grava como se fosse webhook. A janela
        some na MESMA transação da gravação, só depois de a busca dar certo. Sem conector ou sem instância levanta
        RecuperacaoPendente (a janela fica). Devolve quantas mensagens vieram."""
        valor = banco.ler_config(con, JANELA)
        desde = _ler_momento(valor)
        if desde is None:
            return 0
        conector, instancia = self.obter_conector(), banco.ler_config(con, "instancia")
        if conector is None:
            raise RecuperacaoPendente("sem_conector")
        if not instancia:
            raise RecuperacaoPendente("sem_instancia")
        agora = agora or datetime.datetime.now(UTC)
        eventos = conector.mensagens_desde(instancia, desde - FOLGA_SUBIDA, agora)
        con.execute("BEGIN IMMEDIATE")
        try:
            depois = gravar(con, eventos, agora)
            con.execute("DELETE FROM config WHERE chave = ? AND valor = ?", (JANELA, valor))
            con.execute("COMMIT")
        except BaseException:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise
        executar_depois(con, conector, depois)
        return len(eventos)


class RecuperacaoPendente(Exception):
    """Ainda não dá para buscar o que chegou com o serviço parado (motivo: sem_conector ou sem_instancia)."""


def guardar_janela(con):
    """Subida, ANTES do 1º batimento: guarda o início do que falta buscar, só se ainda não houver um (uma subida que
    não buscou não pode empurrar a janela para frente)."""
    if banco.ler_config(con, JANELA):
        return
    desde = ultima_vida(con)
    if desde is not None:
        banco.gravar_config(con, JANELA, _iso(desde))


def ultima_vida(con):
    """Último sinal de vida do serviço antes desta subida: batimento que ficou (queda) ou parado_em (saída limpa)."""
    linha = con.execute("SELECT em FROM batimento WHERE id = 1").fetchone()
    return _ler_momento(linha["em"] if linha else banco.ler_config(con, "parado_em"))


def _ler_momento(valor):
    try:
        momento = datetime.datetime.fromisoformat(valor) if valor else None
    except ValueError:
        return None
    return momento.replace(tzinfo=UTC) if momento and momento.tzinfo is None else momento
