"""Unit tests for scripts/preparar_estudio.py and the estudio module. No network, no real npm."""
import importlib.util
import io
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
    mod._windows = lambda: False  # these tests cover the macOS/Linux path; Windows is in test_modulo_windows.py
    return mod


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.dados = os.path.join(self.tmp, "dados")
        os.makedirs(self.dados)
        self.studio = os.path.join(self.tmp, "studio")
        os.makedirs(os.path.join(self.studio, "node"))
        for nome, txt in (("node/package.json", '{"dependencies": {"hyperframes": "0.9.6"}}'),
                          ("node/package-lock.json", "{}"), ("VERSION", "0.1.0\n")):
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
        esperado = os.path.join(self.dados, "estudio-node", pe.chave_do_ambiente(dentro), "node")
        self.assertEqual(r["node_dir"], esperado)
        self.assertEqual(r["chave"], pe.chave_do_ambiente(dentro))
        self.assertEqual(r["hyperframes"], os.path.join(esperado, "node_modules", ".bin", "hyperframes"))
        self.assertTrue(os.path.isfile(os.path.join(esperado, "package-lock.json")))
        self.assertEqual({cwd for _, cwd in self.chamadas}, {esperado})
        self.assertFalse(os.path.exists(os.path.join(dentro, "node", "node_modules")))

    def test_chave_vem_do_package_lock(self):
        chave = pe.chave_do_ambiente(self.studio)
        self.assertRegex(chave, r"^[0-9a-f]{12}$")
        with open(os.path.join(self.studio, "node", "package-lock.json"), "w") as f:
            f.write('{"lockfileVersion": 3}')
        self.assertNotEqual(pe.chave_do_ambiente(self.studio), chave)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "symlink")
    def test_apaga_outras_chaves_e_a_pasta_antiga_sem_seguir_atalho(self):
        home = os.path.join(self.tmp, "casa")
        dentro = os.path.join(home, ".claude", "plugins", "cache", "tune-up", "tune-up", "2.11.0", "tune-up-studio")
        shutil.copytree(self.studio, dentro)
        self.studio = dentro
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(os.path.join(fora, "x"))
        os.makedirs(os.path.join(self.dados, "estudio-node", "velha", "node"))
        os.makedirs(os.path.join(self.dados, "tune-up-studio", "0.1.0", "node"))
        os.symlink(fora, os.path.join(self.dados, "estudio-node", "atalho"))
        self.preparar(home=home)
        self.assertEqual(os.listdir(os.path.join(self.dados, "estudio-node")), [pe.chave_do_ambiente(dentro)])
        self.assertFalse(os.path.lexists(os.path.join(self.dados, "tune-up-studio")))
        self.assertTrue(os.path.isdir(os.path.join(fora, "x")))  # o alvo do atalho fica

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "symlink")
    def test_pasta_antiga_que_e_atalho_nao_e_seguida(self):
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(os.path.join(fora, "x"))
        os.symlink(fora, os.path.join(self.dados, "tune-up-studio"))
        os.symlink(fora, os.path.join(self.tmp, "estudio-node-alvo"))
        self.preparar()
        self.assertTrue(os.path.isdir(os.path.join(fora, "x")))
        self.assertFalse(os.path.lexists(os.path.join(self.dados, "tune-up-studio")))
        os.symlink(fora, os.path.join(self.dados, "estudio-node"))  # estudio-node atalho: recusa, não instala lá
        with self.assertRaises(OSError):
            self.preparar()
        self.assertEqual(os.listdir(fora), ["x"])

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


class FakeMsvcrt:
    LK_NBLCK = 2

    def __init__(self, erro=None):
        self.erro, self.chamadas = erro, []

    def locking(self, fd, modo, n):
        self.chamadas.append((fd, os.lseek(fd, 0, os.SEEK_CUR), modo, n))
        if self.erro:
            raise self.erro


