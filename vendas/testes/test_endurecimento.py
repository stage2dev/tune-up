"""Endurecimento depois da revisão da Parte B: porta e marca do projeto no banco e no /saude, segredo novo do
webhook desarma a recusa, --refazer mantém a senha do Postgres, regras de negar, válido só conta com o evento
guardado, avisos da subida sem conector, telefone com 00 e 0, transições do envio e hash estável na caixa."""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import http.client  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)

from servico import banco, evolution_local, pasta, rotas, servico, telefone  # noqa: E402
from servico.conectores import evolution  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402

SERVICO = os.path.join(VENDAS, "servico", "servico.py")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta = pasta.pasta_de_dados(self.projeto, base=self.base)

    def subir(self):
        """Sobe o serviço de verdade e devolve (processo, porta). Sem variáveis da Evolution no ambiente."""
        env = {k: v for k, v in os.environ.items() if k not in (evolution.VAR_URL, evolution.VAR_CHAVE)}
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([sys.executable, "-B", SERVICO, "--projeto", self.projeto, "--porta", "0",
                                 "--base", self.base], stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        self.addCleanup(lambda: proc.poll() is None and (proc.kill(), proc.communicate()))
        linha = proc.stdout.readline().decode("utf-8")
        if "127.0.0.1:" not in linha:
            proc.kill()
            self.fail("o serviço não subiu: %s" % proc.communicate()[1].decode("utf-8"))
        return proc, int(linha.split("127.0.0.1:")[1].split()[0])

    def parar(self, proc):
        proc.kill()
        return proc.communicate(timeout=30)[1].decode("utf-8")

    def config(self, chave, padrao=None):
        con = banco.abrir(self.pasta)
        try:
            return banco.ler_config(con, chave, padrao)
        finally:
            con.close()


class TesteSubida(Base):
    def test_registra_porta_e_marca_e_avisa_sem_conector(self):
        proc, porta = self.subir()
        marca = os.path.basename(self.pasta)
        self.assertEqual(self.config("servico_porta"), str(porta))
        self.assertEqual(self.config("servico_marca"), marca)
        con = http.client.HTTPConnection("127.0.0.1", porta, timeout=5)
        con.request("GET", "/saude")
        self.assertEqual(json.loads(con.getresponse().read().decode("utf-8"))["marca"], marca)
        con.close()
        self.assertIn("nenhum conector de WhatsApp configurado", self.parar(proc))

    def test_segredo_novo_desarma_a_recusa(self):
        proc, _ = self.subir()
        self.parar(proc)
        con = banco.abrir(self.pasta)
        banco.gravar_config(con, "webhook_modo", rotas.MODO_RECUSA)
        banco.gravar_config(con, "webhook_validos_seguidos", "25")
        con.close()
        proc, _ = self.subir()  # mesmo segredo: nada muda
        self.assertNotIn("segredo do webhook é novo", self.parar(proc))
        self.assertEqual(self.config("webhook_modo"), rotas.MODO_RECUSA)
        os.remove(os.path.join(self.pasta, servico.ARQUIVO_SEGREDO))
        proc, _ = self.subir()
        self.assertIn("segredo do webhook é novo", self.parar(proc))
        self.assertEqual(self.config("webhook_modo"), rotas.MODO_REGISTRA)
        self.assertEqual(self.config("webhook_validos_seguidos"), "0")

    def test_env_ilegivel_avisa_e_sobe(self):
        os.makedirs(os.path.join(evolution_local.caminho_env(self.pasta)))  # .env que é pasta: OSError ao abrir
        proc, _ = self.subir()
        erro = self.parar(proc)
        self.assertIn("não consegui ler", erro)
        self.assertNotIn("Traceback", erro)

    def test_env_incompleto_avisa(self):
        os.makedirs(evolution_local.pasta_evolution(self.pasta))
        with open(evolution_local.caminho_env(self.pasta), "w", encoding="utf-8") as f:
            f.write("SERVER_URL=http://127.0.0.1:8080\n")
        avisos = io.StringIO()
        with contextlib.redirect_stderr(avisos):
            self.assertIsNone(servico.conector(self.pasta, 8791, "s" * 43, print))
        self.assertIn("incompleto", avisos.getvalue())
        self.assertIn("nenhum conector", avisos.getvalue())


class TesteSegredoTrocado(Base):
    def test_segredo_trocado_volta_para_registra(self):
        con = banco.abrir(self.pasta)
        self.addCleanup(con.close)
        self.assertFalse(rotas.conferir_segredo(con, "a" * 43))
        banco.gravar_config(con, "webhook_modo", rotas.MODO_RECUSA)
        banco.gravar_config(con, "webhook_validos_seguidos", "30")
        self.assertFalse(rotas.conferir_segredo(con, "a" * 43))
        self.assertEqual(banco.ler_config(con, "webhook_modo"), rotas.MODO_RECUSA)
        self.assertTrue(rotas.conferir_segredo(con, "b" * 43))
        self.assertEqual(banco.ler_config(con, "webhook_modo"), rotas.MODO_REGISTRA)
        self.assertEqual(banco.ler_config(con, "webhook_validos_seguidos"), "0")
        self.assertNotIn("b" * 43, json.dumps([tuple(r) for r in con.execute("SELECT * FROM config")]))


class TesteWebhookTransacao(Base):
    def test_valido_so_conta_com_o_evento_guardado(self):
        def quebrar(con, instancia, corpo, segredo_ok):
            banco.registrar_evento(con, "webhook", "{}")
            raise RuntimeError("falha depois de guardar")
        app = rotas.App(self.pasta, 0, "http://127.0.0.1:18787", "t" * 43, "s" * 43, despachar=quebrar)
        srv = rotas.criar_servidor(app, 0)
        threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        con = http.client.HTTPConnection("127.0.0.1", app.porta, timeout=5)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises((http.client.HTTPException, OSError)):
            con.request("POST", "/webhook/loja", body=b'{"event": "x"}', headers={
                "Content-Type": "application/json", rotas.CAB_SEGREDO: "s" * 43})
            con.getresponse().read()
        con.close()
        self.assertEqual(self.config("webhook_validos", "0"), "0")
        self.assertEqual(self.config("webhook_validos_seguidos", "0"), "0")
        c = banco.abrir(self.pasta)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM eventos").fetchone()[0], 0)
        c.close()


class TesteRefazer(Base):
    def valor(self, caminho, chave):
        with open(caminho, encoding="utf-8") as f:
            return re.search(r"^%s=(.*)$" % chave, f.read(), re.M).group(1)

    def test_refazer_mantem_a_senha_e_senha_nova_troca(self):
        env = evolution_local.preparar(self.projeto, base=self.base)["env"]
        chave, senha = self.valor(env, "AUTHENTICATION_API_KEY"), self.valor(env, "POSTGRES_PASSWORD")
        evolution_local.preparar(self.projeto, base=self.base, refazer=True)
        self.assertEqual(self.valor(env, "POSTGRES_PASSWORD"), senha)
        self.assertIn(senha, self.valor(env, "DATABASE_CONNECTION_URI"))
        self.assertNotEqual(self.valor(env, "AUTHENTICATION_API_KEY"), chave)
        with self.assertRaises(ValueError):
            evolution_local.preparar(self.projeto, base=self.base, senha_nova=True)
        evolution_local.preparar(self.projeto, base=self.base, refazer=True, senha_nova=True)
        self.assertNotEqual(self.valor(env, "POSTGRES_PASSWORD"), senha)

    def test_refazer_sem_senha_no_env_recusa_sem_mexer(self):
        env = evolution_local.preparar(self.projeto, base=self.base)["env"]
        with open(env, "w", encoding="utf-8") as f:
            f.write("SERVER_URL=http://127.0.0.1:8080\n")
        with self.assertRaises(ValueError):
            evolution_local.preparar(self.projeto, base=self.base, refazer=True)
        with open(env, encoding="utf-8") as f:
            self.assertEqual(f.read(), "SERVER_URL=http://127.0.0.1:8080\n")


class TesteRegrasDeNegar(unittest.TestCase):
    def test_lista_completa(self):
        portas = ["Bash(*%s:%d*)" % (h, p) for p in list(range(8791, 8796)) + list(range(8080, 8085))
                  for h in ("127.0.0.1", "localhost")]   # toda porta que o preparo pode escolher
        esperado = portas + [
            "Bash(*/api/modulos/*/acao*)", "Bash(*tune-up-vendas*)", "Bash(*docker exec*)", "Bash(*docker inspect*)",
            "Bash(*docker compose config*)", "Bash(*security find-generic-password*)",
            "Read(~/Library/Application Support/tune-up-vendas/**)",
            "Edit(~/Library/Application Support/tune-up-vendas/**)",
            "Write(~/Library/Application Support/tune-up-vendas/**)",
            "Read(~/.local/share/tune-up-vendas/**)", "Edit(~/.local/share/tune-up-vendas/**)",
            "Write(~/.local/share/tune-up-vendas/**)",
            "Read(~/AppData/Local/tune-up-vendas/**)", "Edit(~/AppData/Local/tune-up-vendas/**)",
            "Write(~/AppData/Local/tune-up-vendas/**)"]
        self.assertEqual(carregar_modulo().INFO["negar"], esperado)
        with open(os.path.join(VENDAS, "README.md"), encoding="utf-8") as f:
            leia = f.read()
        for regra in esperado[20:26] + ["Bash(*127.0.0.1:8791*)", "Bash(*localhost:8080*)"]:
            self.assertIn(regra, leia)
        self.assertIn("8791` to `8795", leia)
        self.assertIn("8080` to `8084", leia)


class TesteTelefone(unittest.TestCase):
    def test_00_e_0_de_discagem(self):
        self.assertEqual(telefone.normalizar("0055 11 90000-0001"), "5511900000001")
        self.assertEqual(telefone.normalizar("011 90000-0001"), "5511900000001")
        self.assertEqual(telefone.normalizar("(011) 3000-0001"), "551130000001")
        self.assertEqual(telefone.normalizar("00 44 20 7946 0000"), "442079460000")
        for ruim in ("+0 44 20 7946 0000", "044 20 7946 0000 1", "+00 55 11 90000-0001"):
            with self.assertRaises(telefone.TelefoneInvalido, msg=ruim):
                telefone.normalizar(ruim)


class TesteTransicaoDoEnvio(Base):
    def test_enviado_e_final(self):
        con = banco.abrir(self.pasta)
        self.addCleanup(con.close)
        envio = banco.registrar_envio(con, "k1", "manual")
        banco.mudar_envio(con, envio, "enviado", id_externo="X1")
        for estado in ("negado", "falhou", "pendente", "incerto"):
            with self.assertRaises(banco.EscritaSemEfeito, msg=estado):
                banco.mudar_envio(con, envio, estado)
        self.assertEqual(con.execute("SELECT estado FROM envios WHERE id = ?", (envio,)).fetchone()[0], "enviado")
        outro = banco.registrar_envio(con, "k2", "manual")
        banco.mudar_envio(con, outro, "incerto")
        banco.mudar_envio(con, outro, "enviado")  # o dono confirma que chegou


class TestePastaNaCaixa(Base):
    def test_mesmo_projeto_com_outra_caixa_abre_a_mesma_pasta(self):
        trocado = os.path.join(self.tmp, "PROJETO")
        if not os.path.exists(trocado) or not os.path.samefile(self.projeto, trocado):
            self.skipTest("disco diferencia maiúsculas de minúsculas")
        self.assertEqual(pasta.caminho_da_pasta(trocado, self.base), self.pasta)
        self.assertEqual(pasta.pasta_de_dados(trocado, self.base), self.pasta)


if __name__ == "__main__":
    unittest.main()
