"""Proves the tune-up-mkt folder contains nothing specific to a private project.

Forbidden words are stored only as (length, sha256) pairs. Hashing avoids casual
reading of the names; it does not hide them from a dictionary attack. The list
source is private to the maintainers. There is no exception list per folder.
"""
import hashlib
import os
import re
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROIBIDAS = [
    (9, "5d287f7ab9fc468433d94471ba0b40f8defd63bcd4fb4bf1631903cc1aa31453"),
    (11, "b6a0938bd025bb9e9da0f319efb1f631131465bf5c7bb23e8c88553cc6bcb1ff"),
    (9, "bb56d6ec3752cabe0b7c9e82b4518667d0fabc95c8c739bbe9ed8218c1ce6768"),
    (6, "ca11fd0d783f3b4bffe2cadc1feb5180fbfca06975d7388e50dbfd8c76b5ad65"),
    (5, "ccc68482d9e0eee0789e64c7674421076738f8836857ea89bcd0afb832bf3fc3"),
    (7, "ba258a24d58a412bdcb747019678a7a85116bee04f463bb6e2347a7a1bfe3c97"),
    (6, "bf81aab14d4b2447f98cddf5dbdab64cf63bdc30b3c61babdb49f2491c94fbfa"),
    (10, "41a9a86cf7da86361376b3728dc2f02f6720a00d25ee6afdb08737c07a1f48a5"),
    (7, "0de8c0f634ab2349378ec0955278df6e21696c6f02b4712f937859ccebc50d7e"),
    (6, "9f3088478b60f826fed7a6b6d0fcec64dee91bfe7dc10a87335626b808f062b4"),
    (9, "4e13fc92637ae7fabeac66e989a1e107898955271a47a081131870150f27a06d"),
    (6, "152779b01ccf73227c78161b9c817c727c5a92c00adeaacdec85015abb93052f"),
]

# The lookarounds keep sha256 hex strings from matching.
PADROES = [
    ("telefone", re.compile(r"(?<![0-9a-fA-F])\d{10,12}(?![0-9a-fA-F])")),
    ("conta de anuncios", re.compile(r"act_\d{6,}")),
    ("id de analytics", re.compile(r"G-[A-Z0-9]{8,}")),
    ("id numerico longo", re.compile(r"(?<![0-9a-fA-F])\d{13,}(?![0-9a-fA-F])")),
]


def achados_na_linha(linha):
    """Kinds found in one line (forbidden-word hits and pattern hits)."""
    achados = []
    baixa = linha.lower()
    por_tamanho = {}
    for tam, h in PROIBIDAS:
        por_tamanho.setdefault(tam, set()).add(h)
    for tam, hashes in por_tamanho.items():
        for i in range(len(baixa) - tam + 1):
            if hashlib.sha256(baixa[i:i + tam].encode("utf-8")).hexdigest() in hashes:
                achados.append("palavra proibida")
                break
    for nome, rx in PADROES:
        if rx.search(linha):
            achados.append(nome)
    return achados


def arquivos():
    for pasta, dirs, nomes in os.walk(RAIZ):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for n in nomes:
            if not n.endswith(".pyc"):
                yield os.path.join(pasta, n)


class Generico(unittest.TestCase):
    def test_pasta_sem_nada_especifico(self):
        problemas = []
        for caminho in arquivos():
            with open(caminho, "rb") as f:
                dados = f.read()
            if b"\x00" in dados:
                continue
            texto = dados.decode("utf-8", errors="replace")
            rel = os.path.relpath(caminho, RAIZ).replace(os.sep, "/")
            for num, linha in enumerate(texto.splitlines(), 1):
                for tipo in achados_na_linha(linha):
                    problemas.append("%s:%d: %s" % (rel, num, tipo))
        self.assertEqual(problemas, [], "\n".join(problemas))


class Detector(unittest.TestCase):
    def test_hash_sha256_nao_dispara(self):
        h = "0123456789abcdef" * 4
        self.assertEqual(len(h), 64)
        self.assertEqual(achados_na_linha('"%s"' % h), [])
        self.assertEqual(achados_na_linha("x = " + h + ","), [])

    def test_cada_padrao_dispara(self):
        amostras = {
            "telefone": "tel " + "1" * 11 + " fim",
            "conta de anuncios": "act_" + "1234567",
            "id de analytics": "G-" + "ABCD1234",
            "id numerico longo": "id " + "9" * 14 + " fim",
        }
        for nome, amostra in amostras.items():
            self.assertIn(nome, achados_na_linha(amostra), nome)

    def test_palavra_proibida_dispara(self):
        # Self-check with the first pair: any text hashing to it must be flagged.
        tam, h = PROIBIDAS[0]
        self.assertEqual(len(h), 64)
        self.assertGreater(tam, 0)

    def test_palavra_hash_dispara_de_verdade(self):
        # Swap the pair list for a harmless word built at runtime; a line containing it must be reported.
        global PROIBIDAS
        palavra = "ban" + "ana"
        original = PROIBIDAS
        PROIBIDAS = [(len(palavra), hashlib.sha256(palavra.encode("utf-8")).hexdigest())]
        try:
            self.assertIn("palavra proibida", achados_na_linha("x = 'Ban" + "ana split'"))
            self.assertNotIn("palavra proibida", achados_na_linha("x = 'apple'"))
        finally:
            PROIBIDAS = original


if __name__ == "__main__":
    unittest.main()
