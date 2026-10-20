"""tune-up: intenção do prompt (pesquisa, autorização, segredos, regra nova) e evento prompt."""
import re
from bisect import bisect_left
from .mensagens import msg
from .sessao import contexto, gravar_sessao, ler_sessao, log_erro

# ---------------------------------------------------------------- texto

def normalizar(texto):
    import unicodedata
    t = unicodedata.normalize("NFKD", texto.lower().replace("\u2019", "'").replace("\u2018", "'"))
    return "".join(c for c in t if not unicodedata.combining(c))


RE_COLADO = re.compile(r"<pasted_content\b[^>]*>.*?(</pasted_content>|\Z)", re.S | re.I)
RE_CERCA = re.compile(r"```.*?(```|\Z)", re.S)


def fala_do_dono(prompt):
    t = RE_COLADO.sub(" ", prompt)
    t = RE_CERCA.sub(" ", t)
    t = "\n".join(l for l in t.splitlines() if not l.lstrip().startswith(">"))
    return normalizar(t)


RE_AUTH_VERBO = re.compile(r"\b(pode|roda|rode|rodar|aplica|aplique|aplicar|manda|mande|mandar|"
                           r"sobe|suba|subir|faz|faca|fazer|"
                           r"apply|run)\b")
RE_AUTH_NAO_E_OBJETO = re.compile(r"plano|pesquisa|review|revis|analis|estud|doc")
RE_AUTH_OBJETO = re.compile(r"\b(prod|producao|production|migrations?|migracao|migracoes|banco|database|"
                            r"deploy\w*|edge|sql de escrita|write sql|update|insert|delete)\b")
RE_AUTH_LEITURA = re.compile(r"\b(leitura|select|consulta|so ler|testes?|read[ -]only|tests)\b")
NEGACOES = {"nao", "nunca", "sem", "nem", "jamais", "not", "never", "without",
            "dont", "doesnt", "didnt", "wont", "cant", "shouldnt", "wouldnt", "couldnt",
            "nothing", "except", "exceto"}
RE_NEGACAO = re.compile(r"(?<![\w'])(%s)(?![\w'])|\b(no need to|nada de|pare de)\b" % "|".join(sorted(NEGACOES)))
RE_TN_ABRE = re.compile(r"<task-notification", re.I)
RE_TASK_NOTIF = re.compile(r"<task-notification\b[^>]*>.*?(</task-notification>|\Z)", re.S | re.I)
RE_ROTULO = re.compile(r"^\s*[\wÀ-ú]+:\s")
# linha que cita outra pessoa/sistema: "the customer wrote: ...", "Customer says - ...", "o log diz: ..."
RE_CITACAO = re.compile(r"^[^\n]{0,80}?\b(wrote|writes|said|says|disse|diz|escreveu|falou|fala)\s*[:\-\u2013\u2014]", re.I)
RE_COLADO_TEXTO = re.compile(r"\[pasted text\b[^\]]*\]", re.I)
# linha terminando em "X wrote:" derruba o bloco seguinte até a linha em branco
RE_CITA_BLOCO = re.compile(r"\b(wrote|said|disse|escreveu):\s*$", re.I)
RE_CONTRACAO = re.compile(r"\b(\w{1,40})n't\b")
# aspa simples: apóstrofo só entre letras (don't); as 3+ palavras são contadas em `sem_aspas`
RE_ASPAS = re.compile(r"\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d"
                      r"|(?<!\w)'(?=[^'\s])(?:[^'\s]|(?<=\w)'(?=\w)|\s(?=\s|[^'\s]))+'(?!\w)")
RE_FIM_ORACAO = re.compile(r"[.!;:](?=\s|$)|\?|\n")
RE_PERGUNTA = re.compile(r"\W*((please|ok|okay|so|and|but|hey|then|e|entao|mas)\W+)*"
                         r"(can|could|would|should|will|shall|may|did|do you|does|is|are|why|who|what|how|"
                         r"when|where|por que|pq|quem|sera que)\b")
# en: só imperativo autoriza (início de oração ou depois de please / you can / go ahead and)
RE_IMPERATIVO_EN = re.compile(r"\W*((please|ok|okay|now|then|just|so|and|you can|go ahead and)\W+)*$")
RE_DESTINO_NEGADO = re.compile(r"\b(not|nao|never|nunca|nem|jamais|without|sem|except|exceto)\b(\W+\w+){0,2}?\W+(prod|producao|production)\b")


def palavras(t):
    return re.findall(r"[\w']+", t)


def negado(t):
    return bool(RE_NEGACAO.search(RE_CONTRACAO.sub(r"\1nt", t)))


