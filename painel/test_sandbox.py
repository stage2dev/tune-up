"""Campo `sandbox` e `env` da ação, ação-fixture do estúdio e cwd = pasta de trabalho.

Nada chama o claude de verdade (CLI falso). A prova com sessão real fica em tests_reais/.
"""
import json
import os
import unittest

import catalogo
import sandbox
import test_chat
import trabalho
import travas

AQUI = os.path.dirname(os.path.abspath(__file__))
FIXTURE = os.path.join(AQUI, "tests_reais", "acao_estudio.json")
WS, PACOTE = "/proj [1]", "/proj [1]/.tune-up/painel"
DADOS = PACOTE + "/dados"
CFG = {"workspace": WS, "pacote_dir": PACOTE, "dados_dir": DADOS, "painel_dir": "/plugin/painel"}
SIMPLES = {"id": "dev.x", "grupo": "dev", "titulo": "X", "risco": "leitura", "prompt": "faça"}


def fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return catalogo.validar_acao(json.load(f)["acoes"][0])


def settings(acao, pasta="/proj [1]/.tune-up/painel/dados/trabalhos/abc", cfg=CFG):
    if pasta:
        acao = trabalho.resolver_travas(acao, pasta)
    return json.loads(travas.argv_travas(acao, cfg)[1])


def gancho(conf):
    import shlex
    return travas._decodificar(shlex.split(conf["hooks"]["PreToolUse"][0]["hooks"][0]["command"])[4])


class TesteValidar(unittest.TestCase):
    def test_aceita_e_recusa(self):
        self.assertEqual(sandbox.validar(SIMPLES), {"sandbox": False, "_env": {}})
        self.assertTrue(catalogo.validar_acao(dict(SIMPLES, sandbox=True))["sandbox"])
        ruins = [{"sandbox": "true"}, {"sandbox": 1}, {"sandbox": {"enabled": True}}, {"env": []},
                 {"env": {"path": "x"}}, {"env": {"PATH": "/x"}}, {"env": {"LD_PRELOAD": "x"}},
                 {"env": {"DYLD_INSERT_LIBRARIES": "x"}}, {"env": {"CLAUDE_CODE_X": "1"}},
                 {"env": {"ANTHROPIC_BASE_URL": "x"}}, {"env": {"NODE_OPTIONS": "x"}}, {"env": {"A": 1}},
                 {"sandbox": {"rede_local": 1}}, {"sandbox": {"rede_local": True, "x": 1}}, {"sandbox": {}},
                 {"env": {"A": "a\nb"}}, {"env": {"A": "x" * 201}}, {"env": {"V%d" % i: "" for i in range(21)}}]
        for ruim in ruins:
            with self.assertRaises(ValueError, msg=repr(ruim)):
                catalogo.validar_acao(dict(SIMPLES, **ruim))

    def test_rede_local(self):
        ligada = catalogo.validar_acao(dict(SIMPLES, sandbox={"rede_local": True}, so_com="dev.rede"))
        self.assertEqual((ligada["sandbox"], ligada["_rede_local"]), (True, True))
        self.assertNotIn("_rede_local", catalogo.publica(ligada))
        desligada = catalogo.validar_acao(dict(SIMPLES, sandbox={"rede_local": False}))
        self.assertEqual((desligada["sandbox"], desligada.get("_rede_local")), (True, None))
        rede = settings(desligada, pasta=None)["sandbox"]["network"]
        self.assertEqual(rede, {"strictAllowlist": True, "allowedDomains": []})  # padrão: sem escutar em localhost
        rede = settings(ligada, pasta=None)["sandbox"]["network"]
        self.assertEqual(rede, {"strictAllowlist": True, "allowedDomains": [], "allowLocalBinding": True})

    def test_env_nao_sai_na_api(self):
        a = catalogo.validar_acao(dict(SIMPLES, env={"DO_NOT_TRACK": "1"}))
        self.assertNotIn("_env", catalogo.publica(a))
        self.assertIs(catalogo.publica(a)["sandbox"], False)


