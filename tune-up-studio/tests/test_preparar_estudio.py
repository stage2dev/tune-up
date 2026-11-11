"""Unit tests for scripts/preparar_estudio.py and the estudio module. No network, no real npm."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))

import preparar_estudio as pe  # noqa: E402
import verificar_ambiente as va  # noqa: E402

OK_SO = lambda: [(va.OK, "sistema: teste")]  # noqa: E731


def carregar_modulo():
    caminho = os.path.join(STUDIO, "painel", "modulos", "estudio", "modulo.py")
    spec = importlib.util.spec_from_file_location("estudio_modulo_teste", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dados = os.path.join(self.tmp, "dados")
        os.makedirs(self.dados)
        self.studio = os.path.join(self.tmp, "studio")
        os.makedirs(os.path.join(self.studio, "node"))
        os.makedirs(os.path.join(self.studio, ".claude-plugin"))
        for nome, txt in (("node/package.json", '{"dependencies": {"hyperframes": "0.9.6"}}'),
                          ("node/package-lock.json", "{}"), (".claude-plugin/plugin.json", '{"version": "0.1.0"}')):
            with open(os.path.join(self.studio, *nome.split("/")), "w") as f:
                f.write(txt)
        self.chamadas = []

    def rodar(self, codigos):
        self.chamadas = []

        def f(cmd, cwd, timeout):
            self.chamadas.append((cmd[1:], cwd))
            if cmd[1] == "ci":
                os.makedirs(os.path.join(cwd, "node_modules", ".bin"), exist_ok=True)
                open(os.path.join(cwd, "node_modules", ".bin", "hyperframes"), "w").close()
            return codigos[len(self.chamadas) - 1], "saida do npm"
        return f

    def preparar(self, codigos=(0, 0), itens=None, home=None):
        verificar = lambda projeto, node_dir=None: itens or [(va.OK, "tudo certo")]  # noqa: E731
        return pe.preparar(self.dados, self.tmp, studio=self.studio, rodar=self.rodar(list(codigos)),
                           which=lambda n: "/bin/" + n, verificar=verificar, home=home or self.tmp,
                           sistema=OK_SO)

    def lido(self):
        with open(os.path.join(self.dados, "ambiente.json"), encoding="utf-8") as f:
            return json.load(f)


class TestPreparar(Base):
    def test_pronto_grava_ambiente_e_roda_so_os_dois_passos(self):
        r = self.preparar()
        self.assertTrue(r["pronto"])
        self.assertEqual(self.lido(), r)
        self.assertEqual([c for c, _ in self.chamadas],
                         [["ci", "--ignore-scripts", "--no-audit", "--no-fund"], ["audit", "signatures"]])
        self.assertEqual(r["node_dir"], os.path.join(self.studio, "node"))
        self.assertEqual(r["hyperframes"], os.path.join(self.studio, "node", "node_modules", ".bin", "hyperframes"))
        self.assertEqual(r["postinstall"], [])
        self.assertTrue(r["gravado_em"].endswith("Z"))

    def test_npm_ci_falha_para_e_grava_nao_pronto(self):
        r = self.preparar(codigos=(1,))
        self.assertFalse(self.lido()["pronto"])
        self.assertEqual(len(r["passos"]), 1)
        self.assertEqual(r["passos"][0]["saida"], "saida do npm")

    def test_assinatura_falha_apaga_node_modules(self):
        r = self.preparar(codigos=(0, 1))
        self.assertFalse(r["pronto"])
        self.assertFalse(os.path.exists(os.path.join(self.studio, "node", "node_modules")))
        self.assertIsNone(r["hyperframes"])

    def test_erro_da_verificacao_tira_o_pronto(self):
        r = self.preparar(itens=[(va.ERRO, "ffmpeg: falta")])
        self.assertFalse(r["pronto"])
        self.assertEqual(r["verificacao"], [{"nivel": "erro", "texto": "ffmpeg: falta"}])

    def test_sem_npm_nao_instala(self):
        r = pe.preparar(self.dados, self.tmp, studio=self.studio, rodar=self.rodar([]), which=lambda n: None,
                        verificar=lambda p, n=None: [(va.OK, "x")], home=self.tmp, sistema=OK_SO)
        self.assertFalse(r["pronto"])
        self.assertEqual(self.chamadas, [])

    def test_windows_nativo_nao_instala(self):
        r = pe.preparar(self.dados, self.tmp, studio=self.studio, rodar=self.rodar([]), which=lambda n: "/x",
                        verificar=lambda p, n=None: [(va.ERRO, "sistema")], home=self.tmp,
                        sistema=lambda: [(va.ERRO, "sistema")])
        self.assertFalse(r["pronto"])
        self.assertEqual(self.chamadas, [])

    def test_estudio_dentro_de_dot_claude_instala_em_dados(self):
        home = os.path.join(self.tmp, "casa")
        dentro = os.path.join(home, ".claude", "plugins", "cache", "m", "tune-up-studio", "0.1.0")
        shutil.copytree(self.studio, dentro)
        self.studio = dentro
        r = self.preparar(home=home)
        esperado = os.path.join(self.dados, "tune-up-studio", "0.1.0", "node")
        self.assertEqual(r["node_dir"], esperado)
        self.assertTrue(os.path.isfile(os.path.join(esperado, "package-lock.json")))
        self.assertEqual({cwd for _, cwd in self.chamadas}, {esperado})
        self.assertFalse(os.path.exists(os.path.join(dentro, "node", "node_modules")))

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "symlink")
    def test_atalho_no_lugar_do_ambiente_e_recusado(self):
        alvo = os.path.join(self.tmp, "fora.json")
        open(alvo, "w").close()
        os.symlink(alvo, os.path.join(self.dados, "ambiente.json"))
        with self.assertRaises(OSError):
            self.preparar()
        with open(alvo) as f:
            self.assertEqual(f.read(), "")

    def test_interrompido_no_npm_ci_nao_deixa_pronto_antigo(self):
        pe.gravar(self.dados, {"versao": 1, "pronto": True, "gravado_em": "ontem"})
        vistos = []

        def rodar(cmd, cwd, timeout):  # npm ci apaga node_modules e o Ctrl+C chega no meio
            vistos.append(self.lido())
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            pe.preparar(self.dados, self.tmp, studio=self.studio, rodar=rodar, which=lambda n: "/bin/" + n,
                        verificar=lambda p, n=None: [], home=self.tmp, sistema=OK_SO)
        self.assertEqual((vistos[0]["pronto"], vistos[0]["estado"]), (False, "preparando"))
        self.assertFalse(self.lido()["pronto"])


class TestMain(Base):
    def test_sem_confirmacao_nada_feito(self):
        with mock.patch.object(pe, "preparar") as p:
            self.assertEqual(pe.main(["--dados", self.dados], entrada=lambda _: "n"), 2)
            self.assertEqual(pe.main(["--dados", self.dados], entrada=mock.Mock(side_effect=EOFError)), 2)
        p.assert_not_called()
        self.assertFalse(os.path.exists(os.path.join(self.dados, "ambiente.json")))

    def test_pasta_de_dados_ausente(self):
        self.assertEqual(pe.main(["--dados", os.path.join(self.tmp, "nao"), "--sim"]), 2)

    def test_falha_no_meio_grava_nao_pronto_por_cima_do_antigo(self):
        pe.gravar(self.dados, {"pronto": True})
        with mock.patch.object(pe, "preparar", side_effect=OSError("disco cheio")):
            self.assertEqual(pe.main(["--dados", self.dados, "--sim"]), 1)
        self.assertFalse(self.lido()["pronto"])

    def test_ctrl_c_ou_erro_inesperado_regrava_nao_pronto_e_relanca(self):
        for erro in (KeyboardInterrupt, AttributeError("dependencies")):
            pe.gravar(self.dados, {"pronto": True})
            with mock.patch.object(pe, "preparar", side_effect=erro):
                with self.assertRaises(BaseException):
                    pe.main(["--dados", self.dados, "--sim"])
            self.assertFalse(self.lido()["pronto"])

    @unittest.skipIf(pe.fcntl is None, "flock")
    def test_segundo_preparar_ao_mesmo_tempo_e_recusado(self):
        trava = pe._travar(self.dados)
        self.addCleanup(trava.close)
        with mock.patch.object(pe, "preparar") as p:
            self.assertEqual(pe.main(["--dados", self.dados, "--sim"]), 2)
        p.assert_not_called()


class TestModulo(Base):
    def test_comando_exige_confirmar_e_nao_dispara_sem(self):
        mod = carregar_modulo()
        self.assertEqual(mod.INFO["esquemas"]["preparar"], {"confirmar": "booleano"})
        with mock.patch.object(mod.subprocess, "Popen") as popen:
            for dados in ({}, {"confirmar": False}):
                self.assertFalse(mod.agir({"dados": self.dados}, "preparar", dados)["feito"])
            popen.assert_not_called()
            r = mod.agir({"dados": self.dados, "raiz": self.tmp}, "preparar", {"confirmar": True})
        self.assertTrue(r["feito"])
        argv = popen.call_args[0][0]
        self.assertEqual(argv[1:3], ["-I", os.path.join(STUDIO, "scripts", "preparar_estudio.py")])
        self.assertEqual(argv[3:], ["--dados", self.dados, "--projeto", self.tmp, "--sim", "--trava-herdada"])

    @unittest.skipIf(pe.fcntl is None, "flock")
    def test_comando_repetido_com_preparar_rodando_nao_dispara(self):
        mod = carregar_modulo()
        trava = pe._travar(self.dados)
        self.addCleanup(trava.close)
        with mock.patch.object(mod.subprocess, "Popen") as popen:
            self.assertFalse(mod.agir({"dados": self.dados}, "preparar", {"confirmar": True})["feito"])
        popen.assert_not_called()

    def test_montar_mostra_o_estado(self):
        mod = carregar_modulo()
        self.assertIn("ainda não foi preparado", mod.montar({"dados": self.dados})["alertas"][0]["texto"])
        self.preparar(codigos=(1,))
        a = mod.montar({"dados": self.dados})["alertas"][0]
        self.assertEqual(a["nivel"], "atencao")
        self.assertIn("npm ci --ignore-scripts falhou", a["texto"])
        self.preparar()
        with mock.patch.object(mod, "_versao", return_value="0.1.0"):  # a do plugin de mentira do setUp
            self.assertIn("Estúdio pronto", mod.montar({"dados": self.dados})["alertas"][0]["texto"])
        with mock.patch.object(mod, "_versao", return_value="0.2.0"):  # o plugin foi atualizado
            a = mod.montar({"dados": self.dados})["alertas"][0]
        self.assertEqual(a["nivel"], "atencao")
        self.assertIn("outra versão", a["texto"])
        pe.gravar(self.dados, {"versao": 1, "pronto": False, "estado": "preparando", "gravado_em": "2026-11-11T08:23:00-03:00"})
        texto = mod.montar({"dados": self.dados})["alertas"][0]["texto"]
        self.assertIn("Preparando o estúdio desde as 08:23", texto)  # hora legível, sem data ISO nem caminho de log
        self.assertNotIn("2026-11-11T", texto)


if __name__ == "__main__":
    unittest.main()
