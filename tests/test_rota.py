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
        for a in ("migrations/001.sql", "schema.sql", "db/Schema.SQL", "DB/Migrations/A.PY"):
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

    def test_diff_palavra_em_linha_mudada(self):
        for k in ("auth", "TOKEN", "Secret", "password", "hmac", "signature", "permission",
                  "subprocess", "eval", "../", "..\\"):
            r = self.rota(["a.md"], diff=self.diff("--- a/a.md\n+++ b/a.md\n@@\n+x %s y\n" % k))
            self.assertIn("security", r["reviewers"], k)
            self.assertNotIn("x %s" % k, " ".join(r["why"]))  # keyword name only, never the line
        nada = ("--- a/auth.py\n+++ b/auth.py\n@@ -1,3 +1,3 @@\n-y = 1\n password = token\n"
                "+x = range(1..3)\n+print('...')\n+y = 2\n")
        r = self.rota(["a.md"], diff=self.diff(nada))
        self.assertEqual(r["reviewers"], ["failures"], r["why"])  # header and context: no
        r = self.rota(["a.md"], diff=self.diff(nada.replace("-y = 1", "-token = secret")))
        self.assertIn("security", r["reviewers"])
        self.assertIn("diff keyword in removed line: token", r["why"])

    def test_diff_que_remove_ou_troca_verificacao_sobe_seguranca(self):
        h = "--- a/src/api.py\n+++ b/src/api.py\n"
        casos = {"signature": h + "@@ -1,2 +1,2 @@\n def h(req):\n-    if not verify_signature(req):\n"
                              "+    if False:\n",
                 "auth": h + "@@ -1,2 +1,1 @@\n def h(user):\n-    if not check_auth(user):\n",
                 "token": "-    check(token)\n",  # no headers, no hunk
                 "secret": h + "@@ -1,2 +1,2 @@\n---- secret\n+++ secret\n",  # `-- `/`++ ` content
                 "hmac": "@@\n--- hmac()\n+++ x\n"}  # bare `@@`: a pair not followed by `@@` is content
        for k, texto in casos.items():
            r = self.rota(["src/api.py"], diff=self.diff(texto))
            self.assertEqual(r["reviewers"], ["failures", "security"], k)
            self.assertTrue(any(w.endswith(": " + k) for w in r["why"]), (k, r["why"]))
        sem = h + "@@ -1,2 +1,1 @@\n def h(x):\n-    y = 1\n"
        self.assertEqual(self.rota(["src/api.py"], diff=self.diff(sem))["reviewers"], ["failures"])
        ctx = h + "@@ -1,2 +1,2 @@\n token = 1\n-y = 1\n+y = 2\n"
        self.assertEqual(self.rota(["src/api.py"], diff=self.diff(ctx))["reviewers"], ["failures"])

    def test_diff_ausente_ou_ilegivel_sobe_seguranca(self):
        self.assertIn("security", R.rota(["a.md"], None, None, PADRAO, "/repo")["reviewers"])
        r = self.rota(["a.md"], diff=os.path.join(self.tmp, "nao-existe.patch"))
        self.assertIn("security", r["reviewers"])
        p = os.path.join(self.tmp, "bin.patch")
        with open(p, "wb") as f:
            f.write(b"+x \xff\xfe\n")
        self.assertIn("security", self.rota(["a.md"], diff=p)["reviewers"])

    def test_sem_globs_padrao_nao_desce(self):
        r = R.rota(["migrations/001.sql"], self.diff("+x = 1\n"), None, {}, "/repo")
        self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "database"]))

    def test_constantes_iguais_ao_padrao_json(self):
        for k, v in R.PADROES.items():
            self.assertEqual(list(v), PADRAO[k], k)

    def test_caminho_vazio_nao_conta_como_arquivo(self):
        for files in ([""], ["  "], ["", " \n "]):
            r = self.rota(files)
            self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "security"]), files)
        self.assertEqual(self.rota(["", "src/Button.tsx"])["executor"], SONNET)

    def test_espaco_ou_varios_caminhos_num_argumento_sobem(self):
        for f in ("schema.sql ", "schema.sql src/a.py", "schema.sql\nsrc/a.py", "src/a.py\r\nschema.sql"):
            r = self.rota([f])
            self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "database"]), f)
        r = self.rota(["my folder/Button.tsx"])
        self.assertEqual((r["executor"], r["reviewers"]), (SONNET, ["failures"]))
        self.assertEqual(self.rota(["db/my schema.sql"])["executor"], OPUS)

    def test_caminho_com_linhas_aspas_ou_virgula_sobe(self):
        for f in ("db/schema.sql:10-40", "supabase/schema.sql:12", "schema.sql,", '"schema.sql"',
                  "schema.sql,src/a.py", "`migrations/001.sql`", "db/x.sql#L10-L20",
                  "schema.sql\u200b", "\ufeffschema.sql", "(schema.sql)", "[db/x.sql:3:9]",
                  "- schema.sql:1-2;", "schema.sql:12.", "'db/x.sql'#L4", "db/x.sql:L10",
                  "schema.sql:10\u201340", "schema.sql;src/a.py", "schema.sql|a.py", "**schema.sql**",
                  "db/x.sql#10", "schema.sql\u2060", "[schema.sql](db/schema.sql)", "<db/x.sql>"):
            r = self.rota([f])
            self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "database"]), f)
            if not f.startswith("\ufeff"):  # a leading BOM already matches `*.sql` whole
                self.assertIn("(as ", r["why"][0], f)
        r = self.rota(["C:\\repo\\Schema.SQL:12"], raiz="C:/repo")
        self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "database"]))
        self.assertIn("(as schema.sql)", r["why"][0])
        for f in ("- src/auth/login.ts:1-20", "src/auth.py#L10-L20", "`src/Auth.ts`:3"):
            r = self.rota([f])
            self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "security"]), f)
        for f in ("src/Button.tsx:10-40", '"my folder/Button.tsx"', "src/a.py#L10-L20", "C:\\x\\a.py"):
            r = self.rota([f])
            self.assertEqual((r["executor"], r["reviewers"]), (SONNET, ["failures"]), f)

    def test_diff_sem_conteudo_de_diff_sobe_seguranca(self):
        for texto in ("", "   \n\n", "just some text\n", "--- a/x\n", "--- a/x\n+++ b/x\n"):
            r = self.rota(["src/a.py"], diff=self.diff(texto, "x.patch"))
            self.assertIn("security", r["reviewers"], repr(texto))
            self.assertTrue(any("no diff content" in w for w in r["why"]), repr(texto))
        r = self.rota(["src/a.py"], diff=self.diff("--- a/x\n+++ b/x\n@@ -1 +0,0 @@\n-y = 1\n"))
        self.assertEqual(r["reviewers"], ["failures"])

    def test_erro_inclui_banco(self):
        self.assertEqual(R.rota_erro(ValueError())["reviewers"], ["failures", "security", "database"])

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
        for r in (self.cli("--files", "a.md", env={"TUNEUP_FAKE_EXCECAO": "1"}), self.cli("--x"),
                  self.cli("--files", "migrations/001.sql", "--failed")):
            self.assertEqual((r["executor"], r["reviewers"]), (OPUS, ["failures", "security", "database"]))
            self.assertIn("route up", r["why"][0])
        with open(os.path.join(self.dados, "erros.log"), encoding="utf-8") as f:
            self.assertIn("rota", f.read())

    def test_padrao_json_antigo_com_listas_do_projeto_nao_perde_padroes(self):
        """padrao.json without the glob keys (or with a wrong type) + a project that adds its
        own lists, through the real carregar_config: the built-in defaults still apply."""
        velho = dict(PADRAO)
        for k in R.PADROES:
            del velho[k]
        velho["database_globs"] = "**/*.sql"  # wrong type: dropped, defaults stay
        fake = os.path.join(self.tmp, "fake-scripts")
        os.makedirs(fake)
        with open(os.path.join(fake, "padrao.json"), "w", encoding="utf-8") as f:
            json.dump(velho, f)
        proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(proj, ".tune-up"))
        with open(os.path.join(proj, ".tune-up", "config.json"), "w", encoding="utf-8") as f:
            json.dump({"risk_globs": ["**/infra/**"], "security_globs": ["**/*crypto*"],
                       "database_globs": ["**/*.prisma"]}, f)
        d = os.path.join(self.tmp, "ok.patch")
        with open(d, "w", encoding="utf-8") as f:
            f.write("--- a/b\n+++ b/b\n@@\n+x = 1\n")
        codigo = ("import sys; sys.path.insert(0, sys.argv[1]); from tuneup import config, rota; "
                  "config.AQUI = sys.argv[2]; rota.roda_rota(sys.argv[3:])")
        for arq, rev in (("supabase/migrations/001.sql", ["failures", "database"]),
                         ("src/AuthService.ts", ["failures", "security"]),
                         ("api/webhook.py", ["failures", "security"]),
                         ("infra/main.tf", ["failures"])):
            r = subprocess.run([sys.executable, "-c", codigo, os.path.dirname(SCRIPT), fake,
                                "--files", arq, "--diff-file", d], cwd=proj, env=self.env,
                               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout.strip())
            self.assertEqual((out["executor"], out["reviewers"]), (OPUS, rev), (arq, out))


if __name__ == "__main__":
    unittest.main()
