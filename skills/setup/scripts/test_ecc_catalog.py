import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ecc_catalog  # noqa: E402

FIX = os.path.join(HERE, "fixtures", "ecc")


def snapshot(root):
    found = set()
    for cur, _dirs, files in os.walk(root):
        for f in files:
            found.add(os.path.relpath(os.path.join(cur, f), root))
    return found


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "home")
        self.cache = os.path.join(self.home, ".claude", "plugins", "cache", "ecc", "ecc")
        os.makedirs(self.cache)
        for v in ("2.9.0", "2.10.0"):
            shutil.copytree(os.path.join(FIX, v), os.path.join(self.cache, v))
        self.out = os.path.join(self.tmp, "out")
        old = os.environ.get("HOME")
        os.environ["HOME"] = self.home
        self.addCleanup(lambda: os.environ.__setitem__("HOME", old) if old else os.environ.pop("HOME", None))

    def run_cli(self, *args, out=True):
        argv = list(args) + (["--out", self.out] if out else [])
        so, se = io.StringIO(), io.StringIO()
        with redirect_stdout(so), redirect_stderr(se):
            code = ecc_catalog.main(argv)
        return code, so.getvalue(), se.getvalue()

    def read(self, rel):
        with open(os.path.join(self.out, rel), encoding="utf-8") as fh:
            return fh.read()

