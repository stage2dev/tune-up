"""Portão, o caminho do envio: estados (pendente antes do conector, enviado/falhou/incerto), C6 (aceitou e caiu ->
1 'incerto' e 0 reenvios depois de reiniciar), opt-out depois de enfileirar, corrida com a mesma chave, reenviar a
MESMA linha, rota POST /enviar (origem fixa) e a busca que proíbe enviar_* fora do portão."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import http.client  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)

from servico import banco, pasta, portao, rotas  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.test_portao import AGORA, CLIENTE, INST, Base  # noqa: E402

SERVICO = os.path.join(VENDAS, "servico", "servico.py")
PROIBIDO = re.compile(r"\.enviar_(texto|audio)\b|getattr\([^)]*enviar_(texto|audio)")
PAINEL = "http://127.0.0.1:8787"


def chamadas_proibidas(raiz):
    """Arquivos .py (fora de servico/portao.py e dos testes) que chamam enviar_texto/enviar_audio de um conector."""
    achados = []
    for pasta_atual, dirs, arquivos in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in ("testes", "__pycache__")]
        for nome in arquivos:
            caminho = os.path.join(pasta_atual, nome)
            if not nome.endswith(".py") or os.path.relpath(caminho, raiz) == os.path.join("servico", "portao.py"):
                continue
            with open(caminho, encoding="utf-8") as f:
                for n, linha in enumerate(f, 1):
                    if PROIBIDO.search(linha):
                        achados.append("%s:%d" % (os.path.relpath(caminho, raiz), n))
    return achados


class CaiDepoisDeEntregar(ConectorFalso):
    """Entrega e o processo morre antes de anotar o resultado (KeyboardInterrupt não é Exception)."""

    def enviar_texto(self, instancia, telefone, texto):
        ConectorFalso.enviar_texto(self, instancia, telefone, texto)
        raise KeyboardInterrupt


class Lento(ConectorFalso):
    def enviar_texto(self, instancia, telefone, texto):
        time.sleep(0.3)
        return ConectorFalso.enviar_texto(self, instancia, telefone, texto)


class TesteEstados(Base):
    def contar(self, estado):
        return self.con.execute("SELECT COUNT(*) FROM envios WHERE estado = ?", (estado,)).fetchone()[0]

    def test_pendente_gravado_antes_do_conector(self):
        vistos = []

        class Espiao(ConectorFalso):
            def enviar_texto(s, instancia, telefone, texto):
                outra = banco.abrir(self.pasta)   # outra conexão: a linha já está gravada (commit)
                vistos.append([tuple(l) for l in outra.execute("SELECT estado, origem, telefone FROM envios")])
                outra.close()
                return ConectorFalso.enviar_texto(s, instancia, telefone, texto)
        self.c = Espiao()
        self.enviado(self.mandar("manual"))
        self.assertEqual(vistos, [[("pendente", "manual", "5511900000001")]])

    def test_recusado_falhou_timeout_incerto(self):
        self.c.modo_envio = "recusar"
        r = self.mandar("manual", chave="a")
        self.assertEqual((r["estado"], r["motivo"]), ("falhou", "nao_enviado:400"))
        self.c.modo_envio = "timeout"
        self.assertEqual(self.mandar("manual", chave="b")["estado"], "incerto")
        self.assertEqual(self.mandar("manual", chave="b")["estado"], "duplicado")   # incerto ocupa a chave
        self.assertEqual(self.c.envios(), 2)

    def test_c6_aceitou_e_caiu_reinicio_1_incerto_0_reenvio(self):
        self.c.modo_envio = "aceitar_e_cair"
        self.assertEqual(self.mandar("manual")["estado"], "incerto")
        self.assertEqual(portao.pendentes_para_incerto(self.con), 0)   # reinício: nada pendente, nada reenvia
        self.assertEqual((self.contar("incerto"), self.c.envios(), len(self.c.entregues)), (1, 1, 1))

    def test_c6_processo_morre_no_meio_e_a_subida_real_marca_incerto(self):
        self.c = CaiDepoisDeEntregar()
        with self.assertRaises(KeyboardInterrupt):
            self.mandar("manual")
        self.assertEqual(self.contar("pendente"), 1)
        self.con.close()
        env = {k: v for k, v in os.environ.items() if not k.startswith("VENDAS_")}
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.Popen([sys.executable, "-B", SERVICO, "--projeto", os.path.join(self.tmp, "projeto"),
                                 "--porta", "0", "--base", os.path.join(self.tmp, "dados")],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, cwd=self.tmp)
        self.addCleanup(lambda: proc.poll() is None and (proc.kill(), proc.communicate()))
        linha = proc.stdout.readline().decode("utf-8")
        self.assertIn("serviço de Vendas em", linha, proc.poll())
        proc.kill()
        _, erro = proc.communicate(timeout=10)
        self.assertIn("1 envio(s) ficaram incertos", erro.decode("utf-8"))
        self.con = banco.abrir(self.pasta)
        linhas = [tuple(l) for l in self.con.execute("SELECT estado, motivo FROM envios")]
        self.assertEqual(linhas, [("incerto", "pendente_na_subida")])
        self.assertEqual((self.c.envios(), len(self.c.entregues)), (1, 1))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios WHERE estado='enviado' "
                                          "AND criado_em IS NULL").fetchone()[0], 0)

    def test_optout_depois_de_enfileirar_nega_na_hora(self):
        self.assertEqual(portao.pode_enviar(self.con, "campanha", CLIENTE, agora=AGORA), (True, None))
        banco.marcar_optout(self.con, CLIENTE)   # chegou SAIR entre a fila e o envio
        self.negado(self.mandar("campanha"), "optout")

    def test_corrida_com_a_mesma_chave_chama_o_conector_1_vez(self):
        self.c = Lento()
        largada, resultados = threading.Barrier(2), []

        def correr():
            c = banco.abrir(self.pasta)   # uma conexão por fio, como no servidor
            try:
                largada.wait()
                resultados.append(portao.enviar_manual(c, self.c, INST, CLIENTE, "oi", "clique-1", agora=AGORA))
            finally:
                c.close()
        fios = [threading.Thread(target=correr) for _ in range(2)]
        for f in fios:
            f.start()
        for f in fios:
            f.join(10)
        self.assertEqual(sorted(r["estado"] for r in resultados), ["duplicado", "enviado"])
        self.assertEqual(self.c.envios(), 1)

    def test_enviado_sempre_com_criado_em(self):
        for i, origem in enumerate(("manual", "ia", "campanha")):
            self.mandar(origem, chave="k%d" % i)
        self.assertEqual(self.contar("enviado"), 3)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios WHERE estado='enviado' "
                                          "AND criado_em IS NULL").fetchone()[0], 0)


class TesteReenviar(Base):
    def test_reenviar_volta_a_mesma_linha(self):
        self.c.modo_envio = "timeout"
        envio_id = self.mandar("manual")["envio_id"]
        self.c.modo_envio = "ok"
        r = portao.reenviar(self.con, self.c, INST, envio_id, agora=AGORA)
        self.assertEqual((r["estado"], r["envio_id"]), ("enviado", envio_id))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios").fetchone()[0], 1)
        self.assertEqual(self.c.envios(), 2)
        self.assertEqual(portao.reenviar(self.con, self.c, INST, envio_id)["motivo"], "nao_reenviavel")
        self.assertEqual(self.c.envios(), 2)

    def test_reenviar_reconfere_a_regra(self):
        self.c.modo_envio = "aceitar_e_cair"
        envio_id = self.mandar("campanha")["envio_id"]
        banco.marcar_optout(self.con, CLIENTE)
        r = portao.reenviar(self.con, self.c, INST, envio_id, agora=AGORA)
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "optout"))
        self.assertEqual(self.linha(envio_id)["estado"], "incerto")   # a linha não muda
        self.assertEqual(self.c.envios(), 1)

    def incertos_de_2h_atras(self, n):
        self.c.modo_envio = "timeout"
        antes = AGORA - datetime.timedelta(hours=2)
        ids = [self.mandar("manual", chave="v%d" % i, agora=antes + datetime.timedelta(minutes=i))["envio_id"]
               for i in range(n)]
        self.c.modo_envio = "ok"
        return ids

    def test_reenvio_conta_no_teto_do_minuto(self):
        ids = self.incertos_de_2h_atras(9)
        estados = [portao.reenviar(self.con, self.c, INST, i, agora=AGORA) for i in ids]
        self.assertEqual([r["estado"] for r in estados], ["enviado"] * 8 + ["negado"])
        self.assertEqual(estados[-1]["motivo"], "teto_minuto")
        self.assertEqual(self.c.envios(), 9 + 8)

    def test_reenvio_conta_para_os_envios_seguintes(self):
        for i in self.incertos_de_2h_atras(8):
            self.assertEqual(portao.reenviar(self.con, self.c, INST, i, agora=AGORA)["estado"], "enviado")
        self.negado(self.mandar("manual", chave="novo", agora=AGORA), "teto_minuto", chamadas=8 + 8)
        primeira = self.linha(1)   # criado_em segue sendo a criação; tentado_em é a última tentativa
        self.assertEqual((primeira["criado_em"] < primeira["tentado_em"], primeira["tentado_em"]),
                         (True, portao._iso(AGORA)))


class TesteRota(Base):
    def setUp(self):
        super().setUp()
        banco.gravar_config(self.con, "instancia", INST)
        self.token = "t" * 43
        self.app = rotas.App(self.pasta, 0, PAINEL, self.token, "s" * 43, conector=self.c)
        servidor = rotas.criar_servidor(self.app, 0)
        threading.Thread(target=servidor.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)

    def post(self, corpo, token=None):
        cab = {"Host": "127.0.0.1:%d" % self.app.porta, "Content-Type": "application/json",
               rotas.CAB_TOKEN: self.token if token is None else token}
        con = http.client.HTTPConnection("127.0.0.1", self.app.porta, timeout=5)
        try:
            con.request("POST", "/enviar", body=json.dumps(corpo).encode("utf-8"), headers=cab)
            r = con.getresponse()
            return r.status, r.read().decode("utf-8")
        finally:
            con.close()

    def test_sem_token_403_e_nada_sai(self):
        self.assertEqual(self.post({"telefone": CLIENTE, "texto": "oi", "id_tela": "a"}, token="x")[0], 403)
        self.assertEqual(self.c.envios(), 0)

    def test_origem_do_corpo_ignorada(self):
        status, bruto = self.post({"telefone": CLIENTE, "texto": "segredo-do-texto", "id_tela": "a",
                                   "origem": "teste_audio"})
        self.assertEqual((status, json.loads(bruto)["estado"]), (200, "enviado"))
        self.assertEqual(self.con.execute("SELECT origem FROM envios").fetchone()[0], "manual")
        self.assertNotIn("segredo-do-texto", bruto)
        self.assertNotIn("900000001", bruto)

    def test_optout_pede_confirmacao_explicita(self):
        banco.marcar_optout(self.con, CLIENTE)
        corpo = {"telefone": CLIENTE, "texto": "oi", "id_tela": "a", "confirmar_optout": "true"}
        self.assertEqual(json.loads(self.post(corpo)[1])["motivo"], "optout_pede_confirmacao")
        corpo["confirmar_optout"] = True
        self.assertEqual(json.loads(self.post(corpo)[1])["estado"], "enviado")
        self.assertEqual(self.c.envios(), 1)

    def test_pedido_ruim_e_sem_conector(self):
        self.assertEqual(self.post({"telefone": "123", "texto": "oi", "id_tela": "a"})[0], 400)
        self.assertEqual(self.post({"telefone": CLIENTE, "texto": "", "id_tela": "a"})[0], 400)
        self.assertEqual(self.post({"telefone": CLIENTE, "texto": "oi", "id_tela": "a b"})[0], 400)
        self.app.conector = None
        self.assertEqual(self.post({"telefone": CLIENTE, "texto": "oi", "id_tela": "a"})[0], 503)
        self.assertEqual(self.c.envios(), 0)


class TesteSoOPortaoEnvia(unittest.TestCase):
    def test_ninguem_fora_do_portao_chama_enviar(self):
        self.assertEqual(chamadas_proibidas(VENDAS), [])

    def test_a_busca_pega_quem_chamar(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "servico"))
            for nome, texto in (("servico/portao.py", "c.enviar_texto(i, t, x)\n"),
                                ("servico/outro.py", "x = 1\napp.conector.enviar_audio(i, t, c)\n"),
                                ("modulo.py", "getattr(conector, 'enviar_texto')(i, t, x)\n")):
                with open(os.path.join(tmp, nome), "w", encoding="utf-8") as f:
                    f.write(texto)
            self.assertEqual(sorted(chamadas_proibidas(tmp)),
                             ["modulo.py:1", os.path.join("servico", "outro.py") + ":2"])


if __name__ == "__main__":
    unittest.main()
