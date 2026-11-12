"""scripts/qa_quadros.py: the automatic checks for the defects that kept coming back (round 6), each one green
and red. No Chrome, no network, no ffmpeg (the frames of `quadro_de_corte` are synthetic)."""
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
sys.path.insert(0, HERE)

import qa_css  # noqa: E402
import qa_quadros  # noqa: E402
from test_qa_vazio import png  # noqa: E402

RAPIDA = ("@keyframes tr_sobe { 0%, 34% { clip-path: inset(100% 0 0 0); } 46%, 54% { clip-path: inset(0 0 0 0); } "
          "66%, 100% { clip-path: inset(0 0 100% 0); } }")
LENTA = ("@keyframes tr_sobe { 0% { clip-path: inset(100% 0 0 0); } 45%, 55% { clip-path: inset(0 0 0 0); } "
         "100% { clip-path: inset(0 0 100% 0); } }")


def pagina(corte=1.875, quadros=RAPIDA, script="", extra="", css=""):
    return """<!doctype html><html><head><style>
#tr1 { animation: tr_sobe .44s linear 0s 1 both; } %s %s
</style></head><body><div id="root">
<p id="s1_titulo" class="clip" data-start="0" data-duration="%s">Chegou tarde?</p>
<p id="s2_titulo" class="clip" data-start="%s" data-duration="3">Fornada das 6h</p>
<p id="s2_apoio" class="clip" data-start="%s" data-duration="3">massa de 24 horas</p>
<div id="s2_barra" class="clip" data-start="%s" data-duration="3"></div>
<p id="s2_contato" class="clip" data-start="%s" data-duration="3">link na bio</p>
%s
<div id="tr1" class="clip" data-start="%s" data-duration="0.44"></div>
</div><script>%s</script></body></html>""" % (quadros, css, corte, corte, corte, corte, corte, extra, corte - 0.22,
                                               script)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def doc(self, html):
        with open(os.path.join(self.tmp, "index.html"), "w", encoding="utf-8") as f:
            f.write(html)
        doc = qa_css.ler_fonte(self.tmp)
        return doc, [e for e in doc["elementos"] if "clip" in e["classes"]]


class FolhaLimpa(Base):
    def folha(self, html):
        return qa_quadros.check_folha(*self.doc(html), 10)

    def test_corte_fora_da_grade_com_transicao_rapida_passa(self):
        self.assertTrue(self.folha(pagina())["ok"])

    def test_corte_na_grade_reprova(self):
        rep = self.folha(pagina(corte=1.5))
        self.assertFalse(rep["ok"])
        self.assertIn("tr1 aparece em 1.5 s", rep["details"][0])
        self.assertFalse(self.folha(pagina(corte=2.25))["ok"])  # the studio sheet samples 0.25 + k * 0.5

    def test_transicao_que_dura_o_clip_inteiro_reprova_mesmo_fora_da_grade(self):
        rep = self.folha(pagina(quadros=LENTA))
        self.assertFalse(rep["ok"])  # seen from 1.655 s to 2.095 s: the frames at 1.75 s and 2 s catch it
        self.assertEqual(len(rep["details"]), 2)

    def test_sem_keyframes_vale_o_clip_inteiro(self):
        self.assertFalse(self.folha(pagina(quadros=""))["ok"])


class TextoInteiro(Base):
    def texto(self, script):
        doc, clips = self.doc(pagina(script=script))
        with open(os.path.join(self.tmp, "index.html"), encoding="utf-8") as f:
            return qa_quadros.check_texto_inteiro(f.read(), clips)

    def test_onda_e_segunda_linha_que_sobe_passam(self):
        ok = ('M.palavras("s2_titulo", 0.3, 0.07, "onda"); M.entra("s2_apoio", 0.5, 0.35, "sobe"); '
              'M.entra("s2_barra", 0.3, 0.4, "barra"); M.mascara("s2_barra", 0, 0.4, "esquerda"); '
              'M.contador("s2_apoio", 0.3, 0.8); M.camera(["s1_titulo"], 1, 1.04, 90, 290);')
        self.assertEqual(self.texto(ok)["details"], ["ok"])

    def test_cada_entrada_que_corta_texto_reprova(self):
        for ruim in ('M.mascara("s2_apoio", 0.4, 0.5, "esquerda");', 'M.entra("s2_contato", 0.4, 0.5, "esquerda");',
                     'M.entra("s2_apoio", 0.2, 0.5, "painel");', 'M.entra("s2_apoio", 0.2, 0.5, "barra");',
                     'M.mascara(["s2_barra", "s2_contato"], 0.2, 0.5, "centro");'):
            rep = self.texto(ruim)
            self.assertFalse(rep["ok"], ruim)
            self.assertIn("texto não entra por máscara", rep["details"][0])

    def test_titulo_inteiro_no_corte(self):
        for ruim in ('M.entra("s2_titulo", 0.1, 0.3, "carimbo");', 'M.palavras("s2_titulo", 0, 0.05, "sobe");',
                     'M.entra("s2_titulo", 0, 0.3, "sobe");'):
            rep = self.texto(ruim)
            self.assertFalse(rep["ok"], ruim)
            self.assertIn("já está inteiro no corte", rep["details"][0])
        self.assertFalse(self.texto('M.contador("s2_titulo", 0, 0.5);')["ok"])  # a false number at the cut


