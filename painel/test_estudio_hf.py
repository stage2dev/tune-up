"""{estudio_hf}: o HyperFrames do Estúdio instalado do marketplace (critério C12 da Parte A, item A4).

O plugin mora num HOME/.claude falso (`<home>/.claude/plugins/cache/tune-up/tune-up/2.11.0/`); as travas saem das
4 ações reais de tune-up-studio/painel/acoes/estudio.json pelo mesmo caminho do lançador (catalogo.validar_acao,
embutidos.estudio_da_acao, trabalho.resolver_travas, travas.argv_travas) e o gancho decide com travas.decidir.
"""
import importlib.util
import json
import os
import shlex
import shutil
import tempfile
import unittest
from unittest import mock

import catalogo
import config
import embutidos
import test_chat
import trabalho
import travas

AQUI = os.path.dirname(os.path.abspath(__file__))
STUDIO_REAL = os.path.join(os.path.dirname(AQUI), "tune-up-studio")
ACOES = os.path.join(STUDIO_REAL, "painel", "acoes", "estudio.json")
FIXTURE = os.path.join(AQUI, "tests_reais", "acao_estudio.json")
IDS = ["estudio.post", "estudio.video", "estudio.video-motion", "estudio.anuncio"]


def acoes_reais():
    with open(ACOES, encoding="utf-8") as f:
        return [catalogo.validar_acao(a) for a in json.load(f)["acoes"]]


def gancho(acao, cfg):
    conf = json.loads(travas.argv_travas(acao, cfg)[1])
    return travas._decodificar(shlex.split(conf["hooks"]["PreToolUse"][0]["hooks"][0]["command"])[4])


