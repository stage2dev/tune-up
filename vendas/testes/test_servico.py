"""Serviço local: rotas no servidor real em porta efêmera (saúde, token por origem exata, webhook com segredo,
Host), trava do processo, subida recusada (C9), parada limpa e a tela lendo o batimento."""
import sys

sys.dont_write_bytecode = True

import http.client  # noqa: E402
import importlib.util  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from contextlib import redirect_stderr  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)

from servico import banco, pasta, rotas, travas  # noqa: E402

PAINEL = "http://127.0.0.1:8787"
SERVICO = os.path.join(VENDAS, "servico", "servico.py")
MODULO = os.path.join(VENDAS, "painel", "modulos", "vendas", "modulo.py")


def carregar_modulo():
    spec = importlib.util.spec_from_file_location("vendas_modulo_teste", MODULO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


PARADO = "O serviço de Vendas está parado"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")


class TesteRotas(Base):
    def setUp(self):
        super().setUp()
        self.pasta = pasta.pasta_de_dados(self.projeto, base=self.base)
        self.token, self.segredo = "t" * 43, "s" * 43
        self.app = rotas.App(self.pasta, 0, PAINEL, self.token, self.segredo)
        self.servidor = rotas.criar_servidor(self.app, 0)
        threading.Thread(target=self.servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(self.servidor.server_close)
        self.addCleanup(self.servidor.shutdown)
        self.corpos = []

    def pedir(self, metodo, caminho, cab=None, corpo=None):
        cab = dict(cab or {})
        cab.setdefault("Host", "127.0.0.1:%d" % self.app.porta)
        if isinstance(corpo, (dict, list)):
            corpo = json.dumps(corpo).encode("utf-8")
            cab.setdefault("Content-Type", "application/json")
        con = http.client.HTTPConnection("127.0.0.1", self.app.porta, timeout=5)
        try:
            con.request(metodo, caminho, body=corpo, headers=cab)
            r = con.getresponse()
            bruto = r.read().decode("utf-8")
            self.corpos.append((caminho, bruto))
            return r.status, dict(r.getheaders()), bruto
        finally:
            con.close()

    def contagem(self, chave):
        con = banco.abrir(self.pasta)
        try:
            return int(banco.ler_config(con, chave, "0"))
        finally:
            con.close()

    def eventos(self):
        con = banco.abrir(self.pasta)
        try:
            return [json.loads(l["dados"]) for l in con.execute("SELECT dados FROM eventos ORDER BY id")]
        finally:
            con.close()

    def modo(self, valor):
        con = banco.abrir(self.pasta)
        banco.gravar_config(con, "webhook_modo", valor)
        con.close()

    def test_saude_responde_sem_segredo(self):
        codigo, _, bruto = self.pedir("GET", "/saude")
        self.assertEqual(codigo, 200)
        self.assertTrue(json.loads(bruto)["ok"])
        self.assertNotIn(self.token, bruto)
        self.assertNotIn(self.segredo, bruto)

    def test_token_so_para_a_origem_exata_do_painel(self):
        codigo, cab, bruto = self.pedir("GET", "/token-de-envio", {"Origin": PAINEL})
        self.assertEqual(codigo, 200)
        self.assertEqual(json.loads(bruto), {"token": self.token})
        self.assertEqual(cab.get("Access-Control-Allow-Origin"), PAINEL)
        for origem in (None, "http://127.0.0.1:8788", "http://localhost:8787", "https://127.0.0.1:8787",
                       "http://127.0.0.1:8787/", "null", "http://127.0.0.1"):
            cab_pedido = {"Origin": origem} if origem else {}
            codigo, cab, bruto = self.pedir("GET", "/token-de-envio", cab_pedido)
            self.assertEqual(codigo, 403, origem)
            self.assertNotIn(self.token, bruto)
            self.assertNotIn("Access-Control-Allow-Origin", cab)

    def test_options_e_cors_so_para_o_painel(self):
        codigo, cab, _ = self.pedir("OPTIONS", "/token-de-envio", {"Origin": PAINEL})
        self.assertEqual(codigo, 204)
        self.assertEqual(cab.get("Access-Control-Allow-Origin"), PAINEL)
        self.assertIn(rotas.CAB_TOKEN, cab.get("Access-Control-Allow-Headers"))
        codigo, cab, _ = self.pedir("OPTIONS", "/token-de-envio", {"Origin": "http://127.0.0.1:9999"})
        self.assertEqual(codigo, 403)
        self.assertNotIn("Access-Control-Allow-Origin", cab)
        self.assertEqual(self.pedir("OPTIONS", "/token-de-envio")[0], 403)

    def test_host_recusado_e_docker_so_no_webhook(self):
        self.assertEqual(self.pedir("GET", "/saude", {"Host": "exemplo.com"})[0], 421)
        self.assertEqual(self.pedir("GET", "/saude", {"Host": "127.0.0.1:1"})[0], 421)
        self.assertEqual(self.pedir("GET", "/saude", {"Host": "localhost:%d" % self.app.porta})[0], 200)
        docker = {"Host": "host.docker.internal:%d" % self.app.porta}
        self.assertEqual(self.pedir("GET", "/saude", docker)[0], 421)
        self.assertEqual(self.pedir("GET", "/token-de-envio", dict(docker, Origin=PAINEL))[0], 421)
        cab = dict(docker, **{rotas.CAB_SEGREDO: self.segredo})
        self.assertEqual(self.pedir("POST", "/webhook/inst1", cab, {"event": "x"})[0], 200)

    def test_rota_com_token_compara_o_token(self):
        self.assertEqual(self.pedir("GET", "/estado")[0], 403)
        self.assertEqual(self.pedir("GET", "/estado", {rotas.CAB_TOKEN: "t" * 42 + "u"})[0], 403)
        codigo, _, bruto = self.pedir("GET", "/estado", {rotas.CAB_TOKEN: self.token})
        self.assertEqual(codigo, 200)
        self.assertEqual(json.loads(bruto)["webhook_modo"], rotas.MODO_REGISTRA)

    def test_webhook_modo_recusa_segredo_errado_401(self):
        self.modo(rotas.MODO_RECUSA)
        errado = {rotas.CAB_SEGREDO: "s" * 42 + "x"}
        self.assertEqual(self.pedir("POST", "/webhook/inst1", errado, {"event": "a"})[0], 401)
        self.assertEqual(self.pedir("POST", "/webhook/inst1", {}, {"event": "b"})[0], 401)
        self.assertEqual(self.eventos(), [])
        self.assertEqual(self.contagem("webhook_invalidos"), 2)
        certo = {rotas.CAB_SEGREDO: self.segredo}
        self.assertEqual(self.pedir("POST", "/webhook/inst1", certo, {"event": "c"})[0], 200)
        self.assertEqual(self.eventos(), [{"instancia": "inst1", "segredo_ok": True, "corpo": {"event": "c"}}])
        self.assertEqual(self.contagem("webhook_validos"), 1)

    def test_modo_desconhecido_fecha_como_recusa(self):
        self.modo("qualquer")
        self.assertEqual(self.pedir("POST", "/webhook/inst1", {}, {"event": "a"})[0], 401)

    def test_webhook_modo_registra_aceita_e_conta(self):
        certo = {rotas.CAB_SEGREDO: self.segredo}
        for _ in range(3):
            self.assertEqual(self.pedir("POST", "/webhook/inst1", certo, {"event": "ok"})[0], 200)
        self.assertEqual(self.contagem("webhook_validos_seguidos"), 3)
        self.assertEqual(self.pedir("POST", "/webhook/inst1", {}, {"event": "sem"})[0], 200)
        self.assertEqual(self.contagem("webhook_validos"), 3)
        self.assertEqual(self.contagem("webhook_invalidos"), 1)
        self.assertEqual(self.contagem("webhook_validos_seguidos"), 0)
        self.assertEqual(self.eventos()[-1], {"instancia": "inst1", "segredo_ok": False, "corpo": {"event": "sem"}})

    def test_webhook_so_json_e_com_limite(self):
        certo = {rotas.CAB_SEGREDO: self.segredo}
        texto = dict(certo, **{"Content-Type": "text/plain"})
        self.assertEqual(self.pedir("POST", "/webhook/inst1", texto, b'{"a": 1}')[0], 415)
        json_ = dict(certo, **{"Content-Type": "application/json"})
        self.assertEqual(self.pedir("POST", "/webhook/inst1", json_, b"{nao e json")[0], 400)
        self.assertEqual(self.pedir("POST", "/webhook/inst1", certo, [1, 2])[0], 400)
        grande = b'{"a": "' + b"x" * (rotas.CORPO_MAX + 10) + b'"}'
        self.assertEqual(self.pedir("POST", "/webhook/inst1", json_, grande)[0], 413)
        self.assertEqual(self.pedir("POST", "/webhook/../x", certo, {"a": 1})[0], 404)
        self.assertEqual(self.pedir("POST", "/outra", certo, {"a": 1})[0], 404)
        self.assertEqual(self.eventos(), [])

    def test_nenhum_segredo_em_resposta_e_nada_no_log(self):
        erro = io.StringIO()
        with redirect_stderr(erro):
            self.pedir("GET", "/saude")
            self.pedir("GET", "/estado", {rotas.CAB_TOKEN: self.token})
            self.pedir("GET", "/nada?q=%2B5511900000001")
            self.pedir("POST", "/webhook/inst1", {rotas.CAB_SEGREDO: self.segredo}, {"tel": "+55 11 90000-0001"})
            self.pedir("POST", "/webhook/inst1", {rotas.CAB_SEGREDO: "errado"}, {"tel": "+55 11 90000-0001"})
            self.pedir("OPTIONS", "/token-de-envio", {"Origin": PAINEL})
            self.pedir("GET", "/token-de-envio", {"Origin": "http://127.0.0.1:1"})
        self.assertEqual(erro.getvalue(), "")
        for caminho, bruto in self.corpos:
            self.assertNotIn(self.token, bruto, caminho)
            self.assertNotIn(self.segredo, bruto, caminho)
            self.assertNotIn("9000", bruto, caminho)


class TesteOrigemETrava(Base):
    def test_origem_do_painel_exige_porta_e_nada_mais(self):
        self.assertEqual(rotas.origem_do_painel("http://127.0.0.1:8787/"), PAINEL)
        for ruim in ("http://127.0.0.1", "127.0.0.1:8787", "http://127.0.0.1:8787/x", "ftp://a:1",
                     "http://u:p@127.0.0.1:8787", ""):
            with self.assertRaises(ValueError, msg=ruim):
                rotas.origem_do_painel(ruim)

    def test_segunda_trava_no_mesmo_lugar_recusa_na_hora(self):
        p = pasta.pasta_de_dados(self.projeto, base=self.base)
        primeira = travas.TravaDoProcesso(p).pegar()
        self.addCleanup(primeira.soltar)
        with self.assertRaises(travas.TravaOcupada):
            travas.TravaDoProcesso(p).pegar()
        primeira.soltar()
        travas.TravaDoProcesso(p).pegar().soltar()

    def test_ramo_msvcrt_ocupada_vira_trava_ocupada(self):
        p = pasta.pasta_de_dados(self.projeto, base=self.base)
        falso = mock.Mock(LK_NBLCK=2, LK_UNLCK=0)
        falso.locking.side_effect = OSError(13, "ocupada")
        with mock.patch.object(travas, "fcntl", None), mock.patch.object(travas, "msvcrt", falso):
            with self.assertRaises(travas.TravaOcupada):
                travas.TravaDoProcesso(p).pegar()
        falso.locking.side_effect = None
        with mock.patch.object(travas, "fcntl", None), mock.patch.object(travas, "msvcrt", falso):
            t = travas.TravaDoProcesso(p).pegar()
            t.soltar()
        self.assertEqual([c.args[1] for c in falso.locking.call_args_list], [2, 2, 0])

    def test_segredo_do_webhook_sobrevive_e_e_privado(self):
        p = pasta.pasta_de_dados(self.projeto, base=self.base)
        arq = os.path.join(p, "segredo_webhook")
        s1 = travas.ler_ou_criar_segredo(arq)
        self.assertEqual(s1, travas.ler_ou_criar_segredo(arq))
        if os.name != "nt":
            self.assertEqual(os.stat(arq).st_mode & 0o777, 0o600)


class TesteProcesso(Base):
    def subir(self, base=None, esperar_linha=True):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.Popen([sys.executable, "-B", SERVICO, "--projeto", self.projeto, "--porta", "0",
                                 "--base", base or self.base], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                env=env, cwd=self.tmp)
        self.addCleanup(lambda: proc.poll() is None and (proc.kill(), proc.communicate()))
        if not esperar_linha:
            return proc, None
        linha = proc.stdout.readline().decode("utf-8")
        self.assertIn("serviço de Vendas em http://127.0.0.1:", linha, proc.poll())
        return proc, int(linha.split("127.0.0.1:")[1].split()[0])

    def test_segundo_processo_recusado(self):
        primeiro, porta = self.subir()
        segundo, _ = self.subir(esperar_linha=False)
        saida, erro = segundo.communicate(timeout=10)
        self.assertEqual(segundo.returncode, 3)
        self.assertIn("já está rodando", erro.decode("utf-8"))
        con = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
        con.request("GET", "/saude")
        self.assertEqual(con.getresponse().status, 200)
        con.close()

    def test_recusa_pasta_dentro_do_projeto_e_sob_stfolder(self):
        dentro = os.path.join(self.projeto, "dados")
        sync = os.path.join(self.tmp, "sync")
        os.makedirs(os.path.join(sync, ".stfolder"))
        for base, texto in ((dentro, "dentro do projeto"), (os.path.join(sync, "dados"), "sincronizada")):
            proc, _ = self.subir(base=base, esperar_linha=False)
            saida, erro = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 2)
            self.assertIn(texto, erro.decode("utf-8"))
            self.assertFalse(os.path.exists(base))
        achados = [a for _, _, arqs in os.walk(self.projeto) for a in arqs if a.startswith("vendas.db")]
        self.assertEqual(achados, [])

    @unittest.skipIf(os.name == "nt", "Windows não entrega SIGTERM a um processo filho (terminate mata na hora)")
    def test_tela_le_batimento_e_parada_limpa(self):
        modulo = carregar_modulo()
        proc, _ = self.subir()
        p = pasta.caminho_da_pasta(self.projeto, self.base)
        with open(os.path.join(p, "token_envio"), encoding="utf-8") as f:
            token = f.read()
        if os.name != "nt":
            self.assertEqual(os.stat(os.path.join(p, "token_envio")).st_mode & 0o777, 0o600)
        fim = time.monotonic() + 20  # máquina lenta: a leitura logo depois da subida pode ainda não ver o batimento
        while True:
            dado = modulo.montar({"raiz": self.projeto}, base=self.base)
            bloco = dado["abas"][0]["blocos"][0]
            if bloco["titulo"] != PARADO or time.monotonic() > fim:
                break
            time.sleep(0.2)
        self.assertNotEqual(bloco["titulo"], PARADO, dado["avisos"])   # rodando: o cartão da conexão, sem aviso de parado
        self.assertEqual(dado["avisos"], [])
        self.assertNotIn(token, json.dumps(dado))
        proc.send_signal(signal.SIGTERM)
        saida, erro = proc.communicate(timeout=30)
        self.assertEqual(proc.returncode, 0, erro)
        self.assertIn("parado", saida.decode("utf-8"))
        self.assertFalse(os.path.exists(os.path.join(p, "token_envio")))
        con = banco.abrir(p)
        self.assertIsNone(con.execute("SELECT * FROM batimento").fetchone())
        con.close()
        bloco = modulo.montar({"raiz": self.projeto, "config": {"porta": 8790}}, base=self.base)["abas"][0]["blocos"][0]
        self.assertEqual(bloco["titulo"], PARADO)
        self.assertIn("servico.py --projeto", bloco["texto"])
        self.assertIn("--painel http://127.0.0.1:8790", bloco["texto"])

    def test_batimento_velho_e_parado(self):
        modulo = carregar_modulo()
        p = pasta.pasta_de_dados(self.projeto, base=self.base)
        con = banco.abrir(p)
        con.execute("INSERT INTO batimento (id, pid, em) VALUES (1, 1, '2020-01-01T00:00:00+00:00')")
        bloco = modulo.montar({"raiz": self.projeto}, base=self.base)["abas"][0]["blocos"][0]
        con.close()
        self.assertEqual(bloco["titulo"], PARADO)

    def test_tela_nunca_le_o_arquivo_do_token(self):
        with open(MODULO, encoding="utf-8") as f:
            fonte = f.read()
        self.assertNotIn("token_envio", fonte)
        self.assertNotIn("ARQUIVO_TOKEN", fonte)


if __name__ == "__main__":
    unittest.main()
