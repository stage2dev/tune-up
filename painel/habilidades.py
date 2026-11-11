"""Skills que o dono pode escolher no chat do painel (GET /api/habilidades).

Fontes: plugins instalados (<installPath>/skills/*/SKILL.md, nome "plugin:skill"; desligado em
enabledPlugins = fora da lista do Claude), skills do usuário (~/.claude/skills), do projeto
(<raiz>/.claude/skills e <repo>/.claude/skills) e pastas extras do painel.json (fora da lista).
Cada SKILL.md é lido como dado não confiável: só arquivo comum, sem bloquear, até 8 KB,
frontmatter lido à mão. Grupos por tema em habilidades.json (núcleo) e <pacote>/habilidades.json.
A escolha vira um bloco no FIM do pedido; quem monta é o servidor. Python 3.9, só biblioteca padrão.
"""
import hashlib
import json
import os
import re
import stat
import threading
import time

import config
import mascara
from catalogo import ErroAcao

NUCLEO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "habilidades.json")
RE_NOME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,80}$")
RE_ID = re.compile(r"^[0-9a-f]{12}$")
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f]")
LER_MAX = 8 * 1024
TETO = 3000
MAX_ESCOLHA = 6
DESCRICAO_MAX = 300
TTL = 60
INICIO = "[skills escolhidas pelo dono no painel]"
FIM = "[fim das skills]"
FECHO = ("Use estas skills neste pedido, junto com o fluxo do tune-up, que vale sempre. "
         "Não carregue outras skills sem necessidade.")
RE_LINHA = re.compile(r"^- ([A-Za-z0-9][A-Za-z0-9:._-]{0,80})(?:: use a ferramenta Skill| \(fora da lista\): leia )")
PUBLICOS = ("id", "nome", "titulo", "descricao", "grupo", "origem", "listada", "fixa")

_trava = threading.Lock()
_cache = {}


def ler_skill(caminho):
    """(nome do frontmatter ou None, descrição) de um SKILL.md; None se não for arquivo comum legível."""
    if RE_CONTROLE.search(caminho):
        return None
    try:
        fd = os.open(caminho, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
                     | getattr(os, "O_NOFOLLOW", 0))  # SKILL.md atalho: pula; pasta atalho continua valendo
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):  # FIFO, pasta, aparelho: pula sem ler
            return None
        bruto = os.read(fd, LER_MAX)
    except OSError:
        return None
    finally:
        os.close(fd)
    campos = frontmatter(bruto.decode("utf-8", errors="replace"))
    return campos.get("name"), campos.get("description") or ""


def frontmatter(texto):
    """{chave: valor} do bloco --- ... --- no começo. Aceita valor em uma linha, entre aspas,
    em bloco dobrado (">") ou literal ("|") e continuação recuada. Bloco sem fim = sem campos."""
    linhas = texto.lstrip("﻿").replace("\r\n", "\n").split("\n")
    if not linhas or linhas[0].strip() != "---":
        return {}
    try:
        fim = next(i for i, ln in enumerate(linhas[1:], 1) if ln.strip() in ("---", "..."))
    except StopIteration:
        return {}
    campos, chave, modo, partes = {}, None, "", []

    def fechar():
        if chave is not None:
            junta = "\n".join(partes) if modo == "|" else " ".join(partes)
            campos[chave] = junta.strip()

    for ln in linhas[1:fim]:
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", ln)
        if m and not ln[:1].isspace():
            fechar()
            chave, valor = m.group(1), m.group(2).strip()
            modo = valor[:1] if valor[:1] in ">|" and len(valor) <= 2 else ""
            if not modo and len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
                valor = valor[1:-1]
            partes = [] if modo else [valor]
        elif chave is not None and (ln[:1].isspace() or not ln.strip()):
            partes.append(ln.strip())
    fechar()
    return campos


