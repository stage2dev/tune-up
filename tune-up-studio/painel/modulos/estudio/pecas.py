"""Peças do estúdio: abas Fila, Galeria e Aprovação, e os comandos peca.aprovar / peca.recusar.

As execuções vêm do lançador (ctx["execucoes"]); a pasta de cada uma é <dados>/trabalhos/<id>.
O selo é o do servidor (selo.py). Aprovar copia os arquivos para uma pasta temporária dentro de
<dados>/aprovados/, grava manifesto.json por último (sha256 calculado aqui, dos bytes copiados) e
troca o nome para <dados>/aprovados/<id> com os.replace; já aprovado = 409. Recusar grava
<dados>/recusados/<id>.json. Python 3.9, só biblioteca padrão.
"""
import datetime
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile

import selo

RE_TRABALHO = re.compile(r"^[0-9a-f]{12}$")
RE_DATA = re.compile(r"^\d{4}-(\d{2})-(\d{2})T(\d{2}):(\d{2})")
MAX_PECAS = 30
APROVAVEL = ("terminou", "precisa_de_voce")  # parada (teto, erro) ou ainda rodando: nunca vai para aprovação
INDISPONIVEL = "A lista de peças não está disponível agora. Tente de novo em instantes."
BLOCO = 64 * 1024
FORMATO_VIDEO = "reel 9:16 %s s"
MOTIVOS = {"png": "falta a imagem", "png_size": "imagem no tamanho errado", "png_fresh": "o desenho mudou depois da imagem",
           "video_size": "vídeo no tamanho errado", "duration": "vídeo com a duração errada", "fps": "vídeo travado",
           "frames": "vídeo travado", "codec": "vídeo num formato que o Instagram não aceita",
           "faststart": "vídeo demora a começar", "no_audio": "o vídeo tem som", "video_stream": "o vídeo não abre",
           "video_fresh": "o desenho mudou depois do vídeo", "engine_reserve": "o vídeo não veio do jeito pedido",
           "engine_hyperframes": "o vídeo não veio do jeito pedido",
           "layout_allow_count": "texto pode sair do quadro", "no_gsap": "usa animação proibida",
           "network_lint": "busca coisas na internet", "no_script": "o desenho tem código",
           "fonte": "arquivos do desenho com problema", "atalho": "pasta da peça com atalho",
           "conferencia_da_sessao": "a conferência do Claude não passou", "quadros": "número de quadros errado",
           "legenda": "falta a legenda", "formato": "formato desconhecido", "video": "falta o vídeo",
           "ffprobe": "falta o ffprobe para conferir o vídeo", "probe": "o vídeo não abre",
           "conferir": "não consegui conferir"}