def preparar_estudio():
    spec = importlib.util.spec_from_file_location("preparar_estudio_hf", os.path.join(
        STUDIO_REAL, "scripts", "preparar_estudio.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Base(unittest.TestCase):
    ESPACO = ""  # "proj x": pasta do projeto com espaço (o caminho vai entre aspas no comando)

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "casa")
        self.raiz = os.path.join(self.home, ".claude", "plugins", "cache", "tune-up", "tune-up", "2.11.0")
        studio = os.path.join(self.raiz, "tune-up-studio")
        os.makedirs(os.path.join(studio, "node"))
        os.makedirs(os.path.join(studio, "scripts"))
        os.makedirs(os.path.join(self.raiz, "painel"))
        os.makedirs(os.path.join(self.raiz, ".claude-plugin"))
        shutil.copyfile(os.path.join(STUDIO_REAL, "node", "package-lock.json"),
                        os.path.join(studio, "node", "package-lock.json"))
        self.versao("2.11.0")
        p = mock.patch.object(config, "PAINEL", os.path.join(self.raiz, "painel"))
        p.start()
        self.addCleanup(p.stop)
        self.chave = embutidos.chave_do_ambiente(studio)
        self.usar_layout("pacote")

    def versao(self, v):
        with open(os.path.join(self.raiz, ".claude-plugin", "plugin.json"), "w") as f:
            json.dump({"name": "tune-up", "version": v}, f)

    def usar_layout(self, qual):
        """config.py:366-367: <pacote>/dados ou, com o pacote fora de .tune-up, .tune-up/painel-dados."""
        ws = os.path.join(self.tmp, self.ESPACO or "proj", qual)
        pacote = os.path.join(ws, ".tune-up", "painel")
        dados = os.path.join(pacote, "dados") if qual == "pacote" else os.path.join(ws, ".tune-up", "painel-dados")
        os.makedirs(dados, exist_ok=True)
        self.cfg = {"home": self.home, "workspace": ws, "pacote_dir": pacote, "dados_dir": dados,
                    "painel_dir": os.path.join(self.raiz, "painel")}
        self.dados = dados
        self.hf = os.path.join(dados, "estudio-node", self.chave, "node", "node_modules", ".bin", "hyperframes")
        self.trab = os.path.join(dados, "trabalhos", "abc")

    def preparado(self):
        os.makedirs(os.path.dirname(self.hf), exist_ok=True)
        open(self.hf, "w").close()

    def conf(self, acao):
        est = embutidos.estudio_da_acao(self.cfg, acao)
        return gancho(trabalho.resolver_travas(acao, self.trab, est), self.cfg)

    def decide(self, conf, cmd, ferramenta="Bash"):
        entrada = {"command": cmd} if ferramenta == "Bash" else {"file_path": cmd, "content": "x",
                                                                  "old_string": "a", "new_string": "b"}
        return travas.decidir(conf, ferramenta, entrada, self.trab)


class TesteCaminho(Base):
    def test_chave_igual_a_do_preparar(self):
        pe = preparar_estudio()
        self.assertEqual(embutidos.chave_do_ambiente(STUDIO_REAL), pe.chave_do_ambiente())

    def test_sob_claude_vai_para_dados_e_fora_fica_no_checkout(self):
        self.assertEqual(embutidos.estudio_hf(self.cfg), self.hf)
        with mock.patch.object(config, "PAINEL", os.path.join(os.path.dirname(STUDIO_REAL), "painel")):
            self.assertEqual(embutidos.estudio_hf(self.cfg), os.path.join(
                os.path.realpath(STUDIO_REAL), "node", "node_modules", ".bin", "hyperframes"))
        self.assertIsNone(embutidos.estudio_hf(dict(self.cfg, dados_dir="")))

    def test_d_ambiente_json_adulterado_nao_muda_o_caminho(self):
        self.preparado()
        with open(os.path.join(self.dados, "ambiente.json"), "w") as f:
            json.dump({"pronto": True, "chave": self.chave, "hyperframes": "/tmp/mau/hyperframes",
                       "node_dir": "/tmp/mau"}, f)
        self.assertEqual(embutidos.estudio_hf(self.cfg), self.hf)
        acao = next(a for a in acoes_reais() if a["id"] == "estudio.video-motion")
        prompt = trabalho.montar_prompt(acao, {"briefing": "b"}, self.trab, embutidos.estudio_da_acao(self.cfg, acao))
        self.assertIn("HyperFrames: %s." % self.hf, prompt)
        self.assertNotIn("/tmp/mau", prompt)

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "symlink")
    def test_estudio_node_atalho_para_fora_nao_vale(self):
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(os.path.join(fora, self.chave, "node", "node_modules", ".bin"))
        open(os.path.join(fora, self.chave, "node", "node_modules", ".bin", "hyperframes"), "w").close()
        os.symlink(fora, os.path.join(self.dados, "estudio-node"))
        self.assertIsNone(embutidos.estudio_hf(self.cfg))
        with self.assertRaises(catalogo.ErroAcao) as e:
            embutidos.estudio_da_acao(self.cfg, acoes_reais()[0])
        self.assertEqual(e.exception.codigo, 409)

    def test_g_so_a_versao_do_nucleo_muda_e_segue_pronto(self):
        self.preparado()
        antes = embutidos.estudio_da_acao(self.cfg, acoes_reais()[0])
        self.versao("2.12.0")
        self.assertEqual(embutidos.estudio_da_acao(self.cfg, acoes_reais()[0]), antes)

    def test_marcador_nunca_vira_caminho_vazio(self):
        acao = acoes_reais()[0]
        for pasta in (None, "trabalho", self.trab):
            with self.assertRaises(catalogo.ErroAcao):
                trabalho.montar_prompt(acao, {}, pasta)
        with self.assertRaises(catalogo.ErroAcao):
            trabalho.resolver_travas(acao, self.trab)
        self.assertTrue(trabalho.usa(dict(acao, sandbox=False, _prompt="x {estudio_hf}", params=[], _travas={})))
        with self.assertRaises(ValueError):  # nome reservado
            catalogo.validar_acao({"id": "x.y", "grupo": "x", "titulo": "Y", "risco": "leitura", "prompt": "{estudio_hf}",
                                   "params": [{"nome": "estudio_hf", "tipo": "texto"}]})

    def test_e_nao_preparado_recusa_com_409(self):
        for acao in acoes_reais():
            with self.assertRaises(catalogo.ErroAcao) as e:
                embutidos.estudio_da_acao(self.cfg, acao)
            self.assertEqual(e.exception.codigo, 409, acao["id"])
            self.assertIn("Prepare o Estúdio", e.exception.mensagem)
        self.assertIsNone(embutidos.estudio_da_acao(self.cfg, catalogo.validar_acao(
            {"id": "x.y", "grupo": "x", "titulo": "Y", "risco": "leitura", "prompt": "faça"})))


