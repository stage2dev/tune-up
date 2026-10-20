"""Testes do guarda.py: início, pos_bash, robustez e log de erros. Rode: python3 -m unittest discover -s tests -q"""
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest

from base import Base, mkdtemp


class TestInicioPosBash(Base):
    def test_perfil(self):
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)
        open(os.path.join(perfil, "projeto.md"), "w").close()
        with open(os.path.join(perfil, "config.json"), "w") as f:
            json.dump({"projeto": "demo"}, f)
        s = self.rodar("inicio", {"source": "startup"})
        c = s["hookSpecificOutput"]["additionalContext"]
        self.assertIn("projeto demo", c)
        self.assertIn("Merge: Dono", c)

    def test_compact_sem_perfil(self):
        s = self.rodar("inicio", {"source": "compact"})
        self.assertIn("compactado", s["hookSpecificOutput"]["additionalContext"])

    def test_nada(self):
        self.assertIsNone(self.rodar("inicio", {"source": "resume"}))

    def test_limpa_sessao_velha(self):
        self.sessao()
        p = os.path.join(self.dados, "sessoes", "s1.json")
        velho = time.time() - 4 * 86400
        os.utime(p, (velho, velho))
        self.rodar("inicio", {"source": "startup"})
        self.assertFalse(os.path.exists(p))

    def test_pos_bash_pr(self):
        s = self.rodar("pos_bash", {"tool_name": "Bash", "tool_input": {"command": "gh pr create --title x"},
                                    "tool_response": {"stdout": "https://github.com/a/b/pull/3", "stderr": ""}})
        self.assertEqual(s["hookSpecificOutput"]["hookEventName"], "PostToolUse")

    def test_pos_bash_erro(self):
        s = self.rodar("pos_bash", {"tool_input": {"command": "gh pr create"},
                                    "tool_response": {"is_error": True}})
        self.assertIsNone(s)


class TestRobustez(Base):
    def test_json_invalido(self):
        self.assertIsNone(self.rodar("bash", None, bruto="{isso nao e json"))

    def test_excecao_interna(self):
        s = self.rodar("bash", {"tool_input": {"command": "git add -A"}}, {"TUNEUP_FAKE_EXCECAO": "1"})
        self.assertIsNone(s)
        with open(os.path.join(self.dados, "erros.log")) as f:
            self.assertIn("simulated exception", f.read())


class TestA2ErrosVisiveis(Base):
    def log(self):
        try:
            with open(os.path.join(self.dados, "erros.log")) as f:
                return f.read()
        except OSError:
            return ""

    def perfil(self, conteudo):
        p = os.path.join(self.cwd, ".tune-up")
        os.makedirs(p, exist_ok=True)
        with open(os.path.join(p, "config.json"), "w") as f:
            f.write(conteudo)

    def test_config_invalida_loga_e_avisa_no_inicio(self):
        self.perfil("{nao e json")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("config.json do projeto inválido", s["hookSpecificOutput"]["additionalContext"])
        self.assertIn("config", self.log())

    def test_regex_invalida_loga(self):
        self.perfil(json.dumps({"regras_bash": [{"regex": "(", "acao": "avisar"}]}))
        self.bash("ls")
        self.assertIn("regex", self.log())

    def test_frase_invalida_loga(self):
        self.perfil(json.dumps({"frases_pesquisa_liga": ["(("]}))
        self.confiar(os.path.join(self.cwd, ".tune-up", "config.json"))
        self.rodar("prompt", {"prompt": "oi"})
        self.assertIn("regex", self.log())

    def test_sessao_corrompida_loga(self):
        p = os.path.join(self.dados, "sessoes")
        os.makedirs(p)
        with open(os.path.join(p, "s1.json"), "w") as f:
            f.write("{quebrado")
        self.bash("ls")
        self.assertIn("sess", self.log())

    def test_inicio_conta_erros_novos(self):
        os.makedirs(self.dados, exist_ok=True)
        with open(os.path.join(self.dados, "erros.log"), "w") as f:
            f.write("a\nb\n")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("tune-up: 2 erros nos hooks", s["systemMessage"])
        self.assertIn("2 erros", s["hookSpecificOutput"]["additionalContext"])
        self.assertIsNone(self.rodar("inicio", {"source": "resume"}))
        s = self.rodar("inicio", {"source": "startup"})
        self.assertNotIn("erros", s.get("systemMessage", ""))
        self.assertNotIn("erros", s["hookSpecificOutput"]["additionalContext"])
        with open(os.path.join(self.dados, "erros.log"), "a") as f:
            f.write("c\n")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("1 erros", s["systemMessage"])


class TestD8RuidoNoLog(Base):
    def setUp(self):
        super().setUp()
        del self.env["TUNEUP_FAKE_BRANCH"]

    def test_commit_fora_de_repo_nao_loga(self):
        fora = mkdtemp("tuneup-d8-")
        self.addCleanup(shutil.rmtree, fora, True)
        log = os.path.join(self.dados, "erros.log")
        s = self.rodar("bash", {"cwd": fora, "tool_input": {"command": 'git commit -m "x"'}})
        self.assertEqual(self.decisao(s), "avisar")
        self.assertFalse(os.path.exists(log) and os.path.getsize(log))

    def test_detached_nao_loga(self):
        repo = os.path.join(self.tmp, "repo")
        os.makedirs(repo)
        git = lambda *a: subprocess.run(["git", "-C", repo] + list(a), capture_output=True, check=True)
        git("init", "-q")
        git("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "x")
        git("checkout", "-q", "--detach")
        s = self.rodar("bash", {"cwd": repo, "tool_input": {"command": 'git commit -m "y"'}})
        self.assertEqual(self.decisao(s), "avisar")
        self.assertFalse(os.path.exists(os.path.join(self.dados, "erros.log")))


if __name__ == "__main__":
    unittest.main()
