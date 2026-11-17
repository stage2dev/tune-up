"""Volta 3 do Windows: a ferramenta PowerShell é negada sempre nas sessões do painel, e no Bash do Windows chamar
cmd, PowerShell, WSL ou .bat/.cmd cai na regra forte, antes do `permitir`. Provado em qualquer sistema (`nt=True`
por parâmetro e `travas.os` simulado). Nada chama o claude."""
import json
import ntpath
import sys
import types

sys.dont_write_bytecode = True

import unittest  # noqa: E402

import travas  # noqa: E402
from test_travas import ACAO_CODIGO, ACAO_LEITURA, conf  # noqa: E402

PROT = ("C:\\Users\\u\\proj\\.tune-up\\painel",)
CWD = "C:\\Users\\u\\proj"


def dec(c, ferr, cmd, nt=True):
    return travas.decidir(c, ferr, {"command": cmd}, cwd=CWD, nt=nt)


class TestePowerShellNegado(unittest.TestCase):
    def test_nega_sempre_com_motivo_simples(self):
        acao_ps = dict(ACAO_CODIGO, permitir=["PowerShell(git status)", {"ferramenta": "PowerShell"}])
        for acao in (ACAO_LEITURA, ACAO_CODIGO, acao_ps):
            c = conf(acao, PROT, ())
            for nt in (True, False):
                for cmd in ("Get-Content a.txt", "git status", "Remove-Item a.txt", ""):
                    self.assertEqual(dec(c, "PowerShell", cmd, nt), ("deny", travas.MOTIVO_PS), (acao["id"], cmd))

    def test_powershell_no_permitir_nao_liga_o_bash(self):
        """Antes ligava a checagem de comando composto do Bash também no macOS."""
        c = conf(dict(ACAO_CODIGO, permitir=["PowerShell(git status)"]), PROT, ())
        self.assertFalse(c["bash"])
        self.assertIsNone(dec(c, "Bash", "git status && git log", nt=False))


class TesteShellDentroDoBash(unittest.TestCase):
    SHELLS = ("cmd //c dir", "cmd.exe /c dir", "CMD /C dir", "/c/Windows/System32/cmd.exe //c dir",
              "C:\\Windows\\System32\\cmd.exe /c dir", "c\\md //c dir", "c''md //c dir",
              "powershell -c Get-ChildItem", "powershell.exe -NoProfile -c x", "pwsh -c x", "wsl ls",
              "wsl.exe -e sh -c x", "$COMSPEC //c dir", "\"$ComSpec\" /c dir", "ls; cmd //c dir",
              "env cmd //c dir", "echo x | cmd", "./build.bat", "tools/run.cmd x",
              "cmd //c \"echo x > %USERPROFILE%\\outro\\a.json\"")
    LIVRES = ("git status", "ls src/cmd/main.go", "cat run.cmd.txt", "cat build.bat", "grep -n cmdline a.py",
              "npm run build", "python -m pytest")

    def test_forte_no_windows(self):
        for acao, esperado in ((ACAO_LEITURA, "deny"), (ACAO_CODIGO, "ask")):
            c = conf(acao, PROT, ())
            for cmd in self.SHELLS:
                r = dec(c, "Bash", cmd)
                self.assertEqual(r and r[0], esperado, (acao["risco"], cmd))

    def test_vale_antes_do_permitir(self):
        c = conf(dict(ACAO_CODIGO, permitir=["Bash(cmd *)", {"ferramenta": "Bash", "campo": "command",
                                                                "entrada": "^cmd"}]), PROT, ())
        self.assertEqual(dec(c, "Bash", "cmd //c dir"), ("ask", travas.MOTIVO_SHELL))

    def test_livres_seguem_livres(self):
        c = conf(ACAO_CODIGO, PROT, ())
        for cmd in self.LIVRES:
            self.assertIsNone(dec(c, "Bash", cmd), cmd)

    def test_macos_e_linux_nao_mudam(self):
        c = conf(ACAO_CODIGO, ("/p/.tune-up/painel",), ())
        for cmd in ("cmd //c dir", "pwsh -c x", "powershell -c x", "./build.bat"):
            self.assertIsNone(travas.decidir(c, "Bash", {"command": cmd}, cwd="/p", nt=False), cmd)


class TesteNegarPorPermissao(unittest.TestCase):
    """No Windows o `--settings` também nega o PowerShell por regra: vale até se o gancho não rodar (sem Git Bash)."""

    def negar(self):
        return json.loads(travas.settings_da_sessao(ACAO_CODIGO, PROT, (), python="python", este_arquivo="t.py")
                          ).get("permissions", {}).get("deny", [])

    def test_windows_nega_powershell(self):
        real = travas.os
        travas.os = types.SimpleNamespace(name="nt", path=ntpath, sep="\\")
        try:
            self.assertIn("PowerShell", self.negar())
        finally:
            travas.os = real

    def test_fora_do_windows_nao_muda(self):
        self.assertNotIn("PowerShell", self.negar())


if __name__ == "__main__":
    unittest.main()
