"""Falhas do envio manual: recusa, negado e serviço parado chegam à tela como erro (pelo modulos.agir do painel, não
como 'Feito.'), e o mesmo id da tela depois de um 'falhou' sai de novo na MESMA linha em vez de virar 'clique
repetido'; 'incerto' continua incerto."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from testes.test_aba_conversas import Conversas  # noqa: E402

PAINEL = os.path.join(os.path.dirname(os.path.dirname(AQUI)), "painel")


class TesteMesmoIdDepoisDeFalha(Conversas):
    def test_falhou_e_mesmo_id_sai_de_novo_na_mesma_linha(self):
        self.falso.modo_envio = "recusar"
        primeiro = self.enviar(self.maria, "oi", "u1")
        self.assertEqual(primeiro["ok"], False)
        self.assertIn("recusou", primeiro["mensagem"])
        self.falso.modo_envio = "ok"
        segundo = self.enviar(self.maria, "oi", "u1")
        self.assertEqual((segundo["ok"], segundo["mensagem"]), (True, "Mensagem enviada."))
        self.assertEqual(self.falso.envios(), 2)
        self.assertEqual(len(self.falso.entregues), 1)
        (linha,) = self.envios()
        self.assertEqual((linha["estado"], linha["chave_dedupe"]), ("enviado", "manual:u1:%d" % self.maria))

    def test_falhou_de_novo_continua_erro(self):
        self.falso.modo_envio = "recusar"
        self.enviar(self.maria, "oi", "u1")
        r = self.enviar(self.maria, "oi", "u1")
        self.assertEqual(r["ok"], False)
        self.assertIn("recusou", r["mensagem"])
        self.assertEqual(self.falso.envios(), 2)
        self.assertEqual([e["estado"] for e in self.envios()], ["falhou"])

    def test_incerto_com_mesmo_id_diz_incerto_e_nao_envia(self):
        self.falso.modo_envio = "timeout"
        self.enviar(self.maria, "oi", "u1")
        self.falso.modo_envio = "ok"
        r = self.enviar(self.maria, "oi", "u1")
        self.assertEqual(r["ok"], False)
        self.assertIn("Envios incertos", r["mensagem"])
        self.assertEqual(self.falso.envios(), 1)
        self.assertEqual([e["estado"] for e in self.envios()], ["incerto"])

    def test_enviado_com_mesmo_id_continua_clique_repetido(self):
        self.assertTrue(self.enviar(self.maria, "oi", "u1")["ok"])
        r = self.enviar(self.maria, "oi", "u1")
        self.assertEqual(r["ok"], True)
        self.assertIn("clique repetido", r["mensagem"])
        self.assertEqual(self.falso.envios(), 1)


@unittest.skipUnless(os.path.isfile(os.path.join(PAINEL, "modulos.py")), "painel não está ao lado do plugin")
class TestePeloPainel(Conversas):
    """O caminho de verdade: POST /api/modulos/<id>/acao chama modulos.agir, que embrulha o dict do módulo."""

    def setUp(self):
        super().setUp()
        if PAINEL not in sys.path:
            sys.path.append(PAINEL)
        import modulos
        self.painel = modulos
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)

    def pelo_painel(self, acao, **dados):
        mod = types.SimpleNamespace(INFO=self.mod.INFO,
                                    agir=lambda ctx, a, d: self.mod.agir(self.ctx, a, d, base=self.base))
        with mock.patch.object(self.painel, "carregar", return_value=mod), \
                mock.patch.object(self.painel, "contexto", return_value=self.ctx):
            return self.painel.agir({}, "vendas", acao, dados)

    def enviar_pelo_painel(self, conversa, id_cliente="p1"):
        return self.pelo_painel("enviar_mensagem", conversa_id=conversa, texto="oi", id_cliente=id_cliente)

    def test_enviado_e_200(self):
        codigo, corpo = self.enviar_pelo_painel(self.maria)
        self.assertEqual((codigo, corpo["ok"], corpo["resultado"]["mensagem"]), (200, True, "Mensagem enviada."))

    def test_negado_por_optout_e_erro_na_tela(self):
        codigo, corpo = self.enviar_pelo_painel(self.ana)
        self.assertEqual(codigo, 422)
        self.assertNotIn("ok", corpo)
        self.assertIn("pediu para sair", corpo["erro"])

    def test_falhou_e_erro_na_tela(self):
        self.falso.modo_envio = "recusar"
        codigo, corpo = self.enviar_pelo_painel(self.maria)
        self.assertEqual(codigo, 422)
        self.assertIn("recusou", corpo["erro"])

    def test_servico_parado_e_erro_na_tela(self):
        self.con.execute("UPDATE batimento SET em = '2000-01-01T00:00:00+00:00' WHERE id = 1")
        codigo, corpo = self.enviar_pelo_painel(self.maria)
        self.assertEqual(codigo, 422)
        self.assertIn("parado", corpo["erro"])
        self.assertEqual(self.falso.envios(), 0)


if __name__ == "__main__":
    unittest.main()
