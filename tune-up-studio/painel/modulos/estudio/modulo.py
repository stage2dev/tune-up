"""Módulo `estudio` do painel (vem do plugin tune-up-studio; ligue com
"modulos_de_plugins": ["tune-up-studio@<marketplace>:estudio"]).

Abas: Novo, Fila, Galeria, Aprovação (pecas.py; selo do servidor em selo.py), Marca e Ambiente (telas.py).
Comandos: `preparar`; para a marca, `marca.aprovar` (exige o sha256 curto que vai escondido no botão) /
`marca.redescobrir` e os da tela de marca (marca_acoes.py; `envio.recebido` só o servidor chama, depois de
gravar um envio de INFO["envios"]); para as peças, `peca.aprovar` / `peca.recusar`. A aprovação da marca é gravada
aqui (ctx["gravar_dono"] -> estudio-dono.json); as skills de marca só leem. `preparar`: roda scripts/preparar_estudio.py em segundo plano (npm ci
leva mais que os 20 s de agir) e a tela mostra o <dados_dir>/ambiente.json (pronto = mesma chave do package-lock). O comando exige
{"confirmar": true}: é o único passo do estúdio com rede (risco `codigo`).
Python 3.9, só biblioteca padrão.
"""
import hashlib
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))  # irmãos; o painel já põe e depois tira esta pasta
try:
    import marca_acoes
    import pecas
    import telas
finally:
    sys.path.remove(os.path.dirname(os.path.realpath(__file__)))

try:
    import fcntl
except ImportError:
    fcntl = None

PECA = {"trabalho": "texto", "confirmar": "booleano"}
CAMPO = {"campo": "texto", "valor": "texto"}
TIPOS_IMAGEM = ["png", "jpeg", "webp"]
# logo e fotos que o dono envia moram ao lado do marca.json (<raiz>/.tune-up/estudio/marca/)
MARCA_ASSETS = {"pasta": "estudio/marca/assets", "base": "tune-up"}
MARCA_FOTOS = {"pasta": "estudio/marca/fotos", "base": "tune-up"}
INFO = {"id": "estudio", "titulo": "Estúdio", "icone": "clapperboard",
        "midia": ["trabalhos", "aprovados", MARCA_ASSETS, MARCA_FOTOS],
        "baixar": ["aprovados"],  # a planilha do anúncio (.csv) sai como download, só depois de aprovada
        "envios": {"logo": dict(MARCA_ASSETS, tipos=TIPOS_IMAGEM, max_bytes=5000000, max_arquivos=10, gancho=True),
                   "fotos": dict(MARCA_FOTOS, tipos=TIPOS_IMAGEM, max_bytes=8 * 1024 * 1024,
                                 max_arquivos=marca_acoes.MAX_FOTOS, gancho=True)},
        "acoes": ["preparar", "marca.aprovar", "marca.editar", "marca.redescobrir", "marca.sem_logo",
                  "marca.cores_da_logo", "marca.letras", "marca.tom", "marca.remover_foto",
                  "peca.aprovar", "peca.recusar"],
        "esquemas": {"preparar": {"confirmar": "booleano"}, "marca.aprovar": {"confirmar": "booleano", "sha256": "texto"},
                     "marca.editar": CAMPO, "marca.redescobrir": {"confirmar": "booleano"},
                     "marca.sem_logo": {"confirmar": "booleano"}, "marca.cores_da_logo": {}, "marca.letras": CAMPO,
                     "marca.tom": dict(CAMPO, ligado="booleano"),
                     "marca.remover_foto": {"destino": "texto", "arquivo": "texto"},
                     "peca.aprovar": PECA, "peca.recusar": PECA}}
# o estúdio pede o sandbox do Claude Code, que no Windows só existe dentro do WSL2 preparado (o catálogo já esconde as ações)
SO_WSL2 = "As ações do estúdio pedem o WSL2. Rode scripts\\wsl\\instalar.ps1 (pasta do plugin) e recarregue."
REL_MARCA = marca_acoes.REL_MARCA
SCRIPT = os.path.join(marca_acoes.SCRIPTS, "preparar_estudio.py")
COMANDOS = {"envio.recebido": marca_acoes.recebido, "marca.editar": marca_acoes.editar,
            "marca.sem_logo": marca_acoes.sem_logo, "marca.cores_da_logo": marca_acoes.cores_da_logo,
            "marca.letras": marca_acoes.letras, "marca.tom": marca_acoes.tom,
            "marca.remover_foto": marca_acoes.remover_foto}


