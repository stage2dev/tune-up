"""Testes do limite de linhas (linhas.py). Rode: python3 -m unittest discover -s tests -q"""
import json
import os
import unittest

from base import Base


def texto(n, topo=None):
    linhas = ["x = %d" % i for i in range(n)]
    if topo:
        linhas[topo[0] - 1] = topo[1]
    return "\n".join(linhas) + "\n"


class TestLinhas(Base):
    def arq(self, nome, n=None):
        p = os.path.join(self.cwd, nome)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if n is not None:
            with open(p, "w") as f:
                f.write(texto(n))
        return p

    def write(self, nome, conteudo):
        s = self.rodar("escrita", {"tool_name": "Write",
                                   "tool_input": {"file_path": self.arq(nome), "content": conteudo}})
        return self.decisao(s), s

    def cfg(self, conteudo, confiar=True):
        p = os.path.join(self.cwd, ".tune-up")
        os.makedirs(p, exist_ok=True)
        c = os.path.join(p, "config.json")
        with open(c, "w") as f:
            json.dump(conteudo, f)
        if confiar:
            self.confiar(c)

    def test_tabela_write(self):
        casos = [  # (nome, linhas antes ou None = novo, linhas depois, esperado)
            ("novo451.py", None, 451, "bloquear"),
            ("novo450.py", None, 450, None),
            ("cresce.ts", 440, 460, "bloquear"),
            ("velho.js", 500, 520, "avisar"),
            ("encolhe.js", 520, 500, None),
            ("igual.js", 520, 520, None),
            ("db/schema.sql", None, 900, None),
            ("x.d.ts", None, 900, None),
            ("dist/a.js", None, 900, None),
            ("package-lock.json", None, 900, None),
            ("dados.json", None, 900, None),
            ("README.md", None, 900, None),
            ("app.min.js", None, 900, None),
            ("supabase/migrations/001.ts", None, 900, None),
            ("node_modules/x/i.js", None, 900, None),
        ]
        for nome, antes, depois, esperado in casos:
            with self.subTest(nome=nome):
                self.arq(nome, antes)
                self.assertEqual(self.write(nome, texto(depois))[0], esperado)

    def test_motivo_da_negacao_e_aviso(self):
        _, s = self.write("grande.py", texto(451))
        motivo = s["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("451", motivo)
        self.assertIn("tune-up: allow-long <motivo>", motivo)
        self.assertIn("divida o arquivo", motivo)
        self.arq("velho.py", 500)
        _, s = self.write("velho.py", texto(520))
        self.assertIn("500", s["hookSpecificOutput"]["additionalContext"])

    def test_ingles(self):
        self.user_json({"language": "en"})
        _, s = self.write("grande.py", texto(451))
        self.assertIn("split the file", s["hookSpecificOutput"]["permissionDecisionReason"])

    def test_allow_long(self):
        ok = texto(600, (3, "# tune-up: allow-long tabela gerada à mão"))
        self.assertIsNone(self.write("a.py", ok)[0])
        tarde = texto(600, (6, "# tune-up: allow-long tabela gerada à mão"))
        self.assertEqual(self.write("b.py", tarde)[0], "bloquear")
        sem_motivo = texto(600, (1, "# tune-up: allow-long"))
        self.assertEqual(self.write("c.py", sem_motivo)[0], "bloquear")

    def test_sem_newline_final(self):
        self.assertEqual(self.write("a.py", texto(450) + "y = 1")[0], "bloquear")

    def edit(self, nome, ti, ferramenta="Edit"):
        ti = dict(ti, file_path=os.path.join(self.cwd, nome))
        return self.decisao(self.rodar("escrita", {"tool_name": ferramenta, "tool_input": ti}))

    def test_edit_449_para_451_nega(self):
        self.arq("a.py", 449)
        self.assertEqual(self.edit("a.py", {"old_string": "x = 5\n", "new_string": "x = 5\na\nb\n"}),
                         "bloquear")
        self.assertIsNone(self.edit("a.py", {"old_string": "x = 5\n", "new_string": "x = 5\na\n"}))

    def test_edit_sem_casar_nao_decide(self):
        self.arq("a.py", 449)
        self.assertIsNone(self.edit("a.py", {"old_string": "nao existe", "new_string": "\n" * 50}))

    def test_edit_replace_all(self):
        self.arq("a.py", 440)
        um = {"old_string": "x = 1", "new_string": "x = 1\n\n"}
        self.assertIsNone(self.edit("a.py", um))  # só a 1ª ocorrência: 442
        self.assertEqual(self.edit("a.py", dict(um, replace_all=True)), "bloquear")  # x = 1, 1x: 111

    def test_edit_cria_arquivo(self):
        self.assertEqual(self.edit("novo.py", {"old_string": "", "new_string": texto(451)}), "bloquear")

    def test_multiedit(self):
        self.arq("a.py", 440)
        eds = [{"old_string": "x = 2\n", "new_string": "x = 2\n" * 7},
               {"old_string": "x = 3\n", "new_string": "x = 3\n" * 7}]
        self.assertEqual(self.edit("a.py", {"edits": eds}, "MultiEdit"), "bloquear")
        self.assertIsNone(self.edit("a.py", {"edits": eds[:1]}, "MultiEdit"))
        falha = eds + [{"old_string": "nao existe", "new_string": ""}]
        self.assertIsNone(self.edit("a.py", {"edits": falha}, "MultiEdit"))
        self.arq("b.py", 500)
        self.assertEqual(self.edit("b.py", {"edits": eds}, "MultiEdit"), "avisar")

    def test_binario_nao_decide(self):
        p = self.arq("bin.py")
        with open(p, "wb") as f:
            f.write(b"\0" + b"\n" * 600)
        self.assertIsNone(self.edit("bin.py", {"old_string": "\n", "new_string": "\n\n"}))

    def test_nao_confiado_ignorado(self):
        self.cfg({"line_limit": 30, "line_limit_exclude": ["gerado/*"]}, confiar=False)
        self.assertIsNone(self.write("a.py", texto(100))[0])
        self.assertEqual(self.write("gerado/b.py", texto(451))[0], "bloquear")
        self.cfg({"line_limit": 10000}, confiar=False)
        self.assertEqual(self.write("c.py", texto(451))[0], "bloquear")

    def test_limite_confiado(self):
        self.cfg({"line_limit": 100})
        self.assertEqual(self.write("a.py", texto(101))[0], "bloquear")
        self.assertIsNone(self.write("b.py", texto(100))[0])

    def test_limite_invalido_vira_450(self):
        for v in (0, -1, 49, "texto", True, 3.5):
            with self.subTest(v=v):
                self.cfg({"line_limit": v})
                self.assertIsNone(self.write("a.py", texto(450))[0])
                self.assertEqual(self.write("b.py", texto(451))[0], "bloquear")

    def test_exclude_confiado_libera(self):
        self.cfg({"line_limit_exclude": ["gerado/*", "*.pb.go"]})
        self.assertIsNone(self.write("gerado/sub/b.py", texto(900))[0])
        self.assertIsNone(self.write("api/x.pb.go", texto(900))[0])
        self.assertEqual(self.write("outro/b.py", texto(900))[0], "bloquear")

    def test_outras_travas_vencem(self):
        self.sessao(modo_pesquisa=True)
        self.assertEqual(self.write("a.py", texto(451))[0], "perguntar")
        self.sessao(modo_conversa=True)
        d, s = self.write("a.py", texto(451))
        self.assertEqual(d, "bloquear")
        self.assertIn("modo conversa", s["hookSpecificOutput"]["permissionDecisionReason"])


if __name__ == "__main__":
    unittest.main()
