"""scripts/qa_atencao.py (with qa_css.py and qa_cenas.py): every attention check green and red on minimal HTML,
with a fake brand under <tmp>/.tune-up/estudio/marca/marca.json. No browser, no network."""
import contextlib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))

import qa_atencao  # noqa: E402
import qa_css  # noqa: E402

CORES = {"cores.bg": "#FFF8EC", "cores.surface": "#F4E4C8", "cores.primary": "#C9702B", "cores.text": "#3B2417",
         "cores.accent": "#5A3320"}


def marca(**trocas):
    campos = {k: {"valor": v, "fonte": "styles.css:1", "confianca": "alta", "travado": False} for k, v in CORES.items()}
    campos["nome"] = {"valor": "Casa Exemplo", "fonte": "package.json:2", "confianca": "media", "travado": False}
    campos["logo"] = {"valor": "public/logo-2031.svg", "fonte": "index.html:9", "confianca": "media",
                      "travado": False}
    for k, v in trocas.items():
        campos[k.replace("_", ".")]["valor"] = v
    return {"versao": 1, "gerado_em": "2026-11-11T10:00:00Z", "modo": "marca", "campos": campos}


ENTRADA = ("Primeira fornada sai às 6h10 e acaba às 7h. Fermentação de 24 horas. Já foram 1240 pedidos.\n"
           "Contato: WhatsApp (11) 4002-8922.\n")
ESTRATEGIA = """objetivo: encher a agenda
publico: quem passa a caminho do trabalho antes das 7h
estagio: morno
promessa: pão saindo às 6h10, todo dia
prova: fermentação de 24 horas
arquetipo: número grande
estilo: produto-em-destaque | o pão é o que se vende
gancho 1: [numero+prazo] Sai às 6h10. Acaba às 7h. | nota 5 | concreto e verdadeiro
gancho 2: [pergunta] Pão quente antes das 7h? | nota 3 | menos concreto
gancho 3: [rotulo] Fermentação natural | nota 1 | rótulo
escolhido: 1 | tem horário
cta: Reserve o seu pela manhã | forte
faltou: foto da fornada
"""
COPY = "## q1\nlayout: l-titulo\n\n## Legenda\nSai às 6h10 e acaba às 7h: reserve o seu.\n\nTexto.\n\n#bairro #pao\n"


