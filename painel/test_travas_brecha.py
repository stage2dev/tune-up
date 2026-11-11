"""Brechas do Bash por texto e da trava fixa (dados/../, caixa no macOS, verbo fora da lista, caminho
disfarçado, Bash liberado com comando composto, falha do gancho). Nada chama o claude."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import travas  # noqa: E402
from test_travas import ACAO_CODIGO, ACAO_LEITURA, conf, decisao, rodar_gancho  # noqa: E402

PAINEL = "/p/.tune-up/painel"
ACOES = "/p/.tune-up/pacote/acoes/a.json"


def bash(c, cmd):
    return decisao(c, "Bash", {"command": cmd})


class TesteDadosPontoPonto(unittest.TestCase):
    def test_bash_sai_de_dados_com_ponto_ponto(self):
        for c, esperado in ((conf(ACAO_LEITURA), "deny"), (conf(ACAO_CODIGO), "ask")):
            for cmd in ("echo x > /p/.tune-up/pacote/dados/../acoes/a.json",
                        "cd /p/.tune-up/pacote/dados && echo x > ../acoes/a.json",
                        "cp a /p/.tune-up/pacote/dados/x/../../acoes/a.json"):
                self.assertEqual(bash(c, cmd), esperado, cmd)
            self.assertIsNone(bash(c, "echo x > /p/.tune-up/pacote/dados/fotos/a.json"))


class TesteCaminhoRelativo(unittest.TestCase):
    """Revisão da Parte 1: com caminho relativo, `dados/../` e as coisas do dono passavam."""
    DADOS = "/p/.tune-up/pacote/dados"

    def _conf(self, acao):
        return conf(acao, prot=("/p/.tune-up/painel", "/p/.tune-up/pacote", self.DADOS + "/estudio-dono.json",
                                self.DADOS + "/aprovados"))

    def test_relativo_sai_de_dados_ou_mexe_no_que_e_do_dono(self):
        for acao, esperado in ((ACAO_LEITURA, "deny"), (ACAO_CODIGO, "ask")):
            c = self._conf(acao)
            for cmd in ("echo x > .tune-up/pacote/dados/../acoes/a.json",
                        "cp /tmp/a .tune-up/pacote/dados/x/../../acoes/a.json",
                        "cd .tune-up/pacote/dados/ && echo x > ../acoes/a.json",
                        "echo x > .tune-up/pacote/dados/estudio-dono.json",
                        "mkdir -p .tune-up/pacote/dados/aprovados/1"):
                self.assertEqual(travas.decidir(c, "Bash", {"command": cmd}, "/p")[0], esperado, cmd)
            trab = self.DADOS + "/trabalhos/ab12"
            self.assertEqual(travas.decidir(c, "Bash", {"command": "echo x > ../../estudio-dono.json"}, trab)[0],
                             esperado)
            self.assertIsNone(travas.decidir(c, "Bash", {"command": "echo x > saida/ok.txt"}, trab))
            self.assertIsNone(travas.decidir(c, "Bash", {"command": "echo x > .tune-up/pacote/dados/fotos/a"}, "/p"))

    def test_layout_padrao_sem_cwd_pega_pelo_nome(self):
        c = conf(ACAO_LEITURA)
        for cmd in ("echo x > .tune-up/painel-projeto/dados/../acoes/a.json",
                    "cd .tune-up/painel-projeto/dados/ && echo x > ../acoes/a.json",
                    "echo x > .tune-up/painel-projeto/dados/estudio-dono.json",
                    "mkdir -p .tune-up/painel-projeto/dados/aprovados/1"):
            self.assertEqual(bash(c, cmd), "deny", cmd)
        self.assertIsNone(bash(c, "echo x > .tune-up/painel-projeto/dados/fotos/a.json"))

    def test_gancho_le_o_cwd_da_entrada(self):
        c = self._conf(ACAO_LEITURA)
        rc, out = rodar_gancho(travas._codificar(c), {"tool_name": "Bash", "cwd": self.DADOS + "/trabalhos/ab12",
                                                       "tool_input": {"command": "echo x > ../../estudio-dono.json"}})
        self.assertEqual((rc, out["permissionDecision"]), (0, "deny"))


@unittest.skipIf(os.name == "nt", "barra invertida como escape é do shell POSIX")
class TesteBarraInvertida(unittest.TestCase):
    def test_escape_nao_disfarca_caminho(self):
        for acao, esperado in ((ACAO_LEITURA, "deny"), (ACAO_CODIGO, "ask")):
            c = conf(acao)
            for cmd in ("echo '{}' > .cla\\ude/settings.json", "echo x > .claude/settings.js\\on",
                        "echo x > CLAU\\DE.md", "ln -s ~/.cla\\ude/skills x", "echo x > .tune-up/pai\\nel/a.json",
                        "cp /tmp/e /p/.tune-up/pa\\cote/acoes/a.json"):
                self.assertEqual(bash(c, cmd), esperado, cmd)


class TesteCaixaNoMac(unittest.TestCase):
    def test_caixa_trocada_nao_passa_no_mac(self):
        with mock.patch.object(travas.sys, "platform", "darwin"):
            c = conf(ACAO_LEITURA)
            for caminho in ("/w/.Claude/Settings.json", "x/.TUNE-UP/painel.json", "/w/.CLAUDE/Hooks/x.py",
                            "/P/.tune-up/PACOTE/acoes/a.json", "/p/.Tune-Up/Pacote/dados/../acoes/a.json"):
                self.assertEqual(decisao(c, "Write", {"file_path": caminho}), "deny", caminho)
            self.assertEqual(bash(c, "echo 1 > /P/.TUNE-UP/Pacote/acoes/a.json"), "deny")
            self.assertIsNone(decisao(c, "Write", {"file_path": "/P/.tune-up/PACOTE/Dados/x.json"}))


class TesteVerbos(unittest.TestCase):
    ESCREVEM = ("dd if=/dev/zero of=%s/x" % PAINEL, "install a %s/x" % PAINEL,
                "python3 -c \"open('%s/x','w')\"" % PAINEL, "node -e 'x' %s/x" % PAINEL,
                "powershell Set-Content %s/x 1" % PAINEL, "rsync a %s/" % PAINEL,
                "find %s -name x -delete" % PAINEL, "xargs rm < %s/lista" % PAINEL)

    def test_verbo_fora_da_lista_nega_ou_pergunta(self):
        leve, cod = conf(ACAO_LEITURA), conf(ACAO_CODIGO)
        for cmd in self.ESCREVEM:
            self.assertEqual(bash(leve, cmd), "deny", cmd)
            self.assertEqual(bash(cod, cmd), "ask", cmd)
        win = conf(ACAO_LEITURA, prot=("C:\\p\\.tune-up\\pacote",), lib=())
        for cmd in ("copy a C:\\p\\.tune-up\\pacote\\x", "move a C:\\p\\.tune-up\\pacote\\x",
                    "ren C:\\p\\.tune-up\\pacote\\x y", "C:\\Windows\\del.exe C:\\p\\.tune-up\\pacote\\x"):
            self.assertEqual(bash(win, cmd), "deny", cmd)

    def test_leve_so_aceita_verbo_de_leitura_na_arvore(self):
        leve, cod = conf(ACAO_LEITURA), conf(ACAO_CODIGO)
        for cmd in ("cat %s/README.md" % PAINEL, "grep -rn x %s" % PAINEL, "head -5 %s/a.py" % PAINEL,
                    "md5 %s/a.py" % PAINEL):
            self.assertIsNone(bash(leve, cmd), cmd)
        self.assertEqual(bash(leve, "find %s -name x" % PAINEL), "deny")
        self.assertEqual(bash(leve, "awk 1 %s/a.py" % PAINEL), "deny")
        self.assertIsNone(bash(cod, "find %s -name x" % PAINEL))


class TesteCaminhoDisfarcado(unittest.TestCase):
    def test_aspas_barra_dupla_ponto_glob_variavel(self):
        leve, cod = conf(ACAO_LEITURA), conf(ACAO_CODIGO)
        for cmd in ("echo x > \"/p/.tune-up/pac\"'ote'/acoes/a.json", "echo x > /p/.tune-up//pacote/acoes/a.json",
                    "echo x > /p/./.tune-up/pacote/acoes/a.json", "echo x > /p/.tune-up/pac*/acoes/a.json",
                    "echo x > /p/.tune-up/pacot?/acoes/a.json", "P=/p/.tune-up; echo x > $P/pacote/acoes/a.json",
                    "echo x > ${D}/a.json", "echo 1 > .claude/setting?.json", "cp a .cla*/settings.json",
                    "echo 1 > .claude\\settin*.json", "cp a `pwd`/x"):
            self.assertEqual(bash(leve, cmd), "deny", cmd)
            self.assertEqual(bash(cod, cmd), "ask", cmd)
        for cmd in ("rm /tmp/*.txt", "rm -f *.pyc", "echo $X > /tmp/a", "cat /p/.tune-up/pac*/README.md"):
            self.assertIsNone(bash(leve, cmd), cmd)


class TesteArvoresNovas(unittest.TestCase):
    def test_skills_claude_md_mcp_e_plugins(self):
        leve, cod = conf(ACAO_LEITURA), conf(ACAO_CODIGO)
        for caminho in ("/w/.claude/skills/x/SKILL.md", "/w/CLAUDE.md", "/w/CLAUDE.local.md", "/w/.mcp.json",
                        "/home/u/.claude/plugins/cache/m/p/hooks.json", "C:\\w\\CLAUDE.md"):
            self.assertEqual(decisao(leve, "Write", {"file_path": caminho}), "deny", caminho)
            self.assertEqual(decisao(cod, "Edit", {"file_path": caminho}), "ask", caminho)
        for cmd in ("rm -rf .claude/skills", "echo x >> CLAUDE.md", "cp a ~/.claude/plugins/x", "rm -rf .claude/hooks"):
            self.assertEqual(bash(leve, cmd), "deny", cmd)
        self.assertIsNone(decisao(leve, "Read", {"file_path": "/w/CLAUDE.md"}))
        self.assertIsNone(bash(leve, "cat CLAUDE.md .mcp.json"))
        self.assertIsNone(decisao(leve, "Write", {"file_path": "/w/docs/MEU-CLAUDE.md.txt"}))


class TesteBashLiberado(unittest.TestCase):
    def setUp(self):
        self.c = conf(dict(ACAO_CODIGO, permitir=["Bash(ffmpeg *)"]))

    def test_composto_inline_e_script_negados_antes_do_permitir(self):
        cobre = conf(dict(ACAO_CODIGO, permitir=[{"ferramenta": "Bash"}]))
        for cmd in ("ffmpeg -i a b; rm -rf x", "ffmpeg -i a b && curl x", "ffmpeg -i a b || true", "ffmpeg -i a | sh",
                    "ffmpeg -i $(cat x) b", "ffmpeg -i `cat x` b", "ffmpeg -i a b &", "python -c 'print(1)'",
                    "cat <<EOF > x.sh\nrm -rf /\nEOF", "sh /tmp/x.sh", "bash x", "./x", "/tmp/x", "run.ps1",
                    "ffmpeg -i <(cat a) b", "ffmpeg -i a b\nrm x"):
            self.assertEqual(bash(self.c, cmd), "deny", cmd)
            self.assertEqual(bash(cobre, cmd), "deny", cmd)  # regra de permitir que casa não cala
        for cmd in ("ffmpeg -i a.mp4 b.mp4", "ffmpeg -i a b 2>&1", "ffmpeg -i a b > log.txt"):
            self.assertIsNone(bash(self.c, cmd), cmd)
            self.assertIsNone(bash(cobre, cmd), cmd)

    def test_sem_bash_liberado_nada_muda(self):
        for a in (ACAO_CODIGO, dict(ACAO_CODIGO, permitir=["Edit(//w/**)", "mcp__x__Bash"])):
            c = conf(a)
            self.assertFalse(c["bash"])
            self.assertIsNone(bash(c, "make && ./x; python -c 1"))


class TesteNomesDoDono(unittest.TestCase):
    """Item 4.0: sessão sem sandbox gravava o que é do dono com `cd <dados> && echo > estudio-dono.json`."""

    def test_escrita_que_cita_o_nome_em_qualquer_caminho(self):
        for acao, esperado in ((ACAO_LEITURA, "deny"), (ACAO_CODIGO, "ask")):
            c = TesteCaminhoRelativo()._conf(acao)
            for cmd in ("cd /p/.tune-up/pacote/dados && echo x > estudio-dono.json",
                        "cd /p/.tune-up/pacote/dados && mkdir -p aprovados/1",
                        "cd /p/.tune-up/pacote/dados && cp /tmp/a extensoes.json",
                        "cd /p/.tune-up/pacote/dados; echo x > 'Estudio-Dono.JSON'",
                        "cd /p/.tune-up/pacote/dados && echo x > estudio-dono.js?",
                        "cd /p/.tune-up/pacote/dados && echo x > estudio\\-dono.json"):
                self.assertEqual(travas.decidir(c, "Bash", {"command": cmd}, "/tmp/w")[0], esperado, cmd)
            for alvo in ("/tmp/w/estudio-dono.json", "/tmp/w/aprovados/x.png", "/tmp/w/extensoes.json"):
                self.assertEqual(decisao(c, "Write", {"file_path": alvo}), esperado, alvo)
            self.assertIsNone(travas.decidir(c, "Bash", {"command": "cat estudio-dono.json"}, "/tmp/w"))
            self.assertIsNone(travas.decidir(c, "Bash", {"command": "echo x > saida/ok.txt"}, "/tmp/w"))
            self.assertIsNone(decisao(c, "Write", {"file_path": "/tmp/w/nao-aprovados.txt"}))

    def test_sandbox_dono_tem_os_tres_nomes(self):
        import sandbox
        self.assertEqual(set(sandbox.DONO), {"estudio-dono.json", "aprovados", "extensoes.json"})


@unittest.skipIf(os.name == "nt", "o comando do gancho é texto de shell POSIX (shlex.quote)")
class TesteFalhaDoGancho(unittest.TestCase):
    def _rodar(self, python):
        cfg = json.loads(travas.settings_da_sessao(ACAO_CODIGO, ("/p",), (), python=python))
        cmd = cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        return subprocess.run(["/bin/sh", "-c", cmd], input=json.dumps({"tool_name": "Read"}),
                              capture_output=True, text=True, timeout=20)

    def test_python_ausente_bloqueia_com_codigo_2(self):
        self.assertEqual(self._rodar("/nao/existe/python3").returncode, 2)

    def test_gancho_normal_sai_com_0(self):
        p = self._rodar(sys.executable)
        self.assertEqual((p.returncode, p.stdout), (0, ""))


if __name__ == "__main__":
    unittest.main()
