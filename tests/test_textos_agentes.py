"""Pins the lean texts of agents, work order and part skill (item E)."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


EXECUTORS = ["agents/executor-opus.md", "agents/executor-sonnet.md"]
REVIEWERS = ["agents/reviewer-failures.md", "agents/reviewer-database.md",
             "agents/reviewer-security.md"]
SEARCH = EXECUTORS + REVIEWERS + ["agents/checker.md", "agents/writer.md",
                                  "agents/mapper.md"]

CAP = ("Final report: at most ~25 lines (~1.5k tokens), telegraphic; longer detail goes to a file "
       "in the scratchpad, cited by its absolute path. CRITICAL/HIGH findings are never cut.")
CAPPED = [f"agents/{n}.md" for n in (
    "executor-sonnet", "executor-opus", "executor-hard", "reviewer-failures", "reviewer-database",
    "reviewer-security", "mapper", "checker", "writer", "researcher", "plan-reviewer", "visual",
    "skill-finder")]


class TextosAgentes(unittest.TestCase):
    def test_search_rules(self):
        for f in SEARCH:
            t = read(f)
            self.assertIn("| head -60", t, f)
            self.assertIn("git log -n 30", t, f)

    def test_no_whole_goal(self):
        for f in EXECUTORS + REVIEWERS + ["templates/work-order.md"]:
            self.assertIn("never read the whole goal or progress document", read(f), f)

    def test_executor_steps(self):
        for f in EXECUTORS:
            self.assertIn("~80", read(f), f)
        for f in ["templates/work-order.md", "templates/phase/goal.md", "skills/part/SKILL.md"]:
            self.assertIn("~80", read(f), f)

    def test_no_old_number(self):
        for d in ["agents", "templates", "skills"]:
            for p in (ROOT / d).rglob("*"):
                if p.is_file() and p.suffix in (".md", ".js", ".py", ".json"):
                    self.assertNotIn("~150", p.read_text(encoding="utf-8"), str(p))

    def test_reviewers(self):
        for f in REVIEWERS:
            t = read(f)
            self.assertIn("suspected", t, f)
            self.assertIn("keep the severity", t, f)
            self.assertIn("Every other finding without proof is reported with proof \"suspected\" (severity as judged), never presented as proven.", t, f)
            self.assertIn("never a whole file except the patch;", t, f)
            self.assertNotIn("Group LOW", t, f)
            self.assertNotIn("N LOW", t, f)
            self.assertNotIn("lower the severity", t, f)

    def test_work_order_literal(self):
        t = read("templates/work-order.md")
        self.assertIn("LITERALLY", t)
        self.assertIn("never the whole list", t)

    def test_part_short(self):
        n = len(read("skills/part/SKILL.md").splitlines())
        self.assertLess(n, 100)
        self.assertIn("at most 3 MEDIUM", read("skills/part/SKILL.md"))

    def test_coordinator_defaults_to_opus(self):
        import glob
        files = ["skills/part/SKILL.md", "skills/plan/SKILL.md",
                 "templates/phase/goal.md"]
        for f in files:
            text = read(f)
            self.assertNotIn("highest effort", text, f)
            lines = [l for l in text.splitlines() if "main session" in l]
            self.assertTrue(any("Opus, high effort, by default" in l and
                                "Fable only when the owner opened the session in Fable" in l
                                for l in lines), f)
        prog = read("templates/phase/progress.md")
        self.assertIn("Opus, high effort, by default", prog)
        self.assertNotIn("at the highest", prog)
        for f in glob.glob(str(ROOT / "skills/*/SKILL.md")):
            self.assertNotIn("highest effort",
                             pathlib.Path(f).read_text(encoding="utf-8"), f)


    def test_report_cap(self):
        for f in CAPPED:
            self.assertIn(CAP, read(f), f)
        allm = {f"agents/{p.name}" for p in (ROOT / "agents").glob("*.md")} - {"agents/persona.md"}
        self.assertEqual(allm, set(CAPPED))


if __name__ == "__main__":
    unittest.main()
