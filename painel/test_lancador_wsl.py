"""B3b: a sandboxed action launched from the Windows panel runs inside the tune-up distro.

Nothing calls wsl.exe or claude for real: the runner, probe and anchor are fakes injected into Lancador.
Run: python3 -B -m unittest test_lancador_wsl  (from painel/)
"""
import json
import os
import re
import shutil
import tempfile
import unittest
from unittest import mock

import lancador
import lancador_wsl
import trabalho
import travas
import wsl
from erros import ErroAcao
from test_lancador import ACOES_TESTE, cfg_teste

WS = "C:\\Users\\Ana\\Projetos\\loja"
PACOTE = WS + "\\.tune-up\\painel"
DADOS = PACOTE + "\\dados"
PASTA = DADOS + "\\trabalhos\\abc"
PASTA_W = "/mnt/c/Users/Ana/Projetos/loja/.tune-up/painel/dados/trabalhos/abc"
PLUGIN_WIN = "C:\\Users\\Ana\\.claude\\plugins\\cache\\mkt\\tune-up\\1.0.0"
PLUGIN_DIR = "/home/tuneup/.claude/plugins/cache/mkt/tune-up/1.0.0"
TRAVAS_WSL = {"este_arquivo": PLUGIN_WIN + "\\painel\\travas.py", "codigo": [PLUGIN_WIN + "\\tune-up-studio"]}
PERIGO = "$(id) R$99 `id` \"duplas\" 'simples'"
CAIXA = {"id": "t.caixa", "grupo": "dev", "titulo": "Caixa", "risco": "codigo", "sandbox": True,
         "prompt": "Grave em {trabalho}/x.txt: " + PERIGO + " {ideia}",
         "params": [{"nome": "ideia", "rotulo": "Ideia", "tipo": "texto", "obrigatorio": True, "max": 40}]}
PRONTA = {"pronta": True, "motivo": "pronta",
          "marcador": {"versao": 1, "usuario": "tuneup", "claude_bin": wsl.CLAUDE_BIN, "plugin_dir": PLUGIN_DIR}}
NAO = {"pronta": False, "motivo": "a distro tune-up não está instalada no WSL.", "marcador": {}}
WIN_PATH = re.compile(r"(?i)(^|[^a-z])[a-z]:[\\/]")


class SondaFalsa:
    def __init__(self, ler=PRONTA, atual=PRONTA):
        self.v, self.atual, self.lidas, self.zeradas = ler, atual, 0, 0

    def ler(self, forcar=False):
        self.lidas += 1
        return self.v

    def zerar(self):
        self.zeradas += 1

    def valor_atual(self):
        return self.atual


class AncoraFalsa:
    def __init__(self, log, ok=True):
        self.log, self.ok, self.paradas = log, ok, 0

    def garantir(self):
        self.log.append("garantir")
        return self.ok

    def parar(self):
        self.paradas += 1


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        os.makedirs(os.path.join(self.tmp, "acoes"))
        with open(os.path.join(self.tmp, "acoes", "t.json"), "w") as f:
            json.dump({"acoes": ACOES_TESTE["acoes"] + [CAIXA]}, f)
        self.log, self.chamadas, self.resposta, self.pasta = [], [], None, PASTA
        self.apagadas = []
        for nome, fazer in (("nova_pasta", lambda d, a: self.pasta if trabalho.usa(a) else None),
                            ("criar", lambda *a: None), ("apagar", self.apagadas.append)):
            p = mock.patch.object(trabalho, nome, fazer)  # the Windows work folder cannot be created on this Mac
            p.start()
            self.addCleanup(p.stop)

    def rodar(self, cmd, cwd, timeout):
        self.chamadas.append((list(cmd), cwd))
        self.log.append("rodar")
        if cmd[1:2] == ["agents"]:
            return 0, "[]", ""
        return self.resposta or (0, "backgrounded · abc12345 · x\n", "")

    def lanc(self, plataforma="win32", sonda=None, ancora_ok=True, **cfg):
        c = cfg_teste(self.tmp, **cfg)
        self.sonda = sonda or SondaFalsa()
        self.ancora = AncoraFalsa(self.log, ancora_ok)
        l = lancador.Lancador(c, lambda: {}, rodar=self.rodar, plataforma=plataforma, sonda=self.sonda,
                              ancora=self.ancora)
        c.update(workspace=WS, pacote_dir=PACOTE, dados_dir=DADOS, painel_dir=PLUGIN_WIN + "\\painel")  # registry: tmp
        l.travas_wsl = TRAVAS_WSL
        return l

    def bg(self):
        return [c for c, _ in self.chamadas if c[1:2] != ["agents"]]


