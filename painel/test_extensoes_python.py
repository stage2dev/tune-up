"""O comando de aceitar extensão usa o Python que roda o painel, não um 'python3' literal."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shlex  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import extensoes  # noqa: E402


class TestComandoAceitar(unittest.TestCase):
    def test_posix_cita_o_executavel_e_o_painel(self):
        with mock.patch.object(sys, "executable", "/opt/meu python/bin/python"):
            cmd = extensoes._python("posix")
        self.assertTrue(cmd.startswith("'/opt/meu python/bin/python' "), cmd)
        self.assertTrue(cmd.endswith("painel.py"), cmd)
        self.assertTrue(os.path.isfile(shlex.split(cmd)[1]))  # absoluto: vale de qualquer pasta

    def test_nt_barras_normais_e_aspas_sempre(self):
        """Git Bash come `\\` fora de aspas: no Windows sai `/` entre aspas duplas, com ou sem espaço."""
        for exe in ("C:\\Program Files\\Python\\python.exe", "C:\\Py312\\python.exe"):
            with mock.patch.object(sys, "executable", exe):
                cmd = extensoes._python("nt")
            self.assertTrue(cmd.startswith('"%s" "' % exe.replace("\\", "/")), cmd)
            self.assertNotIn("\\", cmd)
            self.assertTrue(cmd.endswith('painel.py"'), cmd)

    def test_mensagem_de_trava_traz_sys_executable(self):
        import test_extensoes as t
        caso = t.TesteExtensoes("test_conteudo_mudou_recusa_acoes_e_modulo_ate_aceitar")
        caso.setUp()
        try:
            cfg = caso.cfg(acoes_de_plugins=["estudio@meumarket"])
            caso.ids(cfg)
            t.escrever(t.os.path.join(caso.inst, "scripts", "qa.py"), "print('outro')\n")
            with mock.patch.object(sys, "executable", "/opt/py 3/bin/python"):
                _, avisos = caso.ids(cfg)
                esperado = extensoes._python()  # aspas do sistema que roda (POSIX ou Windows)
            msg = [a for a in avisos if "--aceitar-extensao" in a][0]
            self.assertIn("/opt/py 3/bin/python", esperado)
            self.assertIn("com: %s --aceitar-extensao estudio@meumarket" % esperado, msg)
            self.assertNotIn("python3 painel.py", msg)
        finally:
            t.shutil.rmtree(caso.tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
