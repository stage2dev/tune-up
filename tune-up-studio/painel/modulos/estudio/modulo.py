"""Módulo `estudio` do painel (vem do plugin tune-up-studio; ligue com
"modulos_de_plugins": ["tune-up-studio@<marketplace>:estudio"]).

Abas: Novo, Fila, Galeria, Aprovação (pecas.py; selo do servidor em selo.py), Marca e Ambiente (telas.py).
Comandos: `preparar`; para a marca, `marca.aprovar` (exige o sha256 curto mostrado na tela) / `marca.editar` /
`marca.redescobrir`; para as peças, `peca.aprovar` / `peca.recusar`. A aprovação da marca é gravada
aqui (ctx["gravar_dono"] -> estudio-dono.json); as skills de marca só leem. `preparar`: roda scripts/preparar_estudio.py em segundo plano (npm ci
leva mais que os 20 s de agir) e a tela mostra o <dados>/ambiente.json. O comando exige
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
    import pecas
    import telas
finally:
    sys.path.remove(os.path.dirname(os.path.realpath(__file__)))

try:
    import fcntl
except ImportError:
    fcntl = None

PECA = {"trabalho": "texto", "confirmar": "booleano"}
INFO = {"id": "estudio", "titulo": "Estúdio", "icone": "clapperboard", "midia": ["trabalhos", "aprovados"],
        "acoes": ["preparar", "marca.aprovar", "marca.editar", "marca.redescobrir", "peca.aprovar", "peca.recusar"],
        "esquemas": {"preparar": {"confirmar": "booleano"}, "marca.aprovar": {"confirmar": "booleano", "sha256": "texto"},
                     "marca.editar": {"campo": "texto", "valor": "texto"}, "marca.redescobrir": {"confirmar": "booleano"},
                     "peca.aprovar": PECA, "peca.recusar": PECA}}
REL_MARCA = ".tune-up/estudio/marca/marca.json"
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))), "scripts", "preparar_estudio.py")


def _ambiente(dados):
    try:
        with open(os.path.join(dados, "ambiente.json"), encoding="utf-8") as f:
            r = json.load(f)
        return r if isinstance(r, dict) else None
    except (OSError, ValueError):
        return None


def _versao():
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(SCRIPT)), ".claude-plugin", "plugin.json"),
                  encoding="utf-8") as f:
            return json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        return None


def montar(ctx):
    r = _montar_ambiente(ctx)
    m = _marca(ctx)
    sha = hashlib.sha256(m[1]).hexdigest() if m else ""  # o dono aprova o que vê; o sha256 prende a estes bytes
    falta = ctx.get("dono_faltando")
    aprovada = m is not None and callable(falta) and not falta(["estudio.marca"])
    lista = pecas.pecas(ctx)
    ambiente = [{"tipo": "texto", "texto": a["texto"]} for a in r["alertas"]]
    ambiente.append({"tipo": "formulario", "titulo": "Preparar estúdio", "acao": "preparar", "botao": "Preparar",
                     "campos": [], "dados_fixos": {"confirmar": True},
                     "confirmar": "Isto baixa o HyperFrames pela internet (cerca de 100 MB). Continuar?"})
    amb = _ambiente(ctx["dados"]) if ctx.get("dados") else None
    pronto = bool(amb) and amb.get("pronto") is True and amb.get("estudio") == _versao()
    # na ordem do fluxo: preparar, aprovar a marca, pedir, acompanhar, ver e aprovar
    r["abas"] = [{"id": "ambiente", "titulo": "1. Ambiente", "blocos": ambiente},
                 {"id": "marca", "titulo": "2. Marca", "blocos": telas.aba_marca(m, sha, aprovada)},
                 {"id": "novo", "titulo": "3. Novo", "blocos": telas.aba_novo(ctx, aprovada, pronto)},
                 {"id": "fila", "titulo": "Fila", "blocos": pecas.aba_fila(lista)},
                 {"id": "galeria", "titulo": "Galeria", "blocos": pecas.aba_galeria(lista)},
                 {"id": "aprovacao", "titulo": "Aprovação", "blocos": pecas.aba_aprovacao(lista)}]
    return r


def _montar_ambiente(ctx):
    amb = _ambiente(ctx["dados"]) if ctx.get("dados") else None
    if amb is None:
        return {"alertas": [{"nivel": "info", "texto": "Passo 1 de 3: o estúdio ainda não foi preparado. "
                                         "Abra a aba 1. Ambiente e use Preparar."}]}
    if amb.get("estado") == "preparando":
        return {"alertas": [{"nivel": "info", "texto": "Preparando o estúdio (desde %s). Se nada mudar em 20 min, "
                             "o Preparar parou: veja dados/ambiente.log e use Preparar estúdio de novo."
                             % amb.get("gravado_em", "")}]}
    if amb.get("pronto") is True and amb.get("estudio") != _versao():
        return {"alertas": [{"nivel": "atencao", "texto": "Estúdio preparado para a versão %s do plugin; esta é a %s. "
                             "Use Preparar estúdio de novo." % (amb.get("estudio"), _versao())}]}
    if amb.get("pronto") is True:
        return {"alertas": [{"nivel": "info", "texto": "Estúdio pronto."}]}
    faltas = [i.get("texto", "") for i in amb.get("verificacao") or [] if isinstance(i, dict) and i.get("nivel") == "erro"]
    faltas += ["%s falhou" % p.get("passo", "") for p in amb.get("passos") or [] if isinstance(p, dict) and not p.get("ok")]
    if amb.get("erro"):
        faltas.append(str(amb["erro"]))
    return {"alertas": [{"nivel": "atencao", "texto": "Estúdio não está pronto: " + "; ".join(faltas)[:450]}]}


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


def _marca(ctx):
    """(caminho, texto, objeto) of <raiz>/.tune-up/estudio/marca/marca.json, or None."""
    if not ctx.get("raiz"):
        return None
    caminho = os.path.join(ctx["raiz"], *REL_MARCA.split("/"))
    try:
        if os.path.islink(caminho):
            return None
        with open(caminho, "rb") as f:
            bruto = f.read()
        obj = json.loads(bruto.decode("utf-8"))
    except (OSError, ValueError):
        return None
    return (caminho, bruto, obj) if isinstance(obj, dict) and isinstance(obj.get("campos"), dict) else None


def _marca_aprovar(ctx, dados):
    if dados.get("confirmar") is not True:
        return {"feito": False, "mensagem": "Confirme que a marca mostrada está certa."}
    m = _marca(ctx)
    if m is None:
        return {"feito": False, "mensagem": "Ainda não há marca descoberta. Rode a skill de marca antes."}
    curto = dados.get("sha256")
    if not isinstance(curto, str) or len(curto) < 12 or not hashlib.sha256(m[1]).hexdigest().startswith(curto.lower()):
        return {"feito": False, "mensagem": "A marca mudou depois que a tela abriu. Atualize e confira de novo."}
    # dono.faltando confere o sha256 do arquivo no disparo: marca trocada depois disto perde a aprovação
    ctx["gravar_dono"]("marca", {"aprovado": True, "sha256": hashlib.sha256(m[1]).hexdigest(), "arquivo": REL_MARCA})
    return {"feito": True, "mensagem": "Marca aprovada."}


def _marca_editar(ctx, dados):
    sys.path.insert(0, os.path.dirname(SCRIPT))
    try:
        import cores
        import descobrir_marca as dm
        import marca_leitores as ml
    finally:  # descobrir_marca também se põe no sys.path ao ser importado: tira todas as entradas
        while os.path.dirname(SCRIPT) in sys.path:
            sys.path.remove(os.path.dirname(SCRIPT))
    campo, valor = dados.get("campo"), (dados.get("valor") or "").strip()
    if campo not in ml.CAMPOS or not valor or len(valor) > 200 or "\n" in valor:
        return {"feito": False, "mensagem": "Campo ou valor inválido."}
    if campo.startswith("cores."):
        valor = cores.para_hex(valor)
        if valor is None:
            return {"feito": False, "mensagem": "Não entendi essa cor. Use um valor como #1A2B3C."}
    m = _marca(ctx)
    if m is None:
        return {"feito": False, "mensagem": "Ainda não há marca descoberta. Rode a skill de marca antes."}
    caminho, _, obj = m
    obj["campos"][campo] = {"valor": valor, "fonte": "dono", "confianca": "alta", "travado": True}
    if campo == "logo":  # a cópia antiga não é mais o logo do dono: some, e entra a nova se o arquivo existe
        assets = os.path.join(os.path.dirname(caminho), "assets")
        for n in os.listdir(assets) if os.path.isdir(assets) and not os.path.islink(assets) else []:
            if n.lower().startswith("logo."):
                os.remove(os.path.join(assets, n))
        obj["logo_copia"] = dm.copiar_logo(ctx["raiz"], os.path.dirname(caminho), obj["campos"]["logo"])
    dm._gravar(caminho, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")  # O_EXCL|O_NOFOLLOW no .tmp
    # a marca mudou: a aprovação anterior deixa de valer até o dono aprovar de novo
    ctx["gravar_dono"]("marca", {"aprovado": False})
    return {"feito": True, "mensagem": "Campo %s salvo e travado. Aprove a marca de novo." % campo}


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
        return pecas.aprovar(ctx, dados)
    if acao == "peca.recusar":
        return pecas.recusar(ctx, dados)
    if acao == "marca.redescobrir":
        return _marca_redescobrir(ctx, dados)
    if acao == "marca.aprovar":
        return _marca_aprovar(ctx, dados)
    if acao == "marca.editar":
        return _marca_editar(ctx, dados)
    if acao != "preparar":
        return {"feito": False, "mensagem": "Ação desconhecida."}
    if dados.get("confirmar") is not True:
        return {"feito": False, "mensagem": "Confirme: isto baixa o HyperFrames pela internet (cerca de 100 MB)."}
    pasta = ctx.get("dados")
    if not pasta:
        return {"feito": False, "mensagem": "Este projeto não tem pasta de dados do painel."}
    os.makedirs(pasta, exist_ok=True)
    trava = _travar(pasta)
    if trava is None:
        return {"feito": False, "mensagem": "O Preparar estúdio já está rodando. Espere terminar."}
    # o filho herda a trava (pass_fds) e a segura até terminar: um segundo clique cai acima
    with trava, open(os.path.join(pasta, "ambiente.log"), "wb") as log, open(os.devnull, "rb") as nada:
        subprocess.Popen([sys.executable, "-I", SCRIPT, "--dados", pasta, "--projeto", ctx.get("raiz") or pasta,
                          "--sim", "--trava-herdada"], stdin=nada, stdout=log, stderr=subprocess.STDOUT,
                         cwd=pasta, start_new_session=True, pass_fds=(trava.fileno(),))
    return {"feito": True, "mensagem": "Preparando o estúdio em segundo plano. Atualize a tela para ver o resultado."}
