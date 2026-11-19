"""Sandboxed action launched inside the tune-up WSL distro from the Windows panel (B3b).

Functions take the launcher's injected pieces (plataforma, rodar, sonda, ancora); no module global is swapped.
`lanc.travas_wsl` (optional dict, tests only): extra keys for argv_travas(wsl=...), such as este_arquivo/codigo.
"""
import json
import os
import posixpath
import subprocess
import time

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


def portao(lanc, cod, reg=None):
    """Gate refusal (97) of a WSL launch or resume (reg None = the launch): reset the probe, 409 with what to do."""
    if cod == PORTAO_NEGOU and (reg is None or e_wsl(reg)):
        s = sonda(lanc)
        if hasattr(s, "zerar"):
            s.zerar()
        raise ErroAcao(NAO_PRONTA % "a ponte com o Windows (interop) está ligada ou a preparação não terminou", 409)


def conferir(lanc, w, cod, out, err, pasta=None):
    """Failed WSL launch: gate refusal (97) and the folder trust prompt become a 409 with what to do.
    The per-launch work folder is already deleted and new each time: the trust command points at its
    stable parent (trabalhos). Trust inherited by subfolders is not proven here."""
    portao(lanc, cod)
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


# ---- B4: following executions per side (lado == "wsl" in the record; absent = host)

AVISO_LADO = {"host": "Não consegui ler as sessões do Claude neste computador; mostro o último estado conhecido.",
              "wsl": "Não consegui ler as sessões do Claude no WSL; mostro o último estado conhecido."}


def e_wsl(reg):
    return (reg or {}).get("lado") == "wsl"


def pastas(lanc, reg):
    """(projects dir, cwd) of a WSL execution: the distro's projects folder seen from Windows (None = not
    reachable) and the Linux cwd, so the project folder name comes from cwd_wsl. None for host records."""
    if not e_wsl(reg):
        return None
    return (getattr(lanc, "projects_wsl", None) or wsl.projects_dir_wsl)(), reg.get("cwd_wsl")


def localizar(lanc, reg, sid):
    """Transcript path of the execution on its own side, or None (WSL folder unreachable = no transcript)."""
    import transcricao
    pasta, cwd = pastas(lanc, reg) or (lanc.cfg["projects_dir"], reg.get("cwd") or lanc.cfg["workspace"])
    return None if pasta is None else transcricao.localizar(pasta, sid, cwd)


def ocioso(lanc, reg, sid, agora, agora_w=None):
    """(idle seconds, last activity on the panel clock). Host: as before. WSL: the transcript mtime comes from
    the distro clock, so idle = agora_wsl - mtime; no WSL clock = (None, None), never idle-finished."""
    import transcricao
    pasta, cwd = pastas(lanc, reg) or (lanc.cfg["projects_dir"], reg.get("cwd") or lanc.cfg["workspace"])
    ult = None if pasta is None else transcricao.ultima_atividade(pasta, sid, cwd)
    if ult is None:
        return None, None
    if not e_wsl(reg):
        return time.time() - ult, ult
    if agora_w is None:
        return None, None
    return agora_w - ult, agora - (agora_w - ult)


def _lista(cod, out):
    try:
        lista = json.loads(out) if cod == 0 else None
    except ValueError:
        lista = None
    if not isinstance(lista, list):
        return None
    return {str(a.get("id")): a for a in lista if isinstance(a, dict) and a.get("id")}


def _vivas(regs):
    """WSL executions that may still change. terminou_em/parada_pelo_painel are learned markers (the session can
    wake again: attach, a background task ending), so only `falha` (the panel stopped it for good) counts as final."""
    return any(e_wsl(r) and not r.get("falha") for r in regs)


