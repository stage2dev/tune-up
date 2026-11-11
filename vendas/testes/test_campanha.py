"""Campanha e agendador (D2a): janela, 8/min, aquecimento de NOVOS por dia, opt-out depois de enfileirar, reinício
sem duplicar, aceita-e-cai = 1 incerto e 0 reenvios, 5 falhas pausam, jitter nos limites, lead que responde sai.
Conector falso e relógio injetado; nada de rede."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import os  # noqa: E402
import random  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import agendador, banco, campanha, pasta, portao, recebimento  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402

UTC = datetime.timezone.utc
AGORA = datetime.datetime(2026, 11, 10, 15, 0, tzinfo=UTC)   # 12:00 no fuso -03:00
FORA = datetime.datetime(2026, 11, 10, 23, 0, tzinfo=UTC)    # 20:00 no fuso -03:00
INST = "loja"


def numero(i):
    return "+55 11 91000-%04d" % i


class Queda(ConectorFalso):
    """Entrega e o processo "morre" (BaseException) na entrega de número `na`."""
    def __init__(self, na):
        ConectorFalso.__init__(self)
        self.na = na

    def enviar_texto(self, instancia, telefone, texto):
        ident = ConectorFalso.enviar_texto(self, instancia, telefone, texto)
        if len(self.entregues) == self.na:
            raise KeyboardInterrupt("processo caiu depois de entregar")
        return ident


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "projeto"))
        self.pasta = pasta.pasta_de_dados(os.path.join(self.tmp, "projeto"), base=os.path.join(self.tmp, "dados"))
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        banco.gravar_config(self.con, "fuso", "-03:00")
        banco.gravar_config(self.con, "instancia", INST)
        self.c = ConectorFalso()
        self.agora = AGORA
        self.ag = self.novo_agendador()
        self.n = 0

    def novo_agendador(self, conector=None):
        return agendador.Agendador(lambda: banco.abrir(self.pasta), lambda: conector or self.c,
                                   relogio=lambda: self.agora, aleatorio=random.Random(7))

    def campanha(self, n, ativa=True):
        ids = []
        for _ in range(n):
            self.n += 1
            ids.append(banco.salvar_contato(self.con, numero(self.n)))
        cid = campanha.criar(self.con, "teste", "Oi, tudo bem?", ids)
        if ativa:
            self.assertTrue(campanha.ativar(self.con, cid))
        return cid

    def rodar(self, voltas, passo_s=10, ag=None):
        for _ in range(voltas):
            (ag or self.ag).passo()
            self.agora += datetime.timedelta(seconds=passo_s)

    def estados(self, cid):
        return [r["estado"] for r in self.con.execute(
            "SELECT estado FROM campanha_contatos WHERE campanha_id = ? ORDER BY ordem", (cid,))]

    def motivos(self, cid):
        return [r["motivo"] for r in self.con.execute(
            "SELECT motivo FROM campanha_contatos WHERE campanha_id = ? ORDER BY ordem", (cid,))]

    def aquecido(self):
        banco.gravar_config(self.con, portao.chave_aquecimento(INST), "2026-01-01")   # bem depois do dia 8: 680 novos/dia


class TestJanelaETetos(Base):
    def test_fora_da_janela_espera_ate_as_9(self):
        cid = self.campanha(1)
        self.agora = FORA
        espera = self.ag.passo()
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual((self.estados(cid), self.motivos(cid)), (["pendente"], ["fora_da_janela"]))
        self.assertAlmostEqual(espera, 13 * 3600, delta=1)                # 20:00 -> 09:00 do dia seguinte
        self.agora += datetime.timedelta(hours=6)
        self.ag.passo()
        self.assertEqual(self.c.envios(), 0)                               # ainda esperando, sem novo negado
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios WHERE estado = 'negado'").fetchone()[0], 1)
        self.agora = FORA + datetime.timedelta(hours=13)                   # 09:00 local
        self.ag.passo()
        self.assertEqual((self.c.envios(), self.estados(cid)), (1, ["enviado"]))

    def test_nono_envio_no_mesmo_minuto_espera(self):
        self.aquecido()
        cid = self.campanha(9)
        self.rodar(9, passo_s=1)
        self.assertEqual(self.c.envios(), 8)
        self.assertEqual(self.estados(cid)[8], "pendente")
        self.assertEqual(self.motivos(cid)[8], "teto_minuto")
        self.agora = AGORA + datetime.timedelta(seconds=30)
        self.assertGreater(self.ag.passo(), 0)
        self.assertEqual(self.c.envios(), 8)
        self.agora = AGORA + datetime.timedelta(seconds=61)
        self.ag.passo()
        self.assertEqual((self.c.envios(), self.estados(cid)[8]), (9, "enviado"))

    def test_curva_de_aquecimento(self):
        hoje = datetime.date(2026, 11, 10)
        self.assertEqual(portao.teto_contatos_novos(self.con, hoje, INST), 5)   # nenhum envio de campanha ainda
        banco.gravar_config(self.con, portao.chave_aquecimento(INST), hoje.isoformat())
        dias = [portao.teto_contatos_novos(self.con, hoje + datetime.timedelta(days=d), INST) for d in range(10)]
        self.assertEqual(dias, [5, 20, 36, 65, 117, 210, 378, 680, 680, 680])

    def test_aquecimento_dia_1_cinco_novos_dia_2_vinte(self):
        cid = self.campanha(7)
        self.rodar(12)
        self.assertEqual(self.c.envios(), 5)
        self.assertEqual(self.estados(cid), ["enviado"] * 5 + ["pendente"] * 2)
        self.assertEqual(self.motivos(cid)[5], "teto_contatos_novos_dia")
        self.assertEqual(banco.ler_config(self.con, portao.chave_aquecimento(INST)), "2026-11-10")   # dia 1 gravado no banco
        negados = self.con.execute("SELECT COUNT(*) FROM envios WHERE estado = 'negado'").fetchone()[0]
        self.assertEqual(negados, 1)            # o resto dos novos espera sem martelar o portão
        cid2 = self.campanha(25)
        self.agora = AGORA + datetime.timedelta(days=1)                    # dia 2, 12:00 local
        self.rodar(40)
        self.assertEqual(self.c.envios(), 5 + 20)
        self.assertEqual(self.estados(cid), ["enviado"] * 7)               # os 2 de ontem saíram primeiro
        self.assertEqual(self.estados(cid2).count("enviado"), 18)

    def test_trocar_de_instancia_volta_ao_teto_de_5(self):
        self.aquecido()                                                    # instância "loja" já no 680/dia
        velho = self.campanha(3)
        self.rodar(4)
        self.assertEqual(self.estados(velho), ["enviado"] * 3)
        banco.gravar_config(self.con, "instancia", "nova")                 # o que instancia.conectar grava
        self.agora += datetime.timedelta(minutes=5)
        repetidos = campanha.criar(self.con, "de novo", "Oi outra vez",
                                   [banco.buscar_contato(self.con, numero(i))["id"] for i in (1, 2, 3)])
        campanha.ativar(self.con, repetidos)
        cid = self.campanha(10)
        self.rodar(20)
        # os 3 que receberam do número antigo são NOVOS para o número novo: 5 no dia 1, somando as duas campanhas
        self.assertEqual(self.c.envios(), 3 + 5)
        self.assertEqual(self.estados(repetidos), ["enviado"] * 3)
        self.assertEqual(self.estados(cid), ["enviado"] * 2 + ["pendente"] * 8)
        self.assertEqual(self.motivos(cid)[2], "teto_contatos_novos_dia")
        self.assertEqual(banco.ler_config(self.con, portao.chave_aquecimento("nova")), "2026-11-10")
        self.assertEqual(portao.teto_contatos_novos(self.con, datetime.date(2026, 11, 10), "nova"), 5)

    def test_contato_ja_conhecido_passa_depois_do_teto_de_novos(self):
        cid = self.campanha(6)
        conhecido = banco.salvar_contato(self.con, numero(99))
        banco.registrar_envio(self.con, "pre:1", "manual", estado="enviado", contato_id=conhecido,
                              quando=portao._iso(AGORA - datetime.timedelta(days=3)), instancia=INST)
        cid2 = campanha.criar(self.con, "velhos", "Oi de novo", [conhecido])
        campanha.ativar(self.con, cid2)
        self.rodar(10)
        self.assertEqual(self.estados(cid), ["enviado"] * 5 + ["pendente"])
        self.assertEqual(self.estados(cid2), ["enviado"])


class TestOptoutERespostas(Base):
    def test_optout_depois_de_enfileirar_nega_sem_chamar_o_conector(self):
        cid = self.campanha(2)
        banco.marcar_optout(self.con, numero(1))
        self.rodar(5)
        self.assertEqual(self.estados(cid), ["negado", "enviado"])
        self.assertEqual(self.motivos(cid)[0], "optout")
        self.assertEqual([e["telefone"] for e in self.c.entregues], [self.con.execute(
            "SELECT telefone FROM contatos WHERE id = (SELECT contato_id FROM campanha_contatos WHERE ordem = 1)"
        ).fetchone()[0]])
        cid2 = campanha.criar(self.con, "outra", "Oi", [banco.buscar_contato(self.con, numero(1))["id"]])
        campanha.ativar(self.con, cid2)
        self.rodar(3)
        self.assertEqual((self.estados(cid2), self.c.envios()), (["negado"], 1))   # nunca, em nenhuma campanha

    def test_lead_que_responde_sai_da_campanha(self):
        cid = self.campanha(2)
        recebimento.gravar(self.con, [{"tipo_evento": "mensagem", "id_externo": "M1", "remetente": numero(1),
                                       "tipo": "texto", "texto": "quem é?", "timestamp": AGORA.timestamp()}],
                           agora=AGORA)
        self.rodar(4)
        self.assertEqual(self.estados(cid), ["respondeu", "enviado"])
        self.assertEqual(self.c.envios(), 1)


class TestQuedasEFalhas(Base):
    def test_reinicio_no_meio_nao_duplica(self):
        self.aquecido()
        cid = self.campanha(3)
        caiu = Queda(2)
        ag = self.novo_agendador(caiu)
        ag.passo()
        self.agora += datetime.timedelta(seconds=10)
        with self.assertRaises(KeyboardInterrupt):
            ag.passo()
        self.assertEqual(portao.pendentes_para_incerto(self.con), 1)        # a subida do serviço faz isso
        self.agora += datetime.timedelta(seconds=10)
        depois = ConectorFalso()
        self.rodar(5, ag=self.novo_agendador(depois))
        self.assertEqual(self.estados(cid), ["enviado", "incerto", "enviado"])
        self.assertEqual(len(caiu.entregues) + len(depois.entregues), 3)
        self.assertEqual([e["telefone"] for e in depois.entregues], [self.con.execute(
            "SELECT telefone FROM contatos WHERE id = (SELECT contato_id FROM campanha_contatos WHERE ordem = 2)"
        ).fetchone()[0]])

    def test_aceita_e_cai_um_incerto_e_zero_reenvios(self):
        cid = self.campanha(1)
        self.c.modo_envio = "aceitar_e_cair"
        self.rodar(5)
        self.c.modo_envio = "ok"
        self.rodar(5, ag=self.novo_agendador())                            # "reiniciou"
        self.assertEqual(self.c.envios(), 1)
        self.assertEqual(self.estados(cid), ["incerto"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios WHERE estado = 'incerto'").fetchone()[0], 1)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios WHERE estado = 'enviado' AND criado_em IS NULL"
                                          ).fetchone()[0], 0)

    def test_cinco_falhas_seguidas_pausam_a_campanha(self):
        self.aquecido()
        cid = self.campanha(8)
        self.c.modo_envio = "recusar"
        self.rodar(10)
        self.assertEqual(self.c.envios(), 5)
        linha = self.con.execute("SELECT estado, motivo FROM campanhas WHERE id = ?", (cid,)).fetchone()
        self.assertEqual(linha["estado"], "pausada")
        self.assertTrue(linha["motivo"].startswith("5_falhas_seguidas:nao_enviado"), linha["motivo"])
        self.assertEqual(self.estados(cid), ["pendente"] * 8)   # 'falhou' = não saiu: volta à fila
        self.c.modo_envio = "ok"
        self.assertTrue(campanha.retomar(self.con, cid))
        self.rodar(20)
        self.assertEqual(self.estados(cid), ["enviado"] * 8)
        self.assertEqual(self.c.envios(), 5 + 8)
        self.assertEqual(self.con.execute("SELECT estado FROM campanhas WHERE id = ?", (cid,)).fetchone()[0],
                         "concluida")
        # o reenvio usa a MESMA linha (nenhuma chave nova): 8 envios, 13 tentativas
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios WHERE origem = 'campanha'").fetchone()[0], 8)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM tentativas").fetchone()[0], 13)

    def test_falhou_volta_a_fila_e_sai_pelo_reenvio_depois_da_espera(self):
        self.aquecido()
        cid = self.campanha(1)
        self.c.modo_envio = "recusar"
        self.ag.passo()
        envio_id = self.con.execute("SELECT envio_id FROM campanha_contatos").fetchone()[0]
        self.assertEqual((self.estados(cid), self.con.execute("SELECT estado FROM envios WHERE id = ?", (envio_id,)
                                                              ).fetchone()[0]), (["pendente"], "falhou"))
        self.c.modo_envio = "ok"
        self.agora += datetime.timedelta(seconds=30)
        self.ag.passo()
        self.assertEqual(self.c.envios(), 1)                    # ainda na espera da falha
        self.agora += datetime.timedelta(seconds=agendador.ESPERA_FALHA_S)
        self.ag.passo()
        self.assertEqual((self.c.envios(), self.estados(cid)), (2, ["enviado"]))
        self.assertEqual(self.con.execute("SELECT estado FROM envios WHERE id = ?", (envio_id,)).fetchone()[0],
                         "enviado")

    def test_falhou_e_depois_optout_nao_reenvia(self):
        cid = self.campanha(1)
        self.c.modo_envio = "recusar"
        self.ag.passo()
        banco.marcar_optout(self.con, numero(1))
        self.c.modo_envio = "ok"
        self.agora += datetime.timedelta(seconds=agendador.ESPERA_FALHA_S + 1)
        self.rodar(3)
        self.assertEqual((self.c.envios(), self.estados(cid), self.motivos(cid)), (1, ["negado"], ["optout"]))

    def test_pausada_pelo_dono_nao_envia_e_rota_recusa_estado_errado(self):
        cid = self.campanha(2)
        self.assertEqual(campanha.executar(None, self.con, "POST", "/campanhas/%d/pausar" % cid, {}, {})[0], 200)
        self.assertEqual(campanha.executar(None, self.con, "POST", "/campanhas/%d/pausar" % cid, {}, {})[0], 409)
        self.rodar(3)
        self.assertEqual(self.c.envios(), 0)
        codigo, corpo = campanha.executar(None, self.con, "POST", "/campanhas/%d/retomar" % cid, {}, {})
        self.assertEqual((codigo, corpo["campanhas"][0]["estado"]), (200, "ativa"))
        self.rodar(3)
        self.assertEqual(self.c.envios(), 2)

    def test_rascunho_nao_envia(self):
        self.campanha(1, ativa=False)
        self.rodar(3)
        self.assertEqual(self.c.envios(), 0)


class TestJitterEThread(Base):
    def test_jitter_dentro_dos_limites(self):
        r = random.Random(1)
        amostras = [agendador.jitter(r) for _ in range(20000)]
        self.assertGreaterEqual(min(amostras), 1.2)
        self.assertLessEqual(max(amostras), 12.0)
        self.assertAlmostEqual(sum(amostras) / len(amostras), 4.0, delta=0.2)
        self.assertGreater(len(set(round(a, 3) for a in amostras)), 1000)   # aleatório de fato

    def test_espera_depois_de_enviar_e_o_jitter(self):
        self.campanha(1)
        espera = self.ag.passo()
        self.assertEqual(self.c.envios(), 1)
        self.assertEqual(espera, agendador.jitter(random.Random(7)))

    def test_thread_para_limpo(self):
        self.campanha(3)
        parar = threading.Event()
        t = self.ag.iniciar(parar)
        for _ in range(100):
            if self.c.envios():
                break
            threading.Event().wait(0.05)
        parar.set()
        t.join(5)
        self.assertFalse(t.is_alive())
        self.assertEqual(self.c.envios(), 1)          # parou durante o jitter: não mandou o 2º


if __name__ == "__main__":
    unittest.main()
