"""Testes do `guarda.py rota`: executor e revisores pelos caminhos. Rode: python3 -m unittest tests.test_rota"""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from base import SCRIPT, Base

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import jev  # noqa: E402
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
                         (["a", "b"], "d", "opus", None))
        self.assertEqual(R.ler_args(["--files", "a", "--text-file", "t.txt"]), (["a"], None, None, "t.txt"))
        for ruim in (["--bogus"], ["--failed"], ["--files", "a", "--diff-file"], ["--text-file"]):
            with self.assertRaises(ValueError):
                R.ler_args(ruim)


BAIXO = {"mechanical": 0.0, "risk": 0.0, "hard": 0.0, "visual": 0.0}


class TestRoteador(Base):
    """Optional router (C11): order a-f, what reaches the scorer, fallbacks. jev.perguntar is faked."""
    USER_JSON = None

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self.dados})  # erros.log in tmp
        p.start()
        self.addCleanup(p.stop)
        self.chamadas = []
        self.txt = self.texto("Add a tooltip to the save button.\nfiles: Button.tsx\n")

    def texto(self, conteudo, nome="item.txt"):
        p = os.path.join(self.tmp, nome)
        if isinstance(conteudo, str):
            conteudo = conteudo.encode("utf-8")
        with open(p, "wb") as f:
            f.write(conteudo)
        return p

    def cfg(self, **router):
        return dict(PADRAO, router=dict(PADRAO["router"], enabled=True, **router))

    def rota(self, files=("src/Button.tsx",), failed=None, cfg=None, txt="", resp=None, fake=None):
        def f(texto, perguntas):
            self.chamadas.append((texto, dict(perguntas)))
            return dict(BAIXO) if resp is None else resp
        d = os.path.join(self.tmp, "ok.patch")
        with open(d, "w", encoding="utf-8") as fh:
            fh.write("+x = 1\n")
        with mock.patch.object(jev, "perguntar", fake or f):
            return R.rota(list(files), d, failed, cfg or self.cfg(), "/repo",
                          self.txt if txt == "" else txt)

    def test_a_risk_glob_opus_sem_chamar_jev(self):
        for failed in (None, "sonnet"):
            r = self.rota(["migrations/001.sql"], failed=failed, resp=dict(BAIXO))
            self.assertEqual((r["executor"], r["model"], r["source"], r["scores"]),
                             (OPUS, "opus", "globs", {}))
        self.assertEqual(self.chamadas, [])
        r = self.rota(["migrations/001.sql"], failed="opus", cfg=self.cfg(hard_agent="x:hard"))
        self.assertEqual((r["executor"], r["model"], r["source"]), ("x:hard", None, "globs"))
        self.assertEqual(self.chamadas, [])

    def test_b_regra_fixa(self):
        r = self.rota(cfg=PADRAO)  # router disabled
        self.assertEqual(self.chamadas, [])
        self.assertEqual((r["executor"], r["model"], r["scores"], r["source"]), (SONNET, "sonnet", {}, "fixed"))
        self.assertEqual(r["why"], ["no rule fired: sonnet, failures only"])
        for txt in (None, os.path.join(self.tmp, "nao-existe.txt"),
                    self.texto(b"x" * (64 * 1024 + 1), "grande.txt"), self.texto(b"\xff\xfe", "bin.txt"),
                    self.texto("REAL DATA: only this\n", "so-dados.txt")):
            r = self.rota(txt=txt)
            self.assertEqual((r["executor"], r["scores"], r["source"]), (SONNET, {}, "fixed"), txt)
        self.assertEqual(self.chamadas, [])
        r = self.rota(files=[], txt=None)
        self.assertEqual((r["executor"], r["source"]), (OPUS, "fixed"))

    def test_b_jev_none_sem_chave_ou_excecao_fica_na_regra_fixa(self):
        real = jev.perguntar
        casos = (lambda t, p: None,
                 lambda t, p: real(t, p, ambiente={}, settings=os.path.join(self.tmp, "nao.json")),
                 mock.Mock(side_effect=RuntimeError("x")), lambda t, p: {"risk": "alto"},
                 lambda t, p: dict(BAIXO, risk=None))
        for fake in casos:
            for failed, exe in ((None, SONNET), ("sonnet", OPUS)):
                r = self.rota(failed=failed, fake=fake)
                self.assertEqual((r["executor"], r["scores"], r["source"]), (exe, {}, "fixed"), fake)
        with open(os.path.join(self.dados, "erros.log"), encoding="utf-8") as f:
            log = f.read()
        self.assertIn("no key", log)
        self.assertIn("router: RuntimeError", log)

    def test_c_risco_ou_dificil_sobe(self):
        for resp in (dict(BAIXO, risk=0.5), dict(BAIXO, hard=0.6), dict(BAIXO, risk=0.9, visual=1.0)):
            r = self.rota(resp=resp, cfg=self.cfg(visual_agent="x:ui"))
            self.assertEqual((r["executor"], r["model"], r["scores"], r["source"]), (OPUS, "opus", resp, "jev"))
        self.assertEqual(len(self.chamadas), 3)
        self.assertEqual(set(self.chamadas[0][1]), {"mechanical", "risk", "hard", "visual"})
        r = self.rota(resp=dict(BAIXO, risk=0.49, hard=0.59))
        self.assertEqual((r["executor"], r["model"], r["source"]), (SONNET, "sonnet", "jev"))

    def test_d_failed_opus_com_hard_agent(self):
        c = self.cfg(hard_agent="x:hard")
        for fake in (None, lambda t, p: None):
            r = self.rota(failed="opus", cfg=c, fake=fake)
            self.assertEqual((r["executor"], r["model"]), ("x:hard", None))
        self.assertEqual(self.rota(failed="opus")["executor"], OPUS)  # no hard_agent
        self.assertEqual(self.rota(failed="opus", cfg=dict(c, router=dict(c["router"], enabled=False)))
                         ["executor"], OPUS)  # router off: fixed rule

    def test_e_visual_agent(self):
        c = self.cfg(visual_agent="x:ui")
        r = self.rota(cfg=c, resp=dict(BAIXO, visual=0.5))
        self.assertEqual((r["executor"], r["model"], r["source"]), ("x:ui", None, "jev"))
        self.assertEqual(self.rota(cfg=c, resp=dict(BAIXO, visual=0.4))["executor"], SONNET)
        self.assertEqual(self.rota(cfg=c, resp=dict(BAIXO, visual=0.9, risk=0.5))["executor"], OPUS)
        self.assertEqual(self.rota(["src/AuthForm.tsx"], cfg=c, resp=dict(BAIXO, visual=1.0))["executor"], OPUS)
        self.assertEqual(self.rota(cfg=c, failed="sonnet", resp=dict(BAIXO, visual=1.0))["executor"], OPUS)
        self.assertEqual(self.rota(files=[], cfg=c, resp=dict(BAIXO, visual=1.0))["executor"], OPUS)

    def test_f_nunca_desce_nem_haiku(self):
        tudo = {"mechanical": 1.0, "risk": 0.0, "hard": 0.0, "visual": 1.0}
        self.assertEqual(self.rota(resp=tudo)["executor"], SONNET)
        for failed in ("sonnet", "opus", "haiku"):
            r = self.rota(failed=failed, resp=tudo, cfg=self.cfg(visual_agent="x:ui"))
            self.assertEqual((r["executor"], r["source"]), (OPUS, "jev"), failed)

    def test_max_chars_e_corte_defensivo(self):
        self.rota(cfg=self.cfg(max_chars=50), txt=self.texto("abcdefghij" * 100))
        self.assertEqual(self.chamadas[-1][0], "abcdefghij" * 5)
        for marca in ("REAL DATA: row 1", "PITFALLS", "diff --git a/x b/x", "@@ -1 +1 @@", "  PITFALLS:"):
            self.rota(txt=self.texto("Fix the label.\nfiles: a.tsx\n%s\nSEGREDO linha\n" % marca))
            self.assertEqual(self.chamadas[-1][0], "Fix the label.\nfiles: a.tsx", marca)

    def test_mascara_e_nada_alem_do_texto_chega_ao_transporte(self):
        corpos, real = [], jev.perguntar

        def transporte(url, cab, corpo, timeout):
            corpos.append(corpo.decode("utf-8"))
            return json.dumps({"answers": {k: {"noul": 0.1} for k in BAIXO}}).encode()

        def fake(t, p):
            return real(t, p, transporte=transporte, ambiente={"TYPESAFE_API_KEY": "k-teste"},
                        settings=os.path.join(self.tmp, "nao.json"))
        txt = self.texto("Mail ana.souza@example.com, call 11987654321, key sk-abcdefghijklmnopqrstuv.\n"
                         "files: Button.tsx\n")
        d = os.path.join(self.tmp, "seg.patch")
        with open(d, "w", encoding="utf-8") as f:
            f.write("+DIFF_PRIVADO = 1\n")
        with mock.patch.object(jev, "perguntar", fake):
            r = R.rota(["pasta-privada/Button.tsx"], d, None, self.cfg(), "/repo", txt)
        self.assertEqual((r["source"], r["executor"]), ("jev", SONNET))
        self.assertEqual(len(corpos), 1)
        for nada in ("ana.souza@example.com", "11987654321", "sk-abcdefghijklmnopqrstuv",
                     "DIFF_PRIVADO", "pasta-privada", "k-teste"):
            self.assertNotIn(nada, corpos[0], nada)
        self.assertIn("files: Button.tsx", corpos[0])


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
        self.assertEqual(set(r), {"executor", "reviewers", "why", "model", "scores", "source"})
        self.assertEqual((r["executor"], r["model"], r["scores"], r["source"]), (OPUS, "opus", {}, "globs"))
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
            self.assertEqual((r["model"], r["scores"], r["source"]), ("opus", {}, "fixed"))
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

    def test_router_so_com_config_confiada(self):
        """router.enabled in an untrusted project config changes nothing (the scorer is never
        called); the same file trusted turns the router on. jev.perguntar is faked in the child."""
        txt = os.path.join(self.tmp, "item.txt")
        with open(txt, "w", encoding="utf-8") as f:
            f.write("Restyle the header.\nfiles: Header.tsx\n")
        codigo = ("import sys\nsys.path.insert(0, sys.argv[1])\nfrom tuneup import jev, rota\n"
                  "def f(t, p):\n    open(sys.argv[2], 'a').write(t)\n"
                  "    return {'mechanical': 0.0, 'risk': 0.9, 'hard': 0.0, 'visual': 0.0}\n"
                  "jev.perguntar = f\nrota.roda_rota(sys.argv[3:])\n")
        for nome, confiar, esperado in (("nc", False, (SONNET, "fixed")), ("ok", True, (OPUS, "jev"))):
            proj = os.path.join(self.tmp, nome)
            os.makedirs(os.path.join(proj, ".tune-up"))
            c = os.path.join(proj, ".tune-up", "config.json")
            with open(c, "w", encoding="utf-8") as f:
                json.dump({"router": {"enabled": True}}, f)
            if confiar:
                self.confiar(c)
            marca = os.path.join(self.tmp, nome + ".chamou")
            r = subprocess.run([sys.executable, "-c", codigo, os.path.dirname(SCRIPT), marca,
                                "--files", "src/Header.tsx", "--text-file", txt], cwd=proj, env=self.env,
                               stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stderr)
            out = json.loads(r.stdout.strip())
            self.assertEqual((out["executor"], out["source"]), esperado, (nome, out))
            self.assertEqual(os.path.exists(marca), confiar, nome)


if __name__ == "__main__":
    unittest.main()