class TesteArgv(Base):
    def test_argv_exato_pelo_portao(self):
        l = self.lanc()
        l.iniciar("t.caixa", {"ideia": "oi"})
        (cmd,) = self.bg()
        nome = cmd[10]
        self.assertEqual(cmd[:11], [wsl.exe_wsl(), "-d", "tune-up", "--cd", PASTA_W, "--exec",
                                    "/usr/local/bin/tune-up-exec", "/home/tuneup/.local/bin/claude", "--bg", "-n", nome])
        self.assertNotIn("--", cmd)
        self.assertEqual(cmd[-1], "Grave em %s/x.txt: %s oi" % (PASTA_W, PERIGO))
        self.assertEqual(self.chamadas[-1][1], PASTA)  # Windows cwd for the process; Linux cwd is --cd
        settings = cmd[cmd.index("--settings") + 1]
        self.assertIsNone(WIN_PATH.search(settings), settings[:300])
        self.assertIn("/mnt/c/Users/Ana/Projetos/loja/", settings)
        self.assertGreaterEqual(self.sonda.lidas, 1)

    def test_registro_tem_lado_e_cwd_wsl(self):
        l = self.lanc()
        ex = l.iniciar("t.caixa", {"ideia": "oi"})
        reg = l.achar(ex["id"])
        self.assertEqual((reg["lado"], reg["cwd_wsl"], reg["cwd"]), ("wsl", PASTA_W, PASTA))
        self.assertNotIn("avisos", ex)

    def test_pular_permissoes_nao_vale_no_wsl(self):
        l = self.lanc(pular_permissoes=True)
        ex = l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertNotIn("--dangerously-skip-permissions", self.bg()[0])
        self.assertEqual(ex["avisos"], [lancador_wsl.AVISO_PULAR])

    def test_grande_demais(self):
        l = self.lanc()
        l.travas_wsl = dict(TRAVAS_WSL, codigo=["C:\\" + "x" * 1000 + "\\%d" % i for i in range(40)])
        with self.assertRaises(ErroAcao) as e:
            l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertIn("grande demais", e.exception.mensagem)
        self.assertEqual((self.bg(), self.log.count("garantir")), ([], 0))


