"""Endurecimento da mídia recebida (revisão de M1): o trabalhador sobrevive a banco ocupado e sobe de novo se morrer;
arquivo nunca fica sem linha (UPDATE que falha, .tmp de queda, órfão na subida); webhook sem segredo não guarda chave
e não deixa pedir de novo; 400 da Evolution só é expirada com o sinal no corpo; ffprobe recebe o formato (-f)."""
import sys

sys.dont_write_bytecode = True

import base64  # noqa: E402
import os  # noqa: E402
import sqlite3  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import midia  # noqa: E402
from servico.conectores import base  # noqa: E402
from testes.test_midia import OGG, Base, corpo  # noqa: E402
from testes import test_midia_rota as rota  # noqa: E402
from testes.test_midia_rota import INST, PDF, EvolutionFalsa  # noqa: E402

PASSOS = 400   # esperas por condição (0,02 s cada): nada depende do relógio, só de o estado chegar


def esperar(condicao):
    for _ in range(PASSOS):
        if condicao():
            return True
        time.sleep(0.02)
    return condicao()


class ConexaoQueFalha:
    """Conexão de verdade que levanta no UPDATE para 'pronta' (banco ocupado no meio do download)."""

    def __init__(self, con):
        self._con = con

    def execute(self, sql, *args):
        if sql.startswith("UPDATE midias SET estado = 'pronta'"):
            raise sqlite3.OperationalError("database is locked")
        return self._con.execute(sql, *args)

    def __getattr__(self, nome):
        return getattr(self._con, nome)


class TesteTrabalhador(Base):
    def iniciar(self, abrir):
        parar = threading.Event()
        self.addCleanup(parar.set)
        b = midia.Baixador(abrir, lambda: self.c, self.pasta)
        midia.registrar_baixador(b)
        return b, parar

    def test_banco_ocupado_na_limpeza_nao_mata_o_trabalhador(self):
        chamadas = []

        def abrir():
            chamadas.append(1)
            if len(chamadas) == 1:   # a 1ª abertura (limpeza da subida) acha o banco ocupado
                raise sqlite3.OperationalError("database is locked")
            return self.abrir()
        b, parar = self.iniciar(abrir)
        b.iniciar(parar)
        self.assertTrue(esperar(lambda: len(chamadas) >= 1))
        mid = self.chegou("W1")
        self.assertTrue(esperar(lambda: self.linha(mid)["estado"] == "pronta"), self.linha(mid)["estado"])
        self.assertTrue(b._fio.is_alive())

    def test_trabalhador_morto_sobe_de_novo_ao_enfileirar(self):
        b, parar = self.iniciar(self.abrir)
        with mock.patch.object(b, "_rodar", lambda _parar: None):   # a thread termina na hora (morre)
            b.iniciar(parar).join(5)
        self.assertFalse(b._fio.is_alive())
        mid = self.chegou("W2")
        self.assertTrue(esperar(lambda: self.linha(mid)["estado"] == "pronta"), self.linha(mid)["estado"])

    def test_trabalhador_morto_com_o_servico_parando_vira_falhou(self):
        b, parar = self.iniciar(self.abrir)
        with mock.patch.object(b, "_rodar", lambda _parar: None):
            b.iniciar(parar).join(5)
        parar.set()
        mid = self.chegou("W3")
        self.assertEqual((self.linha(mid)["estado"], self.linha(mid)["motivo"]), ("falhou", "sem_baixador"))


class TesteOrfaos(Base):
    def test_update_que_falha_apaga_o_arquivo(self):
        mid = self.chegou("U1")
        with self.assertRaises(sqlite3.OperationalError):
            midia.baixar(lambda: ConexaoQueFalha(self.abrir()), self.c, self.pasta, mid)
        self.assertEqual(self.arquivos(), [])
        self.assertEqual(self.linha(mid)["estado"], "pendente")

    def test_subida_apaga_tmp_e_arquivo_sem_linha(self):
        mid = self.chegou("U2")
        self.assertEqual(self.baixar(mid), "pronta")
        guardado = midia.caminho_do_arquivo(self.pasta, self.linha(mid)["arquivo"])
        pasta = os.path.dirname(guardado)
        sobras = [os.path.join(pasta, "a" * 32 + ".tmp"), os.path.join(pasta, "b" * 32)]
        outra = os.path.join(self.pasta, "midia", "999")
        os.makedirs(outra)
        sobras.append(os.path.join(outra, "c" * 32))
        for caminho in sobras:
            with open(caminho, "wb") as f:
                f.write(b"x")
        fora = os.path.join(self.pasta, "nao-mexer.txt")   # fora de midia/: nunca tocado
        with open(fora, "wb") as f:
            f.write(b"x")
        self.assertEqual(midia.orfaos(self.con, self.pasta), 3)
        self.assertEqual(self.arquivos(), [guardado])
        self.assertTrue(os.path.exists(fora))
        with open(os.path.join(os.path.dirname(AQUI), "servico", "servico.py"), encoding="utf-8") as f:
            self.assertIn("midia.orfaos(con, pasta_dados)", f.read())   # a subida chama a limpeza


