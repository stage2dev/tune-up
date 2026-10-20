#!/usr/bin/env python3
"""Merge environment flags into Claude Code's settings.json, and nothing else.

Usage: settings_merge.py --set-env KEY=VALUE [--set-env KEY=VALUE ...] [--path FILE]
Default --path: ~/.claude/settings.json.

Steps:
  * read the file; invalid JSON (or not an object, or "env" not an object) -> stop, write nothing;
  * refuse any key whose name looks like a secret (KEY, TOKEN, SECRET, PASSWORD):
    secrets never go through this script;
  * values already equal -> write nothing;
  * backup <file>.bak-tune-up-<YYYYMMDD-HHMMSS> (never replaces an older backup);
  * set only the requested env keys, keep every other key as it was;
  * write a temporary file in the same folder, then os.replace (atomic);
    if the file changed on disk since it was read, stop before replacing;
  * read it back and check it equals the expected object.

Python 3.9, stdlib only. Output on stdout is one JSON object; errors go to stderr
as "error: ..." with exit code 1.
"""
import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import time

KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SECRET_RE = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.I)
BACKUP_SUFFIX = ".bak-tune-up-"


class MergeError(Exception):
    pass


def parse_pairs(pairs):
    out = {}
    for pair in pairs:
        if "=" not in pair:
            raise MergeError("expected KEY=VALUE, got %r" % pair)
        key, value = pair.split("=", 1)
        if not KEY_RE.match(key):
            raise MergeError("invalid env name: %r" % key)
        if SECRET_RE.search(key):
            raise MergeError("refusing %s: looks like a secret; secrets never go in settings.json" % key)
        out[key] = value
    return out


def load(path):
    """(data, stat) of the file; ({}, None) when it does not exist."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
            st = os.fstat(fh.fileno())
    except FileNotFoundError:
        return {}, None
    try:
        data = json.loads(text)
    except ValueError as e:
        raise MergeError("%s is not valid JSON (%s); nothing written" % (path, e))
    if not isinstance(data, dict):
        raise MergeError("%s is not a JSON object; nothing written" % path)
    if not isinstance(data.get("env", {}), dict):
        raise MergeError("%s: \"env\" is not an object; nothing written" % path)
    return data, st


def backup(path):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = path + BACKUP_SUFFIX + stamp
    n = 1
    while os.path.lexists(dest):
        dest = "%s%s%s-%d" % (path, BACKUP_SUFFIX, stamp, n)
        n += 1
    shutil.copy2(path, dest)
    return dest


def same_file_state(path, st):
    try:
        now = os.stat(path)
    except FileNotFoundError:
        return st is None
    return st is not None and (now.st_mtime_ns, now.st_size, now.st_ino) == (st.st_mtime_ns, st.st_size, st.st_ino)


def write_atomic(path, data, st):
    folder = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(prefix=".settings-tune-up-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, (st.st_mode & 0o777) if st is not None else 0o600)
        if not same_file_state(path, st):
            raise MergeError("%s changed on disk while merging; nothing written, run again" % path)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def merge(path, wanted):
    path = os.path.realpath(os.path.expanduser(path))
    data, st = load(path)
    env = dict(data.get("env", {}))
    changed = {k: {"before": env.get(k), "after": v} for k, v in wanted.items() if env.get(k) != v}
    result = {"path": path, "changed": changed, "unchanged": sorted(k for k in wanted if k not in changed)}
    if not changed:
        result["written"] = False
        return result
    if st is not None:
        result["backup"] = backup(path)
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    env.update(wanted)
    expected = dict(data)
    expected["env"] = env
    write_atomic(path, expected, st)
    with open(path, encoding="utf-8") as fh:
        if json.load(fh) != expected:
            raise MergeError("read-back check failed for %s; restore %s" % (path, result.get("backup", "it")))
    result["written"] = True
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Set env keys in Claude Code settings.json (no secrets).")
    ap.add_argument("--set-env", action="append", required=True, metavar="KEY=VALUE")
    ap.add_argument("--path", default="~/.claude/settings.json", help="settings file (default ~/.claude/settings.json)")
    args = ap.parse_args(argv)
    try:
        print(json.dumps(merge(args.path, parse_pairs(args.set_env))))
    except (MergeError, OSError) as e:
        print("error: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
