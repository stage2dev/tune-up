"""Conhecimento e tom (servico/conhecimento.py): instruções na ordem regras, métodos, oferta, tom; sem oferta.md a IA
fica desligada e nenhuma chamada sai; arquivos acima do limite avisados; regras fixas sem se apresentar como
assistente/IA e a 1ª resposta sai sem apresentação; metodos-de-venda.md com 8 a 12 métodos e sem citações; aba IA
mostra o que falta."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import re  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, cerebro, conhecimento  # noqa: E402
from testes.openai_falsa import resposta_texto  # noqa: E402
from testes.test_aba_ia import Aba  # noqa: E402
from testes.test_cerebro import Base  # noqa: E402

PLUGIN = os.path.dirname(AQUI)


def gravar(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


class Projeto(Base):
    def vendas(self, nome, texto):
        gravar(os.path.join(conhecimento.pasta_vendas(self.projeto), nome), texto)

    def sistema(self):
        return self.falsa.chamadas_chat()[0]["corpo"]["messages"][0]["content"]


class TesteOrdem(Projeto):
    def test_instrucoes_na_ordem_regras_metodos_oferta_tom(self):
        self.vendas("oferta.md", "OFERTA-UNICA-123")
        self.vendas("tom.md", "TOM-UNICO-456")
        self.falsa.fila = [resposta_texto("Oi!")]
        self.responder()
        s = self.sistema()
        pos = [s.index(conhecimento.REGRAS), s.index("MÉTODOS DE VENDA"), s.index("OFERTA-UNICA-123"),
               s.index("TOM-UNICO-456")]
        self.assertEqual(pos, sorted(pos))
        self.assertIn("Uma pergunta por vez", s)  # texto do arquivo do plugin

    def test_sem_tom_o_resto_segue(self):
        self.falsa.fila = [resposta_texto("Oi!")]
        self.responder()
        self.assertNotIn("TOM DE VOZ", self.sistema())
        self.assertIn("OFERTA", self.sistema())


class TesteSemOferta(Projeto):
    def test_sem_oferta_a_ia_fica_desligada_sem_chamar_a_openai(self):
        os.remove(os.path.join(conhecimento.pasta_vendas(self.projeto), "oferta.md"))
        self.falsa.fila = [resposta_texto("Custa R$ 1!")]
        r = self.responder()
        self.assertIsNone(r["texto"])
        self.assertEqual(r["motivo"], "sem_oferta")
        self.assertEqual(self.falsa.chamadas_chat(), [])
        self.assertEqual(self.precisa(), 1)

    def test_oferta_vazia_ou_grande_demais_tambem_desliga(self):
        for texto, aviso in (("   \n", "vazio"), ("x" * (conhecimento.LIMITE_BYTES + 1), "passa de 20 KB")):
            self.vendas("oferta.md", texto)
            c = conhecimento.ler(self.projeto)
            self.assertIsNone(c["oferta"])
            self.assertTrue(any(aviso in a for a in c["avisos"]), c["avisos"])
            self.assertIsNone(self.responder()["texto"])
        self.assertEqual(self.falsa.chamadas_chat(), [])

    def test_tom_grande_demais_e_ignorado_com_aviso(self):
        self.vendas("tom.md", "y" * (conhecimento.LIMITE_BYTES + 1))
        c = conhecimento.ler(self.projeto)
        self.assertIsNone(c["tom"])
        self.assertTrue(any("tom.md passa de 20 KB" in a for a in c["avisos"]))
        self.assertIsNotNone(c["oferta"])

    @unittest.skipIf(os.name == "nt", "link simbólico exige privilégio no Windows")
    def test_oferta_link_simbolico_para_fora_e_ignorada(self):
        fora = os.path.join(self.tmp, "fora.md")
        gravar(fora, "segredo")
        alvo = os.path.join(conhecimento.pasta_vendas(self.projeto), "oferta.md")
        os.remove(alvo)
        os.symlink(fora, alvo)
        c = conhecimento.ler(self.projeto)
        self.assertIsNone(c["oferta"])
        self.assertTrue(any("fora de .tune-up" in a for a in c["avisos"]))

    def test_pacote_do_painel_json_e_usado(self):
        gravar(os.path.join(self.projeto, ".tune-up", "painel.json"), '{"pacote": "meu-pacote"}')
        self.assertTrue(conhecimento.pasta_vendas(self.projeto).endswith(
            os.path.join(".tune-up", "meu-pacote", "vendas")))


class TesteSemApresentacao(Projeto):
    def test_regras_fixas_proibem_se_apresentar_e_mandam_pedir_humano(self):
        r = conhecimento.REGRAS.lower()
        self.assertIn("nunca se apresente como assistente virtual", r)
        self.assertIn("pedir_humano", r)
        self.assertIn("não negue", r)
        self.assertIn("sair", r)
        self.assertIn("não esteja na oferta", r)
        for frase in ("sou um assistente", "sou uma ia", "sou um robô", "sou o assistente virtual",
                      "sou uma inteligência", "olá, sou a"):
            self.assertNotIn(frase, r)

    def test_primeira_mensagem_sai_sem_apresentacao(self):
        self.falsa.fila = [resposta_texto("Oi! Que bom falar com você. O que você procura?")]
        r = self.cerebro.responder(self.con, self.conversa, [{"role": "user", "content": "Oi"}])
        self.assertEqual(r["texto"], "Oi! Que bom falar com você. O que você procura?")
        s = self.sistema().lower()
        self.assertNotRegex(s, r"(apresente-se|se apresente) como (um |uma )?(assistente|ia|robô)(?! virtual, robô)")
        self.assertNotIn("assistente virtual da", s)
        self.assertNotIn("sou um assistente", s)


class TesteArquivoDeMetodos(unittest.TestCase):
    def texto(self):
        with open(os.path.join(PLUGIN, "conhecimento", "metodos-de-venda.md"), encoding="utf-8") as f:
            return f.read()

    def test_de_8_a_12_metodos_com_titulo(self):
        n = len(re.findall(r"^## \S", self.texto(), re.M))
        self.assertTrue(8 <= n <= 12, n)

    def test_sem_bloco_de_citacao_nem_autor(self):
        t = self.texto()
        self.assertIsNone(re.search(r"^\s*>", t, re.M))
        self.assertNotRegex(t, r"[\"“”«»]")
        self.assertIsNone(re.search(r"\b(segundo|de acordo com|autor|livro)\b", t, re.I))

    def test_exemplos_existem_e_links_e_json_valido(self):
        import json
        for nome in ("oferta.md", "tom.md", "links.json"):
            self.assertTrue(os.path.isfile(os.path.join(PLUGIN, "conhecimento", "exemplos", nome)), nome)
        with open(os.path.join(PLUGIN, "conhecimento", "exemplos", "links.json"), encoding="utf-8") as f:
            self.assertIsInstance(json.load(f), dict)


class TesteAba(Aba):
    def setUp(self):
        super().setUp()
        self.app.raiz = self.projeto

    def textos(self):
        return " ".join(str(b) for b in self.aba())

    def test_aba_mostra_o_que_falta(self):
        t = self.textos()
        self.assertIn("falta: a IA fica desligada", t)
        self.assertIn("a IA não manda link", t)
        self.assertIn("Falta o oferta.md", t)

    def test_aba_com_tudo_pronto_sem_aviso(self):
        gravar(os.path.join(conhecimento.pasta_vendas(self.projeto), "oferta.md"), "Curso por R$ 100")
        gravar(os.path.join(conhecimento.pasta_vendas(self.projeto), "links.json"), '{"a": "https://x.example/a"}')
        t = self.textos()
        self.assertNotIn("Atenção nos arquivos da IA", t)
        self.assertIn("1 link(s)", t)

    def test_estado_nao_vaza_conteudo(self):
        gravar(os.path.join(conhecimento.pasta_vendas(self.projeto), "oferta.md"), "SEGREDO-DA-OFERTA")
        self.assertNotIn("SEGREDO-DA-OFERTA", str(self.estado()))


if __name__ == "__main__":
    unittest.main()
