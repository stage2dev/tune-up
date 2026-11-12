"""Shared base for the guarda_mkt.py tests: runs the script as a subprocess, isolated from HOME."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "scripts", "guarda_mkt.py")
SHELLS = ("Bash", "PowerShell", "Monitor")
DECISAO = {"deny": "bloquear", "ask": "perguntar"}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="tuneup-mkt-")
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("TUNEUP_") and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_DATA")}
        self.env.update({"TUNEUP_TESTE": "1", "CLAUDE_PLUGIN_DATA": self.tmp,
                         "TUNEUP_USER_JSON": os.path.join(self.tmp, "sem-user.json"),
                         "TUNEUP_MKT_JSON": os.path.join(self.tmp, "sem-mkt.json")})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def saida(self, entrada=None, bruto=None, env=None):
        """Raw hookSpecificOutput (or None)."""
        e = dict(self.env)
        e.update(env or {})
        r = subprocess.run([sys.executable, SCRIPT], input=bruto if bruto is not None else json.dumps(entrada),
                           capture_output=True, text=True, env=e, timeout=20, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None

    def rodar(self, entrada=None, bruto=None, env=None):
        s = self.saida(entrada, bruto, env)
        return DECISAO[s["permissionDecision"]] if s else None

    def shell(self, cmd, esperado, env=None):
        """Same command through Bash, PowerShell and Monitor: same decision on all three."""
        for nome in SHELLS:
            with self.subTest(ferramenta=nome):
                self.assertEqual(self.rodar({"tool_name": nome, "tool_input": {"command": cmd}}, env=env), esperado)

    def multi(self, slug, args=None, env=None):
        return self.rodar({"tool_name": "mcp__composio__COMPOSIO_MULTI_EXECUTE_TOOL",
                           "tool_input": {"tools": [{"tool_slug": slug, "arguments": args or {}}]}}, env=env)

    def gravar(self, nome, dados):
        caminho = os.path.join(self.tmp, nome)
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(dados if isinstance(dados, str) else json.dumps(dados))
        return caminho