def sem_lista(ultimo, reg, agora):
    """State when the record's side list is missing (probe not ready, list failed). Host: last seen or 'rodando',
    as before. WSL with no last seen state (panel restart): the record's markers decide, so finished runs never
    come back as 'rodando' and never fill max_execucoes."""
    if reg["id"] in ultimo or not e_wsl(reg):
        return ultimo.get(reg["id"], "rodando")
    if reg.get("falha"):
        return "parada"
    if reg.get("terminou_em") or reg.get("parada_pelo_painel"):
        from estado_exec import mapear_estado
        return mapear_estado(reg, None, agora)
    return "rodando"


def agentes_wsl(lanc, forcar=False):
    """({id: line} of `claude agents --json --all` in the distro or None, agora_wsl or None); same TTL as the host.
    Read-only listing: argv_cru as tuneup, no gate. The distro clock is read with it (idle is computed on it)."""
    with lanc._trava_agentes:
        quando, dado, agora_w = lanc.__dict__.get("_agentes_wsl") or (0.0, None, None)
        if not forcar and dado is not None and lanc.relogio() - quando < _ttl():
            return dado, agora_w
        ws = lanc.cfg["workspace"]
        cod, out, _err = lanc.rodar(wsl.argv_cru([wsl.CLAUDE_BIN, "agents", "--json", "--all"], usuario="tuneup"),
                                    ws, 20)
        dado = _lista(cod, out)
        if dado is None:
            return None, None
        agora_w = wsl.agora_wsl(lambda cmd, timeout: lanc.rodar(cmd, ws, timeout))
        lanc._agentes_wsl = (lanc.relogio(), dado, agora_w)
        return dado, agora_w


def _ttl():
    import lancador
    return lancador.TTL_AGENTES


class Lados:
    """Agents lists for one pass: each execution is matched only against its own side's list."""

    def __init__(self, lanc, regs, forcar=False):
        self.host, self.wsl, self.agora_w = lanc.agentes(forcar), {}, None
        if _vivas(regs):
            v = lanc.sonda_atual()
            pronta = isinstance(v, dict) and v.get("pronta")
            self.wsl, self.agora_w = agentes_wsl(lanc, forcar) if pronta else (None, None)

    def de(self, reg):
        return self.wsl if e_wsl(reg) else self.host

    def marcar(self, ex, reg):
        """The side whose list failed keeps the last known state (done by the caller) and gets one notice."""
        if self.de(reg) is None:
            ex["aviso"] = AVISO_LADO["wsl" if e_wsl(reg) else "host"]
        return ex


def agentes_de(lanc, reg, forcar=False):
    """Agents list of the record's side (WSL: fetched only if the probe is ready)."""
    if not e_wsl(reg):
        return lanc.agentes(forcar)
    v = lanc.sonda_atual()
    return agentes_wsl(lanc, forcar)[0] if isinstance(v, dict) and v.get("pronta") else None


def cli(lanc, reg, *args):
    """`claude stop|rm <id>` on the record's side; WSL: argv_cru as tuneup (no gate, starts no work)."""
    if e_wsl(reg):
        return wsl.argv_cru([wsl.CLAUDE_BIN] + list(args), usuario="tuneup")
    return [lanc.cfg["claude_bin"]] + list(args)


def manter(lanc, reg):
    """WSL resume starts work in the distro: the anchor must be up first (before the `claude stop`), else 409."""
    if e_wsl(reg) and not ancora(lanc).garantir():
        raise ErroAcao(NAO_PRONTA % "não consegui manter o WSL ligado", 409)


def retomar(lanc, reg, sid, texto):
    """`claude --bg --resume <sid> <texto>` on the record's side; WSL: through the gate in cwd_wsl (it starts work)."""
    if e_wsl(reg):
        return wsl.argv(reg.get("cwd_wsl") or "", [wsl.CLAUDE_BIN, "--bg", "--resume", sid, texto])
    return [lanc.cfg["claude_bin"], "--bg", "--resume", sid, texto]


def comando_attach(exec_id):
    """WSL attach command line for display (never run from this string)."""
    return subprocess.list2cmdline(wsl.argv_cru([wsl.CLAUDE_BIN, "attach", exec_id], usuario="tuneup"))
