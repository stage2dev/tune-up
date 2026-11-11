"""Comandos marca.aprovar / marca.editar do módulo estudio (plugin tune-up-studio) e a trava `requer`.

O módulo real é carregado por um módulo-ponte no projeto de teste. Nada chama o claude.
"""
import sys

sys.dont_write_bytecode = True

import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import unittest  # noqa: E402

import catalogo  # noqa: E402
import modulos  # noqa: E402
from test_dono import Base  # noqa: E402
from test_modulos import escrever  # noqa: E402

REAL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tune-up-studio", "painel",
                    "modulos", "estudio", "modulo.py")
PONTE = '''
import importlib.util
_s = importlib.util.spec_from_file_location("estudio_real", %r)
_m = importlib.util.module_from_spec(_s)
_s.loader.exec_module(_m)
INFO = _m.INFO
montar = _m.montar
agir = _m.agir
''' % REAL
# ação de teste mínima: o estúdio real só ganha ação com `requer` no item 5.1
ACAO = catalogo.validar_acao({"id": "estudio.teste", "grupo": "estudio", "titulo": "Teste", "risco": "leitura",
                              "prompt": "/x", "requer": "estudio.marca", "sandbox": True,
                              "params": []})
MARCA = {"versao": 1, "modo": "marca", "campos": {
    "nome": {"valor": "Forno", "fonte": "package.json:2", "confianca": "media", "travado": False},
    "cores.primary": {"valor": "#112233", "fonte": "a.css:1", "confianca": "alta", "travado": False}}}


