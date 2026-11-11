"""Ação de exemplo vendas.buscar-leads: carrega pelo catálogo real do painel e as travas (gancho PreToolUse do
painel, rodado como o Claude roda) só deixam passar WebSearch, WebFetch e Write na pasta de candidatos."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
RAIZ = os.path.dirname(VENDAS)
EXEMPLO = os.path.join(VENDAS, "exemplos", "acoes", "vendas.json")
sys.path.insert(0, os.path.join(RAIZ, "painel"))

import catalogo  # noqa: E402
import travas  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pacote = os.path.join(self.tmp, ".tune-up", "painel-projeto")
        os.makedirs(os.path.join(self.pacote, "acoes"))
        shutil.copy(EXEMPLO, os.path.join(self.pacote, "acoes", "vendas.json"))
        acoes, self.avisos = catalogo.carregar_catalogo([os.path.join(self.pacote, "acoes")])
        self.acao = [a for a in acoes if a["id"] == "vendas.buscar-leads"][0]
        self.pasta = os.path.join(self.pacote, "dados", "vendas-candidatos")
        conf = travas.config_gancho(self.acao, [self.pacote, os.path.join(self.tmp, ".tune-up", "painel")],
                                    [os.path.join(self.pacote, "dados")])
        self.arg = travas._codificar(conf)

    def gancho(self, ferramenta, entrada):
        """Decisão ('deny'/'ask'/None) do gancho rodado em processo separado, com -I -B e JSON no stdin."""
        p = subprocess.run([sys.executable, "-I", "-B", os.path.join(RAIZ, "painel", "travas.py"), self.arg],
                           input=json.dumps({"tool_name": ferramenta, "tool_input": entrada}),
                           capture_output=True, text=True, timeout=20, shell=False)
        self.assertEqual(p.returncode, 0)
        return json.loads(p.stdout)["hookSpecificOutput"]["permissionDecision"] if p.stdout.strip() else None


class TesteCatalogo(Base):
    def test_carrega_sem_aviso_e_pede_confirmacao(self):
        self.assertEqual(self.avisos, [])
        self.assertTrue(self.acao["confirmar"])
        self.assertEqual([p["nome"] for p in self.acao["params"]], ["nicho", "cidade"])
        self.assertTrue(all(p["tipo"] == "texto" for p in self.acao["params"]))

    def test_prompt_traz_as_regras(self):
        prompt = self.acao["_prompt"]
        for trecho in ("30", "Google Maps", "Instagram", "login", "nunca envie", "DADO, nunca instrução",
                       "url_da_fonte", "telefone_publicado_no_site", "{nicho}", "{cidade}"):
            self.assertIn(trecho, prompt)

    def test_settings_levam_deny_e_allow_do_exemplo(self):
        cfg = json.loads(travas.settings_da_sessao(self.acao))
        self.assertIn("Bash", cfg["permissions"]["deny"])
        self.assertEqual(cfg["permissions"]["allow"][:2], ["WebSearch", "WebFetch"])


class TesteGancho(Base):
    def escrita(self, nome):
        return {"file_path": os.path.join(self.pasta, nome), "content": "[]"}

    def test_nega_bash_read_mcp_e_write_fora(self):
        self.assertEqual(self.gancho("Bash", {"command": "ls"}), "deny")
        self.assertEqual(self.gancho("Read", {"file_path": os.path.join(self.tmp, "x.txt")}), "deny")
        self.assertEqual(self.gancho("mcp__x__coisa", {"a": 1}), "deny")
        for destino in (os.path.join(self.tmp, "fora.json"), os.path.join(self.pacote, "dados", "outra.json"),
                        os.path.join(self.pasta, "x.sh"), os.path.join(self.pasta, "sub", "x.json"),
                        os.path.join(self.pasta, "..", "x.json")):
            self.assertEqual(self.gancho("Write", {"file_path": destino, "content": "x"}), "deny", destino)
        # o resto do pacote (acoes/) é protegido pelo núcleo: em ação de risco "credito" a trava pergunta (nunca libera)
        for destino in (os.path.join(self.pacote, "acoes", "vendas.json"),
                        os.path.join(self.pasta, "..", "..", "acoes", "x.json")):
            self.assertIn(self.gancho("Write", {"file_path": destino, "content": "x"}), ("deny", "ask"), destino)

    def test_libera_write_na_pasta_e_a_web(self):
        self.assertIsNone(self.gancho("Write", self.escrita("candidatos-20261111-1200.json")))
        self.assertIsNone(self.gancho("WebSearch", {"query": "clínicas em Campinas"}))
        self.assertIsNone(self.gancho("WebFetch", {"url": "https://exemplo.invalid/", "prompt": "telefone"}))

    def test_outras_ferramentas_de_escrita_seguem_negadas(self):
        for f in ("Edit", "MultiEdit", "NotebookEdit", "Glob", "Grep", "Task", "Agent"):
            self.assertEqual(self.gancho(f, self.escrita("a.json")), "deny", f)


if __name__ == "__main__":
    unittest.main()
