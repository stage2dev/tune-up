"""Sandboxed action launched inside the tune-up WSL distro from the Windows panel (B3b).

Functions take the launcher's injected pieces (plataforma, rodar, sonda, ancora); no module global is swapped.
`lanc.travas_wsl` (optional dict, tests only): extra keys for argv_travas(wsl=...), such as este_arquivo/codigo.
"""
import os
import posixpath
import subprocess

import embutidos
import wsl
import wsl_ancora
from erros import ErroAcao
from travas import argv_travas

PORTAO_NEGOU = 97  # exit code of /usr/local/bin/tune-up-exec when it refuses to run
NAO_PRONTA = ("O WSL do tune-up não está pronto (%s). Rode scripts\\wsl\\instalar.ps1 (ou "
              "scripts\\wsl\\instalar.ps1 -Login) e tente de novo.")
AVISO_PULAR = "No WSL o pular_permissoes não vale: a sessão pede as permissões de sempre."


def sonda(lanc):
    """The launcher's probe (dict, callable or wsl.Sonda); on win32 with none, one shared wsl.Sonda, lazily."""
    with lanc._trava_sonda:
        if lanc.sonda is None and lanc.plataforma == "win32":
            lanc.sonda = wsl.Sonda(plataforma=lanc.plataforma)
        return lanc.sonda


def ancora(lanc):
    """One shared anchor per launcher (injected or a real wsl_ancora.Ancora on the launcher's probe)."""
    s = sonda(lanc)
    with lanc._trava_sonda:
        if lanc.ancora is None:
            if not hasattr(s, "ler"):
                raise ErroAcao(NAO_PRONTA % "a sonda do WSL não dá para ler", 409)
            lanc.ancora = wsl_ancora.Ancora(s)
        return lanc.ancora


def preparar(lanc, acao):
    """None = host launch (not win32 or no sandbox). win32 + sandbox: the probe (blocking read) must say ready,
    else ErroAcao 409; never a host launch of a sandboxed action on Windows. {estudio_hf} is computed for the distro."""
    if lanc.plataforma != "win32" or not acao.get("sandbox"):
        return None
    s = sonda(lanc)
    v = s.ler() if hasattr(s, "ler") else s() if callable(s) else s
    v = v if isinstance(v, dict) else {}
    marcador = v.get("marcador") or {}
    if not v.get("pronta") or not marcador.get("claude_bin"):
        raise ErroAcao(NAO_PRONTA % (v.get("motivo") or "a sonda não respondeu"), 409)
    cache = lanc.__dict__.setdefault("_hf_wsl", {})

    def rodar(cmd, timeout):
        return lanc.rodar(cmd, lanc.cfg["workspace"], timeout)
    est = embutidos.estudio_da_acao(lanc.cfg, acao, hf_pronto=lambda chave: wsl.hf_pronto(rodar, chave, cache=cache))
    return {"marcador": marcador, "est": est}


def alvo(w, pasta):
    """(work folder as the session sees it, its path module) for the prompt and the travas."""
    return (wsl.para_wsl(pasta), posixpath) if w else (pasta, os.path)


def comando(lanc, w, cwd, nome, escolha, acao, prompt):
    """wsl.exe ... --cd <cwd_wsl> --exec tune-up-exec <claude> --bg ...; the prompt is the last element, as is.
    The anchor is ensured before every launch (conservative: kept up once a WSL launch happened)."""
    w["cwd_wsl"] = wsl.para_wsl(cwd)
    extra = {"plugin_dir": w["marcador"].get("plugin_dir"), "chave": (w["est"] or {}).get("chave")}
    extra.update(getattr(lanc, "travas_wsl", None) or {})
    cmd = wsl.argv(w["cwd_wsl"], [w["marcador"]["claude_bin"], "--bg", "-n", nome] + escolha
                   + argv_travas(acao, lanc.cfg, wsl=extra) + [prompt])
    if not ancora(lanc).garantir():
        raise ErroAcao(NAO_PRONTA % "não consegui manter o WSL ligado", 409)
    return cmd


def conferir(lanc, w, cod, out, err, pasta=None):
    """Failed WSL launch: gate refusal (97) and the folder trust prompt become a 409 with what to do.
    The per-launch work folder is already deleted and new each time: the trust command points at its
    stable parent (trabalhos). Trust inherited by subfolders is not proven here."""
    if cod == PORTAO_NEGOU:
        s = sonda(lanc)
        if hasattr(s, "zerar"):
            s.zerar()
        raise ErroAcao(NAO_PRONTA % "a ponte com o Windows (interop) está ligada ou a preparação não terminou", 409)
    if "not trusted" in (out + "\n" + err).lower():
        pasta_w = posixpath.dirname(w["cwd_wsl"]) if pasta else w["cwd_wsl"]
        linha = subprocess.list2cmdline(["wsl.exe", "-d", wsl.DISTRO, "--cd", pasta_w, "--exec",
                                         w["marcador"]["claude_bin"]])  # for display only, never run
        raise ErroAcao("Abra a pasta uma vez no WSL e aceite a confiança: " + linha, 409)


def avisar(lanc, w, ex):
    """WSL launch with pular_permissoes on: the flag was not applied; say so in the result."""
    if w and lanc.cfg.get("pular_permissoes"):
        ex["avisos"] = [AVISO_PULAR]
    return ex
