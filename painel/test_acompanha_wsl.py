"""B4: executions recorded with lado=wsl are followed on the WSL side; host ones keep the host side.

Nothing calls wsl.exe or claude for real: runner, probe, anchor and the WSL projects folder are injected.
Run: python3 -B -m unittest test_acompanha_wsl  (from painel/)
"""
import json
import os
import time
import unittest

import abrir_win
import lancador_wsl
import modulos
import transcricao
import wsl
from erros import ErroAcao
from test_lancador_wsl import NAO, PASTA, PASTA_W, Base, SondaFalsa

SID_W = "aaaaaaaa-1111-4222-8333-444444444444"
SID_H = "bbbbbbbb-1111-4222-8333-444444444444"
AG_WSL = [wsl.exe_wsl(), "-d", "tune-up", "-u", "tuneup", "--exec", wsl.CLAUDE_BIN, "agents", "--json", "--all"]
DATA = [wsl.exe_wsl(), "-d", "tune-up", "--exec", "/usr/bin/date", "+%s"]


def linha(id_, sid, state="working", status="idle", pid=1):
    return {"id": id_, "sessionId": sid, "state": state, "status": status, "pid": pid}


class Lados(Base):
    def setUp(self):
        super().setUp()
        self.host = [linha("aa111111", SID_H)]
        self.wsl_ = [linha("bb222222", SID_W)]
        self.agora_w, self.falha = str(int(time.time())), set()
        self.saida = {}
        self.proj = os.path.join(self.tmp, "proj_wsl")

    def rodar(self, cmd, cwd, timeout):
        self.chamadas.append((list(cmd), cwd))
        if cmd == AG_WSL:
            return (1, "", "x") if "wsl" in self.falha else (0, json.dumps(self.wsl_), "")
        if cmd == DATA:
            return (1, "", "x") if "data" in self.falha else (0, self.agora_w + "\n", "")
        if cmd[1:2] == ["agents"]:
            return (1, "", "x") if "host" in self.falha else (0, json.dumps(self.host), "")
        return self.saida.get(tuple(cmd[-2:-1]) or None) or self.resposta or (0, "", "")

    def montar(self, plataforma="win32", sonda=None, host=True, wsl_=True, **extra):
        l = self.lanc(plataforma, sonda)
        l.projects_wsl = lambda: self.proj
        t = time.time()
        regs = []
        negar = sorted(modulos.regras_de_negar(l.cfg))
        base = {"nome": "n", "acao": "t.caixa", "grupo": "dev", "titulo": "T", "params": {}, "risco": "codigo",
                "iniciada_em": "2026-11-18T10:00:00", "iniciada_ts": t - 3600, "negar_modulos": negar}
        if host:
            regs.append(dict(base, id="aa111111", sessao_id=SID_H, cwd=l.cfg["workspace"], sandbox=False))
        if wsl_:
            regs.append(dict(dict(base, id="bb222222", sessao_id=SID_W, cwd=PASTA, sandbox=True, lado="wsl",
                                  cwd_wsl=PASTA_W), **extra))
        os.makedirs(l.registro.pasta, exist_ok=True)
        l.registro.gravar(regs)
        return l

    def wsl_chamadas(self):
        return [c for c, _ in self.chamadas if c[:1] == [wsl.exe_wsl()]]

    def por_id(self, l):
        return {e["id"]: e for e in l.execucoes(forcar=True)}

    def transcricao(self, cwd_wsl, sid, mtime):
        pasta = os.path.join(self.proj, transcricao.pasta_do_projeto(cwd_wsl))
        os.makedirs(pasta, exist_ok=True)
        arq = os.path.join(pasta, sid + ".jsonl")
        with open(arq, "w") as f:
            f.write("{}\n")
        os.utime(arq, (mtime, mtime))
        return arq