def _windows():
    return os.name == "nt"


def _wsl(ctx):
    """(marca, motivo): marca = the probe's marker when on Windows with a ready distro, else None + the reason."""
    if not _windows():
        return None, ""
    v = ctx.get("sonda")
    v = v() if callable(v) else v
    if isinstance(v, dict) and v.get("pronta") is True and isinstance(v.get("marcador"), dict):
        return v["marcador"], ""
    return None, str(v.get("motivo") or "") if isinstance(v, dict) else "WSL não conferido"


def _recusa_wsl(motivo):
    return SO_WSL2 + (" (%s)" % motivo.rstrip(".") if motivo else "")


def _ffprobe_wsl(ctx):
    """callable(video, pasta, tempo) -> (codigo, saida, erro) running the distro's ffprobe, for selo.py."""
    w, rodar = ctx["wsl"], ctx["wsl_rodar"]

    def f(video, pasta, tempo):
        cmd = w.argv(w.para_wsl(pasta), ["/usr/local/bin/ffprobe", "-v", "error", "-print_format", "json",
                                          "-count_frames", "-show_streams", "-show_format", w.para_wsl(video)])
        return rodar(cmd, tempo)
    return f


def _com_wsl(ctx):
    return dict(ctx, ffprobe_wsl=_ffprobe_wsl(ctx)) if _wsl(ctx)[0] is not None else ctx


def _ambiente(dados):
    try:
        with open(os.path.join(dados, "ambiente.json"), encoding="utf-8") as f:
            r = json.load(f)
        return r if isinstance(r, dict) else None
    except (OSError, ValueError):
        return None


def _chave():
    """A do preparar_estudio.chave_do_ambiente(): 12 hex do sha256 do package-lock.json do estúdio."""
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(SCRIPT)), "node", "package-lock.json"), "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]
    except OSError:
        return None


def _mesma_chave(amb):
    chave = _chave()
    return chave is not None and amb.get("chave") == chave


def _pasta(ctx):
    """A pasta de dados do painel (cfg["dados_dir"]); ctx sem ela (chamada direta) usa ctx["dados"]."""
    return ctx.get("dados_dir") or ctx.get("dados")


def montar(ctx):
    marca, motivo = _wsl(ctx)
    ctx = _com_wsl(ctx)
    r = _montar_ambiente(ctx)
    m = _marca(ctx)
    sha = hashlib.sha256(m[1]).hexdigest() if m else ""  # o dono aprova o que vê; o sha256 prende a estes bytes
    falta = ctx.get("dono_faltando")
    aprovada = m is not None and callable(falta) and not falta(["estudio.marca"])
    lista = pecas.pecas(ctx)
    amb = _ambiente(_pasta(ctx)) if _pasta(ctx) else None
    pronto = bool(amb) and amb.get("pronto") is True and _mesma_chave(amb)
    if marca is not None:  # Windows: the ready flag is the hyperframes inside the distro, not ambiente.json
        pronto = _hf_pronto(ctx)
    texto = r["alertas"][0]["texto"] if amb else ("Clique em Preparar. O estúdio baixa as ferramentas dele "
                                                  "(cerca de 100 MB), uma vez só.")
    ambiente = [{"tipo": "texto", "titulo": "Passo 1 de 3: preparar o estúdio", "texto": texto}
                | ({"ir_para": {"aba": "marca", "rotulo": "Ir para 2. Marca"}} if pronto else {})]
    if pronto and aprovada:  # tudo pronto: nenhum aviso no topo de toda aba (nem número no menu)
        r["alertas"], ambiente[0]["texto"] = [], "Estúdio pronto."
    ambiente.append({"tipo": "formulario", "titulo": "Preparar estúdio", "acao": "preparar", "botao": "Preparar",
                     "campos": [], "dados_fixos": {"confirmar": True},
                     "confirmar": "Isto baixa o HyperFrames pela internet (cerca de 100 MB). Continuar?"})
    # na ordem do fluxo: preparar, aprovar a marca, pedir, acompanhar, ver e aprovar
    r["abas"] = [{"id": "ambiente", "titulo": "1. Ambiente", "blocos": ambiente},
                 {"id": "marca", "titulo": "2. Marca", "blocos": telas.aba_marca(m, sha, aprovada)},
                 {"id": "novo", "titulo": "3. Novo", "blocos": telas.aba_novo(ctx, aprovada, pronto)},
                 {"id": "fila", "titulo": "Fila", "blocos": pecas.aba_fila(lista)},
                 {"id": "galeria", "titulo": "Galeria", "blocos": pecas.aba_galeria(lista)},
                 {"id": "aprovacao", "titulo": "Aprovação", "blocos": pecas.aba_aprovacao(lista, ctx)}]
    if _windows() and marca is None:  # nada de Preparar nem de pedir peça: uma linha só
        r["alertas"] = [{"nivel": "atencao", "texto": _recusa_wsl(motivo)}]
        for aba in (r["abas"][0], r["abas"][2]):
            aba["blocos"] = [{"tipo": "texto", "titulo": "Estúdio", "texto": _recusa_wsl(motivo)}]
    return r


