"""Evolution de outro endereço (VENDAS_EVOLUTION_URL): conta como pronta no motor, na tela (só "Ligar o serviço") e no
gancho (calado), e o serviço recebe esse ambiente. --so-servico sonda a Evolution (só leitura) antes de ligar. Serviço
que já rodava antes de o .env existir = pedir reinício ao dono."""
import sys

sys.dont_write_bytecode = True

import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from servico import evolution_local, pasta, preparo, preparo_evolution, travas  # noqa: E402
from preparo_falso import SistemaFalso  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402

_spec = importlib.util.spec_from_file_location("vendas_inicio_externa", os.path.join(os.path.dirname(AQUI), "scripts",
                                                                                     "inicio.py"))
inicio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inicio)
EXTERNA = {"VENDAS_EVOLUTION_URL": "http://192.168.0.9:8080", "VENDAS_EVOLUTION_CHAVE": "chave-externa-0123456789"}


def mudo(*_a, **_k):
    pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta = pasta.pasta_de_dados(self.projeto, self.base)

    def sistema(self, **k):
        k.setdefault("marca", os.path.basename(self.pasta))
        s = SistemaFalso(**k)
        self.addCleanup(lambda: self.assertEqual(s.inesperados, []))
        return s

    def rodar(self, s, so_servico=False):
        return preparo.Execucao(self.projeto, self.base, sistema=s, avisar=mudo, so_servico=so_servico).rodar()


