"""C10: GET /api/modulos/<id>/arquivo?c= (mídia do módulo, com Range) e os 3 casos de POST de comando.

Servidor de verdade numa porta livre, módulos falsos num pacote temporário. Nada chama o claude.
"""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402

import config  # noqa: E402
import midia  # noqa: E402
import modulos  # noqa: E402
import painel  # noqa: E402
from test_http import TesteHTTP  # noqa: E402
from test_modulos import escrever  # noqa: E402

GALERIA = '''
INFO = {"titulo": "Galeria", "midia": "pecas", "acoes": ["salvar"], "esquemas": {"salvar": {"nome": "texto"}}}
def montar(ctx):
    return {}
def agir(ctx, acao, dados):
    return {"ok": True}
'''
VIDEO = bytes(range(256)) * 4 + b"fim!"  # 1028 bytes, cada trecho é conferível


def _symlink(alvo, nome):
    try:
        os.symlink(alvo, nome)
        return True
    except (OSError, NotImplementedError):  # Windows sem permissão de atalho
        return False


class TesteMidia(unittest.TestCase):
    pedir, cab_post, post = TesteHTTP.pedir, TesteHTTP.cab_post, TesteHTTP.post

    @classmethod
    def setUpClass(cls):
        cls.tmp = t = os.path.realpath(tempfile.mkdtemp())
        pac = os.path.join(t, ".tune-up", "painel-projeto")
        escrever(os.path.join(pac, "modulos", "galeria", "modulo.py"), GALERIA)
        escrever(os.path.join(pac, "modulos", "sem_midia", "modulo.py"), "def montar(ctx):\n    return {}\n")
        escrever(os.path.join(pac, "modulos", "sobe", "modulo.py"),
                 'INFO = {"midia": "../modulos"}\ndef montar(ctx):\n    return {}\n')
        escrever(os.path.join(pac, "modulos", "atalho", "modulo.py"),
                 'INFO = {"midia": "link"}\ndef montar(ctx):\n    return {}\n')
        escrever(os.path.join(t, ".tune-up", "painel.json"), json.dumps(
            {"nome": "Midia", "modulos": ["galeria", "sem_midia", "sobe", "atalho"]}))
        pecas = os.path.join(pac, "dados", "pecas")
        os.makedirs(os.path.join(pecas, "sub"))
        for nome, dado in (("v.mp4", VIDEO), ("a.png", b"\x89PNG-falso"), ("sub/b.webm", b"webm"),
                           ("x.svg", b"<svg/>"), ("x.html", b"<b>"), ("vazio.mp4", b""),
                           (".oculto.png", b"oculto")):
            with open(os.path.join(pecas, *nome.split("/")), "wb") as f:
                f.write(dado)
        with open(os.path.join(pac, "dados", "irmao.png"), "wb") as f:
            f.write(b"fora da pasta declarada")
        with open(os.path.join(t, "segredo.png"), "wb") as f:
            f.write(b"NAO PODE SAIR")
        cls.tem_atalho = _symlink(os.path.join(t, "segredo.png"), os.path.join(pecas, "fuga.png"))
        _symlink(os.path.join(pecas, "v.mp4"), os.path.join(pecas, "dentro.mp4"))
        _symlink(t, os.path.join(pac, "dados", "link"))
        cls.cfg = config.carregar(t, home=t)
        cls.app = painel.App(cls.cfg, rodar_externos=False)
        cls.app.log = False
        cls.srv = painel.criar_servidor(cls.app, 0)
        cls.porta = cls.app.porta
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        modulos.esquecer()
        shutil.rmtree(cls.tmp)

    def arq(self, c, rng=None, mid="galeria", metodo="GET", **cab):
        cab = dict(cab)
        if rng is not None:
            cab["Range"] = rng
        return self.pedir(metodo, "/api/modulos/%s/arquivo?c=%s" % (mid, c), cab=cab)

    # ---- C10: caminho
    def test_c10_ponto_ponto_404(self):
        for c in ("../irmao.png", "sub/../../irmao.png", "../../painel.json"):
            self.assertEqual(self.arq(c)[0], 404, c)

    def test_c10_ponto_ponto_codificado_404(self):
        for c in ("%2e%2e/irmao.png", "%2E%2E%2Firmao.png", "sub%2f..%2f..%2firmao.png", "..%5cirmao.png"):
            st, _c, dados = self.arq(c)
            self.assertEqual(st, 404, c)
            self.assertNotIn(b"fora da pasta", dados)

    def test_c10_caminho_absoluto_recusado(self):
        absoluto = os.path.join(self.tmp, "segredo.png")
        for c in (absoluto, "/" + absoluto.lstrip("/"), "C:%5csegredo.png", "C:/segredo.png", "%2fetc%2fx.png"):
            st, _c, dados = self.arq(c)
            self.assertEqual(st, 404, c)
            self.assertNotIn(b"NAO PODE SAIR", dados)

    def test_c10_atalho_para_fora_recusado(self):
        if not self.tem_atalho:
            self.skipTest("sem permissão de symlink")
        st, _c, dados = self.arq("fuga.png")
        self.assertEqual(st, 404)
        self.assertNotIn(b"NAO PODE SAIR", dados)
        st, _c, dados = self.arq("dentro.mp4")  # atalho que fica dentro da pasta passa
        self.assertEqual((st, dados), (200, VIDEO))

    def test_c10_svg_recusado(self):
        self.assertEqual(self.arq("x.svg")[0], 404)

    def test_c10_html_recusado(self):
        self.assertEqual(self.arq("x.html")[0], 404)

    # ---- C10: Range
    def test_c10_range_inicio_da_206(self):
        st, cab, dados = self.arq("v.mp4", "bytes=0-99")
        self.assertEqual(st, 206)
        self.assertEqual(cab["content-range"], "bytes 0-99/%d" % len(VIDEO))
        self.assertEqual((cab["content-length"], dados), ("100", VIDEO[:100]))
        self.assertEqual((cab["content-type"], cab["accept-ranges"]), ("video/mp4", "bytes"))

    def test_c10_range_alem_do_fim_416(self):
        for rng in ("bytes=%d-" % len(VIDEO), "bytes=5000-6000", "bytes=-0"):
            st, cab, _d = self.arq("v.mp4", rng)
            self.assertEqual(st, 416, rng)
            self.assertEqual(cab["content-range"], "bytes */%d" % len(VIDEO))
        self.assertEqual(self.arq("vazio.mp4", "bytes=-10")[0], 416)

    def test_c10_sufixo_da_o_fim(self):
        st, cab, dados = self.arq("v.mp4", "bytes=-100")
        n = len(VIDEO)
        self.assertEqual((st, cab["content-range"], dados), (206, "bytes %d-%d/%d" % (n - 100, n - 1, n), VIDEO[-100:]))
        self.assertTrue(dados.endswith(b"fim!"))
        st, cab, dados = self.arq("v.mp4", "bytes=-99999")  # maior que o arquivo: o arquivo todo
        self.assertEqual((st, cab["content-range"], dados), (206, "bytes 0-%d/%d" % (n - 1, n), VIDEO))

    def test_c10_varios_intervalos_da_200_inteiro(self):
        for rng in ("bytes=0-9,20-29", "bytes=0-9, -5", "bytes=-5,0-1"):
            st, cab, dados = self.arq("v.mp4", rng)
            self.assertEqual((st, dados), (200, VIDEO), rng)
            self.assertNotIn("content-range", cab)

    # ---- C10: POST de comando (os 3 que a Parte 3 já cobria, aqui contra um módulo com esquema)
    def test_c10_post_sem_token_403(self):
        ok = {"acao": "salvar", "dados": {"nome": "x"}}
        self.assertEqual(self.post("/api/modulos/galeria/acao", ok)[0], 200)
        self.assertEqual(self.post("/api/modulos/galeria/acao", ok, **{"X-Painel-Token": None})[0], 403)

    def test_c10_post_cross_site_403(self):
        ok = {"acao": "salvar", "dados": {"nome": "x"}}
        self.assertEqual(self.post("/api/modulos/galeria/acao", ok, **{"Sec-Fetch-Site": "cross-site"})[0], 403)
        st, _c, _d = self.arq("v.mp4", **{"Sec-Fetch-Site": "cross-site"})  # a mídia também
        self.assertEqual(st, 403)

    def test_c10_post_campo_desconhecido_400(self):
        st, _d = self.post("/api/modulos/galeria/acao", {"acao": "salvar", "dados": {"nome": "x", "outro": 1}})
        self.assertEqual(st, 400)

    # ---- além do C10
    def test_arquivo_inteiro_cabecalhos_e_subpasta(self):
        st, cab, dados = self.arq("v.mp4")
        self.assertEqual((st, dados, cab["accept-ranges"]), (200, VIDEO, "bytes"))
        self.assertIn("media-src 'self'", cab["content-security-policy"])
        self.assertEqual(cab["x-content-type-options"], "nosniff")
        self.assertEqual(self.arq("sub/b.webm")[1]["content-type"], "video/webm")
        self.assertEqual(self.arq("a.png")[1]["content-type"], "image/png")

    def test_range_aberto_meio_e_head(self):
        st, cab, dados = self.arq("v.mp4", "bytes=1000-")
        self.assertEqual((st, cab["content-range"], dados), (206, "bytes 1000-1027/1028", VIDEO[1000:]))
        st, cab, dados = self.arq("v.mp4", "bytes=10-10")
        self.assertEqual((st, dados), (206, VIDEO[10:11]))
        st, cab, dados = self.arq("v.mp4", "bytes=1000-99999")  # fim depois do arquivo é cortado
        self.assertEqual((st, cab["content-range"]), (206, "bytes 1000-1027/1028"))
        for lixo in ("bytes=9-2", "items=0-9", "bytes=x-y", "bytes=-"):
            self.assertEqual(self.arq("v.mp4", lixo)[:3:2], (200, VIDEO), lixo)
        st, cab, dados = self.arq("v.mp4", "bytes=0-99", metodo="HEAD")
        self.assertEqual((st, cab["content-length"], dados), (206, "100", b""))

    def test_pasta_nao_declarada_ou_fora_de_dados(self):
        for mid in ("sem_midia", "sobe", "atalho", "sumido", "..", "galeria%2f..%2fsobe"):
            self.assertEqual(self.arq("v.mp4", mid=mid)[0], 404, mid)

    def test_recusas_de_nome(self):
        for c in ("", ".oculto.png", "sub//b.webm", "./v.mp4", "v.mp4%00.png", "nada.png", "sub", "v.MP4x"):
            self.assertEqual(self.arq(c)[0], 404, c)
        self.assertEqual(self.pedir("GET", "/api/modulos/galeria/arquivo")[0], 404)


class TesteIntervalo(unittest.TestCase):
    def test_tabela(self):
        casos = [(None, None), ("bytes=0-0", (0, 0)), ("bytes=-1", (9, 9)), ("bytes=3-", (3, 9)),
                 ("bytes=10-", "416"), ("bytes=-0", "416"), ("bytes=0-1,2-3", None), ("bytes=5-1", None),
                 (" bytes=1-2 ", (1, 2)), ("bytes=" + "9" * 19 + "-", None)]
        for valor, esperado in casos:
            self.assertEqual(midia._intervalo(valor, 10), esperado, valor)


if __name__ == "__main__":
    unittest.main()
