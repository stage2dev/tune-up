"""Testes da trava de arquivo do registro (trava._TravaArquivo): threads, processos e o ramo msvcrt;
e a insistência do Registro quando o Windows diz PermissionError."""
import sys

sys.dont_write_bytecode = True

import errno  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import lancador  # noqa: E402
import trava  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
FILHO = """
import sys, time
sys.path.insert(0, sys.argv[1])
import trava
with trava._TravaArquivo(sys.argv[2]):
    print("pegou", flush=True)
    time.sleep(0.8)
"""


class MsvcrtFalso:
    """Imita msvcrt.locking: recusa as `ocupada` primeiras tentativas, depois aceita."""
    LK_NBLCK, LK_UNLCK = 2, 0

    def __init__(self, ocupada=0, erro=errno.EACCES, falha_ao_soltar=False):
        self.ocupada, self.erro, self.falha_ao_soltar = ocupada, erro, falha_ao_soltar
        self.chamadas = []

    def locking(self, fd, modo, n):
        self.chamadas.append((modo, n, os.lseek(fd, 0, os.SEEK_CUR)))
        if modo == self.LK_NBLCK and self.ocupada:
            self.ocupada -= 1
            raise OSError(self.erro, "ocupada")
        if modo == self.LK_UNLCK and self.falha_ao_soltar:
            raise OSError(errno.EBADF, "soltar falhou")


