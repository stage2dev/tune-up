import json
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
        self.assertIn("DEFAULT_LENSES = ['failures', 'security']", text)

    def test_design_markers(self):
        code = code_only(read())
        self.assertNotIn("pipeline(", code)   # items run in sequence
        self.assertIn("boundary", code)
        self.assertIn("PREVIOUS FINDINGS", code)
        self.assertIn("${before}..${commit}", code)   # recheck sees only the fix diff

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
        self.assertLessEqual(len(read().splitlines()), 240)

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


DRIVER = '''
import fs from 'fs'
const [,, file, scenario, argsJson] = process.argv
const mod = await import(file)
const calls = []
let n = 0
const fake = (prompt, o) => {
  const t = o.agentType
  if (t === 'tune-up:checker') return { passed: true }
  if (t.startsWith('tune-up:executor')) return { commit: (0x1000000 + ++n).toString(16), summary: 's', tests: 't' }
  const first = !prompt.includes('PREVIOUS FINDINGS')
  const high = { sev: 'HIGH', file: 'a.py', line: 1, introduced: true, proof: 'p', title: 'bug' }
  if (scenario === 'null') return null
  if (scenario === 'clean' || (scenario === 'oneHigh' && !first)) return { verdict: 'approve', findings: [] }
  return { verdict: 'reject', findings: [high] }
}
const agent = async (prompt, o) => { calls.push({ label: o.label, prompt }); return fake(prompt, o) }
const parallel = fns => Promise.all(fns.map(f => f()))
const result = await mod.default(JSON.parse(argsJson), agent, parallel, null, () => {}, () => {})
console.log(JSON.stringify({ result, calls }))
'''


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class WorkflowBehaviour(unittest.TestCase):
    def run_tpl(self, scenario, args):
        args = dict(args, base="b" * 7, worktree="/w")
        with tempfile.TemporaryDirectory() as d:
            tpl, drv = os.path.join(d, "tpl.mjs"), os.path.join(d, "drv.mjs")
            body = read().replace("export const meta", "const meta", 1)
            with open(tpl, "w", encoding="utf-8") as f:
                f.write("export default async function (args, agent, parallel, pipeline, phase, log) {\n" + body + "\n}\n")
            with open(drv, "w", encoding="utf-8") as f:
                f.write(DRIVER)
            r = subprocess.run([shutil.which("node"), drv, tpl, scenario, json.dumps(args)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)

    def part(self, **kw):
        return {"items": [], "review": dict({"commit": "c" * 7, "stat": "x"}, **kw)}

    def test_no_review_is_pending_never_done(self):
        out = self.run_tpl("clean", {"items": [{"id": "A", "order": "o"}, {"id": "B", "order": "o"}]})
        self.assertEqual(out["result"]["review"], "pending")
        self.assertEqual([i["status"] for i in out["result"]["items"]], ["built", "built"])
        self.assertIsNone(out["result"]["check"])

    def test_one_high_then_clean_recheck(self):
        out = self.run_tpl("oneHigh", self.part())
        r = out["result"]["review"]
        self.assertEqual((r["status"], r["fixes"]), ("done", 1))
        fixes = [c for c in out["calls"] if c["label"].startswith("fix")]
        self.assertEqual(len(fixes), 1)
        rechecks = [c for c in out["calls"] if "PREVIOUS FINDINGS" in c["prompt"]]
        self.assertTrue(rechecks)
        self.assertIn("git diff %s..1000001" % ("c" * 7), rechecks[0]["prompt"])
        self.assertNotIn("git diff %s.." % ("b" * 7), rechecks[0]["prompt"])

    def test_never_closes_needs_you_after_two_fixes(self):
        out = self.run_tpl("neverCloses", self.part())
        r = out["result"]["review"]
        self.assertEqual((r["status"], r["fixes"]), ("need_you", 2))
        self.assertEqual(len([c for c in out["calls"] if c["label"].startswith("fix")]), 2)

    def test_reviewer_null_twice_is_interrupted(self):
        out = self.run_tpl("null", self.part())
        self.assertEqual(out["result"]["review"]["status"], "interrupted")
        self.assertEqual(len([c for c in out["calls"] if c["label"].startswith("review:failures")]), 2)

    def test_boundary_unit_when_several_chunks(self):
        out = self.run_tpl("clean", self.part(chunks=[{"id": "front", "paths": ["a"]}, {"id": "back", "paths": ["b"]}]))
        self.assertTrue(any(c["label"] == "review:failures:boundary" for c in out["calls"]))

    def test_base_item_rejected_stops_next(self):
        out = self.run_tpl("neverCloses", {"items": [
            {"id": "A", "order": "o", "base": True}, {"id": "B", "order": "o"}]})
        self.assertEqual([i["status"] for i in out["result"]["items"]], ["need_you", "not_run"])


if __name__ == "__main__":
    unittest.main()
