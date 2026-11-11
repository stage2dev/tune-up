"""Business photos in pieces: scripts/fotos.py copies them, qa_imagem.check_images accepts images only from
assets/, and a Google ad piece may be the photo with no text. Python 3.9, standard library only."""
import contextlib
import hashlib
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
import fotos  # noqa: E402
import qa_imagem  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60 + b"http://ns.adobe.com/xap/1.0/ fetch( gsap" + b"\xff\xd9"
PNG = qa_imagem.PNG_SIGNATURE + b"\x00" * 40


def escrever(caminho, dados):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb" if isinstance(dados, bytes) else "w") as f:
        f.write(dados)


def nome(dados, ext):
    return hashlib.sha256(dados).hexdigest()[:16] + "." + ext


class Fotos(unittest.TestCase):
    def setUp(self):
        self.raiz = tempfile.mkdtemp()
        self.marca = os.path.join(self.raiz, ".tune-up", "estudio", "marca")
        self.trab = os.path.join(self.raiz, ".tune-up", "dados", "trabalhos", "x1")
        os.makedirs(self.trab)
        outro = JPEG + b"2"
        self.nomes = [nome(JPEG, "jpg"), nome(outro, "jpg"), nome(PNG, "png")]
        for n, d in zip(self.nomes, (JPEG, outro, PNG)):
            escrever(os.path.join(self.marca, "fotos", n), d)
        escrever(os.path.join(self.marca, "assets", "logo.png"), PNG)
        self.gravar_marca([{"arquivo": "fotos/" + n, "principal": i == 0} for i, n in enumerate(self.nomes)])

    def tearDown(self):
        shutil.rmtree(self.raiz)

    def gravar_marca(self, lista, logo="assets/logo.png"):
        escrever(os.path.join(self.marca, "marca.json"), json.dumps({"campos": {}, "fotos": lista, "logo_copia": logo}))

    def rodar(self, *extra):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = fotos.main(["--trabalho", self.trab, "--para", "q1/fonte"] + list(extra))
        return code, out.getvalue().splitlines()

    def assets(self):
        pasta = os.path.join(self.trab, "q1", "fonte", "assets")
        return sorted(os.listdir(pasta)) if os.path.isdir(pasta) else []

    def test_copies_at_most_two_photos_main_first_and_logo_on_request(self):
        code, linhas = self.rodar("--logo")
        self.assertEqual(code, 0)
        self.assertEqual(linhas, ["assets/foto1.jpg principal", "assets/foto2.jpg foto", "assets/logo.png logo"])
        with open(os.path.join(self.trab, "q1", "fonte", "assets", "foto1.jpg"), "rb") as f:
            self.assertEqual(f.read(), JPEG)
        self.assertEqual(self.rodar("--quantas", "1")[0], 0)  # second run replaces, never fails
        self.assertEqual(self.assets(), ["foto1.jpg", "foto2.jpg", "logo.png"])

    def test_no_logo_without_flag_and_svg_logo_never_copied(self):
        self.gravar_marca([], logo="assets/logo.svg")
        self.assertEqual(self.rodar("--logo"), (0, ["sem fotos nem logo para copiar"]))
        self.assertEqual(self.assets(), [])

    def test_tampered_renamed_or_outside_photo_is_skipped(self):
        escrever(os.path.join(self.marca, "fotos", self.nomes[0]), JPEG + b"x")  # bytes no longer match the name
        self.gravar_marca([{"arquivo": "fotos/" + self.nomes[0]}, {"arquivo": "../segredo.jpg"},
                           {"arquivo": "fotos/" + self.nomes[2]}])
        code, linhas = self.rodar()
        self.assertEqual((code, linhas), (0, ["assets/foto1.png principal"]))

    def test_bad_destination_and_folder_outside_tune_up_refused(self):
        for para in ("../x", "/abs", "q1/../../x", "q-1"):
            out = io.StringIO()
            with contextlib.redirect_stderr(out), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(fotos.main(["--trabalho", self.trab, "--para", para]), 2, para)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(fotos.main(["--trabalho", self.raiz, "--para", "q1"]), 2)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "symlink")
    def test_link_in_destination_refused(self):
        fora = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, fora)
        os.makedirs(os.path.join(self.trab, "q1"))
        os.symlink(fora, os.path.join(self.trab, "q1", "fonte"))
        self.assertEqual(self.rodar()[0], 2)
        self.assertEqual(os.listdir(fora), [])


