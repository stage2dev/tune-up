"""Modelo e esforço em qualquer ação (não só nos níveis do chat): validação, argv do `--bg` e registro.

Nada chama o claude de verdade: o CLI é falso.
"""
import json
import os
import unittest

import catalogo
import test_chat

DEV = {"id": "dev.teste", "grupo": "dev", "titulo": "Teste", "risco": "codigo", "prompt": "/x {t}",
       "params": [{"nome": "t", "tipo": "texto", "max": 100}], "modelos": "haiku", "esforco": "low"}


class TesteModeloEsforcoEmQualquerAcao(test_chat.Base):
    def test_valida_fora_do_chat(self):
        a = catalogo.validar_acao(DEV)
        self.assertEqual((a["grupo"], a["modelos"], a["esforco"]), ("dev", ["haiku"], "low"))
        for e in catalogo.ESFORCOS:
            self.assertEqual(catalogo.validar_acao(dict(DEV, esforco=e))["esforco"], e)
        for ruim in ({"esforco": "turbo"}, {"esforco": "LOW"}, {"esforco": ["low"]}, {"esforco": ""},
                     {"modelos": "--model"}, {"modelos": "haiku opus"}, {"modelos": "a;b"}, {"modelos": "Haiku"},
                     {"modelos": ""}, {"modelos": ["x%d" % i for i in range(5)]}, {"modelos": {"a": 1}}):
            with self.assertRaises(ValueError, msg=repr(ruim)):
                catalogo.validar_acao(dict(DEV, **ruim))

    def test_acao_invalida_sai_do_catalogo_com_aviso(self):
        self.gravar_acoes([DEV, dict(DEV, id="dev.ruim", esforco="turbo")])
        acoes, avisos = catalogo.carregar_catalogo(os.path.join(self.tmp, "acoes"))
        self.assertEqual([a["id"] for a in acoes], ["dev.teste"])
        self.assertEqual(len(avisos), 1)
        self.assertIn("esforco", avisos[0])

    def test_dispara_com_model_e_effort_e_grava_os_dois(self):
        self.gravar_acoes([DEV])
        ex = self.lanc().iniciar("dev.teste", {"t": "oi"})
        cmd = self.bg()[0]
        self.assertEqual(cmd[cmd.index("--model") + 1], "haiku")
        self.assertEqual(cmd[cmd.index("--effort") + 1], "low")
        self.assertEqual(cmd[-1], "/x oi")
        self.assertEqual([c for c in self.cli.chamadas if c[0][1:2] == ["-p"]], [])  # um modelo só: sem sonda
        self.assertEqual((ex["modelo"], ex["esforco"]), ("haiku", "low"))
        lc = self.lanc()  # outro lançador relê o registro do disco
        reg = [r for r in lc.registro.ler() if r["id"] == ex["id"]][0]
        self.assertEqual((reg["acao"], reg["modelo"], reg["esforco"]), ("dev.teste", "haiku", "low"))
        self.assertEqual([(e["modelo"], e["esforco"]) for e in lc.execucoes(forcar=True)], [("haiku", "low")])

    def test_esforco_max_vai_no_argv(self):
        self.gravar_acoes([dict(DEV, esforco="max")])
        self.lanc().iniciar("dev.teste", {"t": "oi"})
        cmd = self.bg()[0]
        self.assertEqual(cmd[cmd.index("--effort") + 1], "max")
        self.assertNotIn("effortLevel", json.dumps(cmd))  # esforço vai só pela opção, não pelo --settings


if __name__ == "__main__":
    unittest.main()
