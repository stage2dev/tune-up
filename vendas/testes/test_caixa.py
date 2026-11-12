"""Caixa de entrada da aba Conversas (U3): linhas de um banco semeado (nome, telefone formatado, prévia de áudio,
não lidas, selo por prioridade), abrir pelo clique marca como lido, atualizar_em 3 x 15, alerta = não lidas,
serviço parado = UM bloco, sem código cru na tela."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco  # noqa: E402
from testes.test_aba_conversas import Conversas  # noqa: E402


def carregar_caixa():
    import importlib.util
    from testes.test_servico import MODULO
    caminho = os.path.join(os.path.dirname(MODULO), "abas", "caixa.py")
    spec = importlib.util.spec_from_file_location("caixa_teste", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TesteFormatos(unittest.TestCase):
    def test_telefone_formatado_e_relativo(self):
        c = carregar_caixa()
        self.assertEqual(c.formatar_telefone("5519900000602"), "+55 (19) 90000-0602")
        self.assertEqual(c.formatar_telefone("+55 11 3000-0602"), "+55 (11) 3000-0602")
        self.assertEqual(c.formatar_telefone("14155550100"), "+14155550100")
        self.assertEqual(c.formatar_telefone(None), "Sem número")
        agora = datetime.datetime(2026, 5, 10, 15, 0, tzinfo=datetime.timezone.utc)
        iso = lambda **kw: (agora - datetime.timedelta(**kw)).isoformat()  # noqa: E731
        self.assertEqual([c.relativo(iso(seconds=10), agora), c.relativo(iso(minutes=5), agora),
                          c.relativo(iso(days=3), agora), c.relativo(None, agora)],
                         ["agora", "há 5 min", (agora - datetime.timedelta(days=3)).astimezone().strftime("%d/%m"), ""])

    def test_selo_pela_prioridade(self):
        c = carregar_caixa()
        tudo = {"saiu": True, "precisa_de_voce": True, "ia_pausada": True, "tem_rascunho": True}
        ordem = ["saiu", "precisa_de_voce", "ia_pausada", "tem_rascunho"]
        esperado = ["saiu", "precisa de você", "IA pausada", "rascunho esperando"]
        for i, texto in enumerate(esperado):
            self.assertEqual(c.selo({k: True for k in ordem[i:]})["texto"], texto)
        self.assertIsNone(c.selo({}))
        self.assertEqual(c.selo(tudo)["texto"], "saiu")


class TesteCaixa(Conversas):
    def linha(self, conversa):
        return [i for i in self.caixa()["conversas"] if i["id"] == str(conversa)][0]

    def test_audio_aparece_pelo_tipo_na_previa(self):
        banco.registrar_mensagem(self.con, self.joao, "entrada", None, id_externo="aud1", tipo="audio")
        self.assertEqual(self.linha(self.joao)["detalhe"], "Áudio")
        self.assertEqual(self.linha(self.joao)["nao_lidas"], 2)

    def test_nome_do_whatsapp_quando_nao_ha_nome(self):
        self.con.execute("UPDATE contatos SET nome_whatsapp = 'Zé do Posto' WHERE id = "
                         "(SELECT contato_id FROM conversas WHERE id = ?)", (self.joao,))
        titulos = {i["id"]: i["titulo"] for i in self.caixa()["conversas"]}
        self.assertEqual(titulos[str(self.joao)], "Zé do Posto")
        self.assertEqual(titulos[str(self.maria)], "Maria")

    def test_clicar_abre_e_marca_como_lido(self):
        self.assertEqual(self.linha(self.maria)["nao_lidas"], 1)
        self.assertTrue(self.agir("abrir_conversa", conversa_id=str(self.maria))["ok"])
        linha = self.linha(self.maria)
        self.assertNotIn("nao_lidas", linha)
        self.assertTrue(linha["ativa"])
        self.assertEqual(self.linha(self.joao)["nao_lidas"], 1)   # as outras seguem não lidas

    def test_sem_selo_quando_nada_pede_atencao(self):
        self.con.execute("UPDATE conversas SET precisa_de_voce = 0, modo = 'ia' WHERE id IN (?, ?)",
                         (self.maria, self.joao))
        self.con.execute("DELETE FROM config WHERE chave LIKE 'pausa%'")
        self.assertNotIn("selo", self.linha(self.maria))

    def test_selo_rascunho_esperando_so_sem_nada_mais_forte(self):
        self.con.execute("UPDATE conversas SET precisa_de_voce = 0 WHERE id = ?", (self.maria,))
        mensagem = self.con.execute("SELECT MAX(id) FROM mensagens WHERE conversa_id = ?", (self.maria,)).fetchone()[0]
        self.con.execute("INSERT INTO rascunhos (conversa_id, mensagem_id, texto, criado_em, estado) VALUES "
                         "(?, ?, 'oi', ?, 'pendente')", (self.maria, mensagem,
                                                        datetime.datetime.now(datetime.timezone.utc).isoformat()))
        self.assertEqual(self.linha(self.maria)["selo"]["texto"], "rascunho esperando")
        self.con.execute("UPDATE conversas SET precisa_de_voce = 1 WHERE id = ?", (self.maria,))
        self.assertEqual(self.linha(self.maria)["selo"]["texto"], "precisa de você")

    def test_atualizar_em_3_conectado_e_15_nao_conectado(self):
        self.assertEqual(self.mod.montar(self.ctx, base=self.base)["atualizar_em"], 15)   # sem conexão
        self.criar()
        self.falso.estado_atual = "conectado"
        self.assertEqual(self.mod.montar(self.ctx, base=self.base)["atualizar_em"], 3)
        self.falso.estado_atual = "desconectado"
        self.assertEqual(self.mod.montar(self.ctx, base=self.base)["atualizar_em"], 15)

    def test_atualizar_em_15_com_servico_parado(self):
        self.parar_batimento()
        self.con.execute("UPDATE batimento SET em = '2000-01-01T00:00:00+00:00' WHERE id = 1")
        self.assertEqual(self.mod.montar(self.ctx, base=self.base)["atualizar_em"], 15)

    def test_alerta_da_aba_e_o_total_de_nao_lidas(self):
        aba = self.mod.montar(self.ctx, base=self.base)["abas"][1]
        self.assertEqual((aba["id"], aba["alerta"]), ("conversas", 3))
        self.agir("abrir_conversa", conversa_id=str(self.maria))
        self.assertEqual(self.mod.montar(self.ctx, base=self.base)["abas"][1]["alerta"], 2)
        for c in (self.joao, self.ana):
            self.agir("abrir_conversa", conversa_id=str(c))
        self.assertNotIn("alerta", self.mod.montar(self.ctx, base=self.base)["abas"][1])

    def test_servico_parado_um_bloco_e_as_outras_abas_curtas(self):
        self.parar_batimento()
        self.con.execute("UPDATE batimento SET em = '2000-01-01T00:00:00+00:00' WHERE id = 1")
        abas = self.mod.montar(self.ctx, base=self.base)["abas"]
        self.assertEqual(len(abas), 7)
        self.assertEqual([len(a["blocos"]) for a in abas], [1] * 7)
        self.assertIn(self.mod.cliente.PYTHON + " -B", abas[0]["blocos"][0]["texto"])
        self.assertTrue(all("alerta" not in a for a in abas))

    def test_vazio_e_sem_codigo_cru(self):
        self.con.execute("DELETE FROM mensagens")
        self.con.execute("DELETE FROM conversas")
        caixa = self.caixa()
        self.assertEqual(caixa["conversas"], [])
        self.assertIn("Conversas antigas do WhatsApp não são importadas", caixa["vazio"])
        self.assertNotIn("alerta", self.mod.montar(self.ctx, base=self.base)["abas"][1])

    def test_nenhum_motivo_cru_na_conversa_aberta(self):
        from servico import cerebro
        cerebro.marcar_precisa_de_voce(self.con, self.maria, "anti_loop", True)
        self.agir("abrir_conversa", conversa_id=str(self.maria))
        self.assertNotIn("anti_loop", json.dumps(self.aba(), ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