class TesteListas(Lados):
    def test_lista_wsl_argv_exato_sem_portao(self):
        l = self.montar()
        ex = self.por_id(l)
        self.assertIn(AG_WSL, self.wsl_chamadas())
        self.assertIn(DATA, self.wsl_chamadas())
        for c in self.wsl_chamadas():
            self.assertNotIn("--", c)
            self.assertNotIn(wsl.PORTAO, c)
        self.assertEqual(ex["bb222222"]["estado"], "rodando")
        self.assertNotIn("aviso", ex["bb222222"])

    def test_cada_lado_so_na_sua_lista(self):
        self.wsl_ = [linha("aa111111", SID_H, "done", "")]  # same id on the other side: never matched
        self.host = [linha("bb222222", SID_W, "done", "")]
        ex = self.por_id(self.montar())
        self.assertEqual(ex["aa111111"]["estado"], "sumiu")
        self.assertEqual(ex["bb222222"]["estado"], "sumiu")

    def test_sonda_nao_pronta_nao_busca(self):
        l = self.montar(sonda=SondaFalsa(atual=NAO))
        ex = self.por_id(l)
        self.assertEqual(self.wsl_chamadas(), [])
        self.assertEqual(ex["bb222222"]["estado"], "rodando")  # last known (none yet): as the host does
        self.assertIn("WSL", ex["bb222222"]["aviso"])
        self.assertNotIn("aviso", ex["aa111111"])

    def test_sem_execucao_wsl_viva_nao_busca(self):
        l = self.montar(terminou_em="2026-11-18T10:05:00")
        ex = self.por_id(l)
        self.assertEqual(self.wsl_chamadas(), [])
        self.assertEqual(ex["bb222222"]["estado"], "terminou")

    def test_falha_do_host_mantem_o_wsl(self):
        l = self.montar()
        self.host = [linha("aa111111", SID_H, "done", "")]
        self.assertEqual(self.por_id(l)["aa111111"]["estado"], "terminou")
        self.falha = {"host"}
        self.wsl_ = [linha("bb222222", SID_W, "stopped", "")]
        ex = self.por_id(l)
        self.assertEqual(ex["aa111111"]["estado"], "terminou")  # last known
        self.assertIn("neste computador", ex["aa111111"]["aviso"])
        self.assertEqual(ex["bb222222"]["estado"], "parada")  # the WSL side proceeded
        self.assertNotIn("aviso", ex["bb222222"])

    def test_falha_do_wsl_mantem_o_host(self):
        l = self.montar()
        self.wsl_ = [linha("bb222222", SID_W, "blocked", "waiting")]
        self.assertEqual(self.por_id(l)["bb222222"]["estado"], "precisa_de_voce")
        self.falha = {"wsl"}
        self.host = [linha("aa111111", SID_H, "stopped", "")]
        ex = self.por_id(l)
        self.assertEqual(ex["bb222222"]["estado"], "precisa_de_voce")
        self.assertIn("WSL", ex["bb222222"]["aviso"])
        self.assertEqual(ex["aa111111"]["estado"], "parada")
        self.assertNotIn("aviso", ex["aa111111"])

    def test_registro_so_do_host_zero_wsl(self):
        for plat in ("win32", "darwin"):
            self.chamadas = []
            l = self.montar(plataforma=plat, wsl_=False)
            l.execucoes(forcar=True)
            l.parar("aa111111")
            l.abrir_janela = lambda *a: True
            l.abrir("aa111111")
            self.assertEqual(self.wsl_chamadas(), [], plat)

    def test_teto_conta_os_dois_lados(self):
        l = self.montar()
        l.cfg["max_execucoes"] = 2
        with self.assertRaises(ErroAcao) as e:
            l.iniciar("t.caixa", {"ideia": "oi"})
        self.assertEqual(e.exception.codigo, 409)
        self.assertIn("2 rodando", e.exception.mensagem)


class TesteOcioso(Lados):
    def test_relogio_wsl_adiantado_10_min(self):
        agora = time.time()
        self.transcricao(PASTA_W, SID_W, agora)  # Windows clock: just written
        self.agora_w = str(int(agora + 600))  # distro clock: 10 minutes later
        self.assertEqual(self.por_id(self.montar())["bb222222"]["estado"], "terminou")

    def test_relogio_wsl_atrasado_10_min(self):
        agora = time.time()
        self.transcricao(PASTA_W, SID_W, agora - 600)  # Windows clock: 10 minutes old
        self.agora_w = str(int(agora - 590))  # distro clock: written 10 s ago
        self.assertEqual(self.por_id(self.montar())["bb222222"]["estado"], "rodando")

    def test_sem_relogio_wsl_nao_termina_por_ocioso(self):
        self.transcricao(PASTA_W, SID_W, time.time() - 3600)
        self.falha = {"data"}
        self.assertEqual(self.por_id(self.montar())["bb222222"]["estado"], "rodando")


class TestePastas(Lados):
    def test_localhost_antes_de_wsl_dolar(self):
        self.assertEqual(wsl.projects_dir_wsl(lambda p: True), "\\\\wsl.localhost\\tune-up\\home\\tuneup\\.claude\\projects")
        self.assertEqual(wsl.projects_dir_wsl(lambda p: p.startswith("\\\\wsl$")),
                         "\\\\wsl$\\tune-up\\home\\tuneup\\.claude\\projects")
        self.assertIsNone(wsl.projects_dir_wsl(lambda p: False))

    def test_transcricao_pelo_cwd_wsl(self):
        l = self.montar()
        arq = self.transcricao(PASTA_W, SID_W, time.time())
        reg = l.achar("bb222222")
        self.assertEqual(lancador_wsl.localizar(l, reg, SID_W), arq)
        self.assertIn("-mnt-c-Users-Ana", arq)

    def test_pasta_ausente_transcricao_vazia(self):
        l = self.montar()
        l.projects_wsl = lambda: None
        reg = l.achar("bb222222")
        self.assertIsNone(lancador_wsl.localizar(l, reg, SID_W))
        self.assertEqual(transcricao.ler(lancador_wsl.localizar(l, reg, SID_W), 0)["eventos"], [])
        self.assertEqual(self.por_id(l)["bb222222"]["estado"], "rodando")

    def test_host_continua_na_pasta_do_host(self):
        l = self.montar()
        reg = l.achar("aa111111")
        pasta = os.path.join(l.cfg["projects_dir"], transcricao.pasta_do_projeto(reg["cwd"]))
        os.makedirs(pasta)
        arq = os.path.join(pasta, SID_H + ".jsonl")
        open(arq, "w").close()
        self.assertEqual(lancador_wsl.localizar(l, reg, SID_H), arq)


