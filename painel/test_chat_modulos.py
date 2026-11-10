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


class TesteResponderComRegrasDosModulos(test_chat.Base):
    """Responder acorda a sessão com as travas de quando ela COMEÇOU: regra de módulo nova ou módulo
    quebrado recusa (409) sem parar nem acordar nada."""
    _modulo = TesteMascaraDoChat._modulo

    def comecar(self, lc):
        i = lc.iniciar("chat.x", {"pedido": "oi"})["id"]
        lc.execucoes(forcar=True)  # aprende o sessionId
        for a in self.cli.agentes:
            if a["id"] == i:
                a.update(state="done", status="idle")
        lc.esquecer_agentes()
        return i

    def nada_parado_nem_acordado(self, i):
        chamadas = [c[0] for c in self.cli.chamadas]
        self.assertNotIn(["claude", "stop", i], chamadas)
        self.assertEqual([c for c in chamadas if "--resume" in c], [])

    def recusa(self, lc, i):
        with self.assertRaises(lancador.ErroAcao) as erro:
            lc.responder(i, "e agora?")
        self.assertEqual(erro.exception.codigo, 409)
        self.nada_parado_nem_acordado(i)
        return erro.exception.mensagem

    def test_modulo_quebrado_recusa_responder(self):
        i = self.comecar(self.lanc())
        lc = self._modulo("resp_ruim", 'INFO = {"negar": "Bash(*)"}\ndef montar(ctx):\n    return {}\n')
        self.assertIn("resp_ruim", self.recusa(lc, i))
        self.assertFalse(lc.execucao(i)["pode_responder"])

    def test_modulo_ligado_depois_recusa_responder(self):
        i = self.comecar(self.lanc())
        lc = self._modulo("resp_novo", 'INFO = {"negar": ["mcp__servico__apagar"]}\n')
        self.assertFalse(lc.execucao(i)["pode_responder"])
        self.assertIn("mudaram", self.recusa(lc, i))

    def test_mesmas_regras_responde(self):
        lc = self._modulo("resp_igual", 'INFO = {"negar": ["mcp__servico__apagar"]}\n')
        i = self.comecar(lc)
        self.assertEqual(lc.achar(i)["negar_modulos"], ["mcp__servico__apagar"])
        self.assertTrue(lc.execucao(i)["pode_responder"])
        self.assertEqual(lc.responder(i, "e agora?")["estado"], "rodando")
        self.assertEqual(len([c for c in self.bg() if "--resume" in c]), 1)

    def _sem_chave(self, lc, i):
        with lc.registro.trava():
            regs = lc.registro.ler()
            for r in regs:
                r.pop("negar_modulos", None)
            lc.registro.gravar(regs)

    def test_registro_antigo_sem_regras_responde(self):
        lc = self.lanc()
        i = self.comecar(lc)
        self._sem_chave(lc, i)
        self.assertTrue(lc.execucao(i)["pode_responder"])
        self.assertEqual(lc.responder(i, "e agora?")["estado"], "rodando")

    def test_registro_antigo_com_regra_nova_recusa(self):
        lc = self.lanc()
        i = self.comecar(lc)
        self._sem_chave(lc, i)
        lc = self._modulo("resp_antigo", 'INFO = {"negar": ["Bash(rm -rf *)"]}\n')
        self.assertFalse(lc.execucao(i)["pode_responder"])
        self.recusa(lc, i)

    def test_nome_da_sessao_mascarado_antes_do_corte(self):
        pedido = "ligue agora para o cliente no numero 11 98765-4321 e confirme"
        lc = self.lanc()
        ex = lc.iniciar("chat.x", {"pedido": pedido})
        cmd = self.bg()[-1]
        for nome in (cmd[cmd.index("-n") + 1], lc.achar(ex["id"])["nome"], ex["nome"]):
            self.assertNotIn("98765", nome)
        self.assertEqual(lc.achar(ex["id"])["params"]["pedido"], pedido)  # duplicata compara o cru
        with self.assertRaises(lancador.ErroAcao) as erro:
            lc.iniciar("chat.x", {"pedido": pedido})
        self.assertEqual(erro.exception.codigo, 409)


if __name__ == "__main__":
    unittest.main()