def _hf_pronto(ctx):
    chave = _chave()
    try:
        return chave is not None and ctx["wsl"].hf_pronto(ctx["wsl_rodar"], chave) is True
    except Exception:  # noqa: BLE001 - a broken check is "not ready", never a crash of the screen
        return False


def _montar_ambiente(ctx):
    amb = _ambiente(_pasta(ctx)) if _pasta(ctx) else None
    if amb is None:
        return {"alertas": [{"nivel": "info", "texto": "O estúdio ainda não foi preparado. "
                                         "Abra a aba 1. Ambiente e use Preparar."}]}
    if amb.get("estado") == "preparando":
        return {"alertas": [{"nivel": "info", "texto": "Preparando o estúdio%s. Leva alguns minutos; a tela se "
                             "atualiza sozinha. Se nada mudar em 20 min, use Preparar de novo." % _desde(amb)}]}
    if amb.get("pronto") is True and not _mesma_chave(amb):
        return {"alertas": [{"nivel": "atencao", "texto": "O estúdio foi preparado para outra versão das ferramentas "
                             "dele. Use Preparar de novo."}]}
    if amb.get("pronto") is True:
        return {"alertas": [{"nivel": "info", "texto": "Estúdio pronto. Próximo passo: aprovar a marca."}]}
    faltas = [i.get("texto", "") for i in amb.get("verificacao") or [] if isinstance(i, dict) and i.get("nivel") == "erro"]
    faltas += ["%s falhou" % p.get("passo", "") for p in amb.get("passos") or [] if isinstance(p, dict) and not p.get("ok")]
    if amb.get("erro"):
        faltas.append(str(amb["erro"]))
    return {"alertas": [{"nivel": "atencao", "texto": "Estúdio não está pronto: " + "; ".join(faltas)[:450]}]}


def _desde(amb):
    """" desde as 08:23" de um ISO gravado_em, ou "" (nada de data técnica na tela)."""
    m = pecas.RE_DATA.match(str(amb.get("gravado_em") or ""))
    return " desde as %s:%s" % m.groups()[2:] if m else ""


def _travar(dados):
    """Lock file held by this process (the child inherits it), or None when a preparar runs."""
    f = open(os.path.join(dados, "ambiente.lock"), "a")
    if fcntl is not None:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return None
    return f


_marca = marca_acoes.ler


def _marca_aprovar(ctx, dados):
    if dados.get("confirmar") is not True:
        return {"feito": False, "mensagem": "Confirme que a marca mostrada está certa."}
    m = _marca(ctx)
    if m is None:
        return {"feito": False, "mensagem": "Ainda não há marca. Use Procurar de novo no meu projeto."}
    curto = dados.get("sha256")
    if not isinstance(curto, str) or len(curto) < 12 or not hashlib.sha256(m[1]).hexdigest().startswith(curto.lower()):
        return {"feito": False, "mensagem": "A marca mudou depois que a tela abriu. Confira de novo e confirme."}
    # dono.faltando confere o sha256 do arquivo no disparo: marca trocada depois disto perde a aprovação
    ctx["gravar_dono"]("marca", {"aprovado": True, "sha256": hashlib.sha256(m[1]).hexdigest(), "arquivo": REL_MARCA})
    return {"feito": True, "mensagem": "Marca confirmada. Já dá para criar peças na aba 3. Novo."}


