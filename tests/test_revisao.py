"""Tests for `guarda.py review-save` and `review-pending`. Run: python3 -m unittest tests.test_revisao"""
import json
import os
import shutil
import stat
import subprocess
import sys
import unittest
from unittest import mock

from base import IS_WIN, SCRIPT, SEM_MODOS, Base, symlink

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import revisao as V  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(SCRIPT))
RECUSA = {"ok": False, "lens_ran": False}


def achado(**kw):
    f = {"sev": "HIGH", "file": "a.py", "line": 3, "introduced": True, "proof": "read", "title": "t"}
    f.update(kw)
    return f


def bloco(d):
    return "```json\n%s\n```\n" % (d if isinstance(d, str) else json.dumps(d, ensure_ascii=False))


class CLI(Base):
    USER_JSON = None

    def cli(self, *args, entrada="", script=SCRIPT, env=None):
        e = dict(self.env, **(env or {}))
        if isinstance(entrada, str):
            entrada = entrada.encode("utf-8")
        r = subprocess.run([sys.executable, script] + list(args), input=entrada, capture_output=True,
                           env=e, cwd=self.cwd, timeout=20)
        self.assertEqual((r.returncode, r.stderr), (0, b""))
        linhas = r.stdout.decode("ascii").splitlines()
        self.assertEqual(len(linhas), 1, linhas)
        return json.loads(linhas[0])

    def copia_quebrada(self):
        copia = os.path.join(self.tmp, "copia")
        shutil.copytree(os.path.dirname(SCRIPT), copia)
        with open(os.path.join(copia, "tuneup", "__init__.py"), "a", encoding="utf-8") as f:
            f.write("\nraise ImportError('broken on purpose')\n")
        return os.path.join(copia, "guarda.py")


