"""Unit tests for scripts/cores.py (CSS color text -> #RRGGBB)."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))

import cores  # noqa: E402


class TesteParaHex(unittest.TestCase):
    def test_conversoes_conhecidas(self):
        casos = {
            "#fff": "#FFFFFF", "#C9702B": "#C9702B", "#c9702bcc": "#C9702B", "#f00a": "#FF0000",
            "rgb(201, 112, 43)": "#C9702B", "rgb(201 112 43 / .5)": "#C9702B", "rgba(100%,0%,0%,0.3)": "#FF0000",
            "hsl(0 100% 50%)": "#FF0000", "hsl(120deg, 100%, 25%)": "#008000", "hsla(240, 100%, 50%, .2)": "#0000FF",
            "hsl(0.5turn 100% 50%)": "#00FFFF",
            "0 0% 100%": "#FFFFFF", "222.2 47.4% 11.2%": "#0F172A",  # shadcn trio = Tailwind slate-900
            "oklch(1 0 0)": "#FFFFFF", "oklch(0 0 0)": "#000000", "oklch(0.145 0 0)": "#0A0A0A",
            "oklch(0.628 0.2577 29.23)": "#FF0000", "oklch(62.8% 0.2577 29.23)": "#FF0000",
            "white": "#FFFFFF", " #ABC ; ": "#AABBCC", "#123456 !important": "#123456",
        }
        for texto, esperado in casos.items():
            with self.subTest(texto=texto):
                self.assertEqual(cores.para_hex(texto), esperado)

    def test_oklch_fora_da_gama_e_cortado(self):
        valor = cores.para_hex("oklch(0.7 0.5 140)")  # far outside sRGB
        self.assertRegex(valor, r"^#[0-9A-F]{6}$")
        self.assertEqual(valor[1:3] + valor[5:7], "0000")  # red and blue clipped to 0

    def test_nao_e_cor_simples(self):
        for texto in ("var(--primary)", "hsl(var(--primary))", "linear-gradient(red, blue)", "currentColor",
                      "#12", "#12345", "rgb(1, 2)", "rgb(a, b, c)", "oklch(x 0 0)", "", None, 12,
                      "color-mix(in srgb, red, blue)", "transparent"):
            with self.subTest(texto=texto):
                self.assertIsNone(cores.para_hex(texto))


if __name__ == "__main__":
    unittest.main()
