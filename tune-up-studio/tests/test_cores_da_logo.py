"""cores_da_logo.py: colors of an SVG or PNG logo -> brand roles, deterministic, standard library only."""
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import cores_da_logo as cl  # noqa: E402


def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def _filtrar(f, linha, anterior, bpp):
    """Forward PNG filter of one row (the decoder must undo it)."""
    saida = bytearray()
    for i, x in enumerate(linha):
        a = linha[i - bpp] if i >= bpp else 0
        b = anterior[i]
        c = anterior[i - bpp] if i >= bpp else 0
        saida.append((x - (0, a, b, (a + b) // 2, _paeth(a, b, c))[f]) & 255)
    return bytes([f]) + bytes(saida)


def png(linhas, tipo=6, prof=8, filtros=(0,), extra=b"", entrelacado=0):
    """linhas: list of raw row bytes (unfiltered)."""
    w_bytes = len(linhas[0])
    bpp = max(1, {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[tipo] * prof // 8)
    largura = w_bytes * 8 // ({0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[tipo] * prof)
    cru, anterior = b"", bytes(w_bytes)
    for y, linha in enumerate(linhas):
        cru += _filtrar(filtros[y % len(filtros)], linha, anterior, bpp)
        anterior = linha

    def ch(t, c):
        return struct.pack(">I", len(c)) + t + c + struct.pack(">I", zlib.crc32(t + c))
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", largura, len(linhas), prof, tipo, 0, 0, entrelacado))
            + extra + ch(b"IDAT", zlib.compress(cru)) + ch(b"IEND", b""))


def chunk(t, c):
    return struct.pack(">I", len(c)) + t + c + struct.pack(">I", zlib.crc32(t + c))


def rgba(*px):
    return bytes(b for p in px for b in p)


LARANJA, MARROM, BRANCO, NADA = (200, 112, 42, 255), (90, 50, 32, 255), (255, 255, 255, 255), (0, 0, 0, 0)


class TesteCoresDaLogo(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def arquivo(self, nome, dados):
        p = os.path.join(self.tmp, nome)
        with open(p, "wb") as f:
            f.write(dados.encode("utf-8") if isinstance(dados, str) else dados)
        return p

    def test_png_rgba_com_os_cinco_filtros_e_transparencia(self):
        linhas = [rgba(LARANJA, LARANJA, LARANJA, NADA), rgba(LARANJA, LARANJA, MARROM, NADA),
                  rgba(LARANJA, MARROM, BRANCO, NADA), rgba(NADA, NADA, NADA, NADA), rgba(LARANJA, LARANJA, MARROM, BRANCO)]
        for f in range(5):
            r = cl.ler(self.arquivo("logo%d.png" % f, png(linhas, filtros=(f,))))
            self.assertEqual(r["cores"][0], ["#C8702A", 8], f)  # o transparente não conta
            self.assertEqual(r["papeis"], {"primary": "#C8702A", "accent": "#5A3220", "text": "#5A3220",
                                          "bg": "#FFFFFF"}, f)
        r = cl.ler(self.arquivo("mix.png", png(linhas, filtros=(1, 2, 3, 4, 0))))
        self.assertEqual(r["papeis"]["primary"], "#C8702A")

    def test_png_paleta_com_trns_cinza_16_bits_e_rgb(self):
        paleta = chunk(b"PLTE", bytes([10, 20, 200, 255, 0, 0])) + chunk(b"tRNS", bytes([255, 0]))
        p = png([bytes([0b00010000]), bytes([0b00000000])], tipo=3, prof=2, extra=paleta)  # 4 px por linha, 2 bits
        self.assertEqual(cl.ler(self.arquivo("pal.png", p))["papeis"], {"primary": "#0A14C8", "text": "#0A14C8"})
        cinza = png([struct.pack(">HH", 0x1000, 0x1000)], tipo=0, prof=16)
        self.assertEqual(cl.ler(self.arquivo("g.png", cinza))["papeis"], {"primary": "#101010", "text": "#101010"})
        rgb = png([bytes([0, 128, 0]) * 3], tipo=2)
        self.assertEqual(cl.ler(self.arquivo("rgb.png", rgb))["papeis"], {"primary": "#008000", "text": "#008000"})

    def test_svg_conta_fill_stroke_e_css(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg"><style>.a{fill:#c8702a}</style>'
               '<path fill="#C8702A"/><path fill="#c8702a"/><rect stroke="rgb(90,50,32)" fill="none"/>'
               '<circle style="fill: url(#g); stroke:#5A3220"/><stop stop-color="white"/><path fill="var(--x)"/></svg>')
        r = cl.ler(self.arquivo("logo.svg", svg))
        self.assertEqual(r["cores"], [["#C8702A", 3], ["#5A3220", 2], ["#FFFFFF", 1]])
        self.assertEqual(r["papeis"], {"primary": "#C8702A", "accent": "#5A3220", "text": "#5A3220",
                                          "bg": "#FFFFFF"})

    def test_mesma_logo_mesmo_resultado(self):
        p = self.arquivo("l.png", png([rgba(LARANJA, MARROM, BRANCO, BRANCO)]))
        self.assertEqual(cl.ler(p), cl.ler(p))

    def test_recusas_em_palavras(self):
        casos = [("logo.jpg", b"\xff\xd8\xff\xe0", "PNG ou SVG"), ("logo.webp", b"RIFF", "PNG ou SVG"),
                 ("e.png", png([rgba(LARANJA)]), None), ("vazio.svg", "<svg/>", "nenhuma cor"),
                 ("ruim.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "PNG incompleto")]
        casos[2] = ("e.png", png([rgba(LARANJA)], entrelacado=1), "entrelaçado")
        for nome, dados, texto in casos:
            with self.assertRaises(cl.Ilegivel) as e:
                cl.ler(self.arquivo(nome, dados))
            self.assertIn(texto, str(e.exception), nome)
        enorme = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 5000, 5000, 8, 6, 0, 0, 0)) \
            + chunk(b"IDAT", zlib.compress(b"")) + chunk(b"IEND", b"")
        with self.assertRaises(cl.Ilegivel):
            cl.ler(self.arquivo("enorme.png", enorme))  # recusado antes de descomprimir

    def test_cli(self):
        p = self.arquivo("l.svg", '<svg><path fill="#112233"/></svg>')
        self.assertEqual(cl.main([p]), 0)
        self.assertEqual(cl.main([os.path.join(self.tmp, "x.jpg")]), 2)


if __name__ == "__main__":
    unittest.main()
