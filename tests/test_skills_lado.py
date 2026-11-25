"""Tests: `skills_by_glob` (config) and `side_skills` (info), plus the texts that use them."""
import json
import os
import pathlib
import shutil
import unittest

import test_info
from base import IS_WIN, Base, fwd, symlink

RAIZ = pathlib.Path(__file__).resolve().parent.parent
with open(str(RAIZ / "scripts" / "padrao.json"), encoding="utf-8") as _f:
    PADRAO = json.load(_f)["skills_by_glob"]
TODAS = sorted({n for v in PADRAO.values() for n in v})


def ler(f):
    return (RAIZ / f).read_text(encoding="utf-8")


class Lado(Base):
    """Fake catalog in the test HOME."""
    USER_JSON = None
    info = test_info.TestInfo.info

    def setUp(self):
        super().setUp()
        self.pasta = os.path.join(self.tmp, ".config", "tune-up")

    def arquivo(self, nome):
        return os.path.join(self.pasta, "ecc-skills", nome, "SKILL.md")

    def catalogo(self, nomes=TODAS, listados=None):
        for n in nomes:
            os.makedirs(os.path.dirname(self.arquivo(n)))
            with open(self.arquivo(n), "w", encoding="utf-8") as f:
                f.write("---\nname: %s\n---\n" % n)
        with open(os.path.join(self.pasta, "skills-catalog.md"), "w", encoding="utf-8") as f:
            f.write("# Catalog\n\n| Skill | What it does | Path |\n|---|---|---|\n")
            for n in nomes if listados is None else listados:
                f.write("| `%s` | What | `~/.config/tune-up/ecc-skills/%s/SKILL.md` |\n" % (n, n))

    def config(self, valor, confiar=True):
        c = os.path.join(self.cwd, ".tune-up", "config.json")
        os.makedirs(os.path.dirname(c), exist_ok=True)
        with open(c, "w", encoding="utf-8") as f:
            json.dump({"skills_by_glob": valor}, f)
        if confiar:
            self.confiar(c)
        return c

    def globs(self):
        """{name: paths} of side_skills; also checks the sort order."""
        lado = self.info()["side_skills"]
        self.assertEqual([x["name"] for x in lado], sorted(x["name"] for x in lado))
        return {x["name"]: x["paths"] for x in lado}

    def erros(self):
        p = os.path.join(self.dados, "erros.log")
        return pathlib.Path(p).read_text(encoding="utf-8") if os.path.exists(p) else ""

    def aviso(self):
        """The SessionStart message, where the `_invalidas` keys and the untrusted profile show."""
        return json.dumps(self.rodar("inicio", {"source": "startup"}), ensure_ascii=False)


