"""Testes do guarda.py: git e gh no Bash (stash, add/commit, push, PR, branch, prazo). Rode: python3 -m unittest discover -s tests -q"""
import json
import os
import time
import unittest

from base import Base, FakeBin, SCRIPT


class TestStash(Base):
    def test_stash_u(self):
        self.assertEqual(self.bash("git stash -u"), "bloquear")

    def test_stash_push_u(self):
        self.assertEqual(self.bash("git stash push -u -m x"), "bloquear")

    def test_stash_ku(self):
        self.assertEqual(self.bash("git stash -ku"), "bloquear")

    def test_stash_include_untracked(self):
        self.assertEqual(self.bash("git stash --include-untracked"), "bloquear")

    def test_cd_e_stash(self):
        self.assertEqual(self.bash("cd x && git stash"), "perguntar")

    def test_stash_list(self):
        self.assertIsNone(self.bash("git stash list"))

    def test_stash_show(self):
        self.assertIsNone(self.bash("git stash show -p"))

    def test_commit_com_texto_de_stash(self):
        self.assertIsNone(self.bash('git commit -m "nunca git stash -u"'))

    def test_heredoc(self):
        self.assertIsNone(self.bash("cat > f <<'EOF'\ngit stash -u\nEOF"))

    def test_heredoc_em_commit(self):
        cmd = "git commit -m \"$(cat <<'EOF'\nproibido git add -A e git stash -u\nEOF\n)\""
        self.assertIsNone(self.bash(cmd))


class TestAddCommit(Base):
    def test_add_A(self):
        self.assertEqual(self.bash("git add -A"), "bloquear")

    def test_add_ponto(self):
        self.assertEqual(self.bash("git add ."), "bloquear")

    def test_add_nomes(self):
        self.assertIsNone(self.bash("git add src/a.ts src/b.ts"))

    def test_commit_am(self):
        self.assertEqual(self.bash('git commit -am "x"'), "bloquear")

    def test_commit_msg_com_add(self):
        self.assertIsNone(self.bash('git commit -m "git add -A proibido"'))

    def test_commit_na_main(self):
        self.assertEqual(self.bash('git commit -m "x"', {"TUNEUP_FAKE_BRANCH": "main"}), "bloquear")

    def test_commit_em_feat(self):
        self.assertIsNone(self.bash('git commit -m "x"', {"TUNEUP_FAKE_BRANCH": "feat/x"}))

    def test_git_C_e_opcoes_globais(self):
        self.assertEqual(self.bash("git -C ../outro -c core.x=1 --no-pager add -A"), "bloquear")


class TestPush(Base):
    def test_pr_mergeada(self):
        s = self.rodar("bash", {"tool_input": {"command": "git push"}}, {"TUNEUP_FAKE_GH_MERGED": "87"})
        self.assertEqual(self.decisao(s), "bloquear")
        self.assertIn("#87", s["hookSpecificOutput"]["permissionDecisionReason"])

    def test_sem_pr(self):
        self.assertIsNone(self.bash("git push -u origin feat/x"))

    def test_delete(self):
        self.assertIsNone(self.bash("git push origin --delete feat/x", {"TUNEUP_FAKE_GH_MERGED": "87"}))

    def test_force_main(self):
        self.assertEqual(self.bash("git push -f origin main"), "bloquear")

    def test_head_refspec_mergeada(self):
        self.assertEqual(self.bash("git push origin HEAD:feat/y", {"TUNEUP_FAKE_GH_MERGED": "9"}), "bloquear")

    def test_gh_falha_avisa(self):
        s = self.rodar("bash", {"tool_input": {"command": "git push"}}, {"TUNEUP_FAKE_GH_ERRO": "1"})
        self.assertEqual(self.decisao(s), "avisar")
        self.assertIn("gh pr view", s["hookSpecificOutput"]["additionalContext"])


class TestGh(Base):
    def test_merge(self):
        self.assertEqual(self.bash("gh pr merge 12"), "bloquear")

    def test_create_base_feat(self):
        self.assertEqual(self.bash("gh pr create --base feat/a --title x"), "bloquear")

    def test_create_base_main(self):
        self.assertIsNone(self.bash("gh pr create --base main --title x"))

    def test_create_sem_base(self):
        self.assertIsNone(self.bash('gh pr create --title "x" --body "y"'))


class TestPerigosos(Base):
    def test_reset_hard(self):
        self.assertEqual(self.bash("git reset --hard origin/main"), "perguntar")

    def test_clean(self):
        self.assertEqual(self.bash("git clean -fd"), "perguntar")

    def test_restore_staged(self):
        self.assertIsNone(self.bash("git restore --staged x"))

    def test_supabase_db_push_sem_auth(self):
        self.assertEqual(self.bash("supabase db push"), "perguntar")

    def test_regra_do_projeto(self):
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)
        with open(os.path.join(perfil, "config.json"), "w", encoding="utf-8") as f:
            json.dump({"regras_bash": [{"regex": r"\brodar\.zsh\b", "acao": "avisar", "msg": "rode pelo dono"}]}, f)
        self.assertEqual(self.bash("./rodar.zsh"), "avisar")

    def test_modo_pesquisa_commit(self):
        self.sessao(modo_pesquisa=True)
        self.assertEqual(self.bash('git commit -m "x"'), "perguntar")


# ---------------------------------------------------------------- volta 1 (Ordem A)

