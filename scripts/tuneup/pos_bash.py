"""tune-up: evento pos_bash."""
import os
import re
from .bash_parse import comando_simples, segmentos, sem_heredoc
from .mensagens import msg
from .sessao import contexto

# ---------------------------------------------------------------- pos_bash

def resposta_com_erro(r):
    if isinstance(r, dict):
        if r.get("is_error") or r.get("isError") or r.get("interrupted"):
            return True
        for k in ("exit_code", "exitCode", "returnCode", "code"):
            v = r.get(k)
            if isinstance(v, int) and v != 0:
                return True
        return False
    if isinstance(r, str):
        return r.lstrip().lower().startswith("error")
    return False


def ev_pos_bash(d, cfg):
    cmd = (d.get("tool_input") or {}).get("command")
    if not isinstance(cmd, str):
        return None
    tem = False
    limpo = re.sub(r"\\\r?\n", " ", sem_heredoc(cmd))
    for seg in segmentos(limpo):
        toks = comando_simples(seg)
        if toks and os.path.basename(toks[0]) == "gh" and toks[1:3] == ["pr", "create"]:
            tem = True
    resp = d.get("tool_response")
    if not tem or resposta_com_erro(resp):
        return None
    saida = resp.get("stdout") if isinstance(resp, dict) else resp
    if not isinstance(saida, str) or not re.search(r"github\.com/\S+/pull/\d+", saida):
        return None
    return contexto("PostToolUse", [msg("pr_aberta")])