class HeroiFinal(Base):
    def heroi(self, extra="", script="", css=""):
        html = pagina(extra=extra, script=script, css=css)
        doc, clips = self.doc(html)
        return qa_quadros.check_heroi_final(doc, html, clips)

    def test_sem_heroi_nada_a_medir(self):
        self.assertTrue(self.heroi()["ok"])

    def test_trilha_do_quadro_do_heroi(self):
        deco = '<svg id="deco1" class="clip" data-start="0" data-duration="10"><g id="heroi_quadro"></g></svg>'
        css = "#deco1 { left: 0; top: 0; width: 1080px; height: 1920px; }"
        trilha = 'M.trilha("heroi_quadro", "transform", [[0, "translate(0px, 0px) scale(0.9)"], [9.9, "%s"]]);'
        self.assertTrue(self.heroi(deco, trilha % "translate(10px, 900px) scale(0.7)", css)["ok"])
        rep = self.heroi(deco, trilha % "translate(700px, 1500px) scale(0.3)", css)
        self.assertFalse(rep["ok"])
        self.assertIn("28% da largura", rep["details"][0])

    def test_heroi_que_e_um_clip_pequeno(self):
        deco = '<svg id="deco1" class="clip" data-start="0" data-duration="10"></svg>'
        self.assertFalse(self.heroi(deco, css="#deco1 { left: 700px; top: 1400px; width: 300px; height: 300px; }")["ok"])
        self.assertTrue(self.heroi(deco, css="#deco1 { left: 90px; top: 900px; width: 620px; height: 620px; }")["ok"])
        cresce = 'M.trilha("deco1", "transform", [[0, "scale(1)"], [8, "scale(2)"]]);'
        self.assertTrue(self.heroi(deco, cresce, "#deco1 { left: 90px; top: 900px; width: 300px; height: 300px; }")["ok"])


def quadro(cheio):
    """A 216x384 frame as rows of RGB bytes: `cheio` of the safe box's rows carry ink, the rest is background."""
    linhas = []
    for y in range(384):
        tinta = 54 <= y < 54 + int(253 * cheio)
        linhas.append(b"".join(b"\x10\x20\x30" if tinta and 18 <= x < 198 else b"\xf0\xf0\xf0"
                               for x in range(216)))
    return linhas


class QuadroDeCorte(unittest.TestCase):
    def setUp(self):
        self.original = qa_quadros._quadro

    def tearDown(self):
        qa_quadros._quadro = self.original

    def rodar(self, cedo, pronto):
        # scene 2 runs from 2 s to 5 s: 2.35 s is the frame after the cut, 4.1 s (70%) the settled one
        qa_quadros._quadro = lambda video, ffmpeg, t, w, h: quadro(cedo if t < 3 else pronto)
        return qa_quadros.check_quadro_de_corte("v.mp4", "ffmpeg", [(0, 2), (2, 3)])

    def test_cena_que_abre_inteira_passa(self):
        self.assertTrue(self.rodar(0.5, 0.6)["ok"])
        self.assertTrue(self.rodar(0.36, 0.6)["ok"])  # the second line still to come

    def test_quadro_quase_vazio_depois_do_corte_reprova(self):
        rep = self.rodar(0.1, 0.6)
        self.assertFalse(rep["ok"])
        self.assertIn("cena 2: 0.35 s depois do corte", rep["details"][0])

    def test_tinta_mede_a_caixa(self):
        caixa = (18, 54, 198, 307)
        self.assertAlmostEqual(qa_quadros.tinta(216, 384, 3, quadro(0.5), caixa), 0.5, delta=0.05)
        self.assertEqual(qa_quadros.tinta(216, 384, 3, quadro(0), caixa), 0.0)


CAMPO, CLARO, FORMA = b"\x13\x2b\x52", b"\xf7\xf5\xef", b"\xff\xc7\x2c"


class FormaNaMargem(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.png = os.path.join(self.tmp, "q.png")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def medir(self, pixel):
        png(self.png, 540, 675, pixel)  # a 1080x1350 post at 1/2: the margin line is x = 40 and x = 500
        return qa_quadros.check_forma_na_margem(self.png, 1080)

    def test_forma_que_sangra_ate_a_borda_passa(self):
        sangra = lambda x, y: FORMA if x >= 300 and 200 <= y < 500 else CAMPO  # noqa: E731
        self.assertEqual(self.medir(sangra)["details"], ["ok"])
        dentro = lambda x, y: FORMA if 100 <= x < 400 and 200 <= y < 500 else CAMPO  # noqa: E731
        self.assertTrue(self.medir(dentro)["ok"])  # a shape that ends well inside the margin

    def test_forma_cortada_na_margem_reprova(self):
        direita = lambda x, y: FORMA if 300 <= x < 500 and 200 <= y < 500 else CAMPO  # noqa: E731
        rep = self.medir(direita)
        self.assertFalse(rep["ok"])
        self.assertIn("margem direita (x = 1000, 600 px de altura)", rep["details"][0])
        esquerda = lambda x, y: CLARO if 40 <= x < 240 and 100 <= y < 300 else CAMPO  # noqa: E731
        self.assertIn("margem esquerda", self.medir(esquerda)["details"][0])

    def test_haste_de_letra_na_margem_nao_e_forma(self):
        haste = lambda x, y: CLARO if 480 <= x < 500 and 200 <= y < 320 else CAMPO  # noqa: E731 - 40 px wide
        self.assertTrue(self.medir(haste)["ok"])
        curta = lambda x, y: FORMA if 300 <= x < 500 and 200 <= y < 280 else CAMPO  # noqa: E731 - 160 px tall
        self.assertTrue(self.medir(curta)["ok"])

    def test_png_ilegivel_nao_reprova(self):
        self.assertTrue(qa_quadros.check_forma_na_margem(os.path.join(self.tmp, "nao.png"), 1080)["ok"])


if __name__ == "__main__":
    unittest.main()
