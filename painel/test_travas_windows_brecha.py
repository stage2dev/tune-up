"""Brechas do gancho no Windows achadas na revisão (rodada 1), provadas em qualquer sistema: o ramo nt entra por
parâmetro (`nt=True`) e o realpath é falso (test_travas_windows.real_falso). Nada chama o claude."""
import sys

sys.dont_write_bytecode = True

import unittest  # noqa: E402

import travas  # noqa: E402
from test_travas import ACAO_CODIGO, ACAO_LEITURA, conf  # noqa: E402
from test_travas_windows import LIB, PROT, U, real_falso  # noqa: E402

MARKET = (U + "\\marketplace-bruno\\tune-up\\painel",)
FORTE = ((ACAO_LEITURA, "deny"), (ACAO_CODIGO, "ask"))


def dec(c, ferr, cmd, cwd=U, nt=True, realpath=real_falso, campo="command"):
    r = travas.decidir(c, ferr, {campo: cmd}, cwd, nt=nt, realpath=realpath)
    return r[0] if r else None


class TesteCurtoComPrefixo(unittest.TestCase):
    """Achado 1: `./` e `..` antes do nome curto não podem sumir com o nome 8.3."""
    CMDS = (("Bash", "tee ./CLAUDE~1/settings.json"), ("Bash", "cp evil ../u/CLAUDE~1/settings.json"))

    def test_ponto_barra_e_parametro_negam(self):
        for acao, esperado in FORTE:
            c = conf(acao, PROT, LIB)
            for ferr, cmd in self.CMDS:
                self.assertEqual(dec(c, ferr, cmd), esperado, (ferr, cmd))
            self.assertIsNone(dec(c, "Bash", "cat ./PROGRA~1/x.txt"))


class TesteRedeNaoResolve(unittest.TestCase):
    """Achados 2 e 4: o gancho nunca chama o realpath em \\\\host (iria à rede) e não deixa passar o que não resolve:
    \\\\host com nome 8.3, \\\\?\\GLOBALROOT, \\\\?\\Volume{..}, \\\\localhost\\c$."""

    def setUp(self):
        self.chamadas = []

    def real(self, p):
        self.chamadas.append(p)
        return real_falso(p)

    def test_unc_com_nome_curto_nega_sem_ir_a_rede(self):
        for acao, esperado in FORTE:
            c = conf(acao, PROT, LIB)
            for ferr, cmd in (("Bash", "cat <//10.255.255.1/s/a~1; rm -rf C:/Users/u/proj/src"),
                              ("Bash", "echo x > C:/Users/u/x/a.json; cat //10.255.255.1/s/a~1")):
                self.assertEqual(dec(c, ferr, cmd, realpath=self.real), esperado, cmd)
            self.assertEqual(dec(c, "Write", "\\\\10.255.255.1\\s\\a~1\\x", realpath=self.real, campo="file_path"),
                             esperado)
        self.assertFalse([p for p in self.chamadas if p.replace("\\", "/").startswith("//")], self.chamadas)

    def test_dispositivo_e_compartilhamento_local(self):
        alvos = ("\\\\?\\GLOBALROOT\\Device\\HarddiskVolume3\\Users\\u\\proj\\.tune-up\\pacote\\acoes\\a.json",
                 "\\\\?\\Volume{0b1c2d3e-0000-0000-0000-100000000000}\\Users\\u\\proj\\.tune-up\\pacote\\acoes\\a.json",
                 "\\\\localhost\\C$\\Users\\u\\proj\\.tune-up\\pacote\\acoes\\a.json",
                 "\\\\127.0.0.1\\c$\\Users\\u\\proj\\.tune-up\\pacote\\acoes\\a.json")
        for acao, esperado in FORTE:
            c = conf(acao, PROT, LIB)
            for alvo in alvos:
                self.assertEqual(dec(c, "Write", alvo, campo="file_path"), esperado, alvo)
        c = conf(ACAO_LEITURA, PROT, LIB)
        for livre in ("\\\\?\\C:\\Users\\u\\proj\\src\\a.txt", "\\\\srv\\share\\a.txt"):
            self.assertIsNone(dec(c, "Write", livre, campo="file_path"), livre)
        self.assertIsNone(dec(c, "Bash", "cat //srv/share/a.txt"))
        self.assertIsNone(dec(c, "Write", "\\\\?\\GLOBALROOT\\x", nt=False, campo="file_path"))  # fora do Windows igual


class TesteProcCygdrive(unittest.TestCase):
    """Achado 5: no MSYS2/Git Bash /proc/cygdrive/c/ é C:\\."""

    def test_proc_cygdrive_nega(self):
        for acao, esperado in FORTE:
            c = conf(acao, ("C:\\Users\\u\\pacote\\acoes",), ())
            self.assertEqual(dec(c, "Bash", "echo x > /proc/cygdrive/c/Users/u/pacote/acoes/a.json"), esperado)


class TesteSubstituicaoAritmeticaNoBash(unittest.TestCase):
    """Achado 6: no Bash `$((..))` não muda nada."""

    def test_aritmetica_segue_livre(self):
        c = conf(ACAO_CODIGO, PROT, LIB)
        self.assertIsNone(dec(c, "Bash", "echo $((1+2)) > a.txt"))


if __name__ == "__main__":
    unittest.main()
