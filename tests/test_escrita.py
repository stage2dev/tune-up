"""Testes do guarda.py: evento escrita e proteção da guarda. Rode: python3 -m unittest discover -s tests -q"""
import json
import os
import stat
import unittest

from base import Base, IS_WIN, PromptBase, SEM_MODOS, symlink


class TestEscrita(Base):
    def test_chmod_raiz_sincronizada(self):
        raiz = os.path.join(self.tmp, "sync")
        sub = os.path.join(raiz, "sub")
        os.makedirs(sub)
        arq = os.path.join(raiz, "velho.txt")
        open(arq, "w").close()
        os.chmod(arq, 0o444)
        os.chmod(sub, 0o555)
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)
        with open(os.path.join(perfil, "config.json"), "w") as f:
            json.dump({"raizes_sincronizadas": [raiz]}, f)
        self.confiar(os.path.join(perfil, "config.json"))
        s = self.rodar("escrita", {"tool_name": "Write",
                                   "tool_input": {"file_path": os.path.join(sub, "novo.txt"), "content": "x"}})
        self.assertIsNone(s)
        self.assertTrue(os.stat(sub).st_mode & stat.S_IWUSR)
        self.rodar("escrita", {"tool_name": "Edit", "tool_input": {"file_path": arq}})
        self.assertTrue(os.stat(arq).st_mode & stat.S_IWUSR)

    def test_pesquisa_edit_fora(self):
        self.sessao(modo_pesquisa=True)
        s = self.rodar("escrita", {"tool_name": "Edit", "tool_input": {"file_path": "/x/app.py"}})
        self.assertEqual(self.decisao(s), "perguntar")

    def test_pesquisa_write_scratchpad(self):
        self.sessao(modo_pesquisa=True)
        sp = os.path.join(self.tmp, "scratch")
        s = self.rodar("escrita", {"tool_name": "Write", "scratchpad_dir": sp,
                                   "tool_input": {"file_path": os.path.join(sp, "a.md")}})
        self.assertIsNone(s)

    def test_pesquisa_planning(self):
        self.sessao(modo_pesquisa=True)
        s = self.rodar("escrita", {"tool_name": "Write",
                                   "tool_input": {"file_path": os.path.join(self.cwd, ".planning", "GOAL.md")}})
        self.assertIsNone(s)

    def test_planning_de_outro_repo_fora_da_raiz_nao_fica_livre(self):
        import subprocess
        outro = os.path.join(self.tmp, "outro-repo")
        os.makedirs(os.path.join(outro, "x", ".planning"))
        subprocess.run(["git", "init", "-q", outro], check=True)
        alvo = os.path.join(outro, "x", ".planning", "a.py")
        # talk anchors at the file's own repo (21/10): code there is denied, not asked
        for modo, esperado in (("modo_pesquisa", "perguntar"), ("modo_conversa", "bloquear")):
            with self.subTest(modo=modo):
                self.sessao(**{modo: True})
                s = self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": alvo}})
                self.assertEqual(self.decisao(s), esperado)
        self.sessao(modo_pesquisa=True)
        s = self.rodar("escrita", {"tool_name": "Write",
                                   "tool_input": {"file_path": os.path.join(outro, ".planning", "a.md")}})
        self.assertIsNone(s)


class TestC5GuardaSeProtege(PromptBase):
    def escrever(self, caminho, **extra):
        e = {"tool_name": "Write", "tool_input": {"file_path": caminho}}
        e.update(extra)
        return self.decisao(self.rodar("escrita", e))

    def test_settings_sempre_pergunta(self):
        self.prompt("regra nova: a partir de agora mexe no settings")
        for nome in ["settings.json", "settings.local.json"]:
            with self.subTest(nome=nome):
                self.assertEqual(self.escrever(os.path.join(self.tmp, ".claude", nome)), "perguntar")

    def test_protegidos_perguntam_sem_frase(self):
        for c in [os.path.join(self.cwd, ".tune-up", "config.json"),
                  os.path.join(self.tmp, ".claude", "plugins", "tune-up", "scripts", "guarda.py"),
                  os.path.join(self.dados, "perfis_confiaveis.txt")]:
            with self.subTest(c=c):
                self.assertEqual(self.escrever(c), "perguntar")

    def test_frase_do_turno_libera(self):
        self.prompt("/tune-up:profile")
        self.assertIsNone(self.escrever(os.path.join(self.cwd, ".tune-up", "config.json")))
        self.assertEqual(self.ler_sessao().get("aprender_prompt_id"), "p1")
        s = self.rodar("escrita", {"prompt_id": "p2", "tool_name": "Write",
                                   "tool_input": {"file_path": os.path.join(self.cwd, ".tune-up", "config.json")}})
        self.assertEqual(self.decisao(s), "perguntar")

    def test_regra_nova_libera_plugin(self):
        self.prompt("regra permanente: guarde isso no plugin")
        self.assertIsNone(self.escrever(os.path.join(self.tmp, ".claude", "plugins", "x.md")))

    def test_pesquisa_nao_libera_claude_inteiro(self):
        self.sessao(modo_pesquisa=True)
        self.assertEqual(self.escrever(os.path.join(self.tmp, ".claude", "CLAUDE.md")), "perguntar")
        self.assertEqual(self.escrever("/x/memory/a.md"), "perguntar")
        self.assertIsNone(self.escrever(os.path.join(self.tmp, ".claude", "projects", "p", "memory", "a.md")))


