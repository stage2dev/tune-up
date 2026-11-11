"""Anúncio no módulo estudio: selo do servidor (peças no tamanho do plano, textos nos limites, planilha igual à do
script e toda pausada), aprovação com a planilha no manifesto e o download do .csv só de aprovados/.

Nada chama o claude nem uma API de anúncio.
"""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

import midia  # noqa: E402
from test_estudio_pecas import HTML, TID, BasePecas, png  # noqa: E402
from test_modulos import escrever  # noqa: E402

SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tune-up-studio", "scripts")
sys.path.insert(0, SCRIPTS)
import anuncio  # noqa: E402

sys.path.remove(SCRIPTS)
URL = "https://exemplo.test/pao"
TEXTOS = {"plataforma": "google", "url": URL, "titulos": ["Pão de fermentação natural", "Fornadas pequenas",
                                                          "Reserve pelo WhatsApp"],
          "descricoes": ["Pão assado de manhã cedo.", "Reserve o pão de amanhã pelo WhatsApp."], "caminhos": ["pao"]}
LIMPA = "<html><body><div class='t'></div><style>.t{color:#123456}</style></body></html>\n"  # Google: sem texto
SEGURA = ("<html><body><div id='safezone'>Oferta</div><style>#safezone{position:absolute;top:14%;bottom:20%;"
          "left:0;right:0;overflow:hidden}</style></body></html>\n")  # 9:16: texto só na zona segura


def desenho(plataforma, peca):
    return LIMPA if plataforma == "google" else SEGURA if peca["altura"] * 9 == peca["largura"] * 16 else HTML


