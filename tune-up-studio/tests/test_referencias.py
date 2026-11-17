"""Guards for referencias/*.md: size, forbidden words, tics block, seek-safe CSS and visual-device recipes."""
import os
import re
import shutil
import sys
import tempfile
import unittest

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(STUDIO, "referencias")
sys.path.insert(0, os.path.join(STUDIO, "scripts"))
ARQUIVOS = ("ganchos.md", "arquetipos-post.md", "padroes-cena.md", "ritmo.md",
            "legenda.md", "checklist-atencao.md", "recursos-visuais.md", "motion-js.md",
            "kit-post.md", "kit-video.md", "heroi.md")
LEITURA = {
    # round 6: post and video build from the kit (kit-*.md + heroi.md); the layout, device and motion recipes
    # (padroes-cena.md, recursos-visuais.md, motion-js.md) document the engine and the ad image, they are not read.
    "post": ("ganchos.md", "arquetipos-post.md", "legenda.md", "checklist-atencao.md", "kit-post.md", "heroi.md"),
    "video": ("ganchos.md", "ritmo.md", "checklist-atencao.md", "legenda.md", "kit-video.md", "heroi.md"),
    "anuncio": ("ganchos.md", "arquetipos-post.md", "checklist-atencao.md", "recursos-visuais.md"),
}
PROIBIDOS = ("gsap", "http", "<script", "zapscaler", "autoagendai")
TIQUES = ["—", "nao e so", "nao e apenas", "mais do que um", "diga adeus", "proximo nivel",
          "descubra o poder", "no mundo corrido", "seja voce", "experiencia unica",
          "o resultado?", "o melhor:", "pare de rolar", "venha conhecer",
          "qualidade e tradicao", "imagine so"]
LAYOUTS_POST = ("l-titulo", "l-numero", "l-foto", "l-lista", "l-antes-depois", "l-citacao",
                "l-oferta", "l-cheia")
LAYOUTS_VIDEO = ("l-topo", "l-base", "l-cheia", "l-numero", "l-faixa", "l-foto", "l-lista")
NICHOS = ("padaria", "barbearia", "clínica odontológica", "pet shop", "oficina",
          "escola de idiomas", "loja de roupas", "contador")
TIQUES_RE = re.compile(r"```tiques\n(.*?)```", re.S)
CSS_RE = re.compile(r"```css\n(.*?)```", re.S)


def ler(nome):
    with open(os.path.join(REF, nome), encoding="utf-8") as f:
        return f.read()


def keyframes(css):
    """{name: [(selectors, declarations)]} with brace matching (bodies hold nested braces)."""
    out = {}
    for m in re.finditer(r"@keyframes\s+([\w-]+)\s*\{", css):
        i, nivel = m.end(), 1
        while nivel:
            nivel += {"{": 1, "}": -1}.get(css[i], 0)
            i += 1
        corpo = css[m.end():i - 1]
        out[m.group(1)] = [([s.strip() for s in sel.split(",")], dec)
                           for sel, dec in re.findall(r"([^{}]+)\{([^{}]*)\}", corpo)]
    return out


def visivel(decl):
    """True when a keyframe step leaves the element readable."""
    d = re.sub(r"\s+", " ", decl.lower())
    if re.search(r"opacity: ?0(\.0*)?( ?;|$)", d.strip()):
        return False
    if "visibility: hidden" in d or "display: none" in d:
        return False
    for clip in re.findall(r"clip-path: ?([^;]+)", d):
        clip = clip.strip()
        m = re.fullmatch(r"inset\((.*)\)", clip)
        if clip != "none" and not (m and all(re.fullmatch(r"0[a-z%]*", v)
                                               for v in m.group(1).split())):
            return False
    return True


