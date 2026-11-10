"""Ações de módulo sob concorrência e regras de negar que fecham na dúvida. Nada chama o claude.

Os testes trocam montar/agir do módulo carregado por funções com Event: sem sleep, sem sorte.
"""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import queue  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import modulos  # noqa: E402
from test_modulos import escrever, esperar_threads, pacote_loja  # noqa: E402


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cfg = pacote_loja(self.tmp)
        self.cfg["modulos"] = ["loja"]
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)
        esperar_threads()
        self.addCleanup(esperar_threads)
        self.mod = modulos.carregar(self.cfg, "loja")
        self.solta = threading.Event()
        self.addCleanup(self.solta.set)  # nenhuma thread fica presa se um teste falhar
        self.chamadas = []

    def agir_preso(self, ctx, acao, dados):
        self.chamadas.append(acao)
        self.solta.wait(5)
        return {"feito": acao}


class TesteConcorrencia(Base):
    def test_cliques_juntos_rodam_uma_vez_so(self):  # achado 1
        n = 8
        self.mod.agir = self.agir_preso
        largada, saida = threading.Barrier(n), queue.Queue()

        Thread = threading.Thread

        class Lenta(Thread):  # alarga a janela entre reservar a vaga e começar a thread;
            def start(self):  # o resultado certo não depende dessa espera, só o código velho cai
                threading.Event().wait(0.1)
                Thread.start(self)

        troca = mock.patch.object(modulos.threading, "Thread", Lenta)

        def clicar():
            largada.wait(5)
            saida.put(modulos.agir(self.cfg, "loja", "salvar", {"id_cliente": "m1"}))

        ts = [threading.Thread(target=clicar, daemon=True) for _ in range(n)]
        with troca:
            for t in ts:
                t.start()
            recusas = [saida.get(timeout=5)[0] for _ in range(n - 1)]  # só uma fica presa em agir
        self.assertEqual(recusas, [409] * (n - 1))
        self.solta.set()
        self.assertEqual(saida.get(timeout=5)[0], 200)
        for t in ts:
            t.join(5)
        self.assertEqual(self.chamadas, ["salvar"])
        self.assertNotIn("loja", modulos._agindo)  # a vaga foi solta
        self.assertEqual(modulos.agir(self.cfg, "loja", "salvar", {})[0], 200)

    def test_tempo_limite_diz_que_segue_e_o_fim_tardio_apaga_o_cache(self):  # achado 2
        self.assertEqual(modulos.montar(self.cfg, "loja")[0], 200)
        self.assertEqual(self.mod.MONTAR[0], 1)
        self.mod.agir = self.agir_preso
        cod, d = modulos.agir(self.cfg, "loja", "salvar", {}, tempo=0.05)
        self.assertEqual(cod, 504)
        self.assertEqual(d["erro"], "A ação ainda está rodando. Não repita; atualize a tela para ver o resultado.")
        t = modulos._agindo["loja"]
        self.assertEqual(modulos.agir(self.cfg, "loja", "salvar", {})[0], 409)  # ainda rodando
        self.solta.set()
        t.join(5)
        modulos.montar(self.cfg, "loja")
        self.assertEqual(self.mod.MONTAR[0], 2)  # a ação tardia apagou o cache da tela
        self.assertNotIn("loja", modulos._agindo)

    def test_montar_em_voo_nao_grava_cache_velho(self):  # achado 5
        entrou, segura, original = threading.Event(), threading.Event(), self.mod.montar
        self.addCleanup(segura.set)

        def montar_lento(ctx):
            if not entrou.is_set():
                entrou.set()
                segura.wait(5)
            return original(ctx)

        self.mod.montar = montar_lento
        t = threading.Thread(target=modulos.montar, args=(self.cfg, "loja"), kwargs={"usar_cache": False})
        t.start()
        self.assertTrue(entrou.wait(5))
        self.assertEqual(modulos.agir(self.cfg, "loja", "salvar", {})[0], 200)
        segura.set()
        t.join(5)
        antes = self.mod.MONTAR[0]
        modulos.montar(self.cfg, "loja")
        self.assertEqual(self.mod.MONTAR[0], antes + 1)  # o resultado de antes da ação não ficou no cache

    def test_resposta_estranha_e_200_com_aviso_e_apaga_cache(self):  # achado 6
        modulos.montar(self.cfg, "loja")
        for volta, estranho in enumerate(([1, 2], {"x": {1, 2}}, {"x": float("nan")}, None), start=2):
            self.mod.agir = lambda ctx, acao, dados, r=estranho: r
            cod, d = modulos.agir(self.cfg, "loja", "salvar", {})
            self.assertEqual((cod, d["ok"], d["resultado"]), (200, True, {}), estranho)
            self.assertIn("resposta inesperada", d["avisos"][0])
            modulos.montar(self.cfg, "loja")
            self.assertEqual(self.mod.MONTAR[0], volta)


