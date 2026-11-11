"""Saída da IA: fica entre o cérebro e o portão. Nada que a IA escreveu sai sem passar por aqui.

1. Segredo: a chave colada na tela ou algo com cara de token (sk-..., Bearer ..., sequência longa) = nada sai.
2. Ferramenta como texto (JSON, `nome({...})`, bloco de código, marca de papel, texto do sistema) = UMA reescrita
   pelo modelo (sem ferramentas); se ainda falhar, nada sai.
3. Links: só os do links.json do projeto (host+caminho normalizados; sai a URL da lista, nunca a do texto, então
   parâmetro de redirecionamento cai). Domínio sem esquema (golpe.com/pix) também é link. Lista vazia = nenhum link.
   Depois do filtro, uma varredura larga (Unicode, sem olhar o que vem antes; IP com caminho) falha fechado: sobrou
   algo com cara de domínio fora da lista (ação.com.br, ...golpe.com, -golpe.com, homógrafo) = nada sai.
4. No máximo 4 frases e 4096 caracteres (corte em fim de frase); link da lista cortado volta no fim.
5. Anti-loop: a 3ª resposta seguida quase igual às 2 anteriores = nada sai.
6. Até 3 balões, cada um pelo portão (origem 'ia', chave conversa + gatilho + nº do balão), com "digitando" antes
   quando o conector suporta (falha da presença não impede o envio). Balão negado = os seguintes não saem e a
   conversa fica "precisa de você" com os balões que faltaram no evento (ia_envio_negado se foi o 1º,
   ia_envio_parcial se não), salvo opt-out (o lead saiu) e pausa_humana (o dono já está na conversa).
Nada sai (1, 2, 3, texto vazio, 5) = a conversa fica "precisa de você" (como o pedir_humano do cérebro)."""
import difflib
import json
import re
import unicodedata
from urllib.parse import urlsplit

from servico import banco, cerebro, portao

FRASES_MAX = 4
CARACTERES_MAX = 4096
BALOES_MAX = 3
DIGITANDO_MS = 1200
PARECIDA = 0.85
ATIVOS = ("pendente", "enviado", "incerto")
PEDIDO_REESCRITA = ("Reescreva o rascunho como mensagem curta de WhatsApp para o cliente: só texto corrido, sem JSON, "
                    "sem código, sem nome de ferramenta, sem marcas de papel.")

URL = re.compile(r"(?:https?://|www\.)[^\s<>\"'()\[\]{}]+"
                 r"|(?<![@\w.-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}(?![\w@-])"   # domínio sem esquema
                 r"(?::\d+)?(?:/[^\s<>\"'()\[\]{}]*)?", re.I)
FERRAMENTA = re.compile(
    r"\b[A-Za-z_][A-Za-z0-9_.]*\s*\(\s*[{\[]"                        # nome({...}) / nome([...])
    r"|\b(guardar_dado_do_lead|qualificar|enviar_link|pedir_humano)\s*\("
    r"|```|\"(name|arguments|tool_calls|function|role|content)\"\s*:"
    r"|\{\s*\"[^\"\n]{1,40}\"\s*:"                                   # objeto JSON
    r"|(^|\n)\s*(system|assistant|developer|user|tool|sistema|usu[aá]rio)\s*:"
    r"|<\|[^|>]*\|?>|\[/?inst\]|</?\s*(dados_do_cliente|tool_call|function_call)\b|\bfunctions\.\w+", re.I)
SISTEMA_VAZADO = (cerebro.SISTEMA[:60].lower(), "dados_do_cliente")
TOKEN = re.compile(r"\bsk-[A-Za-z0-9_-]{12,}|\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"
                   r"|(?<![A-Za-z0-9])(?=[A-Za-z0-9_+/=-]*\d)(?=[A-Za-z0-9_+/=-]*[A-Za-z])[A-Za-z0-9_+/=-]{32,}", re.I)
FIM_DE_FRASE = re.compile(r"(?<=[.!?…])\s+")
EMAIL = re.compile(r"(?<![^\s(<\"'])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w/@-]|\.\w)")
LARGO = re.compile(r"(?<![\w-])[\w-]+(?:\.[\w-]+)*\.[^\W\d_]{2,}(?::\d+)?(?:[/?#][^\s<>\"'()\[\]{}]*)?"
                   r"|\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?[/?#:][^\s<>\"'()\[\]{}]*")
NAO_CHAMA_O_DONO = ("optout", "pausa_humana")   # balão negado por isso não chama o dono


