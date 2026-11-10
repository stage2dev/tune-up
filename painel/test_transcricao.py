"""Testes da leitura da conversa (.jsonl) com trechos sintéticos."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

import transcricao as tr  # noqa: E402

SID = "0123abcd-1111-2222-3333-444455556666"


def linha(tipo, conteudo, **extra):
    d = {"type": tipo, "timestamp": "2026-11-10T04:00:00Z", "message": {"content": conteudo}}
    d.update(extra)
    return json.dumps(d) + "\n"


class TesteTranscricao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.pasta = os.path.join(self.tmp, "-Users-x-Meu-Projeto")
        os.makedirs(self.pasta)
        self.arq = os.path.join(self.pasta, SID + ".jsonl")

    def escrever(self, *linhas, modo="w"):
        with open(self.arq, modo, encoding="utf-8") as f:
            f.write("".join(linhas))

    def test_localizar(self):
        self.escrever(linha("user", "oi"))
        self.assertEqual(tr.pasta_do_projeto("/Users/x/Meu Projeto"), "-Users-x-Meu-Projeto")
        # Windows: só documenta o comportamento atual; a regra do CLI ali não foi conferida
        self.assertEqual(tr.pasta_do_projeto("C:\\Users\\x\\Meu Projeto"), "C--Users-x-Meu-Projeto")
        self.assertEqual(tr.localizar(self.tmp, SID, "/Users/x/Meu Projeto"), self.arq)
        self.assertEqual(tr.localizar(self.tmp, SID, "/outro"), self.arq)  # acha pelo glob
        self.assertIsNone(tr.localizar(self.tmp, "../../etc/passwd", "/x"))
        self.assertIsNone(tr.localizar(self.tmp, "0123abcd-1111-2222-3333-999999999999", "/x"))

    def test_arquivo_inexistente(self):
        self.assertEqual(tr.ler(None, 5), {"eventos": [], "proximo": 5})
        self.assertEqual(tr.ler(os.path.join(self.tmp, "nao.jsonl"), 0), {"eventos": [], "proximo": 0})

    def test_tipos_de_evento(self):
        self.escrever(
            linha("attachment", None, attachment={"x": 1}),
            linha("user", "<command-message>tune-up:part</command-message>\n<command-name>/tune-up:part</command-name>"
                          "\n<command-args>187 C</command-args>"),
            linha("user", "<system-reminder>segredo do sistema</system-reminder>"),
            linha("user", "<browser_instruction>regras</browser_instruction>"),
            linha("user", "lembrete", isMeta=True),
            linha("assistant", [{"type": "thinking", "thinking": "hmm"}, {"type": "text", "text": "Vou ler."},
                                {"type": "tool_use", "name": "Read", "input": {"file_path": "/a/b.py"}},
                                {"type": "tool_use", "name": "Bash",
                                 "input": {"command": "ls -la", "description": "Listar a pasta"}},
                                {"type": "tool_use", "name": "Agent",
                                 "input": {"subagent_type": "executor", "description": "Item C.1",
                                           "prompt": "faça"}}]),
            linha("user", [{"type": "tool_result", "tool_use_id": "1", "content": "ok"},
                           {"type": "tool_result", "tool_use_id": "2", "is_error": True,
                            "content": [{"type": "text", "text": "Exit code 1: falhou"}]}]),
            linha("assistant", [{"type": "text", "text": "subagente"}], isSidechain=True),
            linha("system", None, subtype="turn_duration"),
            linha("system", None, subtype="api_error", level="error", content="Overloaded"),
            '{"type": "api-request-blob", "message": {"content": [{"type": "text", "text": "prompt do sistema"}]}}\n',
        )
        r = tr.ler(self.arq, 0)
        tipos = [(e["tipo"], e["texto"], e.get("ferramenta"), e.get("erro")) for e in r["eventos"]]
        self.assertEqual(tipos, [
            ("usuario", "/tune-up:part 187 C", None, None),
            ("assistente", "Vou ler.", None, None),
            ("ferramenta", "/a/b.py", "Read", None),
            ("ferramenta", "Listar a pasta", "Bash", None),
            ("subagente", "executor: Item C.1", "Agent", None),
            ("resultado", "Exit code 1: falhou", None, True),
            ("sistema", "Overloaded", None, True),
        ])
        ns = [e["n"] for e in r["eventos"]]
        self.assertEqual(ns, sorted(set(ns)))
        self.assertEqual(r["proximo"], os.path.getsize(self.arq))

    def test_incremental_e_linha_quebrada(self):
        self.escrever(linha("user", "um"), "{quebrada\n", linha("assistant", [{"type": "text", "text": "dois"}]))
        r1 = tr.ler(self.arq, 0)
        self.assertEqual([e["texto"] for e in r1["eventos"]], ["um", "dois"])
        self.escrever('{"type": "user", "message": {"content": "tr', modo="a")  # linha ainda sendo escrita
        r2 = tr.ler(self.arq, r1["proximo"])
        self.assertEqual((r2["eventos"], r2["proximo"]), ([], r1["proximo"]))
        self.escrever('es"}}\n', modo="a")
        r3 = tr.ler(self.arq, r2["proximo"])
        self.assertEqual([e["texto"] for e in r3["eventos"]], ["tres"])
        self.assertGreater(min(e["n"] for e in r3["eventos"]), max(e["n"] for e in r1["eventos"]))
        self.assertEqual(tr.ler(self.arq, 10 ** 9)["proximo"], os.path.getsize(self.arq))  # cursor velho

    def test_corte(self):
        self.escrever(linha("assistant", [{"type": "text", "text": "a" * 5000}]))
        texto = tr.ler(self.arq, 0)["eventos"][0]["texto"]
        self.assertEqual(len(texto), tr.CORTE)
        self.assertTrue(texto.endswith("…"))

    def test_mascara_segredos(self):
        casos = [
            "Authorization: Bearer abcDEF123456789xyz",
            "export OPENAI_API_KEY=sk-proj-abcdefghijklmnop1234",
            "senha=minhasenha123", "password: 'hunter2xx'", "token=ghp_abcdefghijklmnopqrstuvwxyz1234",
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
            "postgres://user:SenhaForte@db.exemplo.com/x", "AKIAABCDEFGHIJKLMNOP",
            "chave AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdEF solta",
        ]
        for c in casos:
            m = tr.mascarar(c)
            self.assertIn("***", m, c)
        for segredo in ("abcDEF123456789xyz", "abcdefghijklmnop1234", "minhasenha123", "hunter2xx",
                        "SenhaForte", "ABCDEFGHIJKLMNOP"):
            self.assertNotIn(segredo, " ".join(tr.mascarar(c) for c in casos))
        sha = "a" * 20 + "0123456789abcdef0123"
        self.assertEqual(tr.mascarar("commit " + sha), "commit " + sha)  # hash hex fica
        self.assertEqual(tr.mascarar("/Users/fulano/projetos/loja"), "/Users/fulano/projetos/loja")


if __name__ == "__main__":
    unittest.main()
