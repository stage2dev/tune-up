"""Endurecimento da mídia no módulo (revisão de M4): arquivo() não transforma 403/500/3xx do serviço em "não
encontrado", recusa corpo cortado e não segue redirecionamento (o X-Vendas-Token nunca vai a outro destino); a aba não
oferece "Tentar de novo" para falha que se repetiria; falha da IA numa pronta tem o botão e ele chega ao serviço; a
prévia da lista guarda a legenda e o texto falado do áudio da própria IA."""
import sys

sys.dont_write_bytecode = True

import importlib.util  # noqa: E402
import os  # noqa: E402
import socket  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import conversas, recebimento  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from testes import test_audio_ia  # noqa: E402
from testes.test_aba_midia import Midias  # noqa: E402
from testes.test_midia import OGG, PDF, PNG  # noqa: E402

ABAS = os.path.join(os.path.dirname(AQUI), "painel", "modulos", "vendas")


def carregar(nome, caminho):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


midia_blocos = carregar("vendas_midia_blocos_teste", os.path.join(ABAS, "abas", "midia_blocos.py"))
arquivo = carregar("vendas_arquivo_teste", os.path.join(ABAS, "arquivo.py"))


class Falso(BaseHTTPRequestHandler):
    modo = "ok"
    pedidos = []

    def log_message(self, *_):
        pass

    def do_GET(self):
        type(self).pedidos.append((self.server.server_address[1], self.path, self.headers.get("X-Vendas-Token")))
        if type(self).modo == "cortado":
            self.send_response(200)
            self.send_header("Content-Type", "audio/ogg")
            self.send_header("Content-Length", "100")
            self.end_headers()
            self.wfile.write(b"OggS" + b"\x00" * 6)   # 10 de 100 bytes e fecha
            self.close_connection = True
            return
        if type(self).modo == "lento":
            time.sleep(1.0)
        if type(self).modo == "redireciona":
            self.send_response(302)
            self.send_header("Location", "http://127.0.0.1:%d/roubar" % type(self).outra)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "audio/ogg")
        self.send_header("Content-Length", str(len(OGG)))
        self.end_headers()
        self.wfile.write(OGG)