def escrever(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return caminho


def projeto(tmp, dados="padrao", entrada=ENTRADA):
    """<tmp>/.tune-up/estudio/trabalhos/x with entrada.md and estrategia.md; the brand unless dados is None."""
    if dados is not None:
        escrever(os.path.join(tmp, ".tune-up", "estudio", "marca", "marca.json"),
                 json.dumps(marca() if dados == "padrao" else dados))
    trabalho = os.path.join(tmp, ".tune-up", "estudio", "trabalhos", "x")
    escrever(os.path.join(trabalho, "entrada.md"), entrada)
    escrever(os.path.join(trabalho, "estrategia.md"), ESTRATEGIA)
    return trabalho


ICONE = '<svg class="icone" viewBox="0 0 10 10" aria-hidden="true"><circle cx="5" cy="5" r="5"/></svg>'


def post_html(h1="Sai às&nbsp;6h10.<br>Acaba às&nbsp;7h.", corpo='<p class="apoio">Reserve o seu. arraste -></p>',
              css="", layout="l-titulo", icone=ICONE, marca='<p class="marca">Casa Exemplo</p>'):
    return ("<!doctype html><html><head><title>Título não conta 99</title><style>\n"
            ":root { --bg: #FFF8EC; --text: #3B2417; --primary: #C9702B; }\n"
            "#root { width: 1080px; height: 1350px; background: var(--bg); color: var(--text); font-size: 32px; "
            "text-wrap: pretty; }\n"
            "h1 { font-size: 120px; color: var(--text); }\n.apoio { font-size: 40px; }\n"
            ".icone { width: 300px; height: 300px; fill: var(--primary); }\n.marca { font-size: 32px; }\n"
            "#cta { font-size: 44px; background: var(--primary); color: #3B2417; }\n%s\n</style></head><body>"
            '<div id="root" class="%s">%s<h1>%s</h1>%s%s</div></body></html>' % (css, layout, marca, h1, icone, corpo))


VIDEO = """<!doctype html><html><head><style>
:root { --bg: #FFF8EC; --text: #3B2417; --primary: #C9702B; --accent: #5A3320; }
#root { position: relative; width: 1080px; height: 1920px; background: var(--bg); color: var(--text); font-size: 48px;
  text-wrap: balance; }
.clip { position: absolute; left: 90px; }
#s1_bloco { top: 0; width: 1080px; height: 300px; background: var(--primary); transform: rotate(-6deg); }
#s3_forma { top: 1100px; width: 400px; height: 400px; border-radius: 50%; background: var(--accent); }
#s4_icone { top: 1150px; width: 300px; height: 300px; fill: var(--primary); }
#s1_titulo { top: 400px; font-size: 120px; animation: assenta 1.5s ease-out 0s 1 both; }
#s1_destaque { top: 560px; font-size: 120px; color: var(--primary); animation: assenta 1.5s ease-out 0s 1 both; }
#s2_titulo { top: 500px; font-size: 104px; animation: sobe 2.5s ease-out 0s 1 both; }
#s2_apoio { top: 700px; font-size: 52px; animation: sobe 2.5s ease-out 0s 1 both; }
#s2_logo { top: 1500px; width: 140px; }
#s3_titulo { top: 600px; font-size: 110px; animation: sobe 2.5s ease-out 0s 1 both; }
#s4_titulo { top: 500px; font-size: 120px; animation: assenta 3.5s ease-out 0s 1 both; }
#s4_contato { top: 800px; font-size: 52px; animation: sobe 3.5s ease-out 0s 1 both; }
#s4_marca { top: 1300px; font-size: 44px; }
#s4_selo { top: 1000px; font-size: 44px; border-radius: 999px; background: var(--accent); color: var(--bg); }
#tr1, #tr2, #tr3 { top: 0; width: 1080px; height: 1920px; background: var(--primary); }
#tr1 { animation: painel 0.6s linear 0s 1 both; }
#tr2 { animation: iris 0.6s linear 0s 1 both; }
#tr3 { animation: painel 0.6s linear 0s 1 both; }
@keyframes assenta { 0% { transform: scale(1.06); } 100% { transform: scale(1); } }
@keyframes sobe { 0% { opacity: 0; transform: translateY(80px); } 20%, 100% { opacity: 1; transform: none; } }
@keyframes painel { 0%, 34% { transform: translateX(-100%); } 50% { transform: none; }
  66%, 100% { transform: translateX(100%); } }
@keyframes iris { 0%, 34% { clip-path: circle(0% at 50% 50%); } 50% { clip-path: circle(80% at 50% 50%); }
  66%, 100% { clip-path: circle(0% at 50% 50%); } }
</style></head><body>
<div id="root" data-composition-id="video" data-start="0" data-duration="10" data-width="1080" data-height="1920">
<div id="s1_bloco" class="clip" data-start="0" data-duration="1.875"></div>
<div id="s1_titulo" class="clip l-topo" data-start="0" data-duration="1.875">Sai às&nbsp;6h10.</div>
<div id="s1_destaque" class="clip" data-start="0" data-duration="1.875">Acaba às&nbsp;7h.</div>
<div id="s2_titulo" class="clip l-base" data-start="1.875" data-duration="2.5">Fermentação de&nbsp;24 horas</div>
<div id="s2_apoio" class="clip" data-start="1.875" data-duration="2.5">Feita na véspera</div>
<img id="s2_logo" class="clip" src="assets/logo.svg" alt="Casa Exemplo 2031" data-start="1.875" data-duration="2.5">
<div id="s3_titulo" class="clip l-cheia" data-start="4.375" data-duration="2.25">Fornadas pequenas</div>
<div id="s3_forma" class="clip" data-start="4.375" data-duration="2.25"></div>
<div id="s4_titulo" class="clip l-faixa" data-start="6.625" data-duration="3.375">Reserve o&nbsp;seu pão</div>
<div id="s4_contato" class="clip" data-start="6.625" data-duration="3.375">link na bio</div>
<div id="s4_selo" class="clip" data-start="6.625" data-duration="3.375">Sai às 6h10</div>
<div id="s4_marca" class="clip" data-start="6.625" data-duration="3.375">Casa Exemplo</div>
<svg id="s4_icone" class="clip" data-start="6.625" data-duration="3.375" viewBox="0 0 10 10"><rect width="10" height="4"/></svg>
<div id="tr1" class="clip" data-start="1.575" data-duration="0.6"></div>
<div id="tr2" class="clip" data-start="4.075" data-duration="0.6"></div>
<div id="tr3" class="clip" data-start="6.325" data-duration="0.6"></div>
</div></body></html>
"""


def video_html(**trocas):
    """VIDEO with exact replacements; every `antes` must exist (a typo never makes a silent green)."""
    html = VIDEO
    for antes, depois in trocas.values():
        assert antes in html, antes
        html = html.replace(antes, depois)
    return html


def falhas(checks):
    return sorted(c["name"] for c in checks if not c["ok"])


def check(checks, nome):
    return next(c for c in checks if c["name"] == nome)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.trabalho = projeto(self.tmp)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def quadro(self, n, html, trabalho=None):
        return os.path.dirname(escrever(os.path.join(trabalho or self.trabalho, "q%d" % n, "fonte", "index.html"),
                                        html))

    def video(self, html=VIDEO, trabalho=None):
        return os.path.dirname(escrever(os.path.join(trabalho or self.trabalho, "fonte", "index.html"), html))


class Puras(unittest.TestCase):
    def test_contraste(self):
        self.assertEqual(qa_atencao.contraste("#000000", "#FFFFFF"), 21.0)
        self.assertLess(qa_atencao.contraste("#777777", "#FFFFFF"), 4.5)

    def test_tiques_por_palavra_inteira(self):
        self.assertEqual(qa_atencao.achar_tiques("Não é solução, é rotina. Deseja você um pão?"), [])
        self.assertEqual(qa_atencao.achar_tiques("Não é só pão"), ["nao e so"])
        self.assertEqual(qa_atencao.achar_tiques("Diga ADEUS à fila!"), ["diga adeus", "!"])
        self.assertEqual(qa_atencao.achar_tiques("Diga adeus!", arte=False), ["diga adeus"])
        self.assertEqual(qa_atencao.achar_tiques("Pão — quente"), ["—"])

    def test_numeros(self):
        self.assertEqual(qa_atencao.numeros("1.240 pães a 12,90 às 6h40 em 15/11, passo 1"),
                         ["1240", "1290", "40", "15", "11"])

    def test_tiques_iguais_ao_checklist(self):
        caminho = os.path.join(STUDIO, "referencias", "checklist-atencao.md")
        self.assertTrue(os.path.isfile(caminho), "referencias/checklist-atencao.md (pacote P1) ainda não existe")
        with open(caminho, encoding="utf-8") as f:
            blocos = re.findall(r"^```tiques\n(.*?)^```", f.read(), re.S | re.M)
        self.assertEqual(len(blocos), 1)
        self.assertEqual(tuple(x.strip() for x in blocos[0].splitlines() if x.strip()), qa_atencao.TIQUES)

    def test_parser(self):
        html = ('<html><head><title>x</title><style>/* a{} */ @font-face { font-family: X; src: local(Y); }'
                '@media (min-width: 1px) { .a, h1 { font-size: 10px; } }'
                '@keyframes k { from { opacity: 0; } to { opacity: 1; } }</style></head>'
                '<body><h1 id="t" class="a b">Oi <em>você</em></h1><img alt="não conta"><br/>fim</body></html>')
        self.assertEqual(qa_css.texto_visivel(html), [("h1", "t", "a b", "Oi"), ("em", "", "", "você"),
                                                      ("body", "", "", "fim")])
        self.assertEqual(qa_css.regras_css(html), [{"seletores": [".a", "h1"], "decl": [("font-size", "10px")]}])
        self.assertEqual(qa_css.keyframes(html), {"k": [(["0%"], [("opacity", "0")]), (["100%"], [("opacity", "1")])]})
        self.assertEqual((qa_css.valor_px("112px"), qa_css.valor_px("2rem"), qa_css.valor_px("calc(1px)")),
                         (112.0, None, None))
        self.assertEqual(qa_css.ultimo_composto(".l-numero > h1.big"), "h1.big")


class Marca(Base):
    def test_cores_da_marca_e_neutro_para_campo_vazio(self):
        cores, erro = qa_atencao.cores_da_marca(self.trabalho)
        self.assertIsNone(erro)
        self.assertEqual(cores, set(CORES.values()))
        escrever(os.path.join(self.tmp, ".tune-up", "estudio", "marca", "marca.json"),
                 json.dumps(marca(cores_accent=None)))
        cores, _ = qa_atencao.cores_da_marca(self.trabalho)
        self.assertIn("#52525B", cores)  # descobrir_marca.PALETA_NEUTRA["cores.accent"]
        fonte = self.quadro(1, post_html(css=".apoio { color: #52525B; }"))
        self.assertTrue(check(qa_atencao.checar_quadro(fonte), "cores_marca")["ok"])

    def test_sem_marca(self):
        outro = tempfile.mkdtemp()
        try:
            self.assertEqual(qa_atencao.cores_da_marca(outro), (set(), "marca.json não encontrado"))
            fonte = self.quadro(1, post_html(), trabalho=outro)
            self.assertEqual(check(qa_atencao.checar_quadro(fonte), "cores_marca")["details"],
                             ["marca.json não encontrado"])
        finally:
            shutil.rmtree(outro)

    def test_pares_ordenados_com_so_titulo(self):
        lista = qa_atencao.pares(self.trabalho)
        self.assertTrue(lista)
        self.assertEqual([p["razao"] for p in lista], sorted((p["razao"] for p in lista), reverse=True))
        self.assertTrue(all(p["razao"] >= 3 for p in lista))
        usos = {(p["texto"], p["fundo"]): p["uso"] for p in lista}
        self.assertEqual(usos[("cores.text", "cores.bg")], "normal")
        self.assertEqual(usos[("cores.primary", "cores.bg")], "so_titulo")  # 3.2:1
        self.assertNotIn(("cores.primary", "cores.surface"), usos)  # below 3
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(qa_atencao.imprimir_pares(self.trabalho), 0)
        self.assertIn("texto cores.text #3B2417 sobre cores.bg #FFF8EC: ", buf.getvalue())
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(qa_atencao.imprimir_pares(self.tmp + "-nada"), 2)

    def test_problemas_textos(self):
        ok = {"plataforma": "google", "url": "https://x.test/99", "caminhos": ["promo-77"],
              "titulos": ["Sai às 6h10", "Reserve já!", "1.240 pedidos", "Casa Exemplo"]}
        self.assertEqual(qa_atencao.problemas_textos(ok, self.trabalho), [])
        ruim = dict(ok, descricoes=["Diga adeus à fila", "Pão por 9,90 hoje"])
        self.assertEqual(qa_atencao.problemas_textos(ruim, self.trabalho),
                         ["descricoes 1: tique 'diga adeus': Diga adeus à fila",
                          "descricoes 2: número 990 não está no briefing (entrada.md) nem na marca: Pão por 9,90 hoje"])
        self.assertEqual(qa_atencao.problemas_textos([], self.trabalho), [])


class Quadro(Base):
    def test_quadro_verde_e_sem_index(self):
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, post_html()))), [])
        self.assertEqual(len(falhas(qa_atencao.checar_quadro(os.path.join(self.trabalho, "q9", "fonte")))), 9)

    def test_titulo(self):
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, "<p>quadro 1</p>"))).count("titulo"), 1)
        for h1, css in (("Sai às 6h10. Acaba às 7h.", "h1 { font-size: 70px; }"),  # below 88
                        ("Sai às 6h10. Acaba às 7h.", ".apoio { font-size: 72px; }"),  # 120 < 1.8 x 72
                        ("Sai às 6h10 e acaba às 7h, todo santo dia", "")):  # 41 characters
            checks = qa_atencao.checar_quadro(self.quadro(1, post_html(h1=h1, css=css)))
            self.assertIn("titulo", falhas(checks), (h1, css))
        dois = post_html(corpo="<h1>Outro</h1>")
        self.assertIn("titulo", falhas(qa_atencao.checar_quadro(self.quadro(1, dois))))
        tag = post_html(corpo='<p>Feito na véspera</p>', css="p { font-size: 72px; }")  # a tag rule counts
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, tag))), ["titulo"])

    def test_titulo_citacao_aspas_grandes(self):
        """l-citacao: the opening quote mark (280 px) is punctuation only and never competes with the h1."""
        for corpo, css in (('<span class="aspas">“</span><p class="apoio">Ana, Centro</p>',
                            ".aspas { font-size: 280px; color: var(--primary); } h1 { font-size: 104px; }"),
                           ('<p class="apoio">Ana, Centro</p>',
                            "h1 { font-size: 104px; } h1::before { content: '“'; font-size: 280px; }"),
                           ('<p class="apoio">Ana, Centro</p>',
                            "h1 { font-size: 104px; } .fantasma { font-size: 300px; }")):  # not in the page
            checks = qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Fiz a&nbsp;prova sem travar.", corpo=corpo,
                                                                       css=css, layout="l-citacao")))
            self.assertEqual(falhas(checks), [], css)
        # a pseudo-element never stands in for the h1's own size
        pseudo = post_html(css="h1::after { content: '.'; font-size: 40px; }")
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, pseudo))), [])
        so_pseudo = post_html(css="h1::before { content: '“'; font-size: 280px; }").replace(
            "h1 { font-size: 120px; ", "h1 { ")
        self.assertIn("titulo", falhas(qa_atencao.checar_quadro(self.quadro(1, so_pseudo))))

    def test_h1_em_l_numero_h1_e_achado(self):
        html = post_html(h1="1.240", layout="l-numero").replace("h1 { font-size: 120px;", ".l-numero h1 { font-size: 240px;")
        self.assertIn(".l-numero h1 { font-size: 240px", html)
        checks = qa_atencao.checar_quadro(self.quadro(1, html))
        self.assertEqual(falhas(checks), [])
        sem = post_html().replace("h1 { font-size: 120px; ", "h1 { ")
        checks = qa_atencao.checar_quadro(self.quadro(1, sem))
        self.assertEqual(falhas(checks), ["fonte_minima", "titulo"])

    def test_fonte_minima(self):
        for css in (".apoio { font-size: 2rem; }", ".apoio { font: 700 40px serif; }", ".apoio { font-size: 20px; }"):
            self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, post_html(css=css)))), ["fonte_minima"],
                             css)
        sem_root = post_html().replace("color: var(--text); font-size: 32px; ", "color: var(--text); ")
        checks = qa_atencao.checar_quadro(self.quadro(1, sem_root))
        self.assertEqual(check(checks, "fonte_minima")["details"], ["#root sem font-size em px"])

    def test_palavras(self):
        longo = "<p class=\"apoio\">%s</p>" % " ".join(["pão"] * 18)  # 5 in the title + 18 = 23
        # round 6: a single post carries hook + offer stack + call, so it takes 30 words like any other frame
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, post_html(corpo=longo)))), [])
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(2, post_html(corpo=longo)))), [])  # up to 30
        # with a q2 beside it, q1 is a carousel cover: 20 words
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, post_html(corpo=longo)))), ["palavras"])

    def test_cores_marca(self):
        verdes = ".apoio { color: transparent; border-color: currentColor; background: inherit; }"
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, post_html(css=verdes)))), [])
        for css in (".apoio { color: #123456; }", ".apoio { color: white; }",
                    ".apoio { color: rgba(59, 36, 23, .5); }", ".apoio { color: #3B241780; }",
                    ".apoio { color: color-mix(in srgb, #3B2417 50%, #FFF8EC); }",
                    ".apoio { box-shadow: 0 0 4px rgb(0 0 0); }"):
            checks = qa_atencao.checar_quadro(self.quadro(1, post_html(css=css)))
            self.assertEqual(falhas(checks), ["cores_marca"], css)
        svg = post_html(corpo='<svg><circle fill="red" r="4"/></svg><p class="apoio">ok</p>')
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, svg))), ["cores_marca"])
        fonte = post_html(css='.apoio { font-family: "Red Hat", serif; color: rgb(59 36 23 / 100%); }')
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, fonte))), [])

    def test_tiques(self):
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Não é&nbsp;só&nbsp;pão")))), ["tiques"])
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Reserve já!")))), ["tiques"])
        ok = post_html(h1="Não é&nbsp;solução", corpo='<p class="apoio">Deseja você?</p>')
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, ok))), [])

    def test_numeros(self):
        for h1, ok in (("1.240 pedidos", True), ("Fermentou 24 horas", True), ("Fermentou 48 horas", False),
                       ("Passo 1 de 3", True), ("Desde 2031", False), ("Casa Exemplo 6h40", False)):
            checks = qa_atencao.checar_quadro(self.quadro(1, post_html(h1=h1)))
            self.assertEqual(check(checks, "numeros")["ok"], ok, h1)
        projeto(self.tmp, entrada="Pão desde 2024.\n")
        checks = qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Há 24 anos")))
        self.assertEqual(check(checks, "numeros")["details"],
                         ["número 24 não está no briefing (entrada.md) nem na marca"])  # token, not substring

    def test_numeros_escritos_em_pedacos(self):
        projeto(self.tmp, entrada="Pão a R$ 12,90. Ligue 11940028922. Cesta por R$ 1.240,00.\n")
        ok = '<p class="apoio">R$ 12<small>,90</small>, (11) 94002-8922, cesta R$ 1.240</p>'
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Pão quente", corpo=ok)))), [])
        ruim = '<p class="apoio">R$ 13<small>,90</small></p>'
        checks = qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Pão quente", corpo=ruim)))
        self.assertEqual(check(checks, "numeros")["details"],
                         ["número 13 não está no briefing (entrada.md) nem na marca",
                          "número 90 não está no briefing (entrada.md) nem na marca"])

    def test_sem_entrada_md_falha_alto(self):
        os.remove(os.path.join(self.trabalho, "entrada.md"))
        checks = qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Pão quente")))  # no number at all
        self.assertEqual(falhas(checks), ["numeros"])
        self.assertIn("entrada.md não encontrado", check(checks, "numeros")["details"][0])
        self.assertIn("entrada.md não encontrado", qa_atencao.problemas_textos({"titulos": ["Pão"]}, self.trabalho)[0])
        escrever(os.path.join(self.trabalho, "entrada.md"), "  \n")
        self.assertIn("entrada.md vazio", check(qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Pão quente"))),
                                                "numeros")["details"][0])

    def test_recurso_visual(self):
        verdes = (("", ""),  # the template's 300x300 svg icon
                  ('<img src="assets/foto1.jpg" alt="">', ""),
                  ('<div class="d"></div>', ".d { width: 1480px; height: 520px; background: var(--primary); "
                                            "transform: rotate(-8deg); }"),  # a band, but diagonal
                  ('<div class="d"></div>', ".d { width: 50%; height: 30%; border-radius: 50%; background: var(--primary); }"),
                  ('<p class="sangra" aria-hidden="true">pão</p>', ".sangra { font-size: 420px; color: var(--primary); }"),
                  ('<span class="mt">quente cedo?</span>', ".mt { background: var(--primary); }"))
        for corpo, css in verdes:
            h1 = "Pão " + corpo if 'class="mt"' in corpo else "Pão quente cedo?"
            html = post_html(h1=h1, corpo="" if 'class="mt"' in corpo else corpo, css=css, icone="" if corpo else ICONE)
            self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, html))), [], corpo)
        numero = post_html(h1="1.240", layout="l-numero", css="h1 { font-size: 240px; }", icone="")
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, numero))), [])
        vermelhos = (("", ""),  # text only
                     ('<img src="assets/logo.svg" alt="">', ""),  # the logo never counts
                     ('<p class="f">Para quem trabalha sentado</p>', ".f { width: 920px; height: 160px; background: var(--primary); }"),
                     ('<div class="f"></div>', ".f { width: 1080px; height: 300px; background: var(--primary); }"),  # plain band
                     ('<div class="f"></div>', ".f { width: 420px; height: 24px; background: var(--primary); }"),  # thin bar
                     ('<div class="f"></div>', ".f { width: 400px; height: 400px; }"),  # no color: nothing to see
                     ('<svg class="f" viewBox="0 0 1 1"></svg>', ""))  # no size
        for corpo, css in vermelhos:
            checks = qa_atencao.checar_quadro(self.quadro(1, post_html(corpo=corpo, css=css, icone="")))
            self.assertEqual(falhas(checks), ["recurso_visual"], corpo + css)
        self.assertIn("só texto", check(checks, "recurso_visual")["details"][0])

    def test_legibilidade(self):
        sem = post_html().replace("text-wrap: pretty; ", "")
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, sem))), ["legibilidade"])
        proprio = sem.replace("h1 { font-size: 120px;", "h1 { text-wrap: balance; font-size: 120px;").replace(
            ".apoio { font-size: 40px; }", ".apoio { font-size: 40px; text-wrap: pretty; }")
        self.assertEqual(falhas(qa_atencao.checar_quadro(self.quadro(1, proprio))), [])
        for css, ok in (("h1 { line-height: 1; clip-path: inset(0 0 0 0); }", False),
                        (".apoio { line-height: 1; overflow: hidden; }", False),
                        ("h1 { line-height: 1; padding: 0.1em 0; clip-path: inset(0); }", False),  # .1em bottom
                        ("h1 { line-height: 1.05; padding: .12em 0 .2em; clip-path: inset(0); }", True),
                        ("h1 { line-height: 1.05; padding-top: 14px; padding-bottom: 24px; clip-path: inset(0); }",
                         True),
                        ("h1 { line-height: 1.25; clip-path: inset(0); }", True),
                        ("h1 { clip-path: inset(0); }", True)):  # line-height normal
            checks = qa_atencao.checar_quadro(self.quadro(1, post_html(css=css)))
            self.assertEqual(falhas(checks), [] if ok else ["legibilidade"], css)

    def test_titulo_quebra_por_sentido(self):
        """Each sentence of the h1 on its own line and every 1-2 letter word glued with &nbsp;: text-wrap never
        leaves "o" or "E" ending a line ("Chegou cedo o / pão? E / o café?")."""
        for h1, ok in (("Chegou cedo o pão? E o café?", False), ("Chegou cedo?<br>E&nbsp;o&nbsp;café?", True),
                       ("Pão quente cedo?<br>E o&nbsp;café?", False), ("Dr.&nbsp;Ana atende sábado", True),
                       ("Pão pronto às 6h", False), ("Pão pronto às&nbsp;6h", True), ("1.240 pedidos", True), ("Reserve o pão", False)):
            checks = qa_atencao.checar_quadro(self.quadro(1, post_html(h1=h1)))
            self.assertEqual(falhas(checks), [] if ok else ["legibilidade"], h1)
        detalhes = check(qa_atencao.checar_quadro(self.quadro(1, post_html(h1="Chegou cedo o pão? E o café?"))),
                         "legibilidade")["details"]
        self.assertIn("duas frases na mesma linha", detalhes[0])
        self.assertEqual(sum("&nbsp;" in d for d in detalhes), 3)  # o, E, o

    def test_layout_post(self):
        for layout in ("", "l-titulo l-numero", "l-grade"):
            checks = qa_atencao.checar_quadro(self.quadro(1, post_html(layout=layout)))
            self.assertEqual(falhas(checks), ["layout_post"], layout)


