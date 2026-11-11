"""Check that this machine can run the studio. Report in Brazilian Portuguese.

Standard library only (Python 3.9+), no network. Checks: operating system
(macOS, Linux or WSL2; native Windows is refused), Node >= 22, the pinned
HyperFrames install (`npm ci` done in tune-up-studio/node), the headless Chrome
HyperFrames uses in its cache, ffmpeg + ffprobe with every filter and the
encoder the scripts use, bwrap and socat on Linux, and the user's sandbox keys
that add to the studio's (`excludedCommands`, `filesystem.allowWrite`,
`network.allowedDomains`): those lists merge across settings scopes, so they
widen the studio sandbox.

Usage: python3 -I scripts/verificar_ambiente.py [--projeto <pasta>]
Exit code: 0 ready (warnings allowed), 1 something is missing or blocks.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
NODE_DIR = os.path.join(STUDIO, "node")

NODE_MIN = 22  # engines of hyperframes 0.9.6
CHROME_VERSION = "152.0.7977.30"  # chrome-headless-shell pinned by hyperframes 0.9.6
# every ffmpeg filter in scripts/reserva_slides.py and scripts/qa_video.py (a test keeps this in sync)
FILTROS = ("blackdetect", "crop", "format", "freezedetect", "scale", "setpts", "setsar", "trim",
           "xfade", "zoompan")
ENCODER = "libx264"
OK, AVISO, ERRO = "ok", "aviso", "erro"
GERENCIADOS = ("/Library/Application Support/ClaudeCode/managed-settings.json",
               "/etc/claude-code/managed-settings.json")


def _rodar(cmd, timeout=20):
    """(exit code, stdout text) or (None, reason)."""
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    except OSError as e:
        return None, str(e)
    except subprocess.TimeoutExpired:
        return None, "demorou mais de %d s" % timeout
    return p.returncode, p.stdout.decode("utf-8", "replace")


def sistema(plataforma=None):
    plataforma = plataforma or sys.platform
    if plataforma == "darwin":
        return [(OK, "sistema: macOS")]
    if plataforma.startswith("linux"):
        return [(OK, "sistema: Linux (WSL2 conta como Linux)")]
    return [(ERRO, "sistema: o estúdio roda só em macOS, Linux e WSL2; no Windows, use o WSL2")]


def node(which=shutil.which, rodar=_rodar):
    exe = which("node")
    if not exe:
        return [(ERRO, "node: não encontrado; instale o Node %d ou mais novo" % NODE_MIN)]
    code, out = rodar([exe, "--version"])
    m = re.match(r"v(\d+)\.", out.strip()) if code == 0 else None
    if not m:
        return [(ERRO, "node: não consegui ler a versão (%s)" % out.strip()[:80])]
    if int(m.group(1)) < NODE_MIN:
        return [(ERRO, "node: versão %s; o HyperFrames pede %d ou mais nova" % (out.strip(), NODE_MIN))]
    return [(OK, "node: %s" % out.strip())]


def _ler_json(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def hyperframes(node_dir=NODE_DIR):
    pedido = (_ler_json(os.path.join(node_dir, "package.json")) or {}).get("dependencies", {}).get("hyperframes")
    instalado = _ler_json(os.path.join(node_dir, "node_modules", "hyperframes", "package.json"))
    cmd = "cd tune-up-studio/node && npm ci --ignore-scripts"
    if not isinstance(instalado, dict):
        return [(ERRO, "hyperframes: não instalado; rode: %s" % cmd)]
    if not pedido or instalado.get("version") != pedido:
        return [(ERRO, "hyperframes: instalado %s, fixado %s; rode: %s" % (instalado.get("version"), pedido, cmd))]
    return [(OK, "hyperframes: %s instalado" % pedido)]


def chrome(env=None, home=None):
    env = os.environ if env is None else env
    for nome in ("HYPERFRAMES_BROWSER_PATH", "PRODUCER_HEADLESS_SHELL_PATH"):
        if env.get(nome):
            if os.path.isfile(env[nome]):
                return [(AVISO, "chrome: usando %s (não é o Chrome fixado do HyperFrames)" % nome)]
            return [(ERRO, "chrome: %s aponta para um arquivo que não existe" % nome)]
    base = env.get("HYPERFRAMES_CACHE_DIR") or os.path.join(home or os.path.expanduser("~"), ".cache", "hyperframes")
    pasta = os.path.join(base, "chrome", "chrome-headless-shell")
    try:
        versoes = sorted(os.listdir(pasta))
    except OSError:
        versoes = []
    for v in versoes:
        if not v.endswith("-" + CHROME_VERSION):
            continue
        dentro = os.path.join(pasta, v)
        for sub in (sorted(os.listdir(dentro)) if os.path.isdir(dentro) else []):
            for exe in ("chrome-headless-shell", "chrome-headless-shell.exe"):
                caminho = os.path.join(dentro, sub, exe)
                if os.path.isfile(caminho) and os.access(caminho, os.X_OK):
                    return [(OK, "chrome: chrome-headless-shell %s no cache do HyperFrames" % CHROME_VERSION)]
    outra = " (há outra versão no cache: %s)" % ", ".join(versoes) if versoes else ""
    return [(ERRO, "chrome: chrome-headless-shell %s não está no cache do HyperFrames%s; "
                   "o Preparar estúdio baixa" % (CHROME_VERSION, outra))]


def nomes_de_filtros(saida):
    """Filter names from `ffmpeg -filters` (lines after the ------ separator)."""
    nomes, depois = set(), False
    for linha in saida.splitlines():
        if linha.strip().startswith("------"):
            depois = True
            continue
        partes = linha.split()
        if depois and len(partes) >= 2:
            nomes.add(partes[1])
    return nomes


def ffmpeg(which=shutil.which, rodar=_rodar):
    exe, probe = which("ffmpeg"), which("ffprobe")
    if not exe:
        return [(ERRO, "ffmpeg: não encontrado; instale o FFmpeg (com ffprobe e libx264)")]
    res = [(OK, "ffprobe: encontrado") if probe else (ERRO, "ffprobe: não encontrado; vem junto com o FFmpeg")]
    code, out = rodar([exe, "-hide_banner", "-filters"])
    if code != 0:
        return res + [(ERRO, "ffmpeg: `ffmpeg -filters` falhou (%s)" % out.strip()[:80])]
    faltam = [f for f in FILTROS if f not in nomes_de_filtros(out)]
    res.append((ERRO, "ffmpeg: faltam os filtros %s" % ", ".join(faltam)) if faltam
               else (OK, "ffmpeg: os %d filtros usados estão presentes" % len(FILTROS)))
    code, out = rodar([exe, "-hide_banner", "-encoders"])
    tem = code == 0 and re.search(r"^\s*\S+\s+%s\s" % ENCODER, out, re.M)
    res.append((OK, "ffmpeg: encoder %s presente" % ENCODER) if tem
               else (ERRO, "ffmpeg: falta o encoder %s (a reserva em slides precisa dele)" % ENCODER))
    return res


def sandbox_linux(plataforma=None, which=shutil.which):
    if not (plataforma or sys.platform).startswith("linux"):
        return []
    return [(OK, "%s: encontrado" % p) if which(p) else
            (ERRO, "%s: não encontrado; o sandbox do Claude Code no Linux precisa dele" % p)
            for p in ("bwrap", "socat")]


def arquivos_de_settings(projeto, home):
    lista = [os.path.join(home, ".claude", "settings.json")]
    if projeto:
        lista += [os.path.join(projeto, ".claude", "settings.json"),
                  os.path.join(projeto, ".claude", "settings.local.json")]
    return lista + list(GERENCIADOS)


def _lista(d, *chaves):
    for c in chaves:
        d = d.get(c) if isinstance(d, dict) else None
    return [x for x in d if isinstance(x, str)] if isinstance(d, list) else []


def sandbox_do_usuario(projeto=None, home=None):
    """excludedCommands and allowedDomains block (the studio is offline and fully sandboxed);
    allowWrite warns (sandboxed commands can write there too)."""
    home = home or os.path.expanduser("~")
    res = []
    for arq in arquivos_de_settings(projeto, home):
        if not os.path.exists(arq):
            continue
        dados = _ler_json(arq)
        if not isinstance(dados, dict):
            res.append((AVISO, "settings: não consegui ler %s; as chaves de sandbox dele não foram conferidas" % arq))
            continue
        sb = dados.get("sandbox")
        fora = _lista(sb, "excludedCommands")
        if fora:
            res.append((ERRO, "settings %s: sandbox.excludedCommands (%s) roda esses comandos fora do sandbox "
                              "nas sessões do estúdio; tire a chave" % (arq, ", ".join(fora)[:120])))
        dominios = _lista(sb, "network", "allowedDomains")
        if dominios:
            res.append((ERRO, "settings %s: sandbox.network.allowedDomains (%s) abre rede nas sessões do "
                              "estúdio, que roda sem rede; tire a chave" % (arq, ", ".join(dominios)[:120])))
        escrita = _lista(sb, "filesystem", "allowWrite")
        if escrita:
            res.append((AVISO, "settings %s: sandbox.filesystem.allowWrite (%s) também vale nas sessões do "
                               "estúdio" % (arq, ", ".join(escrita)[:120])))
    return res or [(OK, "settings: nenhuma chave de sandbox do usuário amplia o estúdio")]


def verificar(projeto=None):
    return (sistema() + node() + hyperframes() + chrome() + ffmpeg() + sandbox_linux()
            + sandbox_do_usuario(projeto))


def relatorio(itens):
    marca = {OK: "[ok]   ", AVISO: "[aviso]", ERRO: "[falta]"}
    linhas = ["%s %s" % (marca[n], t) for n, t in itens]
    erros = sum(1 for n, _ in itens if n == ERRO)
    linhas.append("Pronto para o estúdio." if not erros else
                  "Não está pronto: %d item(ns) acima precisam de ajuste." % erros)
    return "\n".join(linhas)


def main(argv=None):
    p = argparse.ArgumentParser(description="Confere se esta máquina roda o estúdio.")
    p.add_argument("--projeto", default=os.getcwd(), help="pasta do projeto (lê .claude/settings*.json)")
    args = p.parse_args(argv)
    itens = verificar(os.path.abspath(args.projeto))
    print(relatorio(itens))
    return 1 if any(n == ERRO for n, _ in itens) else 0


if __name__ == "__main__":
    sys.exit(main())
