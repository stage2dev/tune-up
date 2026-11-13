"""Textos mostrados ao dono: nenhum sugere --refazer; a pasta pessoal vira ~ em todo comando mostrado. Executor falso
estrito: comando inesperado falha; compose com argv exato; no tempo esgotado, o fim mascarado de `compose ps` no log."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)
sys.path.insert(0, AQUI)

from servico import evolution_local, pasta, preparo, preparo_sistema  # noqa: E402
from preparo_falso import SistemaFalso  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402

CASA = os.path.expanduser("~")
MOSTRADOS = ("skills/instalar/SKILL.md", "README.md", "scripts/inicio.py", "hooks/hooks.json",
             "painel/modulos/vendas/abas/preparar.py", "servico/preparo.py", "servico/preparo_docker.py",
             "servico/preparo_evolution.py", "servico/preparo_sistema.py", "servico/servico.py")


def mudo(*_a, **_k):
    pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta = pasta.caminho_da_pasta(self.projeto, self.base)

    def sistema(self, **k):
        k.setdefault("marca", os.path.basename(self.pasta))
        s = SistemaFalso(**k)
        self.addCleanup(lambda: self.assertEqual(s.inesperados, []))
        return s


class TesteSemRefazer(Base):
    def test_nenhum_texto_mostrado_sugere_refazer(self):
        for nome in MOSTRADOS:
            with open(os.path.join(VENDAS, nome), encoding="utf-8") as f:
                self.assertNotIn("--refazer", f.read(), nome)

    def test_env_incompleto_nao_sugere_refazer(self):
        os.makedirs(os.path.dirname(evolution_local.caminho_env(self.pasta)), exist_ok=True)
        with open(evolution_local.caminho_env(self.pasta), "w", encoding="utf-8") as f:
            f.write("SERVER_URL=\n")
        e = preparo.Execucao(self.projeto, self.base, sistema=self.sistema(), avisar=mudo).rodar()
        p = [p for p in e["passos"] if p["nome"] == "evolution_preparada"][0]
        self.assertEqual(p["estado"], "precisa_do_dono")
        self.assertNotIn("refazer", "%s %s" % (p["mensagem"], p["comando"]))


class TesteCasa(Base):
    def test_motor_troca_a_casa_por_til_no_comando(self):
        comando = "%s/bin/x --pasta %s" % (CASA, os.path.join(CASA, "a b"))
        ex = preparo.Execucao(self.projeto, self.base, sistema=self.sistema(), avisar=mudo)
        ex.passos = (("x", "X", lambda _ex: preparo_sistema.dono("faça", comando)),)
        ex.estado["passos"] = ex.estado["passos"][:1]
        p = ex.rodar()["passos"][0]
        self.assertEqual(p["comando"], "~/bin/x --pasta %s" % os.path.join("~", "a b"))

    def test_til_so_na_fronteira(self):
        self.assertEqual(preparo_sistema.sem_casa(CASA + "x/y " + CASA), CASA + "x/y ~")

    def test_tela_mostra_o_comando_com_til(self):
        mod = carregar_modulo()
        estado = {"estado": "precisa_do_dono", "passos": [{"nome": "docker_instalado", "estado": "precisa_do_dono",
                                                           "mensagem": "m", "comando": CASA + "/bin/x"}]}
        b = mod.preparar.bloco_preparar(estado)
        self.assertEqual(b["campos"][0]["valor"], "~/bin/x")


class TesteExecutorEstrito(Base):
    def arquivo(self):
        return os.path.join(evolution_local.pasta_evolution(self.pasta), evolution_local.ARQUIVO_COMPOSE)

    def test_comando_inesperado_falha(self):
        s = SistemaFalso()
        with self.assertRaises(AssertionError):
            s.rodar(["/falso/bin/docker", "compose", "-f", "/x/compose.yml", "down"], 5)
        self.assertEqual(len(s.inesperados), 1)

    def test_compose_com_argv_exato(self):
        s = self.sistema()
        self.assertEqual(preparo.Execucao(self.projeto, self.base, sistema=s, avisar=mudo).rodar()["estado"], "feito")
        compose = [c for c in s.chamadas if c[1:2] == ["compose"] and c[2:3] != ["version"]]
        self.assertEqual(compose, [["/falso/bin/docker", "compose", "-f", self.arquivo(), "pull"],
                                   ["/falso/bin/docker", "compose", "-f", self.arquivo(), "up", "-d"]])

    def test_tempo_esgotado_guarda_o_fim_mascarado_do_ps(self):
        evolution_local.preparar(self.projeto, self.base)
        chave = evolution_local.ler_ambiente(self.pasta)["VENDAS_EVOLUTION_CHAVE"]
        s = self.sistema()
        s.evolution_sobe = False
        s.saida_ps = "NAME STATUS\napi Restarting (1) chave=%s" % chave
        e = preparo.Execucao(self.projeto, self.base, sistema=s, avisar=mudo).rodar()
        self.assertEqual([p for p in e["passos"] if p["nome"] == "evolution_no_ar"][0]["estado"], "falhou")
        self.assertEqual(s.chamadas[-1], ["/falso/bin/docker", "compose", "-f", self.arquivo(), "ps"])
        with open(preparo.caminhos(self.pasta)["log"], encoding="utf-8") as f:
            log = f.read()
        self.assertIn("api Restarting (1) chave=***", log)
        self.assertNotIn(chave, log)


if __name__ == "__main__":
    unittest.main()