@unittest.skipIf(IS_WIN, SEM_MODOS)
class TestD6Permissoes(PromptBase):
    def test_modos(self):
        self.prompt("pode aplicar a migration")
        self.rodar("bash", {"tool_input": {"command": "git commit -m x"}}, {"TUNEUP_FAKE_BRANCH": ""})
        c = os.path.join(self.cwd, ".tune-up", "config.json")
        os.makedirs(os.path.dirname(c))
        open(c, "w").write("{}")
        self.confiar(c)
        modo = lambda p: stat.S_IMODE(os.stat(p).st_mode)
        self.assertEqual(modo(self.dados), 0o700)
        self.assertEqual(modo(os.path.join(self.dados, "sessoes")), 0o700)
        self.assertEqual(modo(os.path.join(self.dados, "sessoes", "s1.json")), 0o600)
        self.assertEqual(modo(os.path.join(self.dados, "perfis_confiaveis.txt")), 0o600)
        log = os.path.join(self.dados, "erros.log")
        if not os.path.exists(log):
            self.rodar("bash", {}, bruto="nao json")
        self.assertEqual(modo(log), 0o600)



class TestH2bAutoprotecaoPorCaminho(PromptBase):
    """Self-protection by path (level 'turno' = ask), plus the learn/profile/setup turn exception."""
    RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # plugin root, never by name

    def escrever(self, caminho):
        return self.decisao(self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": caminho}}))

    def test_raiz_do_plugin_por_file(self):
        self.assertEqual(self.escrever(os.path.join(self.RAIZ, "scripts", "x.py")), "perguntar")

    def test_plugins_do_claude(self):
        self.assertEqual(self.escrever(os.path.join(self.tmp, ".claude", "plugins", "cache", "m", "a.json")),
                         "perguntar")

    def test_config_tune_up(self):
        self.assertEqual(self.escrever(os.path.join(self.tmp, ".config", "tune-up", "user.json")), "perguntar")

    def test_protected_paths_do_user_json(self):
        self.user_json({"language": "pt-BR", "protected_paths": ["~/cofre", "relativo/ignorado"]})
        self.assertEqual(self.escrever(os.path.join(self.tmp, "cofre", "a.md")), "perguntar")
        self.assertIsNone(self.escrever(os.path.join(self.cwd, "relativo", "ignorado", "a.md")))

    def test_settings_pergunta_sempre(self):
        self.prompt("/tune-up:setup")
        self.assertEqual(self.escrever(os.path.join(self.tmp, ".claude", "settings.json")), "perguntar")

    def test_turno_de_setup_libera(self):
        self.prompt("/tune-up:setup")
        self.assertIsNone(self.escrever(os.path.join(self.tmp, ".config", "tune-up", "user.json")))
        self.prompt("from now on, new rule: x")
        self.assertIsNone(self.escrever(os.path.join(self.tmp, ".claude", "plugins", "x.md")))

    def test_fora_continua_livre(self):
        self.assertIsNone(self.escrever(os.path.join(self.tmp, ".claude", "outra-pasta", "x.md")))


class TestM7SymlinkNoScratch(PromptBase):
    """M7 (22/10): a scratchpad symlink into the project is judged by its real path."""
    def setUp(self):
        super().setUp()
        import subprocess
        subprocess.run(["git", "init", "-q", self.cwd], check=True)
        os.makedirs(os.path.join(self.cwd, "src"))
        self.scratch = os.path.join(self.tmp, "scratch")
        os.makedirs(self.scratch)
        symlink(os.path.join(self.cwd, "src"), os.path.join(self.scratch, "lnk"), True)
        self.alvo = os.path.join(self.scratch, "lnk", "app.py")

    def test_talk_nega(self):
        self.sessao(modo_conversa=True, modo_pesquisa=True)
        s = self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": self.alvo},
                                   "scratchpad_dir": self.scratch})
        self.assertEqual(self.decisao(s), "bloquear")
        s = self.rodar("bash", {"tool_name": "Bash", "tool_input": {"command": "echo x > %s" % self.alvo},
                                "scratchpad_dir": self.scratch})
        self.assertEqual(self.decisao(s), "bloquear")
        livre = os.path.join(self.scratch, "nota.py")
        self.assertIsNone(self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": livre},
                                                 "scratchpad_dir": self.scratch}))

    def test_pesquisa_pergunta(self):
        self.sessao(modo_pesquisa=True)
        s = self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": self.alvo},
                                   "scratchpad_dir": self.scratch})
        self.assertEqual(self.decisao(s), "perguntar")


class TestB5EscritaMalformada(Base):
    def test_tool_input_ou_cwd_invalido_pergunta(self):
        for entrada in ({"tool_name": "Write", "tool_input": "a.py"},
                        {"tool_name": "Write", "tool_input": {"file_path": "a.py"}, "cwd": 3}):
            with self.subTest(entrada=entrada):
                self.assertEqual(self.decisao(self.rodar("escrita", entrada)), "perguntar")


class TestB2RaizesUmaVezPorExecucao(PromptBase):
    def test_achar_perfil_uma_vez(self):
        import sys
        from unittest import mock
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
        import tuneup.escrita as e
        os.makedirs(os.path.join(self.cwd, ".tune-up"))
        chamadas = []

        def conta(cwd):
            chamadas.append(cwd)
            return os.path.join(self.cwd, ".tune-up")
        with mock.patch.object(e, "achar_perfil", conta):
            for i in range(50):
                self.assertIsNone(e.protecao_da_guarda(os.path.join(self.cwd, "f%d" % i), self.cwd))
        self.assertLessEqual(len(chamadas), 1)


if __name__ == "__main__":
    unittest.main()
