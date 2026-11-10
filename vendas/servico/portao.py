"""Portão de envio: a ÚNICA porta para conector.enviar_*. Tabela origem x regra do plano, chave de dedupe por origem.

Cada origem tem a sua função (enviar_manual, enviar_ia, ...): a origem vem de QUAL função o serviço chama, nunca do
corpo de um pedido. Passos: reserva em BEGIN IMMEDIATE (reconfere opt-out, pausa, janela e tetos NA HORA DE ENVIAR)
-> linha 'pendente' gravada ANTES do conector -> 'enviado' (id_externo) | 'falhou' (NaoEnviado) | 'incerto'
(EnvioIncerto ou erro desconhecido). Negado grava o motivo e não ocupa a chave; chave já ocupada = 'duplicado'
(sem linha nova, sem conector). Na subida, todo 'pendente' vira 'incerto' e nada é reenviado sozinho: só
reenviar(), por ação explícita do dono, volta a MESMA linha a 'pendente'."""
import datetime
import re

from servico import banco, telefone
from servico.conectores import base

UTC = datetime.timezone.utc
TETO_MINUTO = 8
TETO_HORA = 200
TETO_TESTE_AUDIO_DIA = 5
TETO_AUDIO_DIA = 20  # padrão do "teto de áudio/dia" da IA; config teto_audio_dia troca
JANELA = (9, 19)     # campanha só das 09:00 às 18:59 no fuso do projeto (config "fuso")
ATIVOS = ("pendente", "enviado", "incerto")  # o que conta como saída do número ('falhou' não saiu)
CONTATO = object()   # marcador na chave: troca pelo id do contato dentro da reserva

# optout: confirmar | nega | livre | exige. teto: minuto, hora, audio_dia, novos_dia, teste_dia
REGRAS = {
    "manual": {"optout": "confirmar", "pausa": False, "janela": False, "teto": ("minuto",)},
    "rascunho_aprovado": {"optout": "nega", "pausa": False, "janela": False, "teto": ("minuto",)},
    "ia": {"optout": "nega", "pausa": True, "janela": False, "teto": ("minuto", "hora")},
    "campanha": {"optout": "nega", "pausa": True, "janela": True, "teto": ("minuto", "hora", "novos_dia")},
    "audio_ia": {"optout": "nega", "pausa": True, "janela": False, "teto": ("minuto", "hora", "audio_dia")},
    "teste_audio": {"optout": "livre", "pausa": False, "janela": False, "teto": ("teste_dia",)},
    # 1 por contato: a chave "confirmacao_sair:<contato>" é única
    "confirmacao_sair": {"optout": "exige", "pausa": False, "janela": False, "teto": ()},
}
ORIGENS = tuple(REGRAS)
AUDIO = ("audio_ia", "teste_audio")


def teto_contatos_novos(con, dia):
    """Gancho do teto de contatos NOVOS por dia da campanha (a curva entra num item seguinte). None = sem teto."""
    return None


def _iso(momento):
    return momento.astimezone(UTC).isoformat(timespec="seconds")


def _agora(agora):
    return agora if agora is not None else datetime.datetime.now(UTC)


def fuso(con):
    """Fuso do projeto (config "fuso": "-03:00" ou nome IANA). Sem config = fuso da máquina; inválido = None."""
    valor = (banco.ler_config(con, "fuso") or "").strip()
    if not valor:
        return datetime.datetime.now().astimezone().tzinfo
    achado = re.match(r"^([+-])(\d{2}):?(\d{2})$", valor)
    if achado:
        horas, minutos = int(achado.group(2)), int(achado.group(3))
        if horas > 14 or minutos > 59:
            return None
        sinal = -1 if achado.group(1) == "-" else 1
        return datetime.timezone(sinal * datetime.timedelta(hours=horas, minutes=minutos))
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(valor)
    except (ImportError, ValueError, KeyError):  # ZoneInfoNotFoundError é KeyError (Windows sem tzdata cai aqui)
        return None


def _contar(con, desde, extra="", args=(), ignorar=None):
    marcas = ",".join("?" * len(ATIVOS))
    sql = "SELECT COUNT(*) FROM envios WHERE estado IN (%s) AND tentado_em > ? AND id <> ? %s" % (marcas, extra)
    return con.execute(sql, ATIVOS + (desde, ignorar or 0) + tuple(args)).fetchone()[0]