class TestReviewSave(CLI):
    def setUp(self):
        super().setUp()
        self.dir = os.path.join(self.tmp, "scratch dir")
        os.makedirs(self.dir)

    def salvar(self, entrada, lens="security", chunk="all", rodada="1", pasta=None, **kw):
        return self.cli("review-save", "--dir", pasta or self.dir, "--lens", lens, "--chunk", chunk,
                        "--round", rodada, entrada=entrada, **kw)

    def recusa(self, r, erro=""):
        self.assertEqual({k: r[k] for k in RECUSA}, RECUSA, r)
        self.assertNotIn("path", r)
        self.assertIn(erro, r["error"])
        self.assertLess(len(r["error"]), 120)

    def lido(self, r):
        with open(r["path"], "rb") as f:
            return json.loads(f.read().decode("utf-8"))

    def test_resposta_inteira_com_bloco(self):
        fs = [achado(), achado(sev="critical", introduced=False), achado(sev="Low", line=None, proof="suspected"),
              achado(sev="MEDIUM", proof="observed", title="ação")]
        r = self.salvar("## Findings\nprose\n" + bloco({"verdict": "REJECT", "findings": fs}) + "done.\n")
        self.assertEqual(r, {"ok": True, "lens_ran": True, "rejected": True, "blocking": 1,
                             "counts": {"CRITICAL": 1, "HIGH": 1, "MEDIUM": 1, "LOW": 1},
                             "path": os.path.join(self.dir, "review-part-security-all-1.json")})
        d = self.lido(r)
        self.assertEqual((d["lens"], d["chunk"], d["round"], d["verdict"]), ("security", "all", 1, "REJECT"))
        self.assertEqual([f["sev"] for f in d["findings"]], ["HIGH", "CRITICAL", "LOW", "MEDIUM"])
        self.assertEqual(d["findings"][3]["title"], "ação")

    def test_modo_0600(self):
        if IS_WIN:
            self.skipTest(SEM_MODOS)
        r = self.salvar(bloco({"verdict": "approve", "findings": []}))
        self.assertEqual(stat.S_IMODE(os.stat(r["path"]).st_mode), 0o600)

    def test_json_puro_e_bom(self):
        puro = json.dumps({"verdict": "APPROVE", "findings": []})
        r = self.salvar(puro)
        self.assertEqual((r["ok"], r["blocking"], r["rejected"]), (True, 0, False))
        self.assertTrue(self.salvar(b"\xef\xbb\xbf" + puro.encode(), chunk="bom")["ok"])

    def test_vale_o_ultimo_bloco(self):
        a, b = {"verdict": "reject", "findings": [achado()]}, {"verdict": "approve", "findings": []}
        extra = "```bash\nls\n```\n" + bloco({"item": "x"}) + bloco("{not json")
        r = self.salvar(bloco(a) + bloco(b) + extra)
        self.assertEqual((r["rejected"], r["blocking"]), (False, 0))
        # an unbalanced fence earlier does not hide the block; a fence inside a title does not cut it
        r = self.salvar("```\nopen\n" + bloco({"verdict": "reject", "findings": [achado(title="``` x")]}), rodada="2")
        self.assertEqual((r["ok"], r["blocking"]), (True, 1))
        # an invalid last block is not replaced by an older valid one
        self.recusa(self.salvar(bloco(b) + bloco({"verdict": "", "findings": []}), rodada="3"), "verdict")

    def test_verdict_recusado(self):
        for i, (v, esp) in enumerate((("Reject: x", True), ("needs changes", True), ("REWORK", True),
                                      ("approve", False), ("not rejected", False))):
            r = self.salvar(bloco({"verdict": v, "findings": []}), chunk="v%d" % i)
            self.assertEqual(r["rejected"], esp, v)

    def test_introduced_ausente_conta_e_preexistente_nao_bloqueia(self):
        sem = achado()
        del sem["introduced"]
        r = self.salvar(bloco({"verdict": "approve", "findings": [sem, achado(introduced=False)]}))
        self.assertEqual((r["blocking"], r["counts"]["HIGH"]), (1, 2))
        self.assertIs(self.lido(r)["findings"][0]["introduced"], True)

    def test_invalidos(self):
        seg = "SECRET-CONTENT"
        sem = achado()
        del sem["line"]
        ruins = [achado(sev="BLOCKER"), achado(sev=None), achado(proof="guess"), achado(proof=["read"]),
                 achado(proof="READ"), achado(line=True), achado(line="3"), achado(line=1.5), achado(file=""),
                 achado(file=None), achado(title=" "), achado(introduced="yes"), achado(introduced=None),
                 sem, "x", None, achado(sev=seg)]
        casos = [json.dumps({"verdict": "approve", "findings": [achado(), f]}) for f in ruins]
        casos += [json.dumps(x) for x in ({"verdict": 1, "findings": []}, {"verdict": "ok", "findings": {}},
                                          {"verdict": "ok"}, {"findings": []}, [], "x")]
        casos += ["", "no json here " + seg, "{broken " + seg, "[" * 100000,
                  '{"verdict":"ok","findings":[],"x":NaN}', '{"verdict":"ok \\ud800","findings":[]}']
        for c in casos:
            for texto in (c, bloco(c)):
                r = self.salvar(texto)
                self.recusa(r)
                self.assertNotIn(seg, json.dumps(r))
        self.recusa(self.salvar(b"\xff\xfe" + bloco({"verdict": "ok", "findings": []}).encode()), "UTF-8")
        self.assertEqual(os.listdir(self.dir), [])

    def test_entrada_gigante(self):
        ok = json.dumps({"verdict": "approve", "findings": []})
        self.recusa(self.salvar(ok + " " * V.MAX_BYTES), "too large")
        self.assertEqual(os.listdir(self.dir), [])
        self.assertTrue(self.salvar(ok + " " * (V.MAX_BYTES - len(ok)))["ok"])

    def test_nome_unico_por_rodada(self):
        a, b = bloco({"verdict": "reject", "findings": [achado()]}), bloco({"verdict": "approve", "findings": []})
        um, dois = self.salvar(a), self.salvar(b, rodada="2")
        self.assertNotEqual(um["path"], dois["path"])
        self.recusa(self.salvar(b), "already exists")
        self.assertEqual(self.lido(um)["verdict"], "reject")  # round 1 untouched
        self.assertTrue(self.salvar(a, lens="failures")["ok"])
        self.assertTrue(self.salvar(a, chunk="item-b1")["ok"])
        self.assertEqual(len(os.listdir(self.dir)), 4)

    def test_symlink_recusado(self):
        for rodada, existe in (("1", True), ("2", False)):
            alvo = os.path.join(self.tmp, "alvo%s.txt" % rodada)
            if existe:
                with open(alvo, "w", encoding="utf-8") as f:
                    f.write("keep")
            symlink(alvo, os.path.join(self.dir, "review-part-security-all-%s.json" % rodada))
            self.recusa(self.salvar(bloco({"verdict": "approve", "findings": []}), rodada=rodada))
            self.assertEqual(os.path.exists(alvo), existe)
        with open(os.path.join(self.tmp, "alvo1.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "keep")

    def test_argumentos_ruins(self):
        ok = bloco({"verdict": "approve", "findings": []})
        arq = os.path.join(self.tmp, "arq")
        open(arq, "w").close()
        for p in (os.path.join(self.tmp, "missing"), "scratch dir", ".", arq):
            self.recusa(self.salvar(ok, pasta=p), "dir")
        for lens in ("style", "Security", "../x", "security\n"):
            self.recusa(self.salvar(ok, lens=lens), "lens")
        for c in ("A", "../../x", "a/b", "a b", "a" * 31, "a\n", "é", "a.b"):
            self.recusa(self.salvar(ok, chunk=c), "chunk")
        for n in ("0", "10", "x", "1\n", "١"):
            self.recusa(self.salvar(ok, rodada=n), "round")
        self.recusa(self.cli("review-save", entrada=ok))
        self.recusa(self.cli("review-save", "--dir", "--lens", "security", entrada=ok))
        self.recusa(self.cli("review-save", "--dir", self.dir, "--dir", self.dir, entrada=ok))
        self.recusa(self.cli("review-save", "--out", "x", entrada=ok))
        self.assertEqual(os.listdir(self.dir), [])

    def test_pasta_sem_escrita(self):
        if IS_WIN or os.geteuid() == 0:
            self.skipTest(SEM_MODOS)
        os.chmod(self.dir, 0o500)
        self.recusa(self.salvar(bloco({"verdict": "approve", "findings": []})), "PermissionError")

    def test_erro_de_escrita_nao_deixa_arquivo(self):
        p = os.path.join(self.dir, "x.json")
        real = os.fdopen

        def cheio(fd, modo):
            f = real(fd, modo)
            f.write(b"half")
            m = mock.MagicMock()
            m.__enter__.return_value.write.side_effect = OSError("disk full")
            m.__exit__.side_effect = lambda *a: f.close()
            return m
        with mock.patch.object(V.os, "fdopen", cheio):
            with self.assertRaises(OSError):
                V.gravar(p, b"data")
        self.assertEqual(os.listdir(self.dir), [])
        V.gravar(p, b"a\nb\n")  # the name is free again
        with open(p, "rb") as f:
            self.assertEqual(f.read(), b"a\nb\n")

    def test_excecao_e_import_quebrado_recusam(self):
        ok = bloco({"verdict": "approve", "findings": []})
        self.recusa(self.salvar(ok, env={"TUNEUP_FAKE_EXCECAO": "1"}), "RuntimeError")
        self.recusa(self.salvar(ok, script=self.copia_quebrada()), "import failed")
        self.assertEqual(os.listdir(self.dir), [])


class TestReviewPending(CLI):
    def progresso(self, texto):
        p = os.path.join(self.tmp, "my PROGRESS.md")
        with open(p, "wb") as f:
            f.write(texto if isinstance(texto, bytes) else texto.encode("utf-8"))
        return p

    def pend(self, texto, *extra, **kw):
        return self.cli("review-pending", "--file", self.progresso(texto), *extra, **kw)

    def test_sem_marca(self):
        self.assertEqual(self.pend("# Progress\n\n- Part A closed\n"), {"pending": False, "lines": []})

    def test_marca_en_e_pt(self):
        for linha in ("- REVIEW PENDING - Part B - since abc123 (items B1, B2)", "- REVISÃO PENDENTE - Parte B - desde abc",
                      "REVIEW PENDING", "## Review pending: x", "> - **revisão pendente** - Parte B", "1. REVIEW PENDING",
                      "- [ ] REVIEW PENDING", "\t* REVISAO PENDENTE", "- REVISÃO PENDENTE"):
            for texto in ("# P\n%s\nx\n" % linha, "﻿%s\r\n" % linha):
                for extra in ((), ("--part", "B"), ("--part", "b"), ("--part", "Part B"), ("--part", "Parte B")):
                    self.assertEqual(self.pend(texto, *extra), {"pending": True, "lines": [linha.strip()]}, (linha, extra))

    def test_mencao_no_meio_nao_conta(self):
        t = "- the REVIEW PENDING line is gone\nwrite `REVISÃO PENDENTE` here\n- `REVIEW PENDING` marker\n"
        self.assertEqual(self.pend(t), {"pending": False, "lines": []})

    def test_outra_parte_de_fora_so_com_rotulo_sozinho(self):
        outra = ("- REVIEW PENDING - Part A - since abc (items A1)", "- **REVISÃO PENDENTE** - Parte A2 - desde abc",
                 "**REVIEW PENDING - Part A**", "REVIEW PENDING: Part A since abc", "- REVIEW PENDING — Part B.1 — since a")
        for linha in outra:
            self.assertFalse(self.pend(linha, "--part", "B")["pending"], linha)
            self.assertTrue(self.pend(linha)["pending"], linha)
        conta = ("- REVIEW PENDING - Part A, B - since abc", "- REVIEW PENDING - Part A and B - since abc",
                 "- REVIEW PENDING - Part A/B", "- REVIEW PENDING - Part A-C - since x", "- REVIEW PENDING - Part B. - since x",
                 "- REVIEW PENDING - Parts A, B", "- REVIEW PENDING - since abc (Part A)", "- REVIEW PENDING")
        for linha in conta:
            self.assertTrue(self.pend(linha, "--part", "B")["pending"], linha)

    def test_linha_encurtada(self):
        r = self.pend("- REVIEW PENDING - Part B - since " + "x" * 500)
        self.assertEqual([len(x) for x in r["lines"]], [200])

    def test_marca_do_usuario(self):
        self.user_json({"language": "es", "names_override": {"review_pending": "REVISIÓN PENDIENTE"}})
        self.assertTrue(self.pend("- REVISIÓN PENDIENTE - Parte B - since abc", "--part", "B")["pending"])

    def test_duvida_e_pendente(self):
        bom = self.progresso("# ok\n")
        casos = [("--file", os.path.join(self.tmp, "missing.md")), ("--file", self.tmp), (), ("--file",), ("--part", "B"),
                 ("--file", bom, "--part", ""), ("--file", bom, "--part"), ("--file", bom, "--part", "<X>"),
                 ("--file", bom, "--part", "A B"), ("--file", bom, "--x", "y"), ("--file", bom, "x")]
        for c in casos:
            r = self.cli("review-pending", *c)
            self.assertEqual((r["pending"], r["lines"]), (True, []), c)
            self.assertTrue(r["error"], c)
        for b in (b"\xff\xfe", "REVIEW PENDING".encode("utf-16-le"), "REVISÃO PENDENTE".encode("latin-1")):
            self.assertIn("error", self.pend(b))
        r = self.pend("# ok\n", env={"TUNEUP_FAKE_EXCECAO": "1"})
        self.assertEqual(r, {"pending": True, "lines": [], "error": "error (RuntimeError)"})

    def test_names_json(self):
        copia = os.path.join(self.tmp, "plugin")
        shutil.copytree(os.path.dirname(SCRIPT), os.path.join(copia, "scripts"))
        script, names = os.path.join(copia, "scripts", "guarda.py"), os.path.join(copia, "templates", "names.json")
        self.assertTrue(self.pend("# ok\n", script=script)["pending"])  # no names.json
        os.makedirs(os.path.dirname(names))
        for conteudo, erro in (("{}", False), ('{"en": {"goal": "G.md"}}', False), ('{"en": {"review_pending": ""}}', False),
                               ("{broken", True), ("[]", True), ('{"en": 1}', True)):
            with open(names, "w", encoding="utf-8") as f:
                f.write(conteudo)
            r = self.pend("# ok\n", script=script)
            self.assertEqual((r["pending"], "error" in r), (erro, erro), conteudo)
            if not erro:  # built-in markers
                for m in ("REVIEW PENDING", "REVISÃO PENDENTE"):
                    self.assertTrue(self.pend("- " + m, script=script)["pending"], conteudo)

    def test_import_quebrado(self):
        script = self.copia_quebrada()
        self.assertEqual(self.pend("# ok\n", script=script), {"pending": True, "lines": [], "error": "import failed"})
        r = self.cli("rota", "--part", "--files", "a.py", "--diff-file", "x", script=script)
        self.assertEqual(r, {"part": True, "risk": True, "reviewers": ["failures", "security", "database"],
                             "model": "opus", "effort": "high", "lines": None, "chunks": 1, "why": mock.ANY})
        self.assertEqual(self.cli("rota", "--files", "a.py", script=script)["executor"], "tune-up:executor-opus")


class TestShip(unittest.TestCase):
    def test_ship_recusa(self):
        with open(os.path.join(RAIZ, "skills", "ship", "SKILL.md"), encoding="utf-8") as f:
            t = f.read()
        cmd = 'sh "${CLAUDE_PLUGIN_ROOT}/scripts/py" scripts/guarda.py review-pending'
        self.assertIn("Bash(%s:*)" % cmd, t.split("---")[1])
        passo = next(l for l in t.splitlines() if l.startswith("3. "))
        for s in (cmd + ' --file "', "--part <X>", "no JSON = STOP: no push, no PR", "names.need_you",
                  "Go on only with `pending: false`", "owner's explicit words"):
            self.assertIn(s, passo)
        self.assertLess(t.index(cmd + " --file"), t.index("**Gate.**"))
        self.assertLess(t.index(cmd + " --file"), t.index("git push"))

    def test_names_json_tem_a_marca(self):
        with open(os.path.join(RAIZ, "templates", "names.json"), encoding="utf-8") as f:
            n = json.load(f)
        self.assertEqual((n["en"]["review_pending"], n["pt-BR"]["review_pending"]), V.MARKERS)


if __name__ == "__main__":
    unittest.main()
