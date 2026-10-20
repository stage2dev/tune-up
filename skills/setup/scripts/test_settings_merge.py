import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import settings_merge  # noqa: E402

FLAG = "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS=1"


class SettingsMergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "settings.json")

    def write(self, text):
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def read(self):
        with open(self.path, encoding="utf-8") as fh:
            return fh.read()

    def run_cli(self, *pairs):
        argv = []
        for p in pairs:
            argv += ["--set-env", p]
        so, se = io.StringIO(), io.StringIO()
        with redirect_stdout(so), redirect_stderr(se):
            code = settings_merge.main(argv + ["--path", self.path])
        return code, so.getvalue(), se.getvalue()

    def backups(self):
        return sorted(f for f in os.listdir(self.tmp) if ".bak-tune-up-" in f)

    def test_merge_keeps_every_other_key(self):
        orig = {"model": "opus", "permissions": {"allow": ["Read"]}, "env": {"OTHER": "x"}, "hooks": {}}
        self.write(json.dumps(orig))
        code, so, _ = self.run_cli(FLAG, "CLAUDE_MEM_TELEMETRY=0")
        self.assertEqual(code, 0)
        res = json.loads(so)
        self.assertTrue(res["written"])
        got = json.loads(self.read())
        want = dict(orig, env={"OTHER": "x", "CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1", "CLAUDE_MEM_TELEMETRY": "0"})
        self.assertEqual(got, want)
        self.assertEqual(res["changed"]["CLAUDE_MEM_TELEMETRY"], {"before": None, "after": "0"})

    def test_invalid_json_writes_nothing(self):
        self.write('{"env": {,}')
        code, _, se = self.run_cli(FLAG)
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", se)
        self.assertEqual(self.read(), '{"env": {,}')
        self.assertEqual(os.listdir(self.tmp), ["settings.json"])

    def test_non_object_env_writes_nothing(self):
        self.write('{"env": []}')
        self.assertEqual(self.run_cli(FLAG)[0], 1)
        self.assertEqual(self.read(), '{"env": []}')

    def test_dated_backup_never_replaced(self):
        self.write('{"a": 1}')
        self.run_cli(FLAG)
        self.run_cli("CLAUDE_MEM_TELEMETRY=0")
        baks = self.backups()
        self.assertEqual(len(baks), 2)
        for b in baks:
            self.assertRegex(b, r"^settings\.json\.bak-tune-up-\d{8}-\d{6}(-\d+)?$")
        with open(os.path.join(self.tmp, baks[0]), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), '{"a": 1}')

    def test_refuses_secret_like_keys(self):
        self.write('{"a": 1}')
        for key in ("TYPESAFE_API_KEY", "GH_TOKEN", "client_secret", "DB_PASSWORD"):
            code, _, se = self.run_cli(FLAG, key + "=abc")
            self.assertEqual(code, 1, key)
            self.assertIn("secret", se)
        self.assertEqual(self.read(), '{"a": 1}')
        self.assertEqual(self.backups(), [])

    def test_bad_pair_rejected(self):
        self.write('{"a": 1}')
        self.assertEqual(self.run_cli("NOEQUALS")[0], 1)
        self.assertEqual(self.run_cli("BAD-NAME=1")[0], 1)
        self.assertEqual(self.read(), '{"a": 1}')

    def test_no_change_no_write_no_backup(self):
        self.write('{"env": {"CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1"}}')
        res = json.loads(self.run_cli(FLAG)[1])
        self.assertFalse(res["written"])
        self.assertEqual(self.backups(), [])

    def test_missing_file_created(self):
        res = json.loads(self.run_cli(FLAG)[1])
        self.assertTrue(res["written"])
        self.assertNotIn("backup", res)
        self.assertEqual(json.loads(self.read()), {"env": {"CLAUDE_CODE_ENABLE_FUNCTION_HOOKS": "1"}})

    def test_atomic_failure_leaves_original(self):
        self.write('{"keep": true}')
        with mock.patch.object(settings_merge.os, "replace", side_effect=OSError("disk full")):
            code, _, se = self.run_cli(FLAG)
        self.assertEqual(code, 1)
        self.assertEqual(self.read(), '{"keep": true}')
        self.assertFalse([f for f in os.listdir(self.tmp) if f.endswith(".tmp")])

    def test_uses_temp_file_in_same_folder(self):
        self.write('{"keep": true}')
        seen = []
        real = os.replace

        def spy(src, dst):
            seen.append((os.path.dirname(src), dst))
            return real(src, dst)

        with mock.patch.object(settings_merge.os, "replace", side_effect=spy):
            self.assertEqual(self.run_cli(FLAG)[0], 0)
        self.assertEqual(seen, [(self.tmp, self.path)])

    def test_concurrent_change_aborts(self):
        self.write('{"keep": true}')
        real = settings_merge.write_atomic

        def racing(path, data, st):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('{"other": "writer"}')
            return real(path, data, st)

        with mock.patch.object(settings_merge, "write_atomic", side_effect=racing):
            code, _, se = self.run_cli(FLAG)
        self.assertEqual(code, 1)
        self.assertIn("changed on disk", se)
        self.assertEqual(self.read(), '{"other": "writer"}')

    def test_output_is_valid_indented_json(self):
        self.write('{"a": 1}')
        self.run_cli(FLAG)
        text = self.read()
        self.assertTrue(re.search(r'^  "env": \{', text, re.M))
        json.loads(text)


if __name__ == "__main__":
    unittest.main()
