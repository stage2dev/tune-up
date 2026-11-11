"""Comando de módulo com esquema, aprovação do dono gravada só pelo servidor e `requer` de ação.

Nada chama o claude: o lançador usa o CLI falso de test_lancador.
"""
import sys

sys.dont_write_bytecode = True

import base64  # noqa: E402
import http.client  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402

import catalogo  # noqa: E402
import dono  # noqa: E402
import lancador  # noqa: E402
import modulos  # noqa: E402
import painel  # noqa: E402
from test_lancador import ESTADO, CLIFalso  # noqa: E402
from test_modulos import escrever, esperar_threads, pacote_loja  # noqa: E402

ESTUDIO = '''
INFO = {"titulo": "Estudio", "acoes": ["aprovar", "livre"],
        "esquemas": {"aprovar": {"aprovado": "booleano", "nota": "texto", "versao": "numero"}}}
MONTAR = [0]
CTX = {}

def montar(ctx):
    MONTAR[0] += 1
    CTX["montar"] = sorted(ctx)
    return {}

def agir(ctx, acao, dados):
    CTX["agir"] = sorted(ctx)
    if acao == "aprovar":
        return ctx["gravar_dono"]("marca", {"aprovado": dados.get("aprovado") is True})
    return {"lido": ctx["ler_dono"]()}
'''

ACOES = {"acoes": [
    {"id": "estudio.post", "grupo": "estudio", "titulo": "Post", "risco": "leitura", "prompt": "/x",
     "requer": "estudio.marca", "sandbox": True, "params": []},
    {"id": "t.leve", "grupo": "dev", "titulo": "Leve", "risco": "leitura", "prompt": "/y", "params": []},
]}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cfg = pacote_loja(self.tmp)
        escrever(os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos", "estudio", "modulo.py"), ESTUDIO)
        self.cfg["modulos"] = ["loja", "estudio"]
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)
        esperar_threads()
        self.addCleanup(esperar_threads)
        self.arq = os.path.join(self.cfg["dados_dir"], "estudio-dono.json")

    def aprovado(self):
        with open(self.arq, encoding="utf-8") as f:
            return json.load(f)["marca"]["aprovado"]


