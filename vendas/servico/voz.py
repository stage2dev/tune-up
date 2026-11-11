"""Voz (nota de voz do WhatsApp) com a conta ElevenLabs DO USUÁRIO: chave num arquivo 0600 da pasta de dados (como a
da OpenAI; nenhuma rota a devolve, só 'configurada' + 4 últimos), voice_id e modelo na config.
Sem ffmpeg, sem chave ou sem voice_id = voz DESLIGADA com aviso; o resto do serviço segue.
Voz padrão = voz de CATÁLOGO da conta. Voz marcada 'clonada' só liga com o consentimento gravado do dono da voz (nome,
data, texto) para AQUELE voice_id, e todo áudio dela começa com AVISO_IA falado (sem chave para tirar).
Ordem de um envio: texto (limite por áudio) -> prontidão -> portão.pode_enviar (sem gastar) -> reserva de caracteres
do dia em BEGIN IMMEDIATE (teto antes de chamar) -> ElevenLabs -> ffmpeg (temporários 0600 na pasta de dados, sempre
apagados) -> portão (origem audio_ia ou teste_audio; teste_audio só para o número do dono)."""
import hashlib
import re
import threading
import time

from servico import banco, chave, portao, telefone, voz_cliente

ARQUIVO_CHAVE = "elevenlabs_chave"
AVISO_IA = "Mensagem de voz gerada por IA."
MODELO_PADRAO = "eleven_multilingual_v2"
FORMATO_PADRAO = "mp3_44100_128"
TETO_PADRAO = 5000      # caracteres por dia (config voz_teto_caracteres_dia)
TETO_MAX = 1000000
CACHE_VOZES_S = 600   # lista de vozes da conta fica 10 min em memória (por chave), só se a ElevenLabs respondeu
LIMITE_TEXTO = 600      # caracteres por áudio (sem contar o aviso)
TEXTO_TESTE = "Olá! Este é um teste da voz do seu atendimento."
ROTA = re.compile(r"^/voz(?:/(vozes|chave|chave/apagar|config|consentimento|teste))?$")


_cache_trava = threading.Lock()


def vozes(app, segredo):
    """Lista de vozes da conta: do cache (10 min, mesma chave) ou de UMA consulta. ErroVoz sobe."""
    marca = hashlib.sha256(segredo.encode("utf-8")).hexdigest()
    with _cache_trava:
        cache = getattr(app, "cache_vozes", None)
        if cache and cache[0] == marca and time.monotonic() - cache[1] < CACHE_VOZES_S:
            return list(cache[2])
    lista = voz_cliente.listar_vozes(getattr(app, "elevenlabs_url", voz_cliente.URL_PADRAO), segredo)
    with _cache_trava:
        app.cache_vozes = (marca, time.monotonic(), list(lista))
    return lista


def _dia():
    return banco.agora()[:10]


def teto(con):
    valor = banco.ler_config(con, "voz_teto_caracteres_dia")
    return int(valor) if valor and valor.isdigit() else TETO_PADRAO


def usados_hoje(con):
    linha = con.execute("SELECT caracteres FROM voz_uso WHERE dia = ?", (_dia(),)).fetchone()
    return linha["caracteres"] if linha else 0


def reservar(con, n):
    """Soma n caracteres ao dia se cabe no teto, em BEGIN IMMEDIATE. (dia, n) para devolver(); None = não cabe."""
    dia = _dia()
    con.execute("BEGIN IMMEDIATE")
    try:
        if usados_hoje(con) + n > teto(con):
            con.execute("COMMIT")
            return None
        banco._exigir(con.execute("INSERT INTO voz_uso (dia, caracteres) VALUES (?, ?) ON CONFLICT(dia) DO UPDATE "
                                  "SET caracteres = caracteres + excluded.caracteres", (dia, n)))
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return dia, n


def devolver(con, reserva):
    """A ElevenLabs respondeu com erro (nada gerado): tira a reserva do dia dela."""
    dia, n = reserva
    con.execute("UPDATE voz_uso SET caracteres = MAX(caracteres - ?, 0) WHERE dia = ?", (n, dia))


