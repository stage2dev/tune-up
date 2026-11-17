"""Tests: BOM-tolerant reads (PowerShell 5.1 saves UTF-8 with BOM) and forward slashes in info paths."""
import hashlib
import os
import sys
import unittest
from unittest import mock

from base import IS_WIN, SEM_MODOS, Base

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
from tuneup import agent, config, info, usuario  # noqa: E402
import titulo_terminal  # noqa: E402

BOM = b"\xef\xbb\xbf"


class TestBom(Base):
    USER_JSON = None

    def escrever(self, nome, dados, bom=True):
        p = os.path.join(self.tmp, nome)
        with open(p, "wb") as f:
            f.write((BOM if bom else b"") + dados)
        return p

    def env_proprio(self):
        return mock.patch.dict(os.environ, {"HOME": self.tmp, "USERPROFILE": self.tmp,
                                            "CLAUDE_PLUGIN_DATA": self.dados})

    def test_user_json_with_bom(self):
        for bom in (True, False):
            p = self.escrever("u.json", b'{"owner": "Ana"}', bom)
            with mock.patch.dict(os.environ, {"TUNEUP_USER_JSON": p}), mock.patch.dict(usuario._CACHE, clear=True):
                u, existe = usuario.ler_usuario()
            self.assertTrue(existe, bom)
            self.assertEqual(u["owner"], "Ana")

    @unittest.skipIf(IS_WIN, SEM_MODOS)
    def test_project_config_with_bom_and_hash_on_raw_bytes(self):
        perfil = os.path.join(self.tmp, "proj", ".tune-up")
        os.makedirs(perfil)
        os.chmod(perfil, 0o700)
        dados = b'{"language": "en"}'
        p = os.path.join(perfil, "config.json")
        for bom in (True, False):
            with open(p, "wb") as f:
                f.write((BOM if bom else b"") + dados)
            os.chmod(p, 0o600)
            with self.env_proprio():
                proj, erro, _ = config.ler_config_projeto(perfil)
            self.assertIsNone(erro, bom)
            self.assertEqual(proj, {"language": "en"})
        # trust is computed on the raw bytes, BOM included: unchanged versus the old code
        with open(p, "wb") as f:
            f.write(BOM + dados)
        os.chmod(p, 0o600)
        with self.env_proprio():
            config.confiar(p)
            _, erro, confiado = config.ler_config_projeto(perfil)
            with open(config.arquivo_confiaveis(), encoding="utf-8") as f:
                linhas = f.read().splitlines()
        self.assertIsNone(erro)
        self.assertIs(confiado, True)
        self.assertEqual(linhas[-1].split("\t")[1], hashlib.sha256(BOM + dados).hexdigest())

    @unittest.skipIf(IS_WIN, SEM_MODOS)
    def test_trust_file_with_bom(self):
        p = os.path.join(self.dados, "perfis_confiaveis.txt")
        os.makedirs(self.dados, mode=0o700, exist_ok=True)
        with open(p, "wb") as f:
            f.write(BOM + ("/a/b\t" + "0" * 64 + "\n").encode())
        os.chmod(p, 0o600)
        with self.env_proprio(), mock.patch.object(config, "arquivo_confiaveis", lambda: p):
            self.assertEqual(config.perfis_confiaveis(), {"/a/b": "0" * 64})

    def test_agent_frontmatter_with_bom(self):
        p = self.escrever("a.md", b"---\nname: x\nmodel: opus\n---\nbody\n")
        self.assertEqual(agent.modelo_frontmatter(p), "opus")

    def test_titulo_terminal_with_bom_and_crlf(self):
        p = self.escrever("settings.json", b'{\r\n    "a": 1\r\n}\r\n')
        item = titulo_terminal.tratar(p, "aplicar")
        self.assertNotIn("erro", item)
        self.assertEqual(item["depois"], "aplicado")
        with open(p, "rb") as f:
            novo = f.read()
        self.assertTrue(novo.startswith(BOM))  # BOM kept
        self.assertNotIn(b"\r\r", novo)  # CRLF not doubled
        self.assertTrue(novo.startswith(BOM + b'{\r\n    "a": 1'))  # untouched part is byte-identical
        self.assertEqual(novo.count(b"\n"), novo.count(b"\r\n"))  # no bare LF: not mixed
        # LF file stays pure LF
        p = self.escrever("lf.json", b'{\n    "a": 1\n}\n', bom=False)
        self.assertEqual(titulo_terminal.tratar(p, "aplicar")["depois"], "aplicado")
        with open(p, "rb") as f:
            lf = f.read()
        self.assertNotIn(b"\r", lf)
        self.assertEqual(lf.count(b"\n"), 4)


class TestInfoBarras(Base):
    def montar(self, nt):
        src = os.path.join(self.tmp, "src\\x")  # a backslash is a legal filename character on POSIX
        os.makedirs(os.path.join(src, ".git"), exist_ok=True)
        cwd = os.path.join(self.tmp, "pro\\j")
        os.makedirs(cwd, exist_ok=True)
        self.user_json({"plugin_source": src})
        with mock.patch.dict(os.environ, self.env), mock.patch.object(info, "NT", nt), \
                mock.patch.dict(usuario._CACHE, clear=True):
            return info.montar_info(cwd)

    @unittest.skipIf(IS_WIN, "needs a backslash in a POSIX file name")
    def test_nt_emits_forward_slashes_posix_unchanged(self):
        d = self.montar(True)
        for campo in ("plans_dir", "plugin_source"):
            self.assertNotIn("\\", d[campo], campo)
        self.assertIn("src/x", d["plugin_source"])
        d = self.montar(False)  # POSIX: byte-identical, the backslash is part of the name
        self.assertIn("src\\x", d["plugin_source"])
        self.assertIn("pro\\j", d["plans_dir"])
        self.assertEqual(info._fwd("a\\b"), "a\\b")


if __name__ == "__main__":
    unittest.main()