def contatos_novos_no_dia(con, inicio_dia):
    """Contador diário: contatos cujo PRIMEIRO envio ativo foi a partir de inicio_dia (iso UTC)."""
    marcas = ",".join("?" * len(ATIVOS))
    return con.execute("SELECT COUNT(*) FROM (SELECT MIN(tentado_em) AS primeiro FROM envios WHERE estado IN (%s) "
                       "AND contato_id IS NOT NULL GROUP BY contato_id) WHERE primeiro >= ?" % marcas,
                       ATIVOS + (inicio_dia,)).fetchone()[0]


def _pausada(con, contato_id, agora):
    conversa = con.execute("SELECT modo, pausada_ate FROM conversas WHERE contato_id = ?", (contato_id,)).fetchone()
    if conversa is None:
        return False
    if conversa["modo"] == "humano":
        return True
    if not conversa["pausada_ate"]:
        return False
    try:
        ate = datetime.datetime.fromisoformat(conversa["pausada_ate"])
    except ValueError:
        return True  # data ilegível: fecha
    if ate.tzinfo is None:
        ate = ate.replace(tzinfo=UTC)
    return ate > agora


def _motivo_teto(con, origem, contato_id, agora, inicio_dia, ignorar):
    teto = REGRAS[origem]["teto"]
    if "minuto" in teto and _contar(con, _iso(agora - datetime.timedelta(minutes=1)), ignorar=ignorar) >= TETO_MINUTO:
        return "teto_minuto"
    if "hora" in teto and _contar(con, _iso(agora - datetime.timedelta(hours=1)), ignorar=ignorar) >= TETO_HORA:
        return "teto_hora"
    if "teste_dia" in teto and _contar(con, inicio_dia, "AND origem = ?", ("teste_audio",),
                                       ignorar) >= TETO_TESTE_AUDIO_DIA:
        return "teto_teste_audio_dia"
    if "audio_dia" in teto:
        limite = int(banco.ler_config(con, "teto_audio_dia", str(TETO_AUDIO_DIA)))
        if _contar(con, inicio_dia, "AND origem = ?", ("audio_ia",), ignorar) >= limite:
            return "teto_audio_dia"
    if "novos_dia" in teto:
        limite = teto_contatos_novos(con, inicio_dia)
        ja = con.execute("SELECT 1 FROM envios WHERE contato_id = ? AND id <> ? AND estado IN (%s)"
                         % ",".join("?" * len(ATIVOS)), (contato_id, ignorar or 0) + ATIVOS).fetchone()
        if limite is not None and ja is None and contatos_novos_no_dia(con, inicio_dia) >= limite:
            return "teto_contatos_novos_dia"
    return None


def _motivo(con, origem, numero, contato_id, confirmar_optout, agora, ignorar=None):
    """Motivo da negação pela linha da tabela da origem, ou None. Lê o banco AGORA (dentro da reserva)."""
    regra = REGRAS[origem]
    if origem == "teste_audio":
        dono = banco.ler_config(con, "numero_dono")
        if not dono:
            return "sem_numero_do_dono"
        try:
            if numero not in telefone.variantes(dono):
                return "nao_e_o_dono"
        except telefone.TelefoneInvalido:
            return "sem_numero_do_dono"
    saiu = contato_id is not None and con.execute(
        "SELECT optout_em FROM contatos WHERE id = ?", (contato_id,)).fetchone()["optout_em"] is not None
    if regra["optout"] == "nega" and saiu:
        return "optout"
    if regra["optout"] == "confirmar" and saiu and confirmar_optout is not True:
        return "optout_pede_confirmacao"
    if regra["optout"] == "exige" and not saiu:
        return "sem_optout"
    if regra["pausa"] and _pausada(con, contato_id, agora):
        return "pausa_humana"
    tz = fuso(con) if (regra["janela"] or {"teste_dia", "audio_dia", "novos_dia"} & set(regra["teto"])) else UTC
    if tz is None:
        return "fuso_invalido"
    local = agora.astimezone(tz)
    if regra["janela"] and not JANELA[0] <= local.hour < JANELA[1]:
        return "fora_da_janela"
    inicio_dia = _iso(local.replace(hour=0, minute=0, second=0, microsecond=0))
    return _motivo_teto(con, origem, contato_id, agora, inicio_dia, ignorar)


