"""Aba Conversas e envio manual: lista e conversa de um banco semeado, telefone mascarado na lista e inteiro só na
conversa, envio pelo portão com origem manual e chave id+conversa, duplo clique, opt-out com liberação de uma
mensagem, reenviar (mesma linha) e descartar, assumir/devolver, limites de página, nenhum segredo nos blocos."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco  # noqa: E402
from testes.test_aba_conexao import Aba  # noqa: E402

MARIA, JOAO, ANA = "+55 11 90000-0001", "+55 11 90000-0002", "+55 11 90000-0003"


class Conversas(Aba):
    def setUp(self):
        super().setUp()
        banco.gravar_config(self.con, "instancia", "loja")
        self.maria = self.semear(MARIA, "Maria", [("entrada", "oi, quero saber o preço")])
        self.joao = self.semear(JOAO, None, [("entrada", "bom dia")])
        self.ana = self.semear(ANA, "Ana", [("entrada", "sair")])
        self.con.execute("UPDATE conversas SET precisa_de_voce = 1 WHERE id = ?", (self.maria,))
        self.con.execute("UPDATE conversas SET modo = 'humano' WHERE id = ?", (self.joao,))
        banco.marcar_optout(self.con, ANA)

    def semear(self, telefone, nome, mensagens):
        contato = banco.salvar_contato(self.con, telefone, nome=nome)
        conversa = banco.abrir_conversa(self.con, contato)
        for i, (direcao, texto) in enumerate(mensagens):
            banco.registrar_mensagem(self.con, conversa, direcao, texto, id_externo="%s-%d" % (telefone, i))
        return conversa

    def aba(self):
        r = self.mod.montar(self.ctx, base=self.base)
        self.assertEqual(r["avisos"], [])
        self.assertEqual([a["id"] for a in r["abas"]], ["conexao", "conversas", "ia"])
        return r["abas"][1]["blocos"]

    def agir(self, acao, **dados):
        return self.mod.agir(self.ctx, acao, dados, base=self.base)

    def enviar(self, conversa, texto="ola", id_cliente="x1"):
        return self.agir("enviar_mensagem", conversa_id=conversa, texto=texto, id_cliente=id_cliente)

    def envios(self):
        return [dict(r) for r in self.con.execute("SELECT * FROM envios ORDER BY id")]


class TesteLista(Conversas):
    def test_lista_com_selos_e_telefone_mascarado(self):
        lista = self.tipos(self.aba(), "lista")[0]
        por_titulo = {i["titulo"]: i for i in lista["itens"]}
        self.assertEqual(por_titulo["Maria (****0001)"]["selo"], {"texto": "precisa de você", "tom": "atencao"})
        self.assertIn("oi, quero saber o preço", por_titulo["Maria (****0001)"]["detalhe"])
        self.assertEqual(por_titulo["****0002"]["selo"]["texto"], "IA pausada")   # sem nome: telefone mascarado
        self.assertEqual(por_titulo["Ana (****0003)"]["selo"], {"texto": "saiu", "tom": "ruim"})
        texto = json.dumps(self.aba(), ensure_ascii=False)
        for inteiro in ("900000001", "900000002", "900000003"):
            self.assertNotIn(inteiro, texto)   # nada aberto ainda: nenhum telefone inteiro na tela

    def test_conversa_aberta_mostra_telefone_inteiro_e_mensagens(self):
        self.assertEqual(self.agir("abrir_conversa", conversa_id=str(self.maria))["ok"], True)
        conversa = self.tipos(self.aba(), "conversa")[0]
        self.assertIn("5511900000001", conversa["titulo"])
        self.assertEqual([(m["de"], m["texto"]) for m in conversa["mensagens"]],
                         [("contato", "oi, quero saber o preço")])
        self.assertEqual(conversa["enviar"], {"acao": "enviar_mensagem", "dados_fixos": {"conversa_id": self.maria},
                                              "rotulo": "Enviar"})
        self.assertEqual([b["acao"] for b in conversa["botoes"]], ["assumir_conversa"])
        self.assertNotIn("5511900000002", json.dumps(self.aba()))

    def test_selecao_fica_por_projeto_no_banco_do_servico(self):
        self.agir("abrir_conversa", conversa_id=self.joao)
        self.assertEqual(banco.ler_config(self.con, "conversa_aberta"), str(self.joao))
        self.assertEqual(self.agir("abrir_conversa", conversa_id=9999)["ok"], False)
        self.assertEqual(banco.ler_config(self.con, "conversa_aberta"), str(self.joao))

    def test_so_as_ultimas_50_mensagens(self):
        for i in range(60):
            banco.registrar_mensagem(self.con, self.maria, "entrada", "msg %02d" % i, id_externo="lote-%d" % i)
        self.agir("abrir_conversa", conversa_id=self.maria)
        mensagens = self.tipos(self.aba(), "conversa")[0]["mensagens"]
        self.assertEqual((len(mensagens), mensagens[-1]["texto"], mensagens[0]["texto"]), (50, "msg 59", "msg 10"))
        status, r = self.pedir_servico("/conversas/%d?limite=5000" % self.maria)
        self.assertEqual((status, len(r["mensagens"])), (200, 61))   # teto 100: as 61 que existem
        status, r = self.pedir_servico("/conversas?limite=2")
        self.assertEqual((len(r["conversas"]), r["total"]), (2, 3))

    def pedir_servico(self, caminho):
        codigo, corpo = self.mod.cliente.chamar(self.ctx, "GET", caminho, base=self.base)
        return codigo, corpo

    def test_leituras_exigem_token(self):
        for caminho in ("/conversas", "/conversas/%d" % self.maria, "/incertos"):
            status, _, _ = self.pedir_bruto("GET", caminho)
            self.assertEqual(status, 403)
        status, _, _ = self.pedir_bruto("POST", "/conversas/%d/modo" % self.maria, corpo={"modo": "humano"})
        self.assertEqual(status, 403)
        self.assertEqual(self.con.execute("SELECT modo FROM conversas WHERE id = ?", (self.maria,)).fetchone()[0],
                         "ia")

    def pedir_bruto(self, metodo, caminho, corpo=None):
        import http.client
        cab = {"Host": "127.0.0.1:%d" % self.app.porta}
        dados = None
        if corpo is not None:
            dados = json.dumps(corpo).encode("utf-8")
            cab["Content-Type"] = "application/json"
        con = http.client.HTTPConnection("127.0.0.1", self.app.porta, timeout=5)
        try:
            con.request(metodo, caminho, body=dados, headers=cab)
            r = con.getresponse()
            return r.status, dict(r.getheaders()), r.read().decode("utf-8")
        finally:
            con.close()

    def test_nenhum_token_ou_segredo_nos_blocos(self):
        self.agir("abrir_conversa", conversa_id=self.maria)
        self.enviar(self.maria)
        tudo = json.dumps([self.mod.montar(self.ctx, base=self.base), self.enviar(self.maria, "outro", "x2")])
        for segredo in (self.token, self.segredo, "X-Vendas"):
            self.assertNotIn(segredo, tudo)

    def test_servico_parado_nao_quebra_a_aba(self):
        self.con.execute("UPDATE batimento SET em = '2000-01-01T00:00:00+00:00' WHERE id = 1")
        r = self.mod.montar(self.ctx, base=self.base)
        self.assertEqual(r["abas"][1]["blocos"][0]["titulo"], "Serviço parado")
        self.assertIn("parado", self.enviar(self.maria)["mensagem"])
        self.assertEqual(self.falso.envios(), 0)


class TesteEnvioManual(Conversas):
    def test_envio_pelo_portao_com_origem_manual_e_chave_combinada(self):
        r = self.enviar(self.maria, "ola", "x1")
        self.assertEqual((r["ok"], r["mensagem"]), (True, "Mensagem enviada."))
        self.assertEqual([(e["telefone"], e["conteudo"]) for e in self.falso.entregues],
                         [("5511900000001", "ola")])
        (linha,) = self.envios()
        self.assertEqual((linha["origem"], linha["estado"], linha["chave_dedupe"]),
                         ("manual", "enviado", "manual:x1:%d" % self.maria))

    def test_mesmo_id_para_duas_conversas_sao_dois_envios(self):
        self.assertTrue(self.enviar(self.maria, "ola", "mesmo")["ok"])
        self.assertTrue(self.enviar(self.joao, "ola", "mesmo")["ok"])   # id da tela vem só do texto
        self.assertEqual(self.falso.envios(), 2)
        self.assertEqual(sorted(e["chave_dedupe"] for e in self.envios()),
                         ["manual:mesmo:%d" % self.maria, "manual:mesmo:%d" % self.joao])

    def test_duplo_clique_na_mesma_conversa_envia_uma_vez(self):
        self.assertEqual(self.enviar(self.maria)["mensagem"], "Mensagem enviada.")
        segundo = self.enviar(self.maria)
        self.assertEqual(self.falso.envios(), 1)
        self.assertEqual(len(self.envios()), 1)
        self.assertIn("clique repetido", segundo["mensagem"])

    def test_id_da_tela_fora_do_formato_vira_hash_e_ainda_deduplica(self):
        self.enviar(self.maria, "oi", "id com espaço / estranho")
        self.enviar(self.maria, "oi", "id com espaço / estranho")
        self.assertEqual(self.falso.envios(), 1)

    def test_pedidos_ruins_nao_chamam_o_conector(self):
        self.assertFalse(self.enviar(self.maria, "   ")["ok"])
        self.assertFalse(self.agir("enviar_mensagem", conversa_id=self.maria, texto="oi")["ok"])   # sem id_cliente
        self.assertFalse(self.enviar(9999)["ok"])
        self.assertFalse(self.agir("enviar_mensagem", texto="oi", id_cliente="a")["ok"])
        self.assertEqual(self.falso.envios(), 0)

    def test_optout_sem_liberar_e_negado_e_o_conector_nao_e_chamado(self):
        r = self.enviar(self.ana)
        self.assertEqual(r["ok"], False)
        self.assertIn("pediu para sair", r["mensagem"])
        self.assertEqual(self.falso.envios(), 0)
        (linha,) = self.envios()
        self.assertEqual((linha["estado"], linha["motivo"]), ("negado", "optout_pede_confirmacao"))

    def test_liberar_vale_para_uma_mensagem(self):
        self.assertTrue(self.agir("liberar_saida", conversa_id=self.ana)["ok"])
        self.assertTrue(self.enviar(self.ana, "so uma", "b1")["ok"])
        self.assertEqual(self.falso.envios(), 1)
        depois = self.enviar(self.ana, "outra", "b2")
        self.assertFalse(depois["ok"])
        self.assertEqual(self.falso.envios(), 1)

    def test_liberar_so_para_quem_saiu(self):
        r = self.agir("liberar_saida", conversa_id=self.maria)
        self.assertEqual(r["ok"], False)
        self.assertIsNone(banco.ler_config(self.con, "liberado_contato"))

    def test_botao_de_liberar_pede_confirmacao_na_tela(self):
        self.agir("abrir_conversa", conversa_id=self.ana)
        botoes = {b["acao"]: b for b in self.tipos(self.aba(), "conversa")[0]["botoes"]}
        self.assertIn("UMA mensagem", botoes["liberar_saida"]["confirmar"])

    def test_negado_por_teto_mostra_motivo_em_portugues(self):
        for i in range(8):
            self.assertTrue(self.enviar(self.maria, "t%d" % i, "t%d" % i)["ok"])
        r = self.enviar(self.maria, "t9", "t9")
        self.assertEqual(r["ok"], False)
        self.assertIn("último minuto", r["mensagem"])
        self.assertEqual(self.falso.envios(), 8)

    def test_incerto_diz_que_nao_sabe_e_nao_manda_de_novo(self):
        self.falso.modo_envio = "aceitar_e_cair"
        r = self.enviar(self.maria)
        self.assertEqual(r["ok"], False)
        self.assertIn("Não sei se a mensagem saiu", r["mensagem"])
        self.falso.modo_envio = "ok"
        self.enviar(self.maria)   # mesmo id: o portão não deixa sair de novo
        self.assertEqual(self.falso.envios(), 1)

    def test_mensagem_enviada_aparece_na_conversa_com_estado(self):
        self.falso.modo_envio = "timeout"
        self.enviar(self.maria, "oi maria")
        self.agir("abrir_conversa", conversa_id=self.maria)
        ultima = self.tipos(self.aba(), "conversa")[0]["mensagens"][-1]
        self.assertEqual((ultima["de"], ultima["texto"], ultima["estado"]), ("eu", "oi maria", "incerto"))
        self.assertIn("não confirmou", ultima["nota"])


class TesteIncertos(Conversas):
    def incerto(self):
        self.falso.modo_envio = "timeout"
        self.enviar(self.maria, "oi maria")
        self.falso.modo_envio = "ok"
        return self.envios()[0]["id"]

    def test_lista_de_incertos_com_as_duas_acoes_e_confirmacao(self):
        envio = self.incerto()
        bloco = [b for b in self.tipos(self.aba(), "conversa") if b["id"] == "incertos"][0]
        self.assertEqual([(b["acao"], b["dados"]) for b in bloco["botoes"]],
                         [("reenviar_envio", {"envio_id": envio}), ("descartar_envio", {"envio_id": envio})])
        self.assertTrue(all(b["confirmar"] for b in bloco["botoes"]))
        self.assertIn("****0001", bloco["mensagens"][0]["texto"])
        self.assertNotIn("5511900000001", json.dumps(bloco))

    def test_reenviar_volta_a_mesma_linha_sem_chave_nova(self):
        envio = self.incerto()
        antes = self.envios()
        r = self.agir("reenviar_envio", envio_id=envio)
        self.assertEqual((r["ok"], self.falso.envios()), (True, 2))
        (depois,) = self.envios()
        self.assertEqual((depois["id"], depois["chave_dedupe"], depois["estado"]),
                         (envio, antes[0]["chave_dedupe"], "enviado"))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM tentativas WHERE envio_id = ?", (envio,))
                         .fetchone()[0], 2)

    def test_reenviar_duas_vezes_nao_duplica(self):
        envio = self.incerto()
        self.agir("reenviar_envio", envio_id=envio)
        segundo = self.agir("reenviar_envio", envio_id=envio)
        self.assertEqual((segundo["ok"], self.falso.envios()), (False, 2))

    def test_descartar_marca_nao_enviado_sem_enviar(self):
        envio = self.incerto()
        r = self.agir("descartar_envio", envio_id=envio)
        self.assertEqual((r["ok"], self.falso.envios()), (True, 1))
        (linha,) = self.envios()
        self.assertEqual((linha["estado"], linha["motivo"]), ("falhou", "descartado_pelo_dono"))
        self.assertEqual(self.con.execute("SELECT estado FROM tentativas WHERE envio_id = ?", (envio,))
                         .fetchone()[0], "falhou")
        self.assertFalse(self.agir("descartar_envio", envio_id=envio)["ok"])   # já decidido
        self.assertEqual(self.tipos([b for b in self.aba()], "conversa"), [])   # some da lista de incertos

    def test_reenviar_a_quem_saiu_depois_exige_liberar(self):
        self.falso.modo_envio = "timeout"
        self.agir("liberar_saida", conversa_id=self.ana)
        self.enviar(self.ana, "tchau", "z1")
        self.falso.modo_envio = "ok"
        envio = self.envios()[0]["id"]
        negado = self.agir("reenviar_envio", envio_id=envio)
        self.assertEqual((negado["ok"], self.falso.envios()), (False, 1))
        self.assertEqual(self.envios()[0]["estado"], "incerto")   # negado no reenvio não muda a linha
        self.agir("liberar_saida", conversa_id=self.ana)
        self.assertTrue(self.agir("reenviar_envio", envio_id=envio)["ok"])
        self.assertEqual(self.falso.envios(), 2)

    def test_envio_inexistente_ou_invalido(self):
        self.assertFalse(self.agir("reenviar_envio", envio_id=999)["ok"])
        self.assertFalse(self.agir("descartar_envio", envio_id="abc")["ok"])
        self.assertEqual(self.falso.envios(), 0)


class TesteModo(Conversas):
    def modo(self, conversa):
        return self.con.execute("SELECT modo, precisa_de_voce, pausada_ate FROM conversas WHERE id = ?",
                                (conversa,)).fetchone()

    def test_assumir_e_devolver(self):
        self.assertTrue(self.agir("assumir_conversa", conversa_id=self.maria)["ok"])
        self.assertEqual(tuple(self.modo(self.maria))[:2], ("humano", 0))
        self.agir("abrir_conversa", conversa_id=self.maria)
        self.assertEqual([b["acao"] for b in self.tipos(self.aba(), "conversa")[0]["botoes"]], ["devolver_ia"])
        self.con.execute("UPDATE conversas SET pausada_ate = '2999-01-01T00:00:00+00:00' WHERE id = ?",
                         (self.maria,))
        self.assertTrue(self.agir("devolver_ia", conversa_id=self.maria)["ok"])
        self.assertEqual(tuple(self.modo(self.maria)), ("ia", 0, None))

    def test_conversa_inexistente_e_modo_invalido(self):
        self.assertFalse(self.agir("assumir_conversa", conversa_id=9999)["ok"])
        codigo, _ = self.mod.cliente.chamar(self.ctx, "POST", "/conversas/%d/modo" % self.maria,
                                            {"modo": "root"}, base=self.base)
        self.assertEqual(codigo, 400)
        self.assertEqual(self.modo(self.maria)["modo"], "ia")


if __name__ == "__main__":
    unittest.main()
