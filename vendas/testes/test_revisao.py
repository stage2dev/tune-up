"""Revisão humana dos candidatos (servico/revisao.py e aba Buscador): só a aprovação do dono cria o lead; descartar não
cria; aprovar duas vezes = 1 contato; opt-out existente fica; candidato sem aprovação nunca entra em campanha;
endereço perigoso não é mostrado; descartado some em 30 dias e não é sugerido de novo."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, campanha, candidatos, disparos, revisao  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402
from testes.test_webhook_modo import PORTA_PAINEL, Base  # noqa: E402

FILTRO_TODOS = {"origem": "", "qualificacao": "", "base_legal": ""}


def linha(nome, fone="(11) 90000-0001", **extra):
    return dict({"nome": nome, "site": "https://www.exemplo.invalid/", "telefone": "+55" + "".join(
        c for c in fone if c.isdigit()), "url_da_fonte": "https://exemplo.invalid/contato", "nicho": "estética",
                 "cidade": "Campinas"}, **extra)


class Revisao(Base):
    def setUp(self):
        super().setUp()
        self.mod = carregar_modulo()
        self.ctx = {"raiz": self.projeto, "config": {"porta": PORTA_PAINEL}}
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        banco.bater(self.con)
        banco.registrar_servico(self.con, self.app.porta, self.app.marca)

    def candidato(self, nome="Clínica A", fone="(11) 90000-0001", **extra):
        candidatos._gravar(self.con, [linha(nome, fone, **extra)])
        return self.con.execute("SELECT id FROM candidatos WHERE nome = ?", (nome,)).fetchone()[0]

    def contatos(self):
        return [dict(r) for r in self.con.execute("SELECT * FROM contatos ORDER BY id")]

    def aba(self):
        return [a for a in self.mod.montar(self.ctx, base=self.base)["abas"] if a["id"] == "buscador"][0]["blocos"]

    def agir(self, acao, **dados):
        return self.mod.agir(self.ctx, acao, dados, base=self.base)


class TesteAprovar(Revisao):
    def test_aprovar_cria_o_contato_com_origem_e_base_legal(self):
        cid = self.candidato()
        self.assertEqual(self.contatos(), [])
        codigo, r = revisao.aprovar(self.con, cid)
        self.assertEqual(codigo, 200)
        (c,) = self.contatos()
        self.assertEqual((c["origem"], c["base_legal"], c["nome"]), ("buscador: estética/Campinas",
                                                                      "contato_publico_da_empresa", "Clínica A"))
        self.assertEqual(c["telefone"], "5511900000001")
        e = self.con.execute("SELECT estado, contato_id, url_da_fonte FROM candidatos WHERE id = ?", (cid,)).fetchone()
        self.assertEqual((e[0], e[1], e[2]), ("aprovado", c["id"], "https://exemplo.invalid/contato"))

    def test_descartar_nao_cria_contato(self):
        cid = self.candidato()
        self.assertEqual(revisao.descartar(self.con, cid)[0], 200)
        self.assertEqual(self.contatos(), [])
        self.assertEqual(self.con.execute("SELECT estado FROM candidatos").fetchone()[0], "descartado")
        self.assertEqual(revisao.aprovar(self.con, cid)[0], 409)   # descartado não vira lead por engano
        self.assertEqual(self.contatos(), [])

    def test_aprovar_duas_vezes_e_um_contato_so(self):
        cid = self.candidato()
        revisao.aprovar(self.con, cid)
        codigo, r = revisao.aprovar(self.con, cid)
        self.assertEqual((codigo, r["ja"]), (200, True))
        self.assertEqual(len(self.contatos()), 1)

    def test_contato_existente_com_optout_continua_fora_e_nao_muda(self):
        antes = banco.salvar_contato(self.con, "5511900000001", "Nome Antigo", "feira", "consentimento")
        banco.marcar_optout(self.con, "5511900000001", "2026-01-01T00:00:00+00:00")
        cid = self.candidato()
        codigo, r = revisao.aprovar(self.con, cid)
        self.assertEqual((codigo, r["mesclado"], r["contato_id"]), (200, True, antes))
        (c,) = self.contatos()
        self.assertEqual((c["optout_em"], c["origem"], c["base_legal"], c["nome"]),
                         ("2026-01-01T00:00:00+00:00", "feira", "consentimento", "Nome Antigo"))

    def test_sem_telefone_nao_vira_lead(self):
        cid = self.candidato("Sem Fone", telefone=None, url_da_fonte=None)
        self.assertEqual(revisao.aprovar(self.con, cid)[0], 409)
        self.assertEqual(self.contatos(), [])

    def test_candidato_que_nao_existe_e_404(self):
        self.assertEqual(revisao.aprovar(self.con, 999)[0], 404)


class TesteCampanha(Revisao):
    def test_sem_aprovacao_nenhum_contato_e_selecionavel_e_depois_e_frio(self):
        cid = self.candidato()
        livres, _ = disparos._selecionar(self.con, FILTRO_TODOS)
        self.assertEqual(livres, [])   # candidato presente, não aprovado: 0 linhas
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM contatos").fetchone()[0], 0)
        revisao.aprovar(self.con, cid)
        livres, _ = disparos._selecionar(self.con, FILTRO_TODOS)
        self.assertEqual(len(livres), 1)
        self.assertTrue(campanha.fria(self.con, livres[0][0]))   # frio: a trava de número descartável vale


class TesteTela(Revisao):
    def test_acoes_registradas_e_aba_mostra_candidato_mascarado_com_botoes(self):
        for a in ("candidato_filtrar", "candidato_aprovar", "candidato_descartar", "importar_candidatos"):
            self.assertIn(a, self.mod.INFO["acoes"])
        cid = self.candidato()
        blocos = self.aba()
        tabela = [b for b in blocos if b["tipo"] == "tabela"][0]
        self.assertEqual(tabela["linhas"][0]["telefone"], "****0001")
        self.assertEqual(tabela["linhas"][0]["fonte"], "https://exemplo.invalid/contato")
        self.assertNotIn("90000", json.dumps(blocos))
        forms = {b["acao"]: b for b in blocos if b["tipo"] == "formulario"}
        self.assertEqual(forms["candidato_aprovar"]["dados_fixos"], {"id": cid})
        self.assertEqual(forms["candidato_descartar"]["dados_fixos"], {"id": cid})
        self.assertIn("importar_candidatos", forms)
        self.assertIn("vendas.buscar-leads", json.dumps(blocos))

    def test_aprovar_pela_tela_e_filtro_por_nicho(self):
        a = self.candidato("A")
        self.candidato("B", "(11) 90000-0002", nicho="dentista")
        self.assertTrue(self.agir("candidato_filtrar", nicho="dentista", cidade="", estado="novo")["ok"])
        tabela = [b for b in self.aba() if b["tipo"] == "tabela"][0]
        self.assertEqual([x["nome"] for x in tabela["linhas"]], ["B"])
        r = self.agir("candidato_aprovar", id=a)
        self.assertTrue(r["ok"], r)
        self.assertEqual([c["nome"] for c in self.contatos()], ["A"])
        self.assertTrue(self.agir("candidato_aprovar", id=a)["ok"])
        self.assertEqual(len(self.contatos()), 1)
        self.assertFalse(self.agir("candidato_aprovar", id="1")["ok"])
        self.assertFalse(self.agir("candidato_filtrar", estado="xyz")["ok"])

    def test_endereco_javascript_ou_data_nao_aparece_nem_como_link(self):
        cid = self.candidato()
        self.con.execute("UPDATE candidatos SET site = 'javascript:alert(1)', url_da_fonte = 'data:text/html,x' "
                         "WHERE id = ?", (cid,))
        texto = json.dumps(self.aba(), ensure_ascii=False)
        self.assertNotIn("javascript:", texto)
        self.assertNotIn("data:text", texto)
        self.assertIn("(endereço não exibido)", texto)

    def test_servico_parado_nao_mostra_candidatos(self):
        self.con.execute("DELETE FROM batimento")
        self.candidato()
        self.assertEqual([b["tipo"] for b in self.aba()], ["texto"])


class TesteDescartados(Revisao):
    def test_purga_so_depois_de_30_dias(self):
        velho, novo = self.candidato("Velho"), self.candidato("Novo", "(11) 90000-0002")
        revisao.descartar(self.con, velho)
        revisao.descartar(self.con, novo)
        dia = lambda n: (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=n)).isoformat()  # noqa
        self.con.execute("UPDATE candidatos SET decidido_em = ? WHERE id = ?", (dia(31), velho))
        self.con.execute("UPDATE candidatos SET decidido_em = ? WHERE id = ?", (dia(29), novo))
        self.assertEqual(revisao.purgar(self.con), 1)
        self.assertEqual([r[0] for r in self.con.execute("SELECT nome FROM candidatos")], ["Novo"])

    def test_purga_na_subida_do_servico_e_nao_apaga_aprovado_nem_novo(self):
        from servico import servico
        velho, aprov, novo = self.candidato("Velho"), self.candidato("Aprov", "(11) 90000-0002"), self.candidato(
            "Novo", "(11) 90000-0003")
        revisao.descartar(self.con, velho)
        revisao.aprovar(self.con, aprov)
        self.con.execute("UPDATE candidatos SET decidido_em = '2020-01-01T00:00:00+00:00'")
        servico.importar_candidatos(self.con, self.projeto, lambda *a, **k: None)
        self.assertEqual(sorted(r[0] for r in self.con.execute("SELECT nome FROM candidatos")), ["Aprov", "Novo"])

    def test_descartado_nao_e_sugerido_de_novo_por_telefone_nem_por_site(self):
        cid = self.candidato("A")
        revisao.descartar(self.con, cid)
        n1, _ = candidatos._gravar(self.con, [linha("Outro Nome")])                          # mesmo telefone
        n2, _ = candidatos._gravar(self.con, [linha("Outro", "(11) 90000-0009", site="http://EXEMPLO.invalid/x")])
        n3, _ = candidatos._gravar(self.con, [linha("Diferente", "(11) 90000-0008", site="https://outro.invalid/")])
        self.assertEqual((n1, n2, n3), (0, 0, 1))


if __name__ == "__main__":
    unittest.main()
