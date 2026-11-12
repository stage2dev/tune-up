"""scripts/qa_vazio.py: the empty area of a rendered frame (check `ocupacao`). No Chrome, no network; the PNG
filter test uses ffmpeg when it is installed."""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import qa_vazio  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
BRANCO, CINZA = b"\xff\xff\xff", b"\x80\x80\x80"


def png(caminho, w, h, pixel):
    """An 8-bit RGB PNG (filter 0) where pixel(x, y) gives each pixel's 3 bytes."""
    def chunk(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))
    cru = b"".join(b"\0" + b"".join(pixel(x, y) for x in range(w)) for y in range(h))
    with open(caminho, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(cru)) + chunk(b"IEND", b""))


class Ocupacao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.png = os.path.join(self.tmp, "q.png")

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_quadro_cheio_passa_e_vazio_reprova(self):
        # 216x270 = a 1080x1350 post at 1/5; the safe box starts 16 px (80 / 5) in.
        listra = lambda x, y: BRANCO if (x + y) % 3 else CINZA  # noqa: E731 - text and devices everywhere
        png(self.png, 216, 270, listra)
        self.assertTrue(qa_vazio.check_png(self.png, 1080, 1350)["ok"])
        buraco = lambda x, y: BRANCO if 16 <= x < 136 and 152 <= y < 232 else listra(x, y)  # noqa: E731
        png(self.png, 216, 270, buraco)
        rep = qa_vazio.check_png(self.png, 1080, 1350)
        self.assertFalse(rep["ok"])
        self.assertIn("área vazia de 600x400 px em (80, 760)", rep["details"][0])
        self.assertIn("(máximo 15%)", rep["details"][0])

    def test_forma_de_outra_cor_nao_e_vazio(self):
        """A big shape in another brand color is the device, not a void; only the background color is empty."""
        def forma(x, y):
            if 100 <= x < 200 and 140 <= y < 254:
                return CINZA  # a 500x570 px block: 26% of the safe box if it counted
            return BRANCO if (x + y) % 3 or not (16 <= x < 200 and 16 <= y < 254) else CINZA
        png(self.png, 216, 270, forma)
        self.assertTrue(qa_vazio.check_png(self.png, 1080, 1350)["ok"])
        png(self.png, 216, 270, lambda x, y: CINZA if 16 <= x < 200 and y >= 16 else BRANCO)
        self.assertFalse(qa_vazio.check_png(self.png, 1080, 1350)["ok"])  # one flat color filling it is empty

    def test_png_fora_do_formato_nao_reprova(self):
        with open(self.png, "wb") as f:
            f.write(b"GIF89a")
        rep = qa_vazio.check_png(self.png, 1080, 1350)
        self.assertTrue(rep["ok"])
        self.assertIn("não medido", rep["details"][0])

    def test_maior_retangulo(self):
        grade = [[False, False, True, True], [True, True, True, False], [True, True, True, False]]
        self.assertEqual(qa_vazio._maior_retangulo(grade), (6, (0, 1, 3, 2)))
        self.assertEqual(qa_vazio._maior_retangulo([[False]]), (0, None))

    @unittest.skipUnless(FFMPEG, "ffmpeg not available")
    def test_filtros_png_decodificados(self):
        """ffmpeg's mixed-prediction PNG uses every filter (Sub, Up, Average, Paeth): the rows match the raw."""
        w, h = 40, 24
        cru = b"".join(bytes(((x * 7 + y * 13) % 256, (x * y) % 256, (x + 3 * y) % 256)) for y in range(h)
                       for x in range(w))
        entrada, saida = os.path.join(self.tmp, "cru.rgb"), os.path.join(self.tmp, "f.png")
        with open(entrada, "wb") as f:
            f.write(cru)
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (w, h),
                        "-i", entrada, "-pred", "mixed", saida], check=True)
        lw, lh, bpp, linhas = qa_vazio.ler_png(saida)
        self.assertEqual((lw, lh, bpp), (w, h, 3))
        self.assertEqual(b"".join(linhas), cru)


if __name__ == "__main__":
    unittest.main()
