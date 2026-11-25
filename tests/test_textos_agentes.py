"""Pins the lean texts of agents, work order and part skill (item E)."""
import pathlib
import re
import unittest

from base import SCRIPT, PromptBase, sh_path

ROOT = pathlib.Path(__file__).resolve().parent.parent


def read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


EXECUTORS = ["agents/executor-opus.md", "agents/executor-sonnet.md"]
REVIEWERS = ["agents/reviewer-failures.md", "agents/reviewer-database.md",
             "agents/reviewer-security.md"]
SEARCH = EXECUTORS + REVIEWERS + ["agents/checker.md", "agents/writer.md",
                                  "agents/mapper.md"]

CAP = ("Final report: at most ~25 lines (~1.5k tokens), telegraphic (no preamble, "
       "do not repeat the order, fragments are fine); longer detail goes to a file "
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

    def test_part_review(self):
        s = read("skills/part/SKILL.md")
        for k in ["review-save", "review-pending", "rota --part", "in SEQUENCE",
                  "never counted as approved", "BASE ITEM"]:
            self.assertIn(k, s, k)
        r = read("skills/part/review.md")
        for k in ["PREVIOUS FINDINGS", "fix ONLY", "boundaries between chunks"]:
            self.assertIn(k, r, k)

    def test_checker_runs_after_the_last_fix(self):
        s = read("skills/part/SKILL.md")
        self.assertLess(s.index("END review approved"), s.index("Checker AFTER the last fix"))
        self.assertNotIn("already ran", s)
        self.assertIn("run the checker again", s)
        self.assertIn("the checker green on the final HEAD compared with main", s)
        for f in ["templates/phase/goal.md", "README.md"]:
            self.assertIn("checker` runs after the last fix" if f != "README.md" else "checker runs after the last fix", read(f), f)
            self.assertIn("on the final HEAD compared with main", read(f), f)
            self.assertNotIn("checker` once", read(f), f)
            self.assertNotIn("checker runs once", read(f), f)

    def test_pending_line_before_the_first_dispatch(self):
        s, r = read("skills/part/SKILL.md"), read("skills/part/review.md")
        self.assertIn("BEFORE the first dispatch of the Part write ONE line", s)
        self.assertIn("in progress BEFORE call 1", s)
        self.assertIn("END review approved: only then replace the pending line", s)
        self.assertIn("its approval never erases the pending line", s)
        self.assertIn("Written BEFORE the first dispatch", r)
        self.assertIn("Only the END review's approval replaces it", r)
        for t in (s, r):
            self.assertNotIn("after EVERY item", t)
            self.assertNotIn("After EVERY item", t)

    def test_answers_saved_by_file(self):
        s, r = read("skills/part/SKILL.md"), read("skills/part/review.md")
        self.assertNotIn("<<", r)
        for k in ["--answer-file", "Write tool"]:
            self.assertIn(k, s, k)
            self.assertIn(k, r, k)
        self.assertIn("<S>/answer-<lens>-<chunk>-<round>.txt", r)
        self.assertIn("the next free number", r)
        self.assertIn('"usage":true', r)
        self.assertIn("`usage` true = fix the call", s)

    def test_recheck_and_base_item_rules(self):
        for f in REVIEWERS:
            self.assertNotIn("cumulative diff", read(f), f)
            self.assertIn("same file, title and sev and `introduced:true`", read(f), f)
            self.assertIn("`line` is an integer or null", read(f), f)
            self.assertIn("equal the json", read(f), f)
        self.assertIn("Base item yes/no", read("templates/phase/brief.md"))
        self.assertIn("NO item starts while it is under review or fix", read("skills/part/SKILL.md"))
        r = read("skills/part/review.md")
        self.assertIn("blocks, whatever its `introduced` says", r)
        self.assertIn("in exactly ONE chunk", r)
        for c in re.findall(r"git diff (?!--stat)[^`\n]*<(?:base|before fix)>\.\.", r):
            self.assertIn("--no-ext-diff --ignore-submodules=none", c)

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

    def test_reuse_rule(self):
        self.assertIn("REUSE: existing functions", read("agents/mapper.md"))
        w = read("templates/work-order.md")
        self.assertIn("REUSE (from the mapper;", w)
        self.assertIn("look for an existing one (REUSE first, then rg)", w)
        for f in EXECUTORS + ["agents/executor-hard.md"]:
            self.assertIn("look for an existing one (REUSE first, then rg); reuse or extend it", read(f), f)
            self.assertIn("what was reused, or why none", read(f), f)
        self.assertIn("and REUSE per item", read("skills/part/SKILL.md"))
        r = read("agents/reviewer-failures.md")
        self.assertIn("11. Business logic copied from something that already exists: HIGH when the copies already diverge or must change together; any other duplication is MEDIUM.", r)


class ComandosDaRevisao(PromptBase):
    """Each command of the texts, filled in, passes the plugin's own Bash guard."""
    def test_guard_lets_the_exact_lines_pass(self):
        raiz, s = sh_path(str(pathlib.Path(SCRIPT).parent.parent)), sh_path(self.tmp)
        t = read("skills/part/review.md")
        cmds = re.findall(r'^(?:sh|git) .*$', t, re.M)
        self.assertEqual([re.search(r"rota --part|review-\w+|diff", c).group(0) for c in cmds],
                         ["diff", "rota --part", "review-save", "review-pending"])
        cmds += re.findall(r'`(sh "\$\{CLAUDE_PLUGIN_ROOT\}[^`]*review-pending[^`]*)`', read("skills/part/SKILL.md"))
        cmds += re.findall(r'`(sh "\$\{CLAUDE_PLUGIN_ROOT\}[^`]*review-pending[^`]*)`', read("skills/ship/SKILL.md"))
        self.assertEqual(len(cmds), 6)
        for c in cmds:
            for a, b in (("${CLAUDE_PLUGIN_ROOT}", raiz), ("<plugin>", raiz), ("<S>", s), ("<R>", s + "/my plans/review-B"),
                         ("<names>", "src/A.tsx 'src/b c.tsx'"), ("<X>", "B"), ("<base>", "b" * 7)):
                c = c.replace(a, b)
            c = re.sub(r"<absolute path of the LOCAL [^>]*>", s + "/my plans/PROGRESS.md", c)
            self.assertNotRegex(c, r"<[a-zA-Z]", c)
            self.assertIsNone(self.bash(c), c)


if __name__ == "__main__":
    unittest.main()