class TesteForjado(Base):
    def test_sem_segredo_nao_guarda_chave_e_nao_pede_de_novo(self):
        b = midia.Baixador(self.abrir, lambda: self.c, self.pasta)
        midia.registrar_baixador(b)
        self.c.midias["F1"] = (OGG, "audio/ogg", None)
        self.receber(corpo("F1"), segredo_ok=False)
        linha = self.con.execute("SELECT id, chave, estado, motivo FROM midias").fetchone()
        self.assertEqual((linha["chave"], linha["estado"], linha["motivo"]), (None, "falhou", "sem_segredo"))
        self.assertFalse(midia.pedir_de_novo(self.con, linha["id"]))   # a rota responde 409
        self.assertEqual(self.linha(linha["id"])["estado"], "falhou")
        self.assertTrue(b.fila.empty())
        self.assertNotIn("baixar_midia", [c[0] for c in self.c.chamadas])


class TesteFfprobe(unittest.TestCase):
    def test_formato_detectado_vai_em_f(self):
        feito = subprocess.CompletedProcess([], 0, stdout=b"12.34\n")
        with mock.patch.object(midia.shutil, "which", return_value="/x/ffprobe"), \
                mock.patch.object(midia.subprocess, "run", return_value=feito) as run:
            self.assertEqual(midia.duracao("/a/b", "audio/ogg"), 12.3)
            args = run.call_args[0][0]
            self.assertEqual(args[args.index("-f") + 1], "ogg")
            self.assertEqual(args[-1], "/a/b")
            for mime, formato in (("audio/mpeg", "mp3"), ("audio/mp4", "mp4"), ("audio/wav", "wav"),
                                  ("audio/aac", "aac")):
                midia.duracao("/a/b", mime)
                args = run.call_args[0][0]
                self.assertEqual(args[args.index("-f") + 1], formato)
            run.reset_mock()
            self.assertIsNone(midia.duracao("/a/b", "text/html"))   # fora da lista: nem roda
            self.assertIsNone(midia.duracao("/a/b"))
            run.assert_not_called()


class TesteEvolution400(unittest.TestCase):
    setUp = rota.TesteConectorEvolution.setUp   # o mesmo servidor falso, sem rodar os testes de lá de novo

    def resposta(self, mensagem):
        return 400, {"status": 400, "error": "Bad Request", "response": {"message": [mensagem]}}

    def test_400_passageiro_tenta_uma_vez_mais(self):
        EvolutionFalsa.respostas = [self.resposta("Error: Connection Closed"),
                                    (200, {"base64": base64.b64encode(PDF).decode()})]
        self.assertEqual(self.evo.baixar_midia(INST, self.chave)[0], PDF)
        self.assertEqual(len(EvolutionFalsa.pedidos), 2)
        EvolutionFalsa.respostas = [self.resposta("Error: Timed Out"), self.resposta("Error: Timed Out")]
        with self.assertRaises(base.MidiaIndisponivel) as ctx:
            self.evo.baixar_midia(INST, self.chave)
        self.assertNotIsInstance(ctx.exception, base.MidiaExpirada)
        self.assertEqual(len(EvolutionFalsa.pedidos), 4)

    def test_400_com_sinal_de_expirada_no_corpo(self):
        for mensagem in ("Message not found", "Error: Request failed with status code 410",
                         "Error: Request failed with status code 404"):
            EvolutionFalsa.respostas, EvolutionFalsa.pedidos = [self.resposta(mensagem)], []
            with self.assertRaises(base.MidiaExpirada, msg=mensagem):
                self.evo.baixar_midia(INST, self.chave)
            self.assertEqual(len(EvolutionFalsa.pedidos), 1)   # expirada não tenta de novo


if __name__ == "__main__":
    unittest.main()