def _marca_redescobrir(ctx, dados):
    if dados.get("confirmar") is not True or not ctx.get("raiz"):
        return {"feito": False, "mensagem": "Confirme que quer ler o projeto de novo."}
    try:  # determinístico, sem rede: campos travados pelo dono ficam
        p = subprocess.run([sys.executable, "-I", os.path.join(os.path.dirname(SCRIPT), "descobrir_marca.py"),
                            "--projeto", ctx["raiz"]], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=15)
    except subprocess.TimeoutExpired:
        return {"feito": False, "mensagem": "Ler a marca demorou demais."}
    ctx["gravar_dono"]("marca", {"aprovado": False})
    texto = p.stdout.decode("utf-8", "replace").strip()[:300]
    return {"feito": p.returncode == 0, "mensagem": ("Marca lida de novo (%s). Confira e aprove." if p.returncode == 0
                                                     else "Não consegui ler a marca: %s") % texto}


def agir(ctx, acao, dados):
    if acao == "peca.aprovar":
        return pecas.aprovar(_com_wsl(ctx), dados)
    if acao == "peca.recusar":
        return pecas.recusar(ctx, dados)
    if acao == "marca.redescobrir":
        return _marca_redescobrir(ctx, dados)
    if acao == "marca.aprovar":
        return _marca_aprovar(ctx, dados)
    if acao in COMANDOS:
        return COMANDOS[acao](ctx, dados)
    if acao != "preparar":
        return {"feito": False, "mensagem": "Ação desconhecida."}
    marca, motivo = _wsl(ctx)
    if _windows() and marca is None:  # Popen(pass_fds=...) quebra no Windows; nada é gravado em disco
        return {"feito": False, "mensagem": _recusa_wsl(motivo)}
    if dados.get("confirmar") is not True:
        return {"feito": False, "mensagem": "Confirme: isto baixa o HyperFrames pela internet (cerca de 100 MB)."}
    pasta = _pasta(ctx)
    if not pasta:
        return {"feito": False, "mensagem": "Este projeto não tem pasta de dados do painel."}
    if marca is not None:
        return _preparar_wsl(ctx, marca, pasta)
    os.makedirs(pasta, exist_ok=True)
    trava = _travar(pasta)
    if trava is None:
        return {"feito": False, "mensagem": "O Preparar estúdio já está rodando. Espere terminar."}
    # o filho herda a trava (pass_fds) e a segura até terminar: um segundo clique cai acima
    with trava, open(os.path.join(pasta, "ambiente.log"), "wb") as log, open(os.devnull, "rb") as nada:
        subprocess.Popen([sys.executable, "-I", SCRIPT, "--dados", pasta, "--projeto", ctx.get("raiz") or pasta,
                          "--sim", "--trava-herdada"], stdin=nada, stdout=log, stderr=subprocess.STDOUT,
                         cwd=pasta, start_new_session=True, pass_fds=(trava.fileno(),))
    return {"feito": True, "mensagem": "Preparando o estúdio. Leva alguns minutos; a tela se atualiza sozinha."}



def _preparar_wsl(ctx, marca, pasta):
    """Windows + ready distro: run the Prepare script inside it (its own lock lives in WSL; no pass_fds here)."""
    w = ctx["wsl"]
    plugin = marca.get("plugin_dir")
    if not w.plugin_dir_valido(plugin):
        return {"feito": False, "mensagem": "A marca do WSL aponta para uma pasta do plugin inválida. "
                                            "Rode scripts\\wsl\\instalar.ps1 de novo."}
    try:
        cmd = w.argv(w.para_wsl(pasta), ["/usr/bin/python3", "-I", plugin + "/tune-up-studio/scripts/preparar_estudio.py",
                                         "--dados", w.para_wsl(pasta), "--projeto", w.para_wsl(ctx.get("raiz") or pasta),
                                         "--sim"])
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, "ambiente.log"), "wb") as log:
            subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                             creationflags=w.CREATE_NO_WINDOW)
    except (w.ErroAcao, OSError) as e:
        return {"feito": False, "mensagem": "Não consegui iniciar o Preparar no WSL: %s" % str(e)[:200]}
    return {"feito": True, "mensagem": "Preparando o estúdio. Leva alguns minutos; a tela se atualiza sozinha."}