class TesteNegarFechado(Base):
    """Achados 3 e 4: módulo ligado com problema barra o disparo, com o id dele no texto."""

    def lancador(self):
        import lancador
        from test_lancador import ACOES_TESTE, ESTADO, CLIFalso
        escrever(os.path.join(self.tmp, "acoes", "t.json"), json.dumps(ACOES_TESTE))
        self.cfg.update(acoes_dir=os.path.join(self.tmp, "acoes"), claude_bin="claude", max_execucoes=3)
        self.cli = CLIFalso()
        return lancador.Lancador(self.cfg, lambda: ESTADO, rodar=self.cli, plataforma="darwin")

    def disparos(self):
        return [c for c, _ in self.cli.chamadas if c[1:2] == ["--bg"]]

    def modulo(self, mid, texto):
        escrever(os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos", mid, "modulo.py"), texto)
        self.cfg["modulos"] = ["loja", mid]

    def recusa(self, lanc, mid):
        import lancador
        with self.assertRaises(lancador.ErroAcao) as e:
            lanc.iniciar("t.leve", {})
        self.assertEqual(e.exception.codigo, 409)
        self.assertEqual(e.exception.mensagem, "A tela %s não carregou; corrija ou desligue-a em painel.json "
                                               "antes de rodar ações." % mid)
        self.assertEqual(self.disparos(), [])

    def test_modulo_quebrado_ou_negar_ruim_barra(self):
        lanc = self.lancador()
        for mid, texto in (("sintaxe", "INFO = {\n"),
                           ("uma_ruim", 'INFO = {"negar": ["Bash(rm:*)", ""]}\n'),
                           ("objeto", 'INFO = {"negar": [{"ferramenta": "x"}]}\n'),
                           ("nao_lista", 'INFO = {"negar": "Bash(*)"}\n')):
            self.modulo(mid, texto)
            self.recusa(lanc, mid)
        self.cfg["modulos"] = ["loja", "sumido"]  # ligado em painel.json, sem arquivo
        self.recusa(lanc, "sumido")

    def test_sem_montar_vale_e_sem_negar_vale(self):
        lanc = self.lancador()
        self.modulo("so_regras", 'INFO = {"negar": ["mcp__x__enviar"]}\n')  # sem montar()
        lanc.iniciar("t.leve", {})
        deny = json.loads(self.disparos()[-1][self.disparos()[-1].index("--settings") + 1])["permissions"]["deny"]
        self.assertIn("mcp__x__enviar", deny)
        self.assertIn("Bash(rm -rf *)", deny)
        self.modulo("sem_negar", "def montar(ctx):\n    return {}\n")
        lanc.iniciar("t.parte", {"fase": "187", "parte": "C"})
        self.assertEqual(len(self.disparos()), 2)

    def test_import_que_trava_recusa_no_tempo_e_fora_das_travas(self):
        portao = types.ModuleType("portao_teste_negar")
        portao.EV = threading.Event()
        sys.modules["portao_teste_negar"] = portao
        self.addCleanup(sys.modules.pop, "portao_teste_negar", None)
        self.addCleanup(portao.EV.set)
        self.modulo("trava", "import portao_teste_negar\nportao_teste_negar.EV.wait(10)\nINFO = {}\n")
        lanc = self.lancador()
        livre = {}
        original = modulos.regras_de_negar

        def espiar(cfg, tempo=None):  # durante a leitura, outra thread pega as travas do lançador
            def tentar():
                livre["painel"] = lanc._trava.acquire(blocking=False)
                if livre["painel"]:
                    lanc._trava.release()
            t = threading.Thread(target=tentar)
            t.start()
            t.join(5)
            return original(cfg, tempo)

        with mock.patch.object(modulos, "TEMPO_LIMITE", 0.2), mock.patch.object(modulos, "regras_de_negar", espiar):
            self.recusa(lanc, "trava")
        self.assertEqual(livre, {"painel": True})
        portao.EV.set()


if __name__ == "__main__":
    unittest.main()