class TestA1BarraFimDeLinha(Base):
    def test_pr_base_quebrada(self):
        self.assertEqual(self.bash("gh pr create \\\n --base feat/a"), "bloquear")

    def test_push_force_quebrado(self):
        self.assertEqual(self.bash("git push \\\n --force origin main"), "bloquear")

    def test_commit_a_quebrado(self):
        self.assertEqual(self.bash("git commit \\\n -am x"), "bloquear")

    def test_stash_u_quebrado(self):
        self.assertEqual(self.bash("git stash \\\r\n -u"), "bloquear")


class TestA3BranchIlegivel(Base):
    def setUp(self):
        super().setUp()
        del self.env["TUNEUP_FAKE_BRANCH"]

    def test_commit_fora_de_repo(self):
        s = self.rodar("bash", {"tool_input": {"command": 'git commit -m "x"'}})
        self.assertEqual(self.decisao(s), "avisar")
        self.assertIn("não consegui ler a branch", s["hookSpecificOutput"]["additionalContext"])

    def test_push_fora_de_repo(self):
        s = self.rodar("bash", {"tool_input": {"command": "git push"}})
        self.assertIn("não consegui ler a branch", s["hookSpecificOutput"]["additionalContext"])


class TestA5ReposLivres(Base):
    def setUp(self):
        super().setUp()
        perfil = os.path.join(self.cwd, ".tune-up")
        os.makedirs(perfil)
        c = os.path.join(perfil, "config.json")
        with open(c, "w", encoding="utf-8") as f:
            json.dump({"free_repos": ["~/plugins-x"]}, f)
        self.confiar(c)

    def test_commit_no_plugin_na_main(self):
        self.assertIsNone(self.bash("git -C ~/plugins-x commit -m x",
                                    {"TUNEUP_FAKE_BRANCH": "main"}))

    def test_cd_plugin_push_main(self):
        self.assertIsNone(self.bash("cd ~/plugins-x && git push origin main",
                                    {"TUNEUP_FAKE_BRANCH": "main"}))


class TestA6PushNaPrincipal(Base):
    def test_head_main(self):
        self.assertEqual(self.bash("git push origin HEAD:main"), "bloquear")

    def test_branch_main(self):
        self.assertEqual(self.bash("git push origin feat/x:main"), "bloquear")

    def test_push_estando_na_main(self):
        s = self.rodar("bash", {"tool_input": {"command": "git push"}}, {"TUNEUP_FAKE_BRANCH": "main"})
        self.assertEqual(self.decisao(s), "bloquear")
        self.assertIn("push na principal = merge", s["hookSpecificOutput"]["permissionDecisionReason"])

    def test_merge_local_na_main(self):
        self.assertEqual(self.bash("git merge feat/x", {"TUNEUP_FAKE_BRANCH": "main"}), "perguntar")

    def test_merge_local_fora_da_main(self):
        self.assertIsNone(self.bash("git merge main"))

    def test_delete_main_nao_e_merge(self):
        self.assertIsNone(self.bash("git push origin --delete main"))


class TestA9PosPR(Base):
    def pos(self, cmd, resp):
        return self.rodar("pos_bash", {"tool_name": "Bash", "tool_input": {"command": cmd}, "tool_response": resp})

    def test_url_avisa(self):
        self.assertIsNotNone(self.pos("gh pr create --fill", {"stdout": "https://github.com/a/b/pull/12\n"}))

    def test_erro_nao_avisa(self):
        self.assertIsNone(self.pos("gh pr create --fill", {"stdout": "", "stderr": "error"}))

    def test_outro_comando_nao_avisa(self):
        self.assertIsNone(self.pos("echo https://github.com/a/b/pull/12",
                                   {"stdout": "https://github.com/a/b/pull/12\n"}))

    def test_hooks_json_sem_if(self):
        caminho = os.path.join(os.path.dirname(os.path.dirname(SCRIPT)), "hooks", "hooks.json")
        with open(caminho, encoding="utf-8") as f:
            h = json.load(f)
        for grupo in h["hooks"]["PostToolUse"]:
            for x in grupo["hooks"]:
                self.assertNotIn("if", x)


class TestD4Prazo(FakeBin):
    def setUp(self):
        super().setUp()
        del self.env["TUNEUP_FAKE_GH_MERGED"]

    def test_um_gh_por_chamada(self):
        self.fake("gh", "echo '[{\"headRefName\": \"b\", \"number\": 42}]'")
        s = self.rodar("bash", {"tool_input": {"command": "git push origin a b c; git push origin d"}})
        self.assertEqual(self.decisao(s), "bloquear")
        self.assertIn("#42", s["hookSpecificOutput"]["permissionDecisionReason"])
        ch = self.chamadas("gh")
        self.assertEqual(len(ch), 1, ch)
        self.assertIn("--state merged", ch[0])
        self.assertIn("--limit 200", ch[0])

    def test_prazo_estourado_avisa(self):
        self.fake("gh", "sleep 5; echo '[]'")
        t = time.time()
        s = self.rodar("bash", {"tool_input": {"command": "git push origin feat/x"}},
                       {"TUNEUP_PRAZO": "1"})
        self.assertLess(time.time() - t, 4)
        self.assertIn("não consegui checar a tempo", s["hookSpecificOutput"]["additionalContext"])

    def test_branch_em_cache(self):
        del self.env["TUNEUP_FAKE_BRANCH"]
        self.fake("git", "echo feat/y")
        self.fake("gh", "echo '[]'")
        self.rodar("bash", {"tool_input": {"command": "git commit -m x; git push; git push origin HEAD"}})
        self.assertEqual(len([c for c in self.chamadas("git") if "rev-parse" in c]), 1)


if __name__ == "__main__":
    unittest.main()
