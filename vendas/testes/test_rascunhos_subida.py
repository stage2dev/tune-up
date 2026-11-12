"""Queda no meio de uma aprovação (servico/rascunhos.py, servico/servico.py): o rascunho travado em 'aprovando' não
fica preso. Na subida, com envio que saiu ou pode ter saído vira 'aprovado'; sem envio, ou com envio que falhou ou foi
negado, volta a 'pendente'; e um rascunho novo da IA volta a ser criado na conversa."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import subprocess  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
VENDAS = os.path.dirname(AQUI)
sys.path.insert(0, VENDAS)

from servico import banco, portao, rascunhos  # noqa: E402
from testes.openai_falsa import resposta_texto  # noqa: E402
from testes.test_rascunhos import BaseRascunho  # noqa: E402

SERVICO = os.path.join(VENDAS, "servico", "servico.py")


class TesteQuedaNaAprovacao(BaseRascunho):
    def travar(self, envio=None):
        """Simula a queda: o rascunho travou e, se envio, a reserva do envio ficou nesse estado."""
        d = self.rascunho()
        self.assertIsNone(rascunhos._travar(self.con, d["id"], d["texto"], "rascunho_aprovado:%d" % d["id"]))
        if envio is not None:
            portao._reservar(self.con, "rascunho_aprovado", "+5511900000001", "texto", d["texto"], [d["id"]], False,
                             portao._agora(None))
            if envio != "pendente":
                self.con.execute("UPDATE envios SET estado = ? WHERE chave_dedupe = ?",
                                 (envio, "rascunho_aprovado:%d" % d["id"]))
        self.assertEqual(self.estado(d["id"]), "aprovando")
        return d

    def subir(self):
        portao.pendentes_para_incerto(self.con)
        return rascunhos.destravar_na_subida(self.con)

    def test_envio_reservado_na_queda_fecha_como_aprovado(self):
        d = self.travar("pendente")
        self.assertEqual(self.subir(), 1)
        self.assertEqual(self.estado(d["id"]), "aprovado")
        eventos = [l["tipo"] for l in self.con.execute("SELECT tipo FROM eventos WHERE tipo LIKE 'rascunho_%'")]
        self.assertEqual(eventos, ["rascunho_destravado_na_subida"])
        self.assertNotEqual(rascunhos.aprovar(self.app, self.con, d["id"])[1]["estado"], "enviado")   # não reenvia
        self.assertEqual((self.c.envios(), self.c.entregues), (0, []))

    def test_envio_enviado_fecha_como_aprovado(self):
        d = self.travar("enviado")
        self.assertEqual(self.subir(), 1)
        self.assertEqual(self.estado(d["id"]), "aprovado")

    def test_sem_envio_volta_a_pendente_e_pode_aprovar(self):
        d = self.travar()
        self.assertEqual(self.subir(), 1)
        self.assertEqual(self.estado(d["id"]), "pendente")
        self.assertEqual(self.pendente()["id"], d["id"])
        self.assertEqual(rascunhos.aprovar(self.app, self.con, d["id"])[1]["estado"], "enviado")
        self.assertEqual(len(self.c.entregues), 1)

    def test_envio_que_falhou_volta_a_pendente(self):
        d = self.travar("falhou")
        self.assertEqual(self.subir(), 1)
        self.assertEqual(self.estado(d["id"]), "pendente")

    def test_envio_negado_volta_a_pendente(self):
        d = self.travar("negado")
        self.assertEqual(self.subir(), 1)
        self.assertEqual(self.estado(d["id"]), "pendente")

    def test_depois_da_subida_mensagem_nova_cria_rascunho(self):
        d = self.travar("pendente")
        self.subir()
        self.falsa.fila = [resposta_texto("Resposta nova")]
        self.chegar("m2", "e ai? alguem?")
        self.assertTrue(self.esperar(lambda: self.pendente() is not None and self.pendente()["id"] != d["id"]))
        self.assertEqual(self.pendente()["texto"], "Resposta nova")

    def test_nada_travado_nao_mexe(self):
        d = self.rascunho()
        self.assertEqual(self.subir(), 0)
        self.assertEqual(self.estado(d["id"]), "pendente")

    def test_subida_real_do_servico_destrava(self):
        d = self.travar("pendente")
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
        self.assertIn("1 rascunho(s) estavam sendo aprovados", erro.decode("utf-8"))
        self.con = banco.abrir(self.pasta)
        self.assertEqual(self.estado(d["id"]), "aprovado")


if __name__ == "__main__":
    unittest.main()
