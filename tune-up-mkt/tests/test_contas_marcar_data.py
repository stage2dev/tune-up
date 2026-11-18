"""D0: `marcar` keeps the top-level conferido_em of the last automatic check; only `status` refreshes it."""
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

from tests.test_contas import C, R, T0, falso, fx, which_tudo

T10 = T0 + timedelta(days=10)


class DataDoTopo(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-contas-data-"))
        self.env = mock.patch.dict(os.environ, {"HOME": self.tmp, "USERPROFILE": self.tmp})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rodar(self, *args, agora=T0):
        rodar, _ = falso(fx("plugin_list_ligado.json"), fx("mcp_list_ligado.txt"),
                         fx("composio_connections_ligado.json"))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = C.main(list(args) + ["--raiz", self.tmp], agora=agora, rodar=rodar, which=which_tudo)
        return rc, out.getvalue(), err.getvalue()

    def topo(self):
        with open(os.path.join(self.tmp, ".tune-up", "mkt", "contas.json"), encoding="utf-8") as f:
            return json.load(f).get("conferido_em")

    def test_marcar_nao_renova_status_velho(self):
        self.assertEqual(self.rodar("status")[0], 0)
        self.assertEqual(self.topo(), R.iso(T0))
        self.assertEqual(self.rodar("marcar", "chrome", "ligado", "--prova", "manual", agora=T10)[0], 0)
        self.assertEqual(self.topo(), R.iso(T0))
        self.assertEqual(self.rodar("falta", agora=T10)[0], 1)  # status is 10 days old

    def test_status_renova(self):
        self.rodar("status")
        self.rodar("marcar", "chrome", "ligado", "--prova", "manual", agora=T10)
        self.assertEqual(self.rodar("status", agora=T10)[0], 0)
        self.assertEqual(self.topo(), R.iso(T10))
        self.assertEqual(self.rodar("falta", agora=T10)[0], 0)

    def test_marcar_sem_arquivo_deixa_data_vazia(self):
        self.assertEqual(self.rodar("marcar", "chrome", "ligado", "--prova", "manual")[0], 0)
        self.assertIsNone(self.topo())
        self.assertEqual(self.rodar("falta")[0], 1)  # asks for a status first


if __name__ == "__main__":
    unittest.main()
