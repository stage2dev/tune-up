"""GET /api/modulos/<id>/arquivo?ref= (arquivo(ctx, ref) do módulo) e a conferência de `midia` nas mensagens.

Servidor de verdade numa porta livre, módulo falso num pacote temporário. Nada sai da máquina.
"""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

import arquivo_ref  # noqa: E402
import config  # noqa: E402
import modulos  # noqa: E402
import painel  # noqa: E402
from modulos_forma import conferir  # noqa: E402
import test_http  # noqa: E402 - so o pedir(); importar a classe rodaria os testes dela de novo aqui
from test_modulos import escrever  # noqa: E402

ARQ = '''
import time
INFO = {"titulo": "Arquivos"}
CHAMADAS = []
def montar(ctx):
    return {}
def arquivo(ctx, ref):
    CHAMADAS.append(ref)
    if ref == "audio":
        return {"mime": "audio/ogg", "dados": b"OggS-falso-0123"}
    if ref == "svg":
        return {"mime": "image/svg+xml", "dados": b"<svg/>"}
    if ref == "html":
        return {"mime": "text/html", "dados": b"<b>oi</b>"}
    if ref == "grande":
        return {"mime": "image/png", "dados": b"0" * (25 * 1024 * 1024 + 1)}
    if ref == "pdf":
        return {"mime": "application/pdf", "dados": b"%PDF-1", "nome": 'Or\\u00e7amento "final"\\r\\n.pdf'}
    if ref == "bin":
        return {"mime": "application/octet-stream", "dados": b"\\x00\\x01"}
    if ref == "foto:baixar":
        return {"mime": "image/jpeg", "dados": b"jpg", "nome": "foto.jpg", "baixar": True}
    if ref == "torto":
        return {"mime": "audio/ogg", "dados": "texto, nao bytes"}
    if ref.startswith("lento:"):
        time.sleep(float(ref.split(":")[1]))
        return {"mime": "audio/ogg", "dados": b"x"}
    if ref == "quebra":
        raise RuntimeError("segredo " + ref)
    raise KeyError(ref)
'''


def _esperar_vagas():
    fim = time.monotonic() + 5
    while arquivo_ref._vagas._value < arquivo_ref.VAGAS and time.monotonic() < fim:
        time.sleep(0.05)


