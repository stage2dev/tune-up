"""Leitura dos arquivos de plano (GOAL/PROGRESS/DEPOIS) e casamento de Parte com branch, PR e sessão.

Funções puras sobre texto: não leem disco nem rodam comando. O leitor.py reexporta tudo.
Python 3.9, só biblioteca padrão.
"""
import re

NOMES_PADRAO = {
    "goal": "GOAL.md",
    "progress": "PROGRESS.md",
    "later": "DEPOIS.md",
    "need_you": "PRECISO DE VOCÊ:",
    "part_closed": "Parte {X} fechada",
    "open_questions": "OPEN QUESTIONS",
}
# Variação antiga do marcador com o nome da pessoa ("PRECISO DO <NOME>:"), vista em fases reais.
RE_PRECISO_DE_ALGUEM = re.compile(r"PRECISO D[OA] [A-ZÀ-Ý]{2,30}:")

RE_CODIGO = re.compile(r"`[^`]*`|\"[^\"\n]*\"|“[^”\n]*”")


def sem_citacao(linha):
    """Tira trechos em `código` e "aspas": lá o marcador é exemplo, não fato."""
    return RE_CODIGO.sub(" ", linha)


def limpar_celula(c):
    return c.strip().strip("*`_ ").strip()


def _celulas(linha):
    s = linha.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [x.strip() for x in re.split(r"(?<!\\)\|", s)]


def tabelas(texto):
    """Tabelas markdown: lista de (linha_inicial, cabecalho, linhas_do_corpo)."""
    out, bloco, inicio = [], [], 0
    for i, linha in enumerate(texto.splitlines() + [""]):
        if linha.lstrip().startswith("|"):
            if not bloco:
                inicio = i + 1
            bloco.append(linha.strip())
            continue
        if len(bloco) >= 2:
            celulas = [_celulas(x) for x in bloco]
            corpo = [c for c in celulas[1:]
                     if not all(re.fullmatch(r":?-{2,}:?", x) for x in c if x)]
            out.append((inicio, celulas[0], corpo))
        bloco = []
    return out


def secoes(texto):
    """Lista de (titulo, numero_da_linha_do_titulo, [(numero, linha), ...])."""
    out, atual = [], ("", 0, [])
    for i, linha in enumerate(texto.splitlines(), 1):
        m = re.match(r"^(#{1,6})\s+(.*)$", linha)
        if m:
            out.append(atual)
            atual = (m.group(2).strip(), i, [])
        else:
            atual[2].append((i, linha))
    out.append(atual)
    return out


def regex_fechada(modelo):
    """'Parte {X} fechada' -> regex com grupo para o id da Parte."""
    if "{X}" not in (modelo or ""):
        modelo = NOMES_PADRAO["part_closed"]
    antes, depois = modelo.split("{X}", 1)
    return re.compile(re.escape(antes) + r"([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)" + re.escape(depois), re.I)


def achar_parte(texto, ids):
    """Id de Parte citado como 'Parte X' em `texto` (o mais longo que casar)."""
    for pid in sorted(ids, key=len, reverse=True):
        if re.search(r"\bParte\s+" + re.escape(pid) + r"(?![A-Za-z0-9-])", texto, re.I):
            return pid
    return None


def parte_do_item(item, ids):
    """'A.2' -> 'A'; 'G1.0' -> 'G1'; 'D2b' -> 'D'. Prefixo mais longo que existe."""
    for pid in sorted(ids, key=len, reverse=True):
        if item.upper().startswith(pid.upper()):
            resto = item[len(pid):]
            if not resto or not resto[0].isalpha():
                return pid
    return None


# ---------------------------------------------------------------- GOAL

RE_ID_PARTE = re.compile(r"^[A-Z0-9][A-Z0-9]{0,2}[a-z]?(?:-[A-Za-z0-9]+)*$")