class TesteTrava(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.arq = os.path.join(self.tmp, "execucoes.lock")

    def test_duas_threads_a_segunda_espera(self):
        ordem, pegou = [], threading.Event()

        def primeira():
            with trava._TravaArquivo(self.arq):
                pegou.set()
                time.sleep(0.3)
                ordem.append("1 soltou")

        t = threading.Thread(target=primeira)
        t.start()
        self.assertTrue(pegou.wait(5))
        with trava._TravaArquivo(self.arq):
            ordem.append("2 entrou")
        t.join(5)
        self.assertEqual(ordem, ["1 soltou", "2 entrou"])

    def test_dois_processos_o_segundo_espera(self):
        p = subprocess.Popen([sys.executable, "-B", "-c", FILHO, AQUI, self.arq],
                             stdout=subprocess.PIPE, text=True)
        self.addCleanup(p.wait, 10)
        self.addCleanup(p.stdout.close)
        self.assertEqual(p.stdout.readline().strip(), "pegou")
        t0 = time.monotonic()
        with trava._TravaArquivo(self.arq):
            esperou = time.monotonic() - t0
        self.assertGreater(esperou, 0.4)

    def test_ramo_msvcrt_tenta_de_novo_e_solta(self):
        falso = MsvcrtFalso(ocupada=3)
        with mock.patch.object(trava, "fcntl", None), mock.patch.object(trava, "msvcrt", falso):
            with trava._TravaArquivo(self.arq, prazo=5) as tr:
                fd = tr.fd
        n, u = MsvcrtFalso.LK_NBLCK, MsvcrtFalso.LK_UNLCK
        self.assertEqual(falso.chamadas, [(n, 1, 0)] * 4 + [(u, 1, 0)])  # 1 byte, sempre no offset 0
        with self.assertRaises(OSError):
            os.fstat(fd)  # fd fechado

    def test_ramo_msvcrt_estoura_o_prazo_com_erro_claro(self):
        falso = MsvcrtFalso(ocupada=10 ** 6)
        with mock.patch.object(trava, "fcntl", None), mock.patch.object(trava, "msvcrt", falso):
            tr = trava._TravaArquivo(self.arq, prazo=0.2)
            with self.assertRaisesRegex(TimeoutError, "ocupada por mais de 0.2 s"):
                tr.__enter__()
        self.assertNotIn(MsvcrtFalso.LK_UNLCK, [c[0] for c in falso.chamadas])
        with self.assertRaises(OSError):
            os.fstat(tr.fd)  # não vaza o fd

    def test_ramo_msvcrt_erro_que_nao_e_ocupada_sobe_na_hora(self):
        falso = MsvcrtFalso(ocupada=10 ** 6, erro=errno.EBADF)
        with mock.patch.object(trava, "fcntl", None), mock.patch.object(trava, "msvcrt", falso):
            tr = trava._TravaArquivo(self.arq, prazo=5)
            t0 = time.monotonic()
            with self.assertRaises(OSError) as ctx:
                tr.__enter__()
        self.assertEqual(ctx.exception.errno, errno.EBADF)
        self.assertEqual(len(falso.chamadas), 1)
        self.assertLess(time.monotonic() - t0, 1)

    def test_ramo_msvcrt_insiste_tambem_em_edeadlock(self):
        falso = MsvcrtFalso(ocupada=2, erro=getattr(errno, "EDEADLOCK", errno.EDEADLK))
        with mock.patch.object(trava, "fcntl", None), mock.patch.object(trava, "msvcrt", falso):
            with trava._TravaArquivo(self.arq, prazo=5):
                pass
        self.assertEqual(len(falso.chamadas), 4)  # 2 recusas, a que pega e a que solta

    def test_erro_ao_destravar_nao_esconde_o_erro_do_corpo(self):
        falso = MsvcrtFalso(falha_ao_soltar=True)
        with mock.patch.object(trava, "fcntl", None), mock.patch.object(trava, "msvcrt", falso), \
                mock.patch("sys.stderr"):
            with self.assertRaisesRegex(ValueError, "do corpo"):
                with trava._TravaArquivo(self.arq, prazo=5) as tr:
                    raise ValueError("do corpo")
        with self.assertRaises(OSError):
            os.fstat(tr.fd)  # fechou mesmo assim

    def test_erro_ao_destravar_sem_erro_no_corpo_sobe(self):
        falso = MsvcrtFalso(falha_ao_soltar=True)
        with mock.patch.object(trava, "fcntl", None), mock.patch.object(trava, "msvcrt", falso):
            with self.assertRaisesRegex(OSError, "soltar falhou"):
                with trava._TravaArquivo(self.arq, prazo=5) as tr:
                    pass
        with self.assertRaises(OSError):
            os.fstat(tr.fd)

    def test_prazo_padrao_cobre_o_maior_rodar_sob_a_trava(self):
        self.assertEqual(trava._TravaArquivo(self.arq).prazo, 90)
        self.assertIs(lancador._TravaArquivo, trava._TravaArquivo)


def falha_n_vezes(n, real):
    """Imita o Windows: as `n` primeiras chamadas dão PermissionError, depois chama `real`."""
    conta = {"n": 0}

    def falso(*a, **k):
        conta["n"] += 1
        if conta["n"] <= n:
            raise PermissionError(13, "aberto por outro processo")
        return real(*a, **k)
    falso.conta = conta
    return falso


class TesteRegistroOcupado(unittest.TestCase):
    """Windows: os.replace/open sobre execucoes.json falham enquanto outro thread o tem aberto."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.reg = lancador.Registro(self.tmp)
        with open(self.reg.arquivo, "w", encoding="utf-8") as f:
            json.dump([{"id": "abcdef01"}], f)
        for alvo, valor in (("PRAZO_OCUPADO", 2), ("time.sleep", lambda s: None)):
            p = mock.patch.object(lancador, alvo, valor) if "." not in alvo else mock.patch(alvo, valor)
            p.start()
            self.addCleanup(p.stop)

    def test_gravar_insiste_no_replace_e_grava(self):
        falso = falha_n_vezes(3, os.replace)
        with mock.patch("os.replace", falso):
            self.reg.gravar([{"id": "abcdef02"}])
        self.assertEqual(falso.conta["n"], 4)
        self.assertEqual([r["id"] for r in self.reg.ler()], ["abcdef02"])

    def test_gravar_desiste_depois_do_prazo_e_nao_deixa_temporario(self):
        with mock.patch.object(lancador, "PRAZO_OCUPADO", 0.2), mock.patch("time.sleep", time.sleep), \
                mock.patch("os.replace", falha_n_vezes(10 ** 6, os.replace)):
            with self.assertRaises(PermissionError):
                self.reg.gravar([{"id": "abcdef02"}])
        self.assertEqual(sorted(os.listdir(self.tmp)), ["execucoes.json"])
        self.assertEqual([r["id"] for r in self.reg.ler()], ["abcdef01"])

    def test_ler_insiste_no_open(self):
        falso = falha_n_vezes(3, open)
        with mock.patch("builtins.open", falso):
            self.assertEqual([r["id"] for r in self.reg.ler()], ["abcdef01"])
        self.assertEqual(falso.conta["n"], 4)

    def test_ler_com_permissionerror_persistente_sobe_em_vez_de_lista_vazia(self):
        with mock.patch.object(lancador, "PRAZO_OCUPADO", 0.2), mock.patch("time.sleep", time.sleep), \
                mock.patch("builtins.open", falha_n_vezes(10 ** 6, open)):
            with self.assertRaises(PermissionError):
                self.reg.ler()

    def test_ler_mantem_lista_vazia_sem_arquivo_e_com_json_invalido(self):
        self.assertEqual(lancador.Registro(os.path.join(self.tmp, "nada")).ler(), [])
        with open(self.reg.arquivo, "w", encoding="utf-8") as f:
            f.write("{quebrado")
        self.assertEqual(self.reg.ler(), [])


if __name__ == "__main__":
    unittest.main()