class TesteArquivoRef(unittest.TestCase):
    pedir = test_http.TesteHTTP.pedir

    @classmethod
    def setUpClass(cls):
        cls.tmp = t = os.path.realpath(tempfile.mkdtemp())
        pac = os.path.join(t, ".tune-up", "painel-projeto")
        escrever(os.path.join(pac, "modulos", "arq", "modulo.py"), ARQ)
        escrever(os.path.join(pac, "modulos", "sem_arquivo", "modulo.py"), "def montar(ctx):\n    return {}\n")
        escrever(os.path.join(t, ".tune-up", "painel.json"), json.dumps(
            {"nome": "Arquivos", "modulos": ["arq", "sem_arquivo"]}))
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

    def setUp(self):
        self.chamadas = modulos.carregar(self.cfg, "arq").CHAMADAS
        del self.chamadas[:]
        self.tempo_antes = arquivo_ref.TEMPO_LIMITE

    def tearDown(self):
        arquivo_ref.TEMPO_LIMITE = self.tempo_antes
        _esperar_vagas()

    def arq(self, ref, mid="arq", metodo="GET", sfs="same-origin", **cab):
        if sfs is not None:
            cab["Sec-Fetch-Site"] = sfs
        return self.pedir(metodo, "/api/modulos/%s/arquivo?ref=%s" % (mid, ref), cab=cab)

    def test_audio_cabecalhos(self):
        st, cab, dados = self.arq("audio")
        self.assertEqual((st, dados), (200, b"OggS-falso-0123"))
        self.assertEqual(cab["content-type"], "audio/ogg")
        self.assertEqual(cab["x-content-type-options"], "nosniff")
        self.assertEqual(cab["cache-control"], "private, max-age=300")
        self.assertIn("sandbox", cab["content-security-policy"])
        self.assertNotIn("script-src", cab["content-security-policy"])
        self.assertNotIn("content-disposition", cab)

    def test_head_sem_corpo_e_range_206(self):
        st, cab, dados = self.arq("audio", metodo="HEAD")
        self.assertEqual((st, dados, cab["content-length"]), (200, b"", "15"))
        st, cab, dados = self.arq("audio", Range="bytes=0-3")
        self.assertEqual((st, dados, cab["content-range"]), (206, b"OggS", "bytes 0-3/15"))

    def test_sem_sec_fetch_site_403_sem_chamar_o_modulo(self):
        for sfs in (None, "none", "same-site", "cross-site"):
            st, cab, dados = self.arq("audio", sfs=sfs)
            self.assertEqual(st, 403, sfs)
            self.assertNotIn(b"OggS", dados)
        self.assertEqual(self.chamadas, [])

    def test_host_de_fora_421(self):
        st, _c, _d = self.arq("audio", Host="evil.example")
        self.assertEqual(st, 421)

    def test_mime_fora_da_lista_415(self):
        for ref in ("svg", "html"):
            st, cab, dados = self.arq(ref)
            self.assertEqual(st, 415, ref)
            self.assertNotIn(b"<", dados)
            self.assertTrue(cab["content-type"].startswith("application/json"))

    def test_grande_demais_413(self):
        st, _c, _d = self.arq("grande")
        self.assertEqual(st, 413)

    def test_pdf_e_octet_stream_sempre_anexo_com_nome_limpo(self):
        st, cab, dados = self.arq("pdf")
        self.assertEqual((st, dados, cab["content-type"]), (200, b"%PDF-1", "application/pdf"))
        self.assertEqual(cab["content-disposition"],
                         'attachment; filename="Orcamento final.pdf"; filename*=UTF-8\'\'Or%C3%A7amento%20final.pdf')
        st, cab, _d = self.arq("bin")
        self.assertEqual((st, cab["content-disposition"]), (200, 'attachment; filename="arquivo"'))

    def test_baixar_true_vira_anexo(self):
        st, cab, _d = self.arq("foto:baixar")
        self.assertEqual((st, cab["content-disposition"]), (200, 'attachment; filename="foto.jpg"'))

    def test_modulo_sem_arquivo_ou_inexistente_404(self):
        self.assertEqual(self.arq("audio", mid="sem_arquivo")[0], 404)
        self.assertEqual(self.arq("audio", mid="nao_tem")[0], 404)

    def test_nao_achou_404_quebrou_500_sem_texto_da_excecao(self):
        self.assertEqual(self.arq("sumiu")[0], 404)
        st, _c, dados = self.arq("quebra")
        self.assertEqual(st, 500)
        self.assertNotIn(b"segredo", dados)
        self.assertEqual(self.arq("torto")[0], 500)

    def test_ref_com_cara_de_caminho_recusada_antes_do_modulo(self):
        for ref in ("..", "../x", "..%2F..%2Fetc%2Fpasswd", "a%2Fb", "%2E%2E", ".oculto", "a..b", "a%5Cb",
                    "a%00b", "a+b", "x" * 201, "aud%C3%ADo"):
            st, _c, _d = self.arq(ref)
            self.assertEqual(st, 400, ref)
        st, _c, _d = self.pedir("GET", "/api/modulos/arq/arquivo?ref=audio&ref=pdf",
                                cab={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(st, 400)
        self.assertEqual(self.chamadas, [])

    def test_tempo_limite_504(self):
        arquivo_ref.TEMPO_LIMITE = 0.2
        inicio = time.monotonic()
        st, _c, _d = self.arq("lento:1")
        self.assertEqual(st, 504)
        self.assertLess(time.monotonic() - inicio, 0.9)

    def test_vagas_limitadas_503_sem_chamar_e_voltam(self):
        arquivo_ref.TEMPO_LIMITE = 0.1
        for _ in range(arquivo_ref.VAGAS):
            self.assertEqual(self.arq("lento:1.2")[0], 504)
        self.assertEqual(self.arq("audio")[0], 503)
        self.assertNotIn("audio", self.chamadas)
        _esperar_vagas()
        self.assertEqual(self.arq("audio")[0], 200)

    def test_rota_c_da_pasta_de_midia_continua_sem_ref(self):
        st, _c, _d = self.pedir("GET", "/api/modulos/arq/arquivo?c=x.png", cab={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual(st, 404)  # arq não declara INFO["midia"]: caiu em midia.py, não em arquivo()
        self.assertEqual(self.chamadas, [])

    def test_registro_sem_ref(self):
        linha = '"GET /api/modulos/arq/arquivo?ref=conversa:123&x=1 HTTP/1.1" 200 -'
        self.assertEqual(arquivo_ref.sem_ref(linha), '"GET /api/modulos/arq/arquivo?ref=*&x=1 HTTP/1.1" 200 -')
        self.assertEqual(arquivo_ref.sem_ref('"GET /x?a=1&ref=abc HTTP/1.1"'), '"GET /x?a=1&ref=* HTTP/1.1"')


INF = {"id": "m", "titulo": "M"}
BOA = {"ref": "msg:1", "tipo": "audio", "nome": "a.ogg", "tamanho": 10, "duracao": 3.5, "estado": "falhou",
       "aviso": "Expirou", "acao": {"acao": "baixar", "dados": {"id": "1"}}}


def _conv(*msgs):
    return {"abas": [{"id": "a", "blocos": [{"tipo": "conversa", "mensagens": list(msgs)}]}]}


class TesteConferirMidia(unittest.TestCase):
    def msgs(self, saida):
        return saida["abas"][0]["blocos"][0]["mensagens"]

    def test_midia_boa_passa_e_chave_extra_sai(self):
        s = conferir(_conv({"id": "1", "midia": dict(BOA, url="javascript:alert(1)"), "transcricao": "oi"}), INF)
        self.assertEqual(self.msgs(s)[0]["midia"], BOA)
        self.assertEqual(self.msgs(s)[0]["transcricao"], "oi")
        self.assertEqual(s["avisos"], [])

    def test_midia_ruim_sai_com_aviso(self):
        ruins = [{"tipo": "audio"}, dict(BOA, ref="../x"), dict(BOA, tipo="video"), dict(BOA, estado="ok"),
                 dict(BOA, tamanho=-1), dict(BOA, duracao="3"), dict(BOA, nome=3), dict(BOA, acao={"dados": {}}),
                 dict(BOA, acao={"acao": "x", "dados": []}), "msg:1", dict(BOA, ref="x" * 201)]
        s = conferir(_conv(*[{"id": str(i), "texto": "t", "midia": m} for i, m in enumerate(ruins)]), INF)
        self.assertTrue(all("midia" not in m and m["texto"] == "t" for m in self.msgs(s)))
        self.assertEqual(len(s["avisos"]), len(ruins))

    def test_transcricao_que_nao_e_texto_sai(self):
        s = conferir(_conv({"id": "1", "transcricao": {"x": 1}}), INF)
        self.assertNotIn("transcricao", self.msgs(s)[0])
        self.assertEqual(len(s["avisos"]), 1)

    def test_conversa_da_caixa_tambem_e_conferida(self):
        caixa = {"tipo": "caixa", "conversas": [], "abrir": {"acao": "abrir"},
                 "conversa": {"mensagens": [{"id": "1", "midia": {"ref": "a b", "tipo": "audio"}}]}}
        s = conferir({"abas": [{"id": "a", "blocos": [caixa]}]}, INF)
        self.assertNotIn("midia", s["abas"][0]["blocos"][0]["conversa"]["mensagens"][0])
        self.assertEqual(len(s["avisos"]), 1)


if __name__ == "__main__":
    unittest.main()