def servidor(teste):
    s = ThreadingHTTPServer(("127.0.0.1", 0), Falso)
    threading.Thread(target=s.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
    teste.addCleanup(s.server_close)
    teste.addCleanup(s.shutdown)
    return s.server_address[1]


class TesteArquivoDoServico(Midias):
    def setUp(self):
        super().setUp()
        Falso.pedidos, Falso.modo = [], "ok"
        self.porta = servidor(self)
        Falso.outra = servidor(self)
        cli = carregar("vendas_cliente_teste", os.path.join(ABAS, "cliente.py"))
        p = mock.patch.object(cli, "_acesso", return_value=("http://127.0.0.1:%d" % self.porta,
                                                            {"X-Vendas-Token": "tok-falso"}))
        p.start()
        self.addCleanup(p.stop)
        self.cli = cli

    def test_corpo_cortado_e_recusado(self):
        self.assertEqual(self.cli.baixar(self.ctx, "/midia/1", 1000)[2], OGG)   # inteiro passa
        Falso.modo = "cortado"
        with self.assertRaises(self.cli.Cortado):
            self.cli.baixar(self.ctx, "/midia/1", 1000)
        with self.assertRaises(Exception) as ctx:   # pelo arquivo(): erro (500 no painel), nunca 404 calado
            arquivo.ler(self.ctx, self.cli, "m:1")
        self.assertNotIsInstance(ctx.exception, FileNotFoundError)

    def test_redirecionamento_nao_e_seguido_e_o_token_nao_sai(self):
        Falso.modo = "redireciona"
        self.assertEqual(self.cli.baixar(self.ctx, "/midia/1", 1000)[0], 302)
        self.assertEqual(self.cli.pedir("GET", "http://127.0.0.1:%d/x" % self.porta, {"X-Vendas-Token": "t"})[0], 302)
        self.assertEqual([p for p in Falso.pedidos if p[0] == Falso.outra], [])
        with self.assertRaises(Exception) as ctx:
            arquivo.ler(self.ctx, self.cli, "m:1")
        self.assertNotIsInstance(ctx.exception, FileNotFoundError)

    def test_403_e_500_do_servico_nao_viram_nao_encontrado(self):
        for codigo in (403, 500):
            falso = types.SimpleNamespace(Recusa=self.cli.Recusa, baixar=lambda *a, c=codigo: (c, {}, b""))
            with self.assertRaises(Exception, msg=codigo) as ctx:
                arquivo.ler(self.ctx, falso, "m:1")
            self.assertNotIsInstance(ctx.exception, FileNotFoundError)
        falso = types.SimpleNamespace(Recusa=self.cli.Recusa, baixar=lambda *a: (404, {}, b""))
        with self.assertRaises(FileNotFoundError):
            arquivo.ler(self.ctx, falso, "m:1")

    def test_so_ref_desconhecida_ou_404_viram_nao_encontrado(self):
        for codigo in (500, 502, 503, 504):   # 5xx do serviço
            falso = types.SimpleNamespace(Recusa=self.cli.Recusa, baixar=lambda *a, c=codigo: (c, {}, b""))
            with self.assertRaises(Exception, msg=codigo) as ctx:
                arquivo.ler(self.ctx, falso, "m:1")
            self.assertNotIsInstance(ctx.exception, FileNotFoundError)
        Falso.modo = "lento"   # tempo esgotado no serviço
        with mock.patch.object(self.cli, "TEMPO_REDE_S", 0.2), self.assertRaises(Exception) as ctx:
            arquivo.ler(self.ctx, self.cli, "m:1")
        self.assertNotIsInstance(ctx.exception, FileNotFoundError)
        s = socket.socket()   # serviço parado: porta sem ninguém ouvindo
        s.bind(("127.0.0.1", 0))
        fechada = s.getsockname()[1]
        s.close()
        with mock.patch.object(self.cli, "_acesso", return_value=("http://127.0.0.1:%d" % fechada, {})), \
                self.assertRaises(Exception) as ctx:
            arquivo.ler(self.ctx, self.cli, "m:1")
        self.assertNotIsInstance(ctx.exception, FileNotFoundError)
        recusa = types.SimpleNamespace(Recusa=self.cli.Recusa, baixar=mock.Mock(side_effect=self.cli.Recusa("parado")))
        with self.assertRaises(self.cli.Recusa):   # batimento velho / outro projeto: Recusa antes do pedido
            arquivo.ler(self.ctx, recusa, "m:1")
        for ref in ("m:x", "1", None):   # ref desconhecida: não encontrado, sem pedir ao serviço
            with self.assertRaises(FileNotFoundError):
                arquivo.ler(self.ctx, recusa, ref)
        self.assertEqual(recusa.baixar.call_count, 1)


class TesteBotaoDaAba(Midias):
    def blocos(self):
        self.abrir_conversa()
        _, msgs = self.mensagens()
        return {m["midia"]["ref"]: m["midia"] for m in msgs if "midia" in m}

    def test_falha_que_se_repetiria_nao_tem_tentar_de_novo(self):
        ids = {}
        for motivo in ("sem_segredo", "grande_demais", "tipo_recusado", "expirada", "indisponivel"):
            ids[motivo], _ = self.chegou("audio", None)
            self.estado(ids[motivo], "falhou", motivo)
        por_ref = self.blocos()
        for motivo, mid in ids.items():
            tem = "acao" in por_ref["m:%d" % mid]
            self.assertEqual(tem, motivo == "indisponivel", motivo)

    def test_falha_da_ia_numa_pronta_tem_o_botao_e_chega_ao_servico(self):
        mid, _ = self.chegou("audio", OGG)
        self.con.execute("UPDATE midias SET falha_ia = 'transcricao_falhou' WHERE id = ?", (mid,))
        b = self.blocos()["m:%d" % mid]
        self.assertEqual(b["acao"], {"acao": "midia_baixar_de_novo", "dados": {"midia_id": mid}})
        self.assertIn("IA", b["aviso"])
        chamados = []
        recebimento.registrar_gancho(lambda c, m: chamados.append((c, m)))
        self.addCleanup(recebimento.registrar_gancho, None)
        r = self.mod.agir(self.ctx, "midia_baixar_de_novo", {"midia_id": mid}, base=self.base)
        self.assertTrue(r["ok"], r)
        self.assertIn("IA vai tentar", r["mensagem"])
        self.assertIsNone(self.con.execute("SELECT falha_ia FROM midias WHERE id = ?", (mid,)).fetchone()[0])
        self.assertEqual(len(chamados), 1)   # a IA tem a vez de novo
        self.assertFalse(self.mod.agir(self.ctx, "midia_baixar_de_novo", {"midia_id": mid}, base=self.base)["ok"])


class TestePreviaDaLista(Midias):
    def detalhe(self):
        caixa, _ = self.mensagens()
        return caixa["conversas"][0]["detalhe"]

    def test_legenda_da_foto_e_do_documento_fica(self):
        _, m1 = self.chegou("imagem", PNG)
        self.con.execute("UPDATE mensagens SET texto = 'olha o modelo' WHERE id = ?", (m1,))
        self.assertEqual(self.detalhe(), "Foto: olha o modelo")
        _, m2 = self.chegou("documento", PDF, nome="proposta.pdf")
        self.assertEqual(self.detalhe(), "Documento: proposta.pdf")
        self.con.execute("UPDATE mensagens SET texto = 'segue a proposta' WHERE id = ?", (m2,))
        self.assertEqual(self.detalhe(), "Documento: proposta.pdf - segue a proposta")


class TesteFalaDaIANaPrevia(test_audio_ia.Base):
    def test_audio_da_ia_mostra_o_texto_falado(self):
        self.chegar("a1")
        self.chegar("t1", "e o preço?")
        self.responder_em_audio()
        self.assertEqual(self.rodar("t1")["estado"], "enviado")
        ident = [e for e in self.c.entregues if e["tipo"] == "audio"][0]["id_externo"]
        eco = {"event": "send.message", "instance": test_audio_ia.INST, "data": {
            "key": {"remoteJid": test_audio_ia.LEAD + "@s.whatsapp.net", "fromMe": True, "id": ident},
            "message": {"audioMessage": {"seconds": 3}}, "messageTimestamp": int(time.time())}}
        recebimento.gravar(self.con, evolution.traduzir(eco))
        item = conversas.listar(self.con, {})["conversas"][0]
        self.assertEqual(item["ultima_tipo"], "audio")
        self.assertEqual(item["ultima_transcricao"], "Oi! O curso custa R$ 100. Veja aqui:")
        self.assertIn("O curso custa", midia_blocos.previa(item))


if __name__ == "__main__":
    unittest.main()
