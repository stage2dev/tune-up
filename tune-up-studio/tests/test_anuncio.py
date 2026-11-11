"""scripts/anuncio.py: plan from formatos.json, text limits, and the import sheet read back from disk."""
import contextlib
import csv
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import anuncio  # noqa: E402

TID = "a1b2c3d4e5f6"
GOOGLE = {"plataforma": "google", "url": "https://exemplo.test/pao?origem=anuncio",
          "titulos": ["Pão de fermentação natural", "Fornadas pequenas", "Reserve pelo WhatsApp"],
          "descricoes": ["Pão assado de manhã cedo, em fornadas pequenas.", "Reserve o pão de amanhã pelo WhatsApp."],
          "caminhos": ["pao", "reserva"]}
META = {"plataforma": "meta", "url": "https://exemplo.test/",
        "titulos": ["Pão de fermentação natural", "Reserve o de amanhã"],
        "textos_principais": ["Fornadas pequenas, assadas de manhã cedo. Reserve pelo WhatsApp."]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.pasta = os.path.join(self.tmp, TID)
        os.makedirs(self.pasta)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def textos(self, d):
        with open(os.path.join(self.pasta, "textos.json"), "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)

    def ler(self, nome):
        with open(os.path.join(self.pasta, "export", nome), encoding="utf-8", newline="") as f:
            return list(csv.DictReader(io.StringIO(f.read())))


class Plano(unittest.TestCase):
    def test_sizes_and_limits_come_from_formatos(self):
        g = anuncio.plano("google")
        self.assertEqual([(p["razao"], p["largura"], p["altura"]) for p in g["pecas"]],
                         [("1.91:1", 1200, 628), ("1:1", 1200, 1200)])
        self.assertEqual(g["limites"]["titulos"], [3, 15, 30])
        self.assertEqual(g["limites"]["descricoes"], [2, 4, 90])
        m = anuncio.plano("meta")
        self.assertEqual([(p["largura"], p["altura"]) for p in m["pecas"]], [(1440, 1800), (1080, 1920)])
        self.assertEqual(m["limites"]["titulos"][2], 27)
        self.assertEqual(m["limites"]["textos_principais"][2], 125)
        self.assertIn("experimental", m["export"])
        with self.assertRaises(ValueError):
            anuncio.plano("tiktok")

    def test_count_is_nfc_and_wide_counts_two(self):
        self.assertEqual(anuncio.contar("pão"), 3)  # "pão" decomposed
        self.assertEqual(anuncio.contar("パン"), 4)


class Conferir(unittest.TestCase):
    def test_good_texts_pass(self):
        self.assertEqual(anuncio.conferir(GOOGLE, "google"), [])
        self.assertEqual(anuncio.conferir(META, "meta"), [])

    def test_over_limit_counts_fields_and_url_fail(self):
        casos = [
            (dict(GOOGLE, titulos=GOOGLE["titulos"][:2]), "titulos: 2 items"),
            (dict(GOOGLE, titulos=GOOGLE["titulos"] + ["x" * 31]), "titulos 4: 31 characters"),
            (dict(GOOGLE, descricoes=["d" * 91, "ok"]), "descricoes 1: 91 characters"),
            (dict(GOOGLE, url="http://exemplo.test/"), "url"),
            (dict(GOOGLE, url="https://exemplo.test/a b"), "url"),
            (dict(GOOGLE, titulos=GOOGLE["titulos"] + ["=HYPERLINK(1)"]), "starts with ="),
            (dict(GOOGLE, titulos=GOOGLE["titulos"] + ["Fornadas Pequenas"]), "repeated"),
            (dict(GOOGLE, caminhos=["a b"]), "no spaces"),
            (dict(GOOGLE, extra=1), "unknown fields"),
            (dict(GOOGLE, plataforma="meta"), "plataforma"),
            ({k: v for k, v in META.items() if k != "titulos"}, "titulos: missing"),
        ]
        for textos, esperado in casos:
            plataforma = "meta" if "textos_principais" in textos else "google"
            problemas = anuncio.conferir(textos, plataforma)
            self.assertTrue(any(esperado in p for p in problemas), (esperado, problemas))


class Exportar(Base):
    def test_google_sheet_read_back_has_columns_paused_and_limits(self):
        self.textos(GOOGLE)
        self.assertEqual(anuncio.exportar(self.pasta, "google"), (True, []))
        linhas = self.ler("google-ads-editor.csv")
        self.assertEqual(list(linhas[0].keys()), anuncio.GOOGLE_COLS)
        self.assertEqual(len(linhas), 3)  # campaign, ad group, ad
        self.assertTrue(all(x["Campaign Status"] == "Paused" for x in linhas))
        self.assertEqual([x["Ad Group Status"] for x in linhas[1:]], ["Paused", "Paused"])
        anuncio_ = linhas[2]
        self.assertEqual((anuncio_["Status"], anuncio_["Ad type"]), ("Paused", "Responsive search ad"))
        self.assertEqual([anuncio_["Headline %d" % i] for i in (1, 2, 3)], GOOGLE["titulos"])
        self.assertEqual(anuncio_["Final URL"], GOOGLE["url"])
        self.assertEqual(linhas[0]["Campaign"], "Estudio " + TID)
        for x in linhas:
            for k, v in x.items():
                if k.startswith("Headline"):
                    self.assertLessEqual(len(v), 30)
                if k.startswith("Description"):
                    self.assertLessEqual(len(v), 90)
        with open(os.path.join(self.pasta, "export", "google-ads-editor.csv"), encoding="utf-8", newline="") as f:
            self.assertEqual(anuncio.ler_planilha(f.read(), "google"), [])

    def test_meta_sheet_is_experimental_and_paused(self):
        self.textos(META)
        self.assertEqual(anuncio.exportar(self.pasta, "meta"), (True, []))
        linhas = self.ler("meta-experimental.csv")
        self.assertEqual(list(linhas[0].keys()), anuncio.META_COLS)
        self.assertEqual(len(linhas), 2)
        for x in linhas:
            self.assertEqual((x["Campaign Status"], x["Ad Set Run Status"], x["Ad Status"]), ("PAUSED",) * 3)
            self.assertEqual(x["Image File Name"], "a1_1440x1800.png")

    def test_bad_texts_write_no_sheet_and_remove_the_stale_one(self):
        self.textos(GOOGLE)
        anuncio.exportar(self.pasta, "google")
        self.textos(dict(GOOGLE, titulos=["x" * 40] * 3))
        ok, problemas = anuncio.exportar(self.pasta, "google")
        self.assertFalse(ok)
        self.assertTrue(problemas)
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "export", "google-ads-editor.csv")))

    def test_hand_edited_or_active_sheet_fails(self):
        self.textos(GOOGLE)
        anuncio.exportar(self.pasta, "google")
        caminho = os.path.join(self.pasta, "export", "google-ads-editor.csv")
        with open(caminho, encoding="utf-8", newline="") as f:
            texto = f.read()
        ativo = texto.replace(",Paused,", ",Enabled,")
        self.assertTrue(anuncio.ler_planilha(ativo, "google"))
        with open(caminho, "w", encoding="utf-8", newline="") as f:
            f.write(ativo)
        self.assertTrue(anuncio.conferir_export(self.pasta, "google", GOOGLE))

    def test_final_without_pieces_needs_your_eye(self):
        self.textos(GOOGLE)
        anuncio.exportar(self.pasta, "google")
        rep = anuncio.final(self.pasta, "google")
        self.assertFalse(rep["ok"])
        self.assertTrue(rep["linha"].startswith("PRECISA DO SEU OLHO: 0 de 2 verdes"))
        self.assertEqual((rep["textos"], rep["planilha"]), ([], []))

    def test_cli(self):
        self.textos(GOOGLE)
        out = os.path.join(self.pasta, "final.json")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(anuncio.main(["--exportar", self.pasta, "--plataforma", "google"]), 0)
            self.assertEqual(anuncio.main(["--final", self.pasta, "--plataforma", "google", "--out", out]), 1)
        with open(out, encoding="utf-8") as f:
            self.assertFalse(json.load(f)["ok"])


if __name__ == "__main__":
    unittest.main()