class TesteDono(Base):
    def test_gravar_e_ler(self):
        self.assertEqual(dono.ler(self.cfg, "estudio"), {})
        v = dono.gravar(self.cfg, "estudio", "marca", {"aprovado": True})
        self.assertIs(v["aprovado"], True)
        self.assertIn("gravado_em", v)
        self.assertEqual(dono.ler(self.cfg, "estudio")["marca"]["aprovado"], True)
        self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), [])

    def test_so_modulo_com_arquivo_protegido(self):
        with self.assertRaises(ValueError):
            dono.gravar(self.cfg, "loja", "marca", {"aprovado": True})  # loja-dono.json não está em sandbox.DONO
        self.assertEqual(dono.faltando(self.cfg, ["loja.marca"]), ["loja.marca"])
        self.assertFalse(os.path.exists(os.path.join(self.cfg["dados_dir"], "loja-dono.json")))

    def test_arquivo_ilegivel_nao_e_sobrescrito_e_nao_libera(self):
        escrever(self.arq, '{"marca": {"aprovado": true}')  # JSON quebrado
        with self.assertRaises(ValueError):
            dono.gravar(self.cfg, "estudio", "marca", {"aprovado": True})
        with open(self.arq, encoding="utf-8") as f:
            self.assertEqual(f.read(), '{"marca": {"aprovado": true}')
        self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), ["estudio.marca"])

    def test_atalho_no_lugar_do_arquivo_nao_libera(self):
        fora = os.path.join(self.tmp, "fora.json")
        escrever(fora, json.dumps({"marca": {"aprovado": True}}))
        os.makedirs(self.cfg["dados_dir"], exist_ok=True)
        try:
            os.symlink(fora, self.arq)
        except (OSError, NotImplementedError):
            self.skipTest("sem permissão de atalho")
        self.assertIsNone(dono.ler(self.cfg, "estudio"))
        self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), ["estudio.marca"])

    def test_aprovacao_de_outro_lugar_nao_libera(self):
        # a sessão escreve marca.json (na pasta de trabalho ou em dados): nada disso é lido
        for pasta in (self.cfg["dados_dir"], os.path.join(self.cfg["dados_dir"], "trabalhos", "x")):
            escrever(os.path.join(pasta, "marca.json"), json.dumps({"aprovado_pelo_dono": True}))
        escrever(self.arq, json.dumps({"marca": {"aprovado": "true"}, "outra": {"aprovado": True}}))
        self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), ["estudio.marca"])
        escrever(self.arq, json.dumps({"marca": True}))
        self.assertEqual(dono.faltando(self.cfg, ["estudio.marca"]), ["estudio.marca"])

    def test_validar_requer(self):
        self.assertEqual(dono.validar_requer(None), [])
        self.assertEqual(dono.validar_requer("estudio.marca"), ["estudio.marca"])
        for ruim in ([], "estudio", "Estudio.marca", "../x.marca", ["a.b"] * 9, [1], {"a": "b"}):
            with self.assertRaises(ValueError, msg=repr(ruim)):
                dono.validar_requer(ruim)
        a = dict(ACOES["acoes"][0], requer="sem_ponto")
        with self.assertRaises(ValueError):
            catalogo.validar_acao(a)
        self.assertEqual(catalogo.validar_acao(ACOES["acoes"][0])["_requer"], ["estudio.marca"])
        self.assertNotIn("_requer", catalogo.publica(catalogo.validar_acao(ACOES["acoes"][0])))

    def test_requer_sem_sandbox_e_recusado_com_aviso(self):
        for sb in (False, None):
            a = dict(ACOES["acoes"][0])
            a.pop("sandbox", None) if sb is None else a.update(sandbox=sb)
            with self.assertRaises(ValueError, msg=repr(sb)) as e:
                catalogo.validar_acao(a)
            self.assertIn("sandbox", str(e.exception))
        self.assertTrue(catalogo.validar_acao(dict(ACOES["acoes"][0], sandbox={"rede_local": False}))["sandbox"])
        escrever(os.path.join(self.tmp, "acoes", "t.json"),
                 json.dumps({"acoes": [dict(ACOES["acoes"][0], sandbox=False)]}))
        acoes, avisos = catalogo.carregar_catalogo(os.path.join(self.tmp, "acoes"))
        self.assertEqual(acoes, [])
        self.assertEqual(len(avisos), 1)
        self.assertIn("estudio.post", avisos[0])

    def test_pacote_nao_ocupa_id_de_plugin_tirando_requer_ou_sandbox(self):
        # o pacote carrega antes dos plugins: a mesma id sem requer/sandbox não pode tomar o lugar
        leve = {"id": "estudio.post", "grupo": "estudio", "titulo": "Falsa", "risco": "leitura",
                "prompt": "/z", "params": []}
        so_caixa = dict(ACOES["acoes"][0], id="estudio.video")
        so_caixa.pop("requer")
        nucleo, pacote, plugin = (os.path.join(self.tmp, n) for n in ("nucleo", "pacote", "plugin"))
        os.makedirs(nucleo)
        escrever(os.path.join(pacote, "meu.json"), json.dumps({"acoes": [leve, dict(leve, id="estudio.video")]}))
        escrever(os.path.join(plugin, "estudio.json"), json.dumps({"acoes": [ACOES["acoes"][0], so_caixa]}))
        acoes, avisos = catalogo.carregar_catalogo([nucleo, pacote, plugin])
        por_id = {a["id"]: a for a in acoes}
        self.assertEqual(sorted(por_id), ["estudio.post", "estudio.video"])
        self.assertEqual(por_id["estudio.post"]["_requer"], ["estudio.marca"])
        self.assertTrue(por_id["estudio.post"]["sandbox"])
        self.assertTrue(por_id["estudio.video"]["sandbox"])
        self.assertEqual(len(avisos), 2, avisos)
        self.assertTrue(all("meu.json" in a for a in avisos), avisos)
        # com requer e sandbox o pacote segue ocupando a id (comportamento de antes)
        escrever(os.path.join(pacote, "meu.json"), json.dumps({"acoes": [dict(ACOES["acoes"][0], titulo="Minha")]}))
        acoes, avisos = catalogo.carregar_catalogo([nucleo, pacote, plugin])
        self.assertEqual([a["titulo"] for a in acoes if a["id"] == "estudio.post"], ["Minha"])


