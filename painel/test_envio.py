"""POST /api/modulos/<id>/envio?destino=<chave>: imagem crua, tipo pelos bytes, nome do servidor (envio.py).

Servidor de verdade numa porta livre, módulos falsos num pacote temporário. Nada chama o claude.
"""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import struct  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
import zlib  # noqa: E402

import config  # noqa: E402
import envio  # noqa: E402
import modulos  # noqa: E402
import painel  # noqa: E402
import test_http  # noqa: E402
from test_midia import _symlink  # noqa: E402
from test_modulos import escrever  # noqa: E402

MARCA = '''
import json, os
INFO = {"midia": ["fotos", "logo"], "envios": {
    "fotos": {"pasta": "fotos", "tipos": ["png", "jpeg", "webp"], "max_bytes": 2000000, "max_arquivos": 50,
              "gancho": True},
    "logo": {"pasta": "logo", "tipos": ["png"], "max_bytes": 100000, "max_arquivos": 2},
    "fora": {"pasta": "link", "tipos": ["png"], "max_bytes": 100000, "max_arquivos": 5},
    "enorme": {"pasta": "fotos", "tipos": ["png"], "max_bytes": 100000000, "max_arquivos": 5}}}
def montar(ctx):
    n = len(os.listdir(os.path.join(ctx["dados"], "fotos"))) if os.path.isdir(os.path.join(ctx["dados"], "fotos")) else 0
    return {"abas": [{"id": "a", "blocos": [{"tipo": "texto", "texto": str(n)}]}]}
def agir(ctx, acao, dados):
    with open(os.path.join(ctx["dados"], "ganchos.log"), "a") as f:
        f.write(json.dumps([acao, dados, callable(ctx.get("gravar_dono"))]) + "\\n")
    if os.path.exists(os.path.join(ctx["dados"], "recusar")):
        return {"feito": False, "mensagem": "sem marca"}
    return {}
'''


def _chunk(nome, dado):
    return struct.pack(">I", len(dado)) + nome + dado + struct.pack(">I", zlib.crc32(nome + dado) & 0xFFFFFFFF)


def png(w=2, h=2, semente=b"", fim=b""):
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(b"\x00" * 13 + semente))
            + _chunk(b"IEND", b"") + fim)


