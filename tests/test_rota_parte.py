"""Tests of `guarda.py rota --part`: the reviewers of a whole Part. Run: python3 -m unittest tests.test_rota_parte"""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from base import SCRIPT, Base

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import rota as R  # noqa: E402
from tuneup import rota_parte as P  # noqa: E402
from tuneup import usuario as U  # noqa: E402

with open(os.path.join(os.path.dirname(SCRIPT), "padrao.json"), encoding="utf-8") as _f:
    PADRAO = json.load(_f)
FRONT = ["src/**", "**/*.tsx"]
CHAVES = {"part", "risk", "reviewers", "models", "effort", "lines", "chunks", "why"}


def git_diff(caminho, mudadas=("+const x = 1",), contexto=0):
    """One file of a well-formed `git diff`: the changed lines, then context lines."""
    velho = sum(m[0] == "-" for m in mudadas) + contexto
    novo = sum(m[0] == "+" for m in mudadas) + contexto
    return ("diff --git a/%s b/%s\nindex 111..222 100644\n--- a/%s\n+++ b/%s\n@@ -1,%d +1,%d @@ f\n" % (
        (caminho,) * 4 + (velho, novo))) + "".join(m + "\n" for m in mudadas) + " c\n" * contexto


class ParteBase(Base):
    USER_JSON = None

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"TUNEUP_USER_JSON": os.path.join(self.tmp, "nao.json")})
        p.start()
        self.addCleanup(p.stop)
        U._CACHE.clear()
        self.addCleanup(U._CACHE.clear)

    def arq(self, texto):
        p = os.path.join(self.tmp, "d.patch")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(texto)
        return p

    def parte(self, files=("src/A.tsx",), diff=None, **cfg):
        c = dict(PADRAO, front_globs=FRONT)
        c.update(cfg)
        if diff is None:
            diff = git_diff("src/A.tsx")
        r = P.rota_parte(list(files), self.arq(diff) if diff else None, c, "/repo")
        self.assertEqual(set(r), CHAVES)
        self.assertEqual((r["part"], r["effort"]), (True, "high"))
        self.assertEqual(set(r["models"]), set(r["reviewers"]))
        self.assertTrue(r["why"])
        return r

    def baixo(self, *a, **k):
        r = self.parte(*a, **k)
        self.assertEqual((r["risk"], r["reviewers"]), (False, ["failures"]), r)
        return r

    def risco(self, *a, **k):
        banco = k.pop("banco", False)
        r = self.parte(*a, **k)
        self.assertEqual((r["risk"], r["reviewers"]),
                         (True, ["failures", "security"] + (["database"] if banco else [])), r)
        return r


