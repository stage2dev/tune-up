"""The reel's JS motion and the round-4 checks: qa_script (engine verbatim, positive and deny lists, hook rule),
movimento (almost-still spans in the MP4), titulo_largura, oferta_destaque, molde and the CSS filter ban.
Each rule has a green and a red case. ffmpeg cases are skipped without ffmpeg/libx264."""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))
sys.path.insert(0, HERE)

import qa_atencao  # noqa: E402
import qa_script  # noqa: E402
import qa_video  # noqa: E402
from test_qa_atencao import ENTRADA, VIDEO, check, escrever, post_html, projeto, video_html  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
with open(qa_script.MOTOR, encoding="utf-8") as _f:
    MOTOR = _f.read()
CENA = """
    M.palavras("s1_titulo", .1, .1, "onda");
    M.camera(["s1_titulo", "s1_destaque"], 1, 1.04, 540, 600);
    M.palavras("s2_titulo", .05, .1, "sobe");
    M.contador("s3_titulo", .3, 1);
    var PASSOS = [[0, "scale(1)", "reta"], [10, "scale(1.1)"]];
    for (var i = 0; i < 2; i++) { M.trilha("s3_forma", "transform", PASSOS); }
    function pose(v) { return "translate(" + v[0] + "px, " + v[1] + "px)"; }
    M.trilha("s4_icone", "transform", [[6.5, pose([0, 0]), "meio"], [7, pose([10, 20])]]);
    M.pulso("s4_icone", 1.5, .8, 1.2);
    M.pronto();
"""


def html(cena=CENA, motor=MOTOR, extra=""):
    return VIDEO.replace("</div></body></html>", "</div>%s<script>\n%s\n%s</script></body></html>"
                         % (extra, motor, cena))


IDS = ["s1_titulo", "s1_destaque", "s2_titulo", "s3_titulo", "s3_forma", "s4_icone"]


def problemas(cena=CENA, **kw):
    return qa_script.checar(html(cena, **kw), IDS, {"s1_titulo", "s1_destaque"})


