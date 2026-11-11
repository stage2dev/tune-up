"""Módulo `estudio` do painel (vem do plugin tune-up-studio; ligue com
"modulos_de_plugins": ["tune-up-studio@<marketplace>:estudio"]).

Comandos: `preparar` e, para a marca, `marca.aprovar` / `marca.editar`. A aprovação da marca é gravada
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

try:
    import fcntl
except ImportError:
    fcntl = None

INFO = {"id": "estudio", "titulo": "Estúdio", "icone": "clapperboard", "acoes": ["preparar", "marca.aprovar", "marca.editar"],
        "esquemas": {"preparar": {"confirmar": "booleano"}, "marca.aprovar": {"confirmar": "booleano"},
                     "marca.editar": {"campo": "texto", "valor": "texto"}}}
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
    amb = _ambiente(ctx["dados"]) if ctx.get("dados") else None
    if amb is None:
        return {"alertas": [{"nivel": "info", "texto": "Estúdio ainda não preparado. Use Preparar estúdio."}]}
    if amb.get("estado") == "preparando":
        return {"alertas": [{"nivel": "info", "texto": "Preparando o estúdio (desde %s). Se nada mudar em 20 min, "
                             "o Preparar parou: veja dados/ambiente.log e use Preparar estúdio de novo."
                             % amb.get("gravado_em", "")}]}
    if amb.get("pronto") is True and amb.get("estudio") != _versao():
        return {"alertas": [{"nivel": "atencao", "texto": "Estúdio preparado para a versão %s do plugin; esta é a %s. "
                             "Use Preparar estúdio de novo." % (amb.get("estudio"), _versao())}]}
    if amb.get("pronto") is True:
        return {"alertas": [{"nivel": "info", "texto": "Estúdio pronto (%s)." % amb.get("gravado_em", "")}]}
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
    caminho = os.path.join(ctx["raiz"], ".tune-up", "estudio", "marca", "marca.json")
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
    ctx["gravar_dono"]("marca", {"aprovado": True, "sha256": hashlib.sha256(m[1]).hexdigest()})
    return {"feito": True, "mensagem": "Marca aprovada."}


def _marca_editar(ctx, dados):
    sys.path.insert(0, os.path.dirname(SCRIPT))
    try:
        import cores
        import marca_leitores as ml
    finally:
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
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    os.replace(tmp, caminho)
    # a marca mudou: a aprovação anterior deixa de valer até o dono aprovar de novo
    ctx["gravar_dono"]("marca", {"aprovado": False})
    return {"feito": True, "mensagem": "Campo %s salvo e travado. Aprove a marca de novo." % campo}


def agir(ctx, acao, dados):
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
