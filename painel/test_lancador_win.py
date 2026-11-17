"""Windows e codificação no lançador e no leitor: rodam em qualquer sistema.

A decodificação é provada num Python filho com a codificação do sistema em ASCII
(LC_ALL=C, sem UTF-8 forçado): é o mesmo tipo de falha que o cp1252 do Windows dá.
"""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import abrir_win  # noqa: E402
import agentes  # noqa: E402
import lancador  # noqa: E402
import leitor  # noqa: E402
from test_lancador import ACOES_TESTE, CLIFalso, cfg_teste  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ESTADO = {"fases": []}

# O neto escreve UTF-8 cru (lancador) ou com print (leitor: só sai UTF-8 se o env tiver PYTHONUTF8=1).
NETO_BYTES = "import sys; sys.stdout.buffer.write('backgrounded \\u00b7 abc123\\n'.encode('utf-8'))"
NETO_PRINT = "print('backgrounded \\u00b7 abc123')"
FILHO = """import sys, json
sys.path.insert(0, %r)
import lancador, leitor
neto = [sys.executable, '-c', sys.argv[2]]
if sys.argv[1] == 'lancador':
    cod, out, err = lancador.rodar_padrao(neto, None, 30)
elif sys.argv[1] == 'agentes':
    import agentes
    cod, out, err = agentes._rodar_padrao(neto, None, 30)
else:
    ok, out, err = leitor.rodar(neto, None, 30)
m = lancador.RE_SAIDA.search(out)
sys.stdout.write(json.dumps({'id': m.group(1) if m else None}))
"""


def rodar_filho_sem_utf8(qual, neto):
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHONUTF8", "PYTHONIOENCODING", "LC_", "LANG"))}
    # PYTHONUTF8=0 também chega ao neto: sem o PYTHONUTF8=1 do leitor, o print dele não sai em UTF-8.
    env.update(LC_ALL="C", PYTHONCOERCECLOCALE="0", PYTHONUTF8="0")
    r = subprocess.run([sys.executable, "-X", "utf8=0", "-c", FILHO % AQUI, qual, neto], env=env,
                       capture_output=True, timeout=60, cwd=AQUI)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")


class TestDecodificacao(unittest.TestCase):
    def test_lancador_le_utf8_com_locale_nao_utf8(self):
        cod, out, err = rodar_filho_sem_utf8("lancador", NETO_BYTES)
        self.assertEqual(cod, 0, err[-400:])
        self.assertEqual(json.loads(out), {"id": "abc123"})

    def test_leitor_le_utf8_e_filho_python_escreve_utf8(self):
        cod, out, err = rodar_filho_sem_utf8("leitor", NETO_PRINT)
        self.assertEqual(cod, 0, err[-400:])
        self.assertEqual(json.loads(out), {"id": "abc123"})

    def test_agentes_le_utf8_com_locale_nao_utf8(self):
        """`claude agents --json` com nome de sessão acentuado (o mesmo erro, em agentes.py)."""
        cod, out, err = rodar_filho_sem_utf8("agentes", NETO_BYTES)
        self.assertEqual(cod, 0, err[-400:])
        self.assertEqual(json.loads(out), {"id": "abc123"})

    def test_kwargs_do_subprocess(self):
        falso = mock.Mock(return_value=mock.Mock(returncode=0, stdout="x", stderr=""))
        with mock.patch.object(lancador.subprocess, "run", falso):
            lancador.rodar_padrao(["a"], None, 5)
        kw = falso.call_args[1]
        self.assertEqual((kw["encoding"], kw["errors"]), ("utf-8", "replace"))
        self.assertNotIn("text", kw)
        with mock.patch.object(leitor.subprocess, "run", falso):
            leitor.rodar(["a"], None, 5)
        kw = falso.call_args[1]
        self.assertEqual((kw["encoding"], kw["errors"], kw["env"]["PYTHONUTF8"]), ("utf-8", "replace", "1"))
        self.assertNotIn("text", kw)
        with mock.patch.object(agentes.subprocess, "run", falso):
            agentes._rodar_padrao(["a"], None, 5)
        kw = falso.call_args[1]
        self.assertEqual((kw["encoding"], kw["errors"]), ("utf-8", "replace"))
        self.assertNotIn("text", kw)


class TestLeitorSaidaVazia(unittest.TestCase):
    def test_none_nao_chega_ao_json_loads(self):
        with mock.patch.object(leitor, "rodar", return_value=(True, None, None)):
            self.assertEqual(leitor.ler_prs(AQUI)[0], [])
            self.assertEqual(leitor.ler_sessoes(AQUI, "claude")[0], [])
            with mock.patch.object(leitor, "cfg_atual", return_value={"guarda": "g.py", "workspace": AQUI}):
                self.assertEqual(leitor.ler_info(AQUI)[0], None)


class TestAbrirWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        os.makedirs(os.path.join(self.tmp, "acoes"))
        with open(os.path.join(self.tmp, "acoes", "t.json"), "w") as f:
            json.dump(ACOES_TESTE, f)
        self.cli = CLIFalso()

    def lanc(self, plataforma, claude_bin="claude"):
        cfg = cfg_teste(self.tmp, claude_bin=claude_bin)
        return lancador.Lancador(cfg, lambda: ESTADO, rodar=self.cli, plataforma=plataforma)

    def iniciar(self, l):
        ex = l.iniciar("t.leve", {})
        self.cli.chamadas.clear()
        return ex["id"]

    def test_comando_attach_por_plataforma(self):
        bin_ = "C:\\Program Files\\Claude\\claude.exe"
        self.assertEqual(self.lanc("win32", bin_).comando_attach("abc123"),
                         '"C:\\Program Files\\Claude\\claude.exe" attach abc123')
        self.assertEqual(self.lanc("darwin", "/opt/my claude").comando_attach("abc123"),
                         "'/opt/my claude' attach abc123")

    def test_abrir_com_windows_terminal(self):
        l = self.lanc("win32")
        i = self.iniciar(l)
        with mock.patch.object(abrir_win.shutil, "which", lambda n: "C:\\wt.exe" if n == "wt.exe" else None):
            l.abrir_janela = lambda c, w, nova: self.cli.chamadas.append((list(c), w, nova)) or True
            r = l.abrir(i)
        self.assertEqual(r, {"ok": True, "comando": "claude attach " + i})
        self.assertEqual(self.cli.chamadas, [(["wt.exe", "-w", "0", "new-tab", "cmd", "/k", "claude", "attach", i],
                                              self.tmp, False)])

    def test_abrir_sem_windows_terminal_abre_console_nova(self):
        l = self.lanc("win32")
        i = self.iniciar(l)
        l.abrir_janela = lambda c, w, nova: self.cli.chamadas.append((list(c), w, nova)) or True
        with mock.patch.object(abrir_win.shutil, "which", lambda n: None):
            self.assertTrue(l.abrir(i)["ok"])
        self.assertEqual(self.cli.chamadas, [(["cmd", "/k", "claude", "attach", i], self.tmp, True)])

    def test_abrir_nao_passa_pipes_nem_herda_handles(self):
        """Com capture_output a janela nova herda o pipe e o pedido fica preso até ela fechar."""
        l = self.lanc("win32")
        i = self.iniciar(l)
        l.rodar = lancador.rodar_padrao
        proc = mock.Mock()
        proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 3)
        with mock.patch.object(abrir_win.shutil, "which", lambda n: None), \
                mock.patch.object(subprocess, "run") as run, \
                mock.patch.object(subprocess, "Popen", return_value=proc) as popen:
            r = l.abrir(i)
        self.assertTrue(r["ok"])
        run.assert_not_called()
        kw = popen.call_args[1]
        for proibido in ("stdin", "stdout", "stderr", "capture_output"):
            self.assertNotIn(proibido, kw)
        self.assertTrue(kw["close_fds"])
        self.assertEqual(kw["creationflags"], abrir_win.CREATE_NEW_CONSOLE)
        self.assertEqual(popen.call_args[0][0], ["cmd", "/k", "claude", "attach", i])

    @unittest.skipUnless(os.name == "nt", "abrir uma console de verdade só existe no Windows")
    def test_windows_real_volta_logo(self):
        import time
        t0 = time.time()
        self.assertTrue(abrir_win.abrir_janela_padrao(["cmd", "/c", "exit", "0"], self.tmp, True))
        self.assertLess(time.time() - t0, abrir_win.ESPERA + 5)

    def test_abrir_recusa_metacaractere_do_cmd(self):
        i = self.iniciar(self.lanc("win32"))
        for ruim in ("claude&calc", "a;b", "c|d", "x%PATH%", 'q"z', "a^b"):
            l = self.lanc("win32", ruim)
            l.abrir_janela = lambda c, w, nova: self.cli.chamadas.append((list(c), w, nova)) or True
            with mock.patch.object(abrir_win.shutil, "which", lambda n: "wt.exe"):
                r = l.abrir(i)
            self.assertFalse(r["ok"], ruim)
            self.assertEqual(self.cli.chamadas, [], ruim)
            gravado = []
            self.assertIsNone(abrir_win.abrir(ruim, "abc123", ".", lambda c, w, nova: gravado.append(c) or True,
                                              which=lambda n: None), ruim)
            self.assertEqual(gravado, [], ruim)

    def test_darwin_e_linux_iguais(self):
        l = self.lanc("darwin")
        i = self.iniciar(l)
        self.assertEqual(l.abrir(i), {"ok": True, "comando": "claude attach " + i})
        self.assertEqual(self.cli.chamadas[0][0][0], "osascript")
        self.cli.chamadas.clear()
        self.assertEqual(self.lanc("linux").abrir(i), {"ok": False, "comando": "claude attach " + i})
        self.assertEqual(self.cli.chamadas, [])


if __name__ == "__main__":
    unittest.main()