def _contato_de(con, origem, numero):
    if origem == "teste_audio":
        return None  # o dono não vira contato
    return banco.salvar_contato(con, numero)


def pode_enviar(con, origem, numero, confirmar_optout=False, agora=None):
    """(True, None) ou (False, motivo) pela tabela, sem gravar nada. A decisão que vale é a da reserva."""
    if origem not in REGRAS:
        raise ValueError("origem desconhecida: %r" % origem)
    canonico = telefone.normalizar(numero)
    contato = banco.buscar_contato(con, canonico) if origem != "teste_audio" else None
    motivo = _motivo(con, origem, canonico, contato["id"] if contato else None, confirmar_optout, _agora(agora))
    return motivo is None, motivo


def _resultado(estado, envio_id=None, motivo=None, id_externo=None):
    return {"estado": estado, "envio_id": envio_id, "motivo": motivo, "id_externo": id_externo}


def _reservar(con, origem, numero, tipo, conteudo, partes, confirmar_optout, agora):
    if con.in_transaction:
        raise RuntimeError("o portão precisa de uma conexão fora de transação")
    canonico = telefone.normalizar(numero)
    con.execute("BEGIN IMMEDIATE")
    try:
        contato_id = _contato_de(con, origem, canonico)
        chave = ":".join([origem] + [str(contato_id) if p is CONTATO else str(p) for p in partes])
        ocupada = con.execute("SELECT id FROM envios WHERE chave_dedupe = ? AND estado <> 'negado'",
                              (chave,)).fetchone()
        if ocupada is not None:
            con.execute("COMMIT")
            return _resultado("duplicado", ocupada["id"], "chave_ocupada"), None
        motivo = _motivo(con, origem, canonico, contato_id, confirmar_optout, agora)
        estado = "negado" if motivo else "pendente"
        envio_id = banco.registrar_envio(con, chave, origem, estado=estado, motivo=motivo, contato_id=contato_id,
                                         telefone=canonico, tipo=tipo, conteudo=conteudo, quando=_iso(agora))
        if envio_id is None:  # não acontece sob BEGIN IMMEDIATE; se acontecer, não envia
            raise banco.EscritaSemEfeito("chave %s ocupada dentro da reserva" % origem)
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    if motivo:
        return _resultado("negado", envio_id, motivo), None
    return None, (envio_id, canonico)


def _fechar(con, envio_id, estado, motivo=None, id_externo=None):
    cur = con.execute("UPDATE envios SET estado = ?, motivo = ?, id_externo = COALESCE(?, id_externo) "
                      "WHERE id = ? AND estado = 'pendente'", (estado, motivo, id_externo, envio_id))
    if cur.rowcount != 1:
        raise banco.EscritaSemEfeito("envio %d não estava pendente ao fechar" % envio_id)
    return _resultado(estado, envio_id, motivo, id_externo)


def _entregar(con, conector, instancia, envio_id, tipo, numero, conteudo):
    """Chama o conector FORA da transação (a linha 'pendente' já está gravada) e fecha a linha."""
    try:
        if tipo == "audio":
            ident = conector.enviar_audio(instancia, numero, conteudo)
        else:
            ident = conector.enviar_texto(instancia, numero, conteudo)
    except base.NaoEnviado as e:
        return _fechar(con, envio_id, "falhou", "nao_enviado" + (":%s" % e.status if e.status else ""))
    except base.EnvioIncerto as e:
        return _fechar(con, envio_id, "incerto", "incerto" + (":%s" % e.status if e.status else ""))
    except Exception as e:  # desconhecido depois de chamar o conector: pode ter saído
        return _fechar(con, envio_id, "incerto", "erro_inesperado:%s" % type(e).__name__)
    if not ident:
        return _fechar(con, envio_id, "incerto", "sem_id_externo")
    return _fechar(con, envio_id, "enviado", None, str(ident))


def _enviar(con, conector, instancia, origem, numero, conteudo, partes, confirmar_optout=False, agora=None):
    if conector is None or not instancia:
        raise ValueError("portão sem conector ou instância")
    if not isinstance(conteudo, str) or not conteudo:
        raise ValueError("conteúdo vazio")
    tipo = "audio" if origem in AUDIO else "texto"
    pronto, reserva = _reservar(con, origem, numero, tipo, conteudo, partes, confirmar_optout, _agora(agora))
    if pronto is not None:
        return pronto
    envio_id, canonico = reserva
    return _entregar(con, conector, instancia, envio_id, tipo, canonico, conteudo)


