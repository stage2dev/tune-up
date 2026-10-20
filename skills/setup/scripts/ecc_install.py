#!/usr/bin/env python3
"""Subcommand "install" of ecc_catalog.py, kept apart so each file stays small.

install --names a,b --dest ~/.claude/skills [--allow-shell a] [--dry-run]
copies chosen skills from <out>/ecc-skills/ (only names listed in the current
skills-catalog.md), never over an existing folder ("skipped_existing"), never
through a symlink. In the copied SKILL.md frontmatter it removes the
allowed-tools field ("stripped_allowed_tools") and the hooks field
("stripped_hooks"), so the copy asks permission like any other skill and runs
no hook. A SKILL.md with a "!`cmd`" placeholder (start of line or after
whitespace) or a "```!" block runs shell when loaded; it is never edited, only
copied when its name is also in --allow-shell, otherwise listed in
"skipped_shell". Every chosen skill with any of these is listed in "risky".

Python 3.9, stdlib only. Output on stdout is one JSON object.
"""
import argparse
import json
import os
import re
import sys

from ecc_catalog import NAME_RE, CatalogError, slurp, tree_files

ALLOWED_RE = re.compile(r"^allowed[-_]tools\s*:")
HOOKS_RE = re.compile(r"^hooks\s*:")
# Same rule Claude Code uses: inline "!`" only at line start or after whitespace.
SHELL_RE = re.compile(r"(?:^|(?<=\s))!`[^`]+`|^[ \t]*```+!", re.M)


def strip_field(text, key_re):
    """Remove one top-level frontmatter field (and its indented/list lines).
    Returns (new_text, removed_value or None). Body and other fields are untouched."""
    m = re.match(r"^(---[ \t]*\r?\n)(.*?\r?\n)(---)", text, re.S)
    if not m:
        return text, None
    kept, removed, inside = [], [], False
    for line in m.group(2).splitlines(True):
        if key_re.match(line):
            inside = True
            removed.append(line.split(":", 1)[1].strip())
            continue
        if inside and (line[:1] in (" ", "\t") or line.lstrip().startswith("- ")):
            removed.append(line.strip())
            continue
        inside = False
        kept.append(line)
    if not removed:
        return text, None
    value = " ".join(r for r in removed if r)
    return m.group(1) + "".join(kept) + text[m.start(3):], value


def strip_allowed_tools(text):
    return strip_field(text, ALLOWED_RE)


def runs_shell(text):
    return SHELL_RE.search(text) is not None


def catalog_names(out):
    """Skill names listed in <out>/skills-catalog.md (first column)."""
    try:
        txt = slurp(os.path.join(out, "skills-catalog.md"), "r")
    except OSError:
        raise CatalogError("no skills-catalog.md under %s (run the catalog first)" % out)
    return set(re.findall(r"^\| `([^`|]+)` \|", txt, re.M))


def write_new(path, data):
    """Create a new regular file; never follows or replaces an existing path."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def split_names(text):
    names = []
    for n in (x.strip() for x in (text or "").split(",")):
        if n and n not in names:
            names.append(n)
    return names


def install(args):
    out = os.path.realpath(os.path.expanduser(args.out or "~/.config/tune-up"))
    dest = os.path.realpath(os.path.expanduser(args.dest))
    base = os.path.join(out, "ecc-skills")
    listed = catalog_names(out)
    res = {"installed": [], "skipped_existing": [], "rejected": [], "stripped_allowed_tools": [],
           "stripped_hooks": [], "risky": [], "skipped_shell": []}
    allow_shell = set(split_names(getattr(args, "allow_shell", None)))
    lic = os.path.join(base, "LICENSE")
    license_data = slurp(lic) if os.path.isfile(lic) and not os.path.islink(lic) else None
    for n in split_names(args.names):
        src = os.path.join(base, n)
        if not NAME_RE.match(n):
            res["rejected"].append({"name": n, "why": "invalid name"})
            continue
        if n not in listed:
            res["rejected"].append({"name": n, "why": "not in the catalog"})
            continue
        if os.path.islink(src) or not os.path.isdir(src) or os.path.islink(os.path.join(src, "SKILL.md")) \
                or not os.path.isfile(os.path.join(src, "SKILL.md")):
            res["rejected"].append({"name": n, "why": "no regular copy in ecc-skills"})
            continue
        target = os.path.join(dest, n)
        if os.path.lexists(target):
            res["skipped_existing"].append(n)
            continue
        original = slurp(os.path.join(src, "SKILL.md")).decode("utf-8", "surrogateescape")
        skill, tools = strip_allowed_tools(original)
        skill, hooks = strip_field(skill, HOOKS_RE)
        shell = runs_shell(original)
        why = [w for w, hit in (("has allowed-tools", tools is not None), ("has hooks", hooks is not None),
                                ("runs shell on load", shell)) if hit]
        if why:
            res["risky"].append({"name": n, "why": ", ".join(why)})
        if shell and n not in allow_shell:
            res["skipped_shell"].append(n)
            continue
        if tools is not None:
            res["stripped_allowed_tools"].append({"name": n, "value": tools})
        if hooks is not None:
            res["stripped_hooks"].append({"name": n, "value": hooks})
        if args.dry_run:
            res["installed"].append(n)
            continue
        os.makedirs(dest, exist_ok=True)
        os.mkdir(target)
        files = tree_files(src)
        for rel in files:
            data = skill.encode("utf-8", "surrogateescape") if rel == "SKILL.md" else slurp(os.path.join(src, rel))
            path = os.path.join(target, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.realpath(os.path.dirname(path)) != os.path.dirname(path):
                raise CatalogError("refusing to write through a symlink: %s" % path)
            write_new(path, data)
        if license_data is not None and "LICENSE" not in files:
            write_new(os.path.join(target, "LICENSE"), license_data)
        res["installed"].append(n)
    if args.dry_run:
        res["dry_run"] = True
    return res


def main(argv):
    ap = argparse.ArgumentParser(prog="ecc_catalog.py install",
                                 description="Copy chosen catalog skills to --dest without allowed-tools or hooks.")
    ap.add_argument("--names", required=True, help="comma list of skill names from the catalog")
    ap.add_argument("--dest", required=True, help="skills dir, e.g. ~/.claude/skills")
    ap.add_argument("--out", help="catalog dir (default: ~/.config/tune-up)")
    ap.add_argument("--allow-shell", help="comma list of names that may keep shell run on load")
    ap.add_argument("--dry-run", action="store_true", help="write nothing")
    args = ap.parse_args(argv)
    try:
        print(json.dumps(install(args)))
    except (CatalogError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
