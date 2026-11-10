"""Testes HTTP: sobe o servidor numa porta livre com um CLI falso (nada chama o claude)."""
import sys

sys.dont_write_bytecode = True

import http.client  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import lancador  # noqa: E402
import painel  # noqa: E402
from test_lancador import ACOES_TESTE, ESTADO, CLIFalso, cfg_teste  # noqa: E402


class TesteHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        t = cls.tmp
        os.makedirs(os.path.join(t, "acoes"))
        with open(os.path.join(t, "acoes", "t.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(ACOES_TESTE, f)
        os.makedirs(os.path.join(t, "plans", "phases"))
        os.makedirs(os.path.join(t, "web", "assets"))
        with open(os.path.join(t, "web", "index.html"), "w", encoding="utf-8", newline="\n") as f:
            f.write("<!doctype html><title>novo</title>")
        with open(os.path.join(t, "web", "assets", "app-123.js"), "w", encoding="utf-8", newline="\n") as f:
            f.write("console.log(1)")
        with open(os.path.join(t, "segredo.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write("NAO PODE SAIR")
        try:  # Windows sem permissão de symlink: sem os atalhos, o teste ainda confere a travessia
            os.symlink(os.path.join(t, "segredo.txt"), os.path.join(t, "web", "assets", "fuga.js"))
            os.symlink(t, os.path.join(t, "web", "atalho"))
        except (OSError, NotImplementedError):
            pass
        cls.cli = CLIFalso()
        cls.cfg = cfg_teste(t, web_dir=os.path.join(t, "web"))
        lanc = lancador.Lancador(cls.cfg, lambda: ESTADO, rodar=cls.cli, plataforma="darwin")
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

    def pedir(self, metodo, caminho, corpo=None, cab=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        try:
            c.request(metodo, caminho, body=corpo, headers=cab or {})
            r = c.getresponse()
            dados = r.read()
            return r.status, dict((k.lower(), v) for k, v in r.getheaders()), dados
        finally:
            c.close()

    def cab_post(self, **troca):
        cab = {"Origin": "http://127.0.0.1:%d" % self.porta, "Content-Type": "application/json",
               "X-Painel-Token": self.app.token, "Sec-Fetch-Site": "same-origin"}
        cab.update(troca)
        return {k: v for k, v in cab.items() if v is not None}

    def post(self, caminho, dado, **troca):
        corpo = dado if isinstance(dado, bytes) else json.dumps(dado).encode()
        st, cab, dados = self.pedir("POST", caminho, corpo, self.cab_post(**troca))
        return st, json.loads(dados or b"null")

    # ---- GET
    def test_sessao_e_listas(self):
        st, cab, dados = self.pedir("GET", "/api/sessao", cab={"Sec-Fetch-Site": "same-origin"})
        d = json.loads(dados)
        self.assertEqual((st, d["token"], d["projeto"]["nome"]), (200, self.app.token, "Teste"))
        self.assertIn("script-src 'self'", cab["content-security-policy"])
        self.assertNotIn("unsafe-inline", cab["content-security-policy"].split("style-src")[0])
        st, _c, dados = self.pedir("GET", "/api/acoes")
        acoes = json.loads(dados)["acoes"]
        self.assertEqual(st, 200)
        self.assertTrue(all("_prompt" not in a and "prompt" not in a for a in acoes))
        st, _c, dados = self.pedir("GET", "/api/estado")
        d = json.loads(dados)
        self.assertEqual((st, d["fases"], d["projeto"]), (200, [], {"nome": "Teste"}))
        self.assertEqual(self.pedir("GET", "/api/nada")[0], 404)
        self.assertEqual(self.pedir("GET", "/api/agentes?sessao=../x")[0], 400)

    def test_host_e_origem_no_get(self):
        self.assertEqual(self.pedir("GET", "/api/sessao", cab={"Host": "evil.example"})[0], 421)
        self.assertEqual(self.pedir("GET", "/api/sessao", cab={"Sec-Fetch-Site": "cross-site"})[0], 403)
        nav = {"Sec-Fetch-Site": "cross-site", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        self.assertEqual(self.pedir("GET", "/", cab=nav)[0], 200)  # abrir por link ou favorito
        self.assertEqual(self.pedir("GET", "/api/sessao", cab=nav)[0], 403)  # a API continua fechada

    def test_sessao_so_para_o_proprio_painel(self):
        # sem Sec-Fetch-Site (curl, outro programa local) o token não sai
        st, _c, dados = self.pedir("GET", "/api/sessao")
        self.assertEqual(st, 403)
        self.assertNotIn(self.app.token.encode(), dados)
        for valor in ("cross-site", "same-site", "none"):
            st, _c, dados = self.pedir("GET", "/api/sessao", cab={"Sec-Fetch-Site": valor})
            self.assertEqual(st, 403, valor)
            self.assertNotIn(self.app.token.encode(), dados)
        st, _c, dados = self.pedir("GET", "/api/sessao", cab={"Sec-Fetch-Site": "same-origin"})
        self.assertEqual((st, json.loads(dados)["token"]), (200, self.app.token))
        # a página e as outras rotas GET seguem como antes
        self.assertEqual(self.pedir("GET", "/")[0], 200)
        nav = {"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"}
        self.assertEqual(self.pedir("GET", "/", cab=nav)[0], 200)
        for rota in ("/api/estado", "/api/acoes", "/api/execucoes"):
            self.assertEqual(self.pedir("GET", rota)[0], 200, rota)
            self.assertEqual(self.pedir("GET", rota, cab={"Sec-Fetch-Site": "none"})[0], 200, rota)
            self.assertEqual(self.pedir("GET", rota, cab={"Sec-Fetch-Site": "cross-site"})[0], 403, rota)

    # ---- defesas do POST
    def disparos(self):
        return len([c for c in self.cli.chamadas if c[0][1:2] == ["--bg"]])

    def test_post_recusado(self):
        ok = {"acao": "t.leve", "params": {}}
        antes = self.disparos()
        self.assertEqual(self.post("/api/execucoes", ok, **{"X-Painel-Token": "errado"})[0], 403)
        self.assertEqual(self.post("/api/execucoes", ok, **{"X-Painel-Token": None})[0], 403)
        self.assertEqual(self.post("/api/execucoes", ok, Origin="http://evil.example")[0], 403)
        self.assertEqual(self.post("/api/execucoes", ok, Origin=None)[0], 403)
        self.assertEqual(self.post("/api/execucoes", ok, Origin="http://127.0.0.1:1")[0], 403)
        self.assertEqual(self.post("/api/execucoes", ok, **{"Sec-Fetch-Site": "same-site"})[0], 403)
        self.assertEqual(self.post("/api/execucoes", ok, **{"Content-Type": "text/plain"})[0], 415)
        st, d = self.post("/api/execucoes", b'{"acao": "x", "lixo": "' + b"x" * 40000 + b'"}')
        self.assertEqual((st, set(d)), (413, {"erro"}))
        self.assertEqual(self.post("/api/execucoes", b"{nao e json")[0], 400)
        self.assertEqual(self.post("/api/execucoes", b"[1]")[0], 400)
        self.assertEqual(self.pedir("PUT", "/api/execucoes")[0], 405)
        self.assertEqual(self.disparos(), antes)  # nada recusado chegou ao claude

    def test_post_valido_409_eventos_parar_abrir(self):
        st, d = self.post("/api/execucoes", {"acao": "t.parte", "params": {"fase": "187", "parte": "C"}})
        self.assertEqual(st, 201)
        ex = d["execucao"]
        self.assertEqual((ex["estado"], ex["fase"], ex["parte"]), ("rodando", "187", "C"))
        st, d = self.post("/api/execucoes", {"acao": "t.parte", "params": {"fase": "187", "parte": "C"}})
        self.assertEqual((st, d["execucao_id"]), (409, ex["id"]))
        st, d = self.post("/api/execucoes", {"acao": "t.parte", "params": {"fase": "187", "parte": "A"}})
        self.assertEqual(st, 400)
        self.assertIn("fechada", d["erro"])
        st, _c, dados = self.pedir("GET", "/api/execucoes")
        self.assertIn(ex["id"], [e["id"] for e in json.loads(dados)["execucoes"]])
        # conversa sintética no lugar onde o Claude grava
        sid = ex["id"] + "-1111-2222-3333-444455556666"
        pasta = os.path.join(self.cfg["projects_dir"], "x")
        os.makedirs(pasta, exist_ok=True)
        with open(os.path.join(pasta, sid + ".jsonl"), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "/tune-up:part 187 C"}}) + "\n")
        st, _c, dados = self.pedir("GET", "/api/execucoes/%s/eventos?desde=0" % ex["id"])
        d = json.loads(dados)
        self.assertEqual((st, [e["texto"] for e in d["eventos"]], d["estado"]), (200, ["/tune-up:part 187 C"], "rodando"))
        st, _c, dados = self.pedir("GET", "/api/execucoes/%s/eventos?desde=%d" % (ex["id"], d["proximo"]))
        self.assertEqual(json.loads(dados)["eventos"], [])
        self.assertEqual(self.pedir("GET", "/api/execucoes/%s/eventos?desde=-1" % ex["id"])[0], 400)
        self.assertEqual(self.pedir("GET", "/api/execucoes/zzzz/eventos")[0], 404)
        self.assertEqual(self.post("/api/execucoes/%s/abrir" % ex["id"], b""),
                         (200, {"ok": True, "comando": "claude attach " + ex["id"]}))
        self.assertEqual(self.post("/api/execucoes/%s/parar" % ex["id"], {}), (200, {"ok": True}))
        self.assertEqual(self.post("/api/execucoes/deadbeef/parar", {})[0], 404)
        self.assertEqual(self.post("/api/execucoes/%s/parar" % ex["id"], {}, **{"X-Painel-Token": "x"})[0], 403)

    # ---- arquivos
    def test_estaticos(self):
        st, cab, dados = self.pedir("GET", "/")
        self.assertEqual((st, dados), (200, b"<!doctype html><title>novo</title>"))
        self.assertEqual(cab["cache-control"], "no-store")
        st, cab, _d = self.pedir("GET", "/assets/app-123.js")
        self.assertEqual((st, cab["content-type"].split(";")[0]), (200, "text/javascript"))
        self.assertIn("immutable", cab["cache-control"])
        self.assertEqual(self.pedir("GET", "/qualquer/rota")[2], b"<!doctype html><title>novo</title>")
        self.assertEqual(self.pedir("GET", "/assets/nao-existe.js")[0], 404)

    def test_travessia_e_atalho(self):
        for caminho in ("/../segredo.txt", "/%2e%2e/segredo.txt", "/assets/..%2f..%2fsegredo.txt",
                        "/assets/fuga.js", "/atalho/segredo.txt", "/..\\segredo.txt", "/.git/config",
                        "/%00", "/assets/%2e%2e/%2e%2e/segredo.txt"):
            st, _c, dados = self.pedir("GET", caminho)
            self.assertEqual(st, 404, caminho)
            self.assertNotIn(b"NAO PODE SAIR", dados)

    # ---- módulos de fora
    def test_modulo_ausente_ou_quebrado(self):
        st, d = self.app.modulo("modulo_que_nao_existe_xyz")
        self.assertEqual((st, set(d)), (503, {"erro", "avisos"}))
        ruim = types.ModuleType("modulo_ruim_xyz")

        def montar(cfg):
            raise RuntimeError("quebrou")
        ruim.montar = montar
        sys.modules["modulo_ruim_xyz"] = ruim
        self.addCleanup(sys.modules.pop, "modulo_ruim_xyz", None)
        st, d = self.app.modulo("modulo_ruim_xyz")
        self.assertEqual(st, 500)
        self.assertIn("quebrou", d["avisos"][0])


class TesteHTTPAcaoDeModulo(unittest.TestCase):
    """POST /api/modulos/<id>/acao e GET ?fresco=1 no servidor de verdade, módulo falso num pacote temporário."""

    @classmethod
    def setUpClass(cls):
        import modulos
        from test_modulos import pacote_loja
        cls.modulos = modulos
        cls.tmp = os.path.realpath(tempfile.mkdtemp())
        cls.cfg = pacote_loja(cls.tmp)
        cls.app = painel.App(cls.cfg, rodar_externos=False)
        cls.app.log = False
        cls.srv = painel.criar_servidor(cls.app, 0)
        cls.porta = cls.app.porta
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp)

    pedir, cab_post, post = TesteHTTP.pedir, TesteHTTP.cab_post, TesteHTTP.post

    def setUp(self):
        self.modulos.esquecer()
        self.addCleanup(self.modulos.esquecer)

    def test_acao_valida_e_erros(self):
        rota = "/api/modulos/loja/acao"
        st, d = self.post(rota, {"acao": "salvar", "dados": {"codigo": "987654"}})
        self.assertEqual((st, d["ok"], d["resultado"]["recebi"]), (200, True, {"codigo": "987654"}))
        self.assertEqual(self.post(rota, {"acao": "apagar", "dados": {}})[0], 400)
        self.assertEqual(self.post(rota, {"dados": {}})[0], 400)
        self.assertEqual(self.post(rota, {"acao": "salvar", "dados": "x"})[0], 400)
        self.assertEqual(self.post("/api/modulos/sumido/acao", {"acao": "salvar", "dados": {}})[0], 404)
        self.assertEqual(self.post("/api/modulos/desligado/acao", {"acao": "salvar", "dados": {}})[0], 404)
        self.assertEqual(self.post("/api/modulos/so_tela/acao", {"acao": "salvar", "dados": {}})[0], 404)
        ok = {"acao": "salvar", "dados": {}}
        self.assertEqual(self.post(rota, ok, **{"X-Painel-Token": None})[0], 403)
        self.assertEqual(self.post(rota, ok, **{"X-Painel-Token": "errado"})[0], 403)
        self.assertEqual(self.post(rota, ok, Origin="http://evil.example")[0], 403)
        self.assertEqual(self.post(rota, ok, **{"Sec-Fetch-Site": "same-site"})[0], 403)
        self.assertEqual(self.post(rota, ok, **{"Content-Type": "text/plain"})[0], 415)

    def test_quebra_e_demora_nao_ecoam_nem_derrubam(self):
        st, d = self.post("/api/modulos/loja/acao", {"acao": "quebrar", "dados": {"senha": "segredo-abc"}})
        self.assertEqual(st, 500)
        self.assertNotIn("segredo-abc", json.dumps(d))
        self.assertEqual(set(d), {"erro", "avisos"})
        curto = mock.patch.object(self.modulos.agir, "__defaults__", (0.2,))  # tempo limite de 0,2 s
        curto.start()
        self.addCleanup(curto.stop)
        st, d = self.post("/api/modulos/loja/acao", {"acao": "demorar", "dados": {"senha": "segredo-abc"}})
        self.assertEqual(st, 504, d)
        self.assertIn("ainda está rodando", d["erro"])
        self.assertNotIn("segredo-abc", json.dumps(d))
        self.assertEqual(self.post("/api/modulos/loja/acao", {"acao": "salvar", "dados": {}})[0], 409)
        for t in list(self.modulos._agindo.values()):
            t.join(5)
        self.assertEqual(self.pedir("GET", "/api/modulos")[0], 200)  # servidor continua de pé

    def test_get_fresco_ignora_cache(self):
        def contagem(rota):
            st, _c, dados = self.pedir("GET", rota)
            self.assertEqual(st, 200)
            return json.loads(dados)["abas"][0]["blocos"][0]["texto"]
        primeiro = contagem("/api/modulos/loja")
        self.assertEqual(contagem("/api/modulos/loja"), primeiro)  # cache de 30 s
        fresco = contagem("/api/modulos/loja?fresco=1")
        self.assertEqual(int(fresco), int(primeiro) + 1)
        self.assertEqual(contagem("/api/modulos/loja"), fresco)


class TesteSemBuild(unittest.TestCase):
    def test_sem_dist_mostra_aviso_sem_script(self):
        import estaticos
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp)
        st, corpo, tipo, _cache = estaticos.resolver("/", os.path.join(tmp, "dist"))
        self.assertEqual((st, tipo.split(";")[0]), (200, "text/html"))
        self.assertIn(b"npm run build", corpo)
        self.assertNotIn(b"<script", corpo)
        self.assertEqual(estaticos.resolver("/outra", os.path.join(tmp, "dist"))[0], 404)


if __name__ == "__main__":
    unittest.main()
