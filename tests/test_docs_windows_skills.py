"""Docs das skills no Windows: launcher scripts/py com encoding, longpaths, start, EPERM."""
import os
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def ler(skill):
    with open(os.path.join(RAIZ, "skills", skill, "SKILL.md"), encoding="utf-8") as f:
        return f.read()


class TestSkillsWindows(unittest.TestCase):
    def test_config_json_com_encoding_e_launcher(self):
        for s in ("profile", "new-project"):
            linhas = [l for l in ler(s).splitlines() if "json.load(open(" in l]
            self.assertTrue(linhas, s)
            for l in linhas:
                self.assertIn("encoding='utf-8'", l, s)
                self.assertIn('scripts/py" -c', l, s)
                self.assertNotIn("python3 -c", l, s)

    def test_plan_worktree_longpaths(self):
        linhas = [l for l in ler("plan").splitlines() if "worktree add" in l]
        self.assertTrue(linhas)
        for l in linhas:
            self.assertIn("-c core.longpaths=true worktree add", l)

    def test_design_start_windows(self):
        self.assertIn('start ""', ler("design"))

    def test_setup_aponta_eperm(self):
        self.assertIn("EPERM", ler("setup"))
        with open(os.path.join(RAIZ, "README.md"), encoding="utf-8") as f:
            self.assertIn("fails with `EPERM ... rename`", f.read())  # the section the skill points to


if __name__ == "__main__":
    unittest.main()
