"""Testes do guarda.py: perfil confiável e tipos do config. Rode: python3 -m unittest discover -s tests -q"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from base import SCRIPT, PromptBase


class TestC2PerfilConfiavel(PromptBase):
    def cfg(self, conteudo, base=None):
        p = os.path.join(base or self.cwd, ".tune-up")
        os.makedirs(p, exist_ok=True)
        c = os.path.join(p, "config.json")
        with open(c, "w") as f:
            json.dump(conteudo, f)
        return c

    def test_fora_do_home_ignorada(self):
        fora = tempfile.mkdtemp(dir="/private/tmp", prefix="tuneup-fora-")
        self.addCleanup(shutil.rmtree, fora, True)
        self.cfg({"regras_bash": [{"regex": "echo", "acao": "bloquear", "msg": "x"}]}, fora)
        s = self.rodar("bash", {"cwd": fora, "tool_name": "Bash", "tool_input": {"command": "echo oi"}})
        self.assertIsNone(s)
        s = self.rodar("bash", {"cwd": fora, "tool_name": "Bash", "tool_input": {"command": "echo oi"}},
                       {"CLAUDE_PROJECT_DIR": fora})
        self.assertIsNone(s)

    def test_nao_confiado_ignora_chaves_que_afrouxam(self):
        c = self.cfg({"merge_pelo_claude": True, "regras_bash": [{"regex": "rodar", "acao": "avisar"}]})
        self.assertEqual(self.bash("gh pr merge 12"), "bloquear")
        self.assertEqual(self.bash("./rodar.zsh"), "avisar")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("perfil %s não confiado: rode /tune-up:profile" % c, s["systemMessage"])

    def test_confiar_libera(self):
        c = self.cfg({"merge_pelo_claude": True})
        self.confiar(c)
        self.confiar(c)
        self.assertIsNone(self.bash("gh pr merge 12"))
        with open(os.path.join(self.dados, "perfis_confiaveis.txt")) as f:
            linhas = f.read().splitlines()
        self.assertEqual(len(linhas), 1)  # trusting the same content twice adds no line
        self.assertEqual(linhas[0].split("\t")[0], os.path.realpath(c))
        self.assertRegex(linhas[0].split("\t")[1], "^[0-9a-f]{64}$")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertNotIn("não confiado", json.dumps(s, ensure_ascii=False) if s else "")

    def test_frase_nao_confiada_nao_autoriza(self):
        self.cfg({"frases_autorizacao": ["oi"]})
        self.assertNotIn("autoriza", self.ctx(self.prompt("oi tudo bem")))

    def test_escrita_por_grupo_ignora_tudo(self):
        c = self.cfg({"merge_pelo_claude": True, "regras_bash": [{"regex": "rodar", "acao": "avisar"}]})
        self.confiar(c)
        os.chmod(c, 0o666)
        self.assertEqual(self.bash("gh pr merge 12"), "bloquear")
        self.assertIsNone(self.bash("./rodar.zsh"))
        os.chmod(c, 0o644)
        os.chmod(os.path.dirname(c), 0o777)
        self.assertEqual(self.bash("gh pr merge 12"), "bloquear")

    def test_regex_aninhada_descartada(self):
        self.cfg({"regras_bash": [{"regex": "(a+)+$", "acao": "bloquear", "msg": "x"},
                                  {"regex": "b" * 301, "acao": "bloquear", "msg": "y"}]})
        self.assertIsNone(self.bash("echo aaaa"))
        self.assertIsNone(self.bash("echo " + "b" * 301))
        with open(os.path.join(self.dados, "erros.log")) as f:
            self.assertIn("discarded", f.read())

    def test_msg_e_projeto_cortados(self):
        perfil = os.path.dirname(self.cfg({"projeto": "p" * 200 + "\nINJETA",
                                           "regras_bash": [{"regex": "rodar", "acao": "avisar",
                                                            "msg": "m" * 200 + "\nINJETA"}]}))
        open(os.path.join(perfil, "projeto.md"), "w").close()
        s = self.rodar("bash", {"tool_name": "Bash", "tool_input": {"command": "./rodar"}})
        self.assertNotIn("INJETA", json.dumps(s))
        self.assertNotIn("\\n", json.dumps(s))
        s = self.rodar("inicio", {"source": "startup"})
        self.assertNotIn("INJETA", json.dumps(s))
        self.assertNotIn("p" * 121, json.dumps(s))


class TestD3TiposDoConfig(PromptBase):
    def cfg(self, conteudo, confiar=True):
        p = os.path.join(self.cwd, ".tune-up")
        os.makedirs(p, exist_ok=True)
        c = os.path.join(p, "config.json")
        with open(c, "w") as f:
            json.dump(conteudo, f)
        if confiar:
            self.confiar(c)
        return c

    def test_regex_numero_nao_desliga_trava(self):
        self.cfg({"regras_bash": [{"regex": 5}, {"regex": "x", "acao": "sumir"}, "lixo",
                                  {"regex": "stash", "acao": "avisar", "msg": 7}]})
        self.assertEqual(self.bash("git stash -u"), "bloquear")
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("bash_rules", s["systemMessage"])

    def test_branch_principal_string(self):
        self.cfg({"branch_principal": "main"})
        self.assertEqual(self.bash("git push origin main"), "bloquear")
        self.assertIsNone(self.bash("git push origin m"))

    def test_raizes_string_descartada(self):
        self.cfg({"raizes_sincronizadas": "/"})
        a = os.path.join(self.tmp, "x.txt")
        open(a, "w").close()
        os.chmod(a, 0o444)
        self.rodar("escrita", {"tool_name": "Edit", "tool_input": {"file_path": a}})
        self.assertFalse(os.stat(a).st_mode & stat.S_IWUSR)
        s = self.rodar("inicio", {"source": "startup"})
        self.assertIn("synced_roots", s["systemMessage"])
        with open(os.path.join(self.dados, "erros.log")) as f:
            self.assertIn("synced_roots", f.read())

    def test_bool_errado(self):
        self.cfg({"merge_pelo_claude": "sim"})
        self.assertEqual(self.bash("gh pr merge 1"), "bloquear")


DUMP = ("import json, sys; sys.path.insert(0, %r); from tuneup import carregar_config; "
        "c = carregar_config(sys.argv[1]); print(json.dumps({k: v for k, v in c.items() "
        "if k not in ('_perfil', '_nao_confiado')}, sort_keys=True))"
        % os.path.join(os.path.dirname(SCRIPT)))
PT = {"branch_principal": "dev", "merge_pelo_claude": True, "commit_na_principal": True,
      "raizes_sincronizadas": ["~/s"], "repos_livres": ["~/r"], "caminhos_livres_modo_pesquisa": ["notas"],
      "frases_autorizacao": ["vai"], "frases_pesquisa_liga": ["olha"], "frases_pesquisa_desliga": ["ok"],
      "regras_bash": [{"regex": "x", "acao": "avisar"}], "projeto": "demo", "prod_supabase": ["abc"]}
EN = {"main_branches": "dev", "claude_may_merge": True, "commit_on_main": True,
      "synced_roots": ["~/s"], "free_repos": ["~/r"], "research_free_paths": ["notas"],
      "auth_phrases": ["vai"], "research_on_phrases": ["olha"], "research_off_phrases": ["ok"],
      "bash_rules": [{"regex": "x", "acao": "avisar"}], "project": "demo"}


class TestH2aContratos(PromptBase):
    def projeto(self, nome, conteudo, confiar=True):
        d = os.path.join(self.tmp, nome)
        os.makedirs(os.path.join(d, ".tune-up"))
        c = os.path.join(d, ".tune-up", "config.json")
        with open(c, "w") as f:
            json.dump(conteudo, f)
        if confiar:
            self.confiar(c)
        return d

    def dump(self, cwd):
        r = subprocess.run([sys.executable, "-c", DUMP, cwd], capture_output=True, text=True,
                           env=self.env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_alias_pt_igual_en(self):
        pt_d, en_d = self.projeto("pt", PT), self.projeto("en", EN)
        pt, en = self.dump(pt_d), self.dump(en_d)
        for c, d in ((pt, pt_d), (en, en_d)):  # plans_dir free path is anchored at each project root
            c["research_free_paths"] = [x.replace(d, "<proj>") for x in c["research_free_paths"]]
        self.assertEqual(pt, en)
        self.assertEqual(en["main_branches"], ["dev"])
        self.assertNotIn("prod_supabase", pt)
        self.assertFalse(any(k in pt for k in PT if k != "prod_supabase" and k not in EN))

    def test_nao_confiado_ignora_frases_pt_e_en(self):
        for chave in ("auth_phrases", "frases_autorizacao"):
            with self.subTest(chave=chave):
                self.cwd = self.projeto("p-" + chave, {chave: ["."]}, confiar=False)
                self.assertNotIn("autoriza", self.ctx(self.prompt("oi tudo bem")))
                s = self.rodar("inicio", {"source": "resume"})
                self.assertIn("não confiado", s["systemMessage"])

    def test_nao_confiado_ignora_chave_en(self):
        self.cwd = self.projeto("p", {"claude_may_merge": True, "supabase_guard": False}, confiar=False)
        self.assertEqual(self.bash("gh pr merge 12"), "bloquear")
        self.assertIs(self.dump(self.cwd)["supabase_guard"], True)

    def test_repos_livres_padrao_vazio(self):
        self.assertEqual(self.bash("git -C ~/plugins-x commit -m x", {"TUNEUP_FAKE_BRANCH": "main"}),
                         "bloquear")

    def test_trust_alias(self):
        c = os.path.join(self.cwd, ".tune-up", "config.json")
        os.makedirs(os.path.dirname(c))
        with open(c, "w") as f:
            json.dump({"claude_may_merge": True}, f)
        r = subprocess.run([sys.executable, SCRIPT, "trust", c], capture_output=True, text=True,
                           env=self.env, timeout=20)
        self.assertIn("perfil confiado", r.stdout)
        self.assertIsNone(self.bash("gh pr merge 12"))

    def test_roda_confiar_pega_trust(self):
        g = os.path.join(self.tmp, "plugin", "scripts", "guarda.py")
        for sub in ("confiar", "trust"):
            with self.subTest(sub=sub):
                self.assertEqual(self.bash("python3 %s %s x" % (g, sub)), "perguntar")
        self.prompt("/tune-up:profile atualiza")
        self.assertIsNone(self.bash("python3 %s trust x" % g))

    def test_learn_e_profile_marcam_o_turno(self):
        for i, t in enumerate(("/tune-up:learn isso", "/tune-up:profile")):
            with self.subTest(t=t):
                self.rodar("prompt", {"prompt": t, "prompt_id": "q%d" % i})
                self.assertEqual(self.ler_sessao().get("aprender_prompt_id"), "q%d" % i)

    def test_plans_dir_livre_em_pesquisa(self):
        for confiar, esperado in ((False, "perguntar"), (True, None)):
            with self.subTest(confiar=confiar):
                self.cwd = self.projeto("p%s" % confiar, {"plans_dir": "docs/plans"}, confiar)
                self.sessao(modo_pesquisa=True)
                alvo = os.path.join(self.cwd, "docs", "plans", "x.md")
                s = self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": alvo}})
                self.assertEqual(self.decisao(s), esperado)
                s = self.rodar("escrita", {"tool_name": "Write",
                                           "tool_input": {"file_path": os.path.join(self.cwd, "src", "x.py")}})
                self.assertEqual(self.decisao(s), "perguntar")

    def test_import_quebrado_loga_e_sai_zero(self):
        copia = os.path.join(self.tmp, "copia")
        shutil.copytree(os.path.dirname(SCRIPT), copia)
        with open(os.path.join(copia, "tuneup", "__init__.py"), "a") as f:
            f.write("\nraise ImportError('broken on purpose')\n")
        r = subprocess.run([sys.executable, os.path.join(copia, "guarda.py"), "bash"], input="{}",
                           capture_output=True, text=True, env=self.env, timeout=20)
        self.assertEqual((r.returncode, r.stdout), (0, ""))
        with open(os.path.join(self.dados, "erros.log")) as f:
            linhas = f.read().splitlines()
        self.assertEqual(len(linhas), 1)
        self.assertIn("broken on purpose", linhas[0])

    def test_plans_dir_hostil_volta_ao_padrao(self):
        hostis = ("/", "/etc", "~/.ssh", "../../..", "a/../../x", "x$(touch /tmp/x); echo", ".", "a\\b")
        for i, pd in enumerate(hostis + ("src",)):
            with self.subTest(plans_dir=pd):
                d = self.projeto("h%d" % i, {"plans_dir": pd})
                c = self.dump(d)
                esperado = "src" if pd == "src" else ".planning"
                self.assertEqual(c["plans_dir"], esperado)
                self.assertEqual(c["research_free_paths"][-1], os.path.join(d, esperado))
                r = subprocess.run([sys.executable, SCRIPT, "info"], cwd=d, env=self.env, timeout=20,
                                   capture_output=True, text=True, stdin=subprocess.DEVNULL)
                self.assertEqual(json.loads(r.stdout)["plans_dir"], os.path.join(d, esperado))
        with open(os.path.join(self.dados, "erros.log")) as f:
            self.assertGreaterEqual(f.read().count("plans_dir invalid"), len(hostis))

    def test_plans_dir_ancorado_na_raiz_do_projeto(self):
        self.cwd = self.projeto("proj2", {"plans_dir": "docs"})
        self.sessao(modo_pesquisa=True)
        casos = ((os.path.join(self.cwd, "docs", "x.md"), None),
                 (os.path.join(self.tmp, "outro-repo", "docs", "app.py"), "perguntar"),
                 (os.path.join(self.cwd, "src", "docs", "x.py"), "perguntar"))
        for alvo, esperado in casos:
            with self.subTest(alvo=alvo):
                s = self.rodar("escrita", {"tool_name": "Write", "tool_input": {"file_path": alvo}})
                self.assertEqual(self.decisao(s), esperado)

    def test_import_quebrado_no_inicio_avisa(self):
        copia = os.path.join(self.tmp, "copia")
        shutil.copytree(os.path.dirname(SCRIPT), copia)
        with open(os.path.join(copia, "tuneup", "__init__.py"), "a") as f:
            f.write("\nraise ImportError('broken on purpose')\n")
        for ev, esperado in (("inicio", True), ("bash", False)):
            with self.subTest(ev=ev):
                r = subprocess.run([sys.executable, os.path.join(copia, "guarda.py"), ev], input="{}",
                                   capture_output=True, text=True, env=self.env, timeout=20)
                self.assertEqual(r.returncode, 0)
                if esperado:
                    log = os.path.join(self.dados, "erros.log")
                    self.assertEqual(json.loads(r.stdout), {
                        "systemMessage": "tune-up: hooks off (import failed), see %s" % log})
                else:
                    self.assertEqual(r.stdout, "")


class TestM8PerfilPorSymlink(PromptBase):
    def test_tune_up_symlinkado_nao_herda_confianca(self):
        a = os.path.join(self.tmp, "A")
        os.makedirs(os.path.join(a, ".tune-up"))
        c = os.path.join(a, ".tune-up", "config.json")
        with open(c, "w") as f:
            json.dump({"merge_pelo_claude": True}, f)
        self.confiar(c)
        s = self.rodar("bash", {"cwd": a, "tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}})
        self.assertIsNone(s)  # A itself stays trusted
        b = os.path.join(self.tmp, "B")
        os.makedirs(b)
        os.symlink(os.path.join(a, ".tune-up"), os.path.join(b, ".tune-up"))
        s = self.rodar("bash", {"cwd": b, "tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}})
        self.assertEqual(self.decisao(s), "bloquear")
        with open(os.path.join(self.dados, "erros.log")) as f:
            self.assertIn("profile not trusted", f.read())


if __name__ == "__main__":
    unittest.main()
