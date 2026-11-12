"""Windows nativo: claude.exe no lugar do claude.cmd e porta exclusiva do servidor.

Os caminhos do Windows rodam em qualquer sistema (parâmetro `nt` e um `which` que
imita o do Windows); só a disputa real de porta com WinError 10048 exige Windows.
"""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from http.server import BaseHTTPRequestHandler  # noqa: E402
from unittest import mock  # noqa: E402

import config  # noqa: E402
import painel  # noqa: E402
import servidor_http  # noqa: E402


def which_windows(pasta):
    """Imita shutil.which do Windows num PATH com uma pasta só (PATHEXT .COM;.EXE;.BAT;.CMD)."""
    def which(nome):
        if os.path.isabs(nome):
            return nome if os.path.isfile(nome) else None
        exts = [""] if os.path.splitext(nome)[1] else [".com", ".exe", ".bat", ".cmd"]
        for ext in exts:
            c = os.path.join(pasta, nome + ext)
            if os.path.isfile(c):
                return c
        return None
    return which


def tocar(caminho):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "wb") as f:
        f.write(b"x")


class TesteClaudeBin(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.path = os.path.join(self.tmp, "bin")
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.path)
        os.makedirs(self.home)

    def resolver(self, valor="claude", nt=True):
        avisos = []
        r = config.resolver_claude_bin(valor, avisos, nt=nt, which=which_windows(self.path), home=self.home)
        return r, avisos

    def test_so_cmd_recusa_e_avisa(self):
        tocar(os.path.join(self.path, "claude.cmd"))
        r, avisos = self.resolver()
        self.assertFalse(r.lower().endswith((".cmd", ".bat")), r)
        self.assertEqual(r, "claude")
        self.assertEqual(len(avisos), 1)
        self.assertIn("claude.cmd", avisos[0])
        self.assertIn("claude.exe", avisos[0])

    def test_cmd_bat_configurado_sem_exe_nunca_volta(self):
        """Um .cmd/.bat iria pelo cmd.exe, que relê o pedido: vira 'claude', que só acha .exe."""
        for nome in ("claude.cmd", "claude.bat"):
            tocar(os.path.join(self.path, nome))
        for valor in ("claude.cmd", "claude.BAT", os.path.join(self.path, "claude.cmd"),
                      os.path.join(self.path, "claude.bat"), "C:\\npm\\claude.cmd", "claude.cmd. "):
            r, avisos = self.resolver(valor)
            self.assertEqual(r, "claude", valor)
            self.assertEqual(len(avisos), 1, valor)
            self.assertIn("claude.exe", avisos[0])
        self.assertEqual(self.resolver("claude.cmd", nt=False), ("claude.cmd", []))

    def test_exe_no_path_vira_caminho_absoluto(self):
        exe = os.path.join(self.path, "claude.exe")
        tocar(exe)
        tocar(os.path.join(self.path, "claude.cmd"))
        r, avisos = self.resolver()
        self.assertEqual((r, avisos), (exe, []))
        self.assertTrue(os.path.isabs(r))

    def test_cmd_configurado_cai_no_exe_do_instalador_nativo(self):
        tocar(os.path.join(self.path, "claude.cmd"))
        nativo = os.path.join(self.home, ".local", "bin", "claude.exe")
        tocar(nativo)
        r, avisos = self.resolver(os.path.join(self.path, "claude.cmd"))
        self.assertEqual((r, avisos), (nativo, []))

    def test_nada_achado_mantem_valor_e_avisa(self):
        r, avisos = self.resolver()
        self.assertEqual(r, "claude")
        self.assertEqual(len(avisos), 1)

    def test_posix_nao_muda(self):
        tocar(os.path.join(self.path, "claude.cmd"))
        tocar(os.path.join(self.path, "claude.exe"))
        self.assertEqual(self.resolver(nt=False), ("claude", []))
        self.assertEqual(self.resolver("~/x/claude", nt=False), ("~/x/claude", []))

    @unittest.skipIf(os.name == "nt", "o padrão de fora do Windows")
    def test_carregar_fora_do_windows_guarda_claude(self):
        tocar(os.path.join(self.path, "claude.exe"))
        with mock.patch.dict(os.environ, {"PATH": self.path}):
            cfg = config.carregar(self.tmp, home=self.home)
        self.assertEqual(cfg["claude_bin"], "claude")

    @unittest.skipUnless(os.name == "nt", "shutil.which de verdade só resolve PATHEXT no Windows")
    def test_carregar_no_windows_real(self):
        tocar(os.path.join(self.path, "claude.cmd"))
        with mock.patch.dict(os.environ, {"PATH": self.path}):
            cfg = config.carregar(self.tmp, home=self.home)
        self.assertFalse(cfg["claude_bin"].lower().endswith(".cmd"))
        self.assertTrue(any("claude.exe" in a for a in cfg["avisos"]))