def partes_do_goal(texto):
    """Partes da 1ª tabela cujo cabeçalho começa com 'Parte'. [] se não houver."""
    if not texto:
        return []
    escolhida = None
    for _inicio, cab, corpo in tabelas(texto):
        if cab and limpar_celula(cab[0]).lower() in ("parte", "partes", "part"):
            escolhida = (cab, corpo)
            break
    if not escolhida:
        return []
    cab, corpo = escolhida
    nomes_col = [limpar_celula(c).lower() for c in cab]

    def coluna(*chaves):
        for i, n in enumerate(nomes_col):
            if any(k in n for k in chaves):
                return i
        return None

    c_itens, c_pre, c_cmd = coluna("iten", "item"), coluna("pré", "pre"), coluna("comando", "command")
    out, vistos = [], set()
    for linha in corpo:
        pid = limpar_celula(linha[0]) if linha else ""
        if not pid or not RE_ID_PARTE.match(pid) or pid in vistos:
            continue
        vistos.add(pid)

        def cel(i):
            return linha[i].strip() if i is not None and i < len(linha) and linha[i].strip() else None

        out.append({"id": pid, "itens_plano": cel(c_itens), "prerequisito": cel(c_pre),
                    "comando_plano": cel(c_cmd)})
    return out


def partes_de_titulos(texto):
    """Plano B: títulos '### Parte X — ...'."""
    out = []
    for titulo, _n, _l in secoes(texto or ""):
        m = re.match(r"^Parte\s+([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\b", titulo, re.I)
        if m and m.group(1) not in [p["id"] for p in out]:
            out.append({"id": m.group(1), "itens_plano": None, "prerequisito": None, "comando_plano": None})
    return out


def titulo_goal(texto):
    for linha in (texto or "").splitlines():
        if linha.startswith("# "):
            return linha[2:].strip()
    return None


# ---------------------------------------------------------------- PROGRESS

RE_BULLET_NEGRITO = re.compile(r"^\s*[-*]\s+\*\*(.+?)\*\*")
RE_BULLET_FECHADA = re.compile(r"^\s*[-*]\s+\*\*\s*([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s+[—–-]+\s+FECHADA", re.I)
RE_ITEM = re.compile(r"^[A-Z][A-Za-z]?\d*(?:[.\-]?\d+[A-Za-z0-9]*)$")
# Contagem 'ALTO 1' / 'ALTO 2→1→0'. O lookahead evita rótulo de achado ('HIGH 1 playbook').
RE_ACHADO = re.compile(r"\b(CR[IÍ]TICO|CRITICAL|ALTO|HIGH)\b\s*:?\s*(\d+(?:\s*(?:→|->)\s*\d+)*)"
                       r"(?=\s*(?:[`,;:.)\]]|$|\(|em\s|in\s|e\s|and\s))", re.I)
# Contagem com o número antes: '2 ALTO', '1 HIGH'.
RE_ACHADO_ANTES = re.compile(r"(?<![\d/])\b(\d+)\s+(CR[IÍ]TICOS?|CRITICAL|ALTOS?|HIGH)\b", re.I)
# Achado sem número ('C1a: ALTO preço travado ...') = 1, menos 'sem CRÍTICO/ALTO', 'CRÍTICO/ALTO por volta'.
RE_ACHADO_NU = re.compile(r"(?<![/\w])(CR[IÍ]TICO|ALTO)(?![/\w])(?!\s+(?:\d|por\b|em aberto|introduzid))")
RE_SEM_ACHADO = re.compile(r"\b(?:sem|nenhum|zero|0)\s*$", re.I)
# Id de item em tabela/sub-bullet: A1a, J1a-1, B5a2, D2b, G1.0 (sempre com dígito).
RE_ITEM_LIVRE = re.compile(r"^[A-Z][A-Za-z]?\.?\d+[A-Za-z0-9]*(?:[.\-][A-Za-z0-9]+)*$")
RE_SUB_BULLET_ITEM = re.compile(r"^\s*[-*]\s+([A-Z][A-Za-z0-9.\-]*\d[A-Za-z0-9.\-]*)\s+[—–]\s+")
RE_VOLTA = re.compile(r"\bvolta\s+(\d+)", re.I)
RE_VOLTA_CURTA = re.compile(r"\bv(\d+)\b")
# Marcador citado como regra do /goal ("OR you wrote PRECISO DE VOCÊ:") não é pedido real.
RE_ANTES_MARCADOR = re.compile(r"(?:wrote|escreveu|escreva|escrever|or|ou)\s*$", re.I)
RE_PR = re.compile(r"(?:PR\s*\[?#|pull/)(\d+)", re.I)


