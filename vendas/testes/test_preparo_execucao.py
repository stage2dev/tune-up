"""Preparo: estado e log 0600 fora do projeto e sem segredo, um preparo por projeto, iniciar destacado, processo
morto = interrompido e retomada, e o Sistema de verdade (comandos com tempo limite, processo solto, HTTP local)."""
import sys

sys.dont_write_bytecode = True

import http.server  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from contextlib import redirect_stdout  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from servico import evolution_local, pasta, preparo, preparo_evolution, preparo_sistema, travas  # noqa: E402
from preparo_falso import SistemaFalso  # noqa: E402


def mudo(*_a, **_k):
    pass


def ler(caminho):
    with open(caminho, encoding="utf-8") as f:
        return f.read()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta_dados = pasta.caminho_da_pasta(self.projeto, self.base)
        self.arquivos = preparo.caminhos(self.pasta_dados)

    def sistema(self, **k):
        k.setdefault("marca", os.path.basename(self.pasta_dados))
        return SistemaFalso(**k)

    def args(self, comando="rodar"):
        return preparo.argumentos([comando, "--projeto", self.projeto, "--base", self.base])


class TesteEstadoELog(Base):
    def test_estado_e_log_0600_fora_do_projeto_sem_a_chave(self):
        self.assertEqual(preparo.rodar(self.args(), self.sistema(), mudo), 0)
        chave = evolution_local.ler_ambiente(self.pasta_dados)["VENDAS_EVOLUTION_CHAVE"]
        senha = evolution_local._ler_env(evolution_local.caminho_env(self.pasta_dados))["POSTGRES_PASSWORD"]
        self.assertEqual(os.listdir(self.projeto), [])
        for nome in ("estado", "log"):
            caminho = self.arquivos[nome]
            self.assertFalse(caminho.startswith(self.projeto + os.sep))
            texto = ler(caminho)
            self.assertNotIn(chave, texto)
            self.assertNotIn(senha, texto)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(os.stat(caminho).st_mode), 0o600)
        estado = json.loads(ler(self.arquivos["estado"]))
        self.assertEqual(estado["estado"], "feito")
        self.assertEqual(estado["pid"], os.getpid())
        for campo in ("id", "inicio", "atualizado", "fim", "passos"):
            self.assertTrue(estado[campo])
        self.assertEqual([p["nome"] for p in estado["passos"]], [n for n, _, _ in preparo.PASSOS])

    def test_rodar_com_preparo_vivo_sai_com_3_sem_mexer(self):
        os.makedirs(self.pasta_dados, exist_ok=True)
        trava = travas.TravaDoProcesso(self.pasta_dados, preparo.ARQUIVO_TRAVA).pegar()
        self.addCleanup(trava.soltar)
        s = self.sistema()
        erro = io.StringIO()
        self.assertEqual(preparo.rodar(self.args(), s, lambda *a, **k: print(*a, file=erro)), 3)
        self.assertEqual(s.chamadas, [])
        self.assertFalse(os.path.exists(self.arquivos["estado"]))

    def test_pid_morto_vira_interrompido_e_a_proxima_retoma(self):
        s = self.sistema(evolution_no_ar=False)
        self.assertEqual(preparo.rodar(self.args(), s, mudo), 0)
        morto = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], stdout=subprocess.PIPE,
                               check=True)
        estado = json.loads(ler(self.arquivos["estado"]))
        estado.update(estado="rodando", pid=int(morto.stdout.decode().strip()), fim=None)
        estado["passos"][4].update(estado="rodando", mensagem=None)
        travas.gravar_segredo(self.arquivos["estado"], json.dumps(estado))
        lido = preparo.ler_estado(self.pasta_dados)
        self.assertEqual(lido["estado"], "interrompido")
        self.assertEqual(lido["passos"][4]["estado"], "falhou")
        s.chamadas, s.soltos, s.servico_no_ar = [], [], False
        self.assertEqual(preparo.rodar(self.args(), s, mudo), 0)
        self.assertFalse(any("pull" in c or "up" in c for c in s.chamadas))
        self.assertEqual(s.instaladores(), [])
        self.assertEqual(len(s.soltos), 1)
        self.assertEqual(preparo.ler_estado(self.pasta_dados)["estado"], "feito")

    def test_cli_estado_e_porta_invalida(self):
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(preparo.main(["estado", "--projeto", self.projeto, "--base", self.base]), 0)
        self.assertEqual(json.loads(saida.getvalue())["estado"], "nunca_rodou")
        self.assertFalse(os.path.exists(self.pasta_dados))
        self.assertEqual(preparo.main(["rodar", "--projeto", self.projeto, "--porta", "80"], avisar=mudo), 2)
        self.assertEqual(preparo.main(["rodar", "--projeto", os.path.join(self.tmp, "nao"), "--base", self.base],
                                      self.sistema(), mudo), 2)

    def test_pasta_de_dados_dentro_do_projeto_recusada(self):
        args = preparo.argumentos(["rodar", "--projeto", self.projeto, "--base", os.path.join(self.projeto, "d")])
        self.assertEqual(preparo.rodar(args, self.sistema(), mudo), 2)
        self.assertEqual(os.listdir(self.projeto), [])