class TesteSettings(unittest.TestCase):
    def test_fixture_gera_o_bloco_do_plano(self):
        conf = settings(fixture())
        self.assertEqual(conf["sandbox"], {
            "enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
            "network": {"strictAllowlist": True, "allowedDomains": [], "allowLocalBinding": True},
            "filesystem": {"denyRead": [WS + "/.env*", WS + "/*.pem", WS + "/*.key",
                                        WS + "/**/.env*", WS + "/**/*.pem", WS + "/**/*.key"],
                           "denyWrite": [DADOS + "/estudio-dono.json", DADOS + "/aprovados",
                                         DADOS + "/extensoes.json"]}})
        self.assertEqual(conf["worktree"], {"bgIsolation": "none"})
        self.assertEqual(conf["env"], {"HYPERFRAMES_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1",
                                       "HYPERFRAMES_NO_UPDATE_CHECK": "1", "HYPERFRAMES_NO_AUTO_INSTALL": "1",
                                       "HYPERFRAMES_SKIP_SKILLS": "1",
                                       "HYPERFRAMES_HISTORY_ROOT": ".hyperframes_history",
                                       "GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""})
        perm = conf["permissions"]
        self.assertIs(perm["blockWritesOutsideWorkingDirectories"], True)
        for r in ("WebFetch", "WebSearch", "mcp__*", "Read(//proj \\[1\\]/**/.env*)"):
            self.assertIn(r, perm["deny"])
        self.assertEqual(perm["allow"], ["Edit(//proj \\[1\\]/.tune-up/painel/dados/trabalhos/abc/**)"])
        self.assertEqual(len(perm["deny"]), len(set(perm["deny"])))

    def test_negar_da_acao_nao_duplica(self):
        a = catalogo.validar_acao(dict(SIMPLES, sandbox=True, negar=["WebFetch", "Bash(rm *)"]))
        deny = settings(a, pasta=None)["permissions"]["deny"]
        self.assertEqual(deny.count("WebFetch"), 1)
        self.assertIn("Bash(rm *)", deny)

    def test_sem_sandbox_nada_muda(self):
        conf = settings(catalogo.validar_acao(dict(SIMPLES, env={"DO_NOT_TRACK": "1"})), pasta=None)
        for chave in ("sandbox", "worktree"):
            self.assertNotIn(chave, conf)
        self.assertEqual(conf["permissions"], {"deny": travas.NEGAR_LEVE})  # só o de sempre (risco leitura)
        self.assertEqual(conf["env"], {"DO_NOT_TRACK": "1"})
        self.assertEqual(set(settings(catalogo.validar_acao(SIMPLES), pasta=None)), {"hooks", "permissions"})

    def test_gancho_protege_dono_e_aprovados_dentro_de_dados(self):
        g = gancho(settings(fixture()))
        for alvo in (DADOS + "/estudio-dono.json", DADOS + "/aprovados/x/manifesto.json"):
            self.assertEqual(travas.decidir(g, "Write", {"file_path": alvo})[0], "deny", alvo)
            self.assertEqual(travas.decidir(g, "Bash", {"command": "echo 1 > '%s'" % alvo})[0], "deny", alvo)
        livre = DADOS + "/trabalhos/abc/saida.png"  # o resto de <dados> segue liberado
        self.assertIsNone(travas.decidir(g, "Write", {"file_path": livre}))

    def test_windows_separador_misto_no_liberado(self):
        """No Windows o liberado sai de os.path.join (`painel\\dados`) e o caminho pode vir com `/`."""
        import ntpath
        import types
        real = travas.os
        travas.os = types.SimpleNamespace(name="nt", path=ntpath, sep="\\")
        try:
            g = gancho(settings(fixture()))
            self.assertIn(PACOTE + "\\dados", g["lib"])
            for livre in (DADOS + "/trabalhos/abc/saida.png", (DADOS + "/trabalhos/abc/saida.png").replace("/", "\\"),
                          PACOTE + "\\DADOS/trabalhos/abc/saida.png"):
                self.assertIsNone(travas.decidir(g, "Write", {"file_path": livre}), livre)
            for alvo in (DADOS + "/estudio-dono.json", DADOS + "\\aprovados\\x\\m.json", PACOTE + "/acoes/x.json",
                         PACOTE + "\\dadosx\\y.json", WS + "/.claude/settings.json"):
                self.assertEqual(travas.decidir(g, "Write", {"file_path": alvo})[0], "deny", alvo)
        finally:
            travas.os = real


class TesteHyperframes(unittest.TestCase):
    """O QA confia nos relatórios em `<fonte>/.hyperframes/`: com sandbox, Write/Edit não grava lá; o Bash grava."""
    TRAB = DADOS + "/trabalhos/abc"

    def test_ferramenta_de_arquivo_negada_com_sandbox(self):
        g = gancho(settings(fixture()))
        alvos = (self.TRAB + "/q1/.hyperframes/check.json", ".hyperframes/lint.json", "q1/.HyperFrames/x.json",
                 self.TRAB + "\\q1\\.hyperframes\\x.json", self.TRAB + "/q1/.hyperframes",
                 self.TRAB + "/q1/x/../.hyperframes/y.json", self.TRAB + "/q1/.hyperframes./y.json")
        for ferr in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            for alvo in alvos:
                chave = "notebook_path" if ferr == "NotebookEdit" else "file_path"
                self.assertEqual(travas.decidir(g, ferr, {chave: alvo}, self.TRAB), ("deny", travas.MOTIVO_HF),
                                 (ferr, alvo))
        for livre in (self.TRAB + "/q1/.hyperframes_history/x", self.TRAB + "/q1/x.hyperframes/y",
                      self.TRAB + "/q1/.hyperframes/../saida.png"):
            self.assertIsNone(travas.decidir(g, "Write", {"file_path": livre}, self.TRAB), livre)

    def test_bash_e_leitura_seguem(self):
        g = gancho(settings(catalogo.validar_acao(dict(SIMPLES, sandbox=True)), pasta=None))
        self.assertIsNone(travas.decidir(g, "Bash", {"command": "echo {} > .hyperframes/check.json"}))
        self.assertIsNone(travas.decidir(g, "Read", {"file_path": ".hyperframes/check.json"}))

    def test_sem_sandbox_nada_muda(self):
        g = gancho(settings(catalogo.validar_acao(SIMPLES), pasta=None))
        self.assertIsNone(travas.decidir(g, "Write", {"file_path": "/w/.hyperframes/check.json"}))

    @unittest.skipIf(os.name == "nt", "link simbólico pede privilégio no Windows")
    def test_link_para_dentro_de_hyperframes(self):
        import tempfile
        g = gancho(settings(fixture()))
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, ".hyperframes"))
            os.symlink(os.path.join(tmp, ".hyperframes"), os.path.join(tmp, "atalho"))
            for alvo in ("atalho/check.json", os.path.join(tmp, "atalho", "check.json")):
                self.assertEqual(travas.decidir(g, "Write", {"file_path": alvo}, tmp)[0], "deny", alvo)
            self.assertIsNone(travas.decidir(g, "Write", {"file_path": "outro/check.json"}, tmp))


