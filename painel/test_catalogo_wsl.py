"""B2: no Windows o catálogo e o módulo embutido do Estúdio seguem a sonda do WSL2. Nada chama wsl.exe de verdade."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402
import unittest.mock  # noqa: E402

import catalogo  # noqa: E402
import config  # noqa: E402
import embutidos  # noqa: E402
import lancador  # noqa: E402
import modulos  # noqa: E402
import test_wsl  # noqa: E402 - fixtures da sonda (RodarFalso, Relogio)
import wsl  # noqa: E402

PRONTA = {"pronta": True, "motivo": "pronta", "marcador": {}}
NAO = {"pronta": False, "motivo": "a distro tune-up não está instalada no WSL.", "marcador": {}}
ESTUDIO = ["estudio.post", "estudio.video", "estudio.anuncio"]


class Conta:
    """Sonda falsa que conta as consultas."""

    def __init__(self, valor):
        self.valor, self.n = valor, 0

    def __call__(self):
        self.n += 1
        return self.valor


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.vazio = os.path.join(self.tmp, "vazio")
        os.makedirs(self.vazio)

    def cfg(self, bruto=None, ligar_estudio=True):
        os.makedirs(os.path.join(self.tmp, ".tune-up"), exist_ok=True)
        with open(os.path.join(self.tmp, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump(bruto or {}, f)
        c = config.carregar(self.tmp, home=self.tmp)
        c.update(acoes_dir=self.vazio, acoes_pacote_dir=None)
        os.makedirs(c["dados_dir"], exist_ok=True)
        with open(os.path.join(c["dados_dir"], embutidos.ARQUIVO), "w", encoding="utf-8") as f:
            json.dump({"estudio": ligar_estudio}, f)
        return c

    def ids(self, plataforma, sonda, **kw):
        acoes, avisos = catalogo.catalogo_do_projeto(self.cfg(**kw), plataforma, sonda)
        return [a["id"] for a in acoes], avisos


class TesteCatalogo(Base):
    def test_pronta_mostra_as_acoes_do_estudio_sem_aviso(self):
        ids, avisos = self.ids("win32", PRONTA)
        self.assertEqual([i for i in ids if i in ESTUDIO], ESTUDIO)
        self.assertFalse([a for a in avisos if "WSL2" in a], avisos)

    def test_nao_pronta_esconde_e_avisa_uma_vez_com_o_motivo(self):
        ids, avisos = self.ids("win32", NAO)
        self.assertFalse([i for i in ids if i in ESTUDIO])
        w = [a for a in avisos if "instalar.ps1" in a]
        self.assertEqual(len(w), 1, avisos)
        self.assertIn("scripts\\wsl\\instalar.ps1", w[0])
        self.assertIn(NAO["motivo"], w[0])

    def test_sem_sonda_vale_como_nao_pronta(self):
        ids, avisos = self.ids("win32", None)
        self.assertFalse([i for i in ids if i in ESTUDIO])
        self.assertIn("WSL não conferido", " ".join(avisos))

    def test_video_motion_segue_a_propria_regra_e_nunca_aparece_no_win32(self):
        for bruto in ({}, {"estudio": {"video_motion": True}}, {"estudio.video_rede_local": True}):
            ids, _ = self.ids("win32", PRONTA, bruto=bruto)
            self.assertNotIn("estudio.video-motion", ids)

    def test_sonda_so_e_consultada_no_win32_e_com_acao_de_sandbox(self):
        for plat in ("darwin", "linux"):
            s = Conta(PRONTA)
            self.ids(plat, s)
            self.assertEqual(s.n, 0, plat)
        s = Conta(PRONTA)
        self.ids("win32", s, ligar_estudio=False)  # no sandbox action in the catalog
        self.assertEqual(s.n, 0)
        self.ids("win32", s)
        self.assertEqual(s.n, 1)

    def test_mac_e_linux_ficam_iguais(self):
        for plat in ("darwin", "linux"):
            ids, avisos = self.ids(plat, NAO)
            self.assertEqual([i for i in ids if i in ESTUDIO], ESTUDIO)
            self.assertFalse([a for a in avisos if "WSL2" in a], avisos)

    def test_plataforma_injetada_chega_aos_embutidos(self):
        # on a real Windows host embutidos falls back to sys.platform: the injected platform must reach it,
        # and the Estúdio folder must load whatever the probe says (the sandbox filter + warning decide)
        real = embutidos.pastas_de_acoes
        vistos = []

        def espia(cfg, plataforma=None, sonda=None):
            pastas = real(cfg, plataforma, sonda)
            vistos.append((plataforma, pastas))
            return pastas

        with unittest.mock.patch.object(embutidos, "pastas_de_acoes", espia):
            for s in (PRONTA, NAO):
                self.ids("win32", s)
        self.assertEqual([p for p, _ in vistos], ["win32", "win32"], vistos)
        self.assertTrue(all(pastas == [embutidos._pasta(embutidos._POR_ID["estudio"]["acoes"])]
                            for _, pastas in vistos), vistos)


class TesteEmbutido(Base):
    def test_ligar_no_win32(self):
        c = self.cfg(ligar_estudio=False)
        st, r = embutidos.mudar(c, "estudio", {"ligado": True}, plataforma="win32", sonda=NAO)
        self.assertEqual(st, 409, r)
        self.assertIn("instalar.ps1", r["erro"])
        self.assertIn(NAO["motivo"], r["erro"])
        self.assertEqual(embutidos.ligados(c, "win32", NAO), [])
        st, r = embutidos.mudar(c, "estudio", {"ligado": True}, plataforma="win32", sonda=PRONTA)
        self.assertEqual(st, 200, r)
        self.assertEqual(embutidos.ligados(c, "win32", PRONTA), ["estudio"])
        item = [e for e in r["embutidos"] if e["id"] == "estudio"][0]
        self.assertTrue(item["ligado"] and item["disponivel"] and item["motivo"] is None, item)

    def test_ligado_no_arquivo_mas_wsl_caiu_fica_desligado(self):
        c = self.cfg()
        self.assertEqual(embutidos.ligados(c, "win32", NAO), [])
        self.assertEqual(embutidos.ligados(c, "linux", NAO), ["estudio"])

    def test_modulo_do_estudio_abre_no_win32_pronto(self):
        c = self.cfg()
        self.assertEqual(modulos.caminho_do_modulo(c, "estudio", sonda=PRONTA), embutidos.caminho("estudio"))


class TesteLancador(Base):
    def lc(self, sonda, plataforma="win32"):
        return lancador.Lancador(self.cfg(), lambda: {}, rodar=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("rodou algo")), plataforma=plataforma, sonda=sonda)

    def test_lista_as_acoes_do_estudio_com_sonda_pronta(self):
        ids = [a["id"] for a in self.lc(lambda: PRONTA).acoes()[0]]
        self.assertTrue(set(ESTUDIO) <= set(ids), ids)
        ids = [a["id"] for a in self.lc(lambda: NAO).acoes()[0]]
        self.assertFalse(set(ESTUDIO) & set(ids), ids)

    def test_sonda_padrao_so_no_win32_e_so_quando_pedida(self):
        self.assertIsNone(self.lc(None, "linux").sonda_atual())
        lc = self.lc(None)
        self.assertIsNone(lc.sonda)  # lazy: nothing created before the first ask


class TesteImportacao(unittest.TestCase):
    def test_import_em_qualquer_ordem(self):
        pasta = os.path.dirname(os.path.abspath(__file__))
        for ordem in ("import catalogo, wsl", "import wsl, catalogo"):
            r = subprocess.run([sys.executable, "-B", "-I", "-c", "import sys; sys.path.insert(0, %r); %s" % (pasta, ordem)],
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 0, r.stderr[-300:])
        import erros
        self.assertIs(catalogo.ErroAcao, erros.ErroAcao)
        self.assertIs(wsl.ErroAcao, erros.ErroAcao)


class TesteZerar(unittest.TestCase):
    def test_zerar_durante_a_sonda_descarta_o_resultado(self):
        solta, entrou, base, rel = threading.Event(), threading.Event(), test_wsl.RodarFalso(), test_wsl.Relogio()

        def rodar(cmd, timeout, env=None):
            if cmd[1] == "-l":
                entrou.set()
                solta.wait(10)
            return base(cmd, timeout, env)
        s = test_wsl.sonda(rodar, relogio=rel)
        saida = []
        fio = threading.Thread(target=lambda: saida.append(s.ler(forcar=True)))
        fio.start()
        self.assertTrue(entrou.wait(5))
        s.zerar()  # e.g. the user just re-ran the installer
        solta.set()
        fio.join(5)
        self.assertEqual(saida[0]["pronta"], False)
        self.assertIn("conferindo de novo", saida[0]["motivo"])
        self.assertIsNone(s._valor)  # nothing stale was stored
        self.assertTrue(s.ler(forcar=True)["pronta"])  # the next read probes again and stores


if __name__ == "__main__":
    unittest.main()