class Script(unittest.TestCase):
    def test_engine_plus_scene_is_green(self):
        self.assertEqual(problemas(), [])
        self.assertEqual(qa_script.checar(VIDEO, IDS), [])  # no script at all: nothing to check here

    def test_engine_must_be_verbatim(self):
        mudado = MOTOR.replace("Math.round(v * 1000) / 1000", "v")
        self.assertIn("motor-motion.js", " ".join(problemas(motor=mudado)))
        # whitespace and indentation may change: the comparison collapses spaces
        self.assertEqual(problemas(motor="\n".join(" " + l.strip() for l in MOTOR.splitlines())), [])

    def test_each_denied_name_is_red(self):
        casos = {
            "fetch": 'fetch("/x");', "XMLHttpRequest": "var x = new XMLHttpRequest();", "WebSocket": "new WebSocket(1);",
            "import": 'import("./x.js");', "eval": 'eval("1");', "Function": 'new Function("1");',
            "Date": "var t = Date.now();", "performance": "var t = performance.now();",
            "random": "var r = Math.random();", "setTimeout": "setTimeout(M.pronto, 1);",
            "setInterval": "setInterval(M.pronto, 1);", "requestAnimationFrame": "requestAnimationFrame(M.pronto);",
            "document": 'document.getElementById("s1_titulo");', "window": "window.x = 1;",
            "cookie": "var c = M.cookie;", "Storage": "localStorage.x = 1;", "navigator": "var n = navigator;",
            "innerHTML": 'M.innerHTML = "x";', "constructor": "var f = M.constructor;", "animate": "M.animate();",
            "then": "M.then();", "addEventListener": "M.addEventListener();",
        }
        for nome, linha in casos.items():
            with self.subTest(nome):
                self.assertTrue(any(nome in p for p in problemas(CENA.replace("M.pronto();", linha + "\n    M.pronto();"))),
                                problemas(CENA.replace("M.pronto();", linha + "\n    M.pronto();")))

    def test_positive_list_and_access(self):
        fora = problemas(CENA.replace("M.pronto();", "var a = Object.keys(M);\n    M.pronto();"))
        self.assertTrue(any("nome fora da lista: Object" in p for p in fora), fora)
        prop = problemas(CENA.replace("M.pronto();", "var a = PASSOS.reverse();\n    M.pronto();"))
        self.assertTrue(any(".reverse" in p for p in prop), prop)
        texto = problemas(CENA.replace("M.pronto();", 'var k = M["pron" + "to"];\n    M.pronto();'))
        self.assertTrue(any("acesso por texto" in p for p in texto), texto)
        variavel = problemas(CENA.replace("M.pronto();", 'var k = "x"; var v = M[k];\n    M.pronto();'))
        self.assertTrue(any("acesso [ ]" in p for p in variavel), variavel)
        crase = problemas(CENA.replace("M.pronto();", "var k = `x`;\n    M.pronto();"))
        self.assertTrue(any("crase" in p for p in crase), crase)
        url = problemas(CENA.replace("M.pronto();", 'var k = "https://x.test/a";\n    M.pronto();'))
        self.assertTrue(any("URL" in p for p in url), url)
        self.assertIn("falta M.pronto(); na última linha", problemas(CENA.replace("M.pronto();", "")))

    def test_script_shape(self):
        self.assertTrue(any("2 scripts" in p for p in qa_script.checar(html(extra="<script>var a = 1;</script>"), IDS)))
        com_src = html().replace("<script>\n", '<script src="assets/x.js">\n', 1)
        self.assertTrue(any("atributos" in p for p in qa_script.checar(com_src, IDS)))
        evento = html().replace('<div id="s3_forma"', '<div onload="M.pronto()" id="s3_forma"')
        self.assertIn("atributo de evento (on...=) numa tag", qa_script.checar(evento, IDS))
        self.assertIn("URL javascript:", qa_script.checar(html().replace("link na bio", "javascript:1"), IDS))

    def test_ids_exist_and_hook_stays_readable(self):
        sumiu = problemas(CENA.replace('M.contador("s3_titulo"', 'M.contador("s9_titulo"'))
        self.assertTrue(any("s9_titulo" in p and "não existe" in p for p in sumiu), sumiu)
        for chamada in ('M.palavras("s1_titulo", .1, .1, "sobe");', 'M.entra("s1_destaque", 0, .5, "sobe");',
                        'M.mascara("s1_titulo", 0, .5, "baixo");', 'M.trilha("s1_titulo", "opacity", [[0, "0"]]);'):
            with self.subTest(chamada):
                ruim = problemas(CENA.replace('M.palavras("s1_titulo", .1, .1, "onda");', chamada))
                self.assertTrue(any("cena 1" in p for p in ruim), ruim)
        self.assertEqual(problemas(CENA.replace("M.pronto();", 'M.pulso("s1_titulo", 0, .5, 1.05);\n    M.pronto();')), [])


