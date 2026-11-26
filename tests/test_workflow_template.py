import json
import os
import sys
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
        self.assertLessEqual(len(read().splitlines()), 260)

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
import { pathToFileURL } from 'url'
const [,, file, scenario, argsJson] = process.argv
const mod = await import(pathToFileURL(file).href)
const calls = []
let n = 0
// A scenario starting with `{` scripts the replies: `commits` (executors, in order) and one list per
// reviewer label (the last one repeats); a reviewer without a list approves.
const script = scenario.startsWith('{') ? JSON.parse(scenario) : null
const ex = c => ({ commit: c, summary: 's', tests: 't', steps: 3, skills_read: ['x'], flags: 'f' })
const fake = (prompt, o) => {
  const t = o.agentType
  if (t === 'tune-up:checker') return { passed: true }
  if (script && t.startsWith('tune-up:executor') && script.commits && script.commits.length) return ex(script.commits.shift())
  if (script && t.startsWith('tune-up:reviewer')) {
    const q = script[o.label] || [{ verdict: 'approve', findings: [] }]
    return q.length > 1 ? q.shift() : q[0]
  }
  if (t.startsWith('tune-up:executor')) return ex((0x1000000 + ++n).toString(16))
  const first = !prompt.includes('PREVIOUS FINDINGS')
  const high = { sev: 'HIGH', file: 'a.py', line: 1, introduced: true, proof: 'p', title: 'bug' }
  if (scenario === 'null') return null
  if (scenario === 'clean' || (scenario === 'oneHigh' && !first)) return { verdict: 'approve', findings: [] }
  return { verdict: 'reject', findings: [high] }
}
const agent = async (prompt, o) => { calls.push({ label: o.label, prompt, model: o.model, agentType: o.agentType }); return fake(prompt, o) }
const parallel = fns => Promise.all(fns.map(f => f()))
const result = await mod.default(JSON.parse(argsJson), agent, parallel, null, () => {}, () => {})
console.log(JSON.stringify({ result, calls }))
'''


R = "review:failures:all"
OK = {"verdict": "approve", "findings": []}


def H(title, **kw):
    return dict({"sev": "HIGH", "file": "a.py", "line": 1, "introduced": True, "proof": "read", "title": title}, **kw)


def no(*findings):
    return {"verdict": "reject", "findings": list(findings)}


@unittest.skipUnless(shutil.which("node"), "node not on PATH")
class WorkflowBehaviour(unittest.TestCase):
    def run_tpl(self, scenario, args):
        args = dict({"base": "b" * 7}, worktree="/w", **args)
        scenario = scenario if isinstance(scenario, str) else json.dumps(scenario)
        with tempfile.TemporaryDirectory() as d:
            tpl, drv = os.path.join(d, "tpl.mjs"), os.path.join(d, "drv.mjs")
            body = read().replace("export const meta", "const meta", 1)
            with open(tpl, "w", encoding="utf-8") as f:
                f.write("export default async function (args, agent, parallel, pipeline, phase, log) {\n" + body + "\n}\n")
            with open(drv, "w", encoding="utf-8") as f:
                f.write(DRIVER)
            r = subprocess.run([shutil.which("node"), drv, tpl, scenario, json.dumps(args)],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)

    def part(self, **kw):
        return {"items": [], "review": dict({"commit": "c" * 7, "stat": "x", "reviewers": ["failures"]}, **kw)}

    def review(self, scenario, args):
        out = self.run_tpl(scenario, args)
        return out["result"]["review"], [c["label"] for c in out["calls"]], out["calls"]

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
        self.assertIn("git diff --no-ext-diff --ignore-submodules=none %s..1000001`" % ("c" * 7), rechecks[0]["prompt"])
        self.assertNotIn("%s.." % ("b" * 7), rechecks[0]["prompt"])

    def test_leftover_needs_you_after_two_fixes(self):
        r, labels, _ = self.review({R: [no(H("a"), H("b"), H("c")), no(H("a"), H("b")), no(H("a"))]}, self.part())
        self.assertEqual((r["status"], r["fixes"], len(r["open"])), ("need_you", 2, 1))
        self.assertEqual(len([x for x in labels if x.startswith("fix")]), 2)

    def test_count_not_dropping_needs_you(self):
        r, labels, _ = self.review({R: [no(H("a")), no(H("new"))]}, self.part())
        self.assertEqual((r["status"], r["fixes"]), ("need_you", 1))
        self.assertNotIn("check", labels)

    def test_dead_or_limited_reviewer_is_not_called_again(self):
        for reply in (None, "You've hit your usage limit"):
            r, labels, _ = self.review({R: [reply, OK]}, self.part())
            self.assertEqual((r["status"], labels), ("interrupted", [R]), reply)

    def test_invalid_answer_is_asked_once(self):
        r, labels, _ = self.review({R: [{"verdict": "approve"}, OK]}, self.part())
        self.assertEqual((r["status"], labels.count(R)), ("done", 2))
        r, labels, _ = self.review({R: [{"verdict": "approve"}]}, self.part())
        self.assertEqual((r["status"], labels.count(R)), ("interrupted", 2))

    def test_rejected_without_blocking_is_asked_once(self):
        pre = no(H("old", introduced=False))
        r, labels, calls = self.review({R: [pre, OK]}, self.part())
        self.assertEqual((r["status"], labels.count(R)), ("done", 2))
        self.assertIn("justify", calls[1]["prompt"])
        r, labels, _ = self.review({R: [pre]}, self.part())
        self.assertEqual((r["status"], labels.count(R)), ("need_you", 2))
        r, _, _ = self.review({R: [pre, None]}, self.part())
        self.assertEqual(r["status"], "interrupted")

    def test_rejects_matches_the_saved_answer_rule(self):
        sys.path.insert(0, os.path.join(os.path.dirname(PATH), "..", "scripts"))
        from tuneup.revisao import aprovado
        for v in ("approve", "APPROVED", "Approved with fixes - 0 CRITICAL, 0 HIGH, 2 MEDIUM", "aprovado com correções",
                  "**APPROVED**", "approve\nwith  notes", "approved, 1 high and 2 low", "not approved", "approve?", "approved but blocked",
                  "reject", "REJECTED", "no", "changes requested", "", "approvedx", "approve e 3 pré-existentes", "approved_"):
            r, _, _ = self.review({R: [dict(OK, verdict=v)]}, self.part())
            self.assertEqual(r["status"], "done" if aprovado(v) else "need_you", v)

    def test_reopened_blocks_whatever_introduced_says(self):
        first = no(H("a"), H("b"))
        for again in (H(" A ", introduced=False), H("other words", introduced=False, reopened=True),
                      H("a", sev="MEDIUM", introduced=False)):
            r, _, calls = self.review({R: [first, dict(OK, findings=[again])]}, self.part())
            self.assertEqual((r["status"], r["fixes"], len(r["open"])), ("need_you", 2, 1), again)
        self.assertTrue(any("same file and title, reopened: true and introduced: true" in c["prompt"] for c in calls))
        r, _, _ = self.review({R: [first, dict(OK, findings=[H("unrelated", introduced=False)])]}, self.part())
        self.assertEqual((r["status"], len(r["later"])), ("done", 1))

    def test_missing_end_reviewers_is_all_three_lenses(self):
        for lenses in (None, [], ["typo"]):
            _, labels, _ = self.review("clean", self.part(reviewers=lenses))
            self.assertEqual(labels, ["review:%s:all" % l for l in ("failures", "security", "database")] + ["check"], lenses)
        _, labels, _ = self.review({R: [no(H("a"))]}, self.part(reviewers=["failures", "failures"]))
        self.assertEqual(labels[:2], [R, "fix1.1:sonnet:part"])

    def test_bad_end_commit_is_interrupted(self):
        items = [{"id": "A", "order": "o"}]
        for name, args in (("missing", self.part(commit=None)), ("HEAD", self.part(commit="HEAD")),
                           ("base", self.part(commit="b" * 7)), ("long base", self.part(commit="b" * 40)),
                           ("stale", dict(self.part(), items=items)),
                           ("moving base", dict(self.part(), base="origin/main"))):
            r, labels, _ = self.review("clean", args)
            self.assertEqual(r["status"], "interrupted", name)
            self.assertFalse([x for x in labels if x.startswith("review") or x == "check"], name)
        for kw in ({"commit": "1000001"}, {"commit": None}):
            r, _, _ = self.review("clean", dict(self.part(**kw), items=items))
            self.assertEqual((r["status"], r["commit"]), ("done", "1000001"))

    def test_unchanged_commit_is_interrupted(self):
        for bad in ("c" * 7, "c" * 40, "b" * 7, "HEAD", ""):
            r, labels, _ = self.review({R: [no(H("a")), OK], "commits": [bad]}, self.part())
            self.assertEqual((r["status"], labels.count(R)), ("interrupted", 1), bad)
        base = lambda i, b: {"id": i, "order": "o", "base": b, "reviewers": ["failures"]}
        for commits, want in ((["b" * 7], ["interrupted", "not_run"]), (["a" * 7, "a" * 40], ["built", "interrupted"])):
            for b in (True, False):
                out = self.run_tpl({"commits": commits}, {"items": [base("A", b), base("B", b)]})
                self.assertEqual([i["status"] for i in out["result"]["items"]], want)

    def test_chunks_cover_every_file_once(self):
        two = [{"id": "front", "paths": ["src/"]}, {"id": "back", "paths": ["api"]}]
        r, labels, calls = self.review("clean", self.part(chunks=two, files=["src/a.ts", "api/b.py", "apix/c.py", "x.md"]))
        self.assertEqual(r["status"], "done")
        self.assertEqual(labels, ["review:failures:%s" % c for c in ("front", "back", "rest", "boundary")] + ["check"])
        self.assertIn('Only these paths: ["apix/c.py","x.md"]', calls[2]["prompt"])
        self.assertIn('Only these paths: ["src/a.ts"]', calls[0]["prompt"])
        _, labels, _ = self.review("clean", self.part(chunks=two, files=["src/a.ts", "api/b.py"]))
        self.assertNotIn("review:failures:rest", labels)
        for ok in (1, None, []):
            self.assertEqual(self.review("clean", self.part(chunks=ok))[1], [R, "check"], ok)

    def test_untrusted_chunks_are_interrupted(self):
        c = lambda i, *p: {"id": i, "paths": list(p)}
        f = ["a/1", "a/b/2", "z"]
        for chunks, files in ((3, f), ("2", f), ([c("x", "a"), c("y", "a/b")], f), ([c("x", "a/1"), c("x", "z")], f),
                              ([{"paths": ["a"]}, c("y", "z")], f), ([c("", "a")], f), ([c("boundary", "a")], f),
                              ([c("rest", "a")], f), ([c("x", "nope")], f), ([c("x")], f), ([{"id": "x"}], f),
                              ([c("x", "a")], None), ([c("x", "a")], [])):
            r, labels, _ = self.review("clean", self.part(chunks=chunks, files=files))
            self.assertEqual((r["status"], labels), ("interrupted", []), (chunks, files))

    def test_base_item_rejected_stops_next(self):
        out = self.run_tpl("neverCloses", {"items": [
            {"id": "A", "order": "o", "base": True}, {"id": "B", "order": "o"}]})
        self.assertEqual([i["status"] for i in out["result"]["items"]], ["need_you", "not_run"])

    def test_review_model_per_lens_and_recheck(self):
        three = self.part(reviewers=["failures", "security", "database"])
        for sev, want in (("HIGH", "sonnet"), ("CRITICAL", "opus"), ("critical", "opus")):
            sc = {"review:%s:all" % l: [no(H("a", sev=sev)), OK] for l in ("security", "database")}
            _, _, calls = self.review(sc, three)
            by = lambda label: [c["model"] for c in calls if c["label"] == label]
            self.assertEqual(set(by("review:failures:all")), {"sonnet"})
            for l in ("security", "database"):
                self.assertEqual(by("review:%s:all" % l), ["opus", want], (sev, l))

    def test_findings_remember_their_lens(self):
        _, _, calls = self.review({"review:security:all": [no(H("a")), OK]}, self.part(reviewers=["security"]))
        self.assertIn('"lens":"security"', [c for c in calls if "PREVIOUS FINDINGS" in c["prompt"]][0]["prompt"])

    def test_fix_routed_by_risk(self):
        def fixes(sc, args):
            _, _, calls = self.review(sc, args)
            return [(c["label"], c["model"], c["agentType"]) for c in calls if c["label"].startswith("fix")]
        self.assertEqual(fixes({R: [no(H("a")), OK]}, self.part()), [("fix1.1:sonnet:part", "sonnet", "tune-up:executor-sonnet")])
        self.assertEqual(fixes({R: [no(H("a", sev="critical")), OK]}, self.part())[0][1:], ("opus", "tune-up:executor-opus"))
        self.assertEqual(fixes({"review:security:all": [no(H("a")), OK]}, self.part(reviewers=["security"]))[0][0], "fix1.1:opus:part")
        self.assertEqual([f[0] for f in fixes({R: [no(H("a"), H("b")), no(H("a")), OK]}, self.part())],
                         ["fix1.1:sonnet:part", "fix2.1:opus:part"])
        for risky, want in ((True, "opus"), (False, "sonnet")):
            item = {"id": "A", "order": "o", "base": True, "risky": risky, "reviewers": ["failures"]}
            self.assertEqual(fixes({"review:failures:A": [no(H("a")), OK]}, {"items": [item]})[0][0], "fix1.1:%s:A" % want)

    def test_results_are_compact_and_complete(self):
        item = lambda i, risky, base: {"id": i, "order": "o", "risky": risky, "base": base, "reviewers": ["failures"]}
        out = self.run_tpl("clean", {"items": [item("A", True, True), item("B", False, False)]})
        a, b = out["result"]["items"]
        for e, who in ((a, "opus"), (b, "sonnet")):
            self.assertEqual((e["status"], e["executor"], e["summary"], e["tests"], e["steps"], e["skills_read"], e["flags"]),
                             ("built", who, "s", "t", 3, ["x"], "f"))
        self.assertEqual((a["commit"], b["commit"]), ("1000001", "1000002"))
        out = self.run_tpl({"commits": ["b" * 7]}, {"items": [item("A", False, True), item("B", False, True)]})
        for e in out["result"]["items"]:
            self.assertFalse({"commit", "executor", "summary", "steps"} & set(e))

    def test_order_file_line_reaches_executor_reviewer_and_fix(self):
        line = 'If the order above is an "ORDER FILE: <path>" line, Read that file first'
        item = {"id": "A", "order": "ORDER FILE: /x/o.md", "base": True, "reviewers": ["failures"]}
        _, _, calls = self.review({"review:failures:A": [no(H("a")), OK]}, {"items": [item]})
        for c in calls:
            if c["label"].startswith(("exec", "fix")) or c["label"] == "review:failures:A" and "PREVIOUS" not in c["prompt"]:
                self.assertIn(line, c["prompt"], c["label"])
                self.assertIn("ORDER FILE: /x/o.md", c["prompt"], c["label"])


if __name__ == "__main__":
    unittest.main()
