"""Candidatos do buscador de leads: importa os arquivos JSON que a sessão do dono deixou em
<raiz>/.tune-up/<pacote>/dados/vendas-candidatos/ para a tabela `candidatos` e APAGA cada arquivo.

Só dado de empresa. Texto vindo da web é dado: nunca é executado nem obedecido, só guardado (limitado, sem controle).
Arquivo inválido: vira um evento `candidatos_recusados` (só nome do arquivo e motivo) e é apagado; nunca fica na pasta.
A pasta só vale se o caminho real dela for o do pacote do projeto (link simbólico ou `..` = recusa)."""
import json
import os
import re
import stat
import threading
from urllib.parse import parse_qsl, urlsplit

from servico import banco, conhecimento, telefone

SUBPASTA = ("dados", "vendas-candidatos")
ARQUIVO_MAX = 256 * 1024
LINHAS_MAX = 30
LIMITES = {"nome": 200, "site": 300, "url_da_fonte": 500, "nicho": 100, "cidade": 100}
CAMPOS = ("nome", "site", "telefone_publicado_no_site", "url_da_fonte", "nicho", "cidade")
RE_CONTROLE = re.compile(r"[\x00-\x1f\x7f-\x9f]")
ROTA = re.compile(r"^/candidatos/importar$")
_trava = threading.Lock()


class PastaRecusada(Exception):
    pass


def pasta_dos_candidatos(raiz):
    """Caminho (não resolvido) da pasta de candidatos do pacote deste projeto."""
    pacote = os.path.dirname(conhecimento.pasta_vendas(raiz))
    return os.path.join(pacote, *SUBPASTA)


def _conferir_pasta(raiz):
    """Pasta existente e com o caminho real exatamente <pacote real>/dados/vendas-candidatos; None se não existe."""
    pasta = pasta_dos_candidatos(raiz)
    if not os.path.lexists(pasta):
        return None
    relativo = os.path.relpath(pasta, raiz)  # .tune-up/<pacote>/dados/vendas-candidatos: tudo tem de ser pasta de verdade
    esperado = os.path.join(os.path.realpath(raiz), relativo)
    if os.path.islink(pasta) or os.path.normcase(os.path.realpath(pasta)) != os.path.normcase(esperado) \
            or not os.path.isdir(pasta):
        raise PastaRecusada("a pasta de candidatos não está dentro do pacote do projeto")
    return pasta


def _texto(valor, limite):
    if not isinstance(valor, str):
        return None
    limpo = " ".join(RE_CONTROLE.sub(" ", valor).split())[:limite]
    return limpo or None


SEM_ESQUEMA = re.compile(r"^[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}(?:[/?#]|$)")  # www.empresa.com[/...]


def _http(valor, sem_esquema=False):
    """URL http(s) com host; `sem_esquema` (só o site): 'www.empresa.com' ganha 'https://'. False = recusada."""
    if valor is None:
        return None
    if sem_esquema and SEM_ESQUEMA.match(valor):
        valor = "https://" + valor
    partes = urlsplit(valor)
    return valor if partes.scheme in ("http", "https") and partes.hostname else False


def validar_linha(bruto):
    """dict limpo ou levanta ValueError (motivo curto, sem o conteúdo). Chaves desconhecidas somem."""
    if not isinstance(bruto, dict):
        raise ValueError("linha não é um objeto")
    nome = _texto(bruto.get("nome"), LIMITES["nome"])
    if not nome:
        raise ValueError("linha sem nome")
    linha = {"nome": nome, "nicho": _texto(bruto.get("nicho"), LIMITES["nicho"]),
             "cidade": _texto(bruto.get("cidade"), LIMITES["cidade"])}
    for chave in ("site", "url_da_fonte"):
        url = _http(_texto(bruto.get(chave), LIMITES[chave]), sem_esquema=chave == "site")
        if url is False:
            raise ValueError("%s precisa ser http ou https" % chave)
        linha[chave] = url
    fone = _texto(bruto.get("telefone_publicado_no_site"), 40)
    linha["telefone"] = None
    if fone:
        if not linha["url_da_fonte"]:
            raise ValueError("telefone sem url_da_fonte")
        try:
            linha["telefone"] = telefone.normalizar(fone)
        except telefone.TelefoneInvalido:
            raise ValueError("telefone inválido")
    return linha


