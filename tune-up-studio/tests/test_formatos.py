"""Schema test for formatos.json: every row has source, date and status."""
import json
import os
import re
import unittest

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TIPOS = {"tamanho", "texto", "zona_segura"}
PLATAFORMAS = {"instagram", "facebook", "linkedin", "tiktok", "youtube-shorts",
               "x", "google-ads", "meta-ads"}


class FormatosTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(STUDIO, "formatos.json"), encoding="utf-8") as f:
            self.dados = json.load(f)

    def test_versao_e_linhas(self):
        self.assertEqual(self.dados["versao"], 1)
        self.assertTrue(self.dados["formatos"])

    def test_cada_linha(self):
        ids = set()
        for r in self.dados["formatos"]:
            rid = r.get("id")
            self.assertTrue(rid and rid not in ids, rid)
            ids.add(rid)
            self.assertIn(r["plataforma"], PLATAFORMAS, rid)
            self.assertIn(r["tipo"], TIPOS, rid)
            self.assertTrue(r["formato"], rid)
            self.assertIsInstance(r["valores"], dict, rid)
            self.assertTrue(r["valores"], rid)
            self.assertTrue(str(r["fonte"]).strip(), rid)
            self.assertRegex(r["verificado_em"], r"^\d{4}-\d{2}-\d{2}$", rid)
            self.assertIn(r["status"], ("oficial", "aproximado"), rid)
            if r["status"] == "oficial":
                self.assertTrue(re.match(r"^https://", r["url"] or ""), rid)
            elif r["url"] is not None:
                self.assertTrue(r["url"].startswith("https://"), rid)

    def test_todas_as_plataformas_da_v1(self):
        usadas = {r["plataforma"] for r in self.dados["formatos"]}
        self.assertEqual(usadas, PLATAFORMAS)


if __name__ == "__main__":
    unittest.main()
