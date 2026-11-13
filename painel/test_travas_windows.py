"""Gancho de travas no Windows, provado em qualquer sistema: o ramo nt entra por parâmetro (`nt=True`, realpath
falso para o nome curto 8.3); o teste com nome 8.3 de verdade só roda no Windows. Nada chama o claude."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import ntpath  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shlex  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import catalogo  # noqa: E402
import travas  # noqa: E402
from test_travas import ACAO_CODIGO, ACAO_LEITURA, conf  # noqa: E402

U = "C:\\Users\\u"
PROJ = U + "\\proj"
PROT = (PROJ + "\\.tune-up\\painel", PROJ + "\\.tune-up\\pacote")
LIB = (PROJ + "\\.tune-up\\pacote\\dados",)


def real_falso(p):
    """realpath do Windows para o nome curto: normaliza (`.`, `..`) e expande CLAUDE~1 (em u e u/proj) e MARKET~1."""
    p = ntpath.normpath(p).replace("\\", "/")
    p = re.sub(r"(?i)^(C:/Users/u(?:/proj)?)/CLAUDE~1(?=/|$)", r"\1/.claude", p)
    return re.sub(r"(?i)^C:/Users/u/MARKET~1(?=/|$)", "C:/Users/u/marketplace-bruno", p)


def dec(c, ferr, entrada, cwd=PROJ, nt=True):
    r = travas.decidir(c, ferr, entrada, cwd, nt=nt, realpath=real_falso)
    return r[0] if r else None


class TesteCaminhoWin32(unittest.TestCase):
    """Item 8: o Win32 ignora fluxo NTFS, ponto/espaço no fim do pedaço e aceita o nome curto 8.3."""
    ALVOS = (U + "\\CLAUDE~1\\settings.json", PROJ + "\\CLAUDE.md.", PROJ + "\\CLAUDE.md::$DATA",
             PROJ + "\\.claude.\\settings.json", PROJ + "\\.claude \\settings.json",
             PROJ + "\\.tune-up\\pacote.\\acoes\\a.json", PROJ + "\\.tune-up\\pacote::$INDEX_ALLOCATION\\acoes\\a.json",
             PROJ + "\\.tune-up\\painel\\painel.py:fluxo:$DATA", "\\\\?\\C:\\Users\\u\\proj\\CLAUDE.md.")

    def test_quatro_casos_reproduzidos_negam(self):
        for acao, esperado in ((ACAO_LEITURA, "deny"), (ACAO_CODIGO, "ask")):
            c = conf(acao, PROT, LIB)
            for alvo in self.ALVOS:
                for ferr in ("Write", "Edit"):
                    self.assertEqual(dec(c, ferr, {"file_path": alvo}), esperado, (ferr, alvo))

    def test_relativo_com_nome_curto_usa_o_cwd(self):
        c = conf(ACAO_LEITURA, PROT, LIB)
        self.assertEqual(dec(c, "Write", {"file_path": "CLAUDE~1\\settings.json"}, cwd=U), "deny")

    def test_liberado_e_resto_seguem_livres(self):
        c = conf(ACAO_LEITURA, PROT, LIB)
        for livre in (PROJ + "\\.tune-up\\pacote\\dados\\fotos\\a.png", PROJ + "\\src\\app.py.",
                      U + "\\PROGRA~1\\x.txt", PROJ + "\\notas.md::$DATA"):
            self.assertIsNone(dec(c, "Write", {"file_path": livre}), livre)

    def test_win_limpo(self):
        for bruto, limpo in (("C:\\a\\CLAUDE.md.", "C:/a/CLAUDE.md"), ("ab::$DATA", "ab"), ("ab:fluxo:$DATA", "ab"),
                             ("x::$DATA", "x:"),
                             (".claude.\\x", ".claude/x"), (".claude ", ".claude"), ("a\\..\\.\\b", "a/.././b"),
                             ("\\\\?\\C:\\a", "C:/a"), ("\\\\.\\C:\\a", "C:/a"), ("\\\\?\\UNC\\srv\\x", "//srv/x")):
            self.assertEqual(travas._win_limpo(bruto), limpo, bruto)


@unittest.skipUnless(os.name == "nt", "nome curto 8.3 de verdade só existe no NTFS")
class TesteNomeCurtoReal(unittest.TestCase):
    def test_nome_curto_real_nega(self):
        import ctypes
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        longa = os.path.realpath(os.path.join(tmp, ".claude-long-name"))
        os.makedirs(longa)
        buf = ctypes.create_unicode_buffer(1024)
        if not ctypes.windll.kernel32.GetShortPathNameW(longa, buf, 1024) or "~" not in os.path.basename(buf.value):
            self.skipTest("nomes 8.3 desligados neste volume")
        c = conf(ACAO_LEITURA, (longa,), ())
        r = travas.decidir(c, "Write", {"file_path": os.path.join(buf.value, "x.txt")}, tmp)
        self.assertEqual(r and r[0], "deny", buf.value)


class TesteBashWin(unittest.TestCase):
    """Item 9: o Git Bash, o WSL e o Cygwin escrevem a unidade como /c/, /mnt/c/, /cygdrive/c/ ou //c/."""
    PROT = ("C:\\Users\\u\\pacote\\acoes",)

    def test_unidade_do_git_bash_nega(self):
        for acao, esperado in ((ACAO_LEITURA, "deny"), (ACAO_CODIGO, "ask")):
            c = conf(acao, self.PROT, ())
            for cmd in ("echo x > /c/Users/u/pacote/acoes/a.json", "cp a /mnt/c/Users/u/pacote/acoes/a.json",
                        "rm /cygdrive/c/Users/u/pacote/acoes/a.json", "echo x > //c/Users/u/pacote/acoes/a.json",
                        "echo x > /C/users/U/pacote/acoes./a.json"):
                self.assertEqual(dec(c, "Bash", {"command": cmd}), esperado, cmd)
            self.assertIsNone(dec(c, "Bash", {"command": "echo x > /c/Users/u/outro/a.json"}))

    def test_fluxo_ponto_e_nome_curto_no_bash(self):
        c = conf(ACAO_LEITURA, PROT, LIB)
        for cmd in ("echo x > CLAUDE.md.", "echo x > 'CLAUDE.md::$DATA'", "echo x > '.claude. /settings.json'",
                    "echo {} > C:/Users/u/CLAUDE~1/settings.json"):
            self.assertEqual(dec(c, "Bash", {"command": cmd}), "deny", cmd)

    def test_sem_nt_nada_muda(self):
        c = conf(ACAO_CODIGO, self.PROT, ())
        self.assertIsNone(dec(c, "Bash", {"command": "echo x > /c/Users/u/pacote/acoes/a.json"}, nt=False))