class TestParteCaminhos(ParteBase):
    def test_front_com_import_relativo_e_baixo(self):
        r = self.baixo(diff=git_diff("src/A.tsx", ("+import x from '../x'", "-const token = authUser")))
        self.assertEqual((r["lines"], r["chunks"]), (2, 1))

    def test_sem_front_globs_e_risco(self):
        self.risco(["src/Button.tsx"], git_diff("src/Button.tsx"), front_globs=[])
        r = P.rota_parte(["src/Button.tsx"], self.arq(git_diff("src/Button.tsx")), {}, "/repo")
        self.assertEqual(r["reviewers"], ["failures", "security"])

    def test_globs_off_solta_so_o_padrao_nomeado_e_so_na_parte(self):
        f, d = ["src/hooks/useX.ts"], git_diff("src/hooks/useX.ts")
        self.risco(f, d)
        r = self.baixo(f, d, globs_off=["**/hooks/**"])
        self.assertIn("globs_off: **/hooks/** is off in Part mode", r["why"])
        self.risco(f, d, globs_off=["**/HOOKS/**"])  # exact string only
        self.risco(f, d, globs_off=["**/hooks/**"], risk_globs=["**/useX*"])  # an extra stays
        self.risco(f, d, globs_off=["**/hooks/**"],  # the project lists the default too
                   risk_globs=PADRAO["risk_globs"] + ["**/hooks/**"])
        self.risco(["src/a.sql"], git_diff("src/a.sql"), banco=True,
                   globs_off=["**/*.sql", "**/migrations/**"])  # database_globs never off
        r = self.risco(["db/migrations/1.py"], git_diff("db/migrations/1.py"), banco=True,
                       globs_off=["**/*.sql", "**/migrations/**"])
        self.assertFalse([w for w in r["why"] if w.startswith("globs_off")], r)

    def test_backend_e_risco_com_seguranca(self):
        for f in ("app/services/evolution.py", "app/services/broadcast_scheduler.py"):
            self.risco([f], git_diff(f))

    def test_migration_soma_banco(self):
        f = "migrations/001.sql"
        self.risco([f], git_diff(f), banco=True)
        self.risco(["src/A.tsx"], git_diff(f), banco=True)  # only in the diff
        self.risco(["src/A.tsx", f], banco=True)  # only in --files

    def test_front_que_casa_uma_lista_e_risco(self):
        for chave, glob, f in (("risk_globs", "**/*cart*", "src/Cart.tsx"),
                               ("security_globs", "**/*login*", "src/Login.tsx"),
                               ("database_globs", "**/*schema*", "src/Schema.tsx")):
            self.baixo([f], git_diff(f))
            r = self.risco([f], git_diff(f), banco=chave == "database_globs", **{chave: [glob]})
            self.assertIn("%s: %s matches %s" % (chave, f, glob), r["why"])

    def test_dois_caminhos_num_argumento_e_risco(self):
        for f in ("src/A.tsx app/x.py", "src/A.tsx,app/x.py", "src/A.tsx, app/x.py", "src/A.tsx;app/x.py"):
            self.risco([f])
        self.risco(["src/A.tsx\napp/x.py"])

    def test_todo_arquivo_precisa_ser_front(self):
        r = self.risco(["src/A.tsx", "app/x.py", "app/y.py"])
        self.assertIn("not in front_globs: app/x.py (+1 more)", r["why"])

    def test_ponto_ponto_e_risco(self):
        for f in ("src/../app/x.py", "src\\..\\app\\x.py", "/repo/src/../app/x.py"):
            self.risco([f])
        self.risco(diff=git_diff("src/../app/x.tsx"))

    def test_caminho_windows(self):
        self.baixo(["src\\A.tsx"], front_globs=["src/**"])
        d = git_diff("src/A.tsx") + git_diff("src/B.ts")
        self.baixo(["src\\A.tsx", "/repo/src/B.ts"], d)
        self.risco(["src\\A.tsx", "/repo/src/B.ts"])  # B.ts is not in the diff
        self.risco(["src\\hooks\\useX.ts"])

    def test_lista_vazia_e_risco(self):
        for f in ([], [""], ["  \n "]):
            self.assertIn("no files: no information", self.risco(f)["why"])

    def test_front_globs_que_casa_tudo_e_rejeitado(self):
        for g in ("**", "*", "**/*", "*.*", "**/**", "?*", "./**", "[a-z]*", "[!]a]*", "[]a]*", "[!/]*/**",
                  "", " "):
            r = self.risco(front_globs=[g])
            self.assertIn("front_globs entry rejected (matches everything): %s" % g, r["why"])
        self.baixo(front_globs=["**", "src/[a-z]*"])
        with open(os.path.join(os.path.dirname(SCRIPT), "padrao.json"), encoding="utf-8") as f:
            d = json.load(f)
        self.assertEqual((d["front_globs"], d["globs_off"]), ([], []))


