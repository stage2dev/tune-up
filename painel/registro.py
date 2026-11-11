"""Registro das execuções que o painel disparou: <dados>/execucoes.json.

0600, escrita atômica (mkstemp + replace) e trava de arquivo. Saiu de lancador.py (tamanho).
"""
import datetime
import json
import os
import re
import tempfile
import time

from trava import _TravaArquivo

RE_ID_EXEC = re.compile(r"^[0-9a-f]{6,16}$")
MAX_REGISTRO = 200
# s: no Windows, abrir/trocar execucoes.json dá PermissionError enquanto outro thread o lê; insiste até isto
PRAZO_OCUPADO = 2 if os.name == "nt" else 0


def agora_iso(t):
    return datetime.datetime.fromtimestamp(t, datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def _insistir(fazer):
    """Roda `fazer`; em PermissionError tenta de novo até PRAZO_OCUPADO s e então sobe o erro."""
    limite = time.monotonic() + PRAZO_OCUPADO
    while True:
        try:
            return fazer()
        except PermissionError:
            if time.monotonic() >= limite:
                raise
            time.sleep(0.05)


class Registro:
    """dados/execucoes.json: lista de execuções. 0600, escrita atômica, trava de arquivo."""

    def __init__(self, pasta):
        self.pasta = pasta
        self.arquivo = os.path.join(pasta, "execucoes.json")
        self.arquivo_trava = os.path.join(pasta, "execucoes.lock")

    def trava(self):
        os.makedirs(self.pasta, mode=0o700, exist_ok=True)
        os.chmod(self.pasta, 0o700)
        return _TravaArquivo(self.arquivo_trava)

    def ler(self):
        try:
            dado = _insistir(self._ler_json)
        except FileNotFoundError:
            return []
        except PermissionError:
            raise  # Windows: aberto por outro além do prazo; lista vazia aqui apagaria o registro
        except (OSError, ValueError):
            return []
        if not isinstance(dado, list):
            return []
        return [x for x in dado if isinstance(x, dict) and RE_ID_EXEC.match(str(x.get("id", "")))]

    def _ler_json(self):
        with open(self.arquivo, encoding="utf-8") as f:
            return json.load(f)

    def gravar(self, lista):
        """Chame com a trava na mão."""
        fd, tmp = tempfile.mkstemp(prefix=".execucoes-", dir=self.pasta)  # nasce 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(lista[-MAX_REGISTRO:], f, ensure_ascii=False, indent=1)
            os.chmod(tmp, 0o600)
            _insistir(lambda: os.replace(tmp, self.arquivo))
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def atualizar(self, exec_id, **campos):
        with self.trava():
            lista = self.ler()
            for r in lista:
                if r["id"] == exec_id:
                    r.update(campos)
            self.gravar(lista)