class TestePararResponder(Lados):
    def test_parar_wsl_sem_portao(self):
        l = self.montar()
        l.parar("bb222222")
        stop = [wsl.exe_wsl(), "-d", "tune-up", "-u", "tuneup", "--exec", wsl.CLAUDE_BIN, "stop", "bb222222"]
        self.assertIn(stop, [c for c, _ in self.chamadas])
        l.parar("aa111111")
        self.assertIn(["claude", "stop", "aa111111"], [c for c, _ in self.chamadas])

    def responder(self, saida):
        self.wsl_ = [linha("bb222222", SID_W, "done", "", None)]  # no pid/status: the process already left
        l = self.montar(sandbox=False)  # sandbox runs cannot be resumed; routing is by lado, not by sandbox
        l.dormir = lambda s: None
        self.saida = {(SID_W,): saida}
        return l

    def test_retomar_pelo_portao_e_copia_apagada_sem_portao(self):
        l = self.responder((0, "backgrounded · c0ffee12 · x\n", ""))
        with self.assertRaises(ErroAcao):
            l.responder("bb222222", "continua")
        cmds = [c for c, _ in self.chamadas]
        retomar = [wsl.exe_wsl(), "-d", "tune-up", "--cd", PASTA_W, "--exec", wsl.PORTAO, wsl.CLAUDE_BIN,
                   "--bg", "--resume", SID_W, "continua"]
        self.assertIn(retomar, cmds)
        for acao in ("stop", "rm"):
            self.assertIn([wsl.exe_wsl(), "-d", "tune-up", "-u", "tuneup", "--exec", wsl.CLAUDE_BIN, acao,
                           "c0ffee12"], cmds)
        for c in self.wsl_chamadas():
            self.assertNotIn("--", c)
            if wsl.PORTAO in c:
                self.assertIn("--resume", c)

    def test_portao_97_na_retomada(self):
        l = self.responder((97, "", "negado"))
        with self.assertRaises(ErroAcao) as e:
            l.responder("bb222222", "continua")
        self.assertEqual(e.exception.codigo, 409)
        self.assertEqual(self.sonda.zeradas, 1)


class TesteAttach(Lados):
    def test_comando_attach_wsl(self):
        ex = self.por_id(self.montar())
        self.assertEqual(ex["bb222222"]["comando_attach"],
                         "%s -d tune-up -u tuneup --exec %s attach bb222222" % (wsl.exe_wsl(), wsl.CLAUDE_BIN))
        self.assertEqual(ex["aa111111"]["comando_attach"], "claude attach aa111111")

    def test_abrir_wsl_argv(self):
        dentro = [wsl.exe_wsl(), "-d", "tune-up", "-u", "tuneup", "--exec", wsl.CLAUDE_BIN, "attach", "bb222222"]
        vistos = []
        abrir = lambda a, c, n: vistos.append((a, n)) or True  # noqa: E731
        self.assertTrue(abrir_win.abrir_wsl("bb222222", "C:\\x", abrir, which=lambda n: "wt"))
        self.assertTrue(abrir_win.abrir_wsl("bb222222", "C:\\x", abrir, which=lambda n: None))
        self.assertEqual(vistos, [(["wt.exe", "-w", "0", "new-tab"] + dentro, False), (["cmd", "/k"] + dentro, True)])

    def test_abrir_pelo_lancador(self):
        l = self.montar()
        vistos = []
        l.abrir_janela = lambda a, c, n: vistos.append(a) or True
        r = l.abrir("bb222222")
        self.assertTrue(r["ok"])
        self.assertIn(wsl.exe_wsl(), vistos[0])
        self.assertEqual(vistos[0][-2:], ["attach", "bb222222"])

    def test_recusa_metacaractere(self):
        chamou = []
        self.assertIsNone(abrir_win.abrir_wsl("bb&22", "C:\\x", lambda *a: chamou.append(a), which=lambda n: "wt"))
        self.assertEqual(chamou, [])


if __name__ == "__main__":
    unittest.main()