def consentimento(con, voz_id):
    if not voz_id:
        return None
    linha = con.execute("SELECT nome, data, texto, criado_em FROM voz_consentimentos WHERE voz_id = ? "
                        "ORDER BY id DESC LIMIT 1", (voz_id,)).fetchone()
    return dict(linha) if linha else None


def _config(con):
    return {"voz_id": banco.ler_config(con, "voz_id"), "clonada": banco.ler_config(con, "voz_clonada") == "1",
            "modelo": banco.ler_config(con, "voz_modelo") or MODELO_PADRAO,
            "formato": banco.ler_config(con, "voz_formato") or FORMATO_PADRAO}


def avisos(app, con, cfg=None):
    """Por que a voz está desligada (lista vazia = ligada)."""
    cfg = cfg or _config(con)
    saida = []
    if not voz_cliente.achar_ffmpeg():
        saida.append("Voz desligada: instale o ffmpeg (ele converte o áudio em nota de voz do WhatsApp).")
    if not chave.ler(app.pasta_dados, ARQUIVO_CHAVE):
        saida.append("Voz desligada: cole a chave da sua conta ElevenLabs.")
    if not cfg["voz_id"]:
        saida.append("Voz desligada: escolha o voice_id de uma voz da sua conta ElevenLabs.")
    elif cfg["clonada"] and consentimento(con, cfg["voz_id"]) is None:
        saida.append("Voz clonada desligada: grave o consentimento do dono da voz (nome, data e texto).")
    return saida


def estado(app, con):
    cfg = _config(con)
    cons = consentimento(con, cfg["voz_id"])
    lista = avisos(app, con, cfg)
    return {"ligada": not lista, "avisos": lista, "chave": chave.estado(app.pasta_dados, ARQUIVO_CHAVE),
            "ffmpeg": voz_cliente.achar_ffmpeg() is not None, "voz_id": cfg["voz_id"], "clonada": cfg["clonada"],
            "aviso_ia": AVISO_IA if cfg["clonada"] else None, "modelo": cfg["modelo"], "formato": cfg["formato"],
            "consentimento": None if cons is None else {"nome": cons["nome"], "data": cons["data"]},
            "dono_configurado": bool(banco.ler_config(con, "numero_dono")),
            "teto_caracteres_dia": teto(con), "usados_hoje": usados_hoje(con), "limite_texto": LIMITE_TEXTO}


def _gerar_e_enviar(app, con, origem, numero, texto, mandar):
    """Resultado do portão ({estado: enviado|falhou|incerto|negado|duplicado, ...}) ou {estado: desligada|teto|erro,
    erro, avisos?}. Nunca leva a chave, o texto falado nem o caminho do arquivo."""
    texto = texto.strip() if isinstance(texto, str) else ""
    if not texto or len(texto) > LIMITE_TEXTO:
        return {"estado": "erro", "erro": "O texto do áudio tem de ter de 1 a %d caracteres." % LIMITE_TEXTO}
    cfg = _config(con)
    lista = avisos(app, con, cfg)
    if lista:
        return {"estado": "desligada", "erro": lista[0], "avisos": lista}
    instancia = banco.ler_config(con, "instancia")
    if getattr(app, "conector", None) is None or not instancia:
        return {"estado": "desligada", "erro": "Conecte o WhatsApp antes de enviar áudio."}
    try:
        ok, motivo = portao.pode_enviar(con, origem, numero, instancia=instancia)
    except telefone.TelefoneInvalido:
        ok, motivo = False, "numero_invalido"
    if not ok:
        return {"estado": "negado", "motivo": motivo}
    falado = (AVISO_IA + " " + texto) if cfg["clonada"] else texto
    reserva = reservar(con, len(falado))
    if reserva is None:
        return {"estado": "teto", "erro": "O teto de voz de hoje (%d caracteres) acabou. Nada foi enviado." % teto(con)}
    entrada = saida = None
    try:
        audio = voz_cliente.sintetizar(getattr(app, "elevenlabs_url", voz_cliente.URL_PADRAO),
                                       chave.ler(app.pasta_dados, ARQUIVO_CHAVE), cfg["voz_id"], cfg["modelo"],
                                       cfg["formato"], falado)
        entrada = voz_cliente.arquivo_temporario(app.pasta_dados, ".entrada")
        with open(entrada, "wb") as f:
            f.write(audio)
        saida = voz_cliente.arquivo_temporario(app.pasta_dados, ".ogg")
        voz_cliente.converter(voz_cliente.achar_ffmpeg() or "ffmpeg", entrada, saida)
        voz_cliente.apagar(entrada)
        entrada = None
        return mandar(app.conector, instancia, saida)
    except voz_cliente.ErroVoz as e:
        if e.sem_cobranca:
            devolver(con, reserva)
        return {"estado": "erro", "erro": e.mensagem, "codigo": e.codigo}
    finally:
        voz_cliente.apagar(entrada, saida)