class SoqueteFalso:
    def __init__(self):
        self.opcoes = []

    def setsockopt(self, nivel, opcao, valor):
        self.opcoes.append((nivel, opcao, valor))

    def bind(self, endereco):
        self.endereco = endereco

    def getsockname(self):
        return ("127.0.0.1", 4321)


class TesteServidorExclusivo(unittest.TestCase):
    EXCLUSIVO = -5  # valor de SO_EXCLUSIVEADDRUSE no Windows (~SO_REUSEADDR)

    def ligar(self, nt):
        classe = servidor_http.fazer_classe(nt=nt)
        srv = classe(("127.0.0.1", 0), BaseHTTPRequestHandler, bind_and_activate=False)
        srv.socket.close()
        srv.socket = SoqueteFalso()
        with mock.patch.object(socket, "SO_EXCLUSIVEADDRUSE", self.EXCLUSIVO, create=True), \
                mock.patch.object(socket, "getfqdn", lambda h="": "localhost"):
            srv.server_bind()
        return classe, srv.socket.opcoes

    def test_classe_segue_o_sistema(self):
        self.assertEqual(servidor_http.ServidorPainel.allow_reuse_address, os.name != "nt")
        self.assertTrue(servidor_http.ServidorPainel.daemon_threads)

    def test_nt_pede_porta_exclusiva_sem_reuso(self):
        classe, opcoes = self.ligar(nt=True)
        self.assertFalse(classe.allow_reuse_address)
        self.assertIn((socket.SOL_SOCKET, self.EXCLUSIVO, 1), opcoes)
        self.assertNotIn(socket.SO_REUSEADDR, [o[1] for o in opcoes])

    def test_posix_igual_a_antes(self):
        classe, opcoes = self.ligar(nt=False)
        self.assertTrue(classe.allow_reuse_address)
        self.assertNotIn(self.EXCLUSIVO, [o[1] for o in opcoes])
        self.assertIn((socket.SOL_SOCKET, socket.SO_REUSEADDR, 1), opcoes)

    def test_criar_servidor_usa_a_classe(self):
        app = types.SimpleNamespace(porta=None)
        srv = painel.criar_servidor(app, 0)
        self.addCleanup(srv.server_close)
        self.assertIsInstance(srv, servidor_http.ServidorPainel)
        self.assertTrue(srv.daemon_threads)
        self.assertEqual(app.porta, srv.server_address[1])

    def test_segundo_painel_na_mesma_porta_falha(self):
        app = types.SimpleNamespace(porta=None)
        primeiro = painel.criar_servidor(app, 0)
        self.addCleanup(primeiro.server_close)
        with self.assertRaises(OSError) as ctx:
            segundo = painel.criar_servidor(types.SimpleNamespace(porta=None), app.porta)
            segundo.server_close()
        if os.name == "nt":
            self.assertEqual(getattr(ctx.exception, "winerror", None), 10048)

    @unittest.skipUnless(os.name == "nt", "WinError 10048 só existe no Windows")
    def test_windows_segundo_bind_winerror_10048(self):
        primeiro = servidor_http.ServidorPainel(("127.0.0.1", 0), BaseHTTPRequestHandler)
        self.addCleanup(primeiro.server_close)
        with self.assertRaises(OSError) as ctx:
            servidor_http.ServidorPainel(("127.0.0.1", primeiro.server_address[1]), BaseHTTPRequestHandler)
        self.assertEqual(ctx.exception.winerror, 10048)


if __name__ == "__main__":
    unittest.main()
