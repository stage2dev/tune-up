"""The composition kit (scripts/montar.py, kit_*.py): from `peca.json` + `heroi.svg` to an index.html that passes
the attention QA, for the post and the reel; the hero file is checked, slots too long are refused, the result
is the same on every run. No Chrome, no network. Sizes come from the machine's fonts (or the average letter)."""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
EXEMPLO = os.path.join(STUDIO, "exemplos", "forno-miudo")
HEROIS = os.path.join(STUDIO, "kit", "herois")
sys.path.insert(0, os.path.join(STUDIO, "scripts"))

import kit_base as kb  # noqa: E402
import kit_medida  # noqa: E402
import montar  # noqa: E402
import qa_atencao  # noqa: E402
import qa_script  # noqa: E402


def falhas(checks):
    return [(c["name"], c["details"]) for c in checks if not c["ok"]]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="kit-")
        marca = os.path.join(self.tmp, ".tune-up", "estudio", "marca")
        os.makedirs(os.path.join(marca, "assets"))
        with open(os.path.join(EXEMPLO, "gabarito.json"), encoding="utf-8") as f:
            g = json.load(f)
        campos = {"cores.%s" % k: {"valor": v} for k, v in g["colors"].items()}
        campos.update({"nome": {"valor": g["name"]}, "fontes.heading": {"valor": g["fonts"]["heading"]},
                       "fontes.body": {"valor": g["fonts"]["body"]},
                       "logo": {"valor": ".tune-up/estudio/marca/assets/logo.svg"}})
        with open(os.path.join(marca, "marca.json"), "w", encoding="utf-8") as f:
            json.dump({"campos": campos}, f, ensure_ascii=False)
        shutil.copy(os.path.join(EXEMPLO, "logo.svg"), os.path.join(marca, "assets", "logo.svg"))
        self.trabalho = os.path.join(self.tmp, ".tune-up", "estudio", "trabalhos", "x")
        os.makedirs(self.trabalho)
        shutil.copy(os.path.join(EXEMPLO, "briefing.md"), os.path.join(self.trabalho, "entrada.md"))
        shutil.copy(os.path.join(EXEMPLO, "estrategia.md"), os.path.join(self.trabalho, "estrategia.md"))
        shutil.copy(os.path.join(EXEMPLO, "heroi.svg"), os.path.join(self.trabalho, "heroi.svg"))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def peca(self, origem, **trocas):
        with open(os.path.join(EXEMPLO, origem, "peca.json"), encoding="utf-8") as f:
            d = json.load(f)
        d.update(trocas)
        caminho = os.path.join(self.trabalho, "peca.json")
        with open(caminho, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False)
        return caminho

    def montar(self, *args, heroi=None):
        """(exit code, stdout, stderr) of montar.py run for the working folder."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = montar.main(list(args) + ["--trabalho", self.trabalho, "--heroi",
                                             heroi or os.path.join(self.trabalho, "heroi.svg")])
        return code, out.getvalue(), err.getvalue()

    def ler(self, *partes):
        with open(os.path.join(self.trabalho, *partes), encoding="utf-8") as f:
            return f.read()


class Post(Base):
    def fonte(self, **trocas):
        code, out, err = self.montar("--tipo", "post", "--peca", self.peca("post-4x5", **trocas), "--out",
                                     os.path.join(self.trabalho, "q1", "fonte"))
        self.assertEqual((code, err), (0, ""))
        return os.path.join(self.trabalho, "q1", "fonte"), out

    def test_post_do_exemplo_passa_na_atencao(self):
        fonte, out = self.fonte()
        self.assertEqual(falhas(qa_atencao.checar_quadro(fonte)), [])
        self.assertIn("titulo:", out)
        html = self.ler("q1", "fonte", "index.html")
        self.assertEqual(html.count("<h1>"), 1)
        self.assertIn('id="oferta"', html)
        self.assertIn('id="cta"', html)
        self.assertTrue(os.path.isfile(os.path.join(fonte, "assets", "logo.svg")))  # the logo is copied by the kit
        self.assertNotIn("<script", html)
        self.assertNotRegex(html, r"https?:")

    def test_cada_composicao_campo_e_lado_passa(self):
        for comp in ("oferta", "palco", "numero"):
            for campo, lado in (("primary", "direita"), ("text", "esquerda"), ("bg", "direita")):
                extra = {"titulo": "6h", "realce": "", "apoio": "sai a primeira fornada"} if comp == "numero" else {}
                fonte, _ = self.fonte(composicao=comp, variante={"campo": campo, "lado": lado}, **extra)
                self.assertEqual(falhas(qa_atencao.checar_quadro(fonte)), [], (comp, campo, lado))

    def test_formato_quadrado_e_quadros_de_carrossel(self):
        code, _, err = self.montar("--tipo", "post", "--peca", self.peca("post-4x5"), "--formato", "1:1", "--out",
                                   os.path.join(self.trabalho, "q1", "fonte"))
        self.assertEqual((code, err), (0, ""))
        self.assertIn('data-height="1080"', self.ler("q1", "fonte", "index.html"))
        code, _, _ = self.montar("--tipo", "post", "--peca", self.peca("post-4x5"), "--quadro", "capa", "--out",
                                 os.path.join(self.trabalho, "q1", "fonte"))
        capa = self.ler("q1", "fonte", "index.html")
        self.assertIn("arraste", capa)       # the swipe cue
        self.assertNotIn('id="cta"', capa)   # only the last frame asks for the action
        self.assertNotIn('id="oferta"', capa)

    def test_preco_com_cifrao_pequeno_e_numero_gigante(self):
        fonte, out = self.fonte(oferta={"nome": "Cesta da manhã", "valor": "R$ 24", "prova": "massa de 24 horas"})
        html = self.ler("q1", "fonte", "index.html")
        self.assertIn('<span class="rs">R$</span>24', html)
        px = int(re.search(r"oferta: (\d+) px", out).group(1))
        self.assertGreaterEqual(px, 160)  # the price is a real second level
        self.assertEqual(falhas(qa_atencao.checar_quadro(fonte)), [])

    def test_slot_longo_ou_faltando_e_recusado_com_o_motivo(self):
        for trocas, motivo in (({"titulo": "x" * 41}, "titulo com 41 caracteres"), ({"titulo": ""}, "falta o texto"),
                               ({"titulo": "Compre já!"}, "'!'"), ({"composicao": "mural"}, "não existe no post"),
                               ({"realce": "outra coisa"}, "não está dentro do titulo"),
                               ({"cta": {"chamada": "Reserve", "condicao": "hoje", "canal": "fax"}}, "canal 'fax'")):
            code, _, err = self.montar("--tipo", "post", "--peca", self.peca("post-4x5", **trocas), "--out",
                                       os.path.join(self.trabalho, "q1", "fonte"))
            self.assertEqual(code, 1, trocas)
            self.assertIn(motivo, err)


class Video(Base):
    def fonte(self, duracao=10, **trocas):
        code, out, err = self.montar("--tipo", "video", "--peca", self.peca("video-9x16", **trocas), "--duracao",
                                     str(duracao), "--out", os.path.join(self.trabalho, "fonte"))
        self.assertEqual((code, err), (0, ""))
        return os.path.join(self.trabalho, "fonte"), out

    def test_reel_do_exemplo_passa_na_atencao(self):
        fonte, out = self.fonte()
        self.assertEqual(falhas(qa_atencao.checar_video(fonte, 10, "hyperframes")), [])
        self.assertIn("cartão final", out)
        html = self.ler("fonte", "index.html")
        self.assertEqual(html.count("<script"), 1)
        self.assertEqual(qa_script.checar(html), [])  # the engine pasted whole + only recipe calls
        self.assertNotIn("gsap", html.lower())

    def test_cada_tema_lado_e_palco_passa(self):
        for tema, lado, palco, textura in (("noite", "direita", "disco", "pontos"),
                                           ("tinta", "esquerda", "corte", "listras"),
                                           ("dia", "direita", "corte", "nenhuma"), ("dia", "esquerda", "disco", "pontos")):
            fonte, _ = self.fonte(variante={"tema": tema, "lado": lado, "palco": palco, "textura": textura})
            self.assertEqual(falhas(qa_atencao.checar_video(fonte, 10, "hyperframes")), [], (tema, lado, palco))

    def test_reel_de_15_s_ganha_a_cena_de_lista(self):
        fonte, _ = self.fonte(15, lista={"titulo": "Na véspera", "itens": ["Massa feita", "Fermenta 24 horas"]})
        self.assertEqual(falhas(qa_atencao.checar_video(fonte, 15, "hyperframes")), [])
        self.assertIn('id="s3_item2"', self.ler("fonte", "index.html"))
        code, _, err = self.montar("--tipo", "video", "--peca", self.peca("video-9x16"), "--duracao", "15", "--out",
                                   os.path.join(self.trabalho, "fonte"))
        self.assertEqual(code, 1)
        self.assertIn("lista", err)

    def test_cortes_fora_da_grade_e_cena_inteira_no_corte(self):
        self.fonte()
        html = self.ler("fonte", "index.html")
        cortes = sorted({float(s) for s in re.findall(r'id="s[2-9]_titulo"[^>]*data-start="([\d.]+)"', html)})
        self.assertEqual(cortes, [1.875, 4.375, 6.875])
        for corte in cortes:  # 0.1 s or more away from every multiple of 0.25 s
            self.assertGreaterEqual(min(corte % 0.25, 0.25 - corte % 0.25), 0.1)
        cena = html.split("M.pronto", 1)[0].rsplit("})();", 1)[1]
        self.assertNotRegex(cena, r"M\.mascara\(")                       # no text behind a mask
        self.assertNotRegex(cena, r'M\.entra\("s\d_titulo"')              # titles are whole at the cut
        self.assertNotRegex(cena, r"M\.contador\(")                       # no number counted up
        self.assertRegex(cena, r'M\.trilha\("heroi_quadro", "transform"')  # one hero, reframed at every cut
        self.assertRegex(cena, r'M\.pulso\("s4_pulso"')                   # the end card keeps moving

    def test_palavras_por_cena_e_gancho_sao_cobrados_ao_montar(self):
        casos = (({"gancho": {"titulo": "O pão da manhã acabou muito cedo", "destaque": "hoje?"}},
                  "gancho com 8 palavras"),
                 ({"oferta": {"nome": "Primeira fornada do dia", "valor": "6h", "prova": "massa de 24 horas feita"}},
                  "oferta (nome + valor + prova) com 10 palavras"),
                 ({"final": {"titulo": "Reserve", "contato": "", "canal": "whatsapp"}}, "falta o texto de final.contato"))
        for trocas, motivo in casos:
            code, _, err = self.montar("--tipo", "video", "--peca", self.peca("video-9x16", **trocas), "--out",
                                       os.path.join(self.trabalho, "fonte"))
            self.assertEqual(code, 1, trocas)
            self.assertIn(motivo, err)

    def test_mesma_entrada_mesmo_html(self):
        self.fonte()
        primeiro = self.ler("fonte", "index.html")
        self.fonte()
        self.assertEqual(primeiro, self.ler("fonte", "index.html"))


HEROI_OK = """<svg viewBox="0 0 1000 1000"><g id="h_corpo">%s</g>
<g transform="translate(500 300)"><g id="h_depois1"><circle class="a" r="60"/></g></g></svg>""" % "".join(
    '<rect class="p" x="%d" y="400" width="40" height="500"/>' % (100 + 60 * i) for i in range(12))


class Heroi(Base):
    def checar(self, texto):
        caminho = os.path.join(self.trabalho, "h.svg")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(texto)
        return kb.heroi(caminho)

    def test_exemplos_do_kit_sao_validos(self):
        nomes = sorted(n for n in os.listdir(HEROIS) if n.endswith(".svg"))
        self.assertGreaterEqual(len(nomes), 4)  # worked examples from different niches
        for nome in nomes:
            _, ids = kb.heroi(os.path.join(HEROIS, nome))
            self.assertIn("h_corpo", ids, nome)
            self.assertTrue(any(i.startswith(("h_depois", "h_traco")) for i in ids), nome)  # each one transforms
            with open(os.path.join(HEROIS, nome), encoding="utf-8") as f:
                self.assertNotRegex(f.read(), r"#[0-9a-fA-F]{3,8}\b|https?:")  # brand colors by class, no network

    def test_heroi_valido(self):
        corpo, ids = self.checar(HEROI_OK)
        self.assertEqual(ids, {"h_corpo", "h_depois1"})
        self.assertNotIn("<svg", corpo)

    def test_cada_coisa_proibida_no_heroi(self):
        casos = ((HEROI_OK.replace("<g id=\"h_corpo\">", "<g id=\"h_corpo\"><script>fetch('x')</script>"),
                  "só formas básicas"),
                 (HEROI_OK.replace('class="a"', 'fill="#ff0000"'), "cor só por classe"),
                 (HEROI_OK.replace('class="a"', 'style="fill: red"'), "atributo style não é permitido"),
                 (HEROI_OK.replace('class="a"', 'class="vermelho"'), "classe vermelho não existe"),
                 (HEROI_OK.replace('class="a"', 'class="a" onclick="x()"'), "só formas básicas"),
                 (HEROI_OK.replace("<circle", '<image href="foto.png"/><circle'), "só formas básicas"),
                 (HEROI_OK.replace("<circle", "<text>Oi</text><circle"), "só formas básicas"),
                 (HEROI_OK.replace('id="h_corpo"', 'id="corpo"'), "ids começam com h_"),
                 (HEROI_OK.replace('id="h_corpo"', 'id="h_base"'), 'falta o grupo <g id="h_corpo">'),
                 (HEROI_OK.replace('viewBox="0 0 1000 1000"', 'viewBox="0 0 100 100"'), "viewBox"),
                 ('<svg viewBox="0 0 1000 1000"><g id="h_corpo"><circle class="p" r="9"/></g></svg>', "é pictograma"))
        for texto, motivo in casos:
            with self.assertRaises(kb.Erro) as cm:
                self.checar(texto)
            self.assertIn(motivo, str(cm.exception))

    def test_reel_exige_a_transformacao(self):
        sem = HEROI_OK.split('<g transform', 1)[0] + "</svg>"
        caminho = os.path.join(self.trabalho, "h.svg")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(sem)
        code, _, err = self.montar("--tipo", "video", "--peca", self.peca("video-9x16"), "--out",
                                   os.path.join(self.trabalho, "fonte"), heroi=caminho)
        self.assertEqual(code, 1)
        self.assertIn("sem transformação", err)

    def test_foto_pedida_sem_arquivo_e_recusada(self):
        code, _, err = self.montar("--tipo", "post", "--peca", self.peca("post-4x5", heroi="foto"), "--out",
                                   os.path.join(self.trabalho, "q1", "fonte"))
        self.assertEqual(code, 1)
        self.assertIn("fotos.py", err)


class Medida(unittest.TestCase):
    def test_fonte_desconhecida_usa_a_letra_media(self):
        self.assertIsNone(kit_medida.face(["Fonte Que Nao Existe 2031"]))
        self.assertAlmostEqual(kit_medida.largura_em("abcd"), 4 * kit_medida.MEDIA_EM)
        self.assertLess(kit_medida.largura_em("il.."), kit_medida.largura_em("abcd"))

    def test_caber_enche_a_coluna_sem_passar(self):
        px, linhas, largura = kb.caber("Vai pegar estrada em dezembro?", None, 900, 400, 250, 88)
        self.assertLessEqual(largura, 900.5)
        self.assertGreaterEqual(largura, 700)       # the widest line fills the column
        self.assertIn(len(linhas), (2, 3))
        self.assertEqual(" ".join(linhas).replace(" ", " "), "Vai pegar estrada em dezembro?")
        curto = kb.caber("Oi", None, 900, 400, 250, 88)
        self.assertEqual(curto[0], 250)             # capped by the biggest size, never stretched

    def test_palavra_curta_e_cifrao_nunca_ficam_no_fim_da_linha(self):
        self.assertEqual(kb.colar("O pão de amanhã"), "O pão de amanhã")
        self.assertEqual(kb.colar("por R$ 89"), "por R$ 89")
        self.assertEqual(kb.colar("(19) 99999-0000"), "(19) 99999-0000")
        for linha in kb.quebrar("Reserve o pão de amanhã", None, 2)[1]:
            self.assertNotRegex(linha, r"(?:^| )(?:o|de)$")

    def test_preco(self):
        px, marcacao, largura = kb.preco("R$ 1.290,90", None, 400, 300, 300)
        self.assertEqual(marcacao, '<span class="rs">R$</span>1.290<span class="ct">,90</span>')
        self.assertLessEqual(largura, 400.5)
        self.assertIsNone(kb.preco("14 dias grátis", None, 400, 300, 300))  # not a price: set as plain text

    def test_escolha_estavel_e_variada(self):
        opcoes = ("noite", "tinta", "dia")
        self.assertEqual(kb.escolha("Forno Miúdo", opcoes), kb.escolha("Forno Miúdo", opcoes))
        self.assertEqual(kb.escolha("Forno Miúdo", opcoes, "dia"), "dia")
        nomes = ["Forno Miúdo", "Auto Center", "Focinho Feliz", "Clínica Sorriso", "Loja Linho", "Studio Pilates"]
        self.assertGreaterEqual(len({kb.escolha(n, opcoes) for n in nomes}), 2)  # two businesses differ by default


if __name__ == "__main__":
    unittest.main()