def enviar_teste(app, con, id_tela, texto=TEXTO_TESTE, numero=None):
    """Teste de áudio: vai SÓ para o número do dono (config numero_dono). A rota nunca passa `numero`; outro número
    é negado pelo portão (origem teste_audio)."""
    numero = numero or banco.ler_config(con, "numero_dono")
    if not numero:
        return {"estado": "negado", "motivo": "sem_numero_do_dono"}
    return _gerar_e_enviar(app, con, "teste_audio", numero, texto, lambda conector, inst, ogg: portao.enviar_teste_audio(
        con, conector, inst, numero, ogg, id_tela))


def enviar_audio_ia(app, con, numero, texto, conversa_id, id_gatilho, balao):
    """Áudio da IA (origem audio_ia): opt-out, pausa e tetos do portão valem."""
    return _gerar_e_enviar(app, con, "audio_ia", numero, texto, lambda conector, inst, ogg: portao.enviar_audio_ia(
        con, conector, inst, numero, ogg, conversa_id, id_gatilho, balao))


def _texto(valor, limite):
    return re.sub(r"[\x00-\x1f\x7f]", " ", valor).strip()[:limite] if isinstance(valor, str) else ""


def _salvar_config(con, corpo):
    voz_id = _texto(corpo.get("voz_id"), 64)
    modelo = _texto(corpo.get("modelo"), 64) or MODELO_PADRAO
    formato = _texto(corpo.get("formato"), 64) or FORMATO_PADRAO
    teto_dia = corpo.get("teto_caracteres_dia", teto(con))
    teto_dia = teto_dia.strip() if isinstance(teto_dia, str) else teto_dia
    if not voz_cliente.FORMATO_ID.match(voz_id):
        return 400, {"erro": "voice_id inválido (8 a 64 letras e números)."}
    if not voz_cliente.FORMATO_NOME.match(modelo) or not voz_cliente.FORMATO_NOME.match(formato):
        return 400, {"erro": "Modelo ou formato inválido."}
    if isinstance(teto_dia, bool) or not (isinstance(teto_dia, int) or (isinstance(teto_dia, str) and teto_dia.isdigit())) \
            or not 0 <= int(teto_dia) <= TETO_MAX:
        return 400, {"erro": "Teto diário inválido (de 0 a %d caracteres)." % TETO_MAX}
    if not isinstance(corpo.get("clonada", False), bool):
        return 400, {"erro": "Marque se a voz é clonada (sim ou não)."}
    dono = _texto(corpo.get("numero_dono"), 40)   # opcional: vazio mantém o que já está gravado
    if dono:
        try:
            dono = telefone.normalizar(dono)
        except telefone.TelefoneInvalido:
            return 400, {"erro": "Número do dono inválido (DDD + número, só dígitos)."}
    con.execute("BEGIN IMMEDIATE")
    try:
        if dono:
            banco.gravar_config(con, "numero_dono", dono)
        banco.gravar_config(con, "voz_id", voz_id)
        banco.gravar_config(con, "voz_clonada", "1" if corpo.get("clonada") else "0")
        banco.gravar_config(con, "voz_modelo", modelo)
        banco.gravar_config(con, "voz_formato", formato)
        banco.gravar_config(con, "voz_teto_caracteres_dia", str(int(teto_dia)))
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return 200, {"voz_id": voz_id, "clonada": bool(corpo.get("clonada")), "modelo": modelo, "formato": formato,
                 "teto_caracteres_dia": int(teto_dia), "dono_configurado": bool(banco.ler_config(con, "numero_dono"))}


