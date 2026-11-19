"""Runner started by the Marketing tab: runs `contas.py status --raiz <raiz>`, then records the exit code and removes
the marker, whatever happened (conferencia.encerrar in a finally). Usage: rodar_conferencia.py --raiz R --id X.
Started by the panel with `python -I`; stdout/stderr already point to the 0600 log. Stdlib only."""
import importlib.util
import os
import subprocess
import sys

_spec = importlib.util.spec_from_file_location("tune_up_mkt_conferencia", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "conferencia.py"))
C = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(C)


def main(argv=None, comando=None):
    """Exit code of contas.py (-1 could not run, -2 timeout). `comando` replaces the real one only in tests."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 4 or argv[0] != "--raiz" or argv[2] != "--id" or not os.path.isabs(argv[1]):
        return 2
    raiz, ident = argv[1], argv[3]
    inicio = C.R.iso(C.agora())
    codigo = -1
    try:
        codigo = subprocess.call(comando or [sys.executable, "-I", C.CONTAS, "status", "--raiz", raiz],
                                 stdin=subprocess.DEVNULL, timeout=C.TEMPO_CONTAS)
    except subprocess.TimeoutExpired:  # call() already killed it
        codigo = -2
    except OSError:
        codigo = -1
    finally:
        C.encerrar(raiz, ident, inicio, codigo)
    return 0 if codigo == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