class TesteGancho(Base):
    def confs(self):
        self.preparado()
        return {a["id"]: self.conf(a) for a in acoes_reais()}

    def test_f_bash_desligado_nas_4_acoes(self):
        acoes = acoes_reais()
        self.assertEqual(sorted(a["id"] for a in acoes), sorted(IDS))
        for a in acoes:
            self.assertIs(travas.config_gancho(a)["bash"], False, a["id"])
            self.assertIs(self.confs()[a["id"]]["bash"], False, a["id"])

    def test_b_o_binario_passa_nas_4_acoes_nos_2_layouts(self):
        for layout in ("pacote", "painel-dados"):
            self.usar_layout(layout)
            for aid, conf in self.confs().items():
                self.assertTrue(conf["sb"], aid)
                self.assertEqual(conf["exe"], [shlex.quote(self.hf)], aid)
                for cmd in ("check fonte --json --strict", "lint fonte", "snapshot fonte --at 0 --no-end -o snap"):
                    cmd = shlex.quote(self.hf) + " " + cmd
                    with self.subTest(layout=layout, acao=aid, cmd=cmd):
                        # painel-dados: a pasta de trabalho inteira já cai na proteção de `.tune-up/painel*` (antes
                        # deste item: `ffmpeg -filters` com esse cwd também é negado); aqui sem cwd, só o binário
                        cwd = self.trab if layout == "pacote" else ""
                        self.assertIsNone(travas.decidir(conf, "Bash", {"command": cmd}, cwd))
                        sem = dict(conf, exe=[], py=None)  # sem a isenção exata o mesmo comando é negado
                        self.assertEqual(travas.decidir(sem, "Bash", {"command": cmd}, cwd)[0], "deny")

    def test_c_parecido_nao_passa(self):
        for aid, conf in self.confs().items():
            outra = self.hf.replace(self.chave, "0123456789ab")
            for cmd in (self.hf + "2 check fonte", outra + " check fonte", self.hf.upper() + " check fonte",
                        self.hf.replace("/estudio-node/", "/estudio-node//") + " check fonte",
                        os.path.join(self.trab, "estudio-node", self.chave, "node", "node_modules", ".bin",
                                     "hyperframes") + " check fonte",
                        "/opt/x/tune-up-studio/node/node_modules/.bin/hyperframes check fonte",
                        "node " + self.hf + " check fonte", self.hf, self.hf + " cloud render fonte",
                        self.hf + " check " + os.path.join(self.dados, "aprovados"),
                        self.hf + " check fonte; cp a " + self.hf,
                        "foo aprovados", "cat " + self.hf):
                with self.subTest(acao=aid, cmd=cmd):
                    got = self.decide(conf, cmd)
                    self.assertIsNotNone(got)
                    self.assertEqual(got[0], "deny")

    def test_c_sem_sandbox_o_binario_nao_e_isento(self):
        self.preparado()
        acao = dict(acoes_reais()[0], sandbox=False)
        conf = gancho(trabalho.resolver_travas(acao, self.trab, embutidos.estudio_da_acao(self.cfg, acao)), self.cfg)
        self.assertFalse(conf["sb"])
        self.assertEqual(self.decide(conf, self.hf + " check fonte")[0], "deny")

    def test_a_sessao_de_codigo_sem_sandbox_nao_grava_no_binario(self):
        self.preparado()
        for layout in ("pacote", "painel-dados"):
            self.usar_layout(layout)
            self.preparado()
            acao = catalogo.validar_acao({"id": "dev.c", "grupo": "dev", "titulo": "C", "risco": "codigo",
                                          "prompt": "faça"})
            conf = gancho(acao, self.cfg)
            self.assertFalse(conf["sb"])
            alvos = [self.hf, os.path.join(self.dados, "estudio-node", "x"), os.path.join(self.dados, "estudio-node")]
            casos = [(f, a) for a in alvos for f in ("Write", "Edit")]
            casos += [("Bash", c) for a in alvos for c in ("cp /tmp/x " + a, "mv /tmp/x " + a, "echo x > " + a)]
            casos += [("Bash", "cd %s && echo x > estudio-node/k" % self.dados)]
            for ferramenta, alvo in casos:
                with self.subTest(layout=layout, ferramenta=ferramenta, alvo=alvo):
                    got = self.decide(conf, alvo, ferramenta)
                    self.assertIsNotNone(got)
                    self.assertIn(got[0], ("deny", "ask"))
            sb = json.loads(travas.argv_travas(dict(acoes_reais()[0], _travas={}), self.cfg)[1])
            self.assertIn(self.dados + "/estudio-node", sb["sandbox"]["filesystem"]["denyWrite"])

    def test_h_script_do_estudio_no_cache_do_marketplace(self):
        scripts = os.path.join(self.raiz, "tune-up-studio", "scripts") + "/"
        self.assertIn("/.claude/plugins/cache/tune-up/tune-up/2.11.0/", scripts)
        for aid, conf in self.confs().items():
            self.assertEqual(conf["py"], scripts, aid)
            for cmd in ("python3 -I %sqa_imagem.py --achados fonte" % scripts,
                        "python3 -I -B %sqa_imagem.py --source fonte --png %s/a.png" % (scripts, self.trab),
                        "python3 -I %sfontes.py" % scripts):
                with self.subTest(acao=aid, cmd=cmd):
                    self.assertIsNone(self.decide(conf, cmd))
            outro = self.raiz.replace("/tune-up/tune-up/", "/outro/outro/") + "/tune-up-studio/scripts/"
            for cmd in ("python3 -I %sqa_imagem.py --achados fonte" % outro,
                        "python3 %sqa_imagem.py --achados fonte" % scripts,
                        "python3 -I %sqa_imagem.pyc --achados fonte" % scripts,
                        "python3 -I %sinstalar.py" % scripts,
                        "python3 -I %sqa_imagem.py --out %s/.claude/plugins/x" % (scripts, self.home),
                        "python3 -I %sqa_imagem.py --achados fonte; cp a %s/.claude/plugins/x" % (scripts, self.home),
                        "cat %sqa_imagem.py" % scripts, "cp a %sqa_imagem.py" % scripts):
                with self.subTest(acao=aid, cmd=cmd):
                    got = self.decide(conf, cmd)
                    self.assertIsNotNone(got)
                    self.assertEqual(got[0], "deny")

    def test_h_fora_do_sandbox_o_script_segue_negado(self):
        self.preparado()
        acao = dict(acoes_reais()[0], sandbox=False)
        conf = gancho(trabalho.resolver_travas(acao, self.trab, embutidos.estudio_da_acao(self.cfg, acao)), self.cfg)
        cmd = "python3 -I %s/tune-up-studio/scripts/qa_imagem.py --achados fonte" % self.raiz
        self.assertEqual(self.decide(conf, cmd)[0], "deny")