class Rodada4(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.trabalho = projeto(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def rodar(self, doc):
        fonte = os.path.join(self.trabalho, "fonte")
        escrever(os.path.join(fonte, "index.html"), doc)
        return qa_atencao.checar_video(fonte, 10, "hyperframes")

    def test_titulo_largura(self):
        self.assertTrue(check(self.rodar(VIDEO), "titulo_largura")["ok"])
        pequeno = video_html(a=("#s4_titulo { top: 500px; font-size: 120px;", "#s4_titulo { top: 500px; font-size: 110px;"))
        self.assertIn("s4_titulo com 110 px", check(self.rodar(pequeno), "titulo_largura")["details"][0])
        curto = video_html(a=(">Sai às&nbsp;6h10.<", ">Sai.<"))
        self.assertTrue(check(self.rodar(curto), "titulo_largura")["ok"])  # round 6: the highlight line counts too
        curto = video_html(a=(">Sai às&nbsp;6h10.<", ">Sai.<"), b=(">Acaba às&nbsp;7h.<", ">Já.<"))
        self.assertIn("s1_titulo ocupa", check(self.rodar(curto), "titulo_largura")["details"][0])

    def test_oferta_destaque(self):
        self.trabalho = projeto(self.tmp, entrada="Pão de fermentação natural. Café grátis no sábado.\n")
        enterrada = video_html(a=(">link na bio<", ">café grátis, link na bio<"))
        self.assertIn("grátis", check(self.rodar(enterrada), "oferta_destaque")["details"][0].replace("gratis", "grátis"))
        grande = video_html(a=(">Fornadas pequenas<", ">Café grátis<"))
        self.assertTrue(check(self.rodar(grande), "oferta_destaque")["ok"])

    def test_molde(self):
        copiado = video_html(a=(">Fornadas pequenas<", ">Chiado ao frear?<"))
        self.assertIn("molde", check(self.rodar(copiado), "molde")["details"][0])
        self.trabalho = projeto(self.tmp, entrada=ENTRADA + "Oficina. Chiado ao frear? Revisão no mesmo dia.\n")
        self.assertTrue(check(self.rodar(copiado), "molde")["ok"])  # written in the briefing: a fact
        self.assertTrue(check(self.rodar(VIDEO), "molde")["ok"])

    def test_filtro_e_script_no_video(self):
        self.assertTrue(check(self.rodar(html()), "script_seguro")["ok"])
        sombra = html().replace("#s3_forma {", "#s3_forma { filter: drop-shadow(8px 8px 0 var(--text));")
        self.assertIn("filtro CSS", check(self.rodar(sombra), "script_seguro")["details"][0])
        self.assertTrue(check(self.rodar(html().replace("#s3_forma {", "#s3_forma { filter: none;")),
                             "script_seguro")["ok"])
        self.assertFalse(check(self.rodar(html(CENA.replace("M.pronto();", "fetch(1);\n    M.pronto();"))),
                               "script_seguro")["ok"])


class Rodada5(unittest.TestCase):
    """Round 5: the price is the second level (never counted up), the `#oferta` text may stand next to the h1,
    the brand name is not copy, and `vaivem` / `palavras(..., t)` are engine recipes."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.trabalho = projeto(self.tmp, entrada=ENTRADA + "Revisão de férias, sem agendar, por R$ 89.\n")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def quadro(self, doc):
        fonte = os.path.join(self.trabalho, "q1", "fonte")
        escrever(os.path.join(fonte, "index.html"), doc)
        return qa_atencao.checar_quadro(fonte)

    def test_preco_grande_no_post(self):
        pequeno = post_html(corpo='<p class="apoio">Revisão de férias, R$&nbsp;89. arraste -></p><p id="cta">Venha</p>')
        self.quadro(pequeno)
        rep = check(qa_atencao.checar_peca_post(self.trabalho, ["q1"]), "preco_destaque")
        self.assertFalse(rep["ok"])
        self.assertIn("R$ 89", rep["details"][0])
        grande = post_html(corpo='<p id="oferta">R$&nbsp;89</p><p id="cta">Venha</p>', css="#oferta { font-size: 104px; }")
        self.quadro(grande)
        self.assertTrue(check(qa_atencao.checar_peca_post(self.trabalho, ["q1"]), "preco_destaque")["ok"])
        # a threshold is no price: "acima de R$ 300" asks nothing
        self.assertEqual(qa_atencao.precos(projeto(self.tmp, entrada="Frete grátis acima de R$ 300.\n")), [])
        self.assertEqual(qa_atencao.precos(projeto(self.tmp, entrada="Kit por R$ 1.290,90. Só hoje.\n")),
                         ["1.290,90"])  # the sentence's period is not part of the price

    def test_oferta_ao_lado_do_h1(self):
        doc = post_html(corpo='<p id="oferta">R$&nbsp;89</p>', css="#oferta { font-size: 104px; }")
        self.assertTrue(check(self.quadro(doc), "titulo")["ok"])  # the 1.8x rule does not apply to #oferta
        # round 6: the price is the giant number of the offer stack, up to 1.7 times the h1 (120 px here)
        gigante = post_html(corpo='<p id="oferta">R$&nbsp;89</p>', css="#oferta { font-size: 200px; }")
        self.assertTrue(check(self.quadro(gigante), "titulo")["ok"])
        demais = post_html(corpo='<p id="oferta">R$&nbsp;89</p>', css="#oferta { font-size: 216px; }")
        self.assertIn("#oferta com 216 px", check(self.quadro(demais), "titulo")["details"][0])
        outro = post_html(corpo='<p class="apoio">R$&nbsp;89</p>', css=".apoio { font-size: 104px; }")
        self.assertFalse(check(self.quadro(outro), "titulo")["ok"])  # only #oferta has the exemption

    def test_nome_da_marca_nao_conta_palavras(self):
        h1 = "Um dois três quatro cinco seis sete oito nove dez onze doze treze catorze quinze dezesseis"
        os.makedirs(os.path.join(self.trabalho, "q2"))  # a carousel: q1 is the cover (20 words)
        doc = post_html(h1=h1, corpo="")  # 16 words + "Casa Exemplo" = 18; the name is not counted
        self.assertTrue(check(self.quadro(doc), "palavras")["ok"])
        mais = post_html(h1=h1 + " a b c d e", corpo="")
        self.assertIn("21 palavras", check(self.quadro(mais), "palavras")["details"][0])

    def test_preco_no_reel_e_contador(self):
        fonte = os.path.join(self.trabalho, "fonte")
        escrever(os.path.join(fonte, "index.html"), VIDEO)
        self.assertFalse(check(qa_atencao.checar_video(fonte, 10, "hyperframes"), "preco_destaque")["ok"])
        preco = video_html(a=(">Fornadas pequenas<", ">R$&nbsp;89<"))
        escrever(os.path.join(fonte, "index.html"), preco)
        self.assertTrue(check(qa_atencao.checar_video(fonte, 10, "hyperframes"), "preco_destaque")["ok"])
        ids, textos = IDS, {"s3_titulo": "R$ 89"}
        ruim = qa_script.checar(html(), ids, {"s1_titulo", "s1_destaque"}, textos)
        self.assertTrue(any("M.contador em s3_titulo" in p for p in ruim), ruim)
        self.assertEqual(qa_script.checar(html(), ids, {"s1_titulo", "s1_destaque"}, {"s3_titulo": "32"}), [])

    def test_receitas_novas(self):
        cena = CENA.replace("M.pronto();", 'M.vaivem("s3_forma", 0, 10, "translateY(0px)", "translateY(-8px)", .5);\n'
                                          '    M.palavras("s2_titulo", 0, .05, "sobe", .35);\n    M.pronto();')
        self.assertEqual(problemas(cena), [])
        self.assertIn("vaivem: function (id, t0, t1, a, b, periodo)", MOTOR)
        self.assertIn("palavras: function (id, atraso, passo, modo, t)", MOTOR)


@unittest.skipUnless(FFMPEG, "ffmpeg not available")
class Movimento(unittest.TestCase):
    CENAS = [(0, 1.5), (1.5, 2.5), (4, 2.5), (6.5, 3.5)]

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def make(self, nome, filtro):
        out = os.path.join(self.tmp, nome)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", filtro, "-pix_fmt", "yuv420p", out],
                       check=True)
        return out

    def test_moving_is_green_and_a_crawl_is_red(self):
        vivo = self.make("vivo.mp4", "testsrc2=size=180x320:rate=30:duration=10")
        self.assertTrue(qa_video.check_movement(vivo, FFMPEG, self.CENAS)["ok"])
        # a 6 px square crawling over a flat color: never frozen (freezedetect passes), but almost still
        lento = self.make("lento.mp4", "color=c=0xF4E4C8:size=180x320:rate=30:duration=10[f];"
                                       "color=c=0x3B2417:size=6x6:rate=30:duration=10[q];"
                                       "[f][q]overlay=x='10+t*3':y=100")
        rep = qa_video.check_movement(lento, FFMPEG, self.CENAS)
        self.assertFalse(rep["ok"])
        self.assertIn("quase parado de 0.00 s", rep["details"][0])

    def test_only_the_final_hold_may_rest(self):
        # round 5: the end card moves too; only its last second may hold still
        filtro = ("testsrc2=size=180x320:rate=30:duration=%s[a];color=c=0xF4E4C8:size=180x320:rate=30:duration=%s[b];"
                  "[a][b]concat=n=2:v=1:a=0")
        self.assertTrue(qa_video.check_movement(self.make("fim.mp4", filtro % (9, 1)), FFMPEG, self.CENAS)["ok"])
        parado = qa_video.check_movement(self.make("parado.mp4", filtro % (6.5, 3.5)), FFMPEG, self.CENAS)
        self.assertFalse(parado["ok"])
        self.assertIn("quase parado de 6.5", parado["details"][0])


if __name__ == "__main__":
    unittest.main()
