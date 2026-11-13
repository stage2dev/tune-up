"""Portas do preparo: nunca aleatórias. Lista fixa (serviço 8791-8795, Evolution 8080-8084), a primeira livre; nenhuma
livre = precisa do dono. As regras de negar da tela cobrem a lista toda."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from servico import evolution_local, pasta, preparo, preparo_sistema  # noqa: E402
from preparo_falso import SistemaFalso  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402


def mudo(*_a, **_k):
    pass


class TestePortas(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta = pasta.caminho_da_pasta(self.projeto, self.base)

    def rodar(self, s):
        return preparo.Execucao(self.projeto, self.base, sistema=s, avisar=mudo).rodar()

    def passo(self, estado, nome):
        return [p for p in estado["passos"] if p["nome"] == nome][0]

    def test_listas_fixas(self):
        self.assertEqual(list(evolution_local.PORTAS_SERVICO), [8791, 8792, 8793, 8794, 8795])
        self.assertEqual(list(evolution_local.PORTAS_EVOLUTION), [8080, 8081, 8082, 8083, 8084])
        self.assertFalse(hasattr(preparo_sistema.Sistema, "porta_qualquer"))

    def test_evolution_ocupada_usa_a_proxima_da_lista(self):
        s = SistemaFalso(marca=os.path.basename(self.pasta))
        s.ocupadas.update({8080, 8081})
        e = self.rodar(s)
        self.assertEqual(e["estado"], "feito", e)
        self.assertEqual(e["portas"]["evolution"], 8082)
        self.assertEqual(evolution_local.ler_ambiente(self.pasta)["VENDAS_EVOLUTION_URL"], "http://127.0.0.1:8082")

    def test_nenhuma_porta_da_evolution_livre_precisa_do_dono(self):
        s = SistemaFalso(marca=os.path.basename(self.pasta))
        s.ocupadas.update(evolution_local.PORTAS_EVOLUTION)
        e = self.rodar(s)
        p = self.passo(e, "evolution_preparada")
        self.assertEqual(p["estado"], "precisa_do_dono", p)
        self.assertIn("8080", p["mensagem"])
        self.assertIn("8084", p["mensagem"])
        self.assertFalse(os.path.exists(evolution_local.caminho_env(self.pasta)))
        self.assertFalse([c for c in s.chamadas if "pull" in c])

    def test_servico_ocupado_usa_a_proxima_e_nenhuma_livre_precisa_do_dono(self):
        s = SistemaFalso(marca=os.path.basename(self.pasta))
        s.ocupadas.add(8791)
        e = self.rodar(s)
        self.assertEqual(e["portas"]["servico"], 8792)
        self.assertEqual(s.soltos[-1][s.soltos[-1].index("--porta") + 1], "8792")
        os.remove(os.path.join(self.pasta, "preparo.json"))
        s2 = SistemaFalso(marca=os.path.basename(self.pasta))
        s2.ocupadas.update(evolution_local.PORTAS_SERVICO)
        s2.evolution_no_ar = True
        p = self.passo(self.rodar(s2), "servico_ligado")
        self.assertEqual(p["estado"], "precisa_do_dono", p)
        self.assertEqual(s2.soltos, [])

    def test_negar_cobre_as_listas(self):
        negar = carregar_modulo().INFO["negar"]
        for porta in list(evolution_local.PORTAS_SERVICO) + list(evolution_local.PORTAS_EVOLUTION):
            for host in ("127.0.0.1", "localhost"):
                self.assertIn("Bash(*%s:%d*)" % (host, porta), negar)


if __name__ == "__main__":
    unittest.main()