class TestParteDiff(ParteBase):
    def test_sem_diff_ou_ilegivel_e_risco(self):
        r = self.risco(diff="")
        self.assertEqual((r["lines"], r["chunks"], r["why"][0]), (None, 1, "no diff: cannot rule risk out"))
        p = os.path.join(self.tmp, "b.patch")
        with open(p, "wb") as f:
            f.write(git_diff("src/A.tsx").encode("utf-16"))
        for d in (p, self.tmp, os.path.join(self.tmp, "nope")):
            r = P.rota_parte(["src/A.tsx"], d, dict(PADRAO, front_globs=FRONT), "/repo")
            self.assertEqual((r["reviewers"], r["lines"]), (["failures", "security"], None))

    def test_sem_diff_so_front_tem_um_motivo(self):
        # the plan skill exempts its review only on this exact `why`
        f = ["src/A.tsx", "src/B.tsx"]
        self.assertEqual(self.parte(f, diff="")["why"], ["no diff: cannot rule risk out"])
        r = self.parte(["src/Cart.tsx"], diff="", risk_globs=["**/*cart*"])
        self.assertIn("risk_globs: src/Cart.tsx matches **/*cart*", r["why"])
        r = self.parte(["src/A.tsx", "docs/x.md"], diff="")
        self.assertIn("not in front_globs: docs/x.md", r["why"])

    def test_diff_sem_conteudo_e_risco(self):
        for d in ("\n", "diff --git a/src/A.tsx b/src/A.tsx\nold mode 100644\nnew mode 100755\n"):
            self.assertIn("diff file has no diff content", self.risco(diff=d)["why"])

    def test_diff_sem_cabecalho_e_risco(self):
        for d in ("+x = 1\n", "@@ -1 +1 @@\n-a\n+b\n", "@@ -0,0 +1 @@\n+b\n" + git_diff("src/A.tsx")):
            self.risco(diff=d)

    def test_arquivo_do_diff_fora_da_lista(self):
        ab = git_diff("src/A.tsx") + git_diff("src/B.ts", ("-a", "+b"), 3)
        self.baixo(["src/A.tsx", "src/B.ts"], ab)
        self.assertIn("in the diff but not in --files: src/B.ts", self.risco(diff=ab)["why"])
        r = self.risco(diff=git_diff("src/A.tsx") + git_diff("app/x.py"))
        self.assertIn("not in front_globs: app/x.py", r["why"])
        for cab in ("diff --git a/app/x.py b/app/x.py\n", "--- a/app/x.py\n", "+++ b/app/x.py\n"):
            self.risco(diff=git_diff("src/A.tsx") + cab)  # each header counts alone

    def test_caminho_sem_hunk_e_risco(self):
        fs = ["src/A.tsx", "src/B.tsx", "src/Session.ts"]
        a, b = git_diff("src/A.tsx"), git_diff("src/B.tsx")
        tudo = a + b + git_diff("src/Session.ts")
        for args in (fs, ["src/A.tsx src/B.tsx", "./src/Session.ts"], ["src/A.tsx, src/B.tsx; src/Session.ts"],
                     ["/repo/src/A.tsx", "src\\B.tsx", "src/Session.ts"]):
            self.baixo(args, tudo)
            self.assertIn("no hunk in the diff: src/B.tsx (+1 more)", self.risco(args, a)["why"])
        so_cabecalho = "diff --git a/src/B.tsx b/src/B.tsx\n"
        for resto in (so_cabecalho, so_cabecalho + "new file mode 100644\nindex 000..e69\n",
                      so_cabecalho + "old mode 100644\nnew mode 100755\n", git_diff("src/B.tsx", (), 2)):
            for d in (a + resto, resto + a):
                self.assertIn("no hunk in the diff: src/B.tsx", self.risco(fs[:2], d)["why"], d)
        self.risco(["src/A.tsx", "src/a.tsx"], a)  # two files where case matters
        self.risco(["src/A.tsx", ","], a)

    def test_symlink_e_submodulo_sao_risco(self):
        d = git_diff("src/A.tsx")
        for modo in ("120000", "160000"):
            for tipo in ("new file", "deleted file", "old", "new"):
                self.risco(diff=d.replace("index", "%s mode %s\nindex" % (tipo, modo)))
            self.risco(diff=d.replace("222 100644", "222 " + modo))  # changed target: no mode line
        self.risco(diff=git_diff("src/A.tsx", ("-Subproject commit 1", "+Subproject commit 2")))

    def test_diff_que_nao_e_utf8_conta_as_linhas(self):
        p = os.path.join(self.tmp, "l.patch")
        with open(p, "wb") as f:
            f.write(git_diff("src/A.tsx", ("+x",) * 3999 + ("+caf\xe9",)).encode("latin-1"))
        r = P.rota_parte(["src/A.tsx"], p, dict(PADRAO, front_globs=FRONT), "/repo")
        self.assertEqual((r["risk"], r["lines"], r["chunks"]), (True, 4000, 3))
        self.assertIn("diff is not UTF-8", r["why"])

    def test_arquivo_novo_apagado_e_com_espaco(self):
        novo = git_diff("src/N.tsx").replace("--- a/src/N.tsx", "--- /dev/null").replace(
            "index", "new file mode 100644\nindex")
        fim = git_diff("src/F.tsx", ("-x",)).replace("+++ b/src/F.tsx", "+++ /dev/null").replace(
            "index", "deleted file mode 100644\nindex")
        self.baixo(["src/N.tsx", "src/F.tsx"], novo + fim + "\\ No newline at end of file\n")
        esp = git_diff("src/a src/b.tsx").replace("b.tsx\n@@", "b.tsx\t\n@@")
        self.assertEqual(P.ler_diff(esp), (["src/a src/b.tsx"], [("+", "const x = 1")], [], {"src/a src/b.tsx"}))
        self.baixo(["src/a src/b.tsx"], esp)
        self.baixo(diff=git_diff("src/A.tsx", ("-a", "+b"), 2).replace("\n", "\r\n"))

    def test_cabecalho_ilegivel_e_risco(self):
        d = git_diff("src/A.tsx")
        casos = (d + "diff --git a/src/A.tsx b/src/B.tsx\nrename from src/A.tsx\nrename to src/B.tsx\n",
                 'diff --git "a/src/\\303.tsx" "b/src/\\303.tsx"\n' + d,
                 "diff --git src/A.tsx src/A.tsx\n" + d, "diff --cc src/A.tsx\n" + d,
                 d.replace("--- a/", "--- "), d.replace("+++ b/", "+++ "), "\x1b[1m" + d,
                 d.replace("@@ -1,0 +1,1 @@ f", "@@"), d.replace("@@ -1,0 +1,1 @@ f", "@@@ -1 -1 +1 @@@"),
                 d + "Binary files a/src/l.tsx and b/src/l.tsx differ\n", d + "Submodule api 1..2:\n",
                 "\ufeff" + d, d + "+solta\n")
        for c in casos:
            self.assertIn("cannot be read", " ".join(self.risco(diff=c)["why"]), c)
        self.risco(diff="diff --git a/db/a.sql b/db/b.sql\n" + d, banco=True)  # unread header, still seen

    def test_conteudo_parecido_com_cabecalho_nao_engana(self):
        self.baixo(diff=git_diff("src/A.tsx", ("--- a/app/x.py", "+++ b/app/x.py", "+diff --git a/z b/z"), 1))
        d = git_diff("src/A.tsx") + git_diff("app/x.py")  # a lying count cannot hide the second file
        self.assertIn("not in front_globs: app/x.py", self.risco(
            diff=d.replace("@@ -1,0 +1,1", "@@ -1,50 +1,50", 1))["why"])

    def test_contagem_que_nao_fecha_e_risco(self):
        d = git_diff("src/A.tsx", ("-a", "+b"), 2)
        self.risco(diff=d.replace("-1,3 +1,3", "-1,4 +1,4"))  # truncated
        self.risco(diff=d.replace("-1,3 +1,3", "-1,1 +1,3"))  # one side goes negative

    def test_palavras_do_front(self):
        for k in ("supabase.auth", "service_role", ".rpc(", "functions.invoke", "dangerouslySetInnerHTML",
                  "innerHTML", "import.meta.env", "localStorage", "PASSWORD", "Secret"):
            for s, tipo in (("+", "added"), ("-", "removed")):
                r = self.risco(diff=git_diff("src/A.tsx", (s + "zz " + k + "x",)))
                self.assertIn("diff keyword in %s line: %s" % (tipo, k.lower()), r["why"])
                self.assertNotIn("zz", " ".join(r["why"]))
        self.assertEqual(set(P.PALAVRAS_FRENTE), {
            "supabase.auth", "service_role", ".rpc(", "functions.invoke", "dangerouslysetinnerhtml",
            "innerhtml", "import.meta.env", "localstorage", "password", "secret"})
        self.baixo(["src/A.tsx", "src/B.tsx"],
                   git_diff("src/A.tsx", ("+auth token eval hmac signature permission ../ ..\\",))
                   + " localStorage\n".join(git_diff("src/B.tsx", contexto=1).split(" c\n")))  # context line
        for sep in ("\u2028", "\x0c", "\r", "\x85"):  # not line ends for git: the tail is still scanned
            self.baixo(diff=git_diff("src/A.tsx", ("+a" + sep + "b",)))
            r = self.risco(diff=git_diff("src/A.tsx", ("+a" + sep + "localStorage",)))
            self.assertEqual((r["lines"], len(r["why"])), (1, 1))

    def test_palavras_fora_do_front_so_informam(self):
        r = self.risco(["app/x.py"], git_diff("app/x.py", ("+token ../ zz", "-SERVICE_ROLE")))
        texto = " ".join(r["why"])
        self.assertIn("diff keyword in added line: token", r["why"])
        self.assertIn("diff keyword in removed line: service_role", r["why"])
        self.assertNotIn("../", texto)
        self.assertNotIn("zz", texto)

    def test_tamanho(self):
        for n, pedacos in ((1, 1), (1500, 1), (1501, 2), (2000, 2), (3001, 3)):
            r = self.baixo(diff=git_diff("src/A.tsx", ("+x",) * (n - 1) + ("-x",), 5))
            self.assertEqual((r["lines"], r["chunks"]), (n, pedacos))
            self.assertEqual("coordinator splits" in " ".join(r["why"]), pedacos > 1)


