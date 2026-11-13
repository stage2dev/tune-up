"""PowerShell (Windows tool) in studio actions: always denied.

The studio's Bash list only lets ffmpeg, ffprobe, the studio scripts and the pinned hyperframes run, inside
the sandbox. The Claude Code sandbox covers the Bash tool only, so the PowerShell tool would run outside it
with network and disk free. Every studio action denies it as a plain permission rule (and the panel core
adds it to every sandboxed session too). Loads the real actions the way the panel does. No session.
"""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
PAINEL = os.path.join(os.path.dirname(STUDIO), "painel")
sys.path.insert(0, PAINEL)

import catalogo  # noqa: E402
import trabalho  # noqa: E402
import travas  # noqa: E402

ACTIONS = os.path.join(STUDIO, "painel", "acoes", "estudio.json")
WORK = "/proj [1]/x y/.tune-up/painel/dados/trabalhos/abc"
CFG = {"workspace": "/proj [1]", "pacote_dir": "/proj [1]/.tune-up/painel",
       "dados_dir": "/proj [1]/.tune-up/painel/dados", "painel_dir": "/plugin/painel"}


class StudioDeniesPowerShell(unittest.TestCase):
    def setUp(self):
        with open(ACTIONS, encoding="utf-8") as f:
            self.raw = json.load(f)["acoes"]

    def test_every_studio_action_denies_powershell(self):
        self.assertTrue(self.raw)
        for a in self.raw:
            self.assertTrue(a.get("sandbox"), a["id"])
            self.assertIn("PowerShell", a["negar"], a["id"])
            self.assertNotIn("PowerShell", " ".join(map(str, a.get("permitir") or [])), a["id"])

    def test_session_settings_deny_powershell(self):
        for a in self.raw:
            acao = trabalho.resolver_travas(catalogo.validar_acao(a), WORK)
            deny = json.loads(travas.argv_travas(acao, CFG)[1])["permissions"]["deny"]
            self.assertIn("PowerShell", deny, a["id"])
            self.assertEqual(deny.count("PowerShell"), 1, a["id"])


if __name__ == "__main__":
    unittest.main()
