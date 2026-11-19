"""Parte das travas que só o processo do painel usa: a configuração do gancho e o `--settings` da sessão.

O gancho (travas.py) roda com `-I` e nunca importa este arquivo; os nomes daqui seguem importáveis de `travas`
(`travas.settings_da_sessao`, `from travas import argv_travas`).
"""
import base64
import json
import os
import posixpath
import re
import shlex
import sys

import travas
from erros import ErroAcao
from travas import NEGAR_LEVE, RISCO_LEVE

# `os` de travas, não o daqui: os testes trocam `travas.os` por um Windows simulado (ntpath) e isso tem de valer aqui


def _os():
    return travas.os


def config_gancho(acao, protegidos=(), liberados=(), perguntas_dir=None):
    trv = acao.get("_travas") or {}
    leve = acao.get("risco") in RISCO_LEVE
    # Bash no `permitir`: liga a checagem de comando composto (o PowerShell é negado sempre: não conta)
    bash = (any(re.match(r"Bash(\(|$)", r) for r in trv.get("permitir") or [])
            or any(re.fullmatch(r["ferramenta"], "Bash") for r in trv.get("regras_permitir") or []))
    conf = {"v": 1, "falha": "deny" if leve else "ask", "forte": "deny" if leve else "ask",
            "leve": leve, "bash": bash, "sb": bool(acao.get("sandbox")),
            "prot": [p for p in protegidos if p], "lib": [p for p in liberados if p],
            "n": trv.get("regras_negar") or [], "p": trv.get("regras_permitir") or []}
    est = acao.get("_estudio") or {}  # trabalho.resolver_travas: o binário exato e a pasta dos scripts do Estúdio
    if est.get("exe"):
        conf["exe"] = [x for x in est["exe"] if x]
    if est.get("py"):
        conf["py"] = est["py"]
    if perguntas_dir and acao.get("_perguntas_chat"):
        conf["perg"] = perguntas_dir  # pergunta de múltipla escolha vai para o chat, não para o terminal
    return conf