class EccCatalogTest(Base):
    def test_highest_numeric_version_default(self):
        code, so, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(so)["version"], "2.10.0")  # 2.10 > 2.9, not string order
        self.assertEqual(self.read("ecc-version.txt").strip(), "2.10.0")

    def test_copy_with_license_and_review_agents_only(self):
        res = json.loads(self.run_cli()[1])
        self.assertEqual((res["skills"], res["agents"]), (6, 1))
        self.assertTrue(os.path.isfile(os.path.join(self.out, "ecc-skills", "alpha-site", "notes.txt")))
        self.assertIn("MIT", self.read("ecc-skills/LICENSE"))
        self.assertIn("MIT", self.read("ecc-agents/LICENSE"))
        self.assertTrue(os.path.isfile(os.path.join(self.out, "ecc-agents", "code-reviewer.md")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "ecc-agents", "planner.md")))

    def test_catalog_grouped(self):
        self.run_cli()
        cat = self.read("skills-catalog.md")
        self.assertIn("How to use", cat)
        self.assertIn("## business-content (1)", cat)
        self.assertIn("## social-distribution (1)", cat)
        self.assertIn("## other (3)", cat)
        self.assertIn("| Skill | What it does | Path |", cat)
        self.assertIn("Plan paid ads and copy.", cat)
        row = [l for l in cat.splitlines() if l.startswith("| `alpha-site`")][0]
        desc = row.split("|")[2].strip()
        self.assertLessEqual(len(desc), 83)
        self.assertTrue(desc.endswith("..."))

    def test_use_map_and_candidates(self):
        code, so, _ = self.run_cli("--uses", "marketing")
        um = json.loads(self.read("use-map.json"))
        self.assertIn("business-content", um["marketing"])
        self.assertIn("framework-language", um["game"])
        self.assertIn("database", um["backend"])
        cands = json.loads(so)["candidates"]
        self.assertIn("business-content/alpha-site", cands)
        self.assertIn("social-distribution/beta-ads", cands)
        self.assertNotIn("other/gamma-misc", cands)

    def test_unknown_use_is_error(self):
        code, _, se = self.run_cli("--uses", "nope")
        self.assertNotEqual(code, 0)
        self.assertIn("unknown use", se)

    def test_no_recopy_without_version_change(self):
        src = os.path.join(self.cache, "2.10.0")
        self.run_cli("--source", src)
        marker = os.path.join(self.out, "ecc-skills", "alpha-site", "notes.txt")
        os.remove(marker)
        res = json.loads(self.run_cli("--source", src)[1])
        self.assertFalse(res["copied"])
        self.assertFalse(os.path.exists(marker))

    def test_recopy_when_version_changes(self):
        self.run_cli("--source", os.path.join(self.cache, "2.9.0"))
        res = json.loads(self.run_cli("--source", os.path.join(self.cache, "2.10.0"))[1])
        self.assertTrue(res["copied"])
        self.assertIn("2.10.0", self.read("ecc-skills/alpha-site/SKILL.md"))

    def test_user_edit_not_overwritten(self):
        self.run_cli("--source", os.path.join(self.cache, "2.9.0"))
        mine = os.path.join(self.out, "ecc-skills", "alpha-site", "SKILL.md")
        with open(mine, "w", encoding="utf-8") as fh:
            fh.write("my edit\n")
        res = json.loads(self.run_cli("--source", os.path.join(self.cache, "2.10.0"))[1])
        with open(mine, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "my edit\n")
        self.assertIn("ecc-skills/alpha-site/SKILL.md", res["kept_user_files"])

    def test_preexisting_untracked_file_kept(self):
        os.makedirs(os.path.join(self.out, "ecc-skills", "beta-ads"))
        with open(os.path.join(self.out, "ecc-skills", "beta-ads", "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("theirs\n")
        self.run_cli()
        self.assertEqual(self.read("ecc-skills/beta-ads/SKILL.md"), "theirs\n")

    def test_dry_run_writes_nothing(self):
        code, so, _ = self.run_cli("--dry-run", "--uses", "marketing")
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(so)["dry_run"])
        self.assertFalse(os.path.exists(self.out))

    def test_no_manifest_goes_to_other(self):
        src = os.path.join(self.cache, "2.10.0")
        os.remove(os.path.join(src, "manifests", "install-modules.json"))
        self.run_cli("--source", src)
        cat = self.read("skills-catalog.md")
        self.assertIn("## other (6)", cat)
        self.assertNotIn("business-content", cat)

    def test_nothing_outside_out_and_symlinks_skipped(self):
        src = os.path.join(self.cache, "2.10.0")
        secret = os.path.join(self.tmp, "secret.txt")
        with open(secret, "w", encoding="utf-8") as fh:
            fh.write("secret")
        os.symlink(secret, os.path.join(src, "skills", "alpha-site", "link.txt"))
        os.symlink(self.tmp, os.path.join(src, "skills", "alpha-site", "linkdir"))
        before = snapshot(self.tmp)
        self.run_cli("--source", src)
        new = snapshot(self.tmp) - before
        outrel = os.path.relpath(self.out, self.tmp)
        self.assertTrue(new)
        for rel in new:
            self.assertTrue(rel.startswith(outrel + os.sep), rel)
            self.assertNotIn("link", os.path.basename(rel))
        self.assertFalse(os.path.exists(os.path.join(self.out, "ecc-skills", "alpha-site", "secret.txt")))

    def test_refuses_symlinked_destination(self):
        os.makedirs(os.path.join(self.out, "ecc-skills"))
        outside = os.path.join(self.tmp, "elsewhere")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.out, "ecc-skills", "alpha-site"))
        code, _, se = self.run_cli()
        self.assertNotEqual(code, 0)
        self.assertEqual(os.listdir(outside), [])

    def test_missing_source_is_error(self):
        code, _, se = self.run_cli("--source", os.path.join(self.tmp, "nope"))
        self.assertNotEqual(code, 0)
        self.assertIn("error:", se)

    def test_invalid_names_skipped_and_cells_escaped(self):
        src = os.path.join(self.cache, "2.10.0")
        for bad in ("x$(touch PWNED)", "a|b`c", "Upper", ".hidden"):
            os.makedirs(os.path.join(src, "skills", bad))
            with open(os.path.join(src, "skills", bad, "SKILL.md"), "w", encoding="utf-8") as fh:
                fh.write("---\nname: bad\ndescription: bad\n---\n")
        with open(os.path.join(src, "agents", "x$(id)-review.md"), "w", encoding="utf-8") as fh:
            fh.write("evil\n")
        with open(os.path.join(src, "skills", "beta-ads", "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("---\nname: beta-ads\ndescription: pipe | and `tick` here\n---\n")
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)
        code, so, _ = self.run_cli("--source", src, "--uses", "marketing")
        self.assertEqual(code, 0)
        res = json.loads(so)
        self.assertEqual(res["skills"], 6)
        for bad in ("skills/x$(touch PWNED)", "skills/a|b`c", "skills/Upper", "skills/.hidden", "agents/x$(id)-review.md"):
            self.assertIn(bad, res["skipped_invalid"])
        self.assertFalse(any("PWNED" in c or "|b" in c for c in res["candidates"]))
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "PWNED")))
        self.assertFalse(os.path.exists(os.path.join(self.out, "ecc-skills", "a|b`c")))
        cat = self.read("skills-catalog.md")
        self.assertNotIn("PWNED", cat)
        row = [l for l in cat.splitlines() if l.startswith("| `beta-ads`")][0]
        self.assertIn("pipe \\| and \\`tick\\` here", row)
        self.assertEqual(len(re.findall(r"(?<!\\)\|", row)), 4)  # still 3 columns

    def test_manifest_saved_on_abort(self):
        os.makedirs(os.path.join(self.out, "ecc-skills"))
        outside = os.path.join(self.tmp, "elsewhere")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.out, "ecc-skills", "beta-ads"))  # alpha-site is written first
        code, _, _ = self.run_cli()
        self.assertNotEqual(code, 0)
        files = json.loads(self.read("manifest.json"))["files"]
        self.assertIn(os.path.join("ecc-skills", "alpha-site", "SKILL.md"), files)