JPEG = (b"\xff\xd8\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        + b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, 30, 40, 1) + b"\x01\x11\x00" + b"\xff\xd9")
VP8L = b"RIFF" + struct.pack("<I", 4 + 8 + 10) + b"WEBP" + b"VP8L" + struct.pack("<I", 10) + b"\x2f" \
    + struct.pack("<I", (40 - 1) | ((30 - 1) << 14)) + b"\x00" * 5


class TesteTipo(unittest.TestCase):
    def test_tipos_pelos_bytes(self):
        self.assertEqual(envio.tipo_dos_bytes(png(7, 9)), ("png", 7, 9))
        self.assertEqual(envio.tipo_dos_bytes(JPEG), ("jpeg", 40, 30))
        self.assertEqual(envio.tipo_dos_bytes(VP8L), ("webp", 40, 30))
        vp8 = b"RIFF" + struct.pack("<I", 22) + b"WEBP" + b"VP8 " + struct.pack("<I", 10) + b"\x00\x00\x00" \
            + b"\x9d\x01\x2a" + struct.pack("<HH", 50, 60)
        self.assertEqual(envio.tipo_dos_bytes(vp8), ("webp", 50, 60))
        vp8x = b"RIFF" + struct.pack("<I", 22) + b"WEBP" + b"VP8X" + struct.pack("<I", 10) + b"\x00" * 4 \
            + (99).to_bytes(3, "little") + (49).to_bytes(3, "little")
        self.assertEqual(envio.tipo_dos_bytes(vp8x), ("webp", 100, 50))

    def test_bytes_que_mentem(self):
        for mentira in (b"<svg xmlns='http://www.w3.org/2000/svg'/>", b"GIF89a" + b"\x00" * 40,
                        b"\x89PNG\r\n\x1a\n<html><script>alert(1)</script></html>",  # assinatura e nada mais
                        png(fim=b"<html>"),  # bytes depois do IEND (poliglota)
                        png()[:-12],  # sem IEND
                        png(0, 5),  # largura zero
                        b"\xff\xd8\xff\xd9" + b"\x00" * 20,  # JPEG sem SOF
                        b"RIFF\xff\xff\xff\x7fWEBPVP8L" + b"\x00" * 20):  # RIFF maior que o arquivo
            self.assertIsNone(envio.tipo_dos_bytes(mentira), mentira[:20])


class TesteEnvio(unittest.TestCase):
    pedir, cab_post = test_http.TesteHTTP.pedir, test_http.TesteHTTP.cab_post

    @classmethod
    def setUpClass(cls):
        cls.tmp = t = os.path.realpath(tempfile.mkdtemp())
        pac = os.path.join(t, ".tune-up", "painel-projeto")
        cls.dados = os.path.join(pac, "dados")
        escrever(os.path.join(pac, "modulos", "marca", "modulo.py"), MARCA)
        escrever(os.path.join(pac, "modulos", "sem", "modulo.py"), 'INFO = {"midia": "x"}\ndef montar(ctx):\n    return {}\n')
        escrever(os.path.join(pac, "modulos", "ruim", "modulo.py"),
                 'INFO = {"envios": {"a": {"pasta": "../modulos", "tipos": ["png"], "max_bytes": 9, '
                 '"max_arquivos": 1}}}\ndef montar(ctx):\n    return {}\n')
        escrever(os.path.join(t, ".tune-up", "painel.json"),
                 json.dumps({"nome": "Envio", "modulos": ["marca", "sem", "ruim"]}))
        cls.fora = os.path.join(t, "fora")
        os.makedirs(cls.fora)
        os.makedirs(cls.dados, exist_ok=True)
        cls.tem_atalho = _symlink(cls.fora, os.path.join(cls.dados, "link"))
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

    def enviar(self, corpo, destino="fotos", mid="marca", **troca):
        cab = self.cab_post(**dict({"Content-Type": "image/png"}, **troca))
        st, _c, dados = self.pedir("POST", "/api/modulos/%s/envio?destino=%s" % (mid, destino), corpo, cab)
        return st, json.loads(dados or b"null")

    def cru(self, cabecalhos, corpo=b"", fechar_escrita=False, destino="fotos"):
        """Pedido à mão: o corpo pode ser menor que o Content-Length. Devolve (status, segundos)."""
        s = socket.create_connection(("127.0.0.1", self.porta), timeout=8)
        inicio = time.monotonic()
        try:
            linhas = ["POST /api/modulos/marca/envio?destino=%s HTTP/1.1" % destino, "Host: 127.0.0.1:%d" % self.porta]
            linhas += ["%s: %s" % kv for kv in self.cab_post(**{"Content-Type": "image/png"}).items()] + cabecalhos
            s.sendall(("\r\n".join(linhas) + "\r\n\r\n").encode() + corpo)
            if fechar_escrita:
                s.shutdown(socket.SHUT_WR)
            resp = s.recv(200)
        finally:
            s.close()
        return int(resp.split(b" ", 2)[1]), time.monotonic() - inicio

    def arquivos(self, pasta):
        p = os.path.join(self.dados, pasta)
        return sorted(os.listdir(p)) if os.path.isdir(p) else []

    # ---- caminho feliz, repetição e gancho
    def test_png_gravado_com_nome_do_servidor_e_servido_pela_midia(self):
        corpo = png(semente=b"feliz")
        st, d = self.enviar(corpo)
        self.assertEqual(st, 201, d)
        nome = d["caminho"].split("/")[-1]
        self.assertRegex(nome, r"^[0-9a-f]{16}\.png$")
        self.assertEqual((d["c"], d["tipo"], d["largura"], d["repetido"]), (d["caminho"], "png", 2, False))
        with open(os.path.join(self.dados, "fotos", nome), "rb") as f:
            self.assertEqual(f.read(), corpo)
        st, _c, servido = self.pedir("GET", "/api/modulos/marca/arquivo?c=" + d["c"])
        self.assertEqual((st, servido), (200, corpo))
        self.assertFalse([n for n in self.arquivos("fotos") if n.startswith(".")])  # nada de temporário

    def test_jpeg_e_webp_ganham_extensao_pelo_conteudo(self):
        self.assertTrue(self.enviar(JPEG, **{"Content-Type": "image/png"})[1]["caminho"].endswith(".jpg"))
        self.assertTrue(self.enviar(VP8L, **{"Content-Type": "text/plain"})[1]["caminho"].endswith(".webp"))

    def test_duas_requisicoes_iguais_nao_duplicam(self):
        corpo = png(semente=b"repetida")
        st1, d1 = self.enviar(corpo)
        antes = self.arquivos("fotos")
        st2, d2 = self.enviar(corpo)
        self.assertEqual((st1, st2, d2["repetido"], d1["caminho"]), (201, 200, True, d2["caminho"]))
        self.assertEqual(antes, self.arquivos("fotos"))
        with open(os.path.join(self.dados, "ganchos.log")) as f:  # o gancho roda de novo: registrar é idempotente
            self.assertEqual(sum(1 for linha in f if d1["caminho"] in linha), 2)
        self.assertEqual((d1["registrado"], d2["registrado"]), (True, True))

    def test_gancho_ocupado_ou_que_recusa_nao_vira_sucesso_e_reenvio_registra(self):
        corpo, pare = png(semente=b"ocupado"), threading.Event()
        t = threading.Thread(target=pare.wait, daemon=True)
        t.start()
        modulos._agindo["marca"] = t  # outra ação do módulo em andamento
        try:
            st, d = self.enviar(corpo)
        finally:
            pare.set()
            t.join()
            modulos._agindo.pop("marca", None)
        self.assertEqual((st, d["registrado"]), (201, False))
        self.assertIn("ação anterior", d["avisos"][0])
        st, d = self.enviar(corpo)  # mesmo arquivo: cai em repetido, mas o gancho roda e registra
        self.assertEqual((st, d["repetido"], d["registrado"], d["avisos"]), (200, True, True, []))
        recusar = os.path.join(self.dados, "recusar")
        open(recusar, "w").close()
        try:
            st, d = self.enviar(png(semente=b"recusado"))
        finally:
            os.remove(recusar)
        self.assertEqual((st, d["registrado"]), (201, False))
        self.assertIn("sem marca", d["avisos"][0])

    def test_gancho_recebe_destino_e_caminho_e_cache_some(self):
        modulos.montar(self.cfg, "marca")  # enche o cache
        st, d = self.enviar(png(semente=b"gancho"))
        self.assertEqual(st, 201)
        with open(os.path.join(self.dados, "ganchos.log")) as f:
            linhas = [json.loads(x) for x in f]
        self.assertIn(["envio.recebido", {"destino": "fotos", "caminho": d["caminho"]}, True], linhas)  # com gravar_dono
        _c, tela = modulos.montar(self.cfg, "marca")  # com cache: já mostra o novo total
        self.assertEqual(tela["abas"][0]["blocos"][0]["texto"], str(len(self.arquivos("fotos"))))
        self.assertNotIn("envio.recebido", envio.modulos.carregar(self.cfg, "marca").INFO.get("acoes", []))
        st, _r = test_http.TesteHTTP.post(self, "/api/modulos/marca/acao", {"acao": "envio.recebido", "dados": {}})
        self.assertEqual(st, 400)  # o gancho não é um comando que a tela possa forjar

    # ---- tamanho
    def test_acima_do_teto_413_sem_ler_o_corpo(self):
        for destino, tamanho in (("logo", 100001), ("enorme", envio.TETO + 1)):  # max_bytes; teto global (pede 100 MB)
            st, seg = self.cru(["Content-Length: %d" % tamanho], b"\x89PNG", destino=destino)
            self.assertEqual(st, 413)
            self.assertLess(seg, 5)  # não esperou os bytes que nunca vieram
        self.assertEqual(envio.declaracao(envio.modulos.carregar(self.cfg, "marca"), "enorme")["max_bytes"],
                         envio.TETO)

    def test_sem_tamanho_411_e_corpo_curto_400(self):
        self.assertEqual(self.cru([], b"")[0], 411)
        self.assertEqual(self.cru(["Transfer-Encoding: chunked"], b"0\r\n\r\n")[0], 411)
        self.assertEqual(self.cru(["Content-Length: 500"], png(), fechar_escrita=True)[0], 400)
        self.assertEqual(self.cru(["Content-Length: -3"], b"")[0], 400)

    # ---- tipo
    def test_tipo_errado_415(self):
        self.assertEqual(self.enviar(JPEG, destino="logo")[0], 415)  # JPEG de verdade, chave só png
        self.assertEqual(self.enviar(b"<svg xmlns='http://www.w3.org/2000/svg'/>")[0], 415)
        self.assertEqual(self.enviar(b"GIF89a" + b"\x00" * 30, **{"Content-Type": "image/gif"})[0], 415)

    def test_bytes_que_mentem_415_e_nada_gravado(self):
        antes = self.arquivos("fotos")
        for corpo in (b"\x89PNG\r\n\x1a\n<html>oi</html>" + b" " * 40, png(fim=b"<script>"), b"<html>" * 10):
            self.assertEqual(self.enviar(corpo, **{"Content-Type": "image/png"})[0], 415)
        self.assertEqual(antes, self.arquivos("fotos"))

    def test_bomba_de_dimensao_415(self):
        self.assertEqual(self.enviar(png(20000, 20000))[0], 415)
        self.assertEqual(self.enviar(png(8000, 8000))[0], 415)  # 64 milhões de pixels

    # ---- defesas de origem
    def test_sem_token_ou_cross_site_403_e_nada_gravado(self):
        antes = self.arquivos("fotos")
        corpo = png(semente=b"atacante")
        for troca in ({"X-Painel-Token": None}, {"X-Painel-Token": "x"}, {"Sec-Fetch-Site": "cross-site"},
                      {"Origin": "http://evil.example"}, {"Origin": None}):
            self.assertEqual(self.enviar(corpo, **troca)[0], 403, troca)
        st, _c, _d = self.pedir("POST", "/api/modulos/marca/envio?destino=fotos", corpo,
                                dict(self.cab_post(), Host="evil.example"))
        self.assertEqual(st, 421)
        self.assertEqual(antes, self.arquivos("fotos"))

    # ---- declaração e caminho
    def test_modulo_sem_declaracao_ou_chave_desconhecida_404(self):
        self.assertEqual(self.enviar(png(), mid="sem")[0], 404)
        self.assertEqual(self.enviar(png(), mid="nao-existe")[0], 404)
        self.assertEqual(self.enviar(png(), destino="outra")[0], 404)
        self.assertEqual(self.enviar(png(), destino="")[0], 404)
        self.assertEqual(self.enviar(png(), mid="ruim", destino="a")[0], 500)  # pasta da declaração sai de dados

    def test_travessia_na_chave_404(self):
        for chave in ("../fotos", "%2e%2e", "..%2ffotos", "fotos%00", "FOTOS", "fotos/x", "%2fetc"):
            self.assertEqual(self.enviar(png(), destino=chave)[0], 404, chave)

    def test_atalho_no_destino_recusado(self):
        if not self.tem_atalho:
            self.skipTest("sem permissão de symlink")
        self.assertEqual(self.enviar(png(semente=b"fuga"), destino="fora")[0], 409)
        self.assertEqual(os.listdir(self.fora), [])

    def test_limite_de_arquivos(self):
        a, b, c = (png(semente=s) for s in (b"l1", b"l2", b"l3"))
        self.assertEqual((self.enviar(a, destino="logo")[0], self.enviar(b, destino="logo")[0]), (201, 201))
        st, d = self.enviar(c, destino="logo")
        self.assertEqual(st, 409, d)
        self.assertEqual(self.enviar(a, destino="logo")[0], 200)  # repetir um que já está não conta
        self.assertEqual(len(self.arquivos("logo")), 2)

    def test_iguais_ao_mesmo_tempo_viram_um_arquivo(self):
        corpo, res = png(semente=b"corrida"), []
        ts = [threading.Thread(target=lambda: res.append(self.enviar(corpo)[0])) for _ in range(4)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(sorted(res)[-1], 201)
        self.assertTrue(all(s in (200, 201) for s in res), res)
        nome = envio.hashlib.sha256(corpo).hexdigest()[:16] + ".png"
        self.assertEqual(self.arquivos("fotos").count(nome), 1)


if __name__ == "__main__":
    unittest.main()