class Peca(Base):
    def carrossel(self, q1=None, q2=None, copy=COPY):
        self.quadro(1, q1 or post_html())
        self.quadro(2, q2 or post_html(h1="Reserve o&nbsp;seu", layout="l-cheia",
                                       corpo='<p id="cta">Peça pelo WhatsApp</p>'))
        if copy is not None:
            escrever(os.path.join(self.trabalho, "copy.md"), copy)
        return qa_atencao.checar_peca_post(self.trabalho, ["q2", "q1"])

    def test_marca_escrita(self):
        """The brand name (campos.nome) is written in some frame; a symbol-only logo is not enough."""
        sem = lambda html: html.replace('<p class="marca">Casa Exemplo</p>', "")  # noqa: E731
        self.quadro(1, sem(post_html()))
        self.quadro(2, sem(post_html(h1="Reserve o&nbsp;seu", layout="l-cheia", corpo='<p id="cta">Peça pelo WhatsApp</p>')))
        escrever(os.path.join(self.trabalho, "copy.md"), COPY)
        checks = qa_atencao.checar_peca_post(self.trabalho, ["q1", "q2"])
        self.assertEqual(falhas(checks), ["marca"])
        self.assertIn("Casa Exemplo", check(checks, "marca")["details"][0])
        self.quadro(2, post_html(h1="Reserve o&nbsp;seu", layout="l-cheia", corpo='<p id="cta">Peça pelo WhatsApp</p>'))
        self.assertEqual(falhas(qa_atencao.checar_peca_post(self.trabalho, ["q1", "q2"])), [])  # one frame is enough

    def test_prazo_do_briefing_na_arte(self):
        self.assertEqual(qa_atencao.prazos("Frete grátis acima de R$ 300, só esta semana. Até 15/12 ou até sábado."),
                         ["esta semana", "15/12", "sabado"])
        self.assertEqual(qa_atencao.prazos("Aberto de segunda a sábado, até 21h. Novo horário a partir de maio."), [])
        projeto(self.tmp, entrada=ENTRADA + "Frete grátis acima de R$ 300, só esta semana.\n")
        cta = '<p id="cta">Compre com frete grátis acima de R$&nbsp;300</p>'
        checks = self.carrossel(q2=post_html(h1="Reserve o&nbsp;seu", layout="l-cheia", corpo=cta))
        self.assertEqual(falhas(checks), ["cta"])
        self.assertIn("prazo do briefing 'esta semana'", check(checks, "cta")["details"][0])
        cta = '<p id="cta">Frete grátis acima de R$&nbsp;300, só esta semana</p>'
        self.assertEqual(falhas(self.carrossel(q2=post_html(h1="Reserve o&nbsp;seu", layout="l-cheia", corpo=cta))), [])

    def test_peca_verde(self):
        self.assertEqual(falhas(self.carrossel()), [])
        item = qa_atencao.item_peca(self.trabalho, [1, 2])
        self.assertEqual((item["frame"], item["ok"], item["failed"]), ("peca", True, []))

    def test_estrategia(self):
        escrever(os.path.join(self.trabalho, "estrategia.md"), ESTRATEGIA.replace("gancho 3:", "# gancho 3"))
        self.assertEqual(check(self.carrossel(), "estrategia")["details"], ["estrategia.md sem gancho 3"])
        os.remove(os.path.join(self.trabalho, "estrategia.md"))
        self.assertEqual(falhas(self.carrossel()), ["estrategia"])

    def test_cta(self):
        no_q1 = post_html(corpo='<p class="apoio">arraste -></p><p id="cta">Peça já</p>')
        self.assertEqual(falhas(self.carrossel(q1=no_q1)), ["cta"])
        redondo = post_html(h1="Reserve o&nbsp;seu", layout="l-cheia", css="#cta { border-radius: 24px; }",
                            corpo='<p id="cta">Peça pelo WhatsApp</p>')
        self.assertEqual(falhas(self.carrossel(q2=redondo)), ["cta"])
        sem = post_html(h1="Reserve o&nbsp;seu", layout="l-cheia")
        self.assertEqual(falhas(self.carrossel(q2=sem)), ["cta"])

    def test_sequencia_layout(self):
        igual = post_html(h1="Reserve o&nbsp;seu", corpo='<p id="cta">Peça pelo WhatsApp</p>')
        self.assertEqual(falhas(self.carrossel(q2=igual)), ["sequencia_layout"])

    def test_arraste(self):
        self.assertEqual(falhas(self.carrossel(q1=post_html(corpo="<p class=\"apoio\">Veja</p>"))), ["arraste"])
        escrever(os.path.join(self.trabalho, "copy.md"), COPY)
        self.quadro(1, post_html(corpo='<p class="apoio">Veja</p><p id="cta">Peça</p>'))
        self.assertEqual(falhas(qa_atencao.checar_peca_post(self.trabalho, ["q1"])), [])  # one frame: no swipe

    def test_legenda(self):
        self.assertEqual(check(self.carrossel(copy=None), "legenda")["details"], ["copy.md não encontrado"])
        for copy in ("## q1\nlayout: l-titulo\n", "## Legenda\n" + "x" * 126 + "\n",
                     "## Legenda\nCurta.\n\n" + "texto " * 200, "## Legenda\nCurta.\n\n#a #b #c #d #e #f\n",
                     "## Legenda\nDiga adeus à fila.\n"):
            self.assertEqual(falhas(self.carrossel(copy=copy)), ["legenda"], copy[:40])
        cinco = "## Legenda\nReserve o seu! Sai às 6h10.\n\n#a #b #c #d #e\n## Notas\n#x #y\n"
        self.assertEqual(falhas(self.carrossel(copy=cinco)), [])  # `!` is fine in a caption
        inventado = "## Legenda\nSai às 6h10 e rende 3x mais: são 48 horas de fermentação.\n\n#pao2031\n"
        self.assertEqual(check(self.carrossel(copy=inventado), "legenda")["details"],
                         ["legenda: número 48 não está no briefing (entrada.md) nem na marca"])
        tag = "## Legenda\nFermentação de 24 horas, 1.240 pedidos.\n\n#padaria2031 #pao\n"
        self.assertEqual(falhas(self.carrossel(copy=tag)), [])  # numbers in hashtags do not count


