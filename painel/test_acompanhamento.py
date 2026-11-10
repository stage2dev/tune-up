"""Testes de acompanhamento.montar com um sqlite temporário (dados sintéticos)."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

import acompanhamento  # noqa: E402

ESQUEMA = """CREATE TABLE work_state_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT, project TEXT NOT NULL, list_name TEXT NOT NULL,
  fields TEXT NOT NULL, created_at TEXT NOT NULL, created_at_epoch INTEGER NOT NULL,
  synced_at INTEGER, origin_device_id TEXT, origin_local_id TEXT, sync_rev TEXT NOT NULL DEFAULT '1')"""


class TestAcompanhamento(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="painel-acomp-")
        self.db = os.path.join(self.tmp, "claude-mem.db")
        con = sqlite3.connect(self.db)
        con.execute(ESQUEMA)
        n = [0]

        def add(projeto, lista, campos):
            n[0] += 1
            txt = campos if isinstance(campos, str) else json.dumps(campos)
            con.execute("INSERT INTO work_state_entries (project, list_name, fields, created_at, created_at_epoch) "
                        "VALUES (?,?,?,?,?)", (projeto, lista, txt, "2026-11-%02dT10:00:00.000Z" % n[0], n[0]))

        P = "Meu-Projeto"
        add(P, "vendas-ranqueamento-2026-11", {"task": "Plano", "status": "todo", "notas": "primeira",
                                            "work_product": "https://github.com/x/y/pull/385"})
        add(P, "vendas-ranqueamento-2026-11", {"task": "Plano", "status": "doing", "notas": "segunda"})
        add(P, "vendas-ranqueamento-2026-11", {"proximo_passo": "olhar", "fase": 174})
        add(P, "fase-187-parte-a", {"task": "A.1", "status": "done",
                                    "work_product": json.dumps([{"title": "PR #400", "url": "https://gh/400"}])})
        add(P, "fase-187-parte-a", {"task": "A.2", "status": "dropped", "falta": "nada", "falta_dono": "olhar"})
        add("meu-projeto", "login-coisa", {"task": "Tarefa sem status", "notas": None, "proximo": "testar"})
        add(P, "fase-174-vendas", {"task": "x", "status": "doing"})
        add(P, "fase-174-vendas", {"area": "dev"})
        add(P, "agent-lifecycle", {"task": "barulho", "status": "doing"})
        add("outro-projeto", "outra-coisa", {"task": "de fora", "status": "doing"})
        add(P, "quebrada", "{nao json")
        add(P, "lista-fechada", {"task": "t", "status": "doing"})
        add(P, "lista-fechada", {"status": "done"})
        add(P, "vendas-ranqueamento-2026-11", {"task": "Plano", "notas": None, "status": "doing"})
        con.commit()
        con.close()
        self.cfg = {"claude_mem_db": self.db, "projeto_mem": P,
                    "areas_acompanhamento": [{"id": "vendas", "titulo": "Vendas", "regex": "^vendas-"},
                                             {"id": "dev", "titulo": "Desenvolvimento", "regex": "^(fase|login)-"}]}

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def montar(self, **extra):
        cfg = dict(self.cfg, **extra)
        return acompanhamento.montar(cfg, usar_cache=False)

    def lista(self, dados, nome):
        return [x for x in dados["listas"] if x["nome"] == nome][0]

    def test_reducao_igual_ao_worker(self):
        d = self.montar()
        nomes = [x["nome"] for x in d["listas"]]
        self.assertNotIn("agent-lifecycle", nomes)
        self.assertNotIn("outra-coisa", nomes)
        self.assertIn("login-coisa", nomes)  # projeto comparado sem caixa
        seo = self.lista(d, "vendas-ranqueamento-2026-11")
        self.assertEqual(nomes[0], "vendas-ranqueamento-2026-11")  # mais nova primeiro
        item = seo["itens"][0]
        self.assertEqual(item["status"], "doing")
        self.assertEqual(item["notas"], "")  # null apagou as notas
        self.assertEqual(item["produtos"], [{"titulo": "385", "url": "https://github.com/x/y/pull/385"}])
        self.assertEqual(seo["estado"], {"proximo_passo": "olhar", "fase": "174"})
        self.assertTrue(seo["aberta"])
        self.assertEqual(seo["area"], "vendas")

    def test_status_produtos_e_extras(self):
        d = self.montar()
        fase = self.lista(d, "fase-187-parte-a")
        self.assertFalse(fase["aberta"])
        self.assertEqual(fase["area"], "dev")
        a1 = [i for i in fase["itens"] if i["tarefa"] == "A.1"][0]
        self.assertEqual(a1["produtos"], [{"titulo": "PR #400", "url": "https://gh/400"}])
        a2 = [i for i in fase["itens"] if i["tarefa"] == "A.2"][0]
        self.assertEqual(a2["notas"], "Falta: nada\nFalta (dono): olhar")
        sem = self.lista(d, "login-coisa")["itens"][0]
        self.assertEqual(sem["status"], "todo")
        self.assertEqual(sem["notas"], "Próximo: testar")

    def test_classificacao(self):
        d = self.montar()
        self.assertEqual(self.lista(d, "fase-174-vendas")["area"], "dev")  # estado.area manda
        self.assertEqual(self.lista(d, "login-coisa")["area"], "dev")
        self.assertEqual(self.lista(d, "lista-fechada")["area"], "geral")
        self.assertFalse(self.lista(d, "lista-fechada")["aberta"])
        self.assertEqual([a["id"] for a in d["areas"]], ["vendas", "dev", "geral"])
        d2 = self.montar(areas_acompanhamento=[{"id": "vendas", "titulo": "V", "regex": "^login-"}])
        self.assertEqual(self.lista(d2, "login-coisa")["area"], "vendas")
        self.assertEqual(self.lista(d2, "vendas-ranqueamento-2026-11")["area"], "geral")
        self.assertEqual(acompanhamento.classificar("pesquisa", {"area": "inventada"}, []), "geral")
        sem = self.montar(areas_acompanhamento=None)  # sem painel.json: tudo cai em "geral"
        self.assertEqual({x["area"] for x in sem["listas"]}, {"geral"})
        self.assertEqual(sem["areas"], [{"id": "geral", "titulo": "Geral"}])

    def test_linha_quebrada_vira_aviso(self):
        d = self.montar()
        self.assertTrue(any("ilegíveis" in a for a in d["avisos"]), d["avisos"])
        self.assertNotIn("quebrada", [x["nome"] for x in d["listas"]])

    def test_banco_ausente(self):
        d = self.montar(claude_mem_db=os.path.join(self.tmp, "nao-existe.db"))
        self.assertEqual(d["listas"], [])
        self.assertTrue(d["avisos"])
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "nao-existe.db")))  # não cria o arquivo

    def test_banco_travado(self):
        trava = sqlite3.connect(self.db, timeout=0.1)
        trava.execute("BEGIN EXCLUSIVE")
        velho = acompanhamento.TIMEOUT_DB
        acompanhamento.TIMEOUT_DB = 0.1
        try:
            d = self.montar()
        finally:
            acompanhamento.TIMEOUT_DB = velho
            trava.rollback()
            trava.close()
        self.assertEqual(d["listas"], [])
        self.assertTrue(any("claude-mem" in a for a in d["avisos"]), d["avisos"])

    def test_tabela_ausente(self):
        vazio = os.path.join(self.tmp, "vazio.db")
        sqlite3.connect(vazio).close()
        d = self.montar(claude_mem_db=vazio)
        self.assertEqual(d["listas"], [])
        self.assertTrue(d["avisos"])

    def test_somente_leitura(self):
        antes = os.path.getmtime(self.db), os.path.getsize(self.db)
        self.montar()
        self.assertEqual((os.path.getmtime(self.db), os.path.getsize(self.db)), antes)
        with self.assertRaises(sqlite3.OperationalError):
            con = sqlite3.connect("file:%s?mode=ro" % self.db, uri=True)
            try:
                con.execute("INSERT INTO work_state_entries (project, list_name, fields, created_at, "
                            "created_at_epoch) VALUES ('a','b','{}','c',1)")
            finally:
                con.close()

    def test_formato_do_contrato(self):
        d = self.montar()
        self.assertEqual(set(d), {"areas", "listas", "avisos"})
        for lista in d["listas"]:
            self.assertEqual(set(lista), {"nome", "area", "atualizado_em", "aberta", "itens", "estado"})
            self.assertIn(lista["area"], [a["id"] for a in d["areas"]])
            for v in lista["estado"].values():
                self.assertIsInstance(v, str)
            for item in lista["itens"]:
                self.assertEqual(set(item), {"tarefa", "status", "notas", "produtos", "atualizado_em"})
                self.assertIn(item["status"], ("todo", "doing", "done", "dropped"))
        json.dumps(d)


if __name__ == "__main__":
    unittest.main()