def enviar_manual(con, conector, instancia, numero, texto, id_tela, confirmar_optout=False, agora=None):
    """Dono digitou. Chave = id gerado na tela (um por clique). Opt-out só passa com confirmar_optout=True."""
    return _enviar(con, conector, instancia, "manual", numero, texto, [id_tela], confirmar_optout, agora)


def enviar_rascunho_aprovado(con, conector, instancia, numero, texto, id_rascunho, agora=None):
    return _enviar(con, conector, instancia, "rascunho_aprovado", numero, texto, [id_rascunho], agora=agora)


def enviar_ia(con, conector, instancia, numero, texto, conversa_id, id_gatilho, balao, agora=None):
    """Chave = conversa + id_externo da mensagem gatilho + nº do balão."""
    return _enviar(con, conector, instancia, "ia", numero, texto, [conversa_id, id_gatilho, balao], agora=agora)


def enviar_campanha(con, conector, instancia, numero, texto, campanha_id, passo, agora=None):
    """Chave = campanha + contato + passo."""
    return _enviar(con, conector, instancia, "campanha", numero, texto, [campanha_id, CONTATO, passo], agora=agora)


def enviar_audio_ia(con, conector, instancia, numero, caminho_ogg, conversa_id, id_gatilho, balao, agora=None):
    """Chave = a da IA com sufixo de áudio."""
    return _enviar(con, conector, instancia, "audio_ia", numero, caminho_ogg,
                   [conversa_id, id_gatilho, balao, "audio"], agora=agora)


def enviar_teste_audio(con, conector, instancia, numero, caminho_ogg, id_tela, agora=None):
    """Só para o número do dono (config numero_dono); outro número = negado."""
    return _enviar(con, conector, instancia, "teste_audio", numero, caminho_ogg, [id_tela], agora=agora)


def enviar_confirmacao_sair(con, conector, instancia, numero, texto, agora=None):
    """A única mensagem depois do opt-out; uma por contato."""
    return _enviar(con, conector, instancia, "confirmacao_sair", numero, texto, [CONTATO], agora=agora)


def reenviar(con, conector, instancia, envio_id, confirmar_optout=False, agora=None):
    """Ação explícita do dono: a MESMA linha 'incerto'/'falhou' volta a 'pendente' (sem chave nova) e sai de novo,
    depois de reconferir a regra da origem. Negado aqui não muda a linha."""
    if conector is None or not instancia:
        raise ValueError("portão sem conector ou instância")
    if con.in_transaction:
        raise RuntimeError("o portão precisa de uma conexão fora de transação")
    momento = _agora(agora)
    con.execute("BEGIN IMMEDIATE")
    try:
        linha = con.execute("SELECT * FROM envios WHERE id = ?", (envio_id,)).fetchone()
        if linha is None:
            raise LookupError("envio %r não existe" % envio_id)
        if linha["estado"] not in ("incerto", "falhou") or not linha["conteudo"] or not linha["telefone"]:
            con.execute("COMMIT")
            return _resultado(linha["estado"], envio_id, "nao_reenviavel")
        motivo = _motivo(con, linha["origem"], linha["telefone"], linha["contato_id"], confirmar_optout, momento,
                         ignorar=envio_id)
        if motivo is None:
            cur = con.execute("UPDATE envios SET estado = 'pendente', motivo = NULL, tentado_em = ? WHERE id = ? "
                              "AND estado IN ('incerto', 'falhou')", (_iso(momento), envio_id))
            banco._exigir(cur)
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    if motivo:
        return _resultado("negado", envio_id, motivo)
    return _entregar(con, conector, instancia, envio_id, linha["tipo"], linha["telefone"], linha["conteudo"])


def pendentes_para_incerto(con):
    """Subida do serviço: todo 'pendente' (processo caiu no meio) vira 'incerto'. Nada é reenviado."""
    return con.execute("UPDATE envios SET estado = 'incerto', motivo = 'pendente_na_subida' "
                       "WHERE estado = 'pendente'").rowcount
