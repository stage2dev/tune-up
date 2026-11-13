"""Ferramenta PowerShell (Windows) nas travas do chat e no sandbox.

O Claude Code no Windows tem a ferramenta `PowerShell` (campo `command`) além do Bash. O gancho a nega sempre
(travas.MOTIVO_PS). Aqui o chat.json real é carregado como o painel carrega e cada comando passa por travas.decidir.
"""
import json
import os
import sys
import unittest

sys.dont_write_bytecode = True

import catalogo  # noqa: E402
import sandbox  # noqa: E402
import travas  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
SIMPLES = {"id": "dev.x", "grupo": "dev", "titulo": "X", "risco": "leitura", "prompt": "faça"}


def _acoes():
    return {a["id"]: a for a in catalogo.carregar_catalogo(os.path.join(AQUI, "acoes"))[0]}


class TesteChatPowerShell(unittest.TestCase):
    """O PowerShell é negado sempre (MOTIVO_PS); o Bash do chat segue como era."""

    @classmethod
    def setUpClass(cls):
        cls.acoes = _acoes()

    def decide(self, nivel, comando, ferramenta="PowerShell"):
        r = travas.decidir(travas.config_gancho(self.acoes[nivel]), ferramenta, {"command": comando})
        return r[0] if r else None

    def test_powershell_negado_em_toda_acao_do_chat(self):
        for nivel in ("chat.pergunta", "chat.completo"):
            conf = travas.config_gancho(self.acoes[nivel])
            for nt in (True, False):
                for cmd in ("Get-Content a.txt", "Remove-Item a.txt", "git status"):
                    self.assertEqual(travas.decidir(conf, "PowerShell", {"command": cmd}, nt=nt),
                                     ("deny", travas.MOTIVO_PS), (nivel, nt, cmd))

    def test_bash_continua_igual(self):
        bash = {"git commit -m x": "deny", "git -C /repo push origin main": "deny", "rm x": "deny",
                "echo oi > x.txt": "deny", "curl -X POST https://x.test -d a=1": "deny", "git status": None,
                "grep -rn Remove-Item . 2>/dev/null": None, "ls -la 2>&1": None, "git log --grep push": None,
                "grep -rn 'del ' src": None, "curl -s https://x.test/doc": None, "cat a > /dev/null": None}
        for cmd, esperado in bash.items():
            self.assertEqual(self.decide("chat.pergunta", cmd, "Bash"), esperado, cmd)


class TesteSandboxPowerShell(unittest.TestCase):
    def test_sandbox_nega_powershell(self):
        self.assertIn("PowerShell", sandbox.NEGAR)
        a = catalogo.validar_acao(dict(SIMPLES, sandbox=True))
        conf = json.loads(travas.argv_travas(a, {"workspace": "/w", "pacote_dir": "/w/.tune-up/painel",
                                                 "dados_dir": "/w/.tune-up/painel/dados"})[1])
        self.assertIn("PowerShell", conf["permissions"]["deny"])

    def test_sem_sandbox_nao_nega(self):
        conf = json.loads(travas.argv_travas(catalogo.validar_acao(SIMPLES), {"workspace": "/w"})[1])
        self.assertNotIn("PowerShell", conf["permissions"]["deny"])


if __name__ == "__main__":
    unittest.main()