class TesteExterna(Base):
    def test_motor_externa_pula_docker_e_evolution_e_repassa_o_ambiente(self):
        s = self.sistema(tem=(), ligado=False, ambiente=EXTERNA)
        e = self.rodar(s)
        self.assertEqual(e["estado"], "feito", e)
        self.assertEqual(s.chamadas, [])
        self.assertFalse(os.path.exists(evolution_local.caminho_env(self.pasta)))
        self.assertEqual(len(s.soltos), 1)
        self.assertIn(preparo_evolution.SERVICO, s.soltos[0])
        for k, v in EXTERNA.items():
            self.assertEqual(s.ambientes_soltos[0][k], v)

    def test_so_servico_externa_sonda_o_endereco_configurado(self):
        s = self.sistema(tem=(), ambiente=EXTERNA, evolution_no_ar=True)
        e = self.rodar(s, so_servico=True)
        self.assertEqual(e["estado"], "feito", e)
        self.assertIn(("http://192.168.0.9:8080/instance/fetchInstances", {"apikey": EXTERNA["VENDAS_EVOLUTION_CHAVE"]}),
                      s.pedidos)
        s2 = self.sistema(tem=(), ambiente=EXTERNA, evolution_no_ar=False)
        p = self.rodar(s2, so_servico=True)["passos"][0]
        self.assertEqual(p["estado"], "falhou", p)
        self.assertNotIn("192.168", p["mensagem"])
        self.assertEqual(s2.soltos, [])

    def test_tela_so_oferece_ligar_o_servico(self):
        mod = carregar_modulo()
        mod.preparar._lancados.clear()
        ctx = {"raiz": self.projeto, "config": {"porta": 8790}}
        with mock.patch.dict(os.environ, EXTERNA):
            blocos = mod.montar(ctx, base=self.base)["abas"][0]["blocos"]
            self.assertEqual([b["acao"] for b in blocos], ["ligar_servico"])
            topo, vivo = mod.preparar.topo(ctx, mod.cliente, mod.conexao, self.base, servico_rodando=True,
                                           precisa=True)
            self.assertEqual((topo, vivo), ([], False))

    def test_gancho_calado(self):
        os.makedirs(os.path.join(self.projeto, ".tune-up"))
        with open(os.path.join(self.projeto, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump({"modulos_de_plugins": ["tune-up-vendas@loja:vendas"]}, f)
        entrada = json.dumps({"cwd": self.projeto})
        self.assertEqual(inicio.linha(entrada, base=self.base), inicio.LINHA)
        with mock.patch.dict(os.environ, EXTERNA):
            self.assertEqual(inicio.linha(entrada, base=self.base), "")


class TesteSoServicoSonda(Base):
    def test_evolution_local_parada_nao_liga_o_servico(self):
        evolution_local.preparar(self.projeto, self.base)
        s = self.sistema(tem=(), evolution_no_ar=False)
        p = self.rodar(s, so_servico=True)["passos"][0]
        self.assertEqual(p["estado"], "falhou", p)
        self.assertIn("Clique de novo", p["mensagem"])
        self.assertNotIn("Preparar tudo", p["mensagem"])   # o botão que a tela mostra é "Tentar de novo"
        self.assertEqual((s.chamadas, s.soltos), ([], []))

    def test_evolution_local_no_ar_liga_e_so_le(self):
        evolution_local.preparar(self.projeto, self.base)
        chave = evolution_local.ler_ambiente(self.pasta)["VENDAS_EVOLUTION_CHAVE"]
        s = self.sistema(tem=(), evolution_no_ar=True)
        self.assertEqual(self.rodar(s, so_servico=True)["estado"], "feito")
        self.assertTrue(any(u.endswith("/instance/fetchInstances") and c.get("apikey") == chave for u, c in s.pedidos))
        self.assertEqual(s.chamadas, [])   # nenhum comando: nem pull, nem up


class TesteReinicio(Base):
    def servico_rodando_desde(self, atraso):
        """Serviço vivo (trava ocupada) que começou `atraso` segundos antes de agora."""
        trava = travas.TravaDoProcesso(self.pasta).pegar()
        self.addCleanup(trava.soltar)
        antes = time.time() - atraso
        os.utime(trava.caminho, (antes, antes))

    def test_servico_de_antes_do_env_pede_reinicio(self):
        self.servico_rodando_desde(120)
        s = self.sistema()
        e = self.rodar(s)
        p = [p for p in e["passos"] if p["nome"] == "servico_ligado"][0]
        self.assertEqual(p["estado"], "precisa_do_dono", p)
        self.assertIn("reinici", p["mensagem"].lower())
        self.assertEqual(s.soltos, [])

    def test_servico_de_depois_do_env_esta_feito(self):
        evolution_local.preparar(self.projeto, self.base)
        antes = time.time() - 300
        os.utime(evolution_local.caminho_env(self.pasta), (antes, antes))
        self.servico_rodando_desde(10)
        s = self.sistema()
        self.assertEqual(self.rodar(s)["estado"], "feito")
        self.assertEqual(s.soltos, [])

    def test_pegar_marca_a_hora_em_que_o_servico_comecou(self):
        caminho = os.path.join(self.pasta, travas.ARQUIVO_TRAVA)
        open(caminho, "w").close()
        os.utime(caminho, (1, 1))
        trava = travas.TravaDoProcesso(self.pasta).pegar()
        self.addCleanup(trava.soltar)
        self.assertGreater(os.path.getmtime(caminho), time.time() - 60)


BOTOES = ("Preparar tudo", "Tentar de novo", "Já fiz, continuar", "Ligar o serviço")


class TesteSemCiclo(Base):
    """"Ligar o serviço" nunca prende o dono: a sonda espera a Evolution subir, e depois de uma falha a tela mostra o
    cartão de preparar, com um texto que só cita o botão que está na tela."""

    def citados(self, bloco):
        return [b for b in BOTOES if b in bloco["descricao"] and b != bloco["botao"]]

    def test_sonda_espera_a_evolution_subir(self):
        evolution_local.preparar(self.projeto, self.base)
        s = self.sistema(tem=(), evolution_no_ar=False)
        original, sondas = s.http, []

        def http(url, tempo=5, cabecalhos=None):
            if url.endswith("/instance/fetchInstances"):
                sondas.append(url)
                s.evolution_no_ar = len(sondas) >= 3   # responde na 3ª sondagem (subindo depois de reiniciar)
            return original(url, tempo, cabecalhos)
        s.http = http
        e = self.rodar(s, so_servico=True)
        self.assertEqual(e["estado"], "feito", e)
        self.assertEqual(len(sondas), 3)
        self.assertEqual(len(s.soltos), 1)
        self.assertEqual(s.chamadas, [])

    def test_sonda_que_nunca_responde_falha_depois_da_espera(self):
        evolution_local.preparar(self.projeto, self.base)
        s = self.sistema(tem=(), evolution_no_ar=False)
        p = self.rodar(s, so_servico=True)["passos"][0]
        self.assertEqual(p["estado"], "falhou")
        self.assertGreaterEqual(s.agora, preparo_evolution.ESPERA_SONDA)
        self.assertEqual(s.soltos, [])

    def test_tela_depois_da_falha_na_sonda_mostra_preparar(self):
        evolution_local.preparar(self.projeto, self.base)
        self.rodar(self.sistema(tem=(), evolution_no_ar=False), so_servico=True)   # a mensagem real do motor
        escuta = socket.socket()
        self.addCleanup(escuta.close)
        escuta.bind(("127.0.0.1", 0))
        escuta.listen(1)                                  # a porta abre, mas a Evolution não responde
        caminho = preparo.caminhos(self.pasta)["estado"]
        with open(caminho, encoding="utf-8") as f:
            estado = json.load(f)
        estado["portas"]["evolution"] = escuta.getsockname()[1]
        travas.gravar_segredo(caminho, json.dumps(estado))
        mod = carregar_modulo()
        mod.preparar._lancados.clear()
        blocos = mod.montar({"raiz": self.projeto, "config": {"porta": 8790}}, base=self.base)["abas"][0]["blocos"]
        self.assertEqual([(b["acao"], b["botao"]) for b in blocos], [("preparar_tudo", "Tentar de novo")])
        self.assertEqual(self.citados(blocos[0]), [])

    def test_falha_ao_comecar_nao_cita_botao_ausente(self):
        mod = carregar_modulo()

        class NaoSolta(SistemaFalso):
            def soltar(self, args, caminho_log, pasta=None):
                raise PermissionError(13, "Permission denied")
        estado = preparo.iniciar(preparo.argumentos(["iniciar", "--projeto", self.projeto, "--base", self.base]),
                                 NaoSolta())
        for bloco in (mod.preparar.bloco_preparar(estado), mod.preparar.bloco_ligar(estado)):
            self.assertEqual(self.citados(bloco), [], bloco)
        with mock.patch.dict(os.environ, EXTERNA):
            blocos = mod.montar({"raiz": self.projeto, "config": {"porta": 8790}}, base=self.base)["abas"][0]["blocos"]
        self.assertEqual([self.citados(b) for b in blocos], [[]])


if __name__ == "__main__":
    unittest.main()