class ReferenciasTest(unittest.TestCase):
    def test_seis_arquivos_curtos_e_quem_le(self):
        for nome in ARQUIVOS:
            linhas = ler(nome).splitlines()
            self.assertLess(len(linhas), 150, nome)
            self.assertTrue(linhas[0].startswith("# "), nome)
            self.assertTrue(linhas[2].startswith("Read by"), nome)

    def test_soma_por_skill(self):
        # 460 since round 5 (was 450): the tested offer stack and the "ground becomes the CTA band" recipe joined
        # recursos-visuais.md, read by the three skills; the video set was already at 445 (CHANGELOG 2.8.x).
        for skill, nomes in LEITURA.items():
            total = sum(len(ler(n).splitlines()) for n in nomes)
            self.assertLessEqual(total, 460, skill)

    def test_leitura_bate_com_o_skill(self):
        """The reading list above is exactly the set of referencias each SKILL.md cites."""
        for skill, nomes in LEITURA.items():
            with open(os.path.join(STUDIO, "skills", skill, "SKILL.md"), encoding="utf-8") as f:
                texto = f.read()
            citados = {n for n in ARQUIVOS if n in texto}
            self.assertEqual(citados, set(nomes), skill)

    def test_sem_palavras_proibidas(self):
        for nome in ARQUIVOS:
            texto = ler(nome).lower()
            for p in PROIBIDOS:
                self.assertNotIn(p, texto, f"{nome}: {p}")

    def test_bloco_tiques_exato(self):
        blocos = TIQUES_RE.findall(ler("checklist-atencao.md"))
        self.assertEqual(len(blocos), 1)
        self.assertEqual([l for l in blocos[0].splitlines() if l.strip()], TIQUES)
        for nome in ARQUIVOS:
            if nome != "checklist-atencao.md":
                self.assertEqual(TIQUES_RE.findall(ler(nome)), [], nome)

    def test_travessao_so_no_bloco(self):
        for nome in ARQUIVOS:
            self.assertNotIn("—", TIQUES_RE.sub("", ler(nome)), nome)

    def test_css_seek_safe(self):
        # Since the JS engine (round 4) the only CSS animation of the reel is the transition: the base and the
        # transition blocks of padroes-cena.md plus the helper block of motion-js.md.
        blocos = CSS_RE.findall(ler("padroes-cena.md")) + CSS_RE.findall(ler("motion-js.md"))
        self.assertGreaterEqual(len(blocos), 3)
        for css in blocos:
            for proibido in ("rgba(", "color-mix(", "animation-delay", "gsap"):
                self.assertNotIn(proibido, css)
            self.assertNotRegex(css, r"(?:left|right|top|bottom): ?-")  # a box resting off canvas fails the check
            for anim in re.findall(r"animation:\s*([^;]+);", css):
                self.assertRegex(anim, r"^[\w-]+ [\d.]+s .+ 0s 1 both$", anim)

    def test_receitas_js_batem_com_o_motor_e_o_qa(self):
        """Every recipe the table of motion-js.md names exists in the engine and in the QA's positive list; the
        hook-safe ones the file names for scene 1 are exactly the QA's (the cover is readable in frame 0)."""
        import qa_script
        texto, motor = ler("motion-js.md"), ler("motor-motion.js")
        tabela = texto.split("## Recipes", 1)[1].split("\n## ", 1)[0]
        nomes = set(re.findall(r"`M\.(\w+)\(", tabela))
        self.assertGreaterEqual(len(nomes), 10)
        for n in nomes:
            self.assertRegex(motor, r"\b%s: function" % n, n)
            self.assertIn(n, qa_script.RECEITAS, n)
        gancho = texto.split("Scene 1 is readable at frame 0", 1)[1].split("\n", 1)[0]
        self.assertEqual(set(re.findall(r"`(\w+)`", gancho)) - {"palavras"}, qa_script.GANCHO_OK)

    def test_motor_sem_relogio_rede_ou_acaso(self):
        motor = ler("motor-motion.js")
        for proibido in ("Date", "performance", "random", "setTimeout", "setInterval", "requestAnimationFrame",
                         "fetch", "XMLHttpRequest", "import", "eval", "Function(", "innerHTML", "http", ".animate(",
                         "localStorage", "cookie", "gsap"):
            self.assertNotIn(proibido, motor)
        self.assertIn("window.__hfAnime", motor)  # the seek hook HyperFrames documents for any seekable object

    def test_visivel_reprova_o_que_esconde(self):
        self.assertFalse(visivel("opacity: 0; transform: scale(.6);"))
        self.assertFalse(visivel("clip-path: inset(100% 0 0 0);"))
        self.assertTrue(visivel("clip-path: inset(0 0px 0% 0); opacity: 1;"))
        self.assertTrue(visivel("transform: scale(1.06);"))

    def test_layouts_nos_arquivos_certos(self):
        post, video = ler("arquetipos-post.md"), ler("padroes-cena.md")
        for l in LAYOUTS_POST:
            self.assertIn(f"`{l}`", post, l)
        for l in LAYOUTS_VIDEO:
            self.assertIn(f"`{l}`", video, l)

    def test_nichos_variados(self):
        tudo = "\n".join(ler(n) for n in ARQUIVOS).lower()
        achados = [n for n in NICHOS if n in tudo]
        self.assertGreaterEqual(len(achados), 4, achados)

    def test_padroes_de_cena_validos(self):
        linhas = re.findall(r"^\| (10|15) \| `([\d.,]+)` \| ([\d., ]+) \| `([\d.,]+)` \| ([\d., ]+) \| ([\d., ]+) \|",
                            ler("ritmo.md"), re.M)
        self.assertEqual(len(linhas), 5)  # round 7: one more D10 row, the reel with a style scene
        for d, tempos, inicios, at, cortes, trs in linhas:
            d, t = int(d), [float(x) for x in tempos.split(",")]
            self.assertIn(len(t), {10: (4, 5), 15: (5, 6)}[d])
            self.assertAlmostEqual(sum(t), d, delta=0.05)
            self.assertLessEqual(t[0], 2.0)
            self.assertGreaterEqual(t[-1], 2.5)
            self.assertTrue(all(x >= 1.5 for x in t))
            acum = [sum(t[:i]) for i in range(len(t))]
            self.assertEqual([float(x) for x in inicios.split(",")], acum)
            meios = [0.0] + [a + x / 2 for a, x in zip(acum, t)]
            self.assertEqual([float(x) for x in at.split(",")], meios)
            self.assertEqual([float(x) for x in cortes.split(",")], acum[1:])
            self.assertEqual([float(x) for x in trs.split(",")],
                             [round(c - 0.22, 3) for c in acum[1:]])  # 0.44 s centered on the cut (round 5)
            for c in acum[1:]:  # round 6: cuts off the 0.25 s grid, so no sampled frame lands on a transition
                self.assertGreaterEqual(min(c % 0.25, 0.25 - c % 0.25), 0.1, c)

    def test_familias_citadas_existem_no_menu(self):
        """Every family the objective table and the short-briefing path name is a row of the opening menu."""
        texto = ler("ganchos.md")
        menu = texto.split("## Opening menu", 1)[1].split("\n## ", 1)[0]
        familias = set(re.findall(r"^\| ([A-Za-z' +/-]+?) \| `", menu, re.M))
        self.assertGreaterEqual(len(familias), 14)
        tabela = texto.split("## Objective -> families", 1)[1].split("\n\n", 1)[0]
        for linha in re.findall(r"^\| [a-zç ]+ \| ([^|]+) \|", tabela, re.M)[1:]:
            for f in linha.split(","):
                self.assertIn(f.strip(), familias, f)
        for f in re.findall(r"`([a-z' ]+)`", texto.split("## Short briefing", 1)[1].split("\n## ", 1)[0]):
            self.assertIn(f, familias)

    def test_uma_margem_so_no_post(self):
        arranjos = ler("arquetipos-post.md")
        self.assertIn("Margin **80 px**", arranjos)
        self.assertNotRegex(arranjos, r"\b(72|96) ?px\b|72/72")
        with open(os.path.join(STUDIO, "skills", "post", "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        self.assertIn("padding: 80px;", skill)
        self.assertNotIn("padding: 96px", skill)

    def test_receitas_de_recurso_visual_passam_no_qa(self):
        """Each recipe of recursos-visuais.md, alone in a post frame, is a device for qa_atencao (no false red)
        and the frame without it is red (the check is not trivially green)."""
        import qa_atencao
        import qa_css
        blocos = re.findall(r"^### ([^\n]+)\n```html\n(.*?)```", ler("recursos-visuais.md"), re.S | re.M)
        pedacos = [(nome, p) for nome, html in blocos for p in re.findall(r"(.*?<style>.*?</style>)", html, re.S)]
        self.assertGreaterEqual(len(blocos), 8)
        self.assertGreaterEqual(len(pedacos), 10)
        tmp = tempfile.mkdtemp()
        try:
            for nome, pedaco in pedacos:
                corpo = re.sub(r"<style>.*?</style>", "", pedaco, flags=re.S)
                css = "".join(re.findall(r"<style>(.*?)</style>", pedaco, re.S))
                self.assertNotRegex(css, r"#[0-9a-fA-F]{3,8}\b|rgba\(|color-mix", nome)
                self.assertNotRegex(css, r"(?:left|right|top|bottom): ?-", nome)  # HyperFrames: nothing off canvas
                h1 = "" if "<h1" in corpo else "<h1>Sentado o dia todo?</h1>"
                with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
                    f.write("<style>#root { position: relative; width: 1080px; height: 1350px; font-size: 40px; }"
                            "h1 { font-size: 120px; } %s</style><div id=\"root\">%s%s</div>" % (css, h1, corpo))
                check = qa_atencao.check_recurso_quadro(qa_css.ler_fonte(tmp))
                self.assertTrue(check["ok"], (nome, check["details"]))
            with open(os.path.join(tmp, "index.html"), "w", encoding="utf-8") as f:
                f.write('<div id="root" style="width:1080px;height:1350px"><h1>Sentado o dia todo?</h1></div>')
            self.assertFalse(qa_atencao.check_recurso_quadro(qa_css.ler_fonte(tmp))["ok"])
        finally:
            shutil.rmtree(tmp)

    def test_kit_cita_o_que_o_codigo_tem(self):
        """Every composition, scene, slot, variant and hero id the kit references name exists in the code, and
        the scene times of kit-video.md are the kit's."""
        import kit_base
        import kit_palco
        import kit_post
        import kit_video
        post, video, heroi = ler("kit-post.md"), ler("kit-video.md"), ler("heroi.md")
        for nome in kit_post.COMPOSICOES + kit_post.QUADROS:
            self.assertIn("`%s`" % nome, post, nome)
        for nome in tuple(kit_video.CENAS) + kit_palco.TEMAS + ("disco", "corte", "faixa", "cortina", "sobe"):
            self.assertIn("`%s`" % nome, video, nome)
        for canal in kit_base.CANAIS:
            self.assertIn("`%s`" % canal, post, canal)
            self.assertIn("`%s`" % canal, video, canal)
        for tabela in (kit_video.TEMPOS, kit_video.TEMPOS_ESTILO):
            for d, tempos in tabela.items():
                lista = ",".join(("%.4f" % t).rstrip("0").rstrip(".") for t in tempos)
                self.assertRegex(video, r"\| %d \| [^|]+ \| `%s` \|" % (d, re.escape(lista)))
                self.assertIn("`%s`" % lista, ler("ritmo.md"))
        for prefixo in ("h_corpo", "h_gira", "h_balanca", "h_antes", "h_depois", "h_traco"):
            self.assertIn("`%s" % prefixo, heroi, prefixo)
        for classe in ("p", "a", "t", "s", "b", "lp", "la", "lt", "ls", "lb"):
            self.assertIn("`%s`" % classe, heroi, classe)
            self.assertIn(classe, kit_base.HEROI_CLASSES)
        exemplos = [a for a in re.findall(r"`([\w-]+\.svg)`", heroi) if a != "heroi.svg"]
        self.assertGreaterEqual(len(exemplos), 4)  # worked examples from different niches
        for arquivo in exemplos:
            self.assertTrue(os.path.isfile(os.path.join(STUDIO, "kit", "herois", arquivo)), arquivo)

    def test_checklist_tem_12_itens(self):
        nota = ler("checklist-atencao.md").split("## Score", 1)[1].split("\n## ", 1)[0]
        itens = re.findall(r"^\| (\d+) \|", nota, re.M)
        self.assertEqual(itens, [str(i) for i in range(1, 13)])


if __name__ == "__main__":
    unittest.main()