class TesteMarca(Base):
    def setUp(self):
        super().setUp()
        escrever(os.path.join(self.tmp, ".tune-up", "painel-projeto", "modulos", "estudio", "modulo.py"), PONTE)
        self.cfg["raiz"] = self.tmp
        modulos.esquecer()
        self.pasta = os.path.join(self.tmp, ".tune-up", "estudio", "marca")
        self.marca = os.path.join(self.pasta, "marca.json")
        escrever(self.marca, json.dumps(MARCA))

    def agir(self, acao, dados):
        return modulos.agir(self.cfg, "estudio", acao, dados)

    def sha(self):  # o sha256 curto que a aba Marca mostra
        with open(self.marca, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()[:12]

    def aprovar(self):
        return self.agir("marca.aprovar", {"confirmar": True, "sha256": self.sha()})

    def recusa(self):
        with self.assertRaises(modulos.ErroModulo) as e:
            modulos.antes_de_disparar(self.cfg, ACAO)
        return e.exception

    def test_409_sem_aprovacao_e_libera_depois_do_comando(self):
        self.assertEqual(self.recusa().codigo, 409)
        cod, d = self.aprovar()
        self.assertEqual((cod, d["resultado"]["feito"]), (200, True))
        modulos.antes_de_disparar(self.cfg, ACAO)  # não levanta
        self.assertIs(self.aprovado(), True)

    def test_aprovar_sem_confirmar_ou_sem_marca_nao_grava(self):
        self.assertIs(self.agir("marca.aprovar", {"confirmar": False})[1]["resultado"]["feito"], False)
        os.remove(self.marca)
        self.assertIs(self.agir("marca.aprovar", {"confirmar": True, "sha256": "0" * 12})[1]["resultado"]["feito"],
                      False)
        self.assertFalse(os.path.exists(self.arq))
        self.assertEqual(self.recusa().codigo, 409)

    def test_marca_json_aprovado_pela_sessao_nao_libera(self):
        for extra in ({"aprovado": True}, {"aprovado_pelo_dono": True}):
            escrever(self.marca, json.dumps(dict(MARCA, **extra)))
            escrever(os.path.join(self.cfg["dados_dir"], "marca.json"), json.dumps(extra))
            self.assertEqual(self.recusa().codigo, 409)
        self.assertFalse(os.path.exists(self.arq))

    def test_editar_trava_campo_com_fonte_dono_e_derruba_aprovacao(self):
        self.aprovar()
        cod, d = self.agir("marca.editar", {"campo": "cores.primary", "valor": "rgb(255, 0, 0)"})
        self.assertEqual((cod, d["resultado"]["feito"]), (200, True))
        with open(self.marca, encoding="utf-8") as f:
            c = json.load(f)["campos"]["cores.primary"]
        self.assertEqual((c["valor"], c["fonte"], c["travado"]), ("#FF0000", "dono", True))
        self.assertEqual(self.recusa().codigo, 409)  # editar tira a aprovação

    def test_editar_recusa_campo_ruim_cor_ruim_e_campo_extra(self):
        for dados in ({"campo": "x", "valor": "a"}, {"campo": "cores.bg", "valor": "var(--x)"},
                      {"campo": "nome", "valor": ""}):
            self.assertIs(self.agir("marca.editar", dados)[1]["resultado"]["feito"], False, dados)
        self.assertEqual(self.agir("marca.editar", {"campo": "nome", "valor": "a", "x": 1})[0], 400)
        with open(self.marca, encoding="utf-8") as f:
            self.assertEqual(json.load(f), MARCA)

    def test_marca_trocada_depois_de_aprovar_perde_aprovacao(self):
        self.aprovar()
        trocada = json.loads(json.dumps(MARCA))
        trocada["campos"]["cores.primary"] = {"valor": "#FF00FF", "fonte": "sessao", "confianca": "alta",
                                              "travado": False}
        escrever(self.marca, json.dumps(trocada))
        self.assertEqual(self.recusa().codigo, 409)
        os.remove(self.marca)
        self.assertEqual(self.recusa().codigo, 409)  # sumiu: também não vale
        escrever(self.marca, json.dumps(MARCA))  # os mesmos bytes aprovados voltam a valer
        modulos.antes_de_disparar(self.cfg, ACAO)

    def test_montar_mostra_campos_e_sha_da_marca(self):
        abas = {a["id"]: a for a in modulos.montar(self.cfg, "estudio", usar_cache=False)[1]["abas"]}
        texto = json.dumps(abas["marca"], ensure_ascii=False)
        for esperado in ("#112233", "Forno", "a.css:1", self.sha(), "data:image/png;base64,"):
            self.assertIn(esperado, texto)
        self.assertIn("Passo 1 de 3", json.dumps(abas["novo"], ensure_ascii=False))  # sem estúdio preparado, o 1º passo

    def test_novo_mostra_o_passo_que_falta_e_depois_os_formularios(self):
        with open(os.path.join(os.path.dirname(os.path.dirname(REAL)), os.pardir, os.pardir, ".claude-plugin",
                               "plugin.json"), encoding="utf-8") as f:
            versao = json.load(f)["version"]
        escrever(os.path.join(self.cfg["dados_dir"], "ambiente.json"), json.dumps({"pronto": True, "estudio": versao}))

        def novo():
            abas = modulos.montar(self.cfg, "estudio", usar_cache=False)[1]["abas"]
            self.assertEqual([a["id"] for a in abas], ["ambiente", "marca", "novo", "fila", "galeria", "aprovacao"])
            return next(a for a in abas if a["id"] == "novo")["blocos"]
        self.assertEqual((novo()[0]["titulo"][:12], novo()[0]["ir_para"]["aba"]), ("Passo 2 de 3", "marca"))
        self.aprovar()
        blocos = novo()
        self.assertTrue(blocos[0]["titulo"].startswith("Passo 3 de 3"))
        self.assertIn("estudio.post", [b.get("catalogo") for b in blocos])

    def test_redescobrir_le_de_novo_e_derruba_aprovacao(self):
        self.aprovar()
        self.assertIs(self.agir("marca.redescobrir", {"confirmar": False})[1]["resultado"]["feito"], False)
        cod, d = self.agir("marca.redescobrir", {"confirmar": True})
        self.assertEqual((cod, d["resultado"]["feito"]), (200, True), d)
        with open(self.marca, encoding="utf-8") as f:
            self.assertIn("gerado_em", json.load(f))
        self.assertEqual(self.recusa().codigo, 409)

    def test_aprovar_exige_o_sha_mostrado(self):
        for sha in (None, "", "abc", "0" * 12):
            dados = {"confirmar": True} if sha is None else {"confirmar": True, "sha256": sha}
            self.assertIs(self.agir("marca.aprovar", dados)[1]["resultado"]["feito"], False, sha)
        self.assertEqual(self.recusa().codigo, 409)
        self.assertIs(self.aprovar()[1]["resultado"]["feito"], True)

    @unittest.skipIf(not hasattr(os, "symlink") or os.name == "nt", "atalho")
    def test_editar_nao_segue_atalho_no_tmp(self):
        fora = os.path.join(self.tmp, "fora.txt")
        escrever(fora, "original")
        os.symlink(fora, self.marca + ".tmp")
        self.assertIs(self.agir("marca.editar", {"campo": "nome", "valor": "Novo"})[1]["resultado"]["feito"], True)
        with open(fora, encoding="utf-8") as f:
            self.assertEqual(f.read(), "original")
        self.assertFalse(os.path.islink(self.marca))
        with open(self.marca, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["campos"]["nome"]["valor"], "Novo")

    def test_editar_logo_tira_a_copia_antiga(self):
        escrever(self.marca, json.dumps(dict(MARCA, logo_copia="assets/logo.png")))
        escrever(os.path.join(self.pasta, "assets", "logo.png"), "PNG-A")
        self.assertIs(self.agir("marca.editar", {"campo": "logo", "valor": "sem logo"})[1]["resultado"]["feito"], True)
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "assets", "logo.png")))
        with open(self.marca, encoding="utf-8") as f:
            self.assertIsNone(json.load(f)["logo_copia"])


if __name__ == "__main__":
    unittest.main()
