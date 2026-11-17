"""Prepare the studio: install the pinned HyperFrames and write <dados>/ambiente.json.

Deterministic script, not an AI session. Run from a terminal or by the studio module command
(`preparar`, which passes --sim after the screen confirmed). It is the only studio step that
uses the network, and only for `npm ci --ignore-scripts` and `npm audit signatures`. No
install script runs (node/README.md: esbuild works without its postinstall). If signatures
fail, node_modules is removed so nothing unverified stays usable.

Install folder: <studio>/node, except when the studio lives under ~/.claude (the plugin
cache, which the Claude Code sandbox protects): then package.json + package-lock.json are
copied to <dados>/estudio-node/<key>/node and the install goes there (key = chave_do_ambiente(),
from package-lock.json; the panel computes the same path for {estudio_hf}). Other key folders
and the old <dados>/tune-up-studio/ folder are removed (never through a symlink).

Usage: python3 -I scripts/preparar_estudio.py --dados <pasta> [--projeto <pasta>] [--sim]
Exit code: 0 ready, 1 not ready (ambiente.json says why), 2 refused or already running.
Python 3.9+, standard library only. Report in Brazilian Portuguese.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

try:
    import fcntl
except ImportError:  # Windows: msvcrt.locking below
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verificar_ambiente as va  # noqa: E402
import saida_utf8  # noqa: E402

STUDIO = va.STUDIO
ARQUIVO, TRAVA = "ambiente.json", "ambiente.lock"
PASTA_NODE, PASTA_ANTIGA = "estudio-node", "tune-up-studio"  # em <dados>; estudio-node é do dono (travas.DONO)
ENV_HF = {"HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1", "HYPERFRAMES_NO_UPDATE_CHECK": "1",
          "HYPERFRAMES_NO_AUTO_INSTALL": "1", "HYPERFRAMES_SKIP_SKILLS": "1",
          "npm_config_update_notifier": "false", "npm_config_fund": "false"}
PASSOS = (("npm ci --ignore-scripts", ["ci", "--ignore-scripts", "--no-audit", "--no-fund"], 900),
          ("npm audit signatures", ["audit", "signatures"], 180))


def versao_do_estudio(studio=STUDIO):
    v = (va._ler_json(os.path.join(studio, ".claude-plugin", "plugin.json")) or {}).get("version")
    return v if isinstance(v, str) and v.replace(".", "").isalnum() else "0"


def _dentro(caminho, pasta):
    c, p = os.path.realpath(caminho), os.path.realpath(pasta)
    return c == p or c.startswith(p.rstrip(os.sep) + os.sep)


def chave_do_ambiente(studio=STUDIO):
    """12 hex of the sha256 of node/package-lock.json: a new pinned HyperFrames = a new key (painel/embutidos.py too)."""
    with open(os.path.join(studio, "node", "package-lock.json"), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def _limpar(dados, manter=None):
    """Remove <dados>/estudio-node/<other key> and the old <dados>/tune-up-studio/. A symlink is unlinked, never followed."""
    raiz = os.path.join(dados, PASTA_NODE)
    if os.path.islink(raiz):
        raise OSError("%s é um atalho; não instalei" % raiz)
    alvos = [os.path.join(dados, PASTA_ANTIGA)]
    alvos += [os.path.join(raiz, n) for n in (os.listdir(raiz) if os.path.isdir(raiz) else []) if n != manter]
    for alvo in alvos:
        if os.path.islink(alvo):
            os.unlink(alvo)
        elif os.path.isdir(alvo):
            shutil.rmtree(alvo, ignore_errors=True)


def pasta_node(dados, studio=STUDIO, home=None):
    """Where node_modules goes: in place, or <dados>/estudio-node/<key>/node when the studio is under ~/.claude."""
    home = home or os.path.expanduser("~")
    if not _dentro(studio, os.path.join(home, ".claude")):
        _limpar(dados)
        return os.path.join(studio, "node")
    chave = chave_do_ambiente(studio)
    _limpar(dados, chave)
    destino = os.path.join(dados, PASTA_NODE, chave, "node")
    os.makedirs(destino, exist_ok=True)
    for nome in ("package.json", "package-lock.json"):
        shutil.copyfile(os.path.join(studio, "node", nome), os.path.join(destino, nome))
    return destino


def _rodar(cmd, cwd, timeout):
    """(exit code or None, last lines of output). Output goes to a temp file, not a pipe."""
    env = dict(os.environ, **ENV_HF)
    try:
        with open(os.devnull, "rb") as nada, tempfile.TemporaryFile() as saida:
            p = subprocess.run(cmd, cwd=cwd, env=env, stdin=nada, stdout=saida, stderr=subprocess.STDOUT,
                               timeout=timeout)
            saida.seek(0)
            texto = saida.read().decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return None, "demorou mais de %d s" % timeout
    except OSError as e:
        return None, str(e)
    return p.returncode, "\n".join(texto.strip().splitlines()[-5:])[:800]


def _agora():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gravar(dados, conteudo):
    """Atomic write of <dados>/ambiente.json; a symlink in its place is refused."""
    alvo = os.path.join(dados, ARQUIVO)
    if os.path.islink(alvo):
        raise OSError("%s é um atalho; não gravei" % alvo)
    tmp = alvo + ".tmp"
    if os.path.lexists(tmp):
        os.remove(tmp)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(conteudo, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, alvo)
    return alvo


def preparar(dados, projeto, studio=STUDIO, rodar=_rodar, which=shutil.which, verificar=va.verificar,
             home=None, sistema=va.sistema):
    """Install, check and write ambiente.json. Returns the dict that was written."""
    # first thing: an interrupted run (Ctrl+C, kill, reboot) must not leave an older "pronto": true
    gravar(dados, {"versao": 1, "estudio": versao_do_estudio(studio), "gravado_em": _agora(), "pronto": False,
                   "estado": "preparando"})
    passos, pronto = [], True
    node_dir = npm = None
    if sistema()[0][0] == va.ERRO:
        pronto = False
    else:
        npm = which("npm")
        if not npm:
            passos.append({"passo": "npm", "ok": False, "codigo": None, "saida": "npm não encontrado"})
            pronto = False
    if pronto:
        node_dir = pasta_node(dados, studio, home)
        for nome, args, limite in PASSOS:
            t0 = time.monotonic()
            codigo, saida = rodar([npm] + args, node_dir, limite)
            ok = codigo == 0
            passos.append({"passo": nome, "ok": ok, "codigo": codigo,
                           "segundos": round(time.monotonic() - t0, 1), "saida": "" if ok else saida})
            if not ok:
                pronto = False
                break
        if not pronto and len(passos) == 2:  # installed but signatures failed: remove it
            shutil.rmtree(os.path.join(node_dir, "node_modules"), ignore_errors=True)
            passos[-1]["saida"] += "\nnode_modules apagado: assinaturas não conferiram"
    itens = verificar(projeto, node_dir) if node_dir else verificar(projeto)
    if any(n == va.ERRO for n, _ in itens):
        pronto = False
    bin_hf = os.path.join(node_dir, "node_modules", ".bin", "hyperframes") if node_dir else None
    conteudo = {"versao": 1, "estudio": versao_do_estudio(studio), "chave": chave_do_ambiente(studio),
                "gravado_em": _agora(), "pronto": pronto,
                "node_dir": node_dir, "hyperframes": bin_hf if bin_hf and os.path.isfile(bin_hf) else None,
                "postinstall": [], "passos": passos,
                "verificacao": [{"nivel": n, "texto": t} for n, t in itens]}
    gravar(dados, conteudo)
    return conteudo


def _travar(dados):
    """Open lock file (held) or None when another preparar runs: flock, or msvcrt.locking on Windows."""
    f = open(os.path.join(dados, TRAVA), "a")
    try:
        if fcntl is not None:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        elif msvcrt is not None:
            f.seek(0)  # mode "a" starts at the end: the locked byte must always be byte 0
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return None
    return f


def main(argv=None, entrada=input):
    saida_utf8.utf8()
    p = argparse.ArgumentParser(description="Prepara o estúdio (instala o HyperFrames fixado).")
    p.add_argument("--dados", required=True, help="pasta de dados do painel (<pacote>/dados)")
    p.add_argument("--projeto", default=os.getcwd(), help="pasta do projeto (lê .claude/settings*.json)")
    p.add_argument("--sim", action="store_true", help="não perguntar (a tela já confirmou)")
    p.add_argument("--trava-herdada", action="store_true", help=argparse.SUPPRESS)  # o módulo já trava
    args = p.parse_args(argv)
    dados = os.path.abspath(args.dados)
    if not os.path.isdir(dados) or os.path.islink(dados):
        print("Pasta de dados não existe (ou é atalho): %s" % dados)
        return 2
    if not args.sim:
        try:
            resposta = entrada("Isto baixa o HyperFrames fixado pela internet (npm, cerca de 100 MB). "
                               "Continuar? [s/N] ")
        except EOFError:
            resposta = ""
        if resposta.strip().lower() not in ("s", "sim"):
            print("Nada feito.")
            return 2
    trava = open(os.devnull) if args.trava_herdada else _travar(dados)
    if trava is None:
        print("Outro Preparar estúdio já está rodando; espere ele terminar.")
        return 2
    with trava:
        try:
            r = preparar(dados, os.path.abspath(args.projeto))
        except BaseException as e:  # Ctrl+C and bugs too: never leave an older "pronto": true behind
            motivo = str(e) or type(e).__name__
            print("Não consegui preparar: %s" % motivo)
            try:
                gravar(dados, {"versao": 1, "gravado_em": _agora(), "pronto": False, "erro": motivo[:300]})
            except OSError:
                pass
            if isinstance(e, OSError):
                return 1
            raise
    print(va.relatorio([(i["nivel"], i["texto"]) for i in r["verificacao"]]))
    for passo in r["passos"]:
        print("%s %s%s" % ("[ok]   " if passo["ok"] else "[falha]", passo["passo"],
                           "" if passo["ok"] else ": " + passo.get("saida", "")))
    print("Gravado: %s (pronto: %s)" % (os.path.join(dados, ARQUIVO), "sim" if r["pronto"] else "não"))
    return 0 if r["pronto"] else 1


if __name__ == "__main__":
    sys.exit(main())
