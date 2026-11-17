"""Sistema do preparo: achar() só devolve caminho absoluto de uma pasta absoluta do PATH estendido (nunca o diretório
atual); os filhos recebem só a lista permitida de variáveis (com NoDefaultCurrentDirectoryInExePath=1 no Windows) e os
soltos rodam com cwd na pasta de dados. Processos de verdade só com o próprio python."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import preparo_sistema  # noqa: E402
from servico.preparo_sistema import Sistema  # noqa: E402


def executavel(pasta, nome):
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, nome)
    with open(caminho, "w") as f:
        f.write("#!/bin/sh\n")
    os.chmod(caminho, os.stat(caminho).st_mode | stat.S_IXUSR)
    return caminho


class TesteAchar(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.atual = os.path.join(self.tmp, "atual")
        self.bin = os.path.join(self.tmp, "bin")
        os.makedirs(self.atual)
        volta = os.getcwd()
        os.chdir(self.atual)
        self.addCleanup(os.chdir, volta)

    def test_posix_ignora_o_diretorio_atual_e_entradas_relativas(self):
        executavel(self.atual, "docker")
        s = Sistema(plataforma="darwin", caminho=os.pathsep.join([".", "relativa", ""]), ambiente={})
        self.assertIsNone(s.achar("docker"))
        bom = executavel(self.bin, "docker")
        s = Sistema(plataforma="darwin", caminho=os.pathsep.join([".", self.bin]), ambiente={})
        self.assertEqual(s.achar("docker"), bom)
        self.assertTrue(os.path.isabs(s.achar("docker")))

    def test_windows_nunca_o_diretorio_atual(self):
        executavel(self.atual, "docker.exe")
        s = Sistema(plataforma="win32", caminho=".", ambiente={"PATHEXT": ".COM;.EXE"})
        self.assertIsNone(s.achar("docker"))
        bom = executavel(self.bin, "docker.exe")
        s = Sistema(plataforma="win32", caminho=os.pathsep.join([".", self.bin]), ambiente={"PATHEXT": ".COM;.EXE"})
        self.assertEqual(s.achar("docker"), bom)


class TesteAmbiente(unittest.TestCase):
    AMBIENTE = {"PATH": "/x", "HOME": "/h", "USER": "u", "LC_ALL": "C", "HOMEBREW_NO_AUTO_UPDATE": "1",
                "DOCKER_HOST": "unix:///d.sock", "VENDAS_EVOLUTION_URL": "http://127.0.0.1:9", "TMPDIR": "/t",
                "OPENAI_API_KEY": "sk-segredo", "AWS_SECRET_ACCESS_KEY": "s", "GITHUB_TOKEN": "g", "SystemRoot": "C:\\W"}

    def test_so_a_lista_permitida_passa(self):
        amb = Sistema(plataforma="darwin", ambiente=self.AMBIENTE).ambiente
        for nome in ("HOME", "USER", "LC_ALL", "HOMEBREW_NO_AUTO_UPDATE", "DOCKER_HOST", "VENDAS_EVOLUTION_URL",
                     "TMPDIR", "SystemRoot", "PATH"):
            self.assertIn(nome, amb)
        for nome in ("OPENAI_API_KEY", "AWS_SECRET_ACCESS_KEY", "GITHUB_TOKEN"):
            self.assertNotIn(nome, amb)
        self.assertNotIn("NoDefaultCurrentDirectoryInExePath", amb)

    def test_windows_sem_caixa_e_sem_diretorio_atual(self):
        amb = Sistema(plataforma="win32", ambiente={"PATH": "", "PROGRAMFILES": "D:\\PF", "OPENAI_API_KEY": "x",
                                                    "LOCALAPPDATA": "D:\\L"}).ambiente
        self.assertEqual(amb["NoDefaultCurrentDirectoryInExePath"], "1")
        self.assertEqual((amb["PROGRAMFILES"], amb["LOCALAPPDATA"]), ("D:\\PF", "D:\\L"))
        self.assertNotIn("OPENAI_API_KEY", amb)
        s = Sistema(plataforma="win32", ambiente={"PATH": "", "PROGRAMFILES": "D:\\PF"})
        self.assertIn(os.path.join("D:\\PF", "Docker", "Docker", "resources", "bin"), s.caminho)

    def test_filho_de_verdade_nao_ve_o_segredo(self):
        # o ambiente real da máquina (no Windows o Python filho não sobe sem o SystemRoot verdadeiro) mais um segredo
        amb = dict(os.environ, OPENAI_API_KEY="sk-segredo", VENDAS_EVOLUTION_URL="http://127.0.0.1:9")
        s = Sistema(ambiente=amb)
        codigo, saida = s.rodar([sys.executable, "-c", "import os; print(os.environ.get('OPENAI_API_KEY'), "
                                 "os.environ.get('VENDAS_EVOLUTION_URL'))"], 30)
        self.assertEqual((codigo, saida.split()), (0, ["None", "http://127.0.0.1:9"]))

    def test_lista_num_lugar_so(self):
        self.assertIn("PATH", preparo_sistema.AMBIENTE_PERMITIDO)
        for nome in ("VENDAS_EVOLUTION_URL", "VENDAS_EVOLUTION_CHAVE", "XDG_DATA_HOME", "LOCALAPPDATA"):
            self.assertIn(nome, preparo_sistema.AMBIENTE_PERMITIDO)


class TesteSoltar(unittest.TestCase):
    def test_solto_roda_na_pasta_do_log(self):
        tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        log = os.path.join(tmp, "preparo.log")
        p = Sistema().soltar([sys.executable, "-c", "import os; print(os.getcwd())"], log)
        p.wait(30)
        with open(log, encoding="utf-8") as f:
            self.assertEqual(os.path.realpath(f.read().strip()), tmp)


if __name__ == "__main__":
    unittest.main()
