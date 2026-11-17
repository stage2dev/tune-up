"""Preparo vivo = trava preparo.trava OCUPADA (um pid vivo não basta: o número pode ter sido reaproveitado), no motor,
na tela e no gancho; e uma falha ao COMEÇAR o preparo vira estado "falhou" com um motivo simples."""
import sys

sys.dont_write_bytecode = True

import importlib.util  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from servico import pasta, preparo, travas  # noqa: E402
from preparo_falso import SistemaFalso  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402

_spec = importlib.util.spec_from_file_location("vendas_inicio_trava", os.path.join(os.path.dirname(AQUI), "scripts",
                                                                                   "inicio.py"))
inicio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inicio)
NOMES = [n for n, _, _ in preparo.PASSOS]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta = pasta.pasta_de_dados(self.projeto, self.base)

    def rodando(self, pid=None):
        """Estado "rodando" com um pid VIVO (o deste teste), como se o número tivesse sido reaproveitado."""
        passos = [{"nome": n, "titulo": n, "estado": "rodando" if i == 1 else ("feito" if i < 1 else "pendente"),
                   "mensagem": None, "comando": None, "detalhe": None} for i, n in enumerate(NOMES)]
        with open(os.path.join(self.pasta, "preparo.json"), "w", encoding="utf-8") as f:
            json.dump({"id": "velho", "pid": pid or os.getpid(), "estado": "rodando", "passos": passos}, f)

    def segurar(self):
        trava = travas.TravaDoProcesso(self.pasta, preparo.ARQUIVO_TRAVA).pegar()
        self.addCleanup(trava.soltar)
        return trava

    def args(self, *extra):
        return preparo.argumentos(["iniciar", "--projeto", self.projeto, "--base", self.base] + list(extra))


class TesteVivoPelaTrava(Base):
    def test_motor_pid_vivo_com_trava_livre_e_interrompido(self):
        self.rodando()
        self.assertEqual(preparo.ler_estado(self.pasta)["estado"], "interrompido")
        self.segurar()
        self.assertEqual(preparo.ler_estado(self.pasta)["estado"], "rodando")

    def test_iniciar_com_trava_livre_recomeca(self):
        self.rodando()
        s = SistemaFalso()
        preparo.iniciar(self.args(), s)
        self.assertEqual(len(s.soltos), 1)   # não devolveu o "rodando" velho

    def test_tela_pid_vivo_com_trava_livre_oferece_tentar_de_novo(self):
        mod = carregar_modulo()
        mod.preparar._lancados.clear()
        self.rodando()
        ctx = {"raiz": self.projeto, "config": {"porta": 8790}}
        blocos = mod.montar(ctx, base=self.base)["abas"][0]["blocos"]
        self.assertEqual([b.get("botao") for b in blocos], ["Tentar de novo"])
        self.segurar()
        self.assertEqual([b["tipo"] for b in mod.montar(ctx, base=self.base)["abas"][0]["blocos"]], ["lista"])

    def test_gancho_pid_vivo_com_trava_livre_avisa(self):
        os.makedirs(os.path.join(self.projeto, ".tune-up"))
        with open(os.path.join(self.projeto, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump({"modulos_de_plugins": ["tune-up-vendas@loja:vendas"]}, f)
        self.rodando()
        entrada = json.dumps({"cwd": self.projeto})
        self.assertEqual(inicio.linha(entrada, base=self.base), inicio.LINHA)
        self.segurar()
        self.assertEqual(inicio.linha(entrada, base=self.base), "")

    def test_ocupada_nao_cria_o_arquivo(self):
        self.assertFalse(travas.ocupada(self.pasta, preparo.ARQUIVO_TRAVA))
        self.assertFalse(os.path.exists(os.path.join(self.pasta, preparo.ARQUIVO_TRAVA)))


class TesteFalhaAoComecar(Base):
    def test_soltar_que_falha_grava_falhou_com_motivo(self):
        class NaoSolta(SistemaFalso):
            def soltar(self, args, caminho_log, pasta=None):
                raise PermissionError(13, "Permission denied")
        r = preparo.iniciar(self.args(), NaoSolta())
        self.assertEqual(r["estado"], "falhou")
        gravado = preparo.ler_estado(self.pasta)
        self.assertEqual(gravado["estado"], "falhou")
        self.assertIn("não começou", gravado["mensagem"])
        self.assertNotIn(self.pasta, gravado["mensagem"])

    def test_processo_que_morre_antes_grava_falhou(self):
        class Morre(SistemaFalso):
            def soltar(self, args, caminho_log, pasta=None):
                class Proc:
                    def poll(self):
                        return 2
                return Proc()
        preparo.iniciar(self.args(), Morre())
        self.assertEqual(preparo.ler_estado(self.pasta)["estado"], "falhou")

    def test_tela_mostra_o_motivo_e_tentar_de_novo(self):
        mod = carregar_modulo()
        mod.preparar._lancados.clear()

        def nao_solta(argv, log):
            raise PermissionError(13, "Permission denied")
        mod.preparar.soltar = nao_solta
        ctx = {"raiz": self.projeto, "config": {"porta": 8790}}
        r = mod.agir(ctx, "preparar_tudo", {}, base=self.base)
        self.assertFalse(r["ok"])
        b = mod.montar(ctx, base=self.base)["abas"][0]["blocos"][0]
        self.assertEqual((b["acao"], b["botao"]), ("preparar_tudo", "Tentar de novo"))
        self.assertIn("não começou", b["descricao"])
        self.assertNotIn(self.pasta, json.dumps(b, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