class TesteLancadorSandbox(test_chat.Base):
    def setUp(self):
        test_chat.Base.setUp(self)
        with open(FIXTURE, encoding="utf-8") as f:
            self.gravar_acoes(json.load(f)["acoes"])

    def lanc(self, **extra):  # a fixture tem rede_local, então so_com: o projeto liga a chave
        return test_chat.Base.lanc(self, bruto={"estudio": {"video_rede_local": True}}, **extra)

    def test_dispara_com_cwd_na_pasta_e_grava(self):
        lc = self.lanc()
        ex = lc.iniciar("estudio.fixture", {"pedido": "grave oi.txt"})
        cmd, cwd = next(c for c in self.cli.chamadas if c[0][1:2] == ["--bg"])
        reg = lc.achar(ex["id"])
        pasta = os.path.join(os.path.realpath(self.cfg_dados()), "trabalhos", reg["trabalho"])
        self.assertTrue(os.path.isdir(pasta))
        self.assertEqual((cwd, reg["cwd"], reg["sandbox"]), (pasta, pasta, True))
        self.assertEqual(cmd[-1], "Pasta de trabalho: %s. grave oi.txt" % pasta)
        conf = json.loads(cmd[cmd.index("--settings") + 1])
        self.assertTrue(conf["sandbox"]["enabled"])
        self.assertEqual(conf["permissions"]["allow"], ["Edit(%s/**)" % trabalho.caminho_de_regra(pasta)])

    def test_sessao_com_sandbox_nao_responde(self):
        lc = self.lanc()
        i = lc.iniciar("estudio.fixture", {"pedido": "oi"})["id"]
        lc.execucoes(forcar=True)
        for a in self.cli.agentes:
            a.update(state="done", status="idle")
        lc.esquecer_agentes()
        self.assertFalse(lc.execucao(i)["pode_responder"])

    def cfg_dados(self):
        return os.path.join(self.tmp, "dados")


if __name__ == "__main__":
    unittest.main()