class CheckImages(unittest.TestCase):
    def setUp(self):
        self.fonte = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.fonte)

    def html(self, corpo, arquivos):
        escrever(os.path.join(self.fonte, "index.html"), "<html><body>%s</body></html>" % corpo)
        for rel, dados in arquivos.items():
            escrever(os.path.join(self.fonte, *rel.split("/")), dados)
        return qa_imagem.check_images(self.fonte)

    def test_photo_from_assets_passes_and_its_bytes_skip_the_text_lint(self):
        r = self.html('<img src="assets/foto1.jpg"><div style="background:url(assets/foto2.jpg)"></div>',
                      {"assets/foto1.jpg": JPEG, "assets/foto2.jpg": JPEG})
        self.assertTrue(r["ok"], r)
        self.assertEqual(qa_imagem.scan(self.fonte, qa_imagem.NETWORK_PATTERNS + [("gsap", qa_imagem.GSAP_RE)]), [])

    def test_image_outside_assets_wrong_type_or_inline_fails(self):
        casos = [('<img src="foto.jpg">', {"foto.jpg": JPEG}),
                 ('<img src="assets/x.gif">', {"assets/x.gif": b"GIF89a"}),
                 ('<img src="assets/x.png">', {"assets/x.png": JPEG}),
                 ('<img src="assets/falta.jpg">', {}),
                 ('<img src="data:image/png;base64,AAAA">', {}),
                 ('<div style="background-image:url(\'../fora.png\')"></div>', {}),
                 ('<img srcset="assets/a.jpg 1x, ../b.jpg 2x">', {"assets/a.jpg": JPEG}),
                 ('<svg><image href="assets/outra.svg"/></svg>', {"assets/outra.svg": "<svg/>"})]
        for corpo, arquivos in casos:
            shutil.rmtree(self.fonte)
            os.makedirs(self.fonte)
            self.assertFalse(self.html(corpo, arquivos)["ok"], corpo)

    def test_logo_svg_and_fragment_refs_pass(self):
        r = self.html('<img src="assets/logo.svg"><svg><rect fill="url(#g)"/></svg>', {"assets/logo.svg": "<svg/>"})
        self.assertTrue(r["ok"], r)


class GooglePhoto(unittest.TestCase):
    def setUp(self):
        self.fonte = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.fonte)

    def peca(self, corpo, *assets):
        escrever(os.path.join(self.fonte, "index.html"), "<html><body>%s</body></html>" % corpo)
        for n in assets:
            escrever(os.path.join(self.fonte, "assets", n), JPEG)
        return anuncio.checar_peca(self.fonte, "google", 1200, 1200)

    def test_photo_only_piece_is_clean(self):
        self.assertEqual(self.peca('<img src="assets/foto1.jpg" style="object-fit:cover">', "foto1.jpg"), [])

    def test_photo_with_text_logo_or_other_image_fails(self):
        self.assertTrue(self.peca('<img src="assets/foto1.jpg"><p>Oferta</p>', "foto1.jpg"))
        shutil.rmtree(os.path.join(self.fonte, "assets"))
        self.assertTrue(self.peca('<img src="assets/foto1.jpg">', "foto1.jpg", "logo.png"))
        shutil.rmtree(os.path.join(self.fonte, "assets"))
        self.assertTrue(self.peca('<img src="assets/logo.png">', "logo.png"))


if __name__ == "__main__":
    unittest.main()