def _gravar_consentimento(con, corpo):
    """Consentimento do dono da voz para o voice_id da config: nome, data (AAAA-MM-DD) e o texto que ele aceitou."""
    voz_id = banco.ler_config(con, "voz_id")
    nome, data, texto = _texto(corpo.get("nome"), 120), _texto(corpo.get("data"), 10), _texto(corpo.get("texto"), 2000)
    if not voz_id:
        return 409, {"erro": "Escolha a voz antes de gravar o consentimento."}
    if not nome or not re.match(r"^\d{4}-\d{2}-\d{2}$", data) or len(texto) < 20:
        return 400, {"erro": "Informe o nome do dono da voz, a data (AAAA-MM-DD) e o texto do consentimento."}
    banco._exigir(con.execute("INSERT INTO voz_consentimentos (voz_id, nome, data, texto, criado_em) VALUES "
                              "(?, ?, ?, ?, ?)", (voz_id, nome, data, texto, banco.agora())))
    return 200, {"consentimento": {"nome": nome, "data": data}}


def _codigo(r):
    return {"enviado": 200, "duplicado": 200, "teto": 429, "erro": 502, "incerto": 502, "falhou": 502}.get(
        r["estado"], 409)


def executar(app, con, metodo, caminho, query, corpo):
    """(código, objeto) de uma rota /voz; None = rota desconhecida."""
    achou = ROTA.match(caminho)
    if not achou:
        return None
    sub = achou.group(1)
    if metodo == "GET":
        if sub is None:
            return 200, estado(app, con)
        if sub != "vozes":
            return None
        segredo = chave.ler(app.pasta_dados, ARQUIVO_CHAVE)
        if not segredo:
            return 409, {"erro": "Cole a chave da ElevenLabs primeiro."}
        try:
            return 200, {"vozes": vozes(app, segredo)}
        except voz_cliente.ErroVoz as e:
            return 502, {"erro": e.mensagem, "codigo": e.codigo}
    if metodo != "POST" or corpo is None or sub is None:
        return None
    if sub == "chave":
        try:
            chave.gravar(app.pasta_dados, corpo.get("chave"), ARQUIVO_CHAVE)
        except chave.ChaveInvalida as e:
            return 400, {"erro": str(e)}
        return 200, {"chave": chave.estado(app.pasta_dados, ARQUIVO_CHAVE)}
    if sub == "chave/apagar":
        if corpo.get("confirmar") is not True:
            return 400, {"erro": "Confirme para apagar a chave."}
        return 200, {"apagada": chave.apagar(app.pasta_dados, ARQUIVO_CHAVE),
                     "chave": chave.estado(app.pasta_dados, ARQUIVO_CHAVE)}
    if sub == "config":
        return _salvar_config(con, corpo)
    if sub == "consentimento":
        return _gravar_consentimento(con, corpo)
    id_tela = corpo.get("id_tela")
    if not isinstance(id_tela, str) or not re.match(r"^[A-Za-z0-9_-]{8,64}$", id_tela):
        return 400, {"erro": "Pedido sem id_tela válido."}
    texto = corpo.get("texto") if isinstance(corpo.get("texto"), str) and corpo["texto"].strip() else TEXTO_TESTE
    r = enviar_teste(app, con, id_tela, texto)
    return _codigo(r), {k: r.get(k) for k in ("estado", "motivo", "erro", "avisos") if r.get(k) is not None}
