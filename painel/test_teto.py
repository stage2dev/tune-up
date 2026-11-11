"""Teto de tempo da execução (max_minutos, max_bloqueado_min): validação, `claude stop`, falha e vaga livre.

Nada chama o claude de verdade e nada dorme: o CLI é falso e o relógio é `self.t`.
"""
import io
import os
import unittest
from unittest import mock

import catalogo
import teto
import test_chat

DEV = {"id": "dev.teto", "grupo": "dev", "titulo": "Teto", "risco": "leitura", "prompt": "/x {t}",
       "params": [{"nome": "t", "tipo": "texto", "max": 100}], "max_minutos": 5}


class CLIStop(test_chat.CLIChat):
    """CLIChat em que o `claude stop` pode falhar."""

    def __init__(self):
        test_chat.CLIChat.__init__(self)
        self.stop_falha = False

    def __call__(self, cmd, cwd, timeout):
        if cmd[1:2] == ["stop"] and self.stop_falha:
            self.chamadas.append((list(cmd), cwd))
            return 1, "", "erro"
        return test_chat.CLIChat.__call__(self, cmd, cwd, timeout)


class TesteTeto(test_chat.Base):
    def setUp(self):
        test_chat.Base.setUp(self)
        self.cli = CLIStop()

    def stops(self):
        return [c[0][2] for c in self.cli.chamadas if c[0][1:2] == ["stop"]]

    def reg(self, lc, i):
        return lc.achar(i)

    def test_validacao(self):
        a = catalogo.validar_acao(DEV)
        self.assertEqual((a["max_minutos"], a["max_bloqueado_min"]), (5, None))
        for bom in (1, 1440):
            self.assertEqual(catalogo.validar_acao(dict(DEV, max_bloqueado_min=bom))["max_bloqueado_min"], bom)
        for ruim in (0, -1, 1441, "5", 2.5, True, [5], ""):
            for campo in teto.CAMPOS:
                with self.assertRaises(ValueError, msg="%s=%r" % (campo, ruim)):
                    catalogo.validar_acao(dict(DEV, **{campo: ruim}))
        self.gravar_acoes([DEV, dict(DEV, id="dev.ruim", max_minutos=0)])
        acoes, avisos = catalogo.carregar_catalogo(os.path.join(self.tmp, "acoes"))
        self.assertEqual([x["id"] for x in acoes], ["dev.teto"])
        self.assertIn("max_minutos", avisos[0])

    def test_max_minutos_para_marca_falha_e_nao_repete(self):
        self.gravar_acoes([DEV])
        lc = self.lanc()
        i = lc.iniciar("dev.teto", {"t": "a"})["id"]
        self.assertEqual((self.reg(lc, i)["max_minutos"], self.reg(lc, i)["max_bloqueado_min"]), (5, None))
        self.t[0] += 299
        self.assertEqual(lc.execucoes(forcar=True)[0]["estado"], "rodando")
        self.assertEqual(self.stops(), [])
        self.t[0] += 1
        ex = lc.execucoes(forcar=True)[0]
        self.assertEqual((ex["estado"], ex["falha"]), ("parada", "max_minutos"))
        self.assertEqual(self.stops(), [i])
        r = self.reg(lc, i)
        self.assertEqual((r["falha"], r["parada_pelo_painel"]), ("max_minutos", True))
        self.t[0] += 600
        self.assertEqual(lc.execucoes(forcar=True)[0]["estado"], "parada")
        self.assertEqual(self.stops(), [i])  # um stop só

    def test_libera_a_vaga_do_teto(self):
        self.gravar_acoes([DEV, dict(DEV, id="dev.sem", max_minutos=None)])
        lc = self.lanc(max_execucoes=1)
        sem = lc.iniciar("dev.sem", {"t": "a"})["id"]
        self.t[0] += 10 ** 6  # sem teto: segue ocupando a vaga
        with self.assertRaises(catalogo.ErroAcao) as e:
            lc.iniciar("dev.teto", {"t": "b"})
        self.assertEqual(e.exception.codigo, 409)
        self.assertEqual(self.stops(), [])
        lc.parar(sem)
        com = lc.iniciar("dev.teto", {"t": "c"})["id"]
        self.t[0] += 300
        novo = lc.iniciar("dev.teto", {"t": "d"})["id"]  # o disparo novo para a velha e entra na vaga
        self.assertNotEqual(novo, com)
        self.assertEqual(self.stops(), [sem, com])
        self.assertEqual(self.reg(lc, com)["falha"], "max_minutos")

    def test_max_bloqueado_conta_so_o_tempo_esperando(self):
        self.gravar_acoes([dict(DEV, max_minutos=None, max_bloqueado_min=2)])
        lc = self.lanc()
        i = lc.iniciar("dev.teto", {"t": "a"})["id"]
        agente = self.cli.agentes[0]
        agente["state"] = "blocked"
        self.t[0] += 10
        self.assertEqual(lc.execucoes(forcar=True)[0]["estado"], "precisa_de_voce")
        self.assertEqual(self.reg(lc, i)["bloqueada_ts"], self.t[0])
        self.t[0] += 119
        lc.execucoes(forcar=True)
        agente["state"] = "working"  # respondeu no terminal: o relógio do bloqueio zera
        self.t[0] += 1
        lc.execucoes(forcar=True)
        self.assertEqual(self.reg(lc, i)["bloqueada_ts"], 0)
        agente["state"] = "blocked"
        lc.execucoes(forcar=True)
        self.t[0] += 119
        lc.execucoes(forcar=True)
        self.assertEqual(self.stops(), [])
        self.t[0] += 1
        ex = lc.execucoes(forcar=True)[0]
        self.assertEqual((ex["estado"], ex["falha"], self.stops()), ("parada", "max_bloqueado_min", [i]))

    def test_stop_que_falha_nao_marca_e_tenta_de_novo(self):
        self.gravar_acoes([DEV])
        lc = self.lanc()
        i = lc.iniciar("dev.teto", {"t": "a"})["id"]
        self.cli.stop_falha = True
        self.t[0] += 300
        ex = lc.execucoes(forcar=True)[0]
        self.assertEqual(ex["estado"], "rodando")
        self.assertNotIn("falha", ex)
        self.assertNotIn("falha", self.reg(lc, i))
        lc.execucoes(forcar=True)
        self.assertEqual(self.stops(), [i, i])
        self.cli.stop_falha = False
        self.assertEqual(lc.execucoes(forcar=True)[0]["falha"], "max_minutos")

    def test_responder_zera_a_falha_e_o_relogio(self):
        self.gravar_acoes([DEV])
        lc = self.lanc()
        i = lc.iniciar("dev.teto", {"t": "a"})["id"]
        self.t[0] += 300
        self.assertTrue(lc.execucoes(forcar=True)[0]["pode_responder"])
        ex = lc.responder(i, "continua")
        self.assertNotIn("falha", ex)
        r = self.reg(lc, i)
        self.assertEqual((r["falha"], r["parada_pelo_painel"], r["respondida_ts"]), ("", False, self.t[0]))
        self.t[0] += 299
        self.assertEqual(lc.execucoes(forcar=True)[0]["estado"], "rodando")

    def test_vigia_olha_so_quando_ha_teto_ativo(self):
        self.gravar_acoes([DEV, dict(DEV, id="dev.sem", max_minutos=None)])
        lc = self.lanc()
        lc.iniciar("dev.sem", {"t": "a"})
        n = len(self.cli.chamadas)
        teto.uma_volta(lc)
        self.assertEqual(len(self.cli.chamadas), n)  # sem teto: nem chama `claude agents`
        i = lc.iniciar("dev.teto", {"t": "b"})["id"]
        self.t[0] += 300
        teto.uma_volta(lc)
        self.assertEqual(self.stops(), [i])
        self.assertEqual(self.reg(lc, i)["falha"], "max_minutos")
        n = len(self.cli.chamadas)
        teto.uma_volta(lc)
        self.assertEqual(len(self.cli.chamadas), n)

    def test_vigia_nao_morre_com_erro(self):
        class Parar:
            def __init__(self):
                self.voltas = 0

            def wait(self, pausa):
                self.voltas += 1
                return self.voltas > 3

        class Quebrado:
            def __init__(self):
                self.n, self._ultimo = 0, {}

            @property
            def registro(self):
                self.n += 1
                raise OSError("x")

        q, p = Quebrado(), Parar()
        with mock.patch("sys.stderr", new_callable=io.StringIO) as err:
            teto.vigiar(q, p, 0)
        self.assertEqual(q.n, 3)
        self.assertEqual(err.getvalue().count("teto de tempo: OSError"), 3)


if __name__ == "__main__":
    unittest.main()
