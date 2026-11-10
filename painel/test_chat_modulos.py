"""Chat x Parte A: o pedido e as falas inteiras (?inteiro=1) saem mascarados; nível do chat leva o
INFO["negar"] dos módulos e não dispara com módulo ligado quebrado (409)."""
import json
import os
import unittest

import lancador
import test_chat
import transcricao

EMAIL, TEL = "fulana.teste@exemplo.com", "+55 11 98765-4321"


class TesteMascaraDoChat(test_chat.Base):
    setUp = test_chat.TesteRotasDoChat.setUp
    pedir = test_chat.TesteRotasDoChat.pedir

    def test_pedido_e_fala_inteira_mascarados(self):
        pedido = "me liga no %s ou escreve para %s" % (TEL, EMAIL)
        st, d = self.pedir("POST", "/api/execucoes", {"acao": "chat.x", "params": {"pedido": pedido}})
        self.assertEqual(st, 201)
        i = d["execucao"]["id"]
        for ex in (d["execucao"], self.pedir("GET", "/api/execucoes")[1]["execucoes"][0]):
            texto = json.dumps(ex, ensure_ascii=False)
            self.assertNotIn(EMAIL, texto)
            self.assertNotIn("98765-4321", texto)
            self.assertIn("me liga no", ex["params"]["pedido"])
        reg = self.lc.achar(i)
        self.assertEqual(reg["params"]["pedido"], pedido)  # o registro guarda cru: só a saída é mascarada

        self.lc.execucoes(forcar=True)
        pasta = os.path.join(self.tmp, "proj", transcricao.pasta_do_projeto(self.tmp))
        os.makedirs(pasta)
        with open(os.path.join(pasta, i + "-1111-2222-3333-444455556666.jsonl"), "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "anotei " + EMAIL + " " + "x " * 400}]}}) + "\n")
        fala = self.pedir("GET", "/api/execucoes/%s/eventos?desde=0&inteiro=1" % i)[1]["eventos"][0]["texto"]
        self.assertTrue(fala.startswith("anotei "))
        self.assertNotIn(EMAIL, fala)


    def _modulo(self, mid, codigo):
        pasta = os.path.join(self.tmp, "pacote", "modulos", mid)
        os.makedirs(pasta)
        with open(os.path.join(pasta, "modulo.py"), "w", encoding="utf-8") as f:
            f.write(codigo)
        return self.lanc(pacote_ok=True, modulos=[mid])

    def test_nivel_do_chat_leva_negar_dos_modulos(self):
        lc = self._modulo("chat_neg_ok", 'INFO = {"negar": ["Bash(rm -rf *)"]}\ndef montar(ctx):\n    return {}\n')
        lc.iniciar("chat.x", {"pedido": "oi"})
        cmd = self.bg()[0]
        self.assertEqual(cmd[cmd.index("--model") + 1], "fable")
        self.assertEqual(cmd[cmd.index("--effort") + 1], "xhigh")
        self.assertIn("Bash(rm -rf *)", json.loads(cmd[cmd.index("--settings") + 1])["permissions"]["deny"])

    def test_nivel_do_chat_com_modulo_quebrado_da_409(self):
        lc = self._modulo("chat_neg_ruim", 'INFO = {"negar": "Bash(*)"}\ndef montar(ctx):\n    return {}\n')
        with self.assertRaises(lancador.ErroAcao) as erro:
            lc.iniciar("chat.x", {"pedido": "oi"})
        self.assertEqual(erro.exception.codigo, 409)
        self.assertEqual(self.bg(), [])


if __name__ == "__main__":
    unittest.main()
