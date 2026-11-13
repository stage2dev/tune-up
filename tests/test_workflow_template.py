import os
import re
import shutil
import subprocess
import tempfile
import unittest

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "templates", "workflow-template.js")


def read():
    with open(PATH, encoding="utf-8") as f:
        return f.read()


def code_only(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("//"))


def agent_calls(code):
    """Yield the argument text of each agent( call (balanced parens)."""
    for m in re.finditer(r"(?<![\w.])agent\(", code):
        depth, i = 1, m.end()
        while depth and i < len(code):
            depth += {"(": 1, ")": -1}.get(code[i], 0)
            i += 1
        yield code[m.end():i]


class WorkflowTemplate(unittest.TestCase):
    def test_meta_first(self):
        self.assertTrue(read().startswith("export const meta"))
        for p in ("Execute", "Review", "Fix", "Check"):
            self.assertIn("title: '%s'" % p, read())

    def test_every_agent_call_typed(self):
        calls = list(agent_calls(code_only(read())))
        self.assertGreaterEqual(len(calls), 7)
        for c in calls:
            self.assertRegex(c, r"agentType: 'tune-up:[a-z-]+'")
            self.assertRegex(c, r"model: '(opus|sonnet|haiku)'")
            self.assertRegex(c, r"effort: '(medium|high)'")

    def test_forbidden(self):
        text = read()
        for bad in ("fable", "Date.now", "Math.random"):
            self.assertNotIn(bad, text)

    def test_constants_and_reviewers(self):
        text = read()
        self.assertIn("MAX_FIXES = 2", text)
        for r in ("failures", "security", "database"):
            self.assertIn("agentType: 'tune-up:reviewer-%s'" % r, text)

    def test_no_patch_file_and_reviewer_runs_diff(self):
        text = read()
        self.assertNotIn(".patch", text)
        self.assertNotIn("do not explore", text.lower())
        self.assertIn("git status --porcelain", text)

    def test_default_lenses_and_executor_schema(self):
        text = read()
        self.assertIn("['failures', 'security']", text)
        m = re.search(r"const EXEC = \{.*?\n\}", text, re.S)
        self.assertTrue(m)
        self.assertRegex(m.group(0), r"required: \[[^\]]*'commit'")

    def test_no_agent_paren_in_comments(self):
        text = read()
        self.assertLessEqual(len(re.findall(r"\bagent\s*\(", text)),
                             len(re.findall(r"\bmodel[\"']?\s*[:=]", text)))

    def test_size(self):
        self.assertLessEqual(len(read().splitlines()), 200)

    def test_node_syntax(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node not on PATH")
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.mjs")
            # Scripts use top-level await/return; wrap the body so --check accepts it.
            body = read().replace("export const meta", "const meta", 1)
            with open(p, "w", encoding="utf-8") as f:
                f.write("export const meta = {};\nexport default async function (args, agent, parallel, pipeline, phase, log) {\n"
                        + body + "\n}\n")
            r = subprocess.run([node, "--check", p], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
