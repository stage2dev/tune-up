"""Módulos embutidos (embutidos.py): Estúdio e Vendas chegam desligados e ligam pela API (C8-C11)."""
import sys

sys.dont_write_bytecode = True

import copy  # noqa: E402
import json  # noqa: E402
import ntpath  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import catalogo  # noqa: E402
import config  # noqa: E402
import embutidos  # noqa: E402
import extensoes  # noqa: E402
import lancador  # noqa: E402
import modulos  # noqa: E402
import painel  # noqa: E402
import sandbox  # noqa: E402
import test_http  # noqa: E402 - módulo, não a classe: senão os testes dele rodam de novo aqui
import test_travas_brecha  # noqa: E402
import travas  # noqa: E402
from test_lancador import ACOES_TESTE, ESTADO, CLIFalso, cfg_teste  # noqa: E402
from test_travas import ACAO_CODIGO, ACAO_LEITURA, decisao  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ESTUDIO_JSON = os.path.join(RAIZ, "tune-up-studio", "painel", "acoes", "estudio.json")
AVISO_COMPAT = "agora faz parte do tune-up; pode tirar essa linha do painel.json"


def escrever(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


def por_id(lista):
    return {e["id"]: e for e in lista}


class TesteHTTPEmbutidos(unittest.TestCase):
    """C8 e C11 pelo servidor de verdade (mesmo arranjo de test_http)."""
    pedir, cab_post, post = test_http.TesteHTTP.pedir, test_http.TesteHTTP.cab_post, test_http.TesteHTTP.post

    @classmethod
    def setUpClass(cls):
        cls.tmp = t = tempfile.mkdtemp()
        escrever(os.path.join(t, "acoes", "t.json"), json.dumps(ACOES_TESTE))
        os.makedirs(os.path.join(t, "plans", "phases"))
        escrever(os.path.join(t, "web", "index.html"), "<!doctype html><title>x</title>")
        cls.cfg = cfg_teste(t, web_dir=os.path.join(t, "web"))
        lanc = lancador.Lancador(cls.cfg, lambda: ESTADO, rodar=CLIFalso(), plataforma="darwin")
        cls.app = painel.App(cls.cfg, os.path.join(t, "plans"), lancador=lanc, rodar_externos=False)
        cls.app.log = False
        cls.srv = painel.criar_servidor(cls.app, 0)
        cls.porta = cls.app.porta
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp)

    def setUp(self):
        arq = os.path.join(self.cfg["dados_dir"], embutidos.ARQUIVO)
        if os.path.exists(arq):
            os.remove(arq)
        modulos.esquecer()

    def get(self, caminho):
        st, _, dados = self.pedir("GET", caminho)
        return st, json.loads(dados)

    @mock.patch.object(embutidos.sys, "platform", "linux")  # no win32 o Estúdio fica indisponível (test_c11)
    def test_c8_chegam_desligados_e_ligam_pela_api(self):
        st, r = self.get("/api/embutidos")
        self.assertEqual(st, 200)
        lista = por_id(r["embutidos"])
        self.assertEqual(set(lista), {"estudio", "vendas"})
        for e in lista.values():
            self.assertIs(e["ligado"], False)
            self.assertIs(e["disponivel"], True)
            self.assertIsNone(e["motivo"])
            self.assertTrue(e["titulo"] and e["descricao"])
        self.assertIn("primeira versão testada só no macOS; precisa de Docker", lista["vendas"]["avisos"])
        self.assertNotIn("estudio", [m["id"] for m in self.get("/api/modulos")[1]["modulos"]])
        self.assertFalse([a for a in self.get("/api/acoes")[1]["acoes"] if a["id"].startswith("estudio.")])

        st, r = self.post("/api/embutidos/estudio", {"ligado": True})
        self.assertEqual(st, 200, r)
        self.assertIs(r["ok"], True)
        self.assertIs(por_id(r["embutidos"])["estudio"]["ligado"], True)
        with open(os.path.join(self.cfg["dados_dir"], embutidos.ARQUIVO), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"estudio": True})
        self.assertIn("estudio", [m["id"] for m in self.get("/api/modulos")[1]["modulos"]])
        ids = [a["id"] for a in self.get("/api/acoes")[1]["acoes"]]
        self.assertTrue({"estudio.post", "estudio.video", "estudio.anuncio"} <= set(ids), ids)

        st, r = self.post("/api/embutidos/estudio", {"ligado": False})
        self.assertEqual(st, 200, r)
        self.assertNotIn("estudio", [m["id"] for m in self.get("/api/modulos")[1]["modulos"]])
        self.assertFalse([a for a in self.get("/api/acoes")[1]["acoes"] if a["id"].startswith("estudio.")])

    def test_c8_post_recusado_como_as_outras_rotas(self):
        arq = os.path.join(self.cfg["dados_dir"], embutidos.ARQUIVO)
        for troca in ({"X-Painel-Token": None}, {"X-Painel-Token": "errado"}, {"Origin": None},
                      {"Origin": "http://evil.example"}):
            st, r = self.post("/api/embutidos/estudio", {"ligado": True}, **troca)
            self.assertEqual(st, 403, (troca, r))
            self.assertFalse(os.path.exists(arq), troca)
        self.assertEqual(self.post("/api/embutidos/nada", {"ligado": True})[0], 404)
        self.assertEqual(self.post("/api/embutidos/..%2Fx", {"ligado": True})[0], 404)
        for corpo in ({"ligado": "sim"}, {"ligado": 1}, {}, {"ligado": None}):
            st, r = self.post("/api/embutidos/vendas", corpo)
            self.assertEqual(st, 400, corpo)
            self.assertIsInstance(r["erro"], str)
        self.assertFalse(os.path.exists(arq))

    def test_c11_windows_estudio_indisponivel(self):
        with mock.patch.object(embutidos.sys, "platform", "win32"):
            lista = por_id(self.get("/api/embutidos")[1]["embutidos"])
            self.assertIs(lista["estudio"]["disponivel"], False)
            self.assertIn("não roda no Windows", lista["estudio"]["motivo"])
            self.assertIs(lista["vendas"]["disponivel"], True)
            st, r = self.post("/api/embutidos/estudio", {"ligado": True})
            self.assertEqual(st, 409, r)
            self.assertIn("WSL2", r["erro"])
            self.assertFalse(os.path.exists(os.path.join(self.cfg["dados_dir"], embutidos.ARQUIVO)))
            escrever(os.path.join(self.cfg["dados_dir"], embutidos.ARQUIVO), '{"estudio": true}')
            self.assertIs(por_id(self.get("/api/embutidos")[1]["embutidos"])["estudio"]["ligado"], False)
            self.assertEqual(embutidos.ligados(self.cfg), [])
            self.assertEqual(self.post("/api/embutidos/estudio", {"ligado": False})[0], 200)  # desligar pode