def _codificar(conf):
    bruto = json.dumps(conf, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(bruto).decode("ascii")


def settings_da_sessao(acao, protegidos=(), liberados=(), python=None, este_arquivo=None, workspace="", dados="",
                       perguntas_dir=None, wsl=None):
    """Texto JSON para `--settings`. Sem segredo: só regra, o caminho deste gancho e o bloco `sandbox`/`env`.
    `wsl` (sessão na distro): caminhos já traduzidos (_argv_wsl); o conf do gancho ganha "wsl"."""
    python = python or sys.executable or "python3"
    este_arquivo = este_arquivo or _os().path.abspath(travas.__file__)
    conf = config_gancho(acao, protegidos, liberados, perguntas_dir)
    if wsl:
        conf["wsl"] = True
    # -X utf8 (junto do -B, para o <conf> seguir no 5º pedaço): o gancho lê e escreve JSON em UTF-8 mesmo com o
    # sistema em cp1252 (Windows); sem isso, caminho com acento não casa e motivo fora do cp1252 derruba o gancho.
    comando = " ".join(shlex.quote(x) for x in (python, "-I", "-BXutf8", este_arquivo, _codificar(conf)))
    comando += " || exit 2"  # python ausente ou quebrado: código 2 bloqueia a chamada (não deixa passar)
    cfg = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": comando, "timeout": 15}]}]}}
    trv = acao.get("_travas") or {}
    import sandbox  # aqui dentro: o gancho roda com -I e não importa nada do painel
    topo, negar_sb, perm = sandbox.bloco(acao, workspace, dados, wsl=wsl)
    negar = (list(NEGAR_LEVE) if acao.get("risco") in RISCO_LEVE else []) + list(trv.get("negar") or [])
    # Windows: PowerShell negado também por regra de permissão (vale até se o gancho não rodar, sem Git Bash)
    negar += [r for r in dict.fromkeys(negar_sb + ["PowerShell"] * bool(wsl or getattr(_os(), "name", "") == "nt"))
              if r not in negar]
    if negar:
        perm["deny"] = negar
    if trv.get("permitir"):
        perm["allow"] = list(trv["permitir"])
    if perm:
        cfg["permissions"] = perm
    cfg.update(topo)
    return json.dumps(cfg, ensure_ascii=False, separators=(",", ":"))


def argv_travas(acao, cfg=None, wsl=None):
    """Pedaço do argv do `claude --bg` com as travas da ação. `wsl`: sessão na distro (ver _argv_wsl)."""
    cfg = cfg or {}
    if wsl:
        return _argv_wsl(acao, cfg, wsl)
    protegidos = [cfg.get("painel_dir"), cfg.get("pacote_dir"), cfg.get("arquivo")]
    os = _os()
    liberados = [os.path.join(cfg["pacote_dir"], "dados")] if cfg.get("pacote_dir") else []
    dados = cfg.get("dados_dir") or ""  # estes saem da exceção `dados`: só o servidor grava
    import embutidos  # aqui dentro, como o sandbox: o gancho roda com -I e não importa nada do painel
    import sandbox
    protegidos += embutidos.pastas_codigo()  # o código dos embutidos, ligados ou não: o painel importa e roda
    protegidos += [os.path.join(dados, x) for x in sandbox.DONO] if dados else []
    perguntas = os.path.join(dados, "perguntas") if dados else None
    return ["--settings", settings_da_sessao(acao, protegidos, liberados, workspace=cfg.get("workspace") or "",
                                             dados=dados, perguntas_dir=perguntas)]


def _argv_wsl(acao, cfg, w):
    """As mesmas travas para a sessão na distro: todo caminho do Windows passa por wsl.para_wsl (/mnt/<letra>/...)
    antes do gancho e do sandbox, junta com posixpath (nunca o travas.os) e o gancho roda no python3 do Linux.
    `w`: {"plugin_dir": da marca, validado de novo aqui; "chave": do Estúdio; "este_arquivo"/"codigo": opcionais,
    o travas.py e as pastas de código dos embutidos como o Windows as vê (padrão: as deste painel)}."""
    import embutidos  # aqui dentro, como no argv_travas
    import sandbox
    import wsl as ponte
    plugin = w.get("plugin_dir")
    if not ponte.plugin_dir_valido(plugin):
        raise ErroAcao("A distro tune-up indicou uma pasta do plugin que não vale. Rode de novo o instalador "
                       "(scripts\\wsl\\instalar.ps1) e tente outra vez.", 409)
    tr = ponte.para_wsl
    codigo = w["codigo"] if "codigo" in w else embutidos.pastas_codigo()
    protegidos = [tr(p) for p in [cfg.get("painel_dir"), cfg.get("pacote_dir"), cfg.get("arquivo")] + list(codigo) if p]
    dados = tr(cfg["dados_dir"]) if cfg.get("dados_dir") else ""
    protegidos += [posixpath.join(dados, x) for x in sandbox.DONO] if dados else []
    liberados = [posixpath.join(tr(cfg["pacote_dir"]), "dados")] if cfg.get("pacote_dir") else []
    if acao.get("_estudio"):  # o binário e os scripts do Estúdio do lado Linux, nunca os do Windows
        acao = dict(acao, _estudio={"exe": [ponte.caminho_hf(w.get("chave"))],
                                    "py": plugin + "/tune-up-studio/scripts/"})
    este = tr(w.get("este_arquivo") or os.path.abspath(travas.__file__))
    return ["--settings", settings_da_sessao(
        acao, protegidos, liberados, "/usr/bin/python3", este, workspace=tr(cfg["workspace"]) if cfg.get("workspace") else "",
        dados=dados, perguntas_dir=posixpath.join(dados, "perguntas") if dados else None, wsl=w)]
