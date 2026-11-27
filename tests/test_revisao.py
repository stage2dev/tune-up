"""Tests for `guarda.py review-save` and `review-pending`. Run: python3 -m unittest tests.test_revisao"""
import json
import os
import re
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
USO = {"ok": False, "usage": True, "lens_ran": None}


def achado(**kw):
    f = {"sev": "HIGH", "file": "a.py", "line": 3, "introduced": True, "proof": "read", "title": "t"}
    f.update(kw)
    return f


def bloco(d):
    return "```json\n%s\n```\n" % (d if isinstance(d, str) else json.dumps(d, ensure_ascii=False))


def resposta(d, veredito=None):
    """A whole reviewer answer: the json block, then the Verdict line."""
    return bloco(d) + "Verdict: %s\n" % (veredito or d["verdict"])


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

    def uso(self, r, erro=""):
        self.assertEqual({k: r[k] for k in USO}, USO, r)
        self.assertEqual(set(r), set(USO) | {"error"})
        self.assertIn(erro, r["error"])
        self.assertLess(len(r["error"]), 120)

    def lido(self, r):
        with open(r["path"], "rb") as f:
            return json.loads(f.read().decode("utf-8"))

    def test_resposta_inteira_com_bloco(self):
        fs = [achado(), achado(sev="critical", introduced=False), achado(sev="Low", line=None, proof="suspected"),
              achado(sev="MEDIUM", proof="observed", title="ação")]
        r = self.salvar("## Findings\nprose\n" + resposta({"verdict": "REJECT", "findings": fs}) + "done.\n")
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
        r = self.salvar(resposta({"verdict": "approve", "findings": []}))
        self.assertEqual(stat.S_IMODE(os.stat(r["path"]).st_mode), 0o600)

    def test_json_puro_e_bom(self):
        puro = json.dumps({"verdict": "APPROVE", "findings": []})
        r = self.salvar(puro)
        self.assertEqual((r["ok"], r["blocking"], r["rejected"]), (True, 0, False))
        self.assertTrue(self.salvar(b"\xef\xbb\xbf" + puro.encode(), chunk="bom")["ok"])

    def test_vale_o_ultimo_bloco(self):
        a, b = {"verdict": "reject", "findings": [achado()]}, {"verdict": "approve", "findings": []}
        r = self.salvar("quoted:\n" + bloco(b) + "```bash\nls\n```\n" + resposta(a, "REJECTED - 0 CRITICAL, 1 HIGH"))
        self.assertEqual((r["rejected"], r["blocking"]), (True, 1))
        # an unbalanced fence earlier does not hide the block; a fence inside a title does not cut it
        r = self.salvar("```\nopen\n" + resposta({"verdict": "reject", "findings": [achado(title="``` x")]}), rodada="2")
        self.assertEqual((r["ok"], r["blocking"]), (True, 1))
        r = self.salvar("```\n%s\n```\nVerdict: reject" % json.dumps(a), rodada="3")  # no `json` after the fence
        self.assertEqual((r["ok"], r["blocking"]), (True, 1))
        # a last block that is broken, cut or not the findings is never replaced by an older valid one
        fim, inteiro = "Verdict: approve\n", json.dumps(a)
        for ultimo in (bloco("{not json"), bloco({"item": "x"}), "```json\n" + inteiro, "```json\n" + inteiro[:60],
                       "```json\n%s\n```json\n" % inteiro, "```json\n%s\n```bash\n" % inteiro,
                       "```\n%s\n```\n" % inteiro[:60] , "```\n{\"findings\": [1,\n```\n", inteiro + "\n",
                       "~~~json\n%s\n~~~\n" % inteiro, "- ```json\n%s\n```\n" % inteiro, "```JSON\n{}\n```\n"):
            self.recusa(self.salvar(bloco(b) + ultimo + fim, rodada="4"), "last block")
        self.recusa(self.salvar(bloco(b) + bloco({"verdict": "", "findings": []}) + fim, rodada="4"), "verdict is not")
        self.assertEqual(len(os.listdir(self.dir)), 3)

    def test_linha_verdict_confere_com_o_json(self):
        ok = {"verdict": "approve", "findings": []}
        um = {"verdict": "reject", "findings": [achado(), achado(introduced=False), achado(sev="LOW")]}
        self.recusa(self.salvar(bloco(ok)), "Verdict")
        self.recusa(self.salvar("Verdict: approve\n" + bloco(ok)), "Verdict")  # only before the block
        for d, linha in ((ok, "REJECTED - 1 CRITICAL, 0 HIGH"), (ok, "REJECTED"), (ok, "APPROVED - 1 CRITICAL"),
                         (ok, "APPROVED, HIGH: 2"), (ok, "BLOCKED"), (ok, "not approved"), (ok, "APPROVED | REJECTED"),
                         (ok, ""), (um, "APPROVED WITH FIXES - 0 CRITICAL, 1 HIGH"), (um, "REJECTED - 0 HIGH"),
                         (um, "REJECTED - 3 HIGH"), (um, "REJECTED - 1 CRITICAL, 1 HIGH"),
                         (ok, "APPROVED\nVerdict: REJECTED"), (ok, "REJECTED\nVerdict: APPROVED")):
            self.recusa(self.salvar(bloco(d) + "Verdict: " + linha), "Verdict")
        self.assertEqual(os.listdir(self.dir), [])
        for i, (d, linha) in enumerate((
                (ok, "Verdict: APPROVED WITH FIXES - 0 CRITICAL, 0 HIGH, 2 MEDIUM"), (ok, "**Verdict:** APPROVED"),
                (ok, "`Verdict: APPROVED - 0 CRITICAL, 0 HIGH, 0 MEDIUM`\r\nlast words"), (um, "Verdict: REJECTED"),
                (um, "> Verdict: REJECTED - 0 CRITICAL, 2 HIGH, 0 MEDIUM"),  # all of them
                (um, "Verdict: **REJECTED** - **0** CRITICAL, **1** HIGH (1 pre-existing)"))):  # only the introduced
            r = self.salvar(bloco(d) + linha, chunk="ok%d" % i)
            self.assertEqual((r["ok"], r.get("rejected")), (True, d is um), linha)

    def test_verdict_dos_agentes_passa(self):
        for lens in V.LENSES:
            with open(os.path.join(RAIZ, "agents", "reviewer-%s.md" % lens), encoding="utf-8") as f:
                formas = re.search(r"`Verdict: (.*?) - N CRITICAL", f.read()).group(1).split(" | ")
            self.assertEqual([V.aprovado(x + " - 0 CRITICAL, 0 HIGH, 0 MEDIUM") for x in formas], [True, True, False])

    def test_so_chaves_conhecidas(self):
        d = {"verdict": "approve", "findings": [achado(extra="x", sev="LOW")], "path": "/etc", "lens": "database"}
        lido = self.lido(self.salvar(resposta(d)))
        self.assertEqual(lido, {"verdict": "approve", "findings": [achado(sev="LOW")], "lens": "security",
                                "chunk": "all", "round": 1})

    def test_answer_file(self):
        arq, ok = os.path.join(self.tmp, "my answer.md"), {"verdict": "approve", "findings": []}

        def de(arquivo, rodada="1"):
            return self.cli("review-save", "--dir", self.dir, "--lens", "security", "--chunk", "all", "--round", rodada,
                            "--answer-file", arquivo, entrada="Verdict: ignored stdin")

        def escreve(texto):
            with open(arq, "wb") as f:
                f.write(texto.encode("utf-8"))
        escreve("prose\nEND\n" + resposta(ok))
        self.assertEqual(self.lido(de(arq))["verdict"], "approve")
        for p in (os.path.join(self.tmp, "missing"), self.dir, "my answer.md"):
            self.uso(de(p, "2"), "answer file")
        if not IS_WIN:
            fifo = os.path.join(self.tmp, "fifo")
            os.mkfifo(fifo)
            self.uso(de(fifo, "2"), "answer file")  # would block
            if os.geteuid():
                os.chmod(arq, 0)
                self.uso(de(arq, "2"), "PermissionError")
                os.chmod(arq, 0o600)
        escreve(" " * (V.MAX_BYTES + 1))
        self.recusa(de(arq, "2"), "too large")
        escreve("")
        self.recusa(de(arq, "2"))

    def test_verdict_recusado(self):
        for i, (v, esp) in enumerate((("Reject: x", True), ("needs changes", True), ("REWORK", True),
                                      ("approve", False), ("not rejected", True), ("**REJECTED**", True),
                                      ("Verdict: REJECTED", True), ("FAIL", True), ("BLOCKED", True), ("not approved", True),
                                      ("approved, but rework", True), ("APPROVED", False), ("approve with notes", False),
                                      ("APPROVED WITH FIXES - 0 CRITICAL, 0 HIGH, 3 MEDIUM", False), ("Aprovado", False),
                                      ("aprovado com correções", False), ("**Approved**", False), ("x", True))):
            r = self.salvar(resposta({"verdict": v, "findings": []}), chunk="v%d" % i)
            self.assertEqual(r["rejected"], esp, v)

    def test_introduced_ausente_conta_e_preexistente_nao_bloqueia(self):
        sem = achado()
        del sem["introduced"]
        r = self.salvar(resposta({"verdict": "approve", "findings": [sem, achado(introduced=False)]}))
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
        a, b = resposta({"verdict": "reject", "findings": [achado()]}), resposta({"verdict": "approve", "findings": []})
        um, dois = self.salvar(a), self.salvar(b, rodada="2")
        self.assertNotEqual(um["path"], dois["path"])
        self.uso(self.salvar(b), "already exists for this lens, chunk and round: use the next --round")
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
            self.uso(self.salvar(resposta({"verdict": "approve", "findings": []}), rodada=rodada))
            self.assertEqual(os.path.exists(alvo), existe)
        with open(os.path.join(self.tmp, "alvo1.txt"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "keep")

    def test_argumentos_ruins(self):
        ok = resposta({"verdict": "approve", "findings": []})
        arq = os.path.join(self.tmp, "arq")
        open(arq, "w").close()
        for p in (os.path.join(self.tmp, "missing"), "scratch dir", ".", arq):
            self.uso(self.salvar(ok, pasta=p), "dir")
        for lens in ("style", "Security", "../x", "security\n"):
            self.uso(self.salvar(ok, lens=lens), "lens")
        for c in ("../../x", "a/b", "a b", "a" * 31, "a\n", "é", "\\a"):
            self.uso(self.salvar(ok, chunk=c), "chunk")
        for n in ("0", "10", "x", "1\n", "١"):
            self.uso(self.salvar(ok, rodada=n), "round")
        self.uso(self.cli("review-save", entrada=ok))
        self.uso(self.cli("review-save", "--dir", "--lens", "security", entrada=ok))
        self.uso(self.cli("review-save", "--dir", self.dir, "--dir", self.dir, entrada=ok))
        self.uso(self.cli("review-save", "--out", "x", entrada=ok))
        self.uso(self.cli("review-save", "--dir", self.dir, "--lens", "security", "--chunk", "a", "--round", "1",
                          "--answer-file", entrada=ok))
        self.assertEqual(os.listdir(self.dir), [])

    def test_rotulo_de_item_do_plano(self):
        for dado, nome in (("item-B1", "item-b1"), ("item-0.1", "item-0-1"), ("item_C2", "item-c2")):
            r = self.salvar(resposta({"verdict": "approve", "findings": []}), chunk=dado)
            self.assertEqual((os.path.basename(r["path"]), self.lido(r)["chunk"]),
                             ("review-part-security-%s-1.json" % nome, nome))

    def test_pasta_sem_escrita(self):
        if IS_WIN or os.geteuid() == 0:
            self.skipTest(SEM_MODOS)
        os.chmod(self.dir, 0o500)
        self.uso(self.salvar(resposta({"verdict": "approve", "findings": []})), "PermissionError")

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
        ok = resposta({"verdict": "approve", "findings": []})
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

    def test_marca_em_qualquer_lugar_da_linha(self):
        for linha in ("- Part B - REVIEW PENDING - since abc", "- Parte B: REVISÃO PENDENTE desde abc",
                      "- 25/11: REVISÃO PENDENTE - Parte B", "- `REVISÃO PENDENTE` - Parte B - desde abc",
                      "| REVIEW PENDING | Part B |", "- [REVIEW PENDING] Part B", "\u26a0\ufe0f REVIEW PENDING - Part B",
                      "<!-- REVIEW PENDING - Part B -->", "- [x] REVIEW PENDING", "- ~~REVIEW PENDING - Part B~~",
                      "- the REVIEW PENDING line is gone", "Part A - REVIEW PENDING - Part A - since x",
                      "- REVIEW PENDING - Part A; Part B", "- REVIEW PENDING - Part A - since a, and Part B",
                      "- REVIEW PENDING - Part A - since a; REVIEW PENDING", "| Part A | REVIEW PENDING | Part B |"):
            for extra in ((), ("--part", "B")):
                self.assertEqual(self.pend("# P\n%s\n" % linha, *extra), {"pending": True, "lines": [linha]}, linha)

    def test_modelo_do_progresso_nao_tem_marca(self):
        with open(os.path.join(RAIZ, "templates", "phase", "progress.md"), encoding="utf-8") as f:
            t = f.read()
        self.assertNotIn("names.review_pending", t)
        with open(os.path.join(RAIZ, "templates", "names.json"), encoding="utf-8") as f:
            idiomas = json.load(f)
        for nomes in idiomas.values():
            r = re.sub(r"\{\{names\.(\w+)\}\}", lambda m: nomes[m.group(1)], t)
            self.assertNotIn("{{names.", r)
            self.assertEqual(self.pend(r), {"pending": False, "lines": []})

    def test_progresso_vazio_e_pendente(self):
        for texto in ("", " \n\t\n", b"\xef\xbb\xbf"):
            self.assertEqual(self.pend(texto), {"pending": True, "lines": [], "error": "progress file is empty"})

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
        for marca in ("* REVISAR", "[ ] REVISAR", "- REVISAR", "1. REVISAR", "\u23f3 REVISAR", "***"):
            self.user_json({"language": "es", "names_override": {"review_pending": marca}})
            for linha in ("- %s - Parte B - desde abc" % marca, "Parte B: " + marca):
                self.assertTrue(self.pend(linha)["pending"], linha)
            self.assertFalse(self.pend("# ok")["pending"], marca)

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
        sys.path.insert(0, os.path.dirname(SCRIPT))
        from tuneup.rota import parte_erro, rota_erro
        script = self.copia_quebrada()
        self.assertEqual(self.pend("# ok\n", script=script), {"pending": True, "lines": [], "error": "import failed"})
        r = self.cli("rota", "--part", "--files", "a.py", "--diff-file", "x", script=script)
        self.assertEqual(r, {"part": True, "risk": True, "reviewers": ["failures", "security", "database"],
                             "models": {"failures": "opus", "security": "opus", "database": "opus"},
                             "effort": "high", "lines": None, "chunks": 1, "why": mock.ANY})
        self.assertEqual(set(r), set(parte_erro(ValueError())))  # same keys as the import-ok error path
        r = self.cli("rota", "--files", "a.py", script=script)
        self.assertEqual(r, dict(rota_erro(ValueError()), why=mock.ANY))


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
