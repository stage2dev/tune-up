"""Configuração do painel: tudo que muda de um projeto para outro.

O núcleo é genérico. O que é de um projeto vive em <raiz>/.tune-up/painel.json
(tudo opcional) e no pacote do projeto (<raiz>/.tune-up/<pacote>/: ações extras,
módulos de tela e dados). Sem arquivo e sem pacote o painel sobe com avisos.

Raiz do projeto: --projeto, senão a variável TUNEUP_PAINEL_PROJETO, senão a
primeira pasta com .tune-up/ subindo a partir do cwd, senão dois níveis acima
da pasta do painel. Python 3.9, só biblioteca padrão.
"""
import json
import os
import re

PAINEL = os.path.dirname(os.path.abspath(__file__))
VERSAO = "2.1.0"
ENV_PROJETO = "TUNEUP_PAINEL_PROJETO"
PACOTE_PADRAO = "painel-projeto"

RE_ORIGEM = re.compile(r"^http://(127\.0\.0\.1|localhost):\d{2,5}$")
RE_NOME_PROJETO = re.compile(r"^[^\x00-\x1f\x7f]{1,60}$")
RE_ID = re.compile(r"^[a-z0-9_-]{1,40}$")
RE_PACOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,59}$")
LIMITE_JSON = 64 * 1024
MAX_AREAS = 20


class Config(dict):
    """dict com acesso por atributo: cfg["raiz"] e cfg.raiz funcionam."""

    def __getattr__(self, chave):
        try:
            return self[chave]
        except KeyError:
            raise AttributeError(chave)


def raiz_compat():
    """Painel em <raiz>/.tune-up/painel: dois níveis acima."""
    return os.path.dirname(os.path.dirname(PAINEL))


def achar_raiz(projeto=None, cwd=None, env=None):
    """(raiz, origem). Ordem: --projeto, variável de ambiente, subir do cwd, pasta do painel."""
    env = os.environ if env is None else env
    if projeto:
        return os.path.realpath(os.path.expanduser(projeto)), "--projeto"
    if env.get(ENV_PROJETO):
        return os.path.realpath(os.path.expanduser(env[ENV_PROJETO])), ENV_PROJETO
    atual = os.path.realpath(cwd or os.getcwd())
    while True:
        if os.path.isdir(os.path.join(atual, ".tune-up")):
            return atual, "cwd"
        pai = os.path.dirname(atual)
        if pai == atual:
            break
        atual = pai
    return os.path.realpath(raiz_compat()), "pasta do painel"


def _caminho(valor, base):
    if not isinstance(valor, str) or not valor.strip() or "\x00" in valor:
        return None
    valor = os.path.expanduser(valor.strip())
    if not os.path.isabs(valor):
        valor = os.path.join(base, valor)
    return os.path.realpath(valor)


def _dentro(caminho, base):
    base = os.path.realpath(base)
    return os.path.realpath(caminho).startswith(base.rstrip(os.sep) + os.sep)


def _achar_repo(raiz):
    if os.path.exists(os.path.join(raiz, ".git")):
        return raiz
    try:
        filhos = sorted(os.listdir(raiz))
    except OSError:
        return None
    for nome in filhos:
        cand = os.path.join(raiz, nome)
        if not nome.startswith(".") and os.path.isdir(cand) and os.path.exists(os.path.join(cand, ".git")):
            return cand
    return None


def _achar_plans(raiz, repo):
    for base in (repo, raiz):
        if base and os.path.isdir(os.path.join(base, ".planning", "phases")):
            return os.path.join(base, ".planning")
    return os.path.join(repo or raiz, ".planning")


def achar_guarda(home=None):
    """guarda.py do plugin tune-up instalado, pelo registro ~/.claude/plugins/installed_plugins.json.

    Devolve (caminho ou None, aviso ou None). Sem o plugin o painel segue sem ele.
    """
    todas = _instalacoes(home)
    if todas is None:
        return None, "plugin tune-up não encontrado (sem installed_plugins.json); sigo sem ele"
    candidatos = []
    for chave, e in todas:
        if str(chave).split("@", 1)[0] != "tune-up":
            continue
        g = os.path.join(os.path.expanduser(e["installPath"]), "scripts", "guarda.py")
        if os.path.isfile(g):
            candidatos.append((_quando(e), g))
    if not candidatos:
        return None, "plugin tune-up não está instalado; sigo sem ele (nomes de marcador padrão)"
    return sorted(candidatos)[-1][1], None


def _quando(e):
    return str(e.get("lastUpdated") or e.get("installedAt") or "")


def _instalacoes(home=None):
    """[(chave, entrada)] de ~/.claude/plugins/installed_plugins.json (só entradas com installPath);
    None se o arquivo não existe ou não lê. `home` troca o ~ (testes)."""
    home = home or os.path.expanduser("~")
    registro = os.path.join(home, ".claude", "plugins", "installed_plugins.json")
    try:
        with open(registro, encoding="utf-8") as f:
            dado = json.load(f)
    except (OSError, ValueError):
        return None
    plugins = dado.get("plugins") if isinstance(dado, dict) else None
    saida = []
    for chave, entradas in (plugins.items() if isinstance(plugins, dict) else []):
        for e in entradas if isinstance(entradas, list) else [entradas]:
            if isinstance(e, dict) and isinstance(e.get("installPath"), str):
                saida.append((chave, e))
    return saida