class TestePowerShell(unittest.TestCase):
    """A ferramenta PowerShell é sempre negada (MOTIVO_PS), em qualquer nível, mesmo com ela no `permitir`."""

    def test_nega_mesmo_com_regra_de_permitir(self):
        for acao in (ACAO_LEITURA, ACAO_CODIGO):
            c = conf(acao, PROT, LIB)
            c["p"] = [{"ferramenta": "PowerShell", "campo": "command", "entrada": ".*"}]
            for nt in (False, True):
                for cmd in ("git status", "Get-Content a.txt", "Remove-Item C:\\x\\a.txt"):
                    self.assertEqual(travas.decidir(c, "PowerShell", {"command": cmd}, nt=nt),
                                     ("deny", travas.MOTIVO_PS), (acao["risco"], nt, cmd))
                self.assertEqual(travas.decidir(c, "PowerShell", {}, nt=nt), ("deny", travas.MOTIVO_PS))

    def test_powershell_no_permitir_nao_liga_o_bash(self):
        for permitir, esperado in (("PowerShell(git status)", False), ("Bash(git status)", True)):
            c = travas.config_gancho(catalogo.validar_acao(dict(ACAO_CODIGO, permitir=[permitir])), PROT, LIB)
            self.assertIs(c["bash"], esperado, permitir)