class TesteAnuncio(BasePecas):
    def anuncio(self, tid=TID, textos=None, plataforma="google", url=URL, kw_html=None, **kw):
        kw_html = kw_html or {}
        p = self.execucao(tid, acao="estudio.anuncio", plataforma=plataforma, url=url, briefing="b", **kw)
        antes = time.time() - 60
        for peca in anuncio.plano(plataforma)["pecas"]:
            escrever(os.path.join(p, peca["id"], "fonte", "index.html"), kw_html.get(peca["id"], desenho(plataforma, peca)))
            os.utime(os.path.join(p, peca["id"], "fonte", "index.html"), (antes, antes))
            png(os.path.join(p, peca["id"], "snap", "frame-00-at-0s.png"), peca["largura"], peca["altura"])
        escrever(os.path.join(p, "textos.json"), textos if isinstance(textos, str) else
                 json.dumps(textos or TEXTOS, ensure_ascii=False))
        with contextlib.redirect_stdout(io.StringIO()):
            anuncio.exportar(p, plataforma)
        escrever(os.path.join(p, "final.json"), json.dumps({"ok": True, "linha": "PRONTO: 2 de 2 pecas verdes"}))
        return p

    def test_anuncio_verde_mostra_textos_na_aprovacao(self):
        self.anuncio()
        abas = self.abas()
        self.assertIn("Anúncio Google", abas["fila"])
        self.assertIn("Pronto para aprovar", abas["fila"])
        self.assertIn("Fornadas pequenas", abas["aprovacao"])
        self.assertIn("Reserve o pão de amanhã pelo WhatsApp.", abas["aprovacao"])
        self.assertIn(URL, abas["aprovacao"])
        self.assertIn("Nada é publicado", abas["aprovacao"])
        self.assertIn("trabalhos/%s/a1/snap/frame-00-at-0s.png" % TID, abas["aprovacao"])
        self.assertIn("peça 1200x628", abas["aprovacao"])

    def test_planilha_mexida_a_mao_ou_ativa_fica_vermelha(self):
        p = self.anuncio()
        caminho = os.path.join(p, "export", "google-ads-editor.csv")
        with open(caminho, encoding="utf-8", newline="") as f:
            texto = f.read()
        with open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(texto.replace(",Paused,", ",Enabled,"))
        self.assertIn("a planilha não é a que o estúdio monta", self.abas()["fila"])
        os.remove(caminho)
        self.assertIn("a planilha não é a que o estúdio monta", self.abas()["fila"])

    def test_textos_fora_do_limite_url_trocada_e_tamanho_errado_ficam_vermelhos(self):
        self.anuncio(textos=dict(TEXTOS, titulos=TEXTOS["titulos"] + ["x" * 31]))
        self.assertIn("títulos ou descrições fora dos limites", self.abas()["fila"])
        self.lista.clear()
        self.anuncio("0123456789ab", textos=dict(TEXTOS, url="https://outro.test/"))
        self.assertIn("o endereço não é o que você pediu", self.abas()["fila"])
        self.lista.clear()
        p = self.anuncio("bbbbbbbbbbbb")
        png(os.path.join(p, "a2", "snap", "frame-00-at-0s.png"), 1080, 1350)
        self.assertIn("imagem no tamanho errado", self.abas()["fila"])

    def test_aprovar_copia_planilha_com_sha_no_manifesto_e_link_de_download(self):
        self.anuncio()
        cod, corpo = self.agir("peca.aprovar")
        self.assertEqual((cod, corpo["resultado"]["feito"]), (200, True), corpo)
        pasta = os.path.join(self.dados, "aprovados", TID)
        with open(os.path.join(pasta, "manifesto.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual((m["plataforma"], m["publicado"], m["experimental"]), ("google-ads", False, False))
        self.assertEqual([a["nome"] for a in m["arquivos"]], ["a1_1200x628.png", "a2_1200x1200.png"])
        self.assertEqual([x["nome"] for x in m["export"]], ["google-ads-editor.csv"])
        with open(os.path.join(pasta, "google-ads-editor.csv"), "rb") as f:
            bruto = f.read()
        self.assertEqual(m["export"][0]["sha256"], hashlib.sha256(bruto).hexdigest())
        self.assertEqual(anuncio.ler_planilha(bruto.decode("utf-8"), "google"), [])
        self.assertEqual(m["textos"]["titulos"], TEXTOS["titulos"])
        aprovacao = self.abas()["aprovacao"]
        self.assertIn("aprovados/%s/google-ads-editor.csv" % TID, aprovacao)
        r = midia.abrir(self.cfg, "estudio", "aprovados/%s/google-ads-editor.csv" % TID, None)
        self.assertIsInstance(r, midia.Aberto)
        self.assertEqual(r.tipo, "text/csv; charset=utf-8")
        self.assertEqual(r.cabecalhos()["Content-Disposition"], 'attachment; filename="google-ads-editor.csv"')
        r.fechar()
        # a planilha da sessão (antes da aprovação) nunca sai pela rota
        self.assertEqual(midia.abrir(self.cfg, "estudio", "trabalhos/%s/export/google-ads-editor.csv" % TID, None)[0], 404)

    def test_meta_e_experimental_no_manifesto_e_na_tela(self):
        textos = {"plataforma": "meta", "url": URL, "titulos": ["Pão de fermentação"],
                  "textos_principais": ["Fornadas pequenas. Reserve pelo WhatsApp."]}
        self.anuncio(textos=textos, plataforma="meta")
        self.assertIn("EXPERIMENTAL", self.abas()["aprovacao"])
        cod, corpo = self.agir("peca.aprovar")
        self.assertTrue(corpo["resultado"]["feito"], corpo)
        with open(os.path.join(self.dados, "aprovados", TID, "manifesto.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual((m["plataforma"], m["experimental"]), ("meta-ads", True))
        self.assertEqual(m["export"][0]["nome"], "meta-experimental.csv")

    def test_google_com_texto_e_9x16_fora_da_zona_segura_ficam_vermelhos(self):
        self.anuncio(kw_html={"a2": HTML})  # texto sobre a imagem: a Pesquisa do Google reprova
        self.assertIn("imagem do Google com texto ou logo", self.abas()["fila"])
        self.lista.clear()
        meta = {"plataforma": "meta", "url": URL, "titulos": ["Pão"], "textos_principais": ["Reserve já."]}
        self.anuncio("0123456789ab", textos=meta, plataforma="meta")
        self.assertIn("Pronto para aprovar", self.abas()["fila"])
        self.lista.clear()
        self.anuncio("bbbbbbbbbbbb", textos=meta, plataforma="meta", kw_html={"a2": HTML})
        self.assertIn("texto fora da zona segura do 9:16", self.abas()["fila"])

    def test_textos_json_fundo_demais_deixa_a_peca_vermelha_e_a_tela_de_pe(self):
        self.anuncio(textos="[" * 5000 + "]" * 5000)
        self.assertIn("títulos ou descrições fora dos limites", self.abas()["fila"])


if __name__ == "__main__":
    unittest.main()
