"""Testes de custo.py: transcritos falsos em pasta temporária; nada toca ~/.claude."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import custo  # noqa: E402

SID = "11111111-1111-4111-8111-111111111111"
SID2 = "22222222-2222-4222-8222-222222222222"


def linha(mid, modelo="claude-opus-4", **uso):
    return json.dumps({"type": "assistant", "message": {"id": mid, "model": modelo, "usage": uso}}) + "\n"


class TesteCusto(unittest.TestCase):
    def setUp(self):
        custo.esquecer()
        self.tmp = tempfile.mkdtemp()
        self.proj = os.path.join(self.tmp, "proj")
        self.pasta = os.path.join(self.proj, "-p")
        os.makedirs(self.pasta)
        self.cfg = {"projects_dir": self.proj, "raiz": self.tmp}

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def escrever(self, sid, linhas, sub=None, wf=None):
        if sub is None:
            caminho = os.path.join(self.pasta, sid + ".jsonl")
        else:
            d = os.path.join(self.pasta, sid, "subagents", *(["workflows", wf] if wf else []))
            os.makedirs(d, exist_ok=True)
            caminho = os.path.join(d, "agent-%s.jsonl" % sub)
        with open(caminho, "w", encoding="utf-8", newline="\n") as f:
            f.write("".join(linhas))
        return caminho

    def um(self, sid=SID):
        cod, corpo = custo.responder(self.cfg, [sid])
        self.assertEqual(cod, 200)
        self.assertTrue(corpo["estimativa"])
        return corpo["sessoes"][0]

    def test_dedupe_pega_o_maximo(self):
        self.escrever(SID, [linha("a", input_tokens=1, output_tokens=5, cache_read_input_tokens=0),
                            linha("a", input_tokens=10, output_tokens=2, cache_read_input_tokens=7),
                            linha("b", input_tokens=3, output_tokens=4)])
        t = self.um()["tokens"]
        self.assertEqual((t["entrada"], t["saida"], t["cache_leitura"], t["total"]), (13, 9, 7, 29))

    def test_cache_1h_e_5m(self):
        cri = {"ephemeral_5m_input_tokens": 400000, "ephemeral_1h_input_tokens": 600000}
        self.escrever(SID, [linha("a", cache_creation_input_tokens=1000000, cache_creation=cri)])
        s = self.um()
        self.assertEqual(s["tokens"]["cache_escrita"], 1000000)
        self.assertAlmostEqual(s["usd"], 0.4 * 6.25 + 0.6 * 10, places=4)

    def test_sem_divisao_conta_5m(self):
        self.escrever(SID, [linha("a", cache_creation_input_tokens=1000000)])
        self.assertAlmostEqual(self.um()["usd"], 6.25, places=4)

    def test_divisao_vem_da_linha_de_maior_cache(self):
        self.escrever(SID, [linha("a", cache_creation_input_tokens=1000000,
                                  cache_creation={"ephemeral_1h_input_tokens": 1000000}),
                            linha("a", cache_creation_input_tokens=500000,
                                  cache_creation={"ephemeral_1h_input_tokens": 0})])
        self.assertAlmostEqual(self.um()["usd"], 10.0, places=4)

    def test_subagentes_e_workflow_somam_e_contexto_so_do_principal(self):
        self.escrever(SID, [linha("a", input_tokens=100, cache_read_input_tokens=50, output_tokens=1)])
        self.escrever(SID, [linha("s", input_tokens=9000, output_tokens=2)], sub="abc")
        self.escrever(SID, [linha("w", input_tokens=1, output_tokens=3)], sub="def", wf="wf_x1")
        s = self.um()
        self.assertEqual(s["subagentes"], 2)
        self.assertEqual(s["tokens"]["entrada"], 9101)
        self.assertEqual(s["tokens"]["saida"], 6)
        self.assertEqual(s["contexto_maximo"], 150)
        self.assertFalse(s["parcial"])

    def test_sintetico_e_sem_usage_ignorados(self):
        self.escrever(SID, [linha("a", "<synthetic>", input_tokens=99), '{"type":"user","message":{"id":"x"}}\n',
                            linha("b", input_tokens=5)])
        s = self.um()
        self.assertEqual(s["tokens"]["entrada"], 5)
        self.assertEqual([m["modelo"] for m in s["modelos"]], ["opus"])

    def test_modelo_desconhecido_sem_preco_e_pct_soma_100(self):
        self.escrever(SID, [linha("a", "claude-opus-4", input_tokens=1000000),
                            linha("b", "claude-sonnet-4", input_tokens=1000000),
                            linha("c", "gpt-novo", input_tokens=1000000)])
        s = self.um()
        por = {m["modelo"]: m for m in s["modelos"]}
        self.assertIsNone(por["gpt-novo"]["usd"])
        self.assertIsNone(por["gpt-novo"]["pct"])
        self.assertTrue(s["usd_incompleto"])
        self.assertAlmostEqual(s["usd"], 8.0)
        self.assertAlmostEqual(por["opus"]["pct"] + por["sonnet"]["pct"], 100.0, delta=0.11)
        self.assertEqual(s["modelos"][0]["modelo"], "opus")

    def test_so_modelo_sem_preco(self):
        self.escrever(SID, [linha("a", "outro", input_tokens=4)])
        s = self.um()
        self.assertIsNone(s["usd"])
        self.assertTrue(s["usd_incompleto"])

    def test_nao_encontrada(self):
        s = self.um(SID2)
        self.assertFalse(s["encontrada"])
        self.assertIsNone(s["tokens"])
        self.assertIsNone(s["usd"])
        self.assertEqual(s["modelos"], [])

    def test_cache_acerta_e_invalida_quando_cresce(self):
        caminho = self.escrever(SID, [linha("a", input_tokens=1)])
        self.assertEqual(self.um()["tokens"]["entrada"], 1)
        with mock.patch("custo.open", side_effect=AssertionError("reabriu"), create=True):
            self.assertEqual(self.um()["tokens"]["entrada"], 1)
        with open(caminho, "a", encoding="utf-8", newline="\n") as f:
            f.write(linha("b", input_tokens=4))
        self.assertEqual(self.um()["tokens"]["entrada"], 5)

    def test_ultima_linha_parcial_e_valores_ruins(self):
        self.escrever(SID, [linha("a", input_tokens=2, output_tokens="x", cache_read_input_tokens=None),
                            linha("b", input_tokens=-5, output_tokens=True),
                            linha("c", input_tokens=3).rstrip("\n")])  # sem \n: ainda sendo escrita
        t = self.um()["tokens"]
        self.assertEqual((t["entrada"], t["saida"], t["cache_leitura"]), (2, 0, 0))

    def test_arquivo_ilegivel_vira_parcial(self):
        self.escrever(SID, [linha("a", input_tokens=1)])
        with mock.patch("custo.open", side_effect=PermissionError, create=True):
            s = self.um()
        self.assertTrue(s["encontrada"])
        self.assertTrue(s["parcial"])

    def test_symlink_fora_e_ignorado(self):
        fora = os.path.join(self.tmp, "fora.jsonl")
        with open(fora, "w", encoding="utf-8") as f:
            f.write(linha("a", input_tokens=77))
        try:
            os.symlink(fora, os.path.join(self.pasta, SID2 + ".jsonl"))
            d = os.path.join(self.pasta, SID, "subagents")
            os.makedirs(d)
            os.symlink(fora, os.path.join(d, "agent-abc.jsonl"))
        except (OSError, NotImplementedError):
            self.skipTest("sem permissão de symlink")
        self.assertFalse(self.um(SID2)["encontrada"])
        self.escrever(SID, [linha("z", input_tokens=1)])
        s = self.um()
        self.assertEqual((s["subagentes"], s["tokens"]["entrada"]), (0, 1))

    def test_ids_invalidos_e_limites(self):
        for ruim in ("../x", SID + "\n", "AAAAAAAA-1111-4111-8111-111111111111", ""):
            self.assertEqual(custo.responder(self.cfg, [ruim]), (400, {"erro": "Sessão inválida."}), repr(ruim))
        muitos = ["%08x-1111-4111-8111-111111111111" % i for i in range(61)]
        self.assertEqual(custo.responder(self.cfg, muitos)[0], 400)
        self.assertEqual(custo.responder(self.cfg, muitos[:60])[0], 200)
        self.assertEqual(custo.responder(self.cfg, []), (200, {"estimativa": True, "sessoes": []}))

    def test_repetidos_uma_vez(self):
        cod, corpo = custo.responder(self.cfg, [SID, SID, SID2])
        self.assertEqual([s["sessao_id"] for s in corpo["sessoes"]], [SID, SID2])


if __name__ == "__main__":
    unittest.main()
