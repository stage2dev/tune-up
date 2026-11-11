"""Campanha (D2a) com número que o WhatsApp diz não existir e com falha de transporte repetida: o número inexistente é
chamado UMA vez e o contato fica 'negado' (numero_invalido) sem contar falha seguida; a falha de transporte tem teto
de tentativas por contato; o reenvio vai para depois dos contatos ainda não tentados. Conector falso, relógio
injetado; nada de rede."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import campanha  # noqa: E402
from servico.conectores import base  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.test_campanha import Base  # noqa: E402


class Seletivo(ConectorFalso):
    """Recusa os números de `inexistentes` como a Evolution recusa exists:false; `falhar` = quantas recusas de
    transporte cada número leva antes de passar."""
    def __init__(self, inexistentes=(), falhar=None):
        ConectorFalso.__init__(self)
        self.inexistentes = set(inexistentes)
        self.falhar = dict(falhar or {})
        self.chamados = []

    def enviar_texto(self, instancia, telefone, texto):
        self.chamados.append(telefone)
        if telefone in self.inexistentes:
            raise base.NumeroInexistente("número não está no WhatsApp", 400)
        if self.falhar.get(telefone, 0) > 0:
            self.falhar[telefone] -= 1
            raise base.NaoEnviado("recusado pelo falso", 400)
        return ConectorFalso.enviar_texto(self, instancia, telefone, texto)


class Fila(Base):
    def telefones(self, cid):
        return [r[0] for r in self.con.execute(
            "SELECT ct.telefone FROM campanha_contatos cc JOIN contatos ct ON ct.id = cc.contato_id "
            "WHERE cc.campanha_id = ? ORDER BY cc.ordem", (cid,))]

    def situacao(self, cid):
        return tuple(self.con.execute("SELECT estado, motivo FROM campanhas WHERE id = ?", (cid,)).fetchone())


class TestNumeroInexistente(Fila):
    def test_cinco_inexistentes_na_frente_e_vinte_bons_concluem(self):
        self.aquecido()
        cid = self.campanha(25)
        tels = self.telefones(cid)
        self.c = Seletivo(inexistentes=tels[:5])
        self.ag = self.novo_agendador()
        self.rodar(120)
        self.assertEqual(sorted(e["telefone"] for e in self.c.entregues), sorted(tels[5:]))
        for t in tels[:5]:
            self.assertEqual(self.c.chamados.count(t), 1, t)
        self.assertEqual(self.estados(cid), ["negado"] * 5 + ["enviado"] * 20)
        self.assertEqual({r[0] for r in self.con.execute(
            "SELECT motivo FROM campanha_contatos WHERE estado = 'negado'")}, {"numero_invalido"})
        self.assertEqual(self.situacao(cid)[0], "concluida")

    def test_lista_fria_um_em_sete_inexistente_conclui(self):
        self.aquecido()
        cid = self.campanha(100)
        tels = self.telefones(cid)
        ruins = tels[::7]
        self.c = Seletivo(inexistentes=ruins)
        self.ag = self.novo_agendador()
        self.rodar(400)
        self.assertEqual(len(self.c.entregues), 100 - len(ruins))
        self.assertEqual(sum(self.c.chamados.count(t) for t in ruins), len(ruins))
        self.assertEqual(self.situacao(cid)[0], "concluida")


class TestFalhaDeTransporte(Fila):
    def test_falha_repetida_para_no_teto_e_a_campanha_conclui(self):
        self.aquecido()
        cid = self.campanha(1)
        self.c.modo_envio = "recusar"
        self.rodar(30, passo_s=70)   # bem mais que ESPERA_FALHA_S entre voltas
        self.assertEqual(self.c.envios(), campanha.TENTATIVAS_FALHOU)
        linha = self.con.execute("SELECT estado, motivo FROM campanha_contatos").fetchone()
        self.assertEqual(linha["estado"], "falhou")
        self.assertTrue(linha["motivo"].startswith("nao_enviado"), linha["motivo"])
        self.assertEqual(campanha.listar(self.con)["campanhas"][0]["contatos"], {"falhou": 1})   # o dono vê
        self.assertEqual(self.con.execute("SELECT estado FROM campanhas").fetchone()[0], "concluida")

    def test_reenvio_vai_depois_dos_contatos_ainda_nao_tentados(self):
        self.aquecido()
        cid = self.campanha(3)
        a, b, c = self.telefones(cid)
        self.c = Seletivo(falhar={a: 1})
        self.ag = self.novo_agendador()
        self.rodar(6, passo_s=70)    # 'a' já venceu na 2ª volta, mas b e c ainda não foram tentados
        self.assertEqual(self.c.chamados, [a, b, c, a])
        self.assertEqual(self.estados(cid), ["enviado"] * 3)


if __name__ == "__main__":
    unittest.main()
