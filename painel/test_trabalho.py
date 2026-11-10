"""Pasta de trabalho criada pelo servidor, marcador {trabalho} e parâmetro texto_longo.

Nada chama o claude de verdade: o CLI é falso. A pasta de dados tem dois espaços seguidos e `[`.
"""
import json
import os
import re
import shlex
import unittest

import catalogo
import test_chat
import trabalho
import travas

TEXTO = "- primeira linha\n\nsegunda  linha com {chave}"
ACAO = {"id": "estudio.post", "grupo": "estudio", "titulo": "Post", "risco": "rascunho",
        "prompt": "Leia {briefing} e grave em {trabalho}/saida.png ({formato})",
        "params": [{"nome": "briefing", "tipo": "texto_longo"},
                   {"nome": "formato", "tipo": "escolha", "opcoes": ["post", "story"]}],
        "permitir": ["Edit({trabalho}/**)"],  # o CLI só casa caminho em regra Edit
        "negar": [{"ferramenta": "Write", "campo": "file_path", "entrada": "^(?!{trabalho}/)", "motivo": "fora"}]}


class TesteCatalogoTrabalho(unittest.TestCase):
    def test_texto_longo_valida(self):
        a = catalogo.validar_acao(ACAO)
        p = a["params"][0]
        self.assertEqual((p["tipo"], p["max"], p["linhas"]), ("texto_longo", 4000, True))
        grande = dict(ACAO, params=[dict(ACAO["params"][0], max=9000), ACAO["params"][1]])
        self.assertEqual(catalogo.validar_acao(grande)["params"][0]["max"], 4000)
        for ruim in ({"params": ACAO["params"] + [{"nome": "outro", "tipo": "texto_longo"}]},  # dois texto_longo
                     {"params": ACAO["params"] + [{"nome": "trabalho", "tipo": "texto"}]},  # nome reservado
                     {"nome_sessao": "Post {trabalho}"}):  # marcador só no prompt e nas travas
            with self.assertRaises(ValueError, msg=repr(ruim)):
                catalogo.validar_acao(dict(ACAO, **ruim))

    def test_valor_aceita_linhas_e_traco_e_respeita_max(self):
        a = catalogo.validar_acao(ACAO)
        v = catalogo.validar_params(a, {"briefing": TEXTO + "\r\n", "formato": "post"}, {})
        self.assertEqual(v["briefing"], TEXTO)
        for ruim in ("x" * 4001, "a\x00b", "a\x1bb"):
            with self.assertRaises(catalogo.ErroAcao):
                catalogo.validar_params(a, {"briefing": ruim, "formato": "post"}, {})

    def test_caminho_de_regra(self):
        self.assertEqual(trabalho.caminho_de_regra("/a  b/[x]/y*"), "//a  b/\\[x\\]/y\\*")
        self.assertEqual(trabalho.caminho_de_regra("C:\\Us er\\[t]"), "//c/Us er/\\[t\\]")


class TestePastaDeTrabalho(test_chat.Base):
    def setUp(self):
        test_chat.Base.setUp(self)
        self.dados = os.path.join(self.tmp, "da  dos [1]")
        self.gravar_acoes([ACAO, {"id": "dev.simples", "grupo": "dev", "titulo": "S", "risco": "leitura",
                                  "prompt": "/x {t}", "params": [{"nome": "t", "tipo": "texto"}]}])

    def lanc(self, **extra):
        return test_chat.Base.lanc(self, dados_dir=self.dados, **extra)

    def pastas(self):
        raiz = os.path.join(self.dados, "trabalhos")
        return sorted(os.listdir(raiz)) if os.path.isdir(raiz) else []

    def test_cria_pasta_resolve_marcador_e_grava_texto(self):
        lc = self.lanc()
        lc.iniciar("estudio.post", {"briefing": TEXTO, "formato": "post"})
        [tid] = self.pastas()
        self.assertTrue(re.match(r"^[0-9a-f]{12}$", tid))
        pasta = os.path.join(os.path.realpath(self.dados), "trabalhos", tid)
        with open(os.path.join(pasta, "entrada.md"), encoding="utf-8") as f:
            self.assertEqual(f.read(), TEXTO)
        with open(os.path.join(pasta, "entrada.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"acao": "estudio.post", "trabalho": tid,
                                            "params": {"briefing": "entrada.md", "formato": "post"}})
        cmd = self.bg()[0]
        self.assertEqual(cmd[-1], "Leia %s e grave em %s/saida.png (post)" % (os.path.join(pasta, "entrada.md"), pasta))
        self.assertNotIn("\n", "".join(cmd))
        conf = json.loads(cmd[cmd.index("--settings") + 1])
        self.assertEqual(conf["permissions"]["allow"], ["Edit(%s/**)" % trabalho.caminho_de_regra(pasta)])
        self.assertTrue(conf["permissions"]["allow"][0].startswith("Edit(//"))
        gancho = travas._decodificar(shlex.split(conf["hooks"]["PreToolUse"][0]["hooks"][0]["command"])[-1])
        self.assertEqual(gancho["n"][0]["entrada"], "^(?!%s/)" % re.escape(pasta))
        self.assertIsNone(travas.decidir(gancho, "Write", {"file_path": pasta + "/saida.png"}))
        for fora in (pasta + "x/a.png", os.path.dirname(pasta) + "/outro/a.png", "/tmp/a.png"):
            self.assertEqual(travas.decidir(gancho, "Write", {"file_path": fora}), ("deny", "fora"))
        reg = lc.achar(lc.execucoes()[0]["id"])
        self.assertEqual((reg["trabalho"], reg["params"]["briefing"]), (tid, TEXTO))

    def test_duplicata_nao_ve_o_id_do_trabalho(self):
        lc = self.lanc()
        lc.iniciar("estudio.post", {"briefing": TEXTO, "formato": "post"})
        with self.assertRaises(catalogo.ErroAcao) as c:
            lc.iniciar("estudio.post", {"briefing": TEXTO, "formato": "post"})
        self.assertEqual(c.exception.codigo, 409)
        self.assertEqual(len(self.pastas()), 1)  # a recusada nem criou pasta
        lc.iniciar("estudio.post", {"briefing": TEXTO + " outro", "formato": "post"})
        self.assertEqual(len(self.pastas()), 2)

    def test_disparo_que_falha_apaga_a_pasta(self):
        lc = self.lanc()
        self.cli.falhar_bg = True
        with self.assertRaises(catalogo.ErroAcao) as c:
            lc.iniciar("estudio.post", {"briefing": TEXTO, "formato": "post"})
        self.assertEqual(c.exception.codigo, 500)
        self.assertEqual(self.pastas(), [])
        self.cli.falhar_bg = False
        original = lc.rodar

        def explode(cmd, cwd, timeout):
            if cmd[1:2] == ["--bg"]:
                self.assertEqual(len(self.pastas()), 1)  # existe enquanto o CLI roda
                raise RuntimeError("caiu")
            return original(cmd, cwd, timeout)
        lc.rodar = explode
        with self.assertRaises(RuntimeError):
            lc.iniciar("estudio.post", {"briefing": TEXTO, "formato": "post"})
        self.assertEqual(self.pastas(), [])
        self.assertEqual(lc.execucoes(), [])

    def test_acao_sem_marcador_nao_cria_pasta(self):
        lc = self.lanc()
        ex = lc.iniciar("dev.simples", {"t": "oi"})
        self.assertEqual(self.pastas(), [])
        self.assertEqual(self.bg()[0][-1], "/x oi")
        self.assertEqual(lc.achar(ex["id"])["trabalho"], "")


if __name__ == "__main__":
    unittest.main()
