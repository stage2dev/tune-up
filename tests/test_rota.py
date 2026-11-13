"""Testes do `guarda.py rota`: executor e revisores pelos caminhos. Rode: python3 -m unittest tests.test_rota"""
import json
import os
import subprocess
import sys
import unittest

from base import SCRIPT, Base

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import rota as R  # noqa: E402

with open(os.path.join(os.path.dirname(SCRIPT), "padrao.json"), encoding="utf-8") as _f:
    PADRAO = json.load(_f)
OPUS, SONNET = R.OPUS, R.SONNET


class TestRotaUnidade(Base):
    USER_JSON = None

    def diff(self, texto, nome="d.patch"):
        p = os.path.join(self.tmp, nome)
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        return p

    def rota(self, files, diff="", failed=None, cfg=None, raiz="/repo"):
        if diff == "":
            diff = self.diff("+x = 1\n", "vazio.patch")  # a harmless diff: security not forced
        return R.rota(files, diff, failed, cfg or PADRAO, raiz)

    def test_cada_glob_de_risco_na_raiz_e_com_maiuscula(self):
        casos = {"**/migrations/**": ("migrations/001.sql", "DB/Migrations/002_X.SQL"),
                 "**/*.sql": ("schema.sql", "db/Schema.SQL"),
                 "**/auth/**": ("auth/x.py", "src/Auth/Login.py"),
                 "**/*auth*": ("auth.py", "src/AuthService.ts"),
                 "**/*webhook*": ("webhook.py", "api/StripeWebhook.ts"),
                 "**/*payment*": ("payment.py", "src/PaymentForm.tsx"),
                 "**/*billing*": ("billing.go", "lib/Billing/x.rb"),
                 "**/*worker*": ("worker.py", "jobs/EmailWorker.ts"),
                 "**/*queue*": ("queue.py", "lib/JobQueue.java"),
                 "**/hooks/**": ("hooks/pre.sh", "src/Hooks/useX.ts")}
        self.assertEqual(set(casos), set(PADRAO["risk_globs"]))
        for g, arqs in casos.items():
            for a in arqs:
                self.assertTrue(R.casa(R.relativo(a, {"/repo"}), g), (g, a))
                self.assertEqual(self.rota([a])["executor"], OPUS, a)

    def test_cada_glob_de_seguranca_e_banco(self):
        for g in PADRAO["security_globs"]:
            palavra = g.strip("*/")
            arqs = ("%s.py" % palavra, "src/My%s.py" % palavra.upper())
            if g == "**/hooks/**":
                arqs = ("hooks/pre.sh", "src/Hooks/useX.ts")
            for a in arqs:
                self.assertTrue(any(R.casa(R.relativo(a, {"/repo"}), x)
                                    for x in [g]), (g, a))
                r = self.rota([a])
                self.assertIn("security", r["reviewers"], (g, a))
        for a in ("migrations/001.sql", "schema.sql", "DB/Migrations/A.PY"):
            self.assertIn("database", self.rota([a])["reviewers"], a)
        self.assertNotIn("database", self.rota(["src/Button.tsx"])["reviewers"])

    def test_arquivo_comum_vai_para_sonnet_so_failures(self):
        r = self.rota(["src/Button.tsx", "README.md"])
        self.assertEqual((r["executor"], r["reviewers"]), (SONNET, ["failures"]))
        self.assertTrue(r["why"])

    def test_windows_barra_invertida_e_absoluto(self):
        r = self.rota(["C:\\repo\\src\\AuthService.ts"], raiz="C:/repo")
        self.assertEqual(r["executor"], OPUS)
        self.assertIn("security", r["reviewers"])
        self.assertEqual(R.relativo("C:\\repo\\migrations\\1.sql", {"c:/repo"}), "migrations/1.sql")
        self.assertEqual(R.relativo("/repo/src/X.ts", {"/repo"}), "src/x.ts")
        self.assertEqual(R.relativo("./src/X.ts", {"/repo"}), "src/x.ts")
        self.assertEqual(R.relativo("/fora/migrations/1.sql", {"/repo"}), "/fora/migrations/1.sql")
        self.assertEqual(self.rota(["/repo/migrations/001.sql"])["executor"], OPUS)
        self.assertEqual(self.rota(["/fora/migrations/001.sql"])["executor"], OPUS)
        self.assertEqual(self.rota(["src\\Button.tsx"])["executor"], SONNET)

    def test_lista_vazia_sobe(self):
        r = self.rota([])
        self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "security"]))

    def test_failed(self):
        self.assertEqual(self.rota(["a.md"], failed="sonnet")["executor"], OPUS)
        self.assertEqual(self.rota(["a.md"], failed="opus")["executor"], OPUS)
        r = self.rota(["a.md"], failed="haiku")
        self.assertEqual(r["executor"], OPUS)
        self.assertTrue(any("unknown --failed" in w for w in r["why"]))

    def test_diff_palavra_so_em_linha_adicionada(self):
        for k in ("auth", "TOKEN", "Secret", "password", "hmac", "signature", "permission",
                  "subprocess", "eval", "../", "..\\"):
            r = self.rota(["a.md"], diff=self.diff("--- a/a.md\n+++ b/a.md\n@@\n+x %s y\n" % k))
            self.assertIn("security", r["reviewers"], k)
            self.assertNotIn("x %s" % k, " ".join(r["why"]))  # keyword name only, never the line
        nada = ("--- a/auth.py\n+++ b/auth.py\n@@ -1,3 +1,3 @@\n-token = secret\n password = 1\n"
                "+x = range(1..3)\n+print('...')\n+y = 2\n")
        r = self.rota(["a.md"], diff=self.diff(nada))
        self.assertEqual(r["reviewers"], ["failures"], r["why"])

    def test_diff_ausente_ou_ilegivel_sobe_seguranca(self):
        self.assertIn("security", R.rota(["a.md"], None, None, PADRAO, "/repo")["reviewers"])
        r = self.rota(["a.md"], diff=os.path.join(self.tmp, "nao-existe.patch"))
        self.assertIn("security", r["reviewers"])
        p = os.path.join(self.tmp, "bin.patch")
        with open(p, "wb") as f:
            f.write(b"+x \xff\xfe\n")
        self.assertIn("security", self.rota(["a.md"], diff=p)["reviewers"])

    def test_sem_globs_padrao_nao_desce(self):
        with self.assertRaises(RuntimeError):
            R.rota(["a.md"], None, None, {}, "/repo")

    def test_args(self):
        self.assertEqual(R.ler_args(["--files", "a", "b", "--failed", "opus", "--diff-file", "d"]),
                         (["a", "b"], "d", "opus"))
        for ruim in (["--bogus"], ["--failed"], ["--files", "a", "--diff-file"]):
            with self.assertRaises(ValueError):
                R.ler_args(ruim)


