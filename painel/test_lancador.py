"""Testes do lançador e do catálogo. Nada chama o claude de verdade: o CLI é falso."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402

import catalogo  # noqa: E402
import config  # noqa: E402
import lancador  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
ESTADO = {"fases": [{"numero": "187", "partes": [{"id": "A", "status": "fechada"},
                                                 {"id": "C", "status": "pendente"},
                                                 {"id": "G1", "status": "rodando"}]}]}
ACOES_TESTE = {"acoes": [
    {"id": "t.parte", "grupo": "dev", "titulo": "Parte", "risco": "codigo", "confirmar": False,
     "prompt": "/tune-up:part {fase} {parte}", "nome_sessao": "Fase {fase} Parte {parte}",
     "params": [{"nome": "fase", "rotulo": "Fase", "tipo": "fase", "obrigatorio": True},
                {"nome": "parte", "rotulo": "Parte", "tipo": "parte", "obrigatorio": True}]},
    {"id": "t.texto", "grupo": "extra", "titulo": "Texto", "risco": "leitura",
     "modelo": "/x {ideia} fim",
     "params": [{"nome": "ideia", "rotulo": "Ideia", "tipo": "texto", "obrigatorio": True, "max": 20},
                {"nome": "canal", "rotulo": "Canal", "tipo": "escolha", "obrigatorio": False,
                 "opcoes": ["azul", "verde"]}]},
    {"id": "t.leve", "area": "dev", "titulo": "Leve", "risco": "leitura", "prompt": "/tune-up:status",
     "params": []},
]}


class CLIFalso:
    """Imita `claude --bg`, `agents --json --all`, `stop` e `osascript`."""

    def __init__(self):
        self.agentes, self.chamadas, self.n = [], [], 0
        self.falhar_bg = False

    def __call__(self, cmd, cwd, timeout):
        self.chamadas.append((list(cmd), cwd))
        if cmd[1:2] == ["--bg"]:
            if self.falhar_bg:
                return 1, "", "erro"
            self.n += 1
            i = "%08x" % (0xabc00000 + self.n)
            self.agentes.append({"id": i, "sessionId": i + "-1111-2222-3333-444455556666", "name": cmd[3],
                                 "cwd": cwd, "kind": "background", "state": "working"})
            return 0, "Starting background service…\n\x1b[1mbackgrounded · %s · %s\x1b[0m\n" % (i, cmd[3]), ""
        if cmd[1:2] == ["agents"]:
            return 0, json.dumps(self.agentes), ""
        if cmd[1:2] == ["stop"]:
            for a in self.agentes:
                if a["id"] == cmd[2]:
                    a["state"] = "stopped" if a["state"] == "working" else a["state"]
            return 0, "stopped " + cmd[2], ""
        if cmd[0] == "osascript":
            return 0, "", ""
        return 127, "", "?"


def ler_json(caminho):
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def cfg_teste(tmp, **extra):
    c = config.Config(workspace=tmp, raiz=tmp, claude_bin="claude", max_execucoes=3, acoes_dir=os.path.join(tmp, "acoes"),
                      dados_dir=os.path.join(tmp, "dados"), projects_dir=os.path.join(tmp, "proj"),
                      web_dir=os.path.join(tmp, "web"), nome="Teste", origens_extras=[], porta=0, versao="t",
                      pacote_dir=os.path.join(tmp, "pacote"), pacote_ok=False, acoes_pacote_dir=None,
                      painel_dir=AQUI, modulos=[], areas_acompanhamento=[], bruto={}, avisos=[])
    c.update(extra)
    return c


class TesteCatalogo(unittest.TestCase):
    def test_dev_json_real_carrega_sem_aviso(self):
        acoes, avisos = catalogo.carregar_catalogo(os.path.join(AQUI, "acoes"))
        ids = [a["id"] for a in acoes]
        for esperado in ("dev.rodar-parte", "dev.planejar-fase", "dev.investigar", "dev.status"):
            self.assertIn(esperado, ids)
        self.assertEqual([x for x in avisos if x.startswith("dev.json")], [])
        parte = [a for a in acoes if a["id"] == "dev.rodar-parte"][0]
        self.assertTrue(parte["confirmar"])
        self.assertNotIn("_prompt", catalogo.publica(parte))

    def test_acao_ruim_vira_aviso(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        with open(os.path.join(tmp, "a.json"), "w") as f:
            json.dump({"acoes": [{"id": "ok.um", "area": "dev", "risco": "leitura", "prompt": "/a"},
                                 {"id": "ruim", "area": "dev", "risco": "leitura", "prompt": "-x"},
                                 {"id": "ruim2", "area": "dev", "risco": "leitura", "prompt": "/a {nada}"},
                                 {"id": "ruim3", "grupo": "Outra Coisa", "risco": "leitura", "prompt": "/a"},
                                 {"id": "ok.um", "area": "dev", "risco": "leitura", "prompt": "/b"}]}, f)
        with open(os.path.join(tmp, "b.json"), "w") as f:
            f.write("{quebrado")
        acoes, avisos = catalogo.carregar_catalogo(tmp)
        self.assertEqual([a["id"] for a in acoes], ["ok.um"])
        self.assertEqual(len(avisos), 5)

    def test_credito_sempre_confirma(self):
        a = catalogo.validar_acao({"id": "m.x", "grupo": "extra", "risco": "credito", "prompt": "/x",
                                   "confirmar": False})
        self.assertTrue(a["confirmar"])


class TesteParams(unittest.TestCase):
    def setUp(self):
        self.acoes = {a["id"]: catalogo.validar_acao(a) for a in ACOES_TESTE["acoes"]}

    def erro(self, acao, params, estado=ESTADO):
        with self.assertRaises(catalogo.ErroAcao) as ctx:
            catalogo.validar_params(self.acoes[acao], params, estado)
        self.assertEqual(ctx.exception.codigo, 400)
        return ctx.exception.mensagem

    def test_parte_valida(self):
        v = catalogo.validar_params(self.acoes["t.parte"], {"fase": "187", "parte": "C"}, ESTADO)
        self.assertEqual(v, {"fase": "187", "parte": "C"})

    def test_fase_e_parte(self):
        self.assertIn("fechada", self.erro("t.parte", {"fase": "187", "parte": "A"}))
        self.assertIn("não tem a Parte", self.erro("t.parte", {"fase": "187", "parte": "Z"}))
        self.assertIn("fase 999", self.erro("t.parte", {"fase": "999", "parte": "C"}))
        self.assertIn("Fase inválida", self.erro("t.parte", {"fase": "18x", "parte": "C"}))
        self.assertIn("Parte inválida", self.erro("t.parte", {"fase": "187", "parte": "c;rm"}))
        self.assertIn("Preencha", self.erro("t.parte", {"fase": "187"}))

    def test_texto(self):
        self.assertIn("começar", self.erro("t.texto", {"ideia": "--dangerously-skip-permissions"}))
        self.assertIn("começar", self.erro("t.texto", {"ideia": "  -x"}))
        self.assertIn("caractere", self.erro("t.texto", {"ideia": "a\nb"}))
        self.assertIn("caractere", self.erro("t.texto", {"ideia": "a‮b"}))
        self.assertIn("20 letras", self.erro("t.texto", {"ideia": "x" * 21}))
        self.assertIn("formato", self.erro("t.texto", ["x"]))
        self.assertIn("texto", self.erro("t.texto", {"ideia": {"a": 1}}))
        self.assertIn("desconhecido", self.erro("t.texto", {"ideia": "a", "cmd": "rm"}))

    def test_escolha(self):
        self.assertIn("opções", self.erro("t.texto", {"ideia": "a", "canal": "roxo"}))
        v = catalogo.validar_params(self.acoes["t.texto"], {"ideia": " oi ", "canal": "azul"}, {})
        self.assertEqual(v, {"ideia": "oi", "canal": "azul"})

    def test_montar_nao_expande_duas_vezes(self):
        self.assertEqual(catalogo.montar("/x {ideia} fim", {"ideia": "{ideia} {outra}"}), "/x {ideia} {outra} fim")
        self.assertEqual(catalogo.montar("/x {a} {b} fim", {"a": "", "b": "z"}), "/x z fim")
        self.assertEqual(catalogo.nome_da_sessao(self.acoes["t.parte"], {"fase": "187", "parte": "C"}),
                         "Fase 187 Parte C")
        self.assertEqual(len(catalogo.nome_da_sessao(self.acoes["t.texto"], {"ideia": "x"})), 5)


class TesteEstado(unittest.TestCase):
    def test_mapear(self):
        reg = {"iniciada_ts": 1000}
        m = lancador.mapear_estado
        self.assertEqual(m(reg, {"state": "working"}, 1001), "rodando")
        self.assertEqual(m(reg, {"state": "working", "status": "busy"}, 1001), "rodando")
        self.assertEqual(m(reg, {"state": "blocked", "status": "waiting"}, 1001), "precisa_de_voce")
        self.assertEqual(m(reg, {"state": "done", "status": "idle"}, 1001), "terminou")
        self.assertEqual(m(reg, {"state": "done"}, 1001), "terminou")
        self.assertEqual(m(reg, {"state": "stopped"}, 1001), "parada")
        self.assertEqual(m(reg, {"status": "idle"}, 1001), "terminou")
        self.assertEqual(m(reg, None, 1010), "rodando")  # ainda não apareceu
        self.assertEqual(m(reg, None, 1000 + lancador.GRACA + 1), "sumiu")
        self.assertEqual(m(dict(reg, parada_pelo_painel=True), None, 5000), "parada")
        self.assertEqual(m(dict(reg, terminou_em="x", parada_pelo_painel=True), None, 5000), "terminou")


class TesteLancador(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        os.makedirs(os.path.join(self.tmp, "acoes"))
        with open(os.path.join(self.tmp, "acoes", "t.json"), "w") as f:
            json.dump(ACOES_TESTE, f)
        self.cli = CLIFalso()
        self.relogio = [1000.0]
        self.l = lancador.Lancador(cfg_teste(self.tmp), lambda: ESTADO, rodar=self.cli,
                                   relogio=lambda: self.relogio[0], plataforma="darwin")

    def test_iniciar_monta_comando_e_registra(self):
        ex = self.l.iniciar("t.parte", {"fase": "187", "parte": "C"})
        self.assertEqual(ex["estado"], "rodando")
        self.assertEqual((ex["fase"], ex["parte"], ex["nome"]), ("187", "C", "Fase 187 Parte C"))
        cmd, cwd = [c for c in self.cli.chamadas if c[0][1:2] == ["--bg"]][0]
        self.assertEqual(cmd[:4] + cmd[-1:], ["claude", "--bg", "-n", "Fase 187 Parte C", "/tune-up:part 187 C"])
        self.assertEqual(cmd[4], "--settings")  # travas de verdade da sessão (ver test_travas)
        self.assertIn("travas.py", json.loads(cmd[5])["hooks"]["PreToolUse"][0]["hooks"][0]["command"])
        self.assertEqual(len(cmd), 7)
        self.assertEqual(cwd, self.tmp)
        self.assertFalse(any(x.startswith("--") and ("skip" in x or "permission" in x) for x in cmd))
        arq = os.path.join(self.tmp, "dados", "execucoes.json")
        if os.name != "nt":  # Windows não tem modo 0600/0700
            self.assertEqual(stat.S_IMODE(os.stat(arq).st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.tmp, "dados")).st_mode), 0o700)
        regs = ler_json(arq)
        self.assertEqual(regs[0]["id"], ex["id"])
        lista = self.l.execucoes(forcar=True)
        self.assertEqual(lista[0]["sessao_id"], ex["id"] + "-1111-2222-3333-444455556666")
        self.assertEqual(ler_json(arq)[0]["sessao_id"], lista[0]["sessao_id"])  # aprendeu e gravou
        self.assertEqual(lista[0]["comando_attach"], "claude attach " + ex["id"])

    def test_409_mesma_acao_e_params(self):
        ex = self.l.iniciar("t.parte", {"fase": "187", "parte": "C"})
        with self.assertRaises(lancador.ErroAcao) as ctx:
            self.l.iniciar("t.parte", {"fase": "187", "parte": "C"})
        self.assertEqual((ctx.exception.codigo, ctx.exception.execucao_id), (409, ex["id"]))
        self.l.iniciar("t.parte", {"fase": "187", "parte": "G1"})  # params diferentes: pode
        self.cli.agentes[0]["state"] = "done"
        self.l.esquecer_agentes()
        self.l.iniciar("t.parte", {"fase": "187", "parte": "C"})  # a primeira terminou: pode de novo

    def test_pular_permissoes_so_quando_ligado(self):
        self.l.iniciar("t.leve", {})
        cmd = [c[0] for c in self.cli.chamadas if c[0][1:2] == ["--bg"]][-1]
        self.assertNotIn("--dangerously-skip-permissions", cmd)
        self.cli.agentes[0]["state"] = "done"
        self.l.esquecer_agentes()
        self.l.cfg["pular_permissoes"] = True
        self.l.iniciar("t.leve", {})
        cmd = [c[0] for c in self.cli.chamadas if c[0][1:2] == ["--bg"]][-1]
        self.assertEqual(cmd[:5], ["claude", "--bg", "-n", cmd[3], "--dangerously-skip-permissions"])
        self.assertIn("--settings", cmd)  # as travas continuam indo junto
        self.assertFalse(cmd[-1].startswith("-"))

    def test_409_teto(self):
        self.l.cfg["max_execucoes"] = 2
        self.l.iniciar("t.leve", {})
        self.l.iniciar("t.texto", {"ideia": "a"})
        with self.assertRaises(lancador.ErroAcao) as ctx:
            self.l.iniciar("t.texto", {"ideia": "b"})
        self.assertEqual(ctx.exception.codigo, 409)
        self.assertIn("2 rodando", ctx.exception.mensagem)
        self.cli.agentes[0]["state"] = "blocked"  # precisa de você ainda conta no teto
        self.l.esquecer_agentes()
        with self.assertRaises(lancador.ErroAcao):
            self.l.iniciar("t.texto", {"ideia": "b"})

    def test_acao_inexistente_e_falha_do_cli(self):
        with self.assertRaises(lancador.ErroAcao) as ctx:
            self.l.iniciar("nao.existe", {})
        self.assertEqual(ctx.exception.codigo, 400)
        self.cli.falhar_bg = True
        with self.assertRaises(lancador.ErroAcao) as ctx:
            self.l.iniciar("t.leve", {})
        self.assertEqual(ctx.exception.codigo, 500)
        self.assertEqual(self.l.registro.ler(), [])

    def test_parar_abrir_e_sumir(self):
        ex = self.l.iniciar("t.leve", {})
        self.assertEqual(self.l.parar(ex["id"]), {"ok": True})
        self.assertEqual(self.l.execucoes(forcar=True)[0]["estado"], "parada")
        r = self.l.abrir(ex["id"])
        self.assertEqual(r, {"ok": True, "comando": "claude attach " + ex["id"]})
        osa = [c[0] for c in self.cli.chamadas if c[0][0] == "osascript"][0]
        self.assertEqual(osa[-1], "claude attach " + ex["id"])  # comando só como argv
        self.assertNotIn(ex["id"], " ".join(osa[:-1]))
        with self.assertRaises(lancador.ErroAcao) as ctx:
            self.l.parar("deadbeef")  # não foi o painel que disparou
        self.assertEqual(ctx.exception.codigo, 404)
        with self.assertRaises(lancador.ErroAcao):
            self.l.abrir("x; rm -rf /")
        fora = lancador.Lancador(self.l.cfg, lambda: ESTADO, rodar=self.cli, plataforma="linux")
        self.assertEqual(fora.abrir(ex["id"])["ok"], False)

    def test_terminou_sobrevive_ao_rm(self):
        ex = self.l.iniciar("t.leve", {})
        self.cli.agentes[0]["state"] = "done"
        self.assertEqual(self.l.execucoes(forcar=True)[0]["estado"], "terminou")
        self.cli.agentes.clear()  # claude rm
        self.relogio[0] += 1000
        self.assertEqual(self.l.execucoes(forcar=True)[0]["estado"], "terminou")
        self.assertEqual(self.l.achar(ex["id"])["id"], ex["id"])

    def test_disparo_concorrente_respeita_409(self):
        erros, oks = [], []

        def tentar():
            try:
                oks.append(self.l.iniciar("t.leve", {}))
            except lancador.ErroAcao as e:
                erros.append(e.codigo)
        ts = [threading.Thread(target=tentar) for _ in range(5)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual((len(oks), erros), (1, [409] * 4))

    def test_registro_corrompido_nao_quebra(self):
        os.makedirs(os.path.join(self.tmp, "dados"))
        with open(os.path.join(self.tmp, "dados", "execucoes.json"), "w") as f:
            f.write("[{\"id\": \"../x\"}, 3, {\"id\": \"abcdef12\"}")
        self.assertEqual(self.l.execucoes(), [])


class TesteConfigELeitor(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_padroes_sem_arquivo(self):
        repo = os.path.join(self.tmp, "Meu Repo")
        os.makedirs(os.path.join(repo, ".git"))
        os.makedirs(os.path.join(repo, ".planning", "phases"))
        c = config.carregar(self.tmp)
        self.assertEqual((c["repo"], c["plans_dir"], c["plans_origem"]),
                         (repo, os.path.join(repo, ".planning"), "padrão"))
        self.assertEqual((c["max_execucoes"], c["claude_bin"], c.nome), (3, "claude", os.path.basename(self.tmp)))

    def test_arquivo_e_valores_ruins(self):
        os.makedirs(os.path.join(self.tmp, ".tune-up", "meu-pacote", "acoes"))
        with open(os.path.join(self.tmp, ".tune-up", "painel.json"), "w") as f:
            json.dump({"nome": "Loja", "plans_dir": "planos", "max_execucoes": 99, "claude_bin": "-x",
                       "origens_extras": ["http://127.0.0.1:5173", "http://evil:1"], "pacote": "meu-pacote",
                       "modulos": ["vendas", "../fora", "vendas"],
                       "areas_acompanhamento": [{"id": "vendas", "titulo": "Vendas", "regex": "^venda-"},
                                                {"id": "ruim", "regex": "(["}, {"id": "X Y", "regex": "a"}]}, f)
        c = config.carregar(self.tmp, home=self.tmp)
        self.assertEqual((c.nome, c.plans_dir, c.plans_origem), ("Loja", os.path.join(self.tmp, "planos"),
                                                                 "painel.json"))
        self.assertEqual((c.max_execucoes, c.claude_bin), (10, "claude"))
        self.assertEqual(c.origens_extras, ["http://127.0.0.1:5173"])
        self.assertEqual((c.pacote_ok, c.modulos), (True, ["vendas"]))
        self.assertEqual(c.acoes_pacote_dir, os.path.join(self.tmp, ".tune-up", "meu-pacote", "acoes"))
        self.assertEqual(c.dados_dir, os.path.join(self.tmp, ".tune-up", "meu-pacote", "dados"))
        self.assertEqual([a["id"] for a in c.areas_acompanhamento], ["vendas"])
        self.assertTrue(any("guarda" in a or "tune-up" in a for a in c.avisos), c.avisos)
        self.assertGreaterEqual(len(c.avisos), 4)

    def test_pacote_nao_sai_de_tune_up(self):
        os.makedirs(os.path.join(self.tmp, ".tune-up"))
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(fora)
        os.symlink(fora, os.path.join(self.tmp, ".tune-up", "painel-projeto"))
        c = config.carregar(self.tmp, home=self.tmp)
        self.assertFalse(c.pacote_ok)
        self.assertFalse(c.dados_dir.startswith(fora))
        with open(os.path.join(self.tmp, ".tune-up", "painel.json"), "w") as f:
            json.dump({"pacote": "../fora"}, f)
        self.assertFalse(config.carregar(self.tmp, home=self.tmp).pacote_ok)

    def test_achar_raiz(self):
        fundo = os.path.join(self.tmp, "proj", "a", "b")
        os.makedirs(fundo)
        os.makedirs(os.path.join(self.tmp, "proj", ".tune-up"))
        proj = os.path.join(self.tmp, "proj")
        self.assertEqual(config.achar_raiz(None, fundo, {}), (proj, "cwd"))
        self.assertEqual(config.achar_raiz(None, fundo, {config.ENV_PROJETO: self.tmp}),
                         (self.tmp, config.ENV_PROJETO))
        self.assertEqual(config.achar_raiz(fundo, None, {config.ENV_PROJETO: self.tmp}), (fundo, "--projeto"))
        self.assertEqual(config.achar_raiz(None, "/", {})[1], "pasta do painel")

    def test_achar_guarda_pelo_registro_do_plugin(self):
        self.assertIsNone(config.achar_guarda(self.tmp)[0])
        velho = os.path.join(self.tmp, "cache", "tune-up", "1.0.0", "scripts")
        novo = os.path.join(self.tmp, "cache", "tune-up", "2.0.0", "scripts")
        for p in (velho, novo):
            os.makedirs(p)
            open(os.path.join(p, "guarda.py"), "w").close()
        os.makedirs(os.path.join(self.tmp, ".claude", "plugins"))
        with open(os.path.join(self.tmp, ".claude", "plugins", "installed_plugins.json"), "w") as f:
            json.dump({"version": 2, "plugins": {
                "tune-up@loja": [{"installPath": os.path.dirname(velho), "lastUpdated": "2026-01-01"},
                                 {"installPath": os.path.dirname(novo), "lastUpdated": "2026-02-01"}],
                "tune-up-extra@loja": [{"installPath": "/nao/existe"}]}}, f)
        self.assertEqual(config.achar_guarda(self.tmp), (os.path.join(novo, "guarda.py"), None))

    def test_leitor_nao_segue_atalho_nem_nome_com_caminho(self):
        import leitor
        plans = os.path.join(self.tmp, "plans")
        fase = os.path.join(plans, "phases", "001-x")
        os.makedirs(fase)
        fora = os.path.join(self.tmp, "fora.md")
        with open(fora, "w") as f:
            f.write("| Parte | Itens |\n|---|---|\n| A | a |\n")
        os.symlink(fora, os.path.join(fase, "GOAL.md"))
        avisos = []
        self.assertIsNone(leitor.ler_texto(os.path.join(fase, "GOAL.md"), avisos, plans))
        self.assertIn("atalho", avisos[0])
        os.symlink(self.tmp, os.path.join(plans, "phases", "002-fuga"))
        avisos = []
        self.assertNotIn("002-fuga", [os.path.basename(p) for p in leitor.listar_fases(plans, avisos)])
        avisos = []
        nomes = leitor.nomes_de({"names": {"goal": "../../etc/passwd", "progress": "P.md", "later": "/abs"}},
                                avisos, cfg_teste(self.tmp))
        self.assertEqual((nomes["goal"], nomes["progress"], nomes["later"]), ("GOAL.md", "P.md", "DEPOIS.md"))
        self.assertEqual(len(avisos), 2)


if __name__ == "__main__":
    unittest.main()


class TestOcioso(unittest.TestCase):
    def test_working_idle_sem_atividade_vira_terminou(self):
        import lancador as L
        reg = {"id": "abcd1234", "iniciada_ts": 0}
        ag = {"state": "working", "status": "idle"}
        self.assertEqual(L.mapear_estado(reg, ag, 1000), "rodando")              # sem sinal: não chuta
        self.assertEqual(L.mapear_estado(reg, ag, 1000, L.OCIOSO - 1), "rodando")
        self.assertEqual(L.mapear_estado(reg, ag, 1000, L.OCIOSO + 1), "terminou")
        self.assertEqual(L.mapear_estado(reg, {"state": "working", "status": "busy"}, 1000, 9999), "rodando")
        self.assertEqual(L.mapear_estado(reg, {"state": "blocked", "status": "waiting"}, 1000, 9999), "precisa_de_voce")


class TesteMigrarRegistro(unittest.TestCase):
    """O registro da versão antiga (<painel>/dados) vem para o pacote uma vez, sem perder execução."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.antiga = os.path.join(self.tmp, ".tune-up", "painel", "dados")
        os.makedirs(self.antiga)
        os.makedirs(os.path.join(self.tmp, ".tune-up", "painel-projeto"))
        self.lista = [{"id": "9ea4b68b", "titulo": "Rodar uma Parte", "sessao_id": "s1"}]
        with open(os.path.join(self.antiga, "execucoes.json"), "w") as f:
            json.dump(self.lista, f)
        self.cfg = config.carregar(self.tmp, home=self.tmp)

    def test_copia_uma_vez_com_aviso(self):
        aviso = config.migrar_registro_antigo(self.cfg, self.antiga)
        self.assertIn("registro de execuções trazido", aviso)
        self.assertIn(aviso, self.cfg["avisos"])
        reg = lancador.Registro(self.cfg["dados_dir"])
        self.assertEqual([r["id"] for r in reg.ler()], ["9ea4b68b"])
        if os.name != "nt":  # Windows não tem modo 0600/0700
            self.assertEqual(stat.S_IMODE(os.stat(self.cfg["dados_dir"]).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(reg.arquivo).st_mode), 0o600)
        self.assertTrue(os.path.isfile(os.path.join(self.antiga, "execucoes.json")))  # painel antigo segue lendo
        reg.gravar([])  # o novo já existe: não volta a copiar por cima
        self.assertIsNone(config.migrar_registro_antigo(self.cfg, self.antiga))
        self.assertEqual(reg.ler(), [])

    def test_pasta_de_outro_projeto_nao_migra(self):
        outro = os.path.join(self.tmp, "x", ".tune-up", "painel", "dados")
        shutil.copytree(self.antiga, outro)
        self.assertIsNone(config.migrar_registro_antigo(self.cfg, outro))
        self.assertFalse(os.path.exists(os.path.join(self.cfg["dados_dir"], "execucoes.json")))
