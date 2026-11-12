"""Evolution local: compose e .env gerados na pasta de dados externa, chave nova a cada vez, portas só em 127.0.0.1."""
import sys

sys.dont_write_bytecode = True

import io  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from contextlib import redirect_stderr, redirect_stdout  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)

from servico import evolution_local, pasta  # noqa: E402

# chaves padrão públicas de versões da Evolution (env.example / configuração): nunca podem sair no gerado
CHAVES_PUBLICAS = ("BQYHJGJHJ", "429683C4C977415CAAFCCE10F7D57E11", "B6D711FCDE4D4FD5936544120E713976")


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


def valor_env(texto, chave):
    return re.search(r"^%s=(.*)$" % chave, texto, re.M).group(1)


class TesteEvolutionLocal(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")

    def preparar(self, **kw):
        return evolution_local.preparar(self.projeto, base=kw.pop("base", self.base), **kw)

    def test_env_0600_fora_do_projeto(self):
        feito = self.preparar()
        self.assertTrue(os.path.isfile(feito["env"]) and os.path.isfile(feito["compose"]))
        raiz = self.projeto + os.sep
        for caminho in feito.values():
            self.assertFalse(os.path.realpath(caminho).startswith(raiz), caminho)
        self.assertEqual(os.path.dirname(feito["env"]), os.path.join(pasta.caminho_da_pasta(self.projeto, self.base),
                                                                     "evolution"))
        achados = [n for _, _, nomes in os.walk(self.projeto) for n in nomes]
        self.assertEqual(achados, [], "nada pode ser gravado na raiz do projeto")
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(feito["env"]).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(feito["pasta"]).st_mode), 0o700)

    def test_duas_execucoes_geram_chaves_diferentes(self):
        a = ler(self.preparar()["env"])
        b = ler(self.preparar(base=os.path.join(self.tmp, "outra"))["env"])
        for chave in ("AUTHENTICATION_API_KEY", "POSTGRES_PASSWORD"):
            self.assertNotEqual(valor_env(a, chave), valor_env(b, chave))
            self.assertGreaterEqual(len(valor_env(a, chave)), 32)
        self.assertIn(valor_env(a, "POSTGRES_PASSWORD"), valor_env(a, "DATABASE_CONNECTION_URI"))

    def test_recusa_sobrescrever_sem_refazer(self):
        env = self.preparar()["env"]
        antes = ler(env)
        with self.assertRaises(evolution_local.JaPreparado):
            self.preparar()
        self.assertEqual(ler(env), antes)
        depois = ler(self.preparar(refazer=True)["env"])
        self.assertNotEqual(valor_env(depois, "AUTHENTICATION_API_KEY"), valor_env(antes, "AUTHENTICATION_API_KEY"))
        self.assertEqual(sorted(os.listdir(os.path.dirname(env))), [".env", "compose.yml"])
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(env).st_mode), 0o600)

    def test_recusa_alvo_na_raiz_do_projeto(self):
        with self.assertRaises(pasta.PastaRecusada):
            self.preparar(base=self.projeto)
        with self.assertRaises(pasta.PastaRecusada):
            self.preparar(base=os.path.join(self.projeto, "sub"))
        erro = io.StringIO()
        with redirect_stderr(erro), redirect_stdout(io.StringIO()):
            codigo = evolution_local.main(["preparar", "--projeto", self.projeto, "--base", self.projeto])
        self.assertEqual(codigo, 2)
        self.assertIn("dentro do projeto", erro.getvalue())
        self.assertEqual([n for _, _, nomes in os.walk(self.projeto) for n in nomes], [])

    def test_compose_so_publica_em_127(self):
        texto = ler(self.preparar(porta_evolution=18080)["compose"])
        self.assertNotIn("0.0.0.0", texto)
        self.assertNotIn("__", texto, "marcador do modelo sobrou")
        portas, dentro = [], None
        for linha in texto.splitlines():
            recuo = len(linha) - len(linha.lstrip())
            if linha.strip() == "ports:":
                dentro = recuo
            elif dentro is not None and linha.strip().startswith("- ") and recuo > dentro:
                portas.append(linha.strip()[2:].strip("\"'"))
            elif linha.strip():
                dentro = None
        self.assertEqual(portas, ["127.0.0.1:18080:8080"])
        self.assertNotIn("expose", texto)
        self.assertIn("host.docker.internal:host-gateway", texto)
        self.assertIn("host.docker.internal:8791", texto)

    def test_chave_publica_nunca_aparece(self):
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(evolution_local.main(["preparar", "--projeto", self.projeto, "--base", self.base]), 0)
        env = os.path.join(pasta.caminho_da_pasta(self.projeto, self.base), "evolution", ".env")
        textos = [ler(env), ler(os.path.join(os.path.dirname(env), "compose.yml")), ler(evolution_local.MODELO),
                  ler(evolution_local.__file__), saida.getvalue()]
        for publica in CHAVES_PUBLICAS:
            for t in textos:
                self.assertNotIn(publica, t)
        self.assertNotIn(valor_env(textos[0], "AUTHENTICATION_API_KEY"), saida.getvalue(), "chave no terminal")
        self.assertIn("docker compose -f", saida.getvalue())

    def test_nunca_roda_o_docker(self):
        fonte = ler(evolution_local.__file__)
        for proibido in ("subprocess", "os.system", "os.popen", "os.exec", "os.spawn"):
            self.assertNotIn(proibido, fonte)

    def test_servico_le_url_e_chave_do_env(self):
        pasta_dados = pasta.pasta_de_dados(self.projeto, base=self.base)
        self.assertEqual(evolution_local.ler_ambiente(pasta_dados), {})
        env = ler(self.preparar(porta_evolution=18081)["env"])
        self.assertEqual(evolution_local.ler_ambiente(pasta_dados), {
            "VENDAS_EVOLUTION_URL": "http://127.0.0.1:18081",
            "VENDAS_EVOLUTION_CHAVE": valor_env(env, "AUTHENTICATION_API_KEY")})

    def test_docker_compose_aceita_o_arquivo(self):
        docker = shutil.which("docker")
        if not docker or subprocess.run([docker, "compose", "version"], capture_output=True).returncode != 0:
            self.skipTest("docker compose não instalado nesta máquina")
        compose = self.preparar()["compose"]
        r = subprocess.run([docker, "compose", "-f", compose, "config", "-q"], capture_output=True, text=True,
                           cwd=self.tmp, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr[-400:])


if __name__ == "__main__":
    unittest.main()
