"""Testes dos módulos do pacote e do painel subindo num projeto vazio. Nada chama o claude."""
import sys

sys.dont_write_bytecode = True

import http.client  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402

import config  # noqa: E402
import modulos  # noqa: E402
import painel  # noqa: E402

BOM = '''
INFO = {"id": "vendas", "titulo": "Vendas", "icone": "grafico"}
import irmao

def montar(ctx):
    return {"alertas": [{"nivel": "atencao", "texto": "caiu"}, {"nivel": "x", "texto": 1}],
            "abas": [{"id": "geral", "titulo": "Geral", "blocos": [
                {"tipo": "kpis", "itens": [{"rotulo": "Hoje", "valor": irmao.VALOR}]},
                {"tipo": "inventado", "x": 1}, {"sem": "tipo"}]}, "nada"],
            "avisos": ["ok", 3], "extra": ctx["config"].get("nome"),
            "raiz": ctx["raiz"], "dados": ctx["dados"], "hoje": ctx["hoje"].isoformat()}
'''
QUEBRADO = 'INFO = {"titulo": "Quebrado"}\ndef montar(ctx):\n    raise RuntimeError("explodiu")\n'
LENTO = 'import time\ndef montar(ctx):\n    time.sleep(2)\n    return {}\n'


def escrever(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


class TesteModulos(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        pac = os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos")
        escrever(os.path.join(pac, "vendas", "modulo.py"), BOM)
        escrever(os.path.join(pac, "vendas", "irmao.py"), "VALOR = 42\n")
        escrever(os.path.join(pac, "quebrado", "modulo.py"), QUEBRADO)
        escrever(os.path.join(pac, "lento", "modulo.py"), LENTO)
        escrever(os.path.join(self.tmp, "fora", "modulo.py"), "def montar(ctx):\n    return {}\n")
        try:  # Windows sem permissão de symlink: sem o atalho, o módulo "fuga" também não existe
            os.symlink(os.path.join(self.tmp, "fora"), os.path.join(pac, "fuga"))
        except (OSError, NotImplementedError):
            pass
        escrever(os.path.join(pac, "desligado", "modulo.py"), "def montar(ctx):\n    return {}\n")
        escrever(os.path.join(self.tmp, ".tune-up", "painel.json"), json.dumps(
            {"nome": "Loja", "modulos": ["vendas", "quebrado", "fuga", "lento", "sumido"]}))
        self.cfg = config.carregar(self.tmp, home=self.tmp)
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)
        for t in list(modulos._rodando.values()):  # um teste anterior pode ter deixado o lento rodando
            t.join(5)
        modulos._rodando.clear()

    def test_montar_confere_a_forma(self):
        cod, d = modulos.montar(self.cfg, "vendas", usar_cache=False)
        self.assertEqual(cod, 200, d)
        self.assertEqual((d["id"], d["titulo"]), ("vendas", "Vendas"))
        self.assertEqual(d["alertas"], [{"nivel": "atencao", "texto": "caiu"}])
        self.assertEqual(len(d["abas"]), 1)
        self.assertEqual([b["tipo"] for b in d["abas"][0]["blocos"]], ["kpis", "inventado"])
        self.assertEqual(d["abas"][0]["blocos"][0]["itens"][0]["valor"], 42)  # importou o irmão
        self.assertNotIn("extra", d)
        self.assertEqual(d["avisos"][0], "ok")
        self.assertTrue(any("alerta" in a for a in d["avisos"]))
        self.assertTrue(d["gerado_em"])

    def test_contexto(self):
        ctx = modulos.contexto(self.cfg)
        self.assertEqual(ctx["raiz"], self.tmp)
        self.assertEqual(ctx["dados"], os.path.join(self.tmp, ".tune-up", "painel-projeto", "dados"))
        self.assertEqual(ctx["config"]["nome"], "Loja")

    def test_quebrado_atalho_desligado_e_lento(self):
        cod, d = modulos.montar(self.cfg, "quebrado", usar_cache=False)
        self.assertEqual((cod, set(d)), (500, {"erro", "avisos"}))
        self.assertIn("explodiu", d["avisos"][0])
        self.assertEqual(modulos.montar(self.cfg, "fuga", usar_cache=False)[0], 404)
        self.assertEqual(modulos.montar(self.cfg, "desligado", usar_cache=False)[0], 404)
        self.assertEqual(modulos.montar(self.cfg, "../x", usar_cache=False)[0], 404)
        self.assertEqual(modulos.montar(self.cfg, "sumido", usar_cache=False)[0], 404)
        cod, d = modulos.montar(self.cfg, "lento", usar_cache=False, tempo=0.2)
        self.assertEqual(cod, 500)
        self.assertIn("demorou", d["erro"])
        self.assertEqual(modulos.montar(self.cfg, "lento", usar_cache=False, tempo=0.2)[0], 503)

    def test_listar(self):
        d = modulos.listar(self.cfg, tempo=0.2)
        por_id = {m["id"]: m for m in d["modulos"]}
        self.assertEqual(por_id["vendas"], {"id": "vendas", "titulo": "Vendas", "icone": "grafico", "alertas": 1})
        self.assertEqual(por_id["quebrado"]["alertas"], 0)
        self.assertNotIn("fuga", por_id)
        self.assertNotIn("sumido", por_id)
        self.assertTrue(d["avisos"])


IRMAOS = '''
import config
import util

def montar(ctx):
    return {"abas": [{"id": "a", "blocos": [{"tipo": "texto", "texto": util.NOME + "|" + config.ORIGEM}]}]}
'''


class TesteModulosIsolados(unittest.TestCase):
    """Dois módulos com util.py e config.py próprios: cada um vê os seus, o núcleo fica intacto."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        pac = os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos")
        for mid in ("vendas", "suporte"):
            escrever(os.path.join(pac, mid, "modulo.py"), IRMAOS)
            escrever(os.path.join(pac, mid, "util.py"), "NOME = %r\n" % mid)
            escrever(os.path.join(pac, mid, "config.py"), "ORIGEM = %r\n" % ("config de " + mid))
        escrever(os.path.join(self.tmp, ".tune-up", "painel.json"), json.dumps({"modulos": ["vendas", "suporte"]}))
        self.cfg = config.carregar(self.tmp, home=self.tmp)
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)

    def test_cada_modulo_ve_os_proprios_irmaos(self):
        caminho_antes, config_antes = list(sys.path), sys.modules["config"]
        for mid in ("vendas", "suporte", "vendas"):
            cod, d = modulos.montar(self.cfg, mid, usar_cache=False)
            self.assertEqual(cod, 200, d)
            self.assertEqual(d["abas"][0]["blocos"][0]["texto"], "%s|config de %s" % (mid, mid))
        self.assertIs(sys.modules["config"], config_antes)  # o config do núcleo não foi trocado
        self.assertIs(config.carregar, config_antes.carregar)
        self.assertNotIn("util", sys.modules)
        self.assertEqual(sys.path, caminho_antes)


LOJA = '''
import time
INFO = {"titulo": "Loja", "acoes": ["salvar", "quebrar", "demorar", 7],
        "negar": ["mcp__fora__apagar", "Bash(rm -rf *)"]}
MONTAR = [0]
ESPERA = [0.0]

def montar(ctx):
    MONTAR[0] += 1
    time.sleep(ESPERA[0])
    return {"abas": [{"id": "a", "blocos": [{"tipo": "texto", "texto": str(MONTAR[0])}]}]}

def agir(ctx, acao, dados):
    if acao == "quebrar":
        raise RuntimeError("vazou " + str(dados))
    if acao == "demorar":
        time.sleep(1.0)
    return {"acao": acao, "recebi": dados, "tem_ctx": bool(ctx["pacote"])}
'''


def pacote_loja(tmp):
    """Pacote com loja (acoes + agir + negar), so_tela (sem agir) e negar_ruim. Devolve a cfg."""
    pac = os.path.join(tmp, ".tune-up", "painel-projeto", "modulos")
    escrever(os.path.join(pac, "loja", "modulo.py"), LOJA)
    escrever(os.path.join(pac, "so_tela", "modulo.py"), "def montar(ctx):\n    return {}\n")
    escrever(os.path.join(pac, "negar_ruim", "modulo.py"),
             'INFO = {"negar": "Bash(*)"}\ndef montar(ctx):\n    return {}\n')
    escrever(os.path.join(pac, "desligado", "modulo.py"), LOJA)
    escrever(os.path.join(tmp, ".tune-up", "painel.json"),
             json.dumps({"nome": "Loja", "modulos": ["loja", "so_tela", "negar_ruim"]}))
    return config.carregar(tmp, home=tmp)


def esperar_threads():
    for t in list(modulos._agindo.values()) + list(modulos._rodando.values()):
        t.join(5)
    modulos._agindo.clear()
    modulos._rodando.clear()


class TesteAcoesDeModulo(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cfg = pacote_loja(self.tmp)
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)
        esperar_threads()
        self.addCleanup(esperar_threads)
        self.mod = modulos.carregar(self.cfg, "loja")

    def test_agir_ok_e_dados_intactos(self):
        dados = {"codigo": "123456", "lista": [1, {"a": None}]}
        cod, d = modulos.agir(self.cfg, "loja", "salvar", dados)
        self.assertEqual((cod, d), (200, {"ok": True, "resultado": {"acao": "salvar", "recebi": dados,
                                                                     "tem_ctx": True}}))

    def test_400_404(self):
        self.assertEqual(modulos.agir(self.cfg, "loja", "apagar", {})[0], 400)  # fora de INFO["acoes"]
        self.assertEqual(modulos.agir(self.cfg, "loja", 7, {})[0], 400)  # 7 está na lista, mas não é texto
        self.assertEqual(modulos.agir(self.cfg, "loja", None, {})[0], 400)
        self.assertEqual(modulos.agir(self.cfg, "loja", "salvar", None)[0], 400)
        self.assertEqual(modulos.agir(self.cfg, "loja", "salvar", ["x"])[0], 400)
        self.assertEqual(modulos.agir(self.cfg, "sumido", "salvar", {})[0], 404)
        self.assertEqual(modulos.agir(self.cfg, "desligado", "salvar", {})[0], 404)  # existe, não habilitado
        self.assertEqual(modulos.agir(self.cfg, "../loja", "salvar", {})[0], 404)
        cod, d = modulos.agir(self.cfg, "so_tela", "salvar", {})
        self.assertEqual((cod, d["erro"]), (404, "Esta tela não tem ações."))

    def test_quebra_nao_vaza_texto(self):
        cod, d = modulos.agir(self.cfg, "loja", "quebrar", {"senha": "segredo-xyz"})
        self.assertEqual((cod, set(d)), (500, {"erro", "avisos"}))
        self.assertNotIn("segredo-xyz", json.dumps(d))
        self.assertNotIn("vazou", json.dumps(d))
        self.assertIn("RuntimeError", d["avisos"][0])

    def test_tempo_limite_409_e_trava_separada_de_montar(self):
        cod, d = modulos.agir(self.cfg, "loja", "demorar", {}, tempo=0.2)
        self.assertEqual(cod, 504, d)
        cod, d = modulos.agir(self.cfg, "loja", "salvar", {})  # a anterior ainda roda
        self.assertEqual(cod, 409, d)
        self.assertEqual(modulos.montar(self.cfg, "loja", usar_cache=False)[0], 200)  # montar não espera ação
        esperar_threads()
        self.mod.ESPERA[0] = 1.0
        t = threading.Thread(target=modulos.montar, args=(self.cfg, "loja"), kwargs={"usar_cache": False})
        t.start()
        self.addCleanup(t.join, 5)
        for _ in range(100):
            if "loja" in modulos._rodando and modulos._rodando["loja"].is_alive():
                break
            threading.Event().wait(0.01)
        self.assertEqual(modulos.montar(self.cfg, "loja", usar_cache=False)[0], 503)  # montar rodando
        self.assertEqual(modulos.agir(self.cfg, "loja", "salvar", {})[0], 200)  # ação não leva 503

    def test_cache_fresco_e_acao_invalida_cache(self):
        self.assertEqual(modulos.montar(self.cfg, "loja")[0], 200)
        modulos.montar(self.cfg, "loja")
        self.assertEqual(self.mod.MONTAR[0], 1)  # cache de 30 s
        modulos.montar(self.cfg, "loja", usar_cache=False)
        self.assertEqual(self.mod.MONTAR[0], 2)
        modulos.agir(self.cfg, "loja", "salvar", {})
        modulos.montar(self.cfg, "loja")
        self.assertEqual(self.mod.MONTAR[0], 3)  # a ação esqueceu o cache da tela
        modulos.montar(self.cfg, "loja", pulso=(("a", "rodando"),))
        modulos.montar(self.cfg, "loja", pulso=(("a", "rodando"),))
        self.assertEqual(self.mod.MONTAR[0], 4)
        modulos.montar(self.cfg, "loja", pulso=(("a", "terminou"),))
        self.assertEqual(self.mod.MONTAR[0], 5)  # a sessão terminou: a fila não espera os 30 s

    def test_negar_dos_modulos_chega_na_sessao(self):
        import lancador
        from test_lancador import ACOES_TESTE, ESTADO, CLIFalso
        regras, avisos = modulos.negar_dos_modulos(self.cfg)
        self.assertEqual(regras, ["mcp__fora__apagar", "Bash(rm -rf *)"])
        self.assertTrue(any("negar_ruim" in a for a in avisos), avisos)
        self.assertEqual(self.mod.MONTAR[0], 0)  # ler INFO não roda montar
        escrever(os.path.join(self.tmp, "acoes", "t.json"), json.dumps(ACOES_TESTE))
        self.cfg.update(acoes_dir=os.path.join(self.tmp, "acoes"), claude_bin="claude", max_execucoes=3)
        cli = CLIFalso()
        lanc = lancador.Lancador(self.cfg, lambda: ESTADO, rodar=cli, plataforma="darwin")
        self.assertTrue(any("negar_ruim" in a for a in lanc.acoes()[1]))
        with self.assertRaises(lancador.ErroAcao) as erro:  # negar ruim num módulo ligado: não dispara
            lanc.iniciar("t.leve", {})
        self.assertEqual(erro.exception.codigo, 409)
        self.assertIn("A tela negar_ruim não carregou", erro.exception.mensagem)
        self.assertEqual([c for c, _ in cli.chamadas if c[1:2] == ["--bg"]], [])
        self.cfg["modulos"] = ["loja", "so_tela"]
        for acao, params in (("t.leve", {}), ("t.parte", {"fase": "187", "parte": "C"})):
            lanc.iniciar(acao, params)
            cmd = [c for c, _ in cli.chamadas if c[1:2] == ["--bg"]][-1]
            deny = json.loads(cmd[cmd.index("--settings") + 1])["permissions"]["deny"]
            self.assertIn("mcp__fora__apagar", deny, acao)
            self.assertIn("Bash(rm -rf *)", deny, acao)
            if acao == "t.leve":
                self.assertIn("Edit(**/.claude/settings*.json)", deny)  # as regras da ação continuam
        self.assertEqual(self.mod.MONTAR[0], 0)


class TesteProjetoVazio(unittest.TestCase):
    """O painel sobe numa pasta sem painel.json, sem pacote e sem .planning: tudo 200 com avisos."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = os.path.realpath(tempfile.mkdtemp())
        cfg = config.carregar(cls.tmp, home=cls.tmp)
        cfg["claude_bin"] = os.path.join(cls.tmp, "nao-existe-claude")
        cfg["claude_mem_db"] = os.path.join(cls.tmp, "nao-existe.db")
        cfg["projects_dir"] = os.path.join(cls.tmp, "projects")
        cls.cfg = cfg
        cls.app = painel.App(cfg, rodar_externos=False)
        cls.app.log = False
        cls.srv = painel.criar_servidor(cls.app, 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp)

    def pedir(self, caminho):
        c = http.client.HTTPConnection("127.0.0.1", self.app.porta, timeout=20)
        try:
            c.request("GET", caminho, headers={"Sec-Fetch-Site": "same-origin"})
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"null")
        finally:
            c.close()

    def test_config_vazia(self):
        self.assertFalse(self.cfg["pacote_ok"])
        self.assertEqual((self.cfg["modulos"], self.cfg["areas_acompanhamento"]), ([], []))
        self.assertTrue(any("painel.json" in a for a in self.cfg["avisos"]))
        self.assertTrue(any("tune-up" in a for a in self.cfg["avisos"]))

    def test_rotas_respondem(self):
        for rota in ("/api/sessao", "/api/estado", "/api/acoes", "/api/execucoes", "/api/acompanhamento",
                     "/api/modulos"):
            st, d = self.pedir(rota)
            self.assertEqual(st, 200, (rota, d))
        st, d = self.pedir("/api/estado")
        self.assertEqual(d["projeto"]["nome"], os.path.basename(self.tmp))
        self.assertTrue(d["avisos"])
        self.assertEqual(d["fases"], [])
        st, d = self.pedir("/api/acoes")
        self.assertTrue(d["acoes"])
        self.assertEqual({a["grupo"] for a in d["acoes"]}, {"dev", "chat"})
        st, d = self.pedir("/api/modulos")
        self.assertEqual(d, {"modulos": [], "avisos": []})
        st, d = self.pedir("/api/acompanhamento")
        self.assertEqual((d["listas"], d["areas"]), ([], [{"id": "geral", "titulo": "Geral"}]))
        self.assertTrue(d["avisos"])
        self.assertEqual(self.pedir("/api/modulos/qualquer")[0], 404)
        st, d = self.pedir("/api/agentes")
        try:
            import agentes  # noqa: F401  (frente que roda em paralelo)
            esperado = 200
        except ImportError:
            esperado = 503
        self.assertEqual(st, esperado, d)
        self.assertIn("avisos", d)


