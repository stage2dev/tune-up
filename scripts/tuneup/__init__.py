"""tune-up: pacote da guarda dos hooks do núcleo (entrada em scripts/guarda.py).

Reexporta os nomes públicos dos módulos para quem ainda lê `guarda.<nome>`.
"""
import json
import os
import sys

from .sessao import *  # noqa: F401,F403
from .config import *  # noqa: F401,F403
from .prompt import *  # noqa: F401,F403
from .bash_parse import *  # noqa: F401,F403
from .mensagens import *  # noqa: F401,F403
from .escrita import *  # noqa: F401,F403
from .sql_prod import *  # noqa: F401,F403
from .bash import *  # noqa: F401,F403
from .agent import *  # noqa: F401,F403
from .pos_bash import *  # noqa: F401,F403
from .usuario import *  # noqa: F401,F403
from .agent import ev_agent
from .bash import ev_bash
from .config import TESTE, carregar_config, confiar
from .info import roda_info
from .mensagens import definir_idioma, msg
from .escrita import ev_escrita
from .pos_bash import ev_pos_bash
from .prompt import ev_prompt
from .sessao import emitir, ev_inicio, log_erro
from .sql_prod import ev_prod

# ---------------------------------------------------------------- main

EVENTOS = {"prompt": ev_prompt, "inicio": ev_inicio, "bash": ev_bash, "agent": ev_agent,
           "escrita": ev_escrita, "prod": ev_prod, "pos_bash": ev_pos_bash}


def main():
    evento = sys.argv[1] if len(sys.argv) > 1 else ""
    if evento in ("confiar", "trust"):  # never reads stdin
        try:
            confiar(sys.argv[2])
        except Exception as e:
            log_erro(evento, "%s: %s" % (type(e).__name__, e))
            print(msg("confiar_falhou", e))
        return
    if evento == "info":  # never reads stdin
        try:
            roda_info()
        except Exception as e:
            log_erro(evento, "%s: %s" % (type(e).__name__, e))
        return
    try:
        bruto = sys.stdin.read()
        try:
            d = json.loads(bruto)
        except ValueError:
            log_erro(evento, "stdin is not JSON")
            return
        if not isinstance(d, dict) or evento not in EVENTOS:
            log_erro(evento, "invalid event or input")
            return
        if TESTE and os.environ.get("TUNEUP_FAKE_EXCECAO") == "1":
            raise RuntimeError("simulated exception")
        cfg = carregar_config(d.get("cwd"))
        definir_idioma(cfg)
        saida = EVENTOS[evento](d, cfg)
        if saida:
            emitir(saida)
    except Exception as e:
        log_erro(evento, "%s: %s" % (type(e).__name__, e))