def _normalizar_url(url):
    """(host sem www/porta padrão, caminho sem / final) ou None se não for http(s) com host."""
    if "://" not in url:
        url = "https://" + url
    try:
        partes = urlsplit(url)
        porta = partes.port
    except ValueError:
        return None
    host = (partes.hostname or "").lower().rstrip(".")
    if partes.scheme.lower() not in ("http", "https") or not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    if porta not in (None, 80, 443):
        host = "%s:%d" % (host, porta)
    return host, partes.path.rstrip("/") or ""


def filtrar_links(texto, permitidos):
    """URL da lista vira a URL da lista (como está no links.json); fora da lista é removida. (texto, removidas)."""
    mapa = {}
    for u in permitidos or ():
        n = _normalizar_url(u)
        if n is not None:
            mapa.setdefault(n, u)
    removidas = []

    def trocar(m):
        bruto = m.group(0).rstrip(".,;:!?…")
        resto = m.group(0)[len(bruto):]
        certa = mapa.get(_normalizar_url(bruto))
        if certa is None:
            removidas.append(bruto)
            return resto
        return certa + resto
    novo = URL.sub(trocar, texto)
    return re.sub(r"[ \t]{2,}", " ", novo).strip(), removidas


def sobras_de_link(texto, permitidos):
    """Varredura larga depois de filtrar_links: o que ainda tem cara de domínio (ou IP com caminho) e não é da lista.
    E-mail inteiro (ana@loja.com, sem caminho) não conta."""
    lista = {_normalizar_url(u) for u in permitidos or ()} - {None}
    sobras = []
    for m in LARGO.finditer(EMAIL.sub(" ", texto)):
        bruto = m.group(0).rstrip(".,;:!?…")
        if _normalizar_url(bruto) not in lista:
            sobras.append(bruto)
    return sobras


def tem_segredo(texto, segredos=()):
    if any(s and s in texto for s in segredos):
        return True
    return bool(TOKEN.search(URL.sub(" ", texto)))


def ferramenta_como_texto(texto):
    baixo = texto.lower()
    return bool(FERRAMENTA.search(texto)) or any(s in baixo for s in SISTEMA_VAZADO)


def limitar(texto, frases=FRASES_MAX, caracteres=CARACTERES_MAX):
    """No máximo `frases` frases e `caracteres` caracteres, cortando em fim de frase (ou de palavra, se uma frase
    sozinha passa do limite)."""
    pedacos = FIM_DE_FRASE.split(texto.strip())
    texto = " ".join(pedacos[:frases]) if len(pedacos) > frases else texto.strip()
    if len(texto) <= caracteres:
        return texto
    corte = texto[:caracteres]
    fins = [m.end() for m in re.finditer(r"[.!?…](?=\s|$)", corte)]
    if fins:
        return corte[:fins[-1]].strip()
    espaco = corte.rfind(" ")
    return (corte[:espaco] if espaco > 0 else corte).strip()


def _limitar_mantendo_links(texto):
    """limitar(), mas os links (já filtrados: todos da lista) que o corte tirou voltam no fim, fora da conta de
    frases e dentro dos 4096 caracteres."""
    links = list(dict.fromkeys(m.group(0).rstrip(".,;:!?…") for m in URL.finditer(texto)))
    cortado = limitar(texto)
    faltam = [u for u in links if u not in cortado]
    if not faltam:
        return cortado
    cortado = limitar(texto, caracteres=CARACTERES_MAX - len("\n".join(faltam)) - 1)
    faltam = [u for u in links if u not in cortado]
    return "\n".join([cortado] + faltam).strip()


def baloes(texto, maximo=BALOES_MAX):
    """Uma linha não vazia por balão; o que passa de `maximo` vai junto no último."""
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    if len(linhas) <= maximo:
        return linhas
    return linhas[:maximo - 1] + ["\n".join(linhas[maximo - 1:])]


def _plano(texto):
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", sem_acento).split())


def parecidas(a, b, limite=PARECIDA):
    a, b = _plano(a), _plano(b)
    return bool(a) and bool(b) and difflib.SequenceMatcher(None, a, b).ratio() >= limite


def _prefixo(conversa_id):
    return "ia:%s:" % conversa_id