@mock.patch.object(embutidos.sys, "platform", "linux")  # no win32 o Estúdio não liga (409): test_c11 cobre
class TesteEmbutidosProjeto(unittest.TestCase):
    """Projeto de verdade em pasta temporária (config.carregar), com HOME falso."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)

    def cfg(self, **chaves):
        escrever(os.path.join(self.tmp, ".tune-up", "painel.json"), json.dumps(dict({"nome": "E"}, **chaves)))
        return config.carregar(self.tmp, home=self.tmp)

    def plugin_velho(self, nome):
        """installed_plugins.json com o plugin separado de antes; o código dele quebra se for importado."""
        inst = os.path.join(self.tmp, "cache", nome, "9")
        for mid in ("estudio", "vendas"):
            escrever(os.path.join(inst, "painel", "modulos", mid, "modulo.py"), "raise RuntimeError('velho')\n")
        escrever(os.path.join(inst, "painel", "acoes", "velho.json"), json.dumps(
            {"acoes": [{"id": "estudio.velho", "area": "dev", "risco": "leitura", "prompt": "/velho"}]}))
        escrever(os.path.join(self.tmp, ".claude", "plugins", "installed_plugins.json"), json.dumps({
            "version": 2, "plugins": {nome + "@tune-up": [{"installPath": inst, "lastUpdated": "2026-01-01"}]}}))

    def test_c8_modulos_reais_importam_e_montam(self):
        cfg = self.cfg()
        for mid in ("estudio", "vendas"):
            self.assertEqual(embutidos.mudar(cfg, mid, {"ligado": True})[0], 200)
            caminho = modulos.caminho_do_modulo(cfg, mid)
            self.assertEqual(caminho, os.path.realpath(embutidos.caminho(mid)))
            self.assertTrue(caminho.startswith(RAIZ + os.sep))
            self.assertTrue(callable(modulos.carregar(cfg, mid).montar))
            codigo, corpo = modulos.montar(cfg, mid, usar_cache=False)
            self.assertEqual(codigo, 200, corpo)  # monta num projeto vazio (tela com alertas de "prepare")
        lista = modulos.listar(cfg)
        self.assertEqual([m["id"] for m in lista["modulos"]], ["estudio", "vendas"], lista["avisos"])

    def test_c8_acao_do_pacote_nao_tira_as_travas_do_embutido(self):
        with open(ESTUDIO_JSON, encoding="utf-8") as f:
            real = [a for a in json.load(f)["acoes"] if a["id"] == "estudio.post"][0]
        sem_sandbox, sem_requer, com_travas = copy.deepcopy(real), copy.deepcopy(real), copy.deepcopy(real)
        del sem_sandbox["sandbox"]
        del sem_requer["requer"]
        com_travas["titulo"] = "Post do pacote"
        substitui = dict(ACOES_TESTE["acoes"][0], substitui=True, titulo="Trocada pelo pacote")
        nucleo = os.path.join(self.tmp, "nucleo")
        escrever(os.path.join(nucleo, "t.json"), json.dumps(ACOES_TESTE))
        for nome, ruim in (("sem_sandbox", sem_sandbox), ("sem_requer", sem_requer)):
            pac = os.path.join(self.tmp, "pacote-" + nome)
            escrever(os.path.join(pac, "p.json"), json.dumps({"acoes": [ruim, substitui]}))
            cfg = cfg_teste(self.tmp, acoes_dir=nucleo, acoes_pacote_dir=pac)
            embutidos.mudar(cfg, "estudio", {"ligado": True})
            acoes, avisos = catalogo.catalogo_do_projeto(cfg)
            post = [a for a in acoes if a["id"] == "estudio.post"]
            self.assertEqual(len(post), 1)
            self.assertTrue(post[0]["sandbox"], nome)
            self.assertEqual(post[0]["_requer"], ["estudio.marca"], nome)
            # sem sandbox a validação já recusa (requer pede sandbox); sem requer, o catálogo recusa a do pacote
            self.assertTrue([x for x in avisos if "estudio.post" in x and "p.json" in x], avisos)
            self.assertEqual([a["titulo"] for a in acoes if a["id"] == substitui["id"]], ["Trocada pelo pacote"])
        pac = os.path.join(self.tmp, "pacote-ok")  # mantém as travas: vale a regra de hoje das ações de plugin
        escrever(os.path.join(pac, "p.json"), json.dumps({"acoes": [com_travas]}))
        acoes, _ = catalogo.catalogo_do_projeto(cfg_teste(self.tmp, acoes_dir=nucleo, acoes_pacote_dir=pac))
        self.assertEqual([a["titulo"] for a in acoes if a["id"] == "estudio.post"], ["Post do pacote"])

    def test_c10_linha_antiga_carrega_do_nucleo(self):
        for plugin, mid in (("tune-up-studio", "estudio"), ("tune-up-vendas", "vendas")):
            self.plugin_velho(plugin)
            cfg = self.cfg(modulos_de_plugins=["%s@qualquer:%s" % (plugin, mid)])
            self.assertEqual(modulos.caminho_do_modulo(cfg, mid), embutidos.caminho(mid))
            self.assertNotIn("cache", modulos.caminho_do_modulo(cfg, mid))
            self.assertEqual(modulos.listar(cfg)["modulos"][0]["id"], mid)
            self.assertEqual(embutidos.ligados(cfg), [mid])
            item = por_id(embutidos.listar(cfg)[1]["embutidos"])[mid]
            self.assertIs(item["ligado"], True)
            self.assertTrue([a for a in item["avisos"] if AVISO_COMPAT in a], item["avisos"])
            # Desligar: o false no arquivo vence a linha antiga
            self.assertEqual(embutidos.mudar(cfg, mid, {"ligado": False})[0], 200)
            self.assertEqual(embutidos.ligados(cfg), [])
            self.assertEqual(modulos.listar(cfg)["modulos"], [])
            os.remove(os.path.join(cfg["dados_dir"], embutidos.ARQUIVO))

    def test_c10_acoes_do_plugin_velho_ignoradas(self):
        self.plugin_velho("tune-up-studio")
        cfg = self.cfg(acoes_de_plugins=["tune-up-studio@tune-up"],
                       modulos_de_plugins=["tune-up-studio@tune-up:estudio"])
        pastas, avisos = extensoes.pastas_de_acoes(cfg)
        self.assertEqual(pastas, [])
        self.assertTrue([a for a in avisos if "ligue o Estúdio na tela Módulos; depois pode tirar essa linha "
                         "do painel.json" in a], avisos)
        ids =[a["id"] for a in catalogo.catalogo_do_projeto(cfg)[0]]
        self.assertIn("estudio.post", ids)
        self.assertNotIn("estudio.velho", ids)
        self.assertFalse(os.path.exists(os.path.join(cfg["dados_dir"], extensoes.ARQUIVO)))  # nem conferiu

    def test_c10_regras_de_negar(self):
        cfg = self.cfg()
        self.assertEqual(modulos.regras_de_negar(cfg), [])  # nunca ligou: sem regra (8080 é porta comum)
        embutidos.mudar(cfg, "vendas", {"ligado": True})
        self.assertIn("Bash(*localhost:8080*)", modulos.regras_de_negar(cfg))
        embutidos.mudar(cfg, "vendas", {"ligado": False})
        self.assertIn("Bash(*tune-up-vendas*)", modulos.regras_de_negar(cfg))
        self.assertIn("Bash(*tune-up-vendas*)", modulos.negar_dos_modulos(cfg)[0])
        cfg2 = config.carregar(self.tmp, home=self.tmp)
        cfg2["dados_dir"] = os.path.join(self.tmp, "outros-dados")
        cfg2["bruto"] = {"modulos_de_plugins": ["tune-up-vendas@x:vendas"]}
        self.assertEqual(modulos.regras_de_negar(cfg2), list(embutidos.NEGAR_VENDAS))  # só a linha antiga

    def test_caminho_no_windows(self):
        """No Windows o realpath troca / por \\: sem normalizar, caminho() era None e o Vendas dava 404."""
        with mock.patch.object(embutidos, "os", types.SimpleNamespace(path=ntpath)), \
                mock.patch.object(config, "PAINEL", "C:\\t\\painel"), mock.patch("ntpath.isdir", return_value=True):
            self.assertEqual(embutidos._pasta("vendas/painel/modulos/vendas"), "C:\\t\\vendas\\painel\\modulos\\vendas")

    def test_lista_fixa_de_negar_igual_a_do_modulo_real(self):
        mod = modulos._importar(embutidos.caminho("vendas"), "vendas")
        self.assertEqual(list(embutidos.NEGAR_VENDAS), mod.INFO["negar"])
        self.assertNotIn("negar", modulos._importar(embutidos.caminho("estudio"), "estudio").INFO)

    def test_arquivo_ilegivel_desliga_tudo_e_mantem_as_regras(self):
        cfg = self.cfg(modulos_de_plugins=["tune-up-studio@x:estudio"])
        arq = os.path.join(cfg["dados_dir"], embutidos.ARQUIVO)
        for ruim in ("{nao json", '{"estudio": "sim"}', "[]", "x" * 5000):
            escrever(arq, ruim)
            lista = embutidos.listar(cfg)[1]["embutidos"]
            self.assertEqual([e["ligado"] for e in lista], [False, False], ruim)
            self.assertTrue(all(any("não abre" in a for a in e["avisos"]) for e in lista))
            self.assertEqual(embutidos.ligados(cfg), [])
            self.assertEqual(modulos.regras_de_negar(cfg), list(embutidos.NEGAR_VENDAS))
        self.assertEqual(embutidos.mudar(cfg, "estudio", {"ligado": True})[0], 200)  # regrava: o resto false
        with open(arq, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"estudio": True, "vendas": False})
        os.remove(arq)
        if os.name != "nt":  # atalho pede privilégio no Windows (como em test_embutidos_trava)
            alvo = os.path.join(self.tmp, "alvo.json")
            escrever(alvo, '{"estudio": true, "vendas": true}')
            os.symlink(alvo, arq)
            self.assertEqual(embutidos.ligados(cfg), [])  # atalho não é seguido

    def test_gravacao_que_falha_vira_erro(self):
        cfg = self.cfg()
        escrever(os.path.join(self.tmp, "arquivo"), "x")
        cfg["dados_dir"] = os.path.join(self.tmp, "arquivo")  # dados_dir é um arquivo: não grava
        chamou = []
        st, r = embutidos.mudar(cfg, "estudio", {"ligado": True}, depois=lambda: chamou.append(1))
        self.assertEqual(st, 500)
        self.assertIn("nada mudou", r["erro"])
        self.assertEqual(chamou, [])
        if os.name == "nt":  # atalho pede privilégio no Windows (como em test_embutidos_trava)
            return
        cfg = self.cfg()
        os.makedirs(cfg["dados_dir"], exist_ok=True)
        os.symlink(os.path.join(self.tmp, "fora.json"), os.path.join(cfg["dados_dir"], embutidos.ARQUIVO + ".gravando"))
        self.assertEqual(embutidos.mudar(cfg, "estudio", {"ligado": True})[0], 500)  # temporário plantado
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "fora.json")))

    def test_modulo_do_projeto_com_o_mesmo_id_vence(self):
        escrever(os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos", "estudio", "modulo.py"),
                 "INFO = {'titulo': 'Meu'}\ndef montar(ctx):\n    return {'blocos': []}\n")
        cfg = self.cfg(modulos=["estudio"])
        embutidos.mudar(cfg, "estudio", {"ligado": True})
        self.assertIn(os.path.join("painel-projeto", "modulos"), modulos.caminho_do_modulo(cfg, "estudio"))
        self.assertEqual([m["id"] for m in modulos.listar(cfg)["modulos"]], ["estudio"])
        item = por_id(embutidos.listar(cfg)[1]["embutidos"])["estudio"]
        self.assertTrue([a for a in item["avisos"] if "módulo próprio" in a])


class TesteSessaoNaoGravaOEstado(unittest.TestCase):
    """C9: o gancho e o sandbox protegem embutidos-ligados.json (e o temporário) como o que é do dono."""

    def test_gancho_recusa_escrita(self):
        for acao, esperado in ((ACAO_LEITURA, "deny"), (ACAO_CODIGO, "ask")):
            c = test_travas_brecha.TesteCaminhoRelativo()._conf(acao)
            for cmd in ("cd /p/.tune-up/pacote/dados && echo '{\"estudio\": true}' > embutidos-ligados.json",
                        "cd /p/.tune-up/pacote/dados && ln -s /tmp/x embutidos-ligados.json.gravando",
                        "cd /p/.tune-up/pacote/dados; echo x > 'Embutidos-Ligados.JSON'"):
                self.assertEqual(travas.decidir(c, "Bash", {"command": cmd}, "/tmp/w")[0], esperado, cmd)
            for alvo in ("/tmp/w/embutidos-ligados.json", "/tmp/w/embutidos-ligados.json.gravando"):
                self.assertEqual(decisao(c, "Write", {"file_path": alvo}), esperado, alvo)
            self.assertIsNone(travas.decidir(c, "Bash", {"command": "cat embutidos-ligados.json"}, "/tmp/w"))

    def test_sandbox_nega_escrita(self):
        self.assertIn(embutidos.ARQUIVO, sandbox.DONO)
        self.assertIn(embutidos.ARQUIVO + ".gravando", sandbox.DONO)


if __name__ == "__main__":
    unittest.main()
