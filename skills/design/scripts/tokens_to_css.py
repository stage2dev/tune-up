#!/usr/bin/env python3
"""Turn the design tokens of a DESIGN.md into CSS variables (stdlib only).

Accepted format (a tiny YAML subset, the one tune-up's design template uses):
  * the tokens live in a frontmatter block between two lines that are `---`
    (a file with no `---` is read whole);
  * 2-space indentation; `key: value` or `key:` followed by indented children;
  * values: plain, "double-quoted" or 'single-quoted' scalars; `#` starts a
    comment at line start or after a space outside quotes, so QUOTE hex colors;
  * no lists, no anchors, no multi-line scalars, no tabs;
  * references like "{colors.primary}" are allowed anywhere in a value.

Variable names:
  colors.X                  -> --color-X
  typography.X.fontFamily   -> --type-X-font-family  (camelCase -> kebab-case)
  rounded.X                 -> --rounded-X
  spacing.X                 -> --space-X
  components.X.backgroundColor -> --comp-X-background-color
  any other top-level group -> --<group>-<path>
References resolve to var(--name) of the referenced token.

Usage:
  tokens_to_css.py DESIGN.md                       print the :root block
  tokens_to_css.py DESIGN.md --prototype TEMPLATE.html --out index.html
      replaces /*TOKENS*/ with the :root block and {{name}} / {{description}}
      with the tokens' name / description; fails if a token the template
      needs is missing.
"""
import argparse
import re
import sys

GROUPS = {"colors": "color", "rounded": "rounded", "spacing": "space",
          "typography": "type", "components": "comp"}
REF = re.compile(r"\{([A-Za-z0-9_.-]+)\}")
VAR_USE = re.compile(r"var\((--[A-Za-z0-9-]+)\)")


class TokenError(ValueError):
    pass


def _strip_comment(text):
    """Drop a trailing ` # comment` that is outside quotes."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or text[i - 1] in " \t"):
            return text[:i]
    return text


def _scalar(raw):
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    return raw


def frontmatter(text):
    """Return the lines of the frontmatter block (or all lines if none)."""
    lines = text.splitlines()
    marks = [i for i, ln in enumerate(lines) if ln.strip() == "---"]
    if len(marks) >= 2 and marks[0] == 0:
        return lines[1:marks[1]]
    return lines


def parse(lines):
    """Parse the YAML subset into nested dicts of strings."""
    root = {}
    stack = [(-1, root)]
    for no, line in enumerate(lines, 1):
        if "\t" in line[: len(line) - len(line.lstrip())]:
            raise TokenError("line %d: tab indentation not supported" % no)
        body = _strip_comment(line).rstrip()
        if not body.strip():
            continue
        indent = len(body) - len(body.lstrip(" "))
        if indent % 2:
            raise TokenError("line %d: indent must be a multiple of 2" % no)
        key, sep, value = body.strip().partition(":")
        if not sep or not key or " " in key:
            raise TokenError("line %d: expected `key: value`" % no)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if not stack:
            raise TokenError("line %d: bad indentation" % no)
        parent = stack[-1][1]
        if value.strip() == "":
            child = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _scalar(value)
    return root


def kebab(name):
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"-\1", name).lower()


def flatten(tree):
    """Return {token path: value} with dotted paths, leaves only."""
    out = {}

    def walk(node, path):
        for k, v in node.items():
            p = path + [k]
            if isinstance(v, dict):
                walk(v, p)
            else:
                out[".".join(p)] = v
    walk(tree, [])
    return out


def var_name(path):
    parts = path.split(".")
    group = GROUPS.get(parts[0], kebab(parts[0]))
    return "--" + "-".join([group] + [kebab(p) for p in parts[1:]])


def resolve(value, flat):
    def sub(m):
        if m.group(1) not in flat:
            raise TokenError("broken reference {%s}" % m.group(1))
        return "var(%s)" % var_name(m.group(1))
    return REF.sub(sub, value)


def to_variables(tree):
    """Return ordered list of (css variable, css value)."""
    flat = flatten(tree)
    meta = ("name", "description")
    return [(var_name(p), resolve(v, flat)) for p, v in flat.items()
            if p not in meta]


def root_block(pairs):
    body = "\n".join("  %s: %s;" % (n, v) for n, v in pairs)
    return ":root {\n%s\n}" % body


def build_prototype(template, tree, css):
    """Fill the template; every var(--x) it uses must be defined."""
    defined = {n for n, _ in to_variables(tree)}
    missing = sorted(set(VAR_USE.findall(template)) - defined)
    if missing:
        raise TokenError("tokens missing for the template: " + ", ".join(missing))
    esc = lambda s: s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    out = template.replace("/*TOKENS*/", css)
    out = out.replace("{{name}}", esc(tree.get("name", "App")))
    return out.replace("{{description}}", esc(tree.get("description", "")))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("design")
    ap.add_argument("--prototype", help="HTML template with /*TOKENS*/")
    ap.add_argument("--out", help="output file for --prototype")
    args = ap.parse_args(argv)
    try:
        with open(args.design, encoding="utf-8") as f:
            tree = parse(frontmatter(f.read()))
        css = root_block(to_variables(tree))
        if not args.prototype:
            print(css)
            return 0
        if not args.out:
            raise TokenError("--prototype needs --out")
        with open(args.prototype, encoding="utf-8") as f:
            html = build_prototype(f.read(), tree, css)
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(html)
        print("wrote " + args.out)
        return 0
    except (TokenError, OSError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