class TestParteCli(ParteBase):
    def cli(self, *args, env=None):
        r = subprocess.run([sys.executable, SCRIPT, "rota"] + list(args), cwd=self.cwd,
                           env=dict(self.env, **(env or {})), stdin=subprocess.DEVNULL,
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(r.stdout.strip().splitlines()), 1, r.stdout)
        return json.loads(r.stdout)

    def config(self, **dados):
        c = os.path.join(self.cwd, ".tune-up", "config.json")
        os.makedirs(os.path.dirname(c), exist_ok=True)
        with open(c, "w", encoding="utf-8") as f:
            json.dump(dados, f)
        return c

    def test_confiada_desce_nao_confiada_e_risco(self):
        c = self.config(front_globs=["src/**"], globs_off=["**/hooks/**"])
        d = self.arq(git_diff("src/hooks/useX.ts", ("+import x from '../x'",)))
        args = ("--part", "--files", "src/hooks/useX.ts", "--diff-file", d)
        r = self.cli(*args)
        self.assertEqual((r["risk"], r["reviewers"]), (True, ["failures", "security"]), r)
        self.assertNotIn("globs_off", " ".join(r["why"]))
        self.confiar(c)
        r = self.cli(*args)
        self.assertEqual((r["risk"], r["reviewers"], r["lines"]), (False, ["failures"], 1), r)
        self.assertEqual(set(r), CHAVES)
        self.config(front_globs=["src/**", "app/**"], globs_off=["**/hooks/**"])  # edited after trust
        self.assertIs(self.cli(*args)["risk"], True)

    def test_cada_chave_exige_confianca_e_tipo_certo(self):
        codigo = ("import json, sys; sys.path.insert(0, sys.argv[1]); from tuneup.config import "
                  "carregar_config as c; print(json.dumps(c(sys.argv[2])))")

        def ler():
            r = subprocess.run([sys.executable, "-c", codigo, os.path.dirname(SCRIPT), self.cwd],
                               env=self.env, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            return json.loads(r.stdout)
        for k in ("front_globs", "globs_off"):
            c = self.config(**{k: ["src/**"]})
            self.assertEqual((ler()[k], ler()["_nao_confiado"]), ([], os.path.realpath(c)))
            self.confiar(c)
            self.assertEqual(ler()[k], ["src/**"])
            for ruim in ("src/**", [1], {"a": 1}):
                self.confiar(self.config(**{k: ruim}))
                self.assertEqual((ler()[k], ler()["_invalidas"]), ([], [k]))

    def test_modo_item_solta_so_o_padrao_desligado(self):
        d = self.arq(git_diff("src/hooks/useX.ts"))
        casos = [("--files", f, "--diff-file", d) for f in ("src/hooks/useX.ts", "src/A.tsx", "app/x.py")]
        c = self.config(front_globs=["src/**"], globs_off=["**/hooks/**"])
        antes = [self.cli(*a) for a in casos]  # untrusted config: changes nothing
        self.assertEqual((antes[0]["executor"], antes[0]["reviewers"]), (R.OPUS, ["failures", "security"]))
        self.assertNotIn("globs_off", " ".join(antes[0]["why"]))
        self.confiar(c)
        depois = [self.cli(*a) for a in casos]
        for r in antes[1:]:  # the other files keep their route; only the note is added
            r["why"].append("globs_off: **/hooks/** is off")
        self.assertEqual(depois[1:], antes[1:])
        self.assertEqual(depois[0]["executor"], R.SONNET, depois[0])
        self.assertIn("globs_off: **/hooks/** is off", depois[0]["why"])

    def test_modo_item_globs_off_em_processo(self):
        d = self.arq(git_diff("src/hooks/useX.ts"))

        def item(f, **cfg):
            return R.rota([f], d, None, dict(PADRAO, **cfg), "/repo")
        r = item("src/hooks/useX.ts", globs_off=["**/hooks/**"])
        self.assertEqual((r["executor"], r["model"]), (R.SONNET, "sonnet"), r)
        self.assertEqual(r["why"][-2:], ["no rule fired: sonnet, failures only", "globs_off: **/hooks/** is off"])
        r = item("src/hooks/useX.ts", globs_off=["**/hooks/**"],
                 risk_globs=PADRAO["risk_globs"] + ["**/hooks/**"])
        self.assertEqual(r["executor"], R.OPUS, r)  # the project lists the default too: stays
        r = item("db/migrations/1.sql", globs_off=["**/*.sql", "**/migrations/**"])
        self.assertIn("database", r["reviewers"])  # database_globs never off
        for f in ("db/x.sql", "db/migrations/1.py"):  # a database default stays in risk_globs too
            r = item(f, globs_off=["**/*.sql", "**/migrations/**"])
            self.assertEqual((r["executor"], r["reviewers"][-1]), (R.OPUS, "database"), r)

    def test_modelo_por_lente_e_override(self):
        d = self.arq(git_diff("app/x.py"))
        args = ("--part", "--files", "app/x.py", "--diff-file", d)
        r = self.cli(*args)
        self.assertEqual(r["models"], {"failures": "sonnet", "security": "opus"}, r)
        self.user_json({"models": {"reviewer-failures": {"model": "opus"},
                                   "reviewer-security": {"model": "fable-5"}}})
        self.assertEqual(self.cli(*args)["models"], {"failures": "opus", "security": "opus"})
        self.user_json({"models": {"reviewer-failures": {"model": "inherit"}}})
        self.assertEqual(self.cli(*args)["models"]["failures"], "opus")
        self.user_json({"models": {"reviewer-failures": {"model": "claude-Haiku-4-5"},
                                   "reviewer-security": {"model": "haiku"}}})
        self.assertEqual(self.cli(*args)["models"], {"failures": "opus", "security": "opus"})

    def test_erro_sai_no_formato_da_parte(self):
        d = self.arq(git_diff("src/A.tsx"))
        ok = ("--part", "--files", "src/A.tsx", "--diff-file", d)
        self.confiar(self.config(front_globs=["src/**"]))
        self.assertIs(self.cli(*ok)["risk"], False)
        for args, env in ((ok, {"TUNEUP_FAKE_EXCECAO": "1"}), (ok + ("--failed", "opus"), None),
                          (ok + ("--text-file", d), None), (ok + ("--x",), None), (ok + ("--failed",), None),
                          (ok + ("--diff-file", d), None), (("--files", "src/A.tsx", "--diff-file", "--part"), None)):
            r = self.cli(*args, env=env)
            self.assertEqual(set(r), CHAVES)
            self.assertEqual((r["part"], r["risk"], r["reviewers"], r["models"], r["effort"], r["lines"],
                              r["chunks"]), (True, True, ["failures", "security", "database"],
                                             {"failures": "opus", "security": "opus", "database": "opus"},
                                             "high", None, 1), r)
            self.assertIn("route up", r["why"][0])
        r = self.cli("--part", "--files", "app/\u00e9.py", env={"PYTHONIOENCODING": "ascii"})
        self.assertEqual((r["reviewers"], r["lines"]), (["failures", "security"], None))  # printable anywhere


if __name__ == "__main__":
    unittest.main()
