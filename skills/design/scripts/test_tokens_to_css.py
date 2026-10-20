import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tokens_to_css as t  # noqa: E402

TEMPLATE = os.path.join(HERE, "..", "templates", "prototype.html")
SAMPLE = '''---
name: "Sample App"
description: A sample # trailing comment
colors:
  primary: "#112233"   # brand
  secondary: '#445566'
  surface: "#ffffff"
  text: "#111111"
  error: "#cc0000"
typography:
  body:
    fontFamily: "Inter, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: "1.5"
  heading:
    fontFamily: "Inter, sans-serif"
    fontSize: "32px"
    fontWeight: 700
rounded:
  md: "8px"
spacing:
  sm: "8px"
  md: "16px"
  lg: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    rounded: "{rounded.md}"
---

# Prose with: colons
'''


class ParseTests(unittest.TestCase):
    def tree(self, text=SAMPLE):
        return t.parse(t.frontmatter(text))

    def test_nested_and_quotes(self):
        tr = self.tree()
        self.assertEqual(tr["colors"]["primary"], "#112233")
        self.assertEqual(tr["colors"]["secondary"], "#445566")
        self.assertEqual(tr["typography"]["body"]["fontWeight"], "400")

    def test_comment_rules(self):
        tr = self.tree()
        self.assertEqual(tr["description"], "A sample")
        tr2 = t.parse(['a: "x # y"', 'b: #fff'])
        self.assertEqual(tr2["a"], "x # y")
        self.assertEqual(tr2["b"], {})  # unquoted `#fff` is a comment: quote hex colors

    def test_prose_ignored(self):
        self.assertNotIn("Prose with", str(self.tree()))

    def test_no_frontmatter_reads_whole(self):
        self.assertEqual(self.tree("a:\n  b: 1\n"), {"a": {"b": "1"}})

    def test_bad_indent_and_tab(self):
        with self.assertRaises(t.TokenError):
            t.parse(["a:", "   b: 1"])
        with self.assertRaises(t.TokenError):
            t.parse(["a:", "\tb: 1"])
        with self.assertRaises(t.TokenError):
            t.parse(["just text"])


class NameTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(t.var_name("colors.primary"), "--color-primary")
        self.assertEqual(t.var_name("typography.body.fontFamily"), "--type-body-font-family")
        self.assertEqual(t.var_name("spacing.lg"), "--space-lg")
        self.assertEqual(t.var_name("rounded.md"), "--rounded-md")
        self.assertEqual(t.var_name("components.button-primary.backgroundColor"),
                         "--comp-button-primary-background-color")
        self.assertEqual(t.var_name("shadows.cardSoft"), "--shadows-card-soft")


class CssTests(unittest.TestCase):
    def css(self):
        return t.root_block(t.to_variables(t.parse(t.frontmatter(SAMPLE))))

    def test_root_block(self):
        css = self.css()
        self.assertTrue(css.startswith(":root {"))
        self.assertIn("--color-primary: #112233;", css)
        self.assertIn("--type-heading-font-weight: 700;", css)
        self.assertNotIn("--name", css)

    def test_reference_resolved(self):
        self.assertIn("--comp-button-primary-background-color: var(--color-primary);", self.css())
        self.assertIn("--comp-button-primary-rounded: var(--rounded-md);", self.css())

    def test_broken_reference(self):
        with self.assertRaises(t.TokenError):
            t.to_variables({"components": {"x": {"c": "{colors.nope}"}}})


class PrototypeTests(unittest.TestCase):
    def run_cli(self, design_text, out):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "DESIGN.md")
            with open(src, "w", encoding="utf-8") as f:
                f.write(design_text)
            dst = os.path.join(d, out)
            r = subprocess.run([sys.executable, os.path.join(HERE, "tokens_to_css.py"), src,
                                "--prototype", TEMPLATE, "--out", dst],
                               capture_output=True, text=True)
            html = open(dst, encoding="utf-8").read() if os.path.exists(dst) else None
            return r, html

    def test_prototype_offline_and_filled(self):
        r, html = self.run_cli(SAMPLE, "index.html")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--color-primary: #112233;", html)
        self.assertIn("Sample App", html)
        self.assertNotIn("/*TOKENS*/", html)
        self.assertNotIn("{{", html)
        self.assertNotIn("http", html)
        self.assertNotIn("<link", html)
        self.assertNotIn("<script src", html)

    def test_missing_token_fails(self):
        r, html = self.run_cli(SAMPLE.replace('  error: "#cc0000"\n', ""), "index.html")
        self.assertEqual(r.returncode, 1)
        self.assertIn("--color-error", r.stderr)
        self.assertIsNone(html)

    def test_name_is_escaped(self):
        tree = t.parse(t.frontmatter(SAMPLE))
        tree["name"] = "<b>&"
        with open(TEMPLATE, encoding="utf-8") as f:
            html = t.build_prototype(f.read(), tree, t.root_block(t.to_variables(tree)))
        self.assertIn("&lt;b&gt;&amp;", html)

    def test_cli_prints_root(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "D.md")
            open(src, "w", encoding="utf-8").write(SAMPLE)
            r = subprocess.run([sys.executable, os.path.join(HERE, "tokens_to_css.py"), src],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)
            self.assertIn(":root {", r.stdout)

    def test_missing_file(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "tokens_to_css.py"), "/nonexistent/x.md"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