class TesteUtf8DoGancho(unittest.TestCase):
    """Item 7: o gancho roda com -X utf8; sem isso, com o sistema fora do UTF-8, o JSON sai e entra errado."""
    LOCAIS = ("en_US.ISO8859-1", "pt_BR.ISO8859-1", "en_US.ISO-8859-1", "pt_BR.ISO-8859-1", "en_US", "pt_BR")

    def test_comando_tem_utf8(self):
        cfg = json.loads(travas.settings_da_sessao(ACAO_CODIGO, ("/p",), ()))
        partes = shlex.split(cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
        self.assertEqual(partes[1:3], ["-I", "-BXutf8"])  # -B -X utf8 juntos: o <conf> segue no 5º pedaço
        self.assertTrue(travas._decodificar(partes[4]))

    def _env_sem_utf8(self):
        base = {k: v for k, v in os.environ.items() if not k.startswith(("PYTHON", "LC_", "LANG"))}
        for local in self.LOCAIS if os.name != "nt" else ("",):
            env = dict(base, PYTHONUTF8="0", PYTHONCOERCECLOCALE="0", **({"LC_ALL": local} if local else {}))
            p = subprocess.run([sys.executable, "-I", "-c", "import sys; print(sys.stdin.encoding)"], env=env,
                               input=b"", capture_output=True, timeout=30)
            if p.returncode == 0 and "utf" not in p.stdout.decode("ascii", "replace").lower():
                return env
        self.skipTest("nenhum locale fora do UTF-8 neste sistema")

    def test_gancho_com_sistema_fora_do_utf8(self):
        env = self._env_sem_utf8()
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, True)
        acao = catalogo.validar_acao(dict(ACAO_LEITURA, negar=[
            {"ferramenta": "mcp__x__.*", "motivo": "envio → fora (não)"}]))
        cfg = json.loads(travas.settings_da_sessao(acao, (os.path.join(tmp, "Ação", "acoes"),), ()))
        argv = shlex.split(cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"].rsplit(" || exit 2", 1)[0])
        casos = (({"tool_name": "Write", "tool_input": {"file_path": os.path.join(tmp, "Ação", "acoes", "a.json")}},
                  "Trava do painel: mexer nas regras do Claude ou do painel"),
                 ({"tool_name": "mcp__x__enviar", "tool_input": {"texto": "olá"}}, "Trava do painel: envio → fora (não)"))
        for dados, motivo in casos:
            p = subprocess.run(argv, env=env, input=json.dumps(dados, ensure_ascii=False).encode("utf-8"),
                               capture_output=True, timeout=30)
            self.assertEqual(p.returncode, 0, p.stderr.decode("utf-8", "replace")[-400:])
            out = json.loads(p.stdout.decode("utf-8"))["hookSpecificOutput"]
            self.assertEqual((out["permissionDecision"], out["permissionDecisionReason"]), ("deny", motivo))


class TesteInsistir(unittest.TestCase):
    """Item 15: no Windows o arquivo da pergunta pode estar aberto pelo painel por um instante."""
    SID = "12345678-1234-1234-1234-123456789abc"
    ENTRADA = {"questions": [{"question": "Qual?", "options": [{"label": "A"}]}]}

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def _falha_duas(self, real):
        chamadas = []

        def falso(*a):
            chamadas.append(a)
            if len(chamadas) <= 2:
                raise PermissionError(13, "aberto por outro processo")
            return real(*a)
        return falso, chamadas

    def test_guardar_e_esquecer_tentam_de_novo(self):
        troca, n_troca = self._falha_duas(os.replace)
        with mock.patch.object(travas.os, "name", "nt"), mock.patch.object(travas.time, "sleep"), \
                mock.patch.object(travas.os, "replace", troca):
            self.assertTrue(travas.guardar_pergunta(self.tmp, self.SID, self.ENTRADA))
        arq = os.path.join(self.tmp, self.SID + ".json")
        self.assertEqual((len(n_troca), os.path.exists(arq)), (3, True))
        apaga, n_apaga = self._falha_duas(os.unlink)
        with mock.patch.object(travas.os, "name", "nt"), mock.patch.object(travas.time, "sleep"), \
                mock.patch.object(travas.os, "unlink", apaga):
            travas.esquecer_pergunta(self.tmp, self.SID)
        self.assertEqual((len(n_apaga), os.path.exists(arq)), (3, False))

    @unittest.skipIf(os.name == "nt", "fora do Windows não insiste")
    def test_fora_do_windows_nao_insiste(self):
        troca, n_troca = self._falha_duas(os.replace)
        with mock.patch.object(travas.os, "replace", troca), mock.patch.object(travas.time, "sleep"):
            self.assertFalse(travas.guardar_pergunta(self.tmp, self.SID, self.ENTRADA))
        self.assertEqual(len(n_troca), 1)


if __name__ == "__main__":
    unittest.main()