class InstallTest(Base):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.run_cli()[0], 0)
        self.dest = os.path.join(self.home, ".claude", "skills")

    def install(self, names, *extra):
        return self.run_cli("install", "--names", names, "--dest", self.dest, "--out", self.out, *extra, out=False)

    def test_strips_allowed_tools_and_lists_it(self):
        code, so, _ = self.install("delta-video,alpha-site")
        self.assertEqual(code, 0)
        res = json.loads(so)
        self.assertEqual(res["installed"], ["delta-video", "alpha-site"])
        self.assertEqual(res["stripped_allowed_tools"], [{"name": "delta-video", "value": "Bash(python:*)"}])
        with open(os.path.join(self.dest, "delta-video", "SKILL.md"), encoding="utf-8") as fh:
            txt = fh.read()
        self.assertNotIn("allowed-tools", txt)
        self.assertTrue(txt.startswith("---\nname: delta-video\ndescription: Edit short videos with a script.\n---\n"))
        self.assertIn("Run the video helper.", txt)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "alpha-site", "notes.txt")))
        with open(os.path.join(self.dest, "alpha-site", "LICENSE"), encoding="utf-8") as fh:
            self.assertIn("MIT", fh.read())

    def test_strips_multiline_allowed_tools(self):
        p = os.path.join(self.out, "ecc-skills", "beta-ads", "SKILL.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("---\nname: beta-ads\nallowed-tools:\n  - Bash\n  - Write\ndescription: x\n---\nbody\n")
        res = json.loads(self.install("beta-ads")[1])
        self.assertEqual(res["stripped_allowed_tools"][0]["value"], "- Bash - Write")
        with open(os.path.join(self.dest, "beta-ads", "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "---\nname: beta-ads\ndescription: x\n---\nbody\n")

    def test_never_overwrites_existing(self):
        os.makedirs(os.path.join(self.dest, "alpha-site"))
        with open(os.path.join(self.dest, "alpha-site", "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("mine\n")
        res = json.loads(self.install("alpha-site")[1])
        self.assertEqual(res["skipped_existing"], ["alpha-site"])
        self.assertEqual(res["installed"], [])
        with open(os.path.join(self.dest, "alpha-site", "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "mine\n")

    def test_existing_symlink_not_followed(self):
        outside = os.path.join(self.tmp, "elsewhere")
        os.makedirs(outside)
        os.makedirs(self.dest)
        os.symlink(outside, os.path.join(self.dest, "beta-ads"))
        res = json.loads(self.install("beta-ads")[1])
        self.assertEqual(res["skipped_existing"], ["beta-ads"])
        self.assertEqual(os.listdir(outside), [])

    def test_rejects_unknown_and_malicious_names(self):
        os.makedirs(os.path.join(self.out, "ecc-skills", "not-listed"))
        with open(os.path.join(self.out, "ecc-skills", "not-listed", "SKILL.md"), "w", encoding="utf-8") as fh:
            fh.write("x\n")
        res = json.loads(self.install("not-listed,../etc,x$(touch PWNED),a|b`c,nope")[1])
        self.assertEqual(res["installed"], [])
        why = {r["name"]: r["why"] for r in res["rejected"]}
        self.assertEqual(why["not-listed"], "not in the catalog")
        self.assertEqual(why["nope"], "not in the catalog")
        for bad in ("../etc", "x$(touch PWNED)", "a|b`c"):
            self.assertEqual(why[bad], "invalid name")
        self.assertFalse(os.path.exists(self.dest))

    def test_source_symlink_not_followed(self):
        secret = os.path.join(self.tmp, "secret.txt")
        with open(secret, "w", encoding="utf-8") as fh:
            fh.write("secret")
        os.symlink(secret, os.path.join(self.out, "ecc-skills", "alpha-site", "leak.txt"))
        self.install("alpha-site")
        self.assertFalse(os.path.lexists(os.path.join(self.dest, "alpha-site", "leak.txt")))

    def test_dry_run_writes_nothing(self):
        res = json.loads(self.install("alpha-site,delta-video", "--dry-run")[1])
        self.assertEqual(res["installed"], ["alpha-site", "delta-video"])
        self.assertEqual(res["stripped_allowed_tools"], [{"name": "delta-video", "value": "Bash(python:*)"}])
        self.assertFalse(os.path.exists(self.dest))


    def test_strips_hooks_block_and_marks_risky(self):
        res = json.loads(self.install("epsilon-hooks")[1])
        self.assertEqual(res["installed"], ["epsilon-hooks"])
        self.assertEqual(res["risky"], [{"name": "epsilon-hooks", "why": "has hooks"}])
        self.assertEqual(res["stripped_hooks"][0]["name"], "epsilon-hooks")
        self.assertIn("./lint.sh", res["stripped_hooks"][0]["value"])
        with open(os.path.join(self.dest, "epsilon-hooks", "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "---\nname: epsilon-hooks\ndescription: Lint after each edit.\n---\n"
                                        "Keep the code tidy.\n")

    def test_strips_single_line_hooks_and_allowed_tools_together(self):
        p = os.path.join(self.out, "ecc-skills", "beta-ads", "SKILL.md")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("---\nname: beta-ads\nhooks: {}\nallowed-tools: Bash\ndescription: x\n---\nhooks: body stays\n")
        res = json.loads(self.install("beta-ads")[1])
        self.assertEqual(res["risky"], [{"name": "beta-ads", "why": "has allowed-tools, has hooks"}])
        self.assertEqual(res["stripped_hooks"], [{"name": "beta-ads", "value": "{}"}])
        with open(os.path.join(self.dest, "beta-ads", "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "---\nname: beta-ads\ndescription: x\n---\nhooks: body stays\n")

    def test_shell_skill_skipped_without_allow_shell(self):
        res = json.loads(self.install("zeta-shell,alpha-site")[1])
        self.assertEqual(res["installed"], ["alpha-site"])
        self.assertEqual(res["skipped_shell"], ["zeta-shell"])
        self.assertEqual(res["risky"], [{"name": "zeta-shell", "why": "runs shell on load"}])
        self.assertFalse(os.path.lexists(os.path.join(self.dest, "zeta-shell")))

    def test_shell_skill_installed_with_allow_shell_unchanged(self):
        res = json.loads(self.install("zeta-shell", "--allow-shell", "zeta-shell,other")[1])
        self.assertEqual(res["installed"], ["zeta-shell"])
        self.assertEqual(res["skipped_shell"], [])
        self.assertEqual(res["risky"], [{"name": "zeta-shell", "why": "runs shell on load"}])
        with open(os.path.join(self.dest, "zeta-shell", "SKILL.md"), encoding="utf-8") as fh:
            self.assertIn("\n!`git diff HEAD`\n", fh.read())

    def test_shell_detection_follows_claude_code_rule(self):
        import ecc_install
        self.assertTrue(ecc_install.runs_shell("!`ls`"))
        self.assertTrue(ecc_install.runs_shell("- diff: !`git diff`"))
        self.assertTrue(ecc_install.runs_shell("text\n```!\nls\n```\n"))
        self.assertFalse(ecc_install.runs_shell("avoid `!`, prefer `?.`"))
        self.assertFalse(ecc_install.runs_shell("Prefer `assert_eq!` over `assert!`"))
        self.assertFalse(ecc_install.runs_shell("KEY=!`cmd`"))

    def test_dry_run_reports_hooks_and_shell(self):
        res = json.loads(self.install("epsilon-hooks,zeta-shell", "--dry-run")[1])
        self.assertEqual(res["installed"], ["epsilon-hooks"])
        self.assertEqual(res["skipped_shell"], ["zeta-shell"])
        self.assertEqual([h["name"] for h in res["stripped_hooks"]], ["epsilon-hooks"])
        self.assertEqual([r["name"] for r in res["risky"]], ["epsilon-hooks", "zeta-shell"])
        self.assertFalse(os.path.exists(self.dest))

if __name__ == "__main__":
    unittest.main()