def achar_plugin(chave, home=None):
    """installPath do plugin `plugin@marketplace`, ou None. Com várias entradas vale a de
    lastUpdated (ou installedAt) mais recente; empate fica com a última do arquivo."""
    achados = [(_quando(e), i, e["installPath"]) for i, (c, e) in enumerate(_instalacoes(home) or [])
               if c == chave]
    return os.path.expanduser(sorted(achados)[-1][2]) if achados else None


def _ler_arquivo(caminho, avisos):
    if not os.path.isfile(caminho):
        avisos.append("sem .tune-up/painel.json: usei os padrões")
        return {}
    try:
        with open(caminho, "rb") as f:
            bruto = f.read(LIMITE_JSON + 1)
        if len(bruto) > LIMITE_JSON:
            avisos.append("painel.json passou de 64 KB; ignorei")
            return {}
        dado = json.loads(bruto.decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as e:
        avisos.append("painel.json ilegível (%s); usei os padrões" % type(e).__name__)
        return {}
    if not isinstance(dado, dict):
        avisos.append("painel.json não é um objeto; usei os padrões")
        return {}
    return dado


def _inteiro(valor, padrao, minimo, maximo):
    if isinstance(valor, bool) or not isinstance(valor, int):
        return padrao
    return max(minimo, min(maximo, valor))


def _pacote(bruto, tune_up, avisos):
    nome = bruto.get("pacote", PACOTE_PADRAO)
    if not isinstance(nome, str) or not RE_PACOTE.match(nome) or nome in (".", ".."):
        avisos.append("painel.json: pacote precisa ser um nome de pasta simples; usei %s" % PACOTE_PADRAO)
        nome = PACOTE_PADRAO
    pasta = os.path.join(tune_up, nome)
    if os.path.lexists(pasta) and not _dentro(pasta, tune_up):
        avisos.append("pacote %s aponta para fora de .tune-up; ignorei" % nome)
        return pasta, False
    if not os.path.isdir(pasta):
        avisos.append("sem pacote do projeto (.tune-up/%s): só as telas e ações do núcleo" % nome)
        return pasta, False
    return os.path.realpath(pasta), True


def _modulos(bruto, avisos):
    lista = bruto.get("modulos", [])
    if not isinstance(lista, list):
        avisos.append("painel.json: modulos precisa ser uma lista; ignorei")
        return []
    ok = []
    for m in lista:
        if isinstance(m, str) and RE_ID.match(m) and m not in ok:
            ok.append(m)
        else:
            avisos.append("painel.json: módulo %r ignorado (id inválido ou repetido)" % str(m)[:40])
    return ok


def _areas(bruto, avisos):
    lista = bruto.get("areas_acompanhamento", [])
    if not isinstance(lista, list):
        avisos.append("painel.json: areas_acompanhamento precisa ser uma lista; ignorei")
        return []
    ok, vistos = [], set()
    for a in lista[:MAX_AREAS]:
        if not isinstance(a, dict) or not isinstance(a.get("id"), str) or not RE_ID.match(a["id"]) \
                or a["id"] in vistos or not isinstance(a.get("regex"), str) or len(a["regex"]) > 500:
            avisos.append("painel.json: área de acompanhamento inválida ignorada")
            continue
        try:
            re.compile(a["regex"])
        except re.error:
            avisos.append("painel.json: regex da área %s inválida; ignorei a área" % a["id"])
            continue
        titulo = a.get("titulo") if isinstance(a.get("titulo"), str) and a["titulo"].strip() else a["id"]
        vistos.add(a["id"])
        ok.append({"id": a["id"], "titulo": titulo.strip()[:60], "regex": a["regex"]})
    return ok


def migrar_registro_antigo(cfg, antiga=None):
    """Uma vez só: copia o registro de execuções de <painel>/dados (versão antiga) para dados_dir.

    Só vale quando o painel mora em <raiz>/.tune-up/painel deste projeto e o registro novo ainda
    não existe. Copia (não move) porque um painel antigo pode estar rodando com a pasta velha.
    Devolve o aviso (também posto em cfg["avisos"]) ou None.
    """
    antiga = os.path.realpath(antiga or os.path.join(PAINEL, "dados"))
    velho = os.path.join(antiga, "execucoes.json")
    destino = cfg.get("dados_dir")
    if not destino or not os.path.isfile(velho) or os.path.realpath(destino) == antiga \
            or os.path.dirname(os.path.dirname(os.path.dirname(antiga))) != os.path.realpath(cfg.get("raiz") or ""):
        return None
    novo = os.path.join(destino, "execucoes.json")
    if os.path.lexists(novo):
        return None
    try:
        with open(velho, "rb") as f:
            bruto = f.read(4 * 1024 * 1024)
        if not isinstance(json.loads(bruto.decode("utf-8")), list):
            raise ValueError("não é uma lista")
        os.makedirs(destino, mode=0o700, exist_ok=True)
        os.chmod(destino, 0o700)
        tmp = novo + ".migrando"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(bruto)
        os.chmod(tmp, 0o600)
        os.replace(tmp, novo)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        aviso = "não consegui trazer o registro antigo de execuções (%s): %s" % (velho, type(e).__name__)
    else:
        aviso = ("registro de execuções trazido de %s para %s; a pasta antiga pode ser apagada "
                 "quando nenhum painel antigo estiver rodando" % (antiga, destino))
    cfg.setdefault("avisos", []).append(aviso)
    return aviso


def carregar(raiz=None, arquivo=None, home=None):
    """Monta a configuração. Nunca levanta exceção por causa do arquivo."""
    avisos = []
    raiz = os.path.realpath(os.path.expanduser(raiz or achar_raiz()[0]))
    tune_up = os.path.join(raiz, ".tune-up")
    arquivo = arquivo or os.path.join(tune_up, "painel.json")
    bruto = _ler_arquivo(arquivo, avisos)

    repo = _caminho(bruto.get("repo"), raiz)
    if bruto.get("repo") is not None and (not repo or not os.path.isdir(repo)):
        avisos.append("painel.json: repo não encontrado; procurei sozinho")
        repo = None
    repo = repo or _achar_repo(raiz)

    plans = _caminho(bruto.get("plans_dir"), raiz)
    plans_origem = "painel.json" if plans else "padrão"
    plans = plans or _achar_plans(raiz, repo)

    claude_bin = bruto.get("claude_bin")
    if not isinstance(claude_bin, str) or not claude_bin.strip() or claude_bin.strip().startswith("-") \
            or re.search(r"[\x00-\x1f\x7f]", claude_bin):
        claude_bin = "claude"
    claude_bin = os.path.expanduser(claude_bin.strip())

    nome = bruto.get("nome")
    if not isinstance(nome, str) or not RE_NOME_PROJETO.match(nome.strip() or ""):
        nome = os.path.basename(raiz) or "projeto"

    origens = [o for o in bruto.get("origens_extras") or [] if isinstance(o, str) and RE_ORIGEM.match(o)]

    guarda = _caminho(bruto.get("guarda"), raiz)
    if guarda and not os.path.isfile(guarda):
        avisos.append("painel.json: guarda não encontrado; procurei o plugin instalado")
        guarda = None
    if not guarda:
        guarda, aviso = achar_guarda(home)
        if aviso:
            avisos.append(aviso)

    pacote, pacote_ok = _pacote(bruto, tune_up, avisos)

    # Chaves opcionais lidas por módulos do núcleo (passam só se o tipo bate).
    extras = {}
    if isinstance(bruto.get("projeto_mem"), str) and RE_NOME_PROJETO.match(bruto["projeto_mem"]):
        extras["projeto_mem"] = bruto["projeto_mem"]
    if _caminho(bruto.get("claude_mem_db"), raiz):
        extras["claude_mem_db"] = _caminho(bruto.get("claude_mem_db"), raiz)

    return Config(
        extras,
        raiz=raiz,
        workspace=raiz,  # nome antigo, mantido para os módulos que ainda o usam
        arquivo=arquivo if os.path.isfile(arquivo) else None,
        bruto=dict(bruto),
        nome=nome.strip(),
        repo=repo,
        plans_dir=plans,
        plans_origem=plans_origem,
        claude_bin=claude_bin,
        max_execucoes=_inteiro(bruto.get("max_execucoes"), 3, 1, 10),
        pular_permissoes=bruto.get("pular_permissoes") is True,
        porta=_inteiro(bruto.get("porta"), 8787, 1024, 65535),
        origens_extras=origens,
        guarda=guarda,
        projects_dir=_caminho(bruto.get("claude_projects_dir"), raiz)
        or os.path.join(os.path.expanduser("~"), ".claude", "projects"),
        pacote_dir=pacote,
        pacote_ok=pacote_ok,
        modulos=_modulos(bruto, avisos),
        home=home or os.path.expanduser("~"),
        areas_acompanhamento=_areas(bruto, avisos),
        painel_dir=PAINEL,
        # registro das execuções e arquivos das ações; pacote fora de .tune-up não recebe escrita
        dados_dir=os.path.join(pacote, "dados") if pacote_ok or not os.path.lexists(pacote)
        else os.path.join(tune_up, "painel-dados"),
        acoes_dir=os.path.join(PAINEL, "acoes"),
        acoes_pacote_dir=os.path.join(pacote, "acoes") if pacote_ok else None,
        web_dir=os.path.join(PAINEL, "web", "dist"),
        versao=VERSAO,
        avisos=avisos,
    )