class TesteComando(Base):
    def test_esquema_campo_desconhecido_ou_tipo_errado_da_400_sem_gravar(self):
        for dados in ({"aprovado": True, "extra": 1}, {"aprovado": "sim"}, {"versao": True},
                      {"versao": float("nan")}, {"nota": "x" * 2001}):
            cod, d = modulos.agir(self.cfg, "estudio", "aprovar", dados)
            self.assertEqual(cod, 400, dados)
            self.assertNotIn("extra", json.dumps(d))  # nome de campo digitado não volta
        self.assertFalse(os.path.exists(self.arq))

    def test_comando_grava_limpa_cache_e_montar_nao_grava(self):
        self.assertEqual(modulos.montar(self.cfg, "estudio")[0], 200)
        mod = modulos.carregar(self.cfg, "estudio")
        self.assertNotIn("gravar_dono", mod.CTX["montar"])
        cod, d = modulos.agir(self.cfg, "estudio", "aprovar", {"aprovado": True, "nota": "ok", "versao": 2})
        self.assertEqual((cod, d["resultado"]["aprovado"]), (200, True))
        self.assertIn("gravar_dono", mod.CTX["agir"])
        self.assertIs(self.aprovado(), True)
        modulos.montar(self.cfg, "estudio")
        self.assertEqual(mod.MONTAR[0], 2)  # o comando apagou o cache
        self.assertEqual(modulos.agir(self.cfg, "estudio", "livre", {"qualquer": [1]})[0], 200)  # sem esquema

    def test_esquema_invalido_do_modulo_fecha(self):
        escrever(os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos", "estudio", "modulo.py"),
                 ESTUDIO.replace('"versao": "numero"', '"versao": "data"'))
        modulos.esquecer()
        self.assertEqual(modulos.agir(self.cfg, "estudio", "aprovar", {"aprovado": True})[0], 500)
        self.assertFalse(os.path.exists(self.arq))


class TesteRequer(Base):
    def lancador(self):
        escrever(os.path.join(self.tmp, "acoes", "t.json"), json.dumps(ACOES))
        self.cfg.update(acoes_dir=os.path.join(self.tmp, "acoes"), claude_bin="claude", max_execucoes=3)
        self.cli = CLIFalso()
        return lancador.Lancador(self.cfg, lambda: ESTADO, rodar=self.cli, plataforma="darwin")

    def disparos(self):
        return [c for c, _ in self.cli.chamadas if c[1:2] == ["--bg"]]

    def test_sem_aprovacao_nao_dispara_com_aprovacao_dispara(self):
        lanc = self.lancador()
        self.assertEqual(lanc.catalogo()[1], [])
        escrever(os.path.join(self.cfg["dados_dir"], "marca.json"), json.dumps({"aprovado_pelo_dono": True}))
        with self.assertRaises(lancador.ErroAcao) as e:
            lanc.iniciar("estudio.post", {})
        self.assertEqual(e.exception.codigo, 409)
        self.assertIn("estudio.marca", e.exception.mensagem)
        self.assertEqual(self.disparos(), [])
        lanc.iniciar("t.leve", {})  # ação sem `requer` segue livre
        self.assertEqual(len(self.disparos()), 1)
        self.assertEqual(modulos.agir(self.cfg, "estudio", "aprovar", {"aprovado": True})[0], 200)
        lanc.iniciar("estudio.post", {})
        self.assertEqual(len(self.disparos()), 2)
        settings = json.loads(self.disparos()[-1][self.disparos()[-1].index("--settings") + 1])
        gancho = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"].split(" || ")[0].split()[-1]
        self.assertIn(self.arq, json.loads(base64.b64decode(gancho))["prot"])  # a sessão não grava o arquivo
        self.assertEqual(modulos.agir(self.cfg, "estudio", "aprovar", {"aprovado": False})[0], 200)
        with self.assertRaises(lancador.ErroAcao):  # revogada: volta a barrar
            lanc.iniciar("estudio.post", {})


class TesteHTTPComando(Base):
    """C10, os 3 casos de POST de comando no servidor de verdade."""

    def setUp(self):
        Base.setUp(self)
        self.app = painel.App(self.cfg, rodar_externos=False)
        self.app.log = False
        srv = painel.criar_servidor(self.app, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)

    def post(self, dado, **troca):
        cab = {"Origin": "http://127.0.0.1:%d" % self.app.porta, "Content-Type": "application/json",
               "X-Painel-Token": self.app.token, "Sec-Fetch-Site": "same-origin"}
        cab.update(troca)
        c = http.client.HTTPConnection("127.0.0.1", self.app.porta, timeout=10)
        try:
            c.request("POST", "/api/modulos/estudio/acao", body=json.dumps(dado).encode(),
                      headers={k: v for k, v in cab.items() if v is not None})
            r = c.getresponse()
            return r.status, json.loads(r.read() or b"null")
        finally:
            c.close()

    def test_c10_post_de_comando(self):
        ok = {"acao": "aprovar", "dados": {"aprovado": True}}
        self.assertEqual(self.post(ok, **{"X-Painel-Token": None})[0], 403)
        self.assertEqual(self.post(ok, **{"Sec-Fetch-Site": "cross-site"})[0], 403)
        self.assertEqual(self.post({"acao": "aprovar", "dados": {"aprovado": True, "x": 1}})[0], 400)
        self.assertFalse(os.path.exists(self.arq))
        st, d = self.post(ok)
        self.assertEqual((st, d["resultado"]["aprovado"]), (200, True))
        self.assertIs(self.aprovado(), True)


if __name__ == "__main__":
    unittest.main()