class TestTravaWindows(Base):
    def setUp(self):
        super().setUp()
        with open(os.path.join(self.dados, pe.TRAVA), "w") as f:
            f.write("bytes de uma rodada antiga\n")

    def test_trava_o_byte_zero_mesmo_no_modo_a(self):
        falso = FakeMsvcrt()
        with mock.patch.object(pe, "fcntl", None), mock.patch.object(pe, "msvcrt", falso, create=True):
            trava = pe._travar(self.dados)
        self.addCleanup(trava.close)
        self.assertEqual(falso.chamadas, [(trava.fileno(), 0, FakeMsvcrt.LK_NBLCK, 1)])

    def test_trava_tomada_devolve_none_e_fecha_o_arquivo(self):
        falso = FakeMsvcrt(OSError(13, "Permission denied"))
        with mock.patch.object(pe, "fcntl", None), mock.patch.object(pe, "msvcrt", falso, create=True):
            self.assertIsNone(pe._travar(self.dados))
            with self.assertRaises(OSError):  # closed (checked before main reuses the fd number)
                os.fstat(falso.chamadas[0][0])
            with mock.patch.object(pe, "preparar") as p:
                self.assertEqual(pe.main(["--dados", self.dados, "--sim"]), 2)
        p.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "real msvcrt.locking, Windows only")
    def test_no_windows_de_verdade_o_segundo_nao_trava(self):
        primeiro = pe._travar(self.dados)
        self.addCleanup(primeiro.close)
        self.assertIsNotNone(primeiro)
        self.assertIsNone(pe._travar(self.dados))


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
        with mock.patch.object(mod, "_chave", return_value=pe.chave_do_ambiente(self.studio)):  # a do setUp
            self.assertIn("Estúdio pronto", mod.montar({"dados": self.dados})["alertas"][0]["texto"])
        with mock.patch.object(mod, "_chave", return_value="0123456789ab"):  # o HyperFrames fixado mudou
            a = mod.montar({"dados": self.dados})["alertas"][0]
        self.assertEqual(a["nivel"], "atencao")
        self.assertIn("outra versão", a["texto"])
        pe.gravar(self.dados, {"versao": 1, "pronto": False, "estado": "preparando", "gravado_em": "2026-11-11T08:23:00-03:00"})
        texto = mod.montar({"dados": self.dados})["alertas"][0]["texto"]
        self.assertIn("Preparando o estúdio desde as 08:23", texto)  # hora legível, sem data ISO nem caminho de log
        self.assertNotIn("2026-11-11T", texto)

    def test_versao_vem_do_arquivo_version(self):
        self.assertEqual(pe.versao_do_estudio(self.studio), "0.1.0")
        real = pe.versao_do_estudio()  # o arquivo de verdade do repo, não o fixture
        self.assertNotEqual(real, "0")
        self.assertRegex(real, r"^\d+\.\d+\.\d+$")

    def test_pronto_segue_a_chave_nao_a_versao(self):
        mod = carregar_modulo()
        self.assertEqual(mod._chave(), pe.chave_do_ambiente())  # o módulo e o preparar calculam a mesma chave
        pe.gravar(self.dados, {"pronto": True, "estudio": "0.0.1", "chave": pe.chave_do_ambiente()})
        self.assertIn("Estúdio pronto", mod.montar({"dados_dir": self.dados})["alertas"][0]["texto"])
        pe.gravar(self.dados, {"pronto": True, "estudio": pe.versao_do_estudio()})  # preparado antes da chave
        self.assertIn("outra versão", mod.montar({"dados_dir": self.dados})["alertas"][0]["texto"])

    def test_preparar_usa_dados_dir_e_nao_a_pasta_do_pacote(self):
        mod = carregar_modulo()
        outra = os.path.join(self.tmp, "pacote-dados")
        with mock.patch.object(mod.subprocess, "Popen") as popen:
            mod.agir({"dados": outra, "dados_dir": self.dados, "raiz": self.tmp}, "preparar", {"confirmar": True})
        self.assertEqual(popen.call_args[0][0][3:5], ["--dados", self.dados])
        self.assertFalse(os.path.exists(outra))


