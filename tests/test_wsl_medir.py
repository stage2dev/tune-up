"""scripts/wsl/medir.sh run for real with bash, fake bwrap/sysctl/npm on PATH and a test root (unittest, stdlib)."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "scripts", "wsl", "medir.sh")

# Fake bwrap: skips its own options (as medir.sh uses them) and runs the rest; `true` honours FAKE_BWRAP_RC.
BWRAP = r"""#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    --unshare-user) shift ;;
    --ro-bind|--bind) shift 3 ;;
    --dev|--proc|--chdir) shift 2 ;;
    *) break ;;
  esac
done
[ "$1" = true ] && exit "${FAKE_BWRAP_RC:-0}"
[ -n "$FAKE_BWRAP_SEM_ECHO" ] && exit 1
exec "$@"
"""
SYSCTL = '#!/bin/sh\n[ -n "$FAKE_SYSCTL" ] || exit 255\necho "$FAKE_SYSCTL"\n'
NPM = ('#!/bin/sh\npwd > "$FAKE_NPM_PWD"\nenv | grep "^npm_config_cache=" >> "$FAKE_NPM_PWD"\n'
       'exit "${FAKE_NPM_RC:-0}"\n')


@unittest.skipIf(sys.platform == "win32", "needs bash")
class Medir(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tumed"))
        self.r = os.path.join(self.tmp, "raiz")
        self.bin = os.path.join(self.tmp, "bin")
        self.plugin = os.path.join(self.tmp, "plugin")
        node = os.path.join(self.plugin, "tune-up-studio", "node")
        for d in (self.bin, node, os.path.join(self.r, "etc"), os.path.join(self.r, "run", "WSL"),
                  os.path.join(self.r, "mnt", "c", "Windows", "System32")):
            os.makedirs(d)
        for nome in ("package.json", "package-lock.json"):
            with open(os.path.join(node, nome), "w") as f:
                f.write("{}")
        self.escrever(os.path.join(self.r, "etc", "passwd"), "root:x:0:0::/root:/bin/bash\ntuneup:x:1000:1000::/h:/bin/bash\n")
        for nome, corpo in (("bwrap", BWRAP), ("sysctl", SYSCTL), ("npm", NPM)):
            p = os.path.join(self.bin, nome)
            self.escrever(p, corpo)
            os.chmod(p, 0o755)
        self.pwd = os.path.join(self.tmp, "npm.pwd")
        self.env = {"PATH": self.bin + ":/usr/bin:/bin", "HOME": os.path.join(self.tmp, "fora"),
                    "TUNE_UP_RAIZ_TESTE": self.r, "FAKE_NPM_PWD": self.pwd, "FAKE_SYSCTL": "1"}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    @staticmethod
    def escrever(p, texto):
        with open(p, "w") as f:
            f.write(texto)

    def cmd_exe(self, rc):
        p = os.path.join(self.r, "mnt", "c", "Windows", "System32", "cmd.exe")
        self.escrever(p, "#!/bin/sh\nexit %d\n" % rc)
        os.chmod(p, 0o755)

    def rodar(self, *args, **env):
        e = dict(self.env, **env)
        return subprocess.run(["/bin/bash", SCRIPT, *args], env=e, capture_output=True, text=True, timeout=60)

    def arvore(self):
        return sorted(os.path.join(d, n) for d, _, ns in os.walk(self.r) for n in ns)

    def test_bwrap_mode_prints_m3_and_m4(self):
        p = self.rodar("--bwrap", "--plugin", self.plugin)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("M3: OK - bwrap --unshare-user true saiu com 0; sysctl apparmor_restrict_unprivileged_userns=1", p.stdout)
        self.assertIn("perfil /etc/apparmor.d/bwrap: nao", p.stdout)
        self.assertIn("M4: OK - ", p.stdout)

    def test_bwrap_failure_is_recorded_not_fatal_and_profile_is_noted(self):
        os.makedirs(os.path.join(self.r, "etc", "apparmor.d"))
        self.escrever(os.path.join(self.r, "etc", "apparmor.d", "bwrap"), "x")
        p = self.rodar("--bwrap", "--plugin", self.plugin, FAKE_BWRAP_RC="1", FAKE_SYSCTL="", FAKE_BWRAP_SEM_ECHO="1")
        self.assertEqual(p.returncode, 0)
        self.assertIn("M3: FALHOU - bwrap --unshare-user true saiu com 1; sysctl apparmor_restrict_unprivileged_userns=ausente", p.stdout)
        self.assertIn("perfil /etc/apparmor.d/bwrap: sim", p.stdout)
        self.assertIn("M4: FALHOU - ", p.stdout)

    def test_interop_mode_ok_when_cmd_exe_fails(self):
        self.cmd_exe(1)
        p = self.rodar("--interop", "--plugin", self.plugin)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("M5: OK - ", p.stdout)
        self.assertIn("binfmt_misc/WSLInterop existe: nao", p.stdout)

    def test_interop_mode_absent_cmd_exe_counts_as_failing(self):
        p = self.rodar("--interop", "--plugin", self.plugin)
        self.assertEqual(p.returncode, 0)
        self.assertIn("M5: OK - ", p.stdout)

    def test_cmd_exe_that_runs_prints_pare_and_exits_nonzero(self):
        self.cmd_exe(0)
        p = self.rodar("--interop", "--plugin", self.plugin)
        self.assertEqual(p.returncode, 9)
        self.assertIn("M5: FALHOU - PARE", p.stdout)

    def test_interop_signals_are_recorded(self):
        self.cmd_exe(1)
        self.escrever(os.path.join(self.r, "run", "WSL", "1_interop"), "")
        p = self.rodar("--interop", "--plugin", self.plugin, WSL_INTEROP="/run/WSL/1_interop")
        self.assertIn("printenv WSL_INTEROP saiu com 0", p.stdout)
        self.assertIn("*_interop em /run/WSL: 1", p.stdout)

    def test_sistema_mode_prints_m6_m7_m8_and_npm_runs_in_a_temp_dir(self):
        p = self.rodar("--sistema", "--plugin", self.plugin)
        self.assertEqual(p.returncode, 0, p.stderr)
        for m in ("M6: REGISTRO - kernel ", "M7: REGISTRO - npm ci no disco Linux levou ", "M8: OK - "):
            self.assertIn(m, p.stdout)
        with open(self.pwd) as f:
            cwd, cache = f.read().split("\n")[:2]
        self.assertTrue(cwd.startswith(tempfile.gettempdir()) or cwd.startswith("/tmp") or cwd.startswith("/var"), cwd)
        self.assertNotIn(self.plugin, cwd)
        self.assertTrue(cache.startswith("npm_config_cache=" + cwd), cache)
        self.assertFalse(os.path.exists(cwd), "temp dir deleted at the end")

    def test_uid_1000_other_than_tuneup_is_flagged(self):
        with open(os.path.join(self.r, "etc", "passwd"), "a") as f:
            f.write("ubuntu:x:1000:1000::/home/ubuntu:/bin/bash\n")
        p = self.rodar("--sistema", "--plugin", self.plugin)
        self.assertIn("M8: FALHOU - o rootfs já traz usuário com uid 1000: ubuntu", p.stdout)

    def test_npm_failure_is_recorded(self):
        p = self.rodar("--sistema", "--plugin", self.plugin, FAKE_NPM_RC="1")
        self.assertEqual(p.returncode, 0)
        self.assertIn("M7: FALHOU - npm ci saiu com 1", p.stdout)

    def test_tudo_prints_every_line_and_writes_nothing_under_the_fake_root(self):
        self.cmd_exe(1)
        antes = self.arvore()
        p = self.rodar("--tudo", "--plugin", self.plugin)
        self.assertEqual(p.returncode, 0, p.stderr)
        linhas = [l.split(":")[0] for l in p.stdout.splitlines() if l.startswith("M")]
        self.assertEqual(linhas, ["M3", "M4", "M5", "M6", "M7", "M8"])
        self.assertEqual(self.arvore(), antes)

    def test_refuses_as_root(self):
        p = self.rodar("--tudo", "--plugin", self.plugin, TUNE_UP_UID_TESTE="0")
        self.assertEqual(p.returncode, 3)
        self.assertIn("não roda como root", p.stderr)
        self.assertNotIn("M3:", p.stdout)

    def test_usage_errors(self):
        self.assertEqual(self.rodar().returncode, 2)
        self.assertEqual(self.rodar("--nada", "--plugin", self.plugin).returncode, 2)
        self.assertEqual(self.rodar("--bwrap").returncode, 2)
        self.assertEqual(self.rodar("--bwrap", "--plugin", "relativo").returncode, 2)


if __name__ == "__main__":
    unittest.main()
