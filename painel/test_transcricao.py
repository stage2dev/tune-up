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
        self.escrever(linha("assistant", [{"type": "text", "text": "x" * 5000}]))
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

    def test_mascara_telefone_br(self):
        for t in ("+55 19 99999-8888", "5519999998888", "(19) 99999-8888", "19999998888", "(19) 3456-7890"):
            m = tr.mascarar("ligar para %s agora" % t)
            self.assertIn("***", m, t)
            self.assertIn(t[-4:], m)
            self.assertNotIn(t, m)
        self.assertEqual(tr.mascarar("tel 19999998888"), "tel ***8888")

    def test_telefone_nao_pega_falso_positivo(self):
        for t in ("2026-11-10", "12345678", "123456789", "file.py:1234", "2026-11-10T15:06:37",
                  "0123abcd-1111-2222-3333-444455556666", "3.13.0", "v1.20.300", "1731250000000",
                  "1731250000", "commit 4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f70"):
            self.assertEqual(tr.mascarar(t), t, t)

    def test_mascara_email(self):
        self.assertEqual(tr.mascarar("fale com ana.silva+x@exemplo.com.br hoje"), "fale com ***@exemplo.com.br hoje")

    def test_mascara_nome_terminado_em_key_token_secret_password(self):
        casos = {
            "FAL_KEY=abc123def456": "FAL_KEY=***",
            "export SERVICO_TOKEN=abc123def456": "export SERVICO_TOKEN=***",
            "APP_SECRET: abc123def456": "APP_SECRET: ***",
            "DB_PASSWORD=abc123def456": "DB_PASSWORD=***",
            '{"EVOLUTION_KEY": "abc123def456"}': '{"EVOLUTION_KEY": "***"}',
            "apikey: abc123def456": "apikey: ***",
            "API_KEY=abc123def456": "API_KEY=***",
        }
        for entrada, esperado in casos.items():
            self.assertEqual(tr.mascarar(entrada), esperado)

    def test_mascara_flags_de_senha(self):
        self.assertEqual(tr.mascarar("curl -u admin:Hunter2pass http://x"), "curl -u *** http://x")
        self.assertEqual(tr.mascarar("curl --user admin:Hunter2pass http://x"), "curl --user *** http://x")
        self.assertEqual(tr.mascarar("tool --password Hunter2pass --ok"), "tool --password *** --ok")
        self.assertEqual(tr.mascarar("tool -p 'S3nh@ forte' --ok"), "tool -p *** --ok")
        self.assertEqual(tr.mascarar("mysql -h db -u root -pHunter2pass"), "mysql -h db -u root -p ***")
        self.assertEqual(tr.mascarar("sshpass -p Hunter2pass ssh a@b.com"), "sshpass -p *** ssh ***@b.com")

    def test_flag_p_de_versao_e_uid_ficam(self):
        for t in ("uv run -p 3.13 script.py", "psql -p 5432 -h db", "docker run -u 1000:1000 img"):
            self.assertEqual(tr.mascarar(t), t)

    def test_mascara_hex_longo_menos_commit(self):
        h = "429683C4C977415CAAFCCE10F7D57E11"
        self.assertEqual(tr.mascarar("401 invalid header value " + h), "401 invalid header value ***")
        sha = "4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f70"
        self.assertEqual(tr.mascarar("commit " + sha), "commit " + sha)
        self.assertEqual(tr.mascarar("x " + sha), "x ***")
        self.assertEqual(tr.mascarar("abc1234 curto"), "abc1234 curto")

    def test_mascara_aws_secret_com_barra(self):
        seg = "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY"
        self.assertEqual(len(seg), 40)
        for t in ("aws_secret_access_key = " + seg, "AWS_SECRET_ACCESS_KEY=" + seg,
                  "aws_secret_access_key   " + seg):
            m = tr.mascarar(t)
            self.assertNotIn("wJalr", m, t)
            self.assertIn("***", m)

    def test_mascara_prefixos_conhecidos(self):
        for t in ("sk-proj-abcdefghijklmnopqrst", "ghp_abcdefghijklmnopqrstuvwx", "sbp_" + "ab12cd34ef" * 4,
                  "AKIAABCDEFGHIJKLMNOP", "EAAB" + "x1y2z3w4" * 3):
            m = tr.mascarar("usei " + t + " ontem")
            self.assertIn("***", m, t)
            self.assertNotIn(t[6:], m)

    def test_mascara_cabecalhos(self):
        self.assertNotIn("abcDEF", tr.mascarar("Authorization: Bearer abcDEF123456789xyz"))
        self.assertIn("***", tr.mascarar("Authorization: Bearer abcDEF123456789xyz"))
        self.assertEqual(tr.mascarar("-H 'apikey: abc123def456'"), "-H 'apikey: ***'")

    def test_mascara_idempotente_e_nunca_levanta(self):
        amostra = ("FAL_KEY=abc123def456 curl -u a:bcdef +55 19 99999-8888 ana@exemplo.com Bearer abcdef123456 "
                   "sk-abcdefghijklmnop1234 sbp_" + "ab12cd34ef" * 4 + " -p 'x y' mysql -pabc123 "
                   + "A1" * 20 + " " + "e" * 33)
        uma = tr.mascarar(amostra)
        self.assertEqual(tr.mascarar(uma), uma)
        self.assertEqual(tr.mascarar(None), "")
        self.assertEqual(tr.mascarar(12345), "12345")

        class Ruim(object):
            def __str__(self):
                raise ValueError("falha")
        self.assertEqual(tr.mascarar(Ruim()), "[texto ocultado]")

    def test_mascara_todos_os_campos_da_transcricao(self):
        seg = "FAL_KEY=abc123def456 ana@exemplo.com (19) 99999-8888"
        with open(self.arq, "w") as f:
            f.write(linha("user", "usuario " + seg))
            f.write(linha("assistant", [{"type": "text", "text": "assistente " + seg},
                                        {"type": "tool_use", "name": "Bash", "input": {"command": "echo " + seg}}]))
            f.write(linha("user", [{"type": "tool_result", "is_error": True, "content": "erro " + seg}]))
        textos = " ".join(e["texto"] for e in tr.ler(self.arq, 0)["eventos"])
        for vazou in ("abc123def456", "ana@", "99999-8888"):
            self.assertNotIn(vazou, textos)
        self.assertEqual(textos.count("***@exemplo.com"), 4)


if __name__ == "__main__":
    unittest.main()
