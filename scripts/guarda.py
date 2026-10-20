#!/usr/bin/env python3
"""tune-up: guarda dos hooks do núcleo.

Uso: python3 guarda.py <prompt|inicio|bash|agent|escrita|prod|pos_bash>
     python3 guarda.py info                  (JSON do perfil; não lê stdin)
     python3 guarda.py confiar|trust <arq>   (não lê stdin)
Lê o JSON do hook no stdin, escreve JSON no stdout quando há decisão.
Sempre sai com código 0. Exceção interna = não decide nada (fail-open)
e grava uma linha em <dados>/erros.log.

O código mora no pacote scripts/tuneup/; este arquivo é só a entrada.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def log_import_quebrado(e):
    """Package failed to import: one line in erros.log using only the stdlib. Returns the log path."""
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(
        os.path.expanduser("~"), ".cache", "tune-up")
    log = os.path.join(base, "erros.log")
    try:
        import time
        os.makedirs(base, mode=0o700, exist_ok=True)
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as f:
            linha = "%s import tuneup package failed: %s: %s" % (
                time.strftime("%Y-%m-%dT%H:%M:%S"), type(e).__name__, e)
            f.write(linha.replace("\n", " ")[:2000] + "\n")
    except Exception:
        pass
    return log


try:
    from tuneup import *  # noqa: E402,F401,F403  (nomes públicos para quem importa guarda)
    from tuneup import EVENTOS, main  # noqa: E402,F401
except BaseException as _e:
    if __name__ != "__main__":
        raise
    _log = log_import_quebrado(_e)
    if sys.argv[1:2] == ["inicio"]:  # SessionStart: tell the user the hooks are off
        try:
            import json
            print(json.dumps({"systemMessage": "tune-up: hooks off (import failed), see %s" % _log}))
        except Exception:
            pass
    sys.exit(0)  # pacote quebrado: fail-open, não decide nada


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        pass
    sys.exit(0)
