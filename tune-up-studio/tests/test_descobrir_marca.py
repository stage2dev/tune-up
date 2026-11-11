"""Tests for scripts/descobrir_marca.py (C9): example vs gabarito, missing fields, locks, no-brand mode."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))

import descobrir_marca as dm  # noqa: E402

EXEMPLO = os.path.join(STUDIO, "exemplos", "forno-miudo")


def _escrever(raiz, rel, texto):
    c = os.path.join(raiz, *rel.split("/"))
    os.makedirs(os.path.dirname(c), exist_ok=True)
    with open(c, "w", encoding="utf-8") as f:
        f.write(texto)
    return c


def _main(*args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return dm.main(list(args))


def _sem_aspas(texto):
    return texto.replace("'", "").replace('"', "")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.raiz = os.path.join(self.tmp, "projeto")
        os.makedirs(self.raiz)
        self.saida = os.path.join(self.raiz, ".tune-up", "estudio", "marca")

    def ler_marca(self):
        with open(os.path.join(self.saida, "marca.json"), encoding="utf-8") as f:
            return json.load(f)


class TesteExemplo(Base):
    def setUp(self):
        super().setUp()
        shutil.rmtree(self.raiz)
        shutil.copytree(EXEMPLO, self.raiz, ignore=shutil.ignore_patterns(".hyperframes", ".tune-up"))
        with open(os.path.join(EXEMPLO, "gabarito.json"), encoding="utf-8") as f:
            self.gabarito = json.load(f)

    def test_bate_com_gabarito(self):
        self.assertEqual(_main("--projeto", self.raiz), 0)
        d = self.ler_marca()
        c = d["campos"]
        self.assertEqual(d["modo"], "marca")
        for nome, hexa in self.gabarito["colors"].items():
            self.assertEqual(c["cores." + nome]["valor"], hexa.upper(), nome)
            self.assertEqual(c["cores." + nome]["confianca"], "alta", nome)
        for nome, pilha in self.gabarito["fonts"].items():
            self.assertEqual(_sem_aspas(c["fontes." + nome]["valor"]), _sem_aspas(pilha), nome)
        self.assertEqual(c["logo"]["valor"], self.gabarito["logo"])
        self.assertEqual(c["nome"]["valor"], self.gabarito["name"])
        self.assertEqual(c["cores.primary"]["fonte"], "styles.css:4")
        self.assertEqual(c["logo"]["fonte"], "index.html:11")
        with open(os.path.join(self.saida, "assets", "logo.svg"), "rb") as a, \
                open(os.path.join(self.raiz, "logo.svg"), "rb") as b:
            self.assertEqual(a.read(), b.read())
        self.assertNotIn("paleta_neutra", d)
        with open(os.path.join(self.saida, "MARCA.md"), encoding="utf-8") as f:
            md = f.read()
        self.assertIn("| cores.primary | #C9702B | alta | styles.css:4 | não |", md)

    def test_campo_ausente_fica_faltando(self):
        c = dm.rodar(self.raiz)["campos"]
        self.assertEqual(c["descricao"], {"valor": None, "fonte": None, "confianca": "faltando", "travado": False})
        for k, v in c.items():
            self.assertEqual(set(v), {"valor", "fonte", "confianca", "travado"}, k)
            if v["confianca"] != "faltando":
                self.assertRegex(v["fonte"], r"^[^:]+:\d+$", k)

    def test_segunda_rodada_preserva_travado(self):
        dm.rodar(self.raiz)
        d = self.ler_marca()
        d["campos"]["cores.primary"] = {"valor": "#123456", "fonte": "dono", "confianca": "alta", "travado": True}
        d["campos"]["cores.bg"]["valor"] = "#000000"  # not locked: discovery overwrites it
        with open(os.path.join(self.saida, "marca.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        dm.rodar(self.raiz)
        c = self.ler_marca()["campos"]
        self.assertEqual(c["cores.primary"], {"valor": "#123456", "fonte": "dono", "confianca": "alta",
                                              "travado": True})
        self.assertEqual(c["cores.bg"]["valor"], "#FFF8EC")

    def test_logo_travado_sem_arquivo_mantem_copia(self):
        dm.rodar(self.raiz)
        d = self.ler_marca()
        d["campos"]["logo"]["travado"] = True
        with open(os.path.join(self.saida, "marca.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.remove(os.path.join(self.raiz, "logo.svg"))
        d2 = dm.rodar(self.raiz)
        self.assertEqual(d2["campos"]["logo"]["valor"], "logo.svg")
        self.assertEqual(d2["logo_copia"], "assets/logo.svg")
        self.assertTrue(os.path.isfile(os.path.join(self.saida, "assets", "logo.svg")))

    def test_marca_json_ilegivel_recusa_e_nao_sobrescreve(self):
        os.makedirs(self.saida)
        alvo = os.path.join(self.saida, "marca.json")
        with open(alvo, "w", encoding="utf-8") as f:
            f.write("{quebrado")
        self.assertEqual(_main("--projeto", self.raiz), 2)
        with open(alvo, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{quebrado")
        self.assertFalse(os.path.exists(os.path.join(self.saida, "MARCA.md")))


class TesteSemMarca(Base):
    def _confere_sem_marca(self, d):
        self.assertEqual(d["modo"], "sem_marca")
        self.assertEqual(d["paleta_neutra"], dm.PALETA_NEUTRA)
        for k in dm.CAMPOS:
            if k.startswith(("cores.", "fontes.")) or k == "logo":
                self.assertIn(d["campos"][k]["confianca"], ("faltando", "baixa"), k)
        self.assertIsNone(d["logo_copia"])
        with open(os.path.join(self.saida, "MARCA.md"), encoding="utf-8") as f:
            self.assertIn("Modo sem marca", f.read())

    def test_pasta_vazia(self):
        self.assertEqual(_main("--projeto", self.raiz), 0)
        d = self.ler_marca()
        self._confere_sem_marca(d)
        self.assertTrue(all(v["confianca"] == "faltando" and v["valor"] is None for v in d["campos"].values()))

    def test_repo_so_de_backend(self):
        _escrever(self.raiz, "pyproject.toml", '[project]\nname = "pedidos-api"\ndescription = "API de pedidos"\n')
        _escrever(self.raiz, "go.mod", "module example.com/acme/worker\n\ngo 1.22\n")
        _escrever(self.raiz, "app/main.py", "print('ok')\n")
        d = dm.rodar(self.raiz)
        self._confere_sem_marca(d)
        # both are package slugs (baixa); same depth, so the first by path wins
        self.assertEqual(d["campos"]["nome"], {"valor": "worker", "fonte": "go.mod:1",
                                               "confianca": "baixa", "travado": False})
        self.assertEqual(d["campos"]["descricao"]["fonte"], "pyproject.toml:3")

    def test_shadcn_padrao_e_baixa(self):
        _escrever(self.raiz, "src/index.css", "@tailwind base;\n:root {\n  --background: 0 0% 100%;\n"
                  "  --foreground: 222.2 84% 4.9%;\n  --primary: 222.2 47.4% 11.2%;\n}\n"
                  ".dark {\n  --primary: 10 90% 50%;\n}\n")
        _escrever(self.raiz, "index.html", '<link rel="icon" href="/vite.svg"><title>Vite + React</title>')
        _escrever(self.raiz, "public/vite.svg", "<svg/>")
        d = dm.rodar(self.raiz)
        self._confere_sem_marca(d)
        self.assertEqual(d["campos"]["cores.primary"]["valor"], "#0F172A")
        self.assertEqual(d["campos"]["cores.primary"]["confianca"], "baixa")
        self.assertIsNone(d["campos"]["logo"]["valor"])


class TesteFontes(Base):
    def test_theme_oklch_e_tailwind_config(self):
        _escrever(self.raiz, "src/app.css", "@import 'tailwindcss';\n:root {\n  --brand: oklch(0.628 0.2577 29.23);\n"
                  "}\n@theme inline {\n  --color-primary: var(--brand);\n  --font-display: 'Fraunces', serif;\n}\n")
        _escrever(self.raiz, "tailwind.config.js", "module.exports = { theme: { extend: {\n  colors: {\n"
                  "    accent: { DEFAULT: 'hsl(160 84% 39%)', foreground: '#fff' },\n    surface: '#f5f0e6',\n"
                  "  },\n  fontFamily: { sans: ['Inter', 'system-ui'] },\n} } }\n")
        c = dm.rodar(self.raiz)["campos"]
        self.assertEqual(c["cores.primary"], {"valor": "#FF0000", "fonte": "src/app.css:3", "confianca": "alta",
                                              "travado": False})
        self.assertEqual(c["fontes.heading"]["valor"], "'Fraunces', serif")
        self.assertEqual(c["cores.accent"]["valor"], "#10B77F")
        self.assertEqual(c["cores.accent"]["fonte"], "tailwind.config.js:3")
        self.assertEqual(c["cores.surface"]["fonte"], "tailwind.config.js:4")
        self.assertEqual(c["fontes.body"]["valor"], "Inter, system-ui")

    def test_ignora_node_modules_url_externa_e_atalho(self):
        _escrever(self.raiz, "node_modules/pkg/logo.svg", "<svg/>")
        _escrever(self.raiz, "node_modules/pkg/style.css", ":root { --primary: #ABCDEF; }")
        _escrever(self.raiz, "index.html", '<img src="https://cdn.example.com/logo.svg" alt="X">'
                  '<img class="logo" src="../fora/logo.png" alt="Y">')
        fora = _escrever(self.tmp, "fora/logo.png", "png")
        try:
            os.symlink(fora, os.path.join(self.raiz, "logo-atalho.png"))
        except (OSError, NotImplementedError):
            pass  # Windows without symlink rights: the other cases still run
        d = dm.rodar(self.raiz)
        self.assertIsNone(d["campos"]["logo"]["valor"])
        self.assertIsNone(d["campos"]["cores.primary"]["valor"])
        self.assertEqual(d["modo"], "sem_marca")

    def test_profundidade_limitada(self):
        _escrever(self.raiz, "a/b/c/d/e/styles.css", ":root { --primary: #ABCDEF; }")
        _escrever(self.raiz, "a/b/c/styles.css", ":root { --accent: #FEDCBA; }")
        c = dm.rodar(self.raiz)["campos"]
        self.assertIsNone(c["cores.primary"]["valor"])
        self.assertEqual(c["cores.accent"]["fonte"], "a/b/c/styles.css:1")


if __name__ == "__main__":
    unittest.main()