class Concorrente(SistemaFalso):
    """soltar() do preparo vira uma thread que roda preparo.rodar com este mesmo sistema; relógio de verdade."""

    def __init__(self, **k):
        super().__init__(**k)
        self.portao = threading.Event()
        self.corridas = []

    def relogio(self):
        return time.monotonic()

    def dormir(self, segundos):
        time.sleep(min(segundos, 0.05))

    def achar(self, nome):
        self.portao.wait(10)   # segura o preparo no 1º passo até o teste soltar
        return super().achar(nome)

    def soltar(self, args, caminho_log, pasta=None):
        if not args[2].endswith("preparo.py"):
            return super().soltar(args, caminho_log, pasta)
        self.soltos.append(list(args))
        corrida = {"codigo": None}

        def correr():
            corrida["codigo"] = preparo.rodar(preparo.argumentos(args[3:]), self, mudo)
        corrida["thread"] = threading.Thread(target=correr)
        self.corridas.append(corrida)
        corrida["thread"].start()

        class Proc:
            def poll(self):
                return corrida["codigo"]
        return Proc()


class TesteIniciar(Base):
    def test_dois_iniciar_ao_mesmo_tempo_um_preparo_so(self):
        s = Concorrente(marca=os.path.basename(self.pasta_dados))
        respostas = []
        ts = [threading.Thread(target=lambda: respostas.append(preparo.iniciar(self.args("iniciar"), s)))
              for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(20)
        self.assertEqual(len(respostas), 2)
        self.assertEqual(respostas[0]["id"], respostas[1]["id"])
        self.assertEqual(respostas[0]["estado"], "rodando")
        terceiro = preparo.iniciar(self.args("iniciar"), s)   # um vivo já roda: devolve o dele, não solta outro
        self.assertEqual(terceiro["id"], respostas[0]["id"])
        soltos = len(s.soltos)
        s.portao.set()
        for c in s.corridas:
            c["thread"].join(20)
        self.assertEqual(soltos, len(s.corridas))
        self.assertEqual(sorted(c["codigo"] for c in s.corridas), [0] + [3] * (len(s.corridas) - 1))
        self.assertEqual(ler(self.arquivos["log"]).count("começou"), 1)
        self.assertEqual(preparo.ler_estado(self.pasta_dados)["estado"], "feito")
        argv = s.soltos[0]
        self.assertEqual(argv[:4], [sys.executable, "-B", os.path.abspath(preparo.__file__), "rodar"])


    def test_iniciar_que_morre_antes_de_comecar_nao_devolve_o_estado_velho(self):
        self.assertEqual(preparo.rodar(self.args(), self.sistema(), mudo), 0)
        velho = preparo.ler_estado(self.pasta_dados)["id"]

        class Morre(SistemaFalso):
            def soltar(self, args, caminho_log, pasta=None):
                self.soltos.append(list(args))

                class Proc:
                    def poll(self):
                        return 2
                return Proc()
        s = Morre()
        r = preparo.iniciar(self.args("iniciar"), s)
        self.assertEqual(r["estado"], "falhou")
        self.assertNotEqual(r.get("id"), velho)
        self.assertEqual(len(s.soltos), 1)


class Evolution(http.server.BaseHTTPRequestHandler):
    chave = None

    def do_GET(self):
        ok = self.path == "/instance/fetchInstances" and self.headers.get("apikey") == self.chave
        corpo = b"[]" if ok else b'{"status":401}'
        self.send_response(200 if ok else 401)
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def log_message(self, *_):
        pass


class TesteSistemaDeVerdade(Base):
    def test_rodar_codigo_saida_tempo_limite_e_programa_ausente(self):
        s = preparo_sistema.Sistema()
        self.assertEqual(s.rodar([sys.executable, "-c", "print('oi'); import sys; sys.exit(3)"], 30),
                         (3, "oi" + os.linesep if os.name == "nt" else "oi\n"))
        codigo, saida = s.rodar([sys.executable, "-c", "import time; time.sleep(10)"], 0.5)
        self.assertIsNone(codigo)
        self.assertIn("tempo limite", saida)
        self.assertIsNone(s.rodar([os.path.join(self.tmp, "nao-existe")], 5)[0])

    def test_caminho_estendido_por_sistema(self):
        mac = preparo_sistema.Sistema(plataforma="darwin", ambiente={"PATH": "/x"})
        self.assertIn("/opt/homebrew/bin", mac.caminho.split(os.pathsep))
        self.assertEqual(mac.ambiente["PATH"], mac.caminho)
        win = preparo_sistema.Sistema(plataforma="win32", ambiente={"PATH": "", "ProgramFiles": "C:\\PF"})
        self.assertIn(os.path.join("C:\\PF", "Docker", "Docker", "resources", "bin"), win.caminho)

    def test_soltar_grava_no_log_0600_e_pid_vivo(self):
        os.makedirs(self.pasta_dados, exist_ok=True)
        log = self.arquivos["log"]
        processo = preparo_sistema.Sistema().soltar([sys.executable, "-c", "print('solto')"], log)
        self.assertTrue(preparo_sistema.pid_vivo(os.getpid()))
        processo.wait(30)
        self.assertIn("solto", ler(log))
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(log).st_mode), 0o600)
        self.assertFalse(preparo_sistema.pid_vivo(processo.pid))
        self.assertFalse(preparo_sistema.pid_vivo(None))

    def test_evolution_falsa_em_127_responde_pelo_http_de_verdade(self):
        servidor = http.server.HTTPServer(("127.0.0.1", 0), Evolution)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        porta = servidor.server_address[1]
        evolution_local.preparar(self.projeto, self.base, porta_evolution=porta)
        Evolution.chave = evolution_local.ler_ambiente(self.pasta_dados)["VENDAS_EVOLUTION_CHAVE"]
        self.addCleanup(setattr, Evolution, "chave", None)

        class HttpDeVerdade(SistemaFalso):
            http = preparo_sistema.Sistema.http
            porta_livre = preparo_sistema.Sistema.porta_livre
        s = HttpDeVerdade(marca=os.path.basename(self.pasta_dados))
        ex = preparo.Execucao(self.projeto, self.base, sistema=s, avisar=mudo)
        r = preparo_evolution.evolution_no_ar(ex)
        self.assertEqual(r["estado"], "feito", r)
        self.assertEqual(s.chamadas, [])   # já respondia com a nossa chave: nem pull nem up

    def test_outro_servidor_http_na_porta_vira_precisa_do_dono(self):
        class Estranho(Evolution):
            def do_GET(self):
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
        servidor = http.server.HTTPServer(("127.0.0.1", 0), Estranho)
        threading.Thread(target=servidor.serve_forever, daemon=True).start()
        self.addCleanup(servidor.server_close)
        self.addCleanup(servidor.shutdown)
        porta = servidor.server_address[1]
        evolution_local.preparar(self.projeto, self.base, porta_evolution=porta)

        class HttpDeVerdade(SistemaFalso):
            http = preparo_sistema.Sistema.http
            porta_livre = preparo_sistema.Sistema.porta_livre
        s = HttpDeVerdade()
        r = preparo_evolution.evolution_no_ar(preparo.Execucao(self.projeto, self.base, sistema=s, avisar=mudo))
        self.assertEqual(r["estado"], "precisa_do_dono", r)
        self.assertIn(str(porta), r["comando"])
        self.assertEqual(s.chamadas, [])   # nada de pull nem up contra o programa de outro

    def test_porta_fechada_nao_responde_e_falha_com_espera_limitada(self):
        livre = preparo_sistema.Sistema().porta_qualquer()
        self.assertEqual(preparo_sistema.Sistema().http("http://127.0.0.1:%d/" % livre, 2), (None, b""))
        evolution_local.preparar(self.projeto, self.base, porta_evolution=livre)

        class HttpDeVerdade(SistemaFalso):
            http = preparo_sistema.Sistema.http
        s = HttpDeVerdade()
        s.evolution_sobe = False
        r = preparo_evolution.evolution_no_ar(preparo.Execucao(self.projeto, self.base, sistema=s, avisar=mudo))
        self.assertEqual(r["estado"], "falhou")
        self.assertGreaterEqual(s.dormido, preparo_evolution.ESPERA_EVOLUTION - preparo_sistema.INTERVALO_S)


if __name__ == "__main__":
    unittest.main()