class TesteGanchoComEspaco(TesteGancho):
    ESPACO = "proj x"  # o caminho do binário tem espaço: vai entre aspas simples (shlex.quote) no prompt e na regra

    def test_caminho_com_espaco_vai_entre_aspas(self):
        self.assertIn(" ", self.hf)
        conf = self.confs()["estudio.post"]
        self.assertIsNone(self.decide(conf, "'%s' check fonte --json --strict" % self.hf))
        self.assertEqual(self.decide(conf, self.hf + " check fonte")[0], "deny")


class TesteLancador(test_chat.Base):
    def setUp(self):
        test_chat.Base.setUp(self)
        with open(FIXTURE, encoding="utf-8") as f:
            self.gravar_acoes(json.load(f)["acoes"])

    def test_e_nao_preparado_lancador_responde_409_e_nao_dispara(self):
        lc = test_chat.Base.lanc(self, bruto={"estudio": {"video_rede_local": True}})
        for hf in (None, os.path.join(self.tmp, "nao-existe", "hyperframes")):
            with mock.patch.object(embutidos, "estudio_hf", return_value=hf):
                with self.assertRaises(catalogo.ErroAcao) as e:
                    lc.iniciar("estudio.fixture", {"pedido": "oi"})
            self.assertEqual(e.exception.codigo, 409)
            self.assertIn("Prepare o Estúdio", e.exception.mensagem)
        self.assertFalse([c for c in self.cli.chamadas if c[0][1:2] == ["--bg"]])


if __name__ == "__main__":
    unittest.main()