def sem_aspas(t):
    return RE_ASPAS.sub(lambda m: " " if m.group(0)[0] != "'" or len(m.group(0).split()) >= 3 else m.group(0), t)


def voz_para_auth(prompt):
    """Voz que AFROUXA: sem linhas `Fulano: ...`/`X wrote:` (e o bloco depois de `wrote:`).
    Com <task-notification> em qualquer ponto, vazia: nada afrouxa (A3)."""
    if RE_TN_ABRE.search(prompt):
        return ""
    linhas, pula = [], False
    for l in RE_COLADO_TEXTO.sub(" ", prompt).splitlines():
        pula = pula and bool(l.strip())
        if not (pula or RE_ROTULO.match(l) or RE_CITACAO.match(l) or RE_CITA_BLOCO.search(l)):
            linhas.append(l)
        pula = pula or bool(RE_CITA_BLOCO.search(l))
    return fala_do_dono("\n".join(linhas))


def voz_interruptor(prompt):
    """Voz que desliga pesquisa/conversa e abre aprender: `voz_para_auth` sem trechos entre aspas."""
    return sem_aspas(RE_CONTRACAO.sub(r"\1nt", voz_para_auth(prompt)))


def voz_restricao(prompt):
    """Voz que só RESTRINGE (liga pesquisa/conversa): fala do dono com rótulo, citação e aspas (M3)."""
    return RE_CONTRACAO.sub(r"\1nt", fala_do_dono(RE_COLADO_TEXTO.sub(" ", RE_TASK_NOTIF.sub(" ", prompt))))


def trecho_auth(voz):
    """Trecho verbo→objeto de prod que autoriza, ou None."""
    voz = sem_aspas(RE_CONTRACAO.sub(r"\1nt", voz))
    if RE_AUTH_LEITURA.search(voz):
        return None
    fins = [x.start() for x in RE_FIM_ORACAO.finditer(voz)]  # fronteiras uma vez; todas têm 1 caractere
    oracao = {}  # ini -> (fim da 1ª negação, destino negado): uma busca por oração
    for m in RE_AUTH_VERBO.finditer(voz):
        i = bisect_left(fins, m.start())
        ini = m.start() if voz[m.start() - 1:m.start()] in (".", "!", ";", ":") else (fins[i - 1] + 1 if i else 0)
        j = bisect_left(fins, m.end())
        fim = fins[j] if j < len(fins) else len(voz)
        if ini not in oracao:
            n = RE_NEGACAO.search(voz, ini, fim)
            oracao[ini] = (n.end() if n else fim + 1, bool(RE_DESTINO_NEGADO.search(voz, ini, fim)))
        if oracao[ini][0] <= m.start() or voz[fim:fim + 1] == "?" or RE_PERGUNTA.match(voz, ini, m.start()):
            continue
        if m.group(1) in ("apply", "run") and not RE_IMPERATIVO_EN.match(voz, ini, m.start()):
            continue
        o = RE_AUTH_OBJETO.search(voz, m.end(), min(m.end() + 41, fim))
        if not o:
            continue
        meio = voz[m.end():o.start()]
        if negado(meio) or negado(" ".join(palavras(voz[max(0, o.start() - 200):o.start()])[-2:])):
            continue
        if RE_AUTH_NAO_E_OBJETO.search(meio) or oracao[ini][1]:
            continue
        return voz[m.start():o.end()]
    return None
