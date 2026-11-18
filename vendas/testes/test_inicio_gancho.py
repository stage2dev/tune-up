"""Gancho SessionStart (scripts/inicio.py): uma linha quando a tela Vendas está ligada e o WhatsApp não está
preparado; nada sem a tela, com tudo pronto, com um preparo vivo; nunca levanta (pasta faltando, estado corrompido,
entrada ruim) e o processo sai 0 rápido. Ligado = a mesma resposta de painel/embutidos.py (arquivo
embutidos-ligados.json do painel ou a linha antiga do painel.json). O hooks.json do núcleo roda o script pelo lançador."""
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
RAIZ = os.path.dirname(VENDAS)
sys.path.insert(0, VENDAS)
SCRIPT = os.path.join(VENDAS, "scripts", "inicio.py")

from servico import pasta, travas  # noqa: E402

sys.path.insert(0, os.path.join(RAIZ, "painel"))   # só no teste: o gancho não importa o painel
import config  # noqa: E402
import embutidos  # noqa: E402

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
        trava = travas.TravaDoProcesso(self.pasta, "preparo.trava").pegar()
        self.estado({"estado": "rodando", "pid": os.getpid()})   # preparo vivo (trava ocupada): não avisa no meio
        self.assertEqual(self.linha(), "")
        trava.soltar()
        self.estado({"estado": "rodando", "pid": 2 ** 30})        # o processo saiu no meio (trava livre)
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

    def test_hooks_json_do_nucleo_roda_o_script(self):
        self.assertFalse(os.path.exists(os.path.join(VENDAS, "hooks")))   # Vendas não é mais plugin próprio
        with open(os.path.join(RAIZ, "hooks", "hooks.json"), encoding="utf-8") as f:
            grupos = json.load(f)["hooks"]["SessionStart"]
        achados = [(g, x) for g in grupos for x in g["hooks"] if "vendas/scripts/inicio.py" in x["command"]]
        self.assertEqual(len(achados), 1)
        grupo, gancho = achados[0]
        self.assertTrue(gancho["command"].startswith('sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" vendas/scripts/inicio.py'))
        self.assertTrue(gancho["command"].endswith(" 2>/dev/null || true"))
        self.assertEqual((grupo["matcher"], gancho["timeout"]), ("startup|resume|clear", 5))


ANTIGA = {"modulos_de_plugins": ["tune-up-vendas@loja:vendas"]}
GRANDE = json.dumps({"vendas": True, "x": "a" * 5000})
# (painel.json, embutidos-ligados.json (None = sem arquivo), pasta de dados sob .tune-up, pacote é arquivo, ligado)
CASOS = (
    ({}, {"vendas": True}, "painel-projeto/dados", False, True),          # ligado pela tela, sem linha antiga
    ({}, None, "painel-projeto/dados", False, False),                     # padrão: desligado
    (ANTIGA, None, "painel-projeto/dados", False, True),                  # linha antiga sem arquivo: ligado
    (ANTIGA, {"vendas": False}, "painel-projeto/dados", False, False),    # o arquivo vence a linha antiga
    (ANTIGA, {"estudio": True}, "painel-projeto/dados", False, True),     # o arquivo não fala de vendas
    (ANTIGA, {"estudio": "sim"}, "painel-projeto/dados", False, False),   # inválido: tudo desligado
    ({}, "{lixo", "painel-projeto/dados", False, False),                  # ilegível
    (ANTIGA, GRANDE, "painel-projeto/dados", False, False),               # passa de 4 KB
    ({}, {"vendas": True}, "painel-dados", True, True),                   # pacote não é pasta: .tune-up/painel-dados
    ({"pacote": "meu"}, {"vendas": True}, "meu/dados", False, True),      # pacote com outro nome
    ({"pacote": "../x"}, {"vendas": True}, "painel-projeto/dados", False, True),   # nome inválido: o padrão
)


class TesteLigado(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def projeto(self, n, conf, estado, dados, pacote_arquivo):
        raiz = os.path.join(self.tmp, "p%d" % n)
        os.makedirs(os.path.join(raiz, ".tune-up", dados))
        with open(os.path.join(raiz, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump(conf, f)
        if pacote_arquivo:
            open(os.path.join(raiz, ".tune-up", "painel-projeto"), "w").close()
        if estado is not None:
            with open(os.path.join(raiz, ".tune-up", dados, "embutidos-ligados.json"), "w", encoding="utf-8") as f:
                f.write(estado if isinstance(estado, str) else json.dumps(estado))
        return raiz

    def test_regra_do_gancho_igual_a_do_painel(self):
        for n, (conf, estado, dados, pacote_arquivo, esperado) in enumerate(CASOS):
            raiz = self.projeto(n, conf, estado, dados, pacote_arquivo)
            painel = "vendas" in embutidos.ligados(config.carregar(raiz, home=self.tmp))
            self.assertEqual((n, inicio.modulo_ligado(raiz), painel), (n, esperado, esperado))

    def test_ligado_pelo_arquivo_avisa_e_desligado_cala(self):
        base = os.path.join(self.tmp, "vendas-dados")
        for n, (conf, estado, dados, pacote_arquivo, esperado) in enumerate(CASOS):
            raiz = self.projeto(n, conf, estado, dados, pacote_arquivo)
            texto = inicio.linha(json.dumps({"cwd": raiz}), base=base)
            self.assertEqual((n, texto), (n, inicio.LINHA if esperado else ""))

    def test_arquivo_ruim_pelo_lancador_sai_0_calado(self):
        for n, estado in ((0, "{lixo"), (1, GRANDE)):
            raiz = self.projeto(n, {}, estado, "painel-projeto/dados", False)
            comeco = time.monotonic()
            r = subprocess.run(["sh", os.path.join(RAIZ, "scripts", "py"), "vendas/scripts/inicio.py"],
                               input=json.dumps({"cwd": raiz}).encode(), stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=30)
            self.assertLess(time.monotonic() - comeco, 5)
            self.assertEqual((r.returncode, r.stdout, r.stderr), (0, b"", b""))

if __name__ == "__main__":
    unittest.main()