def _agora():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _ler_json(caminho, limite=1024 * 1024):
    """Objeto JSON de um arquivo comum pequeno, ou None (atalho, FIFO, grande, ilegível)."""
    try:
        st = os.lstat(caminho)
        if not stat.S_ISREG(st.st_mode) or st.st_size > limite:
            return None
        with open(caminho, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None
    return d if isinstance(d, dict) else None


def execucoes(ctx):
    """Execuções do estúdio com pasta de trabalho, mais novas primeiro; None se o painel não deu a lista."""
    fonte = ctx.get("execucoes")
    if not callable(fonte):
        return None
    try:
        todas = fonte()
    except Exception:  # noqa: BLE001 - o CLI ou o registro falhou: a tela diz que a fila não está disponível
        return None
    return [e for e in todas if str(e.get("acao") or "").startswith("estudio.") and selo.tipo(e.get("acao"))
            and RE_TRABALHO.match(str(e.get("trabalho") or ""))]


def pasta(ctx, tid):
    """Caminho da pasta de trabalho (nunca atalho, dentro de <dados>/trabalhos) ou None."""
    if not ctx.get("dados") or not isinstance(tid, str) or not RE_TRABALHO.match(tid):
        return None
    base = os.path.realpath(os.path.join(ctx["dados"], "trabalhos"))
    p = os.path.join(base, tid)
    try:
        ok = stat.S_ISDIR(os.lstat(p).st_mode) and os.path.realpath(p) == p
    except OSError:
        return None
    return p if ok else None


def _linha_da_sessao(p, tipo):
    """A linha final que a sessão escreveu (só para o rótulo da fila; nunca decide o selo)."""
    d = _ler_json(os.path.join(p, "final.json" if tipo == "post" else "qa.json")) if p else None
    return str((d or {}).get("linha") or "")


def estado(e, p):
    """(palavra, tom) do estado da execução para a tela."""
    est = e.get("estado")
    if est == "rodando":
        return "rodando", "neutro"
    if est == "terminou":
        return "terminou", "bom"
    if est == "precisa_de_voce":  # sessão do estúdio que terminou e ficou parada no CLI: não é trava
        linha = _linha_da_sessao(p, selo.tipo(e.get("acao")))
        if linha.startswith("PRECISA DO SEU OLHO"):
            return "precisa do seu olho", "atencao"
        if linha.startswith("PRONTO"):
            return "terminou", "bom"
        return "esperando sua resposta", "atencao"
    return "parou", "ruim"


def _marcas(ctx, tid):
    aprovado = os.path.lexists(os.path.join(ctx["dados"], "aprovados", tid))
    recusado = os.path.lexists(os.path.join(ctx["dados"], "recusados", tid + ".json"))
    return aprovado, recusado


def pecas(ctx):
    """Lista de peças (as MAX_PECAS execuções mais novas do estúdio) ou None sem lista do painel."""
    lista = execucoes(ctx)
    if lista is None:
        return None
    out = []
    for e in lista[:MAX_PECAS]:
        p = pasta(ctx, e["trabalho"])
        palavra, tom = estado(e, p)
        item = {"e": e, "id": e["trabalho"], "pasta": p, "palavra": palavra, "tom": tom, "selo": None}
        item["aprovado"], item["recusado"] = _marcas(ctx, e["trabalho"])
        if p and e.get("estado") != "rodando":
            try:
                item["selo"] = selo.calcular(p, e["acao"], e.get("params") or {})
            except (OSError, ValueError, MemoryError) as erro:  # pasta sumiu ou mudou no meio: vermelho, com o motivo
                item["selo"] = {"ok": False, "linha": "PRECISA DO SEU OLHO: não consegui conferir (%s)"
                                % type(erro).__name__, "arquivos": [], "falhas": ["conferir"]}
        out.append(item)
    return out


def _titulo(item):
    """"Post de 11/11 às 08:23" (tipo da peça + quando começou)."""
    e = item["e"]
    tipo = "Vídeo" if selo.tipo(e.get("acao")) == "video" else (
        "Carrossel" if str((e.get("params") or {}).get("formato") or "").startswith("carrossel") else "Post")
    m = RE_DATA.match(str(e.get("iniciada_em") or ""))
    return "%s de %s/%s às %s:%s" % ((tipo,) + m.groups()[1::-1] + m.groups()[2:]) if m else tipo


def _nome(arquivo):
    """"q2.png" -> "quadro 2"; o vídeo é "vídeo"."""
    m = re.match(r"^q(\d+)\.png$", arquivo)
    return "quadro %s" % m.group(1) if m else "vídeo"


def _motivos(falhas):
    """Nomes das checagens -> texto simples ("falta a legenda, imagem no tamanho errado")."""
    return ", ".join(dict.fromkeys(MOTIVOS.get(f, "não passou na conferência") for f in falhas or []))[:300]


def _texto_selo(s):
    if s["ok"]:
        return "Pronto para aprovar."
    return "Precisa do seu olho: %s." % (_motivos(s.get("falhas")) or "não consegui conferir")


def _selo_da_peca(i):
    """Selo da fila: o que a pessoa precisa saber em duas palavras."""
    if i["aprovado"]:
        return "aprovada", "bom"
    if i["recusado"]:
        return "recusada", "neutro"
    if i["palavra"] == "rodando":
        return "fazendo agora", "neutro"
    if i["tom"] == "ruim":
        return "parou", "ruim"
    if i["selo"] and i["selo"]["ok"]:
        return "Pronto para aprovar", "bom"
    return "Precisa do seu olho", "atencao"


def _so_a_legenda(copy):
    """Só a seção "## Legenda" do copy.md (sem o contador "(104/125)"); sem a seção, o texto inteiro."""
    m = re.search(r"^##\s*Legenda[^\n]*\n(.*?)(?=^##\s|\Z)", copy, re.M | re.S | re.I)
    return (m.group(1).strip() if m else "") or copy


def _galeria(item, titulo=None):
    s = item["selo"]
    return {"tipo": "galeria", "titulo": titulo or _titulo(item), "vazio": "Nenhum arquivo para mostrar.",
            "itens": [{"arquivo": "trabalhos/%s/%s" % (item["id"], a["c"]), "rotulo": _nome(a["nome"]),
                       "selo": {"texto": "pronto", "tom": "bom"} if not a["falhas"]
                       else {"texto": "precisa do seu olho: " + _motivos(a["falhas"])[:120], "tom": "ruim"}}
                      for a in s["arquivos"]]}


def aba_fila(lista):
    if lista is None:
        return [{"tipo": "texto", "texto": "A fila não está disponível nesta tela."}]
    itens = [{"titulo": _titulo(i), "selo": dict(zip(("texto", "tom"), _selo_da_peca(i))),
              "detalhe": "O Claude ainda está trabalhando. A tela se atualiza sozinha." if i["palavra"] == "rodando"
              else "Aprovada. Os arquivos estão na pasta de aprovados." if i["aprovado"]
              else "Recusada." if i["recusado"]
              else "Parou antes de terminar. Peça de novo na aba Novo." if i["tom"] == "ruim"
              else _texto_selo(i["selo"]) if i["selo"] else ""} for i in lista]
    return [{"tipo": "lista", "titulo": "Peças do estúdio", "itens": itens,
             "vazio": "Nada na fila. Peça uma peça na aba Novo."}]


def aba_galeria(lista):
    if lista is None:
        return [{"tipo": "texto", "texto": INDISPONIVEL}]
    prontas = [i for i in lista if i["selo"] and i["selo"]["arquivos"]]
    if not prontas:
        return [{"tipo": "texto", "texto": "Ainda não há peças prontas."}]
    blocos = []
    for i in prontas:
        marca = "Aprovada." if i["aprovado"] else "Recusada." if i["recusado"] else _texto_selo(i["selo"])
        blocos += [_galeria(i, _titulo(i) + (" (aprovada)" if i["aprovado"] else " (recusada)" if i["recusado"] else "")),
                   {"tipo": "texto", "texto": marca}]
    return blocos


def aba_aprovacao(lista):
    if lista is None:
        return [{"tipo": "texto", "texto": INDISPONIVEL}]
    espera = [i for i in lista if i["selo"] and i["selo"]["ok"] and not i["aprovado"] and not i["recusado"]
              and i["e"].get("estado") in APROVAVEL]
    if not espera:
        return [{"tipo": "texto", "texto": "Nenhuma peça pronta esperando você. Peça uma na aba Novo; "
                 "as já aprovadas ficam na Galeria."}]
    blocos = []
    for i in espera:  # cada arquivo em tamanho cheio e a legenda que vai junto, antes dos botões
        t, fixos = _titulo(i), {"trabalho": i["id"], "confirmar": True}
        blocos += [{"tipo": "midia", "titulo": t if a["nome"] == "video.mp4" else "%s: %s" % (t, _nome(a["nome"])),
                    "arquivo": "trabalhos/%s/%s" % (i["id"], a["c"]), "alt": "%s, %s" % (t, _nome(a["nome"]))}
                   for a in i["selo"]["arquivos"]]
        texto = selo.legenda(i["pasta"]) if selo.tipo(i["e"].get("acao")) == "post" else None
        descricao = ("Legenda que vai junto:\n\n" + _so_a_legenda(texto)) if texto else "Vídeo vertical, sem som."
        blocos.append({"tipo": "formulario", "titulo": "Aprovar ou recusar?", "descricao": descricao,
                       "acao": "peca.aprovar", "botao": "Aprovar", "campos": [], "dados_fixos": fixos,
                       "confirmar": "Aprovar %s? Os arquivos vão para a pasta de aprovados." % t.lower(),
                       "secundario": {"acao": "peca.recusar", "botao": "Recusar", "confirmar": "Recusar %s?" % t.lower()}})
    return blocos


def _achar(ctx, dados):
    """(execução, pasta) da peça pedida, ou texto do erro."""
    tid = dados.get("trabalho")
    if dados.get("confirmar") is not True:
        return "Confirme a escolha."
    lista = execucoes(ctx)
    if lista is None:
        return "A fila não está disponível nesta tela."
    e = next((x for x in lista if x["trabalho"] == tid), None)
    p = pasta(ctx, tid) if e else None
    if not p:
        return "Não achei essa peça."
    if e.get("estado") == "rodando":
        return "O Claude ainda está trabalhando nesta peça. Espere terminar."
    if e.get("estado") not in APROVAVEL:
        return "Esta peça parou antes de terminar. Peça de novo na aba Novo."
    return e, p


def _copiar(origem, destino):
    """Copia sem seguir atalho; devolve (bytes, sha256 dos bytes gravados)."""
    fd = os.open(origem, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NONBLOCK", 0))
    h, total = hashlib.sha256(), 0
    with os.fdopen(fd, "rb") as f, open(destino, "xb") as g:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError("não é arquivo comum")
        for pedaco in iter(lambda: f.read(BLOCO), b""):
            g.write(pedaco)
            h.update(pedaco)
            total += len(pedaco)
    return total, h.hexdigest()


def aprovar(ctx, dados):
    achado = _achar(ctx, dados)
    if isinstance(achado, str):
        return {"feito": False, "mensagem": achado}
    e, p = achado
    tid = e["trabalho"]
    pasta_ap = os.path.join(ctx["dados"], "aprovados")
    destino = os.path.join(pasta_ap, tid)
    if os.path.lexists(destino):
        return {"feito": False, "codigo": 409, "mensagem": "Esta peça já foi aprovada."}
    if _marcas(ctx, tid)[1]:
        return {"feito": False, "mensagem": "Você recusou esta peça."}
    antes = selo.assinatura(p)
    s = selo.calcular(p, e["acao"], e.get("params") or {})
    if not s["ok"]:
        return {"feito": False, "mensagem": "O selo desta peça não está verde: %s" % s["linha"][:300]}
    os.makedirs(pasta_ap, mode=0o700, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".aprovando-", dir=pasta_ap)  # nome com ponto: a rota de mídia não serve
    try:
        arquivos = []
        for a in s["arquivos"]:
            n, sha = _copiar(os.path.join(p, *a["c"].split("/")), os.path.join(tmp, a["nome"]))
            arquivos.append({"nome": a["nome"], "origem": a["c"], "bytes": n, "sha256": sha})
        if selo.assinatura(p) != antes:  # algo mudou na pasta durante a cópia: não aprova o que não foi conferido
            raise OSError("a peça mudou durante a aprovação")
        params = e.get("params") or {}
        copy = selo.legenda(p) if selo.tipo(e["acao"]) == "post" else None
        manifesto = {"versao": 1, "trabalho": tid, "acao": e["acao"], "plataforma": "instagram",
                     "formato": params.get("formato") if selo.tipo(e["acao"]) == "post"
                     else FORMATO_VIDEO % params.get("duracao"),
                     "legenda": _so_a_legenda(copy) if copy else None, "copy": copy, "selo": _texto_selo(s),
                     "arquivos": arquivos, "aprovado_em": _agora()}
        with open(os.path.join(tmp, "manifesto.json"), "x", encoding="utf-8") as f:  # por último
            json.dump(manifesto, f, ensure_ascii=False, indent=1)
        os.replace(tmp, destino)  # pasta com o mesmo nome já existe: falha (POSIX e Windows)
    except Exception as erro:  # noqa: BLE001 - qualquer falha no meio: a pasta temporária some
        shutil.rmtree(tmp, ignore_errors=True)
        if os.path.lexists(destino):
            return {"feito": False, "codigo": 409, "mensagem": "Esta peça já foi aprovada."}
        return {"feito": False, "mensagem": "Não consegui aprovar: %s" % str(erro)[:200]}
    return {"feito": True, "mensagem": "Peça aprovada. Os arquivos estão na pasta de aprovados."}


def recusar(ctx, dados):
    achado = _achar(ctx, dados)
    if isinstance(achado, str):
        return {"feito": False, "mensagem": achado}
    tid = achado[0]["trabalho"]
    aprovado, recusado = _marcas(ctx, tid)
    if aprovado:
        return {"feito": False, "codigo": 409, "mensagem": "Esta peça já foi aprovada."}
    if recusado:
        return {"feito": True, "mensagem": "Esta peça já estava recusada."}
    pasta_rec = os.path.join(ctx["dados"], "recusados")
    os.makedirs(pasta_rec, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".recusando-", dir=pasta_rec)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"trabalho": tid, "recusado_em": _agora()}, f)
    os.replace(tmp, os.path.join(pasta_rec, tid + ".json"))
    return {"feito": True, "mensagem": "Peça recusada."}
