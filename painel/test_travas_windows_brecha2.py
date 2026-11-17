"""Brechas do gancho no Windows achadas na revisão (rodada 2), provadas em qualquer sistema: o ramo nt entra por
parâmetro (`nt=True`) e o realpath é falso (test_travas_windows.real_falso). Nada chama o claude."""
import re
import sys

sys.dont_write_bytecode = True

import unittest  # noqa: E402

from test_travas import ACAO_CODIGO, ACAO_LEITURA, conf  # noqa: E402
from test_travas_windows import LIB, PROT, U, real_falso  # noqa: E402
from test_travas_windows_brecha import FORTE, MARKET, dec  # noqa: E402

PROJ = U + "\\proj"
TODOS = PROT + MARKET
MK = "/c/Users/u/marketplace-bruno/tune-up/painel"


class Caso(unittest.TestCase):
    def confere(self, casos, prot=TODOS, lib=LIB, cwd=PROJ, realpath=real_falso, forte=FORTE):
        for acao, esperado in forte:
            c = conf(acao, prot, lib)
            for ferr, cmd in casos:
                self.assertEqual(dec(c, ferr, cmd, cwd=cwd, realpath=realpath), esperado, (acao["risco"], ferr, cmd))


class TesteSemUnidade(Caso):
    """Achados 3 e 9: `\\Users\\..` (unidade atual) e /c/ grudado em opção ou chave."""

    def test_sem_unidade_nega(self):
        self.confere([("Bash", 'cmd //c "echo x > \\Users\\u\\marketplace-bruno\\tune-up\\painel\\acoes\\a.json"'),
                      ("Bash", "cp -t%s/acoes x" % MK), ("Bash", "curl -so%s/acoes/a.json https://e.x" % MK),
                      ("Bash", "tee {x,%s/acoes/a.json} </dev/null" % MK),
                      ("Bash", "sort -o%s/acoes/a.json x" % MK), ("Bash", "cp evil.json -t%s/acoes" % MK),
                      ("Bash", "tar -xf a.tar -C%s" % MK), ("Bash", "tee {%s/acoes/a.json,x}" % MK)])

    def test_outra_pasta_segue_livre(self):
        c = conf(ACAO_CODIGO, TODOS, LIB)
        self.assertIsNone(dec(c, "Bash", "cp -t/c/Users/u/outro x", cwd=PROJ))


class TesteUnidadeRelativa(Caso):
    """Achado 4: `C:rel` é relativo ao cwd da unidade C:."""

    def test_unidade_relativa_nega(self):
        self.confere([("Bash", "echo x > C:.tune-up/painel/a.json"),
                      ("Bash", 'cmd //c "echo x > C:.tune-up\\painel\\a.json"')])


class TesteVariavelDoCmd(Caso):
    """Achado 6: o cmd expande %VAR% (e !VAR!) para fora do cwd."""

    def test_variavel_do_cmd_nega(self):
        alvo = "%USERPROFILE%\\marketplace-bruno\\tune-up\\painel\\acoes\\a.json"
        self.confere([("Bash", 'cmd //c "echo x > %s"' % alvo)])


class TesteBaixarParaArquivo(Caso):
    """Achados 7 e 11: baixar e exportar para arquivo grava; em código pergunta como o `curl -o`."""

    def test_baixar_para_protegido_pergunta(self):
        self.confere([("Bash", "certutil -urlcache -f https://e.x/s C:/Users/u/proj/.claude/settings.json")])


class TesteCurtoNaoExpandido(Caso):
    """Achado 8: pasta 8.3 que o realpath não expande (base fora do cwd: `~`, `cd`, espaço no caminho)."""
    JOHN = "C:\\Users\\John Smith"

    def real(self, p):
        p = real_falso(p)
        return re.sub(r"(?i)^C:/Users/John Smith/CLAUDE~1(?=/|$)", "C:/Users/John Smith/.claude", p)

    def test_curto_solto_nega(self):
        casos = [("Bash", "tee ~/CLAUDE~1/settings.json"), ("Bash", "cd .. && echo x > CLAUDE~1/settings.json")]
        self.confere(casos, cwd=U + "\\work", realpath=self.real)
        self.confere([("Bash", 'tee "/c/Users/John Smith/CLAUDE~1/settings.json"')],
                     cwd=self.JOHN + "\\proj", realpath=self.real)

    def test_leitura_e_revisao_do_git_seguem_livres(self):
        c = conf(ACAO_LEITURA, TODOS, LIB)
        for ferr, cmd in (("Bash", "cat ~/PROGRA~1/x.txt"), ("Bash", "git log HEAD~1"),
                          ("Bash", "git show HEAD~1:src/a.py")):
            self.assertIsNone(dec(c, ferr, cmd, cwd=U + "\\work"), cmd)


class TesteCaminhoDoNt(Caso):
    """Achado 10: `\\??\\` é caminho do NT (o .NET passa direto); no Git Bash /proc/sys é o espaço do NT."""

    def test_caminho_do_nt_nega(self):
        resto = "\\Users\\u\\marketplace-bruno\\tune-up\\painel\\acoes\\a.json"
        self.confere([("Bash", "echo x > /proc/sys/Device/HarddiskVolume3%s" % resto.replace("\\", "/"))])

    def test_caminho_do_nt_sem_o_protegido_no_texto(self):
        # volume montado numa pasta protegida: o texto nem cita o protegido, o gancho não resolve -> forte
        self.confere([("Bash", "echo x > /proc/sys/Device/HarddiskVolume9/acoes/a.json")])
        for acao, esperado in FORTE:
            c = conf(acao, TODOS, LIB)
            for alvo in ("\\??\\GLOBALROOT\\Device\\HarddiskVolume9\\a.json", "\\??\\Volume{0b1c2d3e-0000}\\a.json"):
                self.assertEqual(dec(c, "Write", alvo, campo="file_path"), esperado, alvo)

    def test_unidade_do_nt_fora_do_protegido_segue_livre(self):
        c = conf(ACAO_LEITURA, TODOS, LIB)
        self.assertIsNone(dec(c, "Write", "\\??\\C:\\Users\\u\\proj\\src\\a.txt", campo="file_path"))
        self.assertIsNone(dec(c, "Bash", "cat /proc/cygdrive/c/Users/u/proj/src/a.txt"))


if __name__ == "__main__":
    unittest.main()