def _nivel(palavra):
    return "critico" if palavra.upper().startswith("CR") else "alto"


def _marcar_fechada(res, pid, n, linha):
    parcial = "parcial" in linha.lower()
    citadas = res["prs_citadas"].setdefault(pid, [])
    citadas.extend(int(x) for x in RE_PR.findall(linha) if int(x) not in citadas)
    atual = res["fechadas"].get(pid)
    if atual is None:
        res["fechadas"][pid] = {"linha": n, "trecho": linha.strip()[:240], "parcial": parcial}
    elif atual["parcial"] and not parcial:  # um marcador sem "parcial" vence
        res["fechadas"][pid] = {"linha": n, "trecho": linha.strip()[:240], "parcial": False}


def _registrar_item(res, token, pid, negrito, linha, n, ler_volta=True):
    item = res["itens"].setdefault(token, {"id": token, "parte": pid, "voltas": {}, "linhas": []})
    if n not in item["linhas"]:
        item["linhas"].append(n)
    mv = ler_volta and (RE_VOLTA.search(negrito) or RE_VOLTA_CURTA.search(negrito) or RE_VOLTA.search(linha))
    volta = int(mv.group(1)) if mv else None

    def somar(v, nivel, valor):
        reg = item["voltas"].setdefault(v if v is not None else 0, {"volta": v, "critico": 0, "alto": 0})
        reg[nivel] = max(reg[nivel], valor)

    achou = False
    for a in RE_ACHADO.finditer(linha):
        achou = True
        nivel = _nivel(a.group(1))
        seq = [int(x) for x in re.findall(r"\d+", a.group(2))]
        for k, valor in enumerate(seq):
            somar((k + 1) if len(seq) > 1 else volta, nivel, valor)
    for a in RE_ACHADO_ANTES.finditer(linha):  # '2 ALTO'
        achou = True
        somar(volta, _nivel(a.group(2)), int(a.group(1)))
    if not achou:  # 'ALTO preço travado ...' sem número = 1 achado
        for a in RE_ACHADO_NU.finditer(linha):
            if not RE_SEM_ACHADO.search(linha[:a.start()]):
                somar(volta, _nivel(a.group(1)), 1)


def _tem_contagem(texto):
    """Há 'ALTO n' / 'n ALTO' com n > 0 no texto?"""
    for a in RE_ACHADO.finditer(texto):
        if any(int(x) for x in re.findall(r"\d+", a.group(2))):
            return True
    return any(int(a.group(1)) for a in RE_ACHADO_ANTES.finditer(texto))


RE_ROTULO_ITEM = re.compile(r"(?:^|(?<=[\s(]))([A-Z][A-Za-z0-9.\-]*\d[A-Za-z0-9\-]*)(?:\s+[a-z]+)?:\s")


def _itens_de_paragrafo(res, texto, ids, parte_secao, n):
    """'F2: silent-failure 2 ALTO (...). C1a: ALTO preço ...' -> um trecho por rótulo de item."""
    rotulos = [m for m in RE_ROTULO_ITEM.finditer(texto) if RE_ITEM_LIVRE.match(m.group(1).rstrip(".-"))]
    for k, m in enumerate(rotulos):
        fim = rotulos[k + 1].start() if k + 1 < len(rotulos) else len(texto)
        token = m.group(1).rstrip(".-")
        pid = parte_secao or (parte_do_item(token, ids) if ids else None)
        if ids and pid is None:
            continue
        # 'fechados na volta 2' diz quando fechou, não em que volta o achado apareceu
        _registrar_item(res, token, pid, "", texto[m.end():fim], n, ler_volta=False)


def _itens_de_tabelas(texto, res, ids, parte_por_linha):
    """Tabela com coluna 'CRÍTICO/ALTO por volta' e 1ª célula = id de item ('| A1a | ... | ALTO 1→0 |')."""
    linhas = texto.splitlines()
    for inicio, cab, _corpo in tabelas(texto):
        nomes_col = [limpar_celula(c).lower() for c in cab]
        col = next((i for i, c in enumerate(nomes_col) if re.search(r"\b(alto|high|cr[ií]tico)\b", c)), None)
        if col is None:
            continue
        for n in range(inicio + 1, len(linhas) + 1):
            linha = linhas[n - 1]
            if not linha.lstrip().startswith("|"):
                break
            cel = _celulas(linha)
            if len(cel) <= col or re.fullmatch(r":?-{2,}:?", cel[0].strip() or "--"):
                continue
            primeira = limpar_celula(cel[0]).split()
            token = primeira[0].strip("*`_:") if primeira else ""
            if not RE_ITEM_LIVRE.match(token):
                continue
            pid = parte_por_linha.get(n) or (parte_do_item(token, ids) if ids else None)
            if ids and pid is None:
                continue
            _registrar_item(res, token, pid, "", cel[col], n)


