"""Tests of tuneup/jev.py (Jev scorer client) and the mascara.py copy. Run: cd tests && python3 -m unittest test_jev"""
import contextlib
import email.message
import importlib.util
import io
import json
import os
import socket
import sys
import unittest
import urllib.error
import urllib.request
import urllib.response
from unittest import mock

from base import SCRIPT, Base

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import jev as J  # noqa: E402
from tuneup import mascara as M  # noqa: E402

CHAVE = "chave-de-teste-ZZ9xq"  # fake; must never show up anywhere
PERG = {"a": "Is it A?", "b": "Is it B?"}


def _resp(**answers):
    return json.dumps({"answers": {n: {"noul": v} for n, v in answers.items()}}).encode("utf-8")


class Fake:
    def __init__(self, resposta=None, erro=None):
        self.resposta, self.erro, self.chamadas = resposta, erro, []

    def __call__(self, url, cabecalhos, corpo, timeout):
        self.chamadas.append((url, cabecalhos, json.loads(corpo.decode("utf-8")), timeout))
        if self.erro:
            raise self.erro
        return self.resposta


class TestJev(Base):
    USER_JSON = None

    def setUp(self):
        super().setUp()
        p = mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": self.dados})
        p.start()
        self.addCleanup(p.stop)
        self.settings = os.path.join(self.tmp, "settings.json")  # never the real ~/.claude/settings.json

    def settings_com(self, conteudo):
        with open(self.settings, "w", encoding="utf-8") as f:
            f.write(conteudo)

    def log(self):
        p = os.path.join(self.dados, "erros.log")
        if not os.path.exists(p):
            return ""
        with open(p, encoding="utf-8") as f:
            return f.read()

    def perguntar(self, transporte, ambiente=None, texto="some text"):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            r = J.perguntar(texto, PERG, transporte=transporte,
                            ambiente={"TYPESAFE_API_KEY": CHAVE} if ambiente is None else ambiente,
                            settings=self.settings)
        for onde in (out.getvalue(), err.getvalue(), self.log()):
            self.assertNotIn(CHAVE, onde)
        return r

    def test_ok_contract(self):
        f = Fake(_resp(a=0.25, b=1))
        self.assertEqual(self.perguntar(f), {"a": 0.25, "b": 1.0})
        url, cab, corpo, timeout = f.chamadas[0]
        self.assertEqual(url, "https://api.typesafe.ai/v1/systemone")
        self.assertEqual(cab, {"authorization": "Bearer " + CHAVE, "content-type": "application/json"})
        self.assertEqual(timeout, 5)
        self.assertEqual(corpo["model"], "jev-latest")
        self.assertEqual(corpo["questions"], {"a": {"type": "noul", "instructions": "Is it A?"},
                                              "b": {"type": "noul", "instructions": "Is it B?"}})
        self.assertEqual(corpo["state"], {"task": "some text"})

    def test_text_is_masked_before_sending(self):
        f = Fake(_resp(a=0.1, b=0.2))
        self.perguntar(f, texto="mail joao@example.com tel 19999998888 Bearer abcdefghijkl123")
        task = f.chamadas[0][2]["state"]["task"]
        for segredo in ("joao@", "19999998888", "abcdefghijkl123"):
            self.assertNotIn(segredo, task)
        self.assertEqual(task, M.mascarar("mail joao@example.com tel 19999998888 Bearer abcdefghijkl123"))

    def test_key_from_settings_when_env_empty(self):
        self.settings_com(json.dumps({"env": {"TYPESAFE_API_KEY": CHAVE}}))
        f = Fake(_resp(a=0.5, b=0.5))
        self.assertEqual(self.perguntar(f, ambiente={"TYPESAFE_API_KEY": ""}), {"a": 0.5, "b": 0.5})
        self.assertEqual(f.chamadas[0][1]["authorization"], "Bearer " + CHAVE)

    def test_env_wins_over_settings(self):
        self.settings_com(json.dumps({"env": {"TYPESAFE_API_KEY": "outra-chave"}}))
        f = Fake(_resp(a=0.5, b=0.5))
        self.perguntar(f)
        self.assertEqual(f.chamadas[0][1]["authorization"], "Bearer " + CHAVE)

    def test_no_key_returns_none_without_call(self):
        for conteudo in (None, "{not json", "[]", json.dumps({"env": {"TYPESAFE_API_KEY": 7}}),
                         json.dumps({"env": None})):
            if conteudo is not None:
                self.settings_com(conteudo)
            f = Fake(_resp(a=0.5, b=0.5))
            self.assertIsNone(self.perguntar(f, ambiente={}), conteudo)
            self.assertEqual(f.chamadas, [])
        self.assertIn("jev no key", self.log())

    def test_transport_errors_return_none(self):
        erros = [socket.timeout("timed out"), TimeoutError(),
                 urllib.error.HTTPError(J.URL, 500, "boom " + CHAVE, {}, None),
                 urllib.error.URLError("refused"), RuntimeError("leak " + CHAVE)]
        for e in erros:
            self.assertIsNone(self.perguntar(Fake(erro=e)), repr(type(e)))
        self.assertIn("HTTPError 500", self.log())

    def test_bad_responses_return_none(self):
        ruins = [b"not json", b"[]", b"{}", json.dumps({"answers": []}).encode(),
                 _resp(a=0.5),  # missing answer b
                 json.dumps({"answers": {"a": {"noul": 0.5}, "b": {}}}).encode(),
                 _resp(a=0.5, b="0.5"), _resp(a=0.5, b=None), _resp(a=0.5, b=True),
                 _resp(a=0.5, b=1.01), _resp(a=-0.01, b=0.5), b'{"answers":{"a":{"noul":NaN},"b":{"noul":0}}}']
        for r in ruins:
            self.assertIsNone(self.perguntar(Fake(r)), r)

    def test_redirect_to_other_host_is_refused(self):
        visitados = []

        class FakeHTTPS(urllib.request.HTTPSHandler):
            def https_open(self, req):
                host = req.host
                visitados.append((host, req.get_header("Authorization")))
                hdr = email.message.Message()
                if host == "api.typesafe.ai":
                    hdr["Location"] = "https://evil.example/steal"
                    r = urllib.response.addinfourl(io.BytesIO(b""), hdr, req.full_url, 302)
                else:
                    r = urllib.response.addinfourl(io.BytesIO(_resp(a=0.5, b=0.5)), hdr, req.full_url, 200)
                r.msg = "x"  # read by urllib's HTTPErrorProcessor
                return r

        def transporte(url, cab, corpo, timeout):
            return J._urllib(url, cab, corpo, timeout, abridor=J._abridor(FakeHTTPS()))

        self.assertIsNone(self.perguntar(transporte))
        self.assertEqual([h for h, _ in visitados], ["api.typesafe.ai"])
        self.assertEqual(visitados[0][1], "Bearer " + CHAVE)  # sent to the first host only
        self.assertIn("HTTPError 302", self.log())


class TestMascaraCopia(unittest.TestCase):
    def test_copy_matches_panel(self):
        raiz = os.path.dirname(os.path.dirname(SCRIPT))
        spec = importlib.util.spec_from_file_location("painel_mascara", os.path.join(raiz, "painel", "mascara.py"))
        painel = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(painel)
        amostras = ["Authorization: Bearer abcdefghijklmnop123", "token=s3cr3tvalue", "sk-abcdefghijklmnopqrst",
                    "ghp_abcdefghijklmnopqrstuv", "fale com maria@example.com.br", "(19) 99999-8888",
                    "+5519999998888", "19 3456 7890", "texto comum sem nada", "",
                    "AKIAABCDEFGHIJKLMNOP e eyJabcdefghij.klmnopqrstu.vwxyz12"]
        for s in amostras:
            self.assertEqual(M.mascarar(s), painel.mascarar(s), s)
            self.assertEqual(M.primeira_linha(s), painel.primeira_linha(s), s)


if __name__ == "__main__":
    unittest.main()