PESQ_LIGA = [
    r"\b(nao|sem) (altere|alterar|mexa|mexer|modifique|modificar|edite|editar|mude|mudar) (nada|em nada)\b",
    r"\bsem alterar\b",
    r"\b(so|apenas|somente) (research|pesquisa|leitura|analise|estudo|diagnostico)\b",
    r"\bpor enquanto (e )?(so |apenas )?(research|pesquisa|analise)\b",
    r"\bainda nao (aplique|altere|mexa|faca|implemente)\b",
    r"\bestude primeiro\b",
    r"\bnao (aplique|implemente) ainda\b",
    r"\b(do not|don'?t) (change|edit|modify|touch) anything\b",
    r"\b(research|read|analysis) only\b", r"\bonly (research|reading|analysis)\b",
    r"\bwithout changing anything\b", r"\bstudy (it )?first\b",
    r"\b(do not|don'?t) (apply|implement) (it |this |anything )?yet\b",
]
# formas fortes: ligam mesmo com verbo de ação no prompt
PESQ_FORTE = [
    r"\b(sem|nao) (alterar|altere|mexer|mexa|mexe) (em )?nada(?=[ \t]*([^\w\s]|\n|$)|\s+ainda\b)",
    r"\bso (pesquisa|research)\b",
    r"\bestude primeiro\b",
    r"\b(do not|don'?t) (change|edit|modify|touch) anything(?=[ \t]*([^\w\s]|\n|$)|\s+yet\b)",
    r"\bresearch only\b",
]
# generic en + pt-BR; personal slang goes in `research_off_phrases` of a trusted config
PESQ_DESLIGA = [
    r"\bpode (fazer|aplicar|seguir|tocar|executar|implementar|mexer|alterar|comecar|ir)\b",
    r"\baprovad[oa]s?\b", r"\bliberad[oa]\b",
    r"\bgo ahead\b", r"\byou (can|may) (start|apply|proceed|implement|change)\b", r"\bapproved\b",
]
# talk mode: strong phrases only ("vamos conversar sobre" does not turn it on)
TALK_COMANDO = r"tune-up:talk\b"
TALK_LIGA = [TALK_COMANDO, r"\bmodo conversa\b", r"\btalk mode\b"]
TALK_DESLIGA = [
    r"\bdesliga(r)? o modo conversa\b", r"\b(turn off|disable) talk mode\b", r"\bpode construir\b", r"\bcomece a aplicar\b", r"\bsair do modo conversa\b",
    r"\bacabou o modo conversa\b", r"\b(parou|paramos) de conversar\b",
    r"\blet'?s build\b", r"\bstart building\b", r"\bend talk\b", r"\b(exit|leave) talk mode\b",
]
SEGREDOS = [r"(?<![A-Za-z0-9])" + p for p in (
    r"sk-[A-Za-z0-9_-]{20,}", r"sk-ant-[A-Za-z0-9_-]{20,}", r"ghp_[A-Za-z0-9]{30,}",
    r"github_pat_[A-Za-z0-9_]{30,}", r"AKIA[0-9A-Z]{16}",
    r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.", r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"AIza[0-9A-Za-z_-]{35}",
    r"(sk_live_|rk_live_|sk_test_)[A-Za-z0-9]{10,}", r"APP_USR-[A-Za-z0-9-]{10,}",
    r"sbp_[A-Za-z0-9]{20,}", r"sb_secret_[A-Za-z0-9_-]{10,}", r"EAA[A-Za-z0-9]{30,}",
    r"GOCSPX-[A-Za-z0-9_-]{10,}", r"postgres(ql)?://[^:\s]+:[^@\s]+@",
)]
RE_NAO_MEXE_OBJETO = re.compile(
    r"\b(sem alterar|nao mexa|nao mexe)\s+(o|a|os|as|no|na|nos|nas|do|da|dos|das|em)\s+(?!nada\b)\w+")
RE_VERBO_ACAO = re.compile(
    r"(?<!\bnao )(?<!\bsem )\b(corri[gj]|consert|implement|arrum|fa[cz]a?|cri[ae]|escrev|ajust|aplic|mude|troqu)")
RE_VERBO_ACAO_EN = re.compile(
    r"(?<!\bnot )(?<!\bdon't )(?<!\bdont )(?<!\bwithout )\b(fix(es|ed|ing)?|implement\w*|chang(e|es|ed|ing)|writ(e|es|ing)|"
    r"creat(e|es|ed|ing)|appl(y|ies|ied|ying)|patch(es|ed|ing)?)\b")


def pedido_de_conserto(voz):
    """Prompt pede mudança — então "sem alterar X" é restrição, não modo pesquisa."""
    return bool(RE_NAO_MEXE_OBJETO.search(voz) or RE_VERBO_ACAO.search(voz) or RE_VERBO_ACAO_EN.search(voz))


REGRA_NOVA = [
    r"\b(guarde|grave|salve|coloque) na memoria\b", r"\ba partir de agora\b",
    r"\bregra (nova|permanente)\b", r"\bnunca mais\b", r"\bsempre (faca|faz|fazer|use|usar)\b",
    r"\bfrom now on\b", r"\b(new|permanent) rule\b", r"\bnever again\b",
    r"\b(save|put|keep) (it |this )?(in|to) (the )?memory\b",
]


# desbloqueio da autoproteção: só comando no início do prompt ou "regra nova/permanente" afirmada
RE_APRENDER_CMD = re.compile(r"\s*/tune-up:(learn|profile|setup)\b", re.I)
APRENDER_FRASES = [r"(?<!\bthe )(?<!\bthis )(?<!\bthat )(?<!\ba )(?<!\bessa )(?<!\besta )"
                   r"\b(regra (nova|permanente)|(new|permanent) rule)\b"]


RE_TAG = re.compile(r"\b(ta|ok|okay|ne|certo|beleza|right)\W*$")  # "..., ta?" não é pergunta