# Antes do marcador 'Parte X fechada' só vale começo de linha/título, bullet, número de lista
# ou fim de oração ('data —', '.', ':', ';', '('). 'só com a', 'depois da', 'quando', 'até' ficam fora.
RE_PREFIXO_LISTA = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*$")
RE_FIM_DE_ORACAO = re.compile(r"(?:[.:;—–(]|\s-)$")
RE_CONDICAO = re.compile(r"\b(?:com|da|de|do|a|quando|at[eé]|ap[oó]s|antes|sem|se|que)$", re.I)


def _abre_clausula(prefixo):
    p = re.sub(r"[\s*_#>~]+$", "", prefixo)
    if RE_PREFIXO_LISTA.match(p):
        return True
    if RE_CONDICAO.search(p):
        return False
    return bool(RE_FIM_DE_ORACAO.search(p))


def _tem_marcador(limpa, marcadores):
    baixo = limpa.lower()
    for mk in marcadores:
        i = baixo.find(mk)
        while i >= 0:
            if not RE_ANTES_MARCADOR.search(baixo[max(0, i - 16):i]):
                return True
            i = baixo.find(mk, i + 1)
    for m in RE_PRECISO_DE_ALGUEM.finditer(limpa):
        if not RE_ANTES_MARCADOR.search(baixo[max(0, m.start() - 16):m.start()]):
            return True
    return False


def analisar_progress(texto, ids, nomes):
    """Marcadores de Parte fechada, 'preciso de você', itens com achados e perguntas abertas."""
    res = {"fechadas": {}, "precisa": [], "itens": {}, "perguntas": [], "ids_vistos": [], "prs_citadas": {},
           "tem_alto_no_texto": False}
    if not texto:
        return res
    re_fech = regex_fechada(nomes.get("part_closed"))
    marcadores = [m.lower() for m in [nomes.get("need_you") or NOMES_PADRAO["need_you"]]]
    titulo_q = (nomes.get("open_questions") or NOMES_PADRAO["open_questions"]).lower()
    por_minusculo = {x.lower(): x for x in ids}
    parte_por_linha = {}

    for titulo, n_titulo, linhas in secoes(texto):
        parte_secao = achar_parte(titulo, ids) if ids else None
        for n, _l in linhas:
            parte_por_linha[n] = parte_secao
        eh_perguntas = titulo.lower().startswith(titulo_q) or titulo.lower().startswith("perguntas abertas")
        todas = ([(n_titulo, titulo)] if titulo else []) + linhas
        for n, linha in todas:
            limpa = sem_citacao(linha)
            # 1) Parte fechada (fora de `código` e "aspas")
            for m in re_fech.finditer(limpa):
                if not _abre_clausula(limpa[:m.start()]):
                    continue  # 'só com a Parte X fechada' é condição, não fato
                pid = m.group(1)
                if ids:
                    if pid.lower() not in por_minusculo:
                        if pid not in res["ids_vistos"]:
                            res["ids_vistos"].append(pid)
                        continue
                    pid = por_minusculo[pid.lower()]
                _marcar_fechada(res, pid, n, linha)
            m = RE_BULLET_FECHADA.match(linha)
            if m and (not ids or m.group(1) in ids):
                _marcar_fechada(res, m.group(1), n, linha)
            # 2) Preciso de você
            if _tem_marcador(limpa, marcadores):
                pid = achar_parte(limpa, ids) if ids else None
                texto_m = linha.strip()
                if n == n_titulo:  # marcador é o título: o pedido está nas linhas de baixo
                    corpo = [x.strip() for _k, x in linhas if x.strip()][:3]
                    texto_m = " · ".join([texto_m] + corpo)
                res["precisa"].append({"parte": pid or parte_secao, "linha": n, "texto": texto_m[:400]})
            # 3) Perguntas abertas
            if eh_perguntas and re.match(r"^\s*[-*]\s+\S", linha):
                baixo = linha.lower()
                if not any(k in baixo for k in ("respondid", "decidid", "~~")):
                    res["perguntas"].append({"linha": n, "texto": re.sub(r"^\s*[-*]\s+", "", linha)[:400]})
            # 4) Itens com revisão ('- **A.1** ... ALTO 1' ou '  - D2a — ... ALTO 1→0')
            mb = RE_BULLET_NEGRITO.match(linha)
            ms = None if mb else RE_SUB_BULLET_ITEM.match(linha)
            if mb:
                negrito = mb.group(1).strip()
                token = negrito.split()[0].rstrip(":") if negrito.split() else ""
                ok = RE_ITEM.match(token) and re.search(r"\d", token)
            elif ms:
                negrito, token = "", ms.group(1).rstrip(".:-")
                ok = RE_ITEM_LIVRE.match(token)
            else:
                ok = False
            if ok:
                pid = parte_secao or (parte_do_item(token, ids) if ids else None)
                if not ids or pid is not None:
                    _registrar_item(res, token, pid, negrito, linha, n)
                continue
            # 5) Parágrafo de revisão: '**Revisão:** F2: ... 2 ALTO (...). C1a: ALTO preço ...'
            if re.match(r"^\s*(?:[-*]\s+)?\*\*Revis[aã]o[^*]*\*\*", linha, re.I):
                _itens_de_paragrafo(res, limpa, ids, parte_secao, n)
    _itens_de_tabelas(texto, res, ids, parte_por_linha)
    res["tem_alto_no_texto"] = _tem_contagem(sem_citacao(texto))
    # Marcador sem Parte seguido, mais abaixo, por uma Parte fechada: a conversa andou, já foi atendido.
    ultima_fechada = max([f["linha"] for f in res["fechadas"].values()] or [0])
    res["precisa"] = [x for x in res["precisa"] if x["parte"] or x["linha"] > ultima_fechada]
    return res