def respostas_anteriores(con, conversa_id, id_gatilho, quantas=2):
    """Textos (balões juntos) das últimas `quantas` respostas da IA na conversa, sem a do gatilho atual."""
    prefixo = _prefixo(conversa_id)
    linhas = con.execute("SELECT chave_dedupe, conteudo FROM envios WHERE origem = 'ia' AND substr(chave_dedupe, 1, ?) "
                         "= ? AND estado IN (?, ?, ?) ORDER BY id", (len(prefixo), prefixo) + ATIVOS).fetchall()
    respostas = {}
    for l in linhas:
        gatilho = l["chave_dedupe"][len(prefixo):].rsplit(":", 1)[0]
        if gatilho != str(id_gatilho):
            respostas.setdefault(gatilho, []).append(l["conteudo"] or "")
            respostas[gatilho] = respostas.pop(gatilho)   # a mais recente vai para o fim
    return ["\n".join(t) for t in list(respostas.values())[-quantas:]]


def _ja_respondido(con, conversa_id, id_gatilho):
    prefixo = "%s%s:" % (_prefixo(conversa_id), id_gatilho)
    return con.execute("SELECT 1 FROM envios WHERE substr(chave_dedupe, 1, ?) = ? AND estado <> 'negado'",
                       (len(prefixo), prefixo)).fetchone() is not None


def _barrar(con, conversa_id, motivo, extra=None, desligar=False):
    cerebro.marcar_precisa_de_voce(con, conversa_id, motivo, desligar)
    dados = {"conversa_id": conversa_id, "motivo": motivo}
    dados.update(extra or {})
    banco.registrar_evento(con, "ia_saida_barrada", json.dumps(dados, ensure_ascii=False))
    return {"estado": "barrado", "motivo": motivo, "baloes": []}


def preparar(texto, permitidos, segredos=(), reescrever=None):
    """(texto pronto, None) ou (None, motivo). Nada aqui envia nem grava."""
    texto = (texto or "").strip()
    if tem_segredo(texto, segredos):
        return None, "segredo"   # sem reescrita: o rascunho não volta ao modelo
    if ferramenta_como_texto(texto):
        texto = (reescrever(texto, PEDIDO_REESCRITA) if reescrever else None) or ""
        if not texto or ferramenta_como_texto(texto):
            return None, "ferramenta_como_texto"
        if tem_segredo(texto, segredos):
            return None, "segredo"
    texto, _ = filtrar_links(texto, permitidos)
    texto = _limitar_mantendo_links(texto)
    if sobras_de_link(texto, permitidos):
        return None, "link_suspeito"   # falha fechado: o filtro deixou passar algo com cara de link
    return (texto, None) if texto else (None, "vazio")


def entregar(con, conector, instancia, numero, conversa_id, id_gatilho, texto, permitidos=(), segredos=(),
             reescrever=None, agora=None):
    """Prepara, confere o anti-loop e manda os balões pelo portão. Devolve {estado, motivo, baloes: [resultados]}.
    estado: 'barrado' (nada saiu, precisa de você), 'duplicado' (o gatilho já foi respondido), ou o do último
    balão tentado ('enviado' quando todos saíram)."""
    if _ja_respondido(con, conversa_id, id_gatilho):
        return {"estado": "duplicado", "motivo": "gatilho_ja_respondido", "baloes": []}
    pronto, motivo = preparar(texto, permitidos, segredos, reescrever)
    if pronto is None:
        return _barrar(con, conversa_id, motivo)
    anteriores = respostas_anteriores(con, conversa_id, id_gatilho)
    if len(anteriores) == 2 and all(parecidas(pronto, a) for a in anteriores):
        return _barrar(con, conversa_id, "anti_loop", desligar=True)   # 3 parecidas: IA sai até o dono devolver
    resultados, lista = [], baloes(pronto)
    for n, balao in enumerate(lista, 1):
        if portao.pode_enviar(con, "ia", numero, agora=agora)[0]:
            try:
                conector.digitando(instancia, numero, DIGITANDO_MS)
            except Exception:
                pass   # presença é enfeite: nunca impede o envio
        r = portao.enviar_ia(con, conector, instancia, numero, balao, conversa_id, id_gatilho, n, agora=agora)
        resultados.append(r)
        if r["estado"] != "enviado":
            if r["motivo"] not in NAO_CHAMA_O_DONO:   # resposta perdida ou cortada no meio: o dono responde/completa
                tipo = "ia_envio_parcial" if n > 1 else "ia_envio_negado"
                cerebro.marcar_precisa_de_voce(con, conversa_id, tipo[len("ia_"):])
                banco.registrar_evento(con, tipo, json.dumps(
                    {"conversa_id": conversa_id, "estado": r["estado"], "motivo": r["motivo"],
                     "faltaram": lista[n - 1:]}, ensure_ascii=False))
            break
    return {"estado": resultados[-1]["estado"], "motivo": resultados[-1]["motivo"], "baloes": resultados}