class TesteRecusas(Base):
    def test_sonda_nao_pronta_409_sem_rodar(self):
        l = self.lanc(sonda=SondaFalsa(ler=NAO))  # the catalog view is stale (ready), the blocking read says no
        with self.assertRaises(ErroAcao) as e:
            l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertEqual(e.exception.codigo, 409)
        self.assertIn("instalar.ps1", e.exception.mensagem)
        self.assertIn(NAO["motivo"], e.exception.mensagem)
        self.assertEqual((self.chamadas, self.log), ([], []))

    def test_sonda_nao_pronta_no_catalogo_nao_vira_host(self):
        l = self.lanc(sonda=SondaFalsa(ler=NAO, atual=NAO))
        with self.assertRaises(ErroAcao):
            l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertEqual(self.chamadas, [])

    def test_portao_97_zera_a_sonda(self):
        l = self.lanc()
        self.resposta = (97, "", "tune-up-exec: recusado\n")
        with self.assertRaises(ErroAcao) as e:
            l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertEqual(e.exception.codigo, 409)
        self.assertIn("instalar.ps1", e.exception.mensagem)
        self.assertIn("-Login", e.exception.mensagem)
        self.assertEqual(self.sonda.zeradas, 1)
        self.assertEqual(self.apagadas, [PASTA])
        self.assertEqual(l.registro.ler(), [])

    def test_pasta_sem_confianca(self):
        l = self.lanc()
        self.resposta = (1, "", "\x1b[31mError: Workspace NOT TRUSTED. Run claude once\x1b[0m")
        with self.assertRaises(ErroAcao) as e:
            l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertEqual(e.exception.codigo, 409)
        self.assertEqual(e.exception.mensagem, "Abra a pasta uma vez no WSL e aceite a confiança: wsl.exe -d tune-up "
                                               "--cd %s --exec /home/tuneup/.local/bin/claude" % PASTA_W)
        self.assertEqual(self.sonda.zeradas, 0)

    def test_falha_comum_continua_500(self):
        l = self.lanc()
        self.resposta = (1, "", "boom")
        with self.assertRaises(ErroAcao) as e:
            l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertEqual(e.exception.codigo, 500)


class TesteAncora(Base):
    def test_garantir_antes_do_disparo(self):
        l = self.lanc()
        l.iniciar("t.caixa", {"ideia": "oi"})
        i = self.log.index("garantir")
        self.assertEqual(self.log[i + 1:], ["rodar"])
        l.iniciar("t.caixa", {"ideia": "outra"})
        self.assertEqual(self.log.count("garantir"), 2)  # every WSL launch
        l.fechar()
        self.assertEqual(self.ancora.paradas, 1)

    def test_ancora_que_nao_sobe_aborta(self):
        l = self.lanc(ancora_ok=False)
        with self.assertRaises(ErroAcao) as e:
            l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertEqual(e.exception.codigo, 409)
        self.assertEqual(self.bg(), [])

    def test_ancora_padrao_e_uma_so(self):
        l = self.lanc()
        l.ancora = None
        a = lancador_wsl.ancora(l)
        self.assertIs(lancador_wsl.ancora(l), a)
        self.assertIs(a.sonda, self.sonda)


class TesteHostIgual(Base):
    def esperado(self, l, acao_id, params, pasta=None):
        acao = next(a for a in l.catalogo()[0] if a["id"] == acao_id)
        if pasta:
            acao = trabalho.resolver_travas(acao, pasta)
        return travas.argv_travas(acao, l.cfg)

    def test_sem_sandbox_no_win32_e_o_argv_de_antes(self):
        l = self.lanc(pular_permissoes=True)
        ex = l.iniciar("t.leve", {})
        cmd = self.bg()[0]
        self.assertEqual(cmd, ["claude", "--bg", "-n", cmd[3], "--dangerously-skip-permissions"]
                         + self.esperado(l, "t.leve", {}) + ["/tune-up:status"])
        self.assertNotIn("lado", l.achar(ex["id"]))
        self.assertEqual((self.sonda.lidas, self.log.count("garantir")), (0, 0))

    def test_darwin_sandbox_e_o_argv_de_antes(self):
        self.pasta = os.path.join(self.tmp, "dados", "trabalhos", "abc")
        l = self.lanc("darwin")
        l.cfg.update(workspace=self.tmp)
        ex = l.iniciar("t.caixa", {"ideia": "oi"})
        cmd = self.bg()[0]
        self.assertEqual(cmd, ["claude", "--bg", "-n", cmd[3]] + self.esperado(l, "t.caixa", {}, self.pasta)
                         + ["Grave em %s/x.txt: %s oi" % (self.pasta, PERIGO)])
        self.assertNotIn("lado", l.achar(ex["id"]))
        self.assertEqual((self.sonda.lidas, self.log.count("garantir")), (0, 0))


if __name__ == "__main__":
    unittest.main()