def contar_depois(texto):
    """(abertos, formato). Conta '- [ ]'. Sem nenhuma caixa -> (None, 'sem_caixas')."""
    if texto is None:
        return None, "sem_arquivo"
    abertos = len(re.findall(r"^\s*[-*]\s+\[ \]", texto, re.M))
    feitos = len(re.findall(r"^\s*[-*]\s+\[[xX]\]", texto, re.M))
    if abertos == 0 and feitos == 0:
        return None, "sem_caixas"
    return abertos, "caixas"

# ---------------------------------------------------------------- casamentos

def _mesmo_numero(a, b):
    return a.lstrip("0") == str(b).lstrip("0")


def parte_da_branch(branch, numero, ids):
    """'feat/fase-187-parte-c' -> 'C'; 'feat/fase-185-a-mfa' -> 'A-mfa'; 'feat/fase-186-j2' -> 'J'."""
    m = re.search(r"fase-?(\d{2,4})[-/](.+)$", branch or "", re.I)
    if not m or not _mesmo_numero(m.group(1), numero):
        return None
    resto = m.group(2).lower()
    if resto.startswith("parte-"):
        resto = resto[6:]
    melhor = None
    for pid in ids:
        p = pid.lower()
        if resto == p or resto.startswith(p + "-") or (resto.startswith(p) and resto[len(p):len(p) + 1].isdigit()):
            if melhor is None or len(pid) > len(melhor):
                melhor = pid
    return melhor


def parte_do_titulo_pr(titulo, numero, ids):
    m = re.search(r"fase\s*(\d{2,4})\b(.*)", titulo or "", re.I)
    if not m or not _mesmo_numero(m.group(1), numero):
        return None
    return achar_parte(m.group(2), ids)


def parte_da_sessao(nome, numero, ids):
    if not nome or not re.search(r"\b0*%d\b" % int(numero), nome):
        return None
    pid = achar_parte(nome, ids)
    if pid:
        return pid
    m = re.search(r"part\s+0*%d\s+([A-Za-z0-9-]+)" % int(numero), nome, re.I)
    return m.group(1) if m and m.group(1) in ids else None