PLUG = ("def montar(ctx):\n    return {\"alertas\": [{\"nivel\": \"info\", \"texto\": \"ola\"}]}\n"
        "INFO = {\"titulo\": \"De plugin\", \"acoes\": [\"x\"], \"negar\": [\"Bash(rm:*)\"]}\n"
        "def agir(ctx, acao, dados):\n    return {\"feito\": acao}\n")


class TesteModulosDePlugin(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.inst = os.path.join(self.tmp, "cache", "meuplugin", "2")
        escrever(os.path.join(self.inst, "painel", "modulos", "vendas", "modulo.py"), PLUG)
        escrever(os.path.join(self.inst, "painel", "modulos", "outro", "modulo.py"), PLUG)
        escrever(os.path.join(self.tmp, "fora", "modulo.py"), PLUG)
        try:  # Windows sem permissão de symlink: sem o atalho, o módulo "fuga" também não existe
            os.symlink(os.path.join(self.tmp, "fora"), os.path.join(self.inst, "painel", "modulos", "fuga"))
        except (OSError, NotImplementedError):
            pass
        antigo = os.path.join(self.tmp, "cache", "meuplugin", "1")
        escrever(os.path.join(antigo, "painel", "modulos", "vendas", "modulo.py"), "raise RuntimeError('velho')\n")
        escrever(os.path.join(self.tmp, ".claude", "plugins", "installed_plugins.json"), json.dumps({
            "version": 2, "plugins": {"meuplugin@meumarket": [
                {"installPath": self.inst, "lastUpdated": "2026-02-01"},
                {"installPath": antigo, "lastUpdated": "2026-01-01"}]}}))
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)

    def cfg(self, **chaves):
        escrever(os.path.join(self.tmp, ".tune-up", "painel.json"), json.dumps(dict({"nome": "L"}, **chaves)))
        return config.carregar(self.tmp, home=self.tmp)

    def test_sem_a_chave_nada_aparece(self):
        for chaves in ({}, {"modulos_de_plugins": []}):
            cfg = self.cfg(**chaves)
            self.assertEqual(modulos.listar(cfg), {"modulos": [], "avisos": []})
            self.assertEqual(modulos.montar(cfg, "vendas")[0], 404)
            self.assertEqual(modulos.agir(cfg, "vendas", "x", {})[0], 404)
            self.assertNotIn("painel_modulo_vendas", sys.modules)

    def test_modulo_de_plugin_funciona_como_o_do_projeto(self):
        cfg = self.cfg(modulos_de_plugins=["meuplugin@meumarket:vendas"])
        r = modulos.listar(cfg)
        self.assertEqual(r["avisos"], [])
        self.assertEqual([(m["id"], m["titulo"], m["alertas"]) for m in r["modulos"]], [("vendas", "De plugin", 1)])
        codigo, corpo = modulos.montar(cfg, "vendas", usar_cache=False)
        self.assertEqual((codigo, corpo["id"]), (200, "vendas"))
        self.assertEqual(modulos.agir(cfg, "vendas", "x", {}), (200, {"ok": True, "resultado": {"feito": "x"}}))
        self.assertEqual(modulos.negar_dos_modulos(cfg), (["Bash(rm:*)"], []))
        self.assertEqual(modulos.montar(cfg, "outro")[0], 404)  # só o que foi nomeado

    def test_id_igual_ao_do_projeto_e_recusado(self):
        escrever(os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos", "vendas", "modulo.py"),
                 "INFO = {\"titulo\": \"Do projeto\"}\ndef montar(ctx):\n    return {}\n")
        cfg = self.cfg(modulos=["vendas"], modulos_de_plugins=["meuplugin@meumarket:vendas"])
        r = modulos.listar(cfg)
        self.assertEqual([m["titulo"] for m in r["modulos"]], ["Do projeto"])
        self.assertTrue(any("já é um módulo do projeto" in a for a in r["avisos"]))

    def test_recusas_com_aviso(self):
        cfg = self.cfg(modulos_de_plugins=[
            "naoexiste@meumarket:zzz", "meuplugin@meumarket:sumido", "meuplugin@meumarket:fuga",
            "ruim", 7, "meuplugin@meumarket:Vendas", "a b@meumarket:x", "meuplugin@meumarket:outro",
            "meuplugin@meumarket:vendas", "meuplugin@meumarket:vendas"])
        r = modulos.listar(cfg)
        self.assertEqual(sorted(m["id"] for m in r["modulos"]), ["outro", "vendas"])
        texto = " | ".join(r["avisos"])
        for trecho in ("naoexiste@meumarket não está instalado", "sumido", "fuga", "'ruim'", "'7'", "Vendas",
                       "a b@meumarket", "já veio de"):
            self.assertIn(trecho, texto)
        self.assertEqual(modulos.montar(cfg, "vendas", usar_cache=False)[0], 200)  # painel segue

    def test_duplicado_vale_o_primeiro(self):
        cfg = self.cfg(modulos_de_plugins=["meuplugin@meumarket:vendas", "outroplug@meumarket:vendas"])
        r = modulos.listar(cfg)
        self.assertEqual(len(r["modulos"]), 1)
        self.assertEqual(len([a for a in r["avisos"] if "já veio de" in a]), 1)

    def test_versao_mais_recente_do_registro(self):
        cfg = self.cfg(modulos_de_plugins=["meuplugin@meumarket:vendas"])
        self.assertEqual(config.achar_plugin("meuplugin@meumarket", cfg["home"]), self.inst)


if __name__ == "__main__":
    unittest.main()
