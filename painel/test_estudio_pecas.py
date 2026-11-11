"""Abas do módulo estudio (plugin tune-up-studio): selo do servidor, fila, aprovação e recusa de peças.

O módulo real entra pela ponte de test_estudio_marca. A lista de execuções é a do lançador de verdade
num caso (App); nos outros, uma lista fixa no lugar de ctx["execucoes"]. Nada chama o claude.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import struct  # noqa: E402
import subprocess  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
import zlib  # noqa: E402

import midia  # noqa: E402
import modulos  # noqa: E402
import painel  # noqa: E402
from test_dono import Base  # noqa: E402
from test_estudio_marca import PONTE  # noqa: E402
from test_modulos import escrever  # noqa: E402

TID, TID_V = "a1b2c3d4e5f6", "0123456789ab"
HTML = "<html><body><div class='t'>Oferta</div><style>.t{color:#123456}</style></body></html>\n"


def png(caminho, largura, altura):
    def pedaco(tipo, corpo):
        return struct.pack(">I", len(corpo)) + tipo + corpo + struct.pack(">I", zlib.crc32(tipo + corpo))
    bruto = (b"\x00" + b"\x10\x20\x30" * largura) * altura
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + pedaco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0))
                + pedaco(b"IDAT", zlib.compress(bruto)) + pedaco(b"IEND", b""))


class BasePecas(Base):
    def setUp(self):
        super().setUp()
        escrever(os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos", "estudio", "modulo.py"), PONTE)
        self.cfg["raiz"] = self.tmp
        modulos.esquecer()
        self.dados = modulos.contexto(self.cfg)["dados"]
        self.lista = []
        self.cfg["_execucoes"] = lambda: list(self.lista)

    def execucao(self, tid, acao="estudio.post", estado="terminou", **params):
        self.lista.append({"id": "e" + tid[:7], "acao": acao, "titulo": "Peça", "iniciada_em": "2026-11-11T10:00",
                           "trabalho": tid, "estado": estado, "params": params or {"formato": "post 4:5"}})
        return os.path.join(self.dados, "trabalhos", tid)

    def post(self, tid=TID, largura=1080, altura=1350, **kw):
        p = self.execucao(tid, **kw)
        escrever(os.path.join(p, "q1", "fonte", "index.html"), HTML)
        escrever(os.path.join(p, "copy.md"), "Oferta da semana\n\nLegenda do post.")
        antes = time.time() - 60
        os.utime(os.path.join(p, "q1", "fonte", "index.html"), (antes, antes))
        png(os.path.join(p, "q1", "snap", "frame-00-at-0s.png"), largura, altura)
        escrever(os.path.join(p, "final.json"), json.dumps({"ok": True, "linha": "PRONTO: 1 de 1 quadros verdes"}))
        return p

    def abas(self):
        cod, corpo = modulos.montar(self.cfg, "estudio", usar_cache=False)
        self.assertEqual(cod, 200, corpo)
        return {a["id"]: json.dumps(a, ensure_ascii=False) for a in corpo["abas"]}

    def agir(self, acao, tid=TID):
        return modulos.agir(self.cfg, "estudio", acao, {"trabalho": tid, "confirmar": True})


class TesteSelo(BasePecas):
    def test_post_verde_e_verde_da_sessao_nao_sobe_o_selo(self):
        self.post()
        self.post(TID_V, largura=1080, altura=1080)  # PNG 1:1 num post 4:5: vermelho, mesmo com a sessão dizendo PRONTO
        escrever(os.path.join(self.dados, "trabalhos", TID_V, "q1", "qa.json"), json.dumps({"ok": True, "checks": []}))
        abas = self.abas()
        self.assertIn("Pronto para aprovar", abas["galeria"])
        self.assertIn("imagem no tamanho errado", abas["galeria"])  # o 1:1 ficou vermelho pelo tamanho
        self.assertIn("peca.aprovar", abas["aprovacao"])
        self.assertIn(TID, abas["aprovacao"])
        self.assertNotIn(TID_V, abas["aprovacao"])
        self.assertIn("trabalhos/%s/q1/snap/frame-00-at-0s.png" % TID, abas["galeria"])

    def test_vermelho_ou_falta_da_conferencia_da_sessao_baixa_o_selo(self):
        p = self.post()
        escrever(os.path.join(p, "final.json"), json.dumps(
            {"ok": False, "linha": "PRECISA DO SEU OLHO: 0 de 1 verdes, q1: snapshot, hyperframes_check"}))
        self.assertNotIn(TID, self.abas()["aprovacao"])
        self.assertIs(self.agir("peca.aprovar")[1]["resultado"]["feito"], False)
        os.remove(os.path.join(p, "final.json"))  # sessão cortada antes da conferência final
        self.assertIn("a conferência do Claude não passou", self.abas()["galeria"])
        self.assertIs(self.agir("peca.aprovar")[1]["resultado"]["feito"], False)
        self.assertFalse(os.path.exists(os.path.join(self.dados, "aprovados", TID)))

    def test_quadros_que_nao_batem_com_o_formato_ou_sem_legenda_ficam_vermelhos(self):
        self.post(formato="carrossel 4:5", quadros="5")  # carrossel de 1 quadro só
        p = self.post(TID_V)
        os.remove(os.path.join(p, "copy.md"))
        abas = self.abas()
        self.assertNotIn("Pronto para aprovar", abas["galeria"])
        self.assertIn("quadros", abas["galeria"])
        self.assertIn("legenda", abas["galeria"])
        for tid in (TID, TID_V):
            self.assertIs(self.agir("peca.aprovar", tid)[1]["resultado"]["feito"], False, tid)

    @unittest.skipIf(not hasattr(os, "symlink") or os.name == "nt", "atalho")
    def test_pasta_de_quadro_que_e_atalho_fica_vermelha(self):
        p = self.post()
        fora = os.path.join(self.tmp, "fora")
        shutil.move(os.path.join(p, "q1"), fora)
        os.symlink(fora, os.path.join(p, "q1"))
        self.assertIn("pasta da peça com atalho", self.abas()["galeria"])
        self.assertIs(self.agir("peca.aprovar")[1]["resultado"]["feito"], False)

    def test_gsap_url_e_layout_allow_na_fonte_ficam_vermelhos(self):
        for i, ruim in enumerate(("<script src='gsap.min.js'></script>", "<img src='https://x.example/a.png'>",
                                  "<div data-layout-allow-overflow></div>")):
            p = self.post(tid="%012x" % (i + 1))
            escrever(os.path.join(p, "q1", "fonte", "index.html"), HTML + ruim)
            antes = time.time() - 60
            os.utime(os.path.join(p, "q1", "fonte", "index.html"), (antes, antes))
        texto = self.abas()["galeria"]
        self.assertNotIn("Pronto para aprovar", texto)
        for nome in ("usa animação proibida", "busca coisas na internet", "texto pode sair do quadro"):
            self.assertIn(nome, texto)
        for tecnico in ("no_gsap", "network_lint", "layout_allow_count", "PRONTO:", "PRECISA DO SEU OLHO:"):
            self.assertNotIn(tecnico, texto)  # a tela fala a língua do dono

    def test_fonte_mais_nova_que_o_png_e_atalho_ficam_vermelhos(self):
        p = self.post()
        os.utime(os.path.join(p, "q1", "fonte", "index.html"), None)
        os.utime(os.path.join(p, "q1", "snap", "frame-00-at-0s.png"), (time.time() - 120,) * 2)
        self.assertIn("o desenho mudou depois da imagem", self.abas()["galeria"])
        if hasattr(os, "symlink") and os.name != "nt":
            os.symlink("/etc/hosts", os.path.join(p, "q1", "fonte", "x.html"))
            self.assertIn("arquivos do desenho com problema", self.abas()["galeria"])  # a fonte com atalho não é lida

    def test_fila_mostra_estado_em_palavras(self):
        p = self.post(estado="precisa_de_voce")
        escrever(os.path.join(p, "final.json"), json.dumps({"linha": "PRECISA DO SEU OLHO: 0 de 1 verdes"}))
        self.execucao(TID_V, estado="rodando")
        fila = self.abas()["fila"]
        self.assertIn("Precisa do seu olho", fila)
        self.assertIn("fazendo agora", fila)
        self.assertNotIn("travad", fila)


class TesteAprovar(BasePecas):
    def test_cartao_mostra_so_a_secao_legenda_do_copy(self):
        p = self.post()
        escrever(os.path.join(p, "copy.md"), "# Copy — post 4:5\n\n## Quadro 1\n- Título (32/40): X\n\n"
                 "## Legenda (17/125)\nPão saindo às 7h.\n\n## Chamada para ação\nReserve")
        cartao = [b for b in json.loads(self.abas()["aprovacao"])["blocos"] if b["tipo"] == "formulario"][0]
        self.assertEqual(cartao["descricao"], "Legenda que vai junto:\n\nPão saindo às 7h.")

    def test_aprovar_grava_manifesto_com_sha_do_servidor_e_segunda_vez_409(self):
        p = self.post()
        cartao = [b for b in json.loads(self.abas()["aprovacao"])["blocos"] if b["tipo"] == "formulario"]
        self.assertEqual(len(cartao), 1)  # Aprovar e Recusar no mesmo cartão, com a legenda antes dos botões
        self.assertEqual((cartao[0]["acao"], cartao[0]["secundario"]["acao"]), ("peca.aprovar", "peca.recusar"))
        self.assertIn("Legenda do post.", cartao[0]["descricao"])
        cod, corpo = self.agir("peca.aprovar")
        self.assertEqual((cod, corpo["resultado"]["feito"]), (200, True), corpo)
        destino = os.path.join(self.dados, "aprovados", TID)
        with open(os.path.join(destino, "manifesto.json"), encoding="utf-8") as f:
            m = json.load(f)
        with open(os.path.join(p, "q1", "snap", "frame-00-at-0s.png"), "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        self.assertEqual([(a["nome"], a["sha256"]) for a in m["arquivos"]], [("q1.png", sha)])
        with open(os.path.join(destino, "q1.png"), "rb") as f:
            self.assertEqual(hashlib.sha256(f.read()).hexdigest(), sha)
        self.assertEqual((m["formato"], m["trabalho"]), ("post 4:5", TID))
        self.assertIn("Legenda do post.", m["legenda"])
        self.assertEqual([n for n in os.listdir(os.path.join(self.dados, "aprovados")) if n.startswith(".")], [])
        cod, corpo = self.agir("peca.aprovar")
        self.assertEqual(cod, 409, corpo)
        self.assertEqual(self.agir("peca.recusar")[0], 409)
        self.assertIn("Aprovada.", self.abas()["galeria"])
        r = midia.abrir(self.cfg, "estudio", "aprovados/%s/q1.png" % TID, None)  # a rota serve o aprovado
        self.assertIsInstance(r, midia.Aberto)
        r.fechar()

    def test_nao_aprova_parada_pelo_teto(self):
        self.post(estado="parada")
        self.assertNotIn(TID, self.abas()["aprovacao"])
        self.assertIs(self.agir("peca.aprovar")[1]["resultado"]["feito"], False)
        self.assertFalse(os.path.exists(os.path.join(self.dados, "aprovados", TID)))

    def test_nao_aprova_vermelho_rodando_ou_recusado(self):
        self.post(largura=10, altura=10)
        self.assertIs(self.agir("peca.aprovar")[1]["resultado"]["feito"], False)
        self.post(TID_V, estado="rodando")
        self.assertIn("trabalhando", self.agir("peca.aprovar", TID_V)[1]["resultado"]["mensagem"])
        self.lista[-1]["estado"] = "terminou"
        self.assertIs(self.agir("peca.recusar", TID_V)[1]["resultado"]["feito"], True)
        self.assertIs(self.agir("peca.aprovar", TID_V)[1]["resultado"]["feito"], False)
        self.assertFalse(os.path.exists(os.path.join(self.dados, "aprovados", TID_V)))
        self.assertIs(self.agir("peca.aprovar", "../" + TID)[1]["resultado"]["feito"], False)

    def test_peca_que_muda_durante_a_copia_nao_aprova_e_nao_deixa_resto(self):
        p = self.post()
        self.abas()  # carrega o módulo real (e o pecas.py dele)
        pecas = sys.modules["pecas"]
        original = pecas._copiar

        def copiar_e_mexer(origem, destino):
            r = original(origem, destino)
            escrever(os.path.join(p, "q1", "fonte", "extra.css"), "body{}")
            return r
        pecas._copiar = copiar_e_mexer
        try:
            cod, corpo = self.agir("peca.aprovar")
        finally:
            pecas._copiar = original
        self.assertEqual((cod, corpo["resultado"]["feito"]), (200, False), corpo)
        self.assertEqual(os.listdir(os.path.join(self.dados, "aprovados")), [])

    def test_midia_serve_previa_do_trabalho(self):
        self.post()
        r = midia.abrir(self.cfg, "estudio", "trabalhos/%s/q1/snap/frame-00-at-0s.png" % TID, None)
        self.assertIsInstance(r, midia.Aberto)
        r.fechar()
        for ruim in ("q1/snap/frame-00-at-0s.png", "outros/%s/x.png" % TID, "trabalhos/.x/a.png"):
            self.assertEqual(midia.abrir(self.cfg, "estudio", ruim, None)[0], 404, ruim)

    def test_app_liga_a_lista_do_lancador(self):
        del self.cfg["_execucoes"]
        app = painel.App(self.cfg, rodar_externos=False)
        self.assertEqual(self.cfg["_execucoes"], app.lancador.execucoes)
        self.assertIn("Nada na fila", self.abas()["fila"])


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg")
class TesteVideo(BasePecas):
    def video(self, tid):
        p = self.execucao(tid, acao="estudio.video-motion", duracao="10")
        escrever(os.path.join(p, "fonte", "index.html"), HTML)
        antes = time.time() - 60
        os.utime(os.path.join(p, "fonte", "index.html"), (antes, antes))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x336699:s=1080x1920:r=30:d=10",
                        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                        os.path.join(p, "video.mp4")], check=True, stdout=subprocess.DEVNULL)
        escrever(os.path.join(p, "qa.json"), json.dumps({"ok": True, "linha": "PRONTO: video verde (hyperframes)"}))
        return p

    def test_mp4_verde_e_truncado_fica_vermelho(self):
        self.video(TID)
        p = self.video(TID_V)
        with open(os.path.join(p, "video.mp4"), "r+b") as f:
            f.truncate(os.path.getsize(os.path.join(p, "video.mp4")) // 2)
        galeria = self.abas()["galeria"]
        self.assertEqual(galeria.count("Pronto para aprovar"), 1, galeria)
        self.assertIn("Precisa do seu olho", galeria)

    def test_qa_da_sessao_vermelho_baixa_o_selo_do_video(self):
        p = self.video(TID)
        escrever(os.path.join(p, "qa.json"), json.dumps({"ok": False, "linha": "PRECISA DO SEU OLHO: fonts"}))
        self.assertNotIn("Pronto para aprovar", self.abas()["galeria"])


if __name__ == "__main__":
    unittest.main()