class TestWsl(Base):
    """Under WSL with dados on /mnt/<letter>/ the node folder and the lock live on the Linux disk."""

    def setUp(self):
        super().setUp()
        self.home = os.path.join(self.tmp, "home")
        os.makedirs(self.home)
        self.linux = os.path.join(self.home, ".local", "share", "tune-up")
        self.mnt = "/mnt/c/Users/x/dados"
        p = mock.patch.object(pe, "_real", lambda c: self.mnt if c == self.dados else c)
        p.start()
        self.addCleanup(p.stop)

    def test_pasta_node_vai_para_o_disco_do_linux(self):
        chave = pe.chave_do_ambiente(self.studio)
        esperado = os.path.join(self.linux, "estudio-node", chave, "node")
        sob_claude = os.path.join(self.home, ".claude", "studio")  # studio under ~/.claude: same answer
        shutil.copytree(self.studio, sob_claude)
        for studio in (self.studio, sob_claude):
            d = pe.pasta_node(self.dados, studio, self.home, wsl=lambda: 2)
            self.assertEqual(d, esperado)
        for nome in ("package.json", "package-lock.json"):
            self.assertTrue(os.path.isfile(os.path.join(d, nome)))
        self.assertFalse(os.path.exists(os.path.join(self.dados, "estudio-node")))

    def test_chaves_velhas_do_disco_do_linux_somem(self):
        velha = os.path.join(self.linux, "estudio-node", "velha", "node")
        os.makedirs(velha)
        pe.pasta_node(self.dados, self.studio, self.home, wsl=lambda: 1)
        self.assertFalse(os.path.exists(os.path.dirname(velha)))

    def test_wsl_com_dados_no_disco_do_linux_nao_muda(self):
        with mock.patch.object(pe, "_real", lambda c: c):
            d = pe.pasta_node(self.dados, self.studio, self.home, wsl=lambda: 2)
        self.assertEqual(d, os.path.join(self.studio, "node"))
        self.assertFalse(os.path.exists(self.linux))

    def test_fora_do_wsl_nao_muda(self):
        d = pe.pasta_node(self.dados, self.studio, self.home, wsl=lambda: None)
        self.assertEqual(d, os.path.join(self.studio, "node"))
        self.assertFalse(os.path.exists(self.linux))

    @unittest.skipIf(sys.platform == "win32", "symlinks need privileges on Windows")
    def test_atalho_no_destino_e_recusado(self):
        alvo = os.path.join(self.tmp, "alvo")
        os.makedirs(alvo)
        os.makedirs(os.path.join(self.linux, "estudio-node"))
        os.symlink(alvo, os.path.join(self.linux, "estudio-node", pe.chave_do_ambiente(self.studio)))
        with self.assertRaises(OSError):
            pe.pasta_node(self.dados, self.studio, self.home, wsl=lambda: 2)
        self.assertEqual(os.listdir(alvo), [])

    def test_caminho_da_trava(self):
        self.assertEqual(pe._caminho_trava(self.dados, self.home, lambda: 2), os.path.join(self.linux, "ambiente.lock"))
        self.assertEqual(oct(os.stat(self.linux).st_mode & 0o777), "0o700")
        self.assertEqual(pe._caminho_trava(self.dados, self.home, lambda: None), os.path.join(self.dados, "ambiente.lock"))
        with mock.patch.object(pe, "_real", lambda c: c):
            self.assertEqual(pe._caminho_trava(self.dados, self.home, lambda: 2), os.path.join(self.dados, "ambiente.lock"))

    def test_so_instalar_fora_do_wsl_sai_com_2(self):
        r = pe.main(["--so-instalar"], wsl=lambda: None, home=self.home, rodar=self.rodar([0, 0]),
                    which=lambda n: "/bin/" + n, studio=self.studio, plataforma="darwin")
        self.assertEqual(r, 2)
        self.assertEqual(self.chamadas, [])
        self.assertFalse(os.path.exists(self.linux))

    def test_so_instalar_no_wsl2_roda_os_dois_passos_sem_ambiente_json(self):
        destino = os.path.join(self.linux, "estudio-node", pe.chave_do_ambiente(self.studio), "node")
        r = pe.main(["--so-instalar"], wsl=lambda: 2, home=self.home, rodar=self.rodar([0, 0]),
                    which=lambda n: "/bin/" + n, studio=self.studio, plataforma="linux")
        self.assertEqual(r, 0)
        self.assertEqual([c for c, _ in self.chamadas],
                         [["ci", "--ignore-scripts", "--no-audit", "--no-fund"], ["audit", "signatures"]])
        self.assertEqual({cwd for _, cwd in self.chamadas}, {destino})
        self.assertFalse(os.path.exists(os.path.join(self.dados, "ambiente.json")))

    def test_so_instalar_apaga_node_modules_se_a_auditoria_falha(self):
        destino = os.path.join(self.linux, "estudio-node", pe.chave_do_ambiente(self.studio), "node")
        r = pe.main(["--so-instalar"], wsl=lambda: 2, home=self.home, rodar=self.rodar([0, 1]),
                    which=lambda n: "/bin/" + n, studio=self.studio, plataforma="linux")
        self.assertEqual(r, 1)
        self.assertFalse(os.path.exists(os.path.join(destino, "node_modules")))

    def so(self, args, wsl=lambda: None, codigos=(0, 0), rodar=None, plataforma="linux", home=None):
        return pe.main(args, wsl=wsl, home=home or self.home, rodar=rodar or self.rodar(list(codigos)),
                       which=lambda n: "/bin/" + n, studio=self.studio, plataforma=plataforma)

    def destino(self):
        return os.path.join(self.linux, "estudio-node", pe.chave_do_ambiente(self.studio), "node")

    def test_so_instalar_em_linux_comum_imprime_node_dir_por_ultimo(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            r = self.so(["--so-instalar"])
        self.assertEqual(r, 0)
        self.assertEqual(out.getvalue().splitlines()[-1], "node_dir=" + os.path.abspath(self.destino()))

    def test_so_instalar_recusa_wsl1_e_nao_linux(self):
        for wsl, plat in ((lambda: 1, "linux"), (lambda: None, "win32"), (lambda: None, "darwin")):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                self.assertEqual(self.so(["--so-instalar"], wsl=wsl, plataforma=plat), 2)
            self.assertEqual(len(out.getvalue().splitlines()), 1)
        self.assertEqual(self.chamadas, [])
        self.assertFalse(os.path.exists(self.linux))

    def test_onde_imprime_so_o_caminho_e_nao_cria_nada(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            r = self.so(["--onde"])
        self.assertEqual(r, 0)
        self.assertEqual(out.getvalue(), os.path.abspath(self.destino()) + "\n")
        self.assertFalse(os.path.exists(self.linux))
        self.assertEqual(self.chamadas, [])

    def test_onde_recusa_onde_so_instalar_recusa(self):
        for wsl, plat in ((lambda: 1, "linux"), (lambda: None, "darwin")):
            with mock.patch("sys.stdout", new_callable=io.StringIO) as out, \
                    mock.patch("sys.stderr", new_callable=io.StringIO) as err:
                self.assertEqual(self.so(["--onde"], wsl=wsl, plataforma=plat), 2)
            self.assertEqual(out.getvalue(), "")
            self.assertEqual(len(err.getvalue().splitlines()), 1)

    @unittest.skipIf(sys.platform == "win32", "symlinks need privileges on Windows")
    def test_so_instalar_com_trava_em_atalho_retorna_1_sem_traceback(self):
        alvo = os.path.join(self.tmp, "alvo")
        os.makedirs(alvo)
        os.makedirs(os.path.dirname(self.linux))
        os.symlink(alvo, self.linux)
        self.assertEqual(self.so(["--so-instalar"]), 1)
        self.assertEqual(self.so(["--dados", self.dados, "--sim"], wsl=lambda: 2), 1)
        self.assertEqual(os.listdir(alvo), [])

    def test_so_instalar_apaga_node_modules_se_o_ci_falha_ou_e_interrompido(self):
        self.assertEqual(self.so(["--so-instalar"], codigos=(1,)), 1)
        self.assertFalse(os.path.exists(os.path.join(self.destino(), "node_modules")))
        base = self.rodar([0, 0])

        def interrompido(cmd, cwd, timeout):
            base(cmd, cwd, timeout)
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.so(["--so-instalar"], rodar=interrompido)
        self.assertFalse(os.path.exists(os.path.join(self.destino(), "node_modules")))

    def test_destino_linux_cria_a_raiz_com_0700(self):
        pe._destino_linux(self.home, "k")
        self.assertEqual(oct(os.stat(self.linux).st_mode & 0o777), "0o700")

    def test_trava_herdada_no_wsl_ainda_respeita_a_trava_do_disco_do_linux(self):
        trava = pe._travar_em(pe._caminho_trava(None, self.home))
        self.addCleanup(trava.close)
        r = pe.main(["--dados", self.dados, "--sim", "--trava-herdada"], wsl=lambda: 2, home=self.home,
                    rodar=self.rodar([0, 0]), which=lambda n: "/bin/" + n, studio=self.studio)
        self.assertEqual(r, 2)
        self.assertEqual(self.chamadas, [])
        self.assertFalse(os.path.exists(os.path.join(self.dados, "ambiente.json")))

    def test_sem_dados_e_sem_so_instalar_continua_erro_do_argparse(self):
        with self.assertRaises(SystemExit) as e:
            pe.main([])
        self.assertEqual(e.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