def _ler_json(caminho, avisos, rotulo):
    """Objeto JSON de um arquivo comum (sem bloquear, até 256 KB). Ausente: {} sem aviso."""
    try:
        fd = os.open(caminho, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
    except FileNotFoundError:
        return {}
    except OSError as e:
        avisos.append("%s ilegível (%s); ignorei" % (rotulo, type(e).__name__))
        return {}
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("não é arquivo comum")
        dado = json.loads(os.read(fd, 256 * 1024).decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        avisos.append("%s ilegível (%s); ignorei" % (rotulo, type(e).__name__))
        return {}
    finally:
        os.close(fd)
    if not isinstance(dado, dict):
        avisos.append("%s não é um objeto; ignorei" % rotulo)
        return {}
    return dado


def _ligados(cfg, home, avisos):
    """(enabledPlugins de usuário, projeto e local da raiz, onde a sessão roda (o último vence);
    False se um settings existe e não abre)."""
    arquivos = [os.path.join(home, ".claude", "settings.json")]
    if cfg.get("raiz"):
        arquivos += [os.path.join(cfg["raiz"], ".claude", n) for n in ("settings.json", "settings.local.json")]
    ligados, ok = {}, True
    for arq in arquivos:
        erros = []
        mapa = _ler_json(arq, erros, "").get("enabledPlugins")
        ok = ok and not erros
        if isinstance(mapa, dict):
            ligados.update({k: v for k, v in mapa.items() if isinstance(v, bool)})
    if not ok:
        avisos.append("não consegui ler um settings do Claude; as skills de plugin vão pelo caminho do arquivo")
    return ligados, ok


def _mesma(a, b):
    return bool(a and b) and os.path.realpath(a) == os.path.realpath(b)


def _fontes(cfg, home, avisos):
    """[(pasta skills, origem, listada, plugin ou None)] na ordem de prioridade. `listada` só para
    fonte que a sessão (aberta na raiz) carrega de verdade."""
    (ligados, ok), vistos, fontes = _ligados(cfg, home, avisos), {}, []
    instalados = config._instalacoes(home)
    if instalados is None and os.path.lexists(os.path.join(home, ".claude", "plugins", "installed_plugins.json")):
        avisos.append("não consegui ler a lista de plugins; as skills de plugin ficaram de fora")
    for chave, e in instalados or []:  # várias entradas: vale a mais recente
        atual = vistos.get(chave)
        if atual is None or config._quando(e) >= config._quando(atual):
            vistos[chave] = e
    for chave in sorted(vistos):
        plugin = str(chave).split("@", 1)[0]
        pasta = os.path.join(os.path.expanduser(vistos[chave]["installPath"]), "skills")
        fixo = plugin == "tune-up" or plugin.startswith("tune-up-")
        fontes.append((pasta, plugin, (ok or fixo) and ligados.get(chave, True) is not False, plugin))
    fontes.append((os.path.join(home, ".claude", "skills"), "Suas skills", True, None))
    for base in dict.fromkeys(b for b in (cfg.get("raiz"), cfg.get("repo")) if b):
        fontes.append((os.path.join(base, ".claude", "skills"), "Projeto", _mesma(base, cfg.get("raiz")), None))
    for extra in cfg.get("habilidades_pastas") or []:
        fontes.append((extra["pasta"], extra["titulo"], False, None))
    return fontes


def _regra(r, ids):
    if not isinstance(r, dict) or r.get("grupo") not in ids or not isinstance(r.get("regex"), str) \
            or len(r["regex"]) > 500:
        return None
    try:
        return r["grupo"], re.compile(r["regex"], re.I)
    except re.error:
        return None


def _regras(cfg, avisos):
    """(grupos [{id, titulo}], regras [(grupo, regex)], mapa plugin->grupo). Pacote antes do núcleo."""
    nucleo = _ler_json(NUCLEO, avisos, "habilidades.json do núcleo")
    grupos = [g for g in nucleo.get("grupos") or [] if isinstance(g, dict)
              and isinstance(g.get("id"), str) and isinstance(g.get("titulo"), str)]
    ids = {g["id"] for g in grupos}
    regras, mapa, fontes = [], {}, []
    if cfg.get("pacote_ok") and cfg.get("pacote_dir"):
        rotulo = "habilidades.json do pacote"
        fontes.append((rotulo, _ler_json(os.path.join(cfg["pacote_dir"], "habilidades.json"), avisos, rotulo)))
    fontes.append(("habilidades.json do núcleo", nucleo))
    for rotulo, dado in fontes:
        lista = dado.get("regras", [])
        for r in lista if isinstance(lista, list) else [None]:
            regra = _regra(r, ids)
            if regra:  # (grupo, regex, é do pacote)
                regras.append(regra + (dado is not nucleo,))
            else:
                avisos.append("%s: regra de grupo inválida ignorada" % rotulo)
        plugins = dado.get("plugins", {})
        for nome, grupo in (plugins.items() if isinstance(plugins, dict) else [(None, None)]):
            if isinstance(nome, str) and grupo in ids:
                mapa.setdefault(nome, grupo)
            else:
                avisos.append("%s: plugin %r com grupo inválido ignorado" % (rotulo, str(nome)[:40]))
    return grupos, regras, mapa


def _grupo(h, plugin, regras, mapa):
    if h["fixa"]:
        return "tuneup"
    if plugin in mapa:
        return mapa[plugin]
    nome = " ".join((h["nome"].replace("-", " ").replace(":", " "), plugin or ""))
    # regra do pacote vale no texto todo e vem antes; nas do núcleo o nome diz mais que a descrição
    # ("API design" na descrição não faz a skill ser de design)
    for alvo, pacote in ((nome + " " + h["descricao"], True), (nome, False), (h["descricao"], False)):
        g = next((g for g, rx, do_pacote in regras if do_pacote == pacote and rx.search(alvo)), None)
        if g:
            return g
    return "outras"


def descobrir(cfg, home=None):
    """{grupos, habilidades, avisos}; cada habilidade leva também `_pasta` (só para o servidor)."""
    home = home or cfg.get("home") or os.path.expanduser("~")
    avisos, achadas, por_nome = [], [], {}
    grupos, regras, mapa = _regras(cfg, avisos)
    cortou = False
    for pasta, origem, listada, plugin in _fontes(cfg, home, avisos):
        try:
            nomes = sorted(os.listdir(pasta))
        except OSError:
            continue
        for d in nomes:
            if len(achadas) >= TETO:
                cortou = True
                break
            sub = os.path.join(pasta, d)
            lido = ler_skill(os.path.join(sub, "SKILL.md")) if RE_NOME.match(d) else None  # vai para o prompt
            if lido is None:
                continue
            curto = lido[0] if isinstance(lido[0], str) and lido[0] else d
            nome = "%s:%s" % (plugin, curto) if plugin else curto
            if not RE_NOME.match(nome) or not RE_NOME.match(curto):
                continue
            desc = re.sub(r"\s+", " ", mascara.mascarar(lido[1])).strip()
            fixa = bool(plugin) and (plugin == "tune-up" or plugin.startswith("tune-up-"))
            h = {"id": hashlib.sha1(("%s\0%s" % (origem, nome)).encode("utf-8")).hexdigest()[:12],
                 "nome": nome, "titulo": curto, "descricao": desc[:DESCRICAO_MAX], "origem": origem,
                 "listada": listada, "fixa": fixa, "_pasta": os.path.abspath(sub)}
            h["grupo"] = _grupo(h, plugin, regras, mapa)
            antes = por_nome.get(nome)
            if antes is None:
                por_nome[nome] = len(achadas)
                achadas.append(h)
            elif listada and not achadas[antes]["listada"]:  # fica a que o Claude já lista
                achadas[antes] = h
    if cortou:
        avisos.append("Há skills demais; mostrei só as primeiras %d." % TETO)
    usados = {h["grupo"] for h in achadas}
    return {"grupos": [{"id": g["id"], "titulo": g["titulo"]} for g in grupos if g["id"] in usados],
            "habilidades": achadas, "avisos": avisos}


def _chave(cfg):
    pastas = json.dumps(cfg.get("habilidades_pastas") or [], sort_keys=True)
    return (cfg.get("home"), cfg.get("raiz"), cfg.get("repo"), cfg.get("pacote_dir"), cfg.get("pacote_ok"), pastas)


def listar(cfg, forcar=False, relogio=time.monotonic):
    """descobrir() com cache de TTL segundos (a trava evita duas varreduras ao mesmo tempo)."""
    with _trava:
        chave, agora = _chave(cfg), relogio()
        guardado = _cache.get(chave)
        if forcar or guardado is None or agora - guardado[0] > TTL:
            _cache.clear()
            guardado = _cache[chave] = (agora, descobrir(cfg))
        return guardado[1]


def para_tela(dado):
    """Resposta da rota: sem caminho de arquivo."""
    return {"grupos": dado["grupos"], "avisos": dado["avisos"],
            "habilidades": [{k: h[k] for k in PUBLICOS} for h in dado["habilidades"]]}


def anexar(cfg, grupo, texto, ids):
    """(texto com o bloco das skills no fim, [nomes]). Sem escolha: texto igual e []. Levanta ErroAcao."""
    if any(ln.strip() in (INICIO, FIM) for ln in texto.split("\n")):
        raise ErroAcao("O texto tem uma linha reservada do painel. Tire a linha que começa com [skills "
                       "ou [fim das skills.")
    if ids is None or ids == []:
        return texto, []
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ErroAcao("Lista de skills inválida.")
    if grupo != "chat":
        raise ErroAcao("Skills só podem ser escolhidas no chat.")
    if len(ids) > MAX_ESCOLHA:
        raise ErroAcao("Escolha no máximo %d skills por pedido." % MAX_ESCOLHA)
    if len(set(ids)) != len(ids):
        raise ErroAcao("A mesma skill veio duas vezes.")
    por_id = {h["id"]: h for h in listar(cfg)["habilidades"]}
    escolhidas = []
    for i in ids:
        h = por_id.get(i) if RE_ID.match(i) else None
        if h is None:
            raise ErroAcao("Essa skill não existe mais. Atualize a lista.")
        if h["fixa"]:
            raise ErroAcao("As skills do tune-up já valem sempre; não precisa escolher.")
        escolhidas.append(h)
    linhas = [INICIO]
    for h in escolhidas:
        if h["listada"]:
            linhas.append('- %s: use a ferramenta Skill com "%s"' % (h["nome"], h["nome"]))
        else:
            linhas.append("- %s (fora da lista): leia %s e siga" % (h["nome"], os.path.join(h["_pasta"], "SKILL.md")))
    linhas += [FECHO, FIM]
    return texto.rstrip() + "\n\n" + "\n".join(linhas), [h["nome"] for h in escolhidas]


def tirar_bloco(texto):
    """(texto sem o bloco do fim, [nomes] ou None se não havia bloco). Marca de início só como linha
    inteira; a de fim só como última linha."""
    linhas = texto.rstrip().split("\n")
    i = max((j for j, ln in enumerate(linhas) if ln == INICIO), default=-1)
    if i < 0 or linhas[-1] != FIM:
        return texto, None
    nomes = [m.group(1) for m in map(RE_LINHA.match, linhas[i:]) if m]
    return "\n".join(linhas[:i]).rstrip(), nomes


def pedido(cfg, grupo, prompt, ids):
    """Prompt de uma ação nova (lancador.iniciar): recusa vazio ou começando com "-" e põe o bloco no fim."""
    if not prompt or prompt.startswith("-"):
        raise ErroAcao("O pedido ficou vazio.")
    return anexar(cfg, grupo, prompt, ids)
