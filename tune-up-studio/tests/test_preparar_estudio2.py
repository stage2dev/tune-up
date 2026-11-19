"""More preparar_estudio.py cases (A4b): signature stamp of --so-instalar and lock errors. No network, no real npm."""
import errno
import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_preparar_estudio import Base, pe, va  # noqa: E402


class FakeFcntl:
    LOCK_EX, LOCK_NB = 2, 4

    def __init__(self, numero):
        self.numero = numero

    def flock(self, fd, modo):
        raise OSError(self.numero, os.strerror(self.numero))


class TestSelo(Base):
    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.destino = os.path.join(self.home, ".local", "share", "tune-up", "estudio-node",
                                    pe.chave_do_ambiente(self.studio), "node")
        self.selo = os.path.join(self.destino, va.SELO)
        self.visto = []

    def so(self, codigos=(0, 0), rodar=None):
        base = rodar or self.rodar(list(codigos))

        def f(cmd, cwd, timeout):  # records whether the stamp exists when each npm step starts
            self.visto.append((cmd[1], os.path.lexists(self.selo)))
            return base(cmd, cwd, timeout)
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            return pe.main(["--so-instalar"], wsl=lambda: None, home=self.home, rodar=f,
                           which=lambda n: "/bin/" + n, studio=self.studio, plataforma="linux")

    def velho(self):
        os.makedirs(os.path.join(self.destino, "node_modules"), exist_ok=True)
        with open(self.selo, "w") as f:
            f.write("velho\n")

    def test_apaga_o_selo_antes_do_ci_e_grava_depois_da_auditoria(self):
        self.velho()
        self.assertEqual(self.so(), 0)
        self.assertEqual(self.visto, [("ci", False), ("audit", False)])
        with open(self.selo) as f:
            self.assertEqual(f.read(), pe.chave_do_ambiente(self.studio) + "\n")
        self.assertFalse(os.path.exists(self.selo + ".tmp"))

    def test_auditoria_falha_nao_deixa_selo(self):
        self.velho()
        self.assertEqual(self.so(codigos=(0, 1)), 1)
        self.assertFalse(os.path.lexists(self.selo))
        self.assertFalse(os.path.exists(os.path.join(self.destino, "node_modules")))

    def test_interrompido_no_ci_nao_deixa_selo_e_a_proxima_reinstala(self):
        self.velho()
        base = self.rodar([0, 0])

        def morto(cmd, cwd, timeout):
            base(cmd, cwd, timeout)
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.so(rodar=morto)
        self.assertFalse(os.path.lexists(self.selo))
        self.visto = []
        self.assertEqual(self.so(), 0)
        self.assertEqual([c for c, _ in self.visto], ["ci", "audit"])
        self.assertTrue(os.path.isfile(self.selo))

    def test_verificar_com_node_dir_exige_o_selo(self):
        self.assertEqual(self.so(), 0)
        os.makedirs(os.path.join(self.destino, "node_modules", "hyperframes"))
        with open(os.path.join(self.destino, "node_modules", "hyperframes", "package.json"), "w") as f:
            f.write('{"version": "0.9.6"}')
        self.assertEqual(va.hyperframes(self.destino, selo=True)[0][0], va.OK)
        os.remove(self.selo)
        self.assertEqual(va.hyperframes(self.destino, selo=True)[0][0], va.ERRO)


class TestTravaErro(Base):
    def test_erro_de_trava_no_main_grava_nao_pronto(self):
        pe.gravar(self.dados, {"pronto": True})
        with mock.patch.object(pe, "_travar", side_effect=OSError("sem espaço")), \
                mock.patch.object(pe, "preparar") as p, mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(pe.main(["--dados", self.dados, "--sim"]), 1)
        p.assert_not_called()
        self.assertFalse(self.lido()["pronto"])
        self.assertIn("sem espaço", self.lido()["erro"])

    def test_errno_inesperado_do_flock_nao_vira_ja_rodando(self):
        caminho = os.path.join(self.dados, pe.TRAVA)
        for numero in (errno.EWOULDBLOCK, errno.EAGAIN, errno.EACCES):
            with mock.patch.object(pe, "fcntl", FakeFcntl(numero)):
                self.assertIsNone(pe._travar_em(caminho), numero)
        pe.gravar(self.dados, {"pronto": True})
        with mock.patch.object(pe, "fcntl", FakeFcntl(errno.EIO)):
            with self.assertRaises(OSError):
                pe._travar_em(caminho)
            with mock.patch.object(pe, "preparar") as p, \
                    mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(pe.main(["--dados", self.dados, "--sim"]), 1)
                self.assertEqual(pe.main(["--so-instalar"], wsl=lambda: None, home=self.tmp,
                                         which=lambda n: "/bin/" + n, studio=self.studio, plataforma="linux"), 1)
        p.assert_not_called()
        self.assertNotIn("já está rodando", out.getvalue())
        self.assertFalse(self.lido()["pronto"])


if __name__ == "__main__":
    unittest.main()