def _ler(caminho):
    """Lista de objetos do arquivo, ou levanta ValueError. Só arquivo regular (nunca link), com tamanho limitado."""
    if not stat.S_ISREG(os.lstat(caminho).st_mode):
        raise ValueError("não é um arquivo comum")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(caminho, flags)
    with os.fdopen(fd, "rb") as f:
        bruto = f.read(ARQUIVO_MAX + 1)
    if len(bruto) > ARQUIVO_MAX:
        raise ValueError("arquivo grande demais")
    try:
        dado = json.loads(bruto.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise ValueError("não é JSON válido")
    if isinstance(dado, dict):
        dado = dado.get("candidatos")
    if not isinstance(dado, list):
        raise ValueError("esperava uma lista de empresas")
    return dado


PLATAFORMAS = frozenset(("instagram.com", "facebook.com", "fb.com", "linktr.ee", "wa.me", "whatsapp.com",
                          "google.com", "g.page", "goo.gl", "tiktok.com", "youtube.com",
                          "linkedin.com", "x.com", "twitter.com"))
PARAMETROS_QUE_IDENTIFICAM = ("id", "phone", "cid")  # profile.php?id=, send?phone=, maps?cid=


def chave_do_site(site):
    """Site normalizado para a anti re-sugestão: host (sem 'www.') + caminho, minúsculo, sem barra final nem âncora.
    Query ignorada, salvo em plataforma (ou subdomínio dela), onde id/phone/cid entram ordenados: lá a query é que
    identifica a empresa. None se não há site ou se é só a raiz de uma plataforma (não identifica a empresa)."""
    partes = urlsplit(site) if site else None
    host = ((partes.hostname or "") if partes else "").lower()
    host = host[4:] if host.startswith("www.") else host
    if not host:
        return None
    caminho = partes.path.rstrip("/").lower()
    if not any(host == p or host.endswith("." + p) for p in PLATAFORMAS):
        return host + caminho
    ids = sorted("%s=%s" % (k, v) for k, v in parse_qsl(partes.query.lower()) if k in PARAMETROS_QUE_IDENTIFICAM)
    if not caminho and not ids:
        return None
    return host + caminho + ("?" + "&".join(ids) if ids else "")


def _gravar(con, linhas):
    """Insere numa transação. Devolve (novos, repetidos, descartados_recentes); repetido = mesmo telefone ou mesmo
    nome/cidade/nicho; descartado recente = mesmo site (chave_do_site) de um candidato descartado nos últimos 30 dias."""
    novos = descartados = 0
    con.execute("BEGIN IMMEDIATE")
    try:
        for l in linhas:
            host = chave_do_site(l["site"])  # coluna site_host guarda a chave do site (host + caminho)
            if host and con.execute("SELECT 1 FROM candidatos WHERE site_host = ? AND estado = 'descartado'",
                                    (host,)).fetchone():
                descartados += 1
                continue  # empresa descartada há pouco: não sugere de novo (telefone igual já cai no índice único)
            cur = con.execute(
                "INSERT OR IGNORE INTO candidatos (nome, site, telefone, url_da_fonte, nicho, cidade, criado_em, "
                "site_host) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (l["nome"], l["site"], l["telefone"],
                                                              l["url_da_fonte"], l["nicho"], l["cidade"],
                                                              banco.agora(), host))
            novos += cur.rowcount
        con.execute("COMMIT")
    except BaseException:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    return novos, len(linhas) - novos - descartados, descartados


def _apagar(caminho):
    """Apaga o arquivo (se for link, só o link; nunca o alvo). False se não conseguiu."""
    try:
        os.remove(caminho)
        return True
    except FileNotFoundError:
        return True
    except OSError:
        return False


def importar(con, raiz):
    """Importa e apaga os arquivos da pasta. Devolve {arquivos, novos, repetidos, descartados_recentes, recusados,
    linhas_recusadas, nao_apagados}. Levanta PastaRecusada se a pasta fugir do pacote. Erro do banco deixa o arquivo na pasta."""
    r = {"arquivos": 0, "novos": 0, "repetidos": 0, "descartados_recentes": 0, "recusados": 0, "linhas_recusadas": 0,
         "nao_apagados": 0}
    with _trava:
        pasta = _conferir_pasta(raiz)
        if pasta is None:
            return r
        for nome in sorted(os.listdir(pasta)):
            caminho = os.path.join(pasta, nome)
            r["arquivos"] += 1
            try:
                if not nome.lower().endswith(".json"):
                    raise ValueError("só arquivos .json")
                brutas = _ler(caminho)
                ruins, boas = 0, []
                for b in brutas[:LINHAS_MAX]:
                    try:
                        boas.append(validar_linha(b))
                    except ValueError:
                        ruins += 1
                ruins += max(0, len(brutas) - LINHAS_MAX)
                if brutas and not boas:
                    raise ValueError("nenhuma linha válida")
            except (ValueError, OSError) as e:
                motivo = str(e) if isinstance(e, ValueError) else "não consegui ler"
                banco.registrar_evento(con, "candidatos_recusados", json.dumps(
                    {"arquivo": _texto(nome, 80), "motivo": motivo}, ensure_ascii=False))
                r["recusados"] += 1
                if not _apagar(caminho):
                    r["nao_apagados"] += 1
                continue
            novos, repetidos, descartados = _gravar(con, boas)
            r["novos"] += novos
            r["repetidos"] += repetidos
            r["descartados_recentes"] += descartados
            r["linhas_recusadas"] += ruins
            if not _apagar(caminho):
                r["nao_apagados"] += 1
    return r


def resumo(r):
    texto = "%d arquivo(s): %d candidato(s) novo(s), %d repetido(s)" % (r["arquivos"], r["novos"], r["repetidos"])
    if r.get("descartados_recentes"):
        texto += "; %d descartado(s) há menos de 30 dias (não sugeridos de novo)" % r["descartados_recentes"]
    if r["recusados"] or r["linhas_recusadas"]:
        texto += "; recusado(s): %d arquivo(s), %d linha(s)" % (r["recusados"], r["linhas_recusadas"])
    if r["nao_apagados"]:
        texto += "; %d arquivo(s) não puderam ser apagados, apague à mão" % r["nao_apagados"]
    return texto + "."


def executar(app, con, metodo, caminho, query, corpo):
    """Rota POST /candidatos/importar (com token): importa a pasta deste projeto."""
    if not ROTA.match(caminho) or metodo != "POST":
        return None
    if not app.raiz:
        return 409, {"erro": "O serviço não sabe a raiz do projeto."}
    try:
        return 200, importar(con, app.raiz)
    except PastaRecusada as e:
        return 409, {"erro": str(e)}