class TestRotaCli(Base):
    USER_JSON = None

    def cli(self, *args, env=None):
        e = dict(self.env)
        e.update(env or {})
        r = subprocess.run([sys.executable, SCRIPT, "rota"] + list(args), cwd=self.cwd, env=e,
                           stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        linhas = r.stdout.strip().splitlines()
        self.assertEqual(len(linhas), 1, r.stdout)
        return json.loads(linhas[0])

    def test_ponta_a_ponta(self):
        r = self.cli("--files", "migrations/001.sql", "src/Button.tsx")
        self.assertEqual(set(r), {"executor", "reviewers", "why"})
        self.assertEqual(r["executor"], OPUS)
        self.assertEqual(r["reviewers"], ["failures", "security", "database"])
        d = os.path.join(self.tmp, "ok.patch")
        with open(d, "w", encoding="utf-8") as f:
            f.write("--- a/b.tsx\n+++ b/b.tsx\n@@\n+const x = 1\n")
        r = self.cli("--files", "src/Button.tsx", "--diff-file", d)
        self.assertEqual((r["executor"], r["reviewers"]), (SONNET, ["failures"]))

    def test_excecao_e_argumento_ruim_sobem(self):
        for r in (self.cli("--files", "a.md", env={"TUNEUP_FAKE_EXCECAO": "1"}), self.cli("--x")):
            self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "security"]))
            self.assertIn("route up", r["why"][0])
        with open(os.path.join(self.dados, "erros.log"), encoding="utf-8") as f:
            self.assertIn("rota", f.read())


if __name__ == "__main__":
    unittest.main()