def casa_frase(padroes, voz, pergunta_cancela=False):
    """Frase de interruptor que vale: sem negação nas 3 palavras antes (e, se pedido, fora de pergunta)."""
    for p in padroes:
        for m in re.finditer(p, voz):
            if negado(" ".join(palavras(voz[:m.start()])[-3:])):
                continue
            f = RE_FIM_ORACAO.search(voz, m.end())
            if pergunta_cancela and f and f.group(0) == "?" and not RE_TAG.search(voz, m.end(), f.start()):
                continue
            return True
    return False


def casa_algum(padroes, texto):
    for p in padroes:
        try:
            if re.search(p, texto):
                return True
        except re.error as e:
            log_erro("prompt", "invalid regex in phrases %r: %s" % (p, e))
            if normalizar(p) in texto:
                return True
    return False


def normalizar_regex(p):
    """Como `normalizar`, mas não mexe na letra depois de `\\` (\\S, \\B, \\W continuam)."""
    import unicodedata
    out, i = [], 0
    while i < len(p):
        c = p[i]
        if c == "\\" and i + 1 < len(p):
            out.append(p[i:i + 2])
            i += 2
            continue
        out.append(normalizar(c))
        i += 1
    return "".join(out)


def frases_cfg(cfg, chave):
    return [normalizar_regex(str(x)) for x in (cfg.get(chave) or []) if isinstance(x, str)]


def estado_talk(voz_i, voz_r=None):
    """(desliga, liga) do modo conversa: desliga pela voz que afrouxa, liga pela que restringe."""
    off = casa_frase(TALK_DESLIGA, voz_i)
    return off, not off and casa_frase(TALK_LIGA, voz_i if voz_r is None else voz_r, pergunta_cancela=True)


def aprender(prompt, voz_i):
    if RE_TN_ABRE.search(prompt):
        return False
    return bool(RE_APRENDER_CMD.match(prompt)) or casa_frase(APRENDER_FRASES, voz_i, pergunta_cancela=True)


# ---------------------------------------------------------------- prompt / inicio

def ev_prompt(d, cfg):
    prompt = d.get("prompt") or ""
    if not isinstance(prompt, str):
        return None
    sid = d.get("session_id")
    pid = d.get("prompt_id")
    voz = fala_do_dono(prompt)
    voz_i = voz_interruptor(prompt)
    voz_r = voz_restricao(prompt)
    estado = ler_sessao(sid)
    linhas = []
    mudou = False

    voz_auth = voz_para_auth(prompt)
    trecho = trecho_auth(voz_auth)
    if trecho is None and voz_auth:
        for p in frases_cfg(cfg, "auth_phrases"):
            if casa_algum([p], voz_auth):
                trecho = p
                break
    auth = trecho is not None
    liga = casa_algum(PESQ_FORTE, voz_r) or (
        casa_algum(PESQ_LIGA + frases_cfg(cfg, "research_on_phrases"), voz_r) and not pedido_de_conserto(voz_r))
    desliga = bool(voz_i) and casa_algum(PESQ_DESLIGA + frases_cfg(cfg, "research_off_phrases"), voz_i)

    if auth:
        estado["auth_prompt_id"] = pid
        mudou = True
    antes = bool(estado.get("modo_pesquisa"))
    if liga:
        estado["modo_pesquisa"] = True
        mudou = True
        if not antes:
            linhas.append(msg("pesquisa_liga"))
    elif desliga and antes:
        estado["modo_pesquisa"] = False
        mudou = True
        linhas.append(msg("pesquisa_desliga"))
    talk_off, talk_on = estado_talk(voz_i, voz_r)
    if talk_on:
        if not estado.get("modo_conversa"):
            linhas.append(msg("talk_liga"))
        estado["modo_conversa"] = True
        mudou = True
    elif talk_off and estado.get("modo_conversa"):
        estado["modo_conversa"] = False
        mudou = True
        linhas.append(msg("talk_desliga"))
    if auth:
        linhas.append(msg("auth_detectada", trecho))
    if any(re.search(p, prompt) for p in SEGREDOS):
        linhas.append(msg("segredo"))
    if aprender(prompt, voz_i):
        estado["aprender_prompt_id"] = pid
        mudou = True
    if casa_algum(REGRA_NOVA, voz):
        linhas.append(msg("regra_nova"))

    if mudou:
        try:
            gravar_sessao(sid, estado)
        except Exception as e:
            log_erro("prompt", "gravar_sessao failed: %r" % (e,))
    return contexto("UserPromptSubmit", linhas) if linhas else None