class Video(Base):
    def rodar(self, html=VIDEO, duracao=10, engine="hyperframes"):
        return qa_atencao.checar_video(self.video(html), duracao, engine)

    def test_video_verde_e_estrategia(self):
        checks = self.rodar()
        self.assertEqual(falhas(checks), [])
        self.assertEqual([c["name"] for c in checks],
                         ["estrategia", "cenas", "gancho", "palavras_cena", "recurso_visual", "legibilidade",
                          "fonte_minima", "cores_marca",
                          "cta_final", "sequencia_layout", "transicoes", "estilo", "tiques", "numeros", "marca",
                          "titulo_largura", "oferta_destaque", "preco_destaque", "molde", "script_seguro",
                          "folha_limpa", "texto_inteiro", "heroi_final"])
        os.remove(os.path.join(self.trabalho, "estrategia.md"))
        self.assertEqual(falhas(self.rodar()), ["estrategia"])

    def test_cenas(self):
        longa = video_html(a=('id="s1_titulo" class="clip l-topo" data-start="0" data-duration="1.875"',
                              'id="s1_titulo" class="clip l-topo" data-start="0" data-duration="2"'))
        self.assertEqual(falhas(self.rodar(longa)), ["cenas"])  # s1 clips with different times
        self.assertIn("cenas", falhas(self.rodar(duracao=15)))  # 4 scenes summing 10 in a 15 s video
        solto = video_html(a=('<div id="tr1"', '<div id="legenda" class="clip" data-start="0" data-duration="10">'
                                               'oi</div><div id="tr1"'))
        self.assertIn("clip de texto sem id", " ".join(check(self.rodar(solto), "cenas")["details"]))

    def test_gancho(self):
        some = video_html(a=("#s1_titulo { top: 400px; font-size: 120px; animation: assenta",
                             "#s1_titulo { top: 400px; font-size: 120px; animation: sobe"))
        self.assertEqual(falhas(self.rodar(some)), ["gancho"])
        fechado = video_html(a=("#s1_destaque { top: 560px;", "#s1_destaque { clip-path: circle(0%); top: 560px;"))
        self.assertEqual(falhas(self.rodar(fechado)), ["gancho"])
        aberto = video_html(a=("#s1_destaque { top: 560px;", "#s1_destaque { clip-path: inset(0px 0% 0 0); top: 560px;"))
        self.assertEqual(falhas(self.rodar(aberto)), [])
        logo = video_html(a=('src="assets/logo.svg" alt="Casa Exemplo 2031" data-start="1.875"',
                             'src="assets/logo.svg" alt="Casa Exemplo 2031" data-start="0"'))
        self.assertIn("s2_logo visível em t=0", " ".join(check(self.rodar(logo), "gancho")["details"]))

    def test_palavras_cena(self):
        self.assertEqual(falhas(self.rodar()), [])  # 1.5 s scene 1 has 6 words: the floor
        sete = video_html(a=(">Acaba às&nbsp;7h.<", ">Acaba às&nbsp;7h hoje.<"))
        self.assertEqual(falhas(self.rodar(sete)), ["palavras_cena"])

    def test_fonte_minima(self):
        classe = video_html(a=("#s2_apoio { top: 700px; font-size: 52px;", "#s2_apoio { top: 700px;"),
                            b=(".clip { position: absolute; left: 90px; }",
                               ".clip { position: absolute; left: 90px; font-size: 52px; }"))
        self.assertEqual(check(self.rodar(classe), "fonte_minima")["details"],
                         ["s2_apoio sem font-size em px na própria regra"])
        pequeno = video_html(a=("#s3_titulo { top: 600px; font-size: 110px;", "#s3_titulo { top: 600px; font-size: 90px;"))
        self.assertEqual(falhas(self.rodar(pequeno)), ["fonte_minima"])

    def test_cores_marca(self):
        self.assertEqual(falhas(self.rodar(video_html(a=("--accent: #5A3320;", "--accent: #000000;")))), ["cores_marca"])

    def test_recurso_visual(self):
        sem3 = video_html(a=('<div id="s3_forma" class="clip" data-start="4.375" data-duration="2.25"></div>', ""))
        self.assertEqual(check(self.rodar(sem3), "recurso_visual")["details"][0][:7], "cena 3 ")
        reto = video_html(a=("background: var(--primary); transform: rotate(-6deg); }", "background: var(--primary); }"))
        self.assertEqual(falhas(self.rodar(reto)), ["recurso_visual"])  # a plain band is a background
        sem4 = video_html(a=('<svg id="s4_icone"', '<svg id="s4_nada"'))  # an svg with no size
        self.assertEqual(falhas(self.rodar(sem4)), ["recurso_visual"])
        sem2 = video_html(a=('<div id="s2_titulo"', '<div id="s2_titulo"'))  # scene 2 is not a key scene
        self.assertEqual(falhas(self.rodar(sem2)), [])
        deco = video_html(a=('<div id="s3_forma" class="clip" data-start="4.375" data-duration="2.25"></div>',
                             '<div id="deco1" class="clip" data-start="0" data-duration="10"></div>'),
                          b=("#s3_forma {", "#deco1, #s3_forma {"))
        self.assertEqual(falhas(self.rodar(deco)), [])  # a persistent shape counts for every scene
        numero = video_html(a=("#s3_titulo { top: 600px; font-size: 110px;", "#s3_titulo { top: 600px; font-size: 300px;"),
                            b=('<div id="s3_forma" class="clip" data-start="4.375" data-duration="2.25"></div>', ""))
        self.assertEqual(falhas(self.rodar(numero)), [])

    def test_legibilidade(self):
        corta = video_html(a=("@keyframes sobe { 0% { opacity: 0;", "@keyframes sobe { 0% { clip-path: inset(100% 0 0 0); opacity: 0;"),
                           b=("#s2_titulo { top: 500px; font-size: 104px;", "#s2_titulo { top: 500px; line-height: 1; font-size: 104px;"))
        self.assertEqual(check(self.rodar(corta), "legibilidade")["details"][0][:10], "s2_titulo ")
        folga = corta.replace("line-height: 1; font-size: 104px;", "line-height: 1.05; padding: .12em 0 .2em; font-size: 104px;")
        self.assertEqual(falhas(self.rodar(folga)), [])
        sem = video_html(a=("font-size: 48px;\n  text-wrap: balance; }", "font-size: 48px; }"))
        self.assertEqual(falhas(self.rodar(sem)), ["legibilidade"])

    def test_transicao_que_cobre_tudo(self):
        longa = video_html(a=("@keyframes painel { 0%, 34% { transform: translateX(-100%); } 50% { transform: none; }\n  66%,",
                              "@keyframes painel { 0% { transform: translateX(-100%); } 20%, 80% { transform: none; }\n  "))
        detalhes = check(self.rodar(longa), "transicoes")["details"]
        self.assertEqual(len(detalhes), 2)  # tr1 and tr3
        self.assertIn("tr1 cobre a tela inteira de uma cor por 0.36 s", detalhes[0])
        for iris, ok in (("40%, 60% { clip-path: circle(80% at 50% 50%); }", True),  # 0.12 s
                         ("20%, 80% { clip-path: circle(45% at 85% 15%); }", True),  # never all of it
                         ("20%, 80% { clip-path: circle(71% at 50% 50%); }", False)):
            html = video_html(a=("50% { clip-path: circle(80% at 50% 50%); }", iris),  # a plain 0-x-100 iris
                              b=("@keyframes iris { 0%, 34% {", "@keyframes iris { 0% {"),
                              c=("66%, 100% { clip-path: circle(0%", "100% { clip-path: circle(0%"))
            self.assertEqual(check(self.rodar(html), "transicoes")["ok"], ok, iris)

    def test_titulo_do_video_quebra_por_sentido(self):
        duas = video_html(a=('data-duration="1.875">Sai às&nbsp;6h10.<', 'data-duration="1.875">Sai cedo. Acaba às&nbsp;7h.<'),
                          b=('data-duration="1.875">Acaba às&nbsp;7h.<', 'data-duration="1.875">Corra.<'))
        self.assertEqual(falhas(self.rodar(duas)), ["legibilidade"])
        solta = video_html(a=(">Reserve o&nbsp;seu pão<", ">Reserve o seu pão<"))
        self.assertIn("'o' pode ficar sozinha", check(self.rodar(solta), "legibilidade")["details"][0])

    def test_marca_e_prazo_no_fim(self):
        sem = video_html(a=('<div id="s4_marca" class="clip" data-start="6.625" data-duration="3.375">Casa Exemplo</div>', ""))
        self.assertEqual(falhas(self.rodar(sem)), ["marca"])
        projeto(self.tmp, entrada=ENTRADA + "Reserva só até sábado.\n")
        self.assertEqual(falhas(self.rodar()), ["cta_final"])
        prazo = video_html(a=('data-duration="3.375">Sai às 6h10</div>', 'data-duration="3.375">até sábado</div>'))
        self.assertEqual(falhas(self.rodar(prazo)), [])

    def test_contato_como_escrito(self):
        for contato, ok in (("WhatsApp no link na bio", True), ("pelo WhatsApp", True), ("(11) 4002 8922", True),
                            ("Telegram (11) 4002-8922", False), ("@casaexemplo", False), ("WhatsApp 4002-0000", False)):
            html = video_html(a=(">link na bio<", ">%s<" % contato))
            self.assertEqual(check(self.rodar(html), "cta_final")["ok"], ok, contato)
        os.remove(os.path.join(self.trabalho, "entrada.md"))
        self.assertEqual(falhas(self.rodar()), ["cta_final", "numeros"])  # no briefing file: loud, never silent

    def test_cta_final(self):
        # the rounded `_selo` with its own background is the stamp recipe: it passes in the green source
        inventado = video_html(a=(">link na bio<", ">(11) 99999-0000<"))
        self.assertEqual(falhas(self.rodar(inventado)), ["cta_final", "numeros"])
        escrito = video_html(a=(">link na bio<", ">WhatsApp (11) 4002-8922<"))
        self.assertEqual(falhas(self.rodar(escrito)), [])
        pilula = video_html(a=("#s4_contato { top: 800px;", "#s4_contato { border-radius: 40px; top: 800px;"))
        self.assertEqual(falhas(self.rodar(pilula)), ["cta_final"])
        fundo = video_html(a=("#s4_titulo { top: 500px;", "#s4_titulo { background: var(--primary); top: 500px;"))
        self.assertEqual(falhas(self.rodar(fundo)), ["cta_final"])
        sem = video_html(a=('<div id="s4_contato" class="clip" data-start="6.625" data-duration="3.375">link na bio</div>',
                            ""))
        self.assertEqual(falhas(self.rodar(sem)), ["cta_final"])

    def test_sequencia_layout(self):
        repetido = video_html(a=('class="clip l-cheia"', 'class="clip l-base"'))
        self.assertEqual(falhas(self.rodar(repetido)), ["sequencia_layout"])

    def test_transicoes(self):
        mesma = video_html(a=("#tr2 { animation: iris", "#tr2 { animation: painel"))
        self.assertEqual(falhas(self.rodar(mesma)), ["transicoes"])
        fora = video_html(a=('id="tr2" class="clip" data-start="4.075"', 'id="tr2" class="clip" data-start="3"'))
        self.assertEqual(falhas(self.rodar(fora)), ["folha_limpa", "transicoes"])  # off its cut and on the 0.25 s grid
        self.assertNotIn("transicoes", [c["name"] for c in self.rodar(mesma, engine="reserve")])
        self.assertEqual(falhas(self.rodar(mesma, engine="reserve")), [])

    def test_tiques_e_numeros(self):
        self.assertEqual(falhas(self.rodar(video_html(a=(">Fornadas pequenas<", ">Fornadas pequenas!<")))), ["tiques"])
        self.assertEqual(falhas(self.rodar(video_html(a=(">Fornadas pequenas<", ">Fornadas de&nbsp;30<")))), ["numeros"])


if __name__ == "__main__":
    unittest.main()
