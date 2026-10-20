"""Tests: guard paths by file identity, letter case, ancestors and protected_paths (security
review H2b, 21/10). Run: python3 -m unittest discover -s tests -q"""
import json
import os
import unittest
from base import PromptBase


def disco_sem_caixa(pasta):
    p = os.path.join(pasta, "SondaCaixa")
    open(p, "w", encoding="utf-8").close()
    try:
        return os.path.exists(os.path.join(pasta, "sondacaixa"))
    finally:
        os.remove(p)


class SegBase(PromptBase):
    def setUp(self):
        super().setUp()
        for d in (".config/tune-up", ".claude", "dados"):
            os.makedirs(os.path.join(self.tmp, d), exist_ok=True)
        os.makedirs(os.path.join(self.cwd, ".tune-up"))
        for p, txt in ((".config/tune-up/user.json", "{}"), (".claude/settings.json", "{}"),
                       ("dados/perfis_confiaveis.txt", "")):
            with open(os.path.join(self.tmp, p), "w", encoding="utf-8") as f:
                f.write(txt)
        with open(os.path.join(self.cwd, ".tune-up", "config.json"), "w", encoding="utf-8") as f:
            f.write('{"project": "p"}')

    def escrever(self, caminho):
        return self.decisao(self.rodar("escrita", {"tool_name": "Write",
                                                   "tool_input": {"file_path": caminho}}))


class TestSegCaixa(SegBase):
    def test_maiusculas_por_write_e_bash(self):
        if not disco_sem_caixa(self.tmp):
            self.skipTest("disk distinguishes letter case")
        alvos = [os.path.join(self.tmp, ".CONFIG", "Tune-Up", "USER.JSON"),
                 os.path.join(self.tmp, ".claude", "Settings.json"),
                 os.path.join(self.tmp, ".Claude", "SETTINGS.LOCAL.JSON"),
                 os.path.join(self.cwd, ".Tune-Up", "config.json"),
                 os.path.join(self.cwd, ".tune-up", "Config.json"),
                 os.path.join(self.dados, "Perfis_Confiaveis.txt"),
                 os.path.join(self.tmp, ".Claude", "Plugins", "x", "y.json"),
                 os.path.join(self.tmp, ".CONFIG", "TUNE-UP", "novo.json")]  # does not exist yet
        for a in alvos:
            with self.subTest(write=a):
                self.assertEqual(self.escrever(a), "perguntar")
            with self.subTest(bash=a):
                self.assertEqual(self.bash("echo x > '%s'" % a), "perguntar")
        self.assertEqual(self.bash("echo x >> ~/.claude/Settings.json"), "perguntar")
        self.assertEqual(self.bash("cp a ~/.CONFIG/tune-up/user.json"), "perguntar")

    def test_hardlink_do_user_json(self):
        u = os.path.join(self.cwd, "u.json")
        for origem in (os.path.join(self.tmp, ".config", "tune-up", "user.json"),
                       os.path.join(self.dados, "perfis_confiaveis.txt")):
            if os.path.exists(u):
                os.remove(u)
            os.link(origem, u)
            with self.subTest(origem=origem):
                self.assertEqual(self.escrever(u), "perguntar")
                self.assertEqual(self.bash("echo x > u.json"), "perguntar")
        os.remove(u)
        os.link(os.path.join(self.tmp, "user.json"), u)  # $TUNEUP_USER_JSON
        self.assertEqual(self.escrever(u), "perguntar")
        self.assertEqual(self.bash("echo x > u.json"), "perguntar")
        self.assertIsNone(self.escrever(os.path.join(self.cwd, "outro.json")))


class TestSegAncestral(SegBase):
    def test_mv_rm_cp_de_ancestral_perguntam(self):
        for cmd in ["mv ~/.config ~/c2", "mv ~/.claude ~/c3", "rm -rf ~/.claude", "rm -rf ~/.config",
                    "mv .tune-up t2", "rm -r .tune-up", "rsync -a --delete x/ ~/.config/",
                    "cp -r x ~/novo/.tune-up"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")
        os.rename(os.path.join(self.tmp, ".config"), os.path.join(self.tmp, "c2"))
        for cmd in ["mv ~/c2 ~/.config", "cp -r ~/c2 ~/.config", "rsync -a ~/c2/ ~/.config"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.bash(cmd), "perguntar")

    def test_comum_passa(self):
        os.makedirs(os.path.join(self.cwd, "dst"))
        for cmd in ["rm -rf build", "mv a.txt b.txt", "cp -r src dst", "rsync -a src/ dst/", "mv x dst"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.bash(cmd))


class TestSegProtectedPaths(SegBase):
    def test_item_ruim_nao_derruba_os_bons_e_avisa(self):
        self.user_json({"language": "pt-BR", "protected_paths": ["~/cofre", "rel/dir", 5]})
        self.assertEqual(self.escrever(os.path.join(self.tmp, "cofre", "a")), "perguntar")
        self.assertEqual(self.bash("echo x > ~/cofre/a"), "perguntar")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("protected_paths", s["systemMessage"])
        self.assertIn("rel/dir", s["systemMessage"])
        with open(os.path.join(self.dados, "erros.log"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("protected_paths ignored (not absolute): rel/dir", log)
        self.assertIn("protected_paths ignored (not text): 5", log)


class TestSegLnDePerfil(SegBase):
    def test_ln_de_pasta_tune_up_pergunta(self):  # M8: a symlinked .tune-up would inherit the trust
        a = os.path.join(self.tmp, "A", ".tune-up")
        os.makedirs(a)
        b = os.path.join(self.tmp, "B")
        os.makedirs(b)
        for cmd in ["ln -s ~/A/.tune-up .tune-up", "ln -s ../A/.tune-up ~/B/.tune-up", "ln -s ~/A/.tune-up ~/B/"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self.decisao(self.rodar("bash", {"cwd": b, "tool_name": "Bash",
                                                                  "tool_input": {"command": cmd}})), "perguntar")


if __name__ == "__main__":
    unittest.main()
