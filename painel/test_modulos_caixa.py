"""conferir(): bloco caixa (caixa de entrada), alerta da aba e atualizar_em. Nada chama o claude."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import unittest  # noqa: E402

import modulos  # noqa: E402

INF = {"id": "m", "titulo": "M"}
LINHA = {"id": "c1", "titulo": "Contato Um", "detalhe": "oi", "nao_lidas": 2, "ativa": True}


def tela(blocos=None, **extra):
    aba = {"id": "a", "titulo": "A", "blocos": blocos or []}
    aba.update(extra.pop("aba", {}))
    return dict({"abas": [aba]}, **extra)


class TesteCaixa(unittest.TestCase):
    def test_caixa_boa_passa_inteira(self):
        b = {"tipo": "caixa", "conversas": [LINHA], "abrir": {"acao": "abrir", "dados_fixos": {"x": 1}},
             "conversa": {"mensagens": [{"id": "1", "de": "contato", "texto": "[audio]", "tipo": "audio", "quando": "q"}]},
             "vazio": "nada", "extra_desconhecido": 1}
        s = modulos.conferir(tela([b]), INF)
        self.assertEqual(s["abas"][0]["blocos"], [b])
        self.assertEqual(s["avisos"], [])

    def test_caixa_sem_abrir_ou_sem_lista_sai_com_aviso(self):
        ruins = [{"tipo": "caixa", "conversas": [LINHA]},
                 {"tipo": "caixa", "conversas": [LINHA], "abrir": {"acao": ""}},
                 {"tipo": "caixa", "conversas": [LINHA], "abrir": "abrir"},
                 {"tipo": "caixa", "conversas": "x", "abrir": {"acao": "abrir"}}]
        for b in ruins:
            s = modulos.conferir(tela([b, {"tipo": "texto", "texto": "fica"}]), INF)
            self.assertEqual([x["tipo"] for x in s["abas"][0]["blocos"]], ["texto"], b)
            self.assertTrue(any("caixa" in a for a in s["avisos"]), s["avisos"])

    def test_linha_ruim_sai_e_conversa_nao_objeto_some(self):
        b = {"tipo": "caixa", "abrir": {"acao": "abrir"}, "conversa": ["nao"],
             "conversas": [LINHA, {"id": "", "titulo": "x"}, {"id": "c3"}, {"id": 4, "titulo": "y"}, "z"]}
        s = modulos.conferir(tela([b]), INF)
        out = s["abas"][0]["blocos"][0]
        self.assertEqual(out["conversas"], [LINHA])
        self.assertNotIn("conversa", out)
        self.assertTrue(any("conversa sem" in a for a in s["avisos"]))

    def test_alerta_da_aba(self):
        for valor, esperado in ((3, 3), (2.7, 2), (0, None), (-1, None), ("3", None), (True, None), (float("nan"), None)):
            aba = modulos.conferir(tela(aba={"alerta": valor}), INF)["abas"][0]
            self.assertEqual(aba.get("alerta"), esperado, valor)

    def test_atualizar_em_preso_em_2_a_60(self):
        for valor, esperado in ((5, 5), (1, 2), (0, 2), (-3, 2), (600, 60), (2.5, 2.5)):
            self.assertEqual(modulos.conferir(tela(atualizar_em=valor), INF)["atualizar_em"], esperado, valor)
        for valor in ("5", None, True, float("inf"), float("nan")):
            s = modulos.conferir(tela(atualizar_em=valor), INF)
            self.assertNotIn("atualizar_em", s, valor)
            json.dumps(s, allow_nan=False)  # nada fora de JSON escapa


if __name__ == "__main__":
    unittest.main()