class TestSideSkills(Lado):
    def test_padrao_sem_config_de_projeto(self):
        self.catalogo()
        i = self.info()
        lado = {x["name"]: x for x in i["side_skills"]}
        self.assertEqual(sorted(lado), TODAS)
        self.assertEqual(i["side_skills_missing"], [])
        self.assertEqual(lado["react-patterns"], {
            "name": "react-patterns", "path": fwd(os.path.realpath(self.arquivo("react-patterns"))),
            "paths": ["**/*.tsx", "**/*.jsx"]})  # one entry per name, globs merged
        self.assertEqual(lado["python-patterns"]["paths"], ["**/*.py"])
        self.assertEqual(lado["database-migrations"]["paths"], ["**/*.sql"])
        self.assertTrue(all(os.path.isabs(x["path"]) for x in i["side_skills"]))

    def test_padrao_e_valido(self):
        import sys
        sys.path.insert(0, str(RAIZ / "scripts"))
        try:
            from tuneup.config import skills_mescladas
        finally:
            sys.path.pop(0)
        ruins = set()
        self.assertEqual(skills_mescladas({}, PADRAO, ruins), PADRAO)
        self.assertEqual(ruins, set())

    def test_projeto_soma_troca_e_desliga(self):
        self.catalogo(TODAS + ["go-patterns"])
        self.config({"**/*.go": ["go-patterns"], "**/*.py": ["python-testing"], "**/*.sql": []})
        g = self.globs()
        self.assertEqual(g["go-patterns"], ["**/*.go"])
        self.assertEqual(g["python-testing"], ["**/*.py"])
        for fora in ("python-patterns", "postgres-patterns", "database-migrations"):
            self.assertNotIn(fora, g)
        self.assertEqual(g["coding-standards"], ["**/*.ts"])  # untouched default
        self.assertNotIn("skills_by_glob", self.erros())

    def test_nao_confiado_e_ignorado(self):
        self.catalogo(TODAS + ["go-patterns"])
        c = self.config({"**/*.go": ["go-patterns"], "**/*.py": []}, confiar=False)
        self.assertEqual(sorted(self.globs()), TODAS)
        self.assertIn(json.dumps(os.path.realpath(c))[1:-1], self.aviso())
        self.confiar(c)
        self.assertIn("go-patterns", self.globs())
        self.config({"**/*.go": ["go-patterns"], "**/*.py": [], "**/*.rb": []}, confiar=False)
        self.assertEqual(sorted(self.globs()), TODAS)  # edited after trust

    def test_entrada_ruim_cai_sozinha(self):
        self.catalogo()
        for g, v in (("**", ["python-patterns"]), ("**/*", []), ("", []), ("[a-z]*", []),
                     ("x" * 121, []), ("a\nb", []), ("a\ud800", []),
                     ("**/*.py", ["a", "b", "c"]), ("**/*.py", ["../x"]), ("**/*.py", ["a/b"]),
                     ("**/*.py", [".."]), ("**/*.py", ["a\n"]), ("**/*.py", ["A"]),
                     ("**/*.py", ["a" * 65]), ("**/*.py", [1]), ("**/*.py", "python-testing"),
                     ("**/*.py", None), ("**/*.py", {"a": 1})):
            with self.subTest(g=g, v=v):
                shutil.rmtree(self.dados, ignore_errors=True)
                self.config({g: v, "**/*.ts": ["python-testing"]})
                achadas = self.globs()
                self.assertEqual(achadas["python-patterns"], ["**/*.py"])  # the default stays
                self.assertEqual(achadas["python-testing"], ["**/*.ts", "**/*.py"])  # the good one counts
                self.assertIn("skills_by_glob: 1 entries discarded", self.erros())
        self.assertIn("skills_by_glob", self.aviso())

    def test_valor_de_tipo_errado_cai_inteiro(self):
        self.catalogo()
        for ruim in ("python-patterns", ["python-patterns"], 1, None, True):
            with self.subTest(ruim=ruim):
                self.config(ruim)
                self.assertEqual(sorted(self.globs()), TODAS)
        self.assertIn("key skills_by_glob discarded", self.erros())
        self.assertIn("skills_by_glob", self.aviso())

    def test_limite_de_entradas(self):
        self.catalogo(TODAS + ["go-patterns"])
        self.config({"g%03d/**" % i: ["go-patterns"] for i in range(60)})
        self.assertEqual(len(self.globs()["go-patterns"]), 50)
        self.assertIn("10 entries discarded", self.erros())

    def test_sem_catalogo_tudo_falta(self):
        i = self.info()
        self.assertEqual((i["catalog_path"], i["side_skills"], i["side_skills_missing"]), (None, [], TODAS))

    def test_fora_da_lista_ou_sem_arquivo_falta(self):
        self.catalogo(TODAS, listados=[n for n in TODAS if n != "python-testing"])
        shutil.rmtree(os.path.dirname(self.arquivo("react-patterns")))
        os.remove(self.arquivo("coding-standards"))
        os.mkdir(self.arquivo("coding-standards"))  # a folder is not a regular file
        i = self.info()
        fora = ["coding-standards", "python-testing", "react-patterns"]
        self.assertEqual(i["side_skills_missing"], fora)
        self.assertEqual([x["name"] for x in i["side_skills"]], [n for n in TODAS if n not in fora])

    def test_symlink_que_sai_do_catalogo_falta(self):
        self.catalogo()
        alvo = os.path.join(self.tmp, "fora.md")
        with open(alvo, "w", encoding="utf-8") as f:
            f.write("instructions")
        os.remove(self.arquivo("python-patterns"))
        symlink(alvo, self.arquivo("python-patterns"))
        pasta = os.path.dirname(self.arquivo("react-patterns"))
        shutil.move(pasta, os.path.join(self.tmp, "react-fora"))
        symlink(os.path.join(self.tmp, "react-fora"), pasta, dir_=True)
        self.assertEqual(self.info()["side_skills_missing"], ["python-patterns", "react-patterns"])

    def test_catalogo_ilegivel_tudo_falta_com_log(self):
        os.makedirs(os.path.join(self.pasta, "skills-catalog.md"))
        i = self.info()
        self.assertEqual((i["side_skills"], i["side_skills_missing"]), ([], TODAS))
        self.assertIn("skills-catalog.md is not a regular file", self.erros())

    @unittest.skipIf(IS_WIN or not hasattr(os, "geteuid") or os.geteuid() == 0, "needs POSIX modes, not root")
    def test_catalogo_sem_permissao_tudo_falta_com_log(self):
        self.catalogo()
        os.chmod(os.path.join(self.pasta, "skills-catalog.md"), 0)
        i = self.info()
        self.assertEqual((i["side_skills"], i["side_skills_missing"]), ([], TODAS))
        self.assertIn("skills-catalog.md unreadable", self.erros())


class TestTextos(unittest.TestCase):
    def tem(self, f, *trechos):
        t = ler(f)
        for x in trechos:
            self.assertIn(x, t, f)

    def test_part_sempre_com_o_lado(self):
        self.tem("skills/part/SKILL.md",
                 '"Skills to read" ALWAYS includes every entry of `info.pitfall_skills`',
                 "every entry of `info.side_skills` whose `paths` match",
                 "repo convention > pitfall skill > generic side skill",
                 "match NO `info.side_skills` glob",
                 "`skills_read` misses a matched pitfall OR side skill",
                 "Side skills go to EXECUTORS only",
                 "pitfall and side skills read (from the handoff json",
                 "`info.side_skills_missing` non-empty, or no catalog: say so ONCE in progress")
        self.tem("skills/part/review.md", "`PITFALLS TO READ`, the side skill paths the executor had (reference only")

    def test_ordem(self):
        self.tem("templates/work-order.md", "ALWAYS the pitfall skills and the side skills",
                 '(Empty: write "none" and the reason.)', "LIBRARY DOC (optional")

    def test_plano(self):
        self.tem("skills/plan/SKILL.md", "Only for an item whose files match NO `side_skills` glob",
                 "the plan warns ONCE", "`/tune-up:setup`, ECC step", "LIBRARY DOC")
        self.tem("templates/phase/goal.md", "every `info.side_skills` entry that matches")
        self.tem("templates/phase/brief.md", "the matched `info.side_skills`")

    def test_readme(self):
        self.tem("README.md", "`skills_by_glob` maps a glob", "`side_skills_missing`")


if __name__ == "__main__":
    unittest.main()
