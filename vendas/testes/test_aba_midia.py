"""Mídia na aba Conversas e arquivo() do módulo (M4): bytes e mime de um serviço semeado, ref de outra forma recusada,
serviço de outro projeto ou parado = não encontrado, blocos de áudio pronta/pendente/falhou/expirada, imagem e
documento, prévias da lista, o botão de tentar de novo chega ao serviço e nenhum token ou caminho aparece."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import queue  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, midia, recebimento  # noqa: E402
from testes.test_aba_conexao import Aba  # noqa: E402
from testes.test_midia import INST, OGG, PDF, PNG, corpo  # noqa: E402

LEAD2 = "5511900000002"


class Midias(Aba):
    def setUp(self):
        super().setUp()
        banco.gravar_config(self.con, "instancia", INST)
        self.rec = recebimento.Recebimento(lambda: self.falso)
        recebimento.registrar_gancho(None)
        self.addCleanup(midia.registrar_baixador, None)
        self.contador = 0

    def chegou(self, tipo, conteudo, nome=None, baixar=True, de=None):
        self.contador += 1
        ident = "M%d" % self.contador
        if conteudo is not None:
            self.falso.midias[ident] = (conteudo, "image/png" if tipo == "imagem" else "x", nome)
        self.con.execute("BEGIN IMMEDIATE")
        depois = self.rec(self.con, INST, corpo(ident, tipo, **({"de": de} if de else {})), True)
        self.con.execute("COMMIT")
        if depois:
            depois(self.con)
        mid, mensagem = self.con.execute("SELECT d.id, d.mensagem_id FROM midias d JOIN mensagens m ON m.id = "
                                         "d.mensagem_id WHERE m.id_externo = ?", (ident,)).fetchone()
        if baixar:
            midia.baixar(lambda: banco.abrir(self.pasta), self.falso, self.pasta, mid)
        return mid, mensagem

    def estado(self, mid, estado, motivo=None):
        self.con.execute("UPDATE midias SET estado = ?, motivo = ? WHERE id = ?", (estado, motivo, mid))

    def mensagens(self):
        r = self.mod.montar(self.ctx, base=self.base)
        self.assertEqual(r["avisos"], [])
        caixa = [b for b in r["abas"][1]["blocos"] if b["tipo"] == "caixa"][0]
        return caixa, caixa.get("conversa", {}).get("mensagens", [])

    def abrir_conversa(self):
        cid = self.con.execute("SELECT id FROM conversas ORDER BY id LIMIT 1").fetchone()[0]
        self.assertTrue(self.mod.agir(self.ctx, "abrir_conversa", {"conversa_id": cid}, base=self.base)["ok"])


class TesteArquivo(Midias):
    def test_devolve_bytes_e_mime(self):
        mid, _ = self.chegou("audio", OGG)
        r = self.mod.arquivo(self.ctx, "m:%d" % mid, base=self.base)
        self.assertEqual((r["mime"], r["dados"]), ("audio/ogg", OGG))
        self.assertNotIn("baixar", r)

    def test_documento_vira_anexo_com_nome(self):
        mid, _ = self.chegou("documento", PDF, nome="proposta final.pdf")
        r = self.mod.arquivo(self.ctx, "m:%d" % mid, base=self.base)
        self.assertEqual((r["mime"], r["dados"], r["baixar"], r["nome"]), ("application/pdf", PDF, True,
                                                                           "proposta final.pdf"))

    def test_ref_de_outra_forma_recusada(self):
        mid, _ = self.chegou("audio", OGG)
        for ref in ("%d" % mid, "x:%d" % mid, "m:abc", "m:", "m:%d/../1" % mid, "m:-1", "m:%d " % mid, "m:%d\n" % mid, "M:%d" % mid,
                    "m:%d.ogg" % mid, "m:1234567890123", "", None, 7, "../%d" % mid):
            with self.assertRaises(FileNotFoundError, msg=repr(ref)):
                self.mod.arquivo(self.ctx, ref, base=self.base)

    def test_midia_que_nao_esta_pronta_ou_nao_existe_e_nao_encontrada(self):
        pendente, _ = self.chegou("audio", OGG, baixar=False)
        for ref in ("m:%d" % pendente, "m:99999"):
            with self.assertRaises(FileNotFoundError):
                self.mod.arquivo(self.ctx, ref, base=self.base)
        mid, _ = self.chegou("audio", OGG)
        self.estado(mid, "expirada", "retencao")
        with self.assertRaises(FileNotFoundError):
            self.mod.arquivo(self.ctx, "m:%d" % mid, base=self.base)

    def test_servico_de_outro_projeto_recusado_sem_pedir_o_token(self):
        mid, _ = self.chegou("audio", OGG)
        banco.gravar_config(self.con, "servico_marca", "outramarca0000000")
        with self.assertRaises(FileNotFoundError):
            self.mod.arquivo(self.ctx, "m:%d" % mid, base=self.base)

    def test_servico_parado_e_nao_encontrado(self):
        mid, _ = self.chegou("audio", OGG)
        self.parar_batimento()
        self.con.execute("UPDATE batimento SET em = '2000-01-01T00:00:00+00:00' WHERE id = 1")
        with self.assertRaises(FileNotFoundError):
            self.mod.arquivo(self.ctx, "m:%d" % mid, base=self.base)

    def test_leitura_para_no_teto(self):
        mid, _ = self.chegou("documento", PDF + b"x" * 5000, nome="a.pdf")
        antes = self.mod._arquivo.LIMITE
        self.addCleanup(setattr, self.mod._arquivo, "LIMITE", antes)
        self.mod._arquivo.LIMITE = 100
        r = self.mod.arquivo(self.ctx, "m:%d" % mid, base=self.base)
        self.assertEqual(len(r["dados"]), 101)   # um byte além do teto: o painel responde 413


class TesteBlocos(Midias):
    def test_audio_pronta_pendente_falhou_expirada(self):
        pronta, _ = self.chegou("audio", OGG)
        pendente, _ = self.chegou("audio", OGG, baixar=False)
        falhou, _ = self.chegou("audio", None)   # o conector não tem o arquivo: falha de verdade
        expirada, _ = self.chegou("audio", OGG)
        self.estado(expirada, "expirada", "retencao")
        self.assertEqual(self.con.execute("SELECT estado FROM midias WHERE id = ?", (falhou,)).fetchone()[0], "falhou")
        self.estado(falhou, "falhou", "indisponivel")   # falha que outra tentativa pode resolver
        self.abrir_conversa()
        _, msgs = self.mensagens()
        por_ref = {m["midia"]["ref"]: m["midia"] for m in msgs if "midia" in m}
        p = por_ref["m:%d" % pronta]
        self.assertEqual((p["tipo"], p["estado"]), ("audio", "pronta"))
        self.assertEqual(p["tamanho"], len(OGG))
        self.assertNotIn("aviso", p)
        self.assertNotIn("acao", p)
        self.assertEqual(por_ref["m:%d" % pendente]["estado"], "pendente")
        self.assertIn("Baixando", por_ref["m:%d" % pendente]["aviso"])
        f = por_ref["m:%d" % falhou]
        self.assertEqual(f["estado"], "falhou")
        self.assertTrue(f["aviso"])
        self.assertEqual(f["acao"], {"acao": "midia_baixar_de_novo", "dados": {"midia_id": falhou}})
        e = por_ref["m:%d" % expirada]
        self.assertEqual(e["estado"], "expirada")
        self.assertIn("30 dias", e["aviso"])
        self.assertNotIn("acao", e)

    def test_imagem_e_documento_e_transcricao(self):
        _, msg_audio = self.chegou("audio", OGG)
        imagem, _ = self.chegou("imagem", PNG)
        doc, _ = self.chegou("documento", PDF, nome="orcamento.pdf")
        self.con.execute("UPDATE mensagens SET transcricao = 'quero saber o preço' WHERE id = ?", (msg_audio,))
        self.con.execute("UPDATE midias SET duracao_s = 12.4 WHERE mensagem_id = ?", (msg_audio,))
        self.abrir_conversa()
        _, msgs = self.mensagens()
        audio = [m for m in msgs if m.get("tipo") == "audio"][0]
        self.assertEqual(audio["transcricao"], "quero saber o preço")
        self.assertEqual(audio["midia"]["duracao"], 12)
        self.assertEqual([m["midia"]["tipo"] for m in msgs if m.get("tipo") in ("imagem", "documento")],
                         ["imagem", "documento"])
        d = [m["midia"] for m in msgs if m.get("tipo") == "documento"][0]
        self.assertEqual((d["ref"], d["nome"], d["tamanho"]), ("m:%d" % doc, "orcamento.pdf", len(PDF)))
        self.assertEqual([m["midia"]["ref"] for m in msgs if m.get("tipo") == "imagem"], ["m:%d" % imagem])

    def test_mensagem_de_texto_nao_tem_midia(self):
        contato = banco.salvar_contato(self.con, "+55 11 90000-0001", nome="Maria")
        conversa = banco.abrir_conversa(self.con, contato)
        banco.registrar_mensagem(self.con, conversa, "entrada", "oi", id_externo="t1")
        self.abrir_conversa()
        _, msgs = self.mensagens()
        self.assertTrue(msgs)
        self.assertTrue(all("midia" not in m and "transcricao" not in m for m in msgs))

    def test_previa_na_lista(self):
        def detalhe():
            caixa, _ = self.mensagens()
            return caixa["conversas"][0]["detalhe"]
        _, m1 = self.chegou("audio", OGG)
        self.assertEqual(detalhe(), "Áudio")
        self.con.execute("UPDATE midias SET duracao_s = 12 WHERE mensagem_id = ?", (m1,))
        self.assertEqual(detalhe(), "Áudio (0:12)")
        self.con.execute("UPDATE mensagens SET transcricao = ? WHERE id = ?",
                         ("oi tudo bem queria saber o preço do plano mensal", m1))
        self.assertEqual(detalhe(), "Áudio (0:12): oi tudo bem queria saber o…")
        self.chegou("imagem", PNG)
        self.assertEqual(detalhe(), "Foto")
        self.chegou("documento", PDF, nome="proposta.pdf")
        self.assertEqual(detalhe(), "Documento: proposta.pdf")

    def test_nada_de_token_caminho_ou_pasta_nos_blocos(self):
        for tipo, conteudo in (("audio", OGG), ("imagem", PNG), ("documento", PDF)):
            self.chegou(tipo, conteudo, nome="a.pdf" if tipo == "documento" else None)
        self.chegou("audio", None)
        self.abrir_conversa()
        r = self.mod.montar(self.ctx, base=self.base)
        texto = json.dumps(r["abas"][1], ensure_ascii=False)   # aba Conversas (a de Leads mostra comando com caminho)
        for segredo in (self.token, self.pasta, self.tmp, os.path.join("midia", ""), "X-Vendas-Token"):
            self.assertNotIn(segredo, texto)
        for arq in self.con.execute("SELECT arquivo FROM midias WHERE arquivo IS NOT NULL"):
            self.assertNotIn(arq[0], texto)


class TesteTentarDeNovo(Midias):
    def test_chega_ao_servico_e_volta_a_pendente(self):
        falhou, _ = self.chegou("audio", None)
        fila = queue.Queue()
        midia.registrar_baixador(type("B", (), {"fila": fila, "garantir": lambda self: True})())
        r = self.mod.agir(self.ctx, "midia_baixar_de_novo", {"midia_id": falhou}, base=self.base)
        self.assertTrue(r["ok"], r)
        self.assertEqual(self.con.execute("SELECT estado FROM midias WHERE id = ?", (falhou,)).fetchone()[0],
                         "pendente")
        self.assertEqual(fila.get_nowait(), falhou)   # o pedido entrou na fila do serviço

    def test_midia_que_nao_falhou_ou_id_ruim_e_recusado(self):
        pronta, _ = self.chegou("audio", OGG)
        self.assertFalse(self.mod.agir(self.ctx, "midia_baixar_de_novo", {"midia_id": pronta}, base=self.base)["ok"])
        for ruim in (None, "abc", 0, -1, True):
            self.assertFalse(self.mod.agir(self.ctx, "midia_baixar_de_novo", {"midia_id": ruim},
                                           base=self.base)["ok"], repr(ruim))
        self.assertIn("midia_baixar_de_novo", self.mod.INFO["acoes"])


if __name__ == "__main__":
    unittest.main()
