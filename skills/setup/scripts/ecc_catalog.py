#!/usr/bin/env python3
"""Copy the ECC skill bodies out of the (disabled) ECC plugin cache and build a catalog.

Writes only inside --out (default ~/.config/tune-up/):
  ecc-skills/<name>/...   copy of skills/<name>/ from the source, plus LICENSE
  ecc-agents/*.md         source agents whose name contains "review", plus LICENSE
  ecc-version.txt         version of the last copy; the copy is redone only when it changes
  skills-catalog.md       skills grouped by manifest module: | Skill | What it does | Path |
  use-map.json            kind of use -> ECC modules (fixed map USE_MAP below)
  manifest.json           sha256 of every file this script wrote

Safety rules:
  * a file the user changed (hash differs from manifest.json) is never overwritten;
    a pre-existing file we never wrote is treated the same way;
  * symlinks in the source are never followed or copied;
  * nothing is written outside --out; --dry-run writes nothing.

--uses a,b prints candidate skills of the mapped modules. It only pre-filters:
the final choice belongs to the skill-finder agent.

Skill and agent folder names must match NAME_RE; any other name is ignored and
listed in "skipped_invalid". Table cells escape "|" and "`".

Subcommand "install --names a,b --dest ~/.claude/skills" copies chosen skills
from <out>/ecc-skills/ (only names listed in the current skills-catalog.md),
never over an existing folder ("skipped_existing"), never through a symlink,
and removes the allowed-tools and hooks fields from the copied SKILL.md
frontmatter; a skill that runs shell on load is skipped unless named in
--allow-shell. Code and details: ecc_install.py.

Python 3.9, stdlib only. Output on stdout is one JSON object.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

# Fixed map: kind of use -> ECC modules (ids from manifests/install-modules.json).
# Hand-made because ECC has no per-use tag. Edit here to change the pre-filter.
USE_MAP = {
    "site": ["framework-language", "media-generation", "business-content", "security"],
    "landing": ["framework-language", "media-generation", "business-content"],
    "app": ["framework-language", "swift-apple", "database", "security"],
    "game": ["framework-language", "media-generation"],
    "marketing": ["business-content", "social-distribution", "media-generation", "research-apis"],
    "automation": ["agentic-patterns", "operator-workflows", "orchestration", "research-apis"],
    "backend": ["database", "devops-infra", "security"],
    "data": ["database", "devops-infra", "security", "machine-learning"],
}
DESC_MAX = 80
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
HOW_TO = (
    "# ECC skills catalog\n\n"
    "How to use: find the skill below, read its `SKILL.md` at the Path column "
    "(plus sibling files it mentions) and follow it. The ECC plugin stays "
    "disabled; only these copies are read. Pick few skills, not all.\n"
)


class CatalogError(Exception):
    pass


def vkey(text):
    """Numeric version key: '2.10.1' > '2.9.0'."""
    return tuple(int(n) for n in re.findall(r"\d+", text))


def default_source(home):
    base = os.path.join(home, ".claude", "plugins", "cache", "ecc", "ecc")
    dirs = [d for d in glob.glob(os.path.join(base, "*")) if os.path.isdir(d) and re.search(r"\d", os.path.basename(d))]
    if not dirs:
        raise CatalogError("no ECC cache found under %s (use --source)" % base)
    return max(dirs, key=lambda d: vkey(os.path.basename(d)))


def read_version(src):
    p = os.path.join(src, "VERSION")
    if os.path.isfile(p) and not os.path.islink(p):
        v = slurp(p, "r").strip()
        if v:
            return v
    return os.path.basename(os.path.normpath(src))


def slurp(path, mode="rb"):
    with open(path, mode) as fh:
        return fh.read()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def frontmatter(path):
    try:
        txt = slurp(path, "r")
    except (OSError, UnicodeDecodeError):
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---", txt, re.S)
    if not m:
        return {}
    fm, cur = {}, None
    for line in m.group(1).splitlines():
        km = re.match(r"^([A-Za-z_-]+):\s*(.*)$", line)
        if km and not line.startswith((" ", "\t")):
            cur = km.group(1)
            fm[cur] = km.group(2).strip().strip("'\"")
        elif cur and line.startswith((" ", "\t")):
            fm[cur] = (fm[cur] + " " + line.strip()).strip()
    return fm


def short(desc):
    d = re.sub(r"\s+", " ", desc or "").strip().lstrip(">|- ").strip()
    return d if len(d) <= DESC_MAX else d[:DESC_MAX].rstrip() + "..."


def esc(text):
    """Markdown table cell: escape the column bar and the backtick."""
    return text.replace("\\", "\\\\").replace("|", "\\|").replace("`", "\\`")


def code_cell(text):
    """`text` as inline code; a text with a backtick cannot be a code span, so it is escaped plain."""
    return esc(text) if "`" in text else "`%s`" % text.replace("|", "\\|")


def module_of(src):
    """skill name -> first manifest module that lists skills/<name>. Missing manifest -> {}."""
    p = os.path.join(src, "manifests", "install-modules.json")
    try:
        data = json.loads(slurp(p, "r"))
    except (OSError, ValueError):
        return {}
    out = {}
    for mod in data.get("modules", []):
        for path in mod.get("paths", []):
            if path.startswith("skills/"):
                out.setdefault(path.split("/", 1)[1].strip("/"), mod.get("id", "other"))
    return out


def list_skills(src, invalid=None):
    """Valid skill folder names; names failing NAME_RE go to invalid (if given)."""
    base = os.path.join(src, "skills")
    names = []
    if os.path.isdir(base):
        for n in sorted(os.listdir(base)):
            d = os.path.join(base, n)
            if not os.path.islink(d) and os.path.isfile(os.path.join(d, "SKILL.md")) \
                    and not os.path.islink(os.path.join(d, "SKILL.md")):
                if NAME_RE.match(n):
                    names.append(n)
                elif invalid is not None:
                    invalid.append("skills/" + n)
    return names


def list_agents(src, invalid=None):
    base = os.path.join(src, "agents")
    if not os.path.isdir(base):
        return []
    found = []
    for n in sorted(os.listdir(base)):
        if n.endswith(".md") and "review" in n.lower() and not os.path.islink(os.path.join(base, n)) \
                and os.path.isfile(os.path.join(base, n)):
            if NAME_RE.match(n):
                found.append(n)
            elif invalid is not None:
                invalid.append("agents/" + n)
    return found


def tree_files(root):
    """Relative paths of regular files under root; symlinks (file or dir) are skipped."""
    found = []
    for cur, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(cur, d))]
        for f in files:
            p = os.path.join(cur, f)
            if not os.path.islink(p) and os.path.isfile(p):
                found.append(os.path.relpath(p, root).replace(os.sep, "/"))  # same keys on every OS
    return sorted(found)


class Writer:
    """Writes files under out, honouring manifest hashes and --dry-run."""

    def __init__(self, out, dry):
        self.out = os.path.realpath(out)
        self.dry = dry
        self.mf_path = os.path.join(self.out, "manifest.json")
        self.hashes = {}
        if os.path.isfile(self.mf_path):
            try:
                self.hashes = json.loads(slurp(self.mf_path, "r")).get("files", {})
            except (OSError, ValueError):
                self.hashes = {}
        self.written = 0
        self.kept = []

    def put(self, rel, data):
        dest = os.path.join(self.out, rel)
        real_parent = os.path.realpath(os.path.dirname(dest))
        if not (real_parent == self.out or real_parent.startswith(self.out + os.sep)) or os.path.islink(dest):
            raise CatalogError("refusing to write outside the output dir: %s" % rel)
        new = sha(data)
        if os.path.isfile(dest):
            cur = sha(slurp(dest))
            if cur == new:
                self.hashes[rel] = new
                return
            if self.hashes.get(rel) != cur:  # user changed it, or we never wrote it
                self.kept.append(rel)
                return
        elif os.path.exists(dest):
            self.kept.append(rel)
            return
        self.written += 1
        self.hashes[rel] = new
        if not self.dry:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as fh:
                fh.write(data)

    def put_text(self, rel, text):
        self.put(rel, text.encode("utf-8"))

    def save(self):
        if self.dry:
            return
        os.makedirs(self.out, exist_ok=True)
        with open(self.mf_path, "w", encoding="utf-8") as fh:
            json.dump({"files": dict(sorted(self.hashes.items()))}, fh, indent=1)


def display(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


def build_catalog(src, names, out):
    mods = module_of(src)
    groups = {}
    for n in names:
        groups.setdefault(mods.get(n, "other"), []).append(n)
    order = sorted(groups, key=lambda m: (m == "other", m))
    lines = [HOW_TO]
    for m in order:
        lines += ["## %s (%d)" % (m, len(groups[m])), "", "| Skill | What it does | Path |", "|---|---|---|"]
        for n in groups[m]:
            fm = frontmatter(os.path.join(src, "skills", n, "SKILL.md"))
            path = display(os.path.join(out, "ecc-skills", n, "SKILL.md"))
            lines.append("| %s | %s | %s |" % (code_cell(n), esc(short(fm.get("description"))), code_cell(path)))
        lines.append("")
    return "\n".join(lines), groups


def run(args):
    home = os.path.expanduser("~")
    src = os.path.abspath(os.path.expanduser(args.source)) if args.source else default_source(home)
    if not os.path.isdir(os.path.join(src, "skills")):
        raise CatalogError("source has no skills/ directory: %s" % src)
    out = os.path.abspath(os.path.expanduser(args.out or "~/.config/tune-up"))
    uses = [u.strip() for u in args.uses.split(",") if u.strip()] if args.uses else []
    bad = [u for u in uses if u not in USE_MAP]
    if bad:
        raise CatalogError("unknown use(s): %s (valid: %s)" % (", ".join(bad), ",".join(USE_MAP)))

    version = read_version(src)
    invalid = []
    names = list_skills(src, invalid)
    agents = list_agents(src, invalid)
    w = Writer(out, args.dry_run)
    ver_file = os.path.join(w.out, "ecc-version.txt")
    old = slurp(ver_file, "r").strip() if os.path.isfile(ver_file) else None
    copied = old != version or not os.path.isdir(os.path.join(w.out, "ecc-skills"))
    try:  # an abort mid-copy still records what was written
        if copied:
            lic = os.path.join(src, "LICENSE")
            license_data = slurp(lic) if os.path.isfile(lic) and not os.path.islink(lic) else None
            for n in names:
                root = os.path.join(src, "skills", n)
                for rel in tree_files(root):
                    w.put(os.path.join("ecc-skills", n, rel), slurp(os.path.join(root, rel)))
            for a in agents:
                w.put(os.path.join("ecc-agents", a), slurp(os.path.join(src, "agents", a)))
            if license_data is not None:
                w.put(os.path.join("ecc-skills", "LICENSE"), license_data)
                w.put(os.path.join("ecc-agents", "LICENSE"), license_data)
            w.put_text("ecc-version.txt", version + "\n")
        catalog, groups = build_catalog(src, names, w.out)
        w.put_text("skills-catalog.md", catalog)
        w.put_text("use-map.json", json.dumps(USE_MAP, indent=1, sort_keys=True) + "\n")
    finally:
        w.save()

    result = {"version": version, "skills": len(names), "agents": len(agents), "copied": copied}
    if invalid:
        result["skipped_invalid"] = invalid
    if w.kept:
        result["kept_user_files"] = sorted(w.kept)
    if args.dry_run:
        result["dry_run"] = True
    if uses:
        wanted = []
        for u in uses:
            wanted += [m for m in USE_MAP[u] if m not in wanted]
        result["candidates"] = ["%s/%s" % (m, n) for m in wanted for n in groups.get(m, [])]
    return result


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv[:1] == ["install"]:
        import ecc_install  # the install subcommand lives there
        return ecc_install.main(argv[1:])
    ap = argparse.ArgumentParser(description="Copy ECC skills and build a catalog under --out.")
    ap.add_argument("--source", help="ECC dir (default: highest version in the plugin cache)")
    ap.add_argument("--out", help="output dir (default: ~/.config/tune-up)")
    ap.add_argument("--uses", help="comma list of: " + ",".join(USE_MAP))
    ap.add_argument("--dry-run", action="store_true", help="write nothing")
    args = ap.parse_args(argv)
    try:
        print(json.dumps(run(args)))
    except (CatalogError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
