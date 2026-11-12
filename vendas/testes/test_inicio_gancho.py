"""Gancho SessionStart (scripts/inicio.py): uma linha quando a tela Vendas está ligada e o WhatsApp não está
preparado; nada sem a tela, com tudo pronto, com um preparo vivo; nunca levanta (pasta faltando, estado corrompido,
entrada ruim) e o processo sai 0 rápido. hooks.json do plugin aponta para o script."""
import sys

sys.dont_write_bytecode = True

import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)
SCRIPT = os.path.join(VENDAS, "scripts", "inicio.py")

from servico import pasta  # noqa: E402

_spec = importlib.util.spec_from_file_location("vendas_inicio_teste", SCRIPT)
inicio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inicio)


class TesteGancho(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        self.sub = os.path.join(self.projeto, "src", "a")
        os.makedirs(self.sub)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta = pasta.pasta_de_dados(self.projeto, self.base)

    def painel(self, conf):
        os.makedirs(os.path.join(self.projeto, ".tune-up"), exist_ok=True)
        with open(os.path.join(self.projeto, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            f.write(conf if isinstance(conf, str) else json.dumps(conf))

    def ligar(self):
        self.painel({"modulos_de_plugins": ["tune-up-vendas@loja:vendas"]})

    def evolution(self):
        os.makedirs(os.path.join(self.pasta, "evolution"), exist_ok=True)
        for n in ("compose.yml", ".env"):
            open(os.path.join(self.pasta, "evolution", n), "w").close()

    def estado(self, conteudo):
        with open(os.path.join(self.pasta, "preparo.json"), "w", encoding="utf-8") as f:
            f.write(conteudo if isinstance(conteudo, str) else json.dumps(conteudo))

    def linha(self, entrada=None):
        if entrada is None:
            entrada = json.dumps({"cwd": self.sub, "hook_event_name": "SessionStart"})
        return inicio.linha(entrada, base=self.base)

    def test_tela_ligada_sem_preparo_uma_linha(self):
        self.ligar()
        texto = self.linha()
        self.assertEqual(texto, inicio.LINHA)
        self.assertNotIn("\n", texto)
        self.assertIn("Preparar tudo", texto)
        self.assertIn("/tune-up-vendas:instalar", texto)
        self.assertNotIn(self.pasta, texto)

    def test_sem_tela_ligada_nada(self):
        self.assertEqual(self.linha(), "")                       # sem .tune-up
        self.painel({"modulos_de_plugins": ["outro@loja:vendas"], "modulos": ["vendas"]})
        self.assertEqual(self.linha(), "")

    def test_pronto_nada_e_parado_avisa(self):
        self.ligar()
        self.evolution()
        self.assertEqual(self.linha(), "")
        self.estado({"estado": "feito", "passos": []})
        self.assertEqual(self.linha(), "")
        for final in ("falhou", "precisa_do_dono"):
            self.estado({"estado": final, "passos": []})
            self.assertEqual(self.linha(), inicio.LINHA)
        self.estado({"estado": "rodando", "pid": os.getpid()})   # preparo vivo: não avisa no meio
        self.assertEqual(self.linha(), "")
        self.estado({"estado": "rodando", "pid": 2 ** 30})        # o processo saiu no meio
        self.assertEqual(self.linha(), inicio.LINHA)

    def test_nunca_levanta(self):
        self.ligar()
        self.evolution()
        self.estado("{corrompido")
        self.assertEqual(self.linha(), "")                        # estado ilegível com os arquivos prontos
        shutil.rmtree(self.pasta)                                 # pasta de dados sumiu
        self.assertEqual(self.linha(), inicio.LINHA)
        self.painel("{nao e json")
        self.assertEqual(self.linha(), "")
        for entrada in ("", "[]", "nao json", json.dumps({"cwd": 3}), json.dumps({"cwd": "/nao/existe/x"})):
            self.assertIsInstance(inicio.linha(entrada, base=self.base), str)

    def test_processo_sai_0_rapido_e_calado(self):
        for entrada in (b"lixo", json.dumps({"cwd": self.sub}).encode()):
            comeco = time.monotonic()
            r = subprocess.run([sys.executable, "-B", SCRIPT], input=entrada, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=30)
            self.assertLess(time.monotonic() - comeco, 5)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))

    def test_hooks_json_aponta_para_o_script(self):
        with open(os.path.join(VENDAS, "hooks", "hooks.json"), encoding="utf-8") as f:
            ganchos = json.load(f)["hooks"]
        self.assertEqual(list(ganchos), ["SessionStart"])
        comando = ganchos["SessionStart"][0]["hooks"][0]["command"]
        self.assertIn('"${CLAUDE_PLUGIN_ROOT}/scripts/inicio.py"', comando)
        self.assertTrue(comando.endswith("|| true"))


if __name__ == "__main__":
    unittest.main()
