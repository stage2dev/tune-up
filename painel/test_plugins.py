"""Plugins do Claude (plugins.py, C15 lado servidor): GET/POST /api/plugins pelo servidor de verdade, HOME temporário."""
import sys

sys.dont_write_bytecode = True

import glob  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import stat  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import habilidades  # noqa: E402
import lancador  # noqa: E402
import painel  # noqa: E402
import plugins  # noqa: E402
import test_http  # noqa: E402 - módulo, não a classe: senão os testes dele rodam de novo aqui
from test_lancador import ACOES_TESTE, ESTADO, CLIFalso, cfg_teste  # noqa: E402

SEGREDO = "sk-ant-FALSO-0123456789abcdef"
USUARIO = ('{\n    "env": {"ANTHROPIC_API_KEY": "%s", "X": "ção"},\n    "model": "opus",\n'
           '    "enabledPlugins": {\n        "b@m": true,\n        "a@m": false,\n        "tune-up@m": true,\n'
           '        "tune-up-mkt@m": true,\n        "lista@m": ["x"]\n    },\n    "z": [1, 2.5, null]\n}\n' % SEGREDO)
NT = os.name == "nt"


def escrever(caminho, texto, modo="w"):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, modo, **({} if "b" in modo else {"encoding": "utf-8", "newline": "\n"})) as f:
        f.write(texto)


def ler(caminho):
    with open(caminho, "rb") as f:
        return f.read()


class TestePlugins(unittest.TestCase):
    pedir, cab_post, post = test_http.TesteHTTP.pedir, test_http.TesteHTTP.cab_post, test_http.TesteHTTP.post

    @classmethod
    def setUpClass(cls):
        cls.tmp = t = tempfile.mkdtemp()
        escrever(os.path.join(t, "acoes", "t.json"), json.dumps(ACOES_TESTE))
        os.makedirs(os.path.join(t, "plans", "phases"))
        escrever(os.path.join(t, "web", "index.html"), "<!doctype html><title>x</title>")
        cls.home = os.path.join(t, "home")
        cls.proj = os.path.join(t, "proj-raiz")
        cls.cfg = cfg_teste(t, web_dir=os.path.join(t, "web"), home=cls.home, raiz=cls.proj)
        lanc = lancador.Lancador(cls.cfg, lambda: ESTADO, rodar=CLIFalso(), plataforma="darwin")
        cls.app = painel.App(cls.cfg, os.path.join(t, "plans"), lancador=lanc, rodar_externos=False)
        cls.app.log = False
        cls.srv = painel.criar_servidor(cls.app, 0)
        cls.porta = cls.app.porta
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        shutil.rmtree(cls.tmp)

    def setUp(self):
        for d in (self.home, self.proj, os.path.join(self.tmp, "dotfiles")):
            shutil.rmtree(d, ignore_errors=True)
        self.arq = os.path.join(self.home, ".claude", "settings.json")
        self.pasta = os.path.dirname(self.arq)

    def get(self):
        st, _, dados = self.pedir("GET", "/api/plugins")
        self.assertNotIn(SEGREDO.encode(), dados)
        return st, json.loads(dados)

    def mudar(self, pid, ligar, **troca):
        st, r = self.post("/api/plugins", {"id": pid, "enabled": ligar}, **troca)
        self.assertNotIn(SEGREDO, json.dumps(r))
        return st, r

    def backups(self, pasta=None):
        return sorted(glob.glob(os.path.join(pasta or self.pasta, "settings.json.bak-*")))

    def temps(self, pasta=None):
        return glob.glob(os.path.join(pasta or self.pasta, ".settings.json.*.tmp"))

    def instalar(self):
        base = os.path.join(self.tmp, "instalado-b")
        shutil.rmtree(base, ignore_errors=True)
        escrever(os.path.join(base, "skills", "um", "SKILL.md"), "---\nname: um\ndescription: abc  def\n---\n")
        escrever(os.path.join(base, "skills", "dois", "SKILL.md"), "---\nname: dois\ndescription: xyz\n---\n")
        escrever(os.path.join(base, "agents", "rev.md"), "x")
        escrever(os.path.join(base, "agents", "nota.txt"), "x")
        escrever(os.path.join(self.home, ".claude", "plugins", "installed_plugins.json"),
                 json.dumps({"plugins": {"b@m": [{"installPath": base, "lastUpdated": "1"}]}}))

    # ---- GET
    def test_get_lista_valores_origem_e_peso(self):
        escrever(self.arq, USUARIO)
        escrever(os.path.join(self.proj, ".claude", "settings.json"), '{"enabledPlugins": {"a@m": true, "p@m": false}}')
        escrever(os.path.join(self.proj, ".claude", "settings.local.json"), '{"enabledPlugins": {"a@m": false}}')
        self.instalar()
        st, d = self.get()
        self.assertEqual((st, d["aviso"]), (200, None))
        por = {p["id"]: p for p in d["plugins"]}
        self.assertEqual(sorted(por), ["a@m", "b@m", "p@m", "tune-up-mkt@m", "tune-up@m"])  # só valores bool
        self.assertEqual(por["a@m"], {"id": "a@m", "ligado": False, "origem": "local", "sobreposto": True,
                                      "valores": {"usuario": False, "projeto": True, "local": False}, "fixo": False,
                                      "skills": 0, "agentes": 0, "peso": 0})
        self.assertEqual((por["p@m"]["origem"], por["p@m"]["sobreposto"], por["p@m"]["valores"]),
                         ("projeto", False, {"projeto": False}))
        b = por["b@m"]
        self.assertEqual((b["ligado"], b["origem"], b["sobreposto"], b["skills"], b["agentes"], b["peso"]),
                         (True, "usuario", False, 2, 1, len("abc def") + len("xyz")))
        self.assertEqual((por["tune-up@m"]["fixo"], por["tune-up-mkt@m"]["fixo"]), (True, False))

    def test_get_sem_settings_e_com_settings_ilegivel(self):
        self.assertEqual(self.get(), (200, {"plugins": [], "aviso": None}))
        self.assertEqual(self.mudar("b@m", False)[0], 404)
        self.assertFalse(os.path.exists(self.arq))
        escrever(os.path.join(self.proj, ".claude", "settings.json"), '{"enabledPlugins": {"p@m": true}}')
        self.assertEqual(self.mudar("p@m", False)[0], 404)  # só no projeto: nunca cria no usuário
        self.assertFalse(os.path.exists(self.arq))
        self.assertEqual(ler(os.path.join(self.proj, ".claude", "settings.json")), b'{"enabledPlugins": {"p@m": true}}')
        for ruim in ('{\n  // comentário\n  "enabledPlugins": {"b@m": true}\n}\n', '{"enabledPlugins": {"b@m": true}',
                     '{"enabledPlugins": {"b@m": true}, "enabledPlugins": {"b@m": true}}', "[1]"):
            escrever(self.arq, ruim)
            st, d = self.get()
            self.assertIn("settings do usuário", d["aviso"], ruim)
            self.assertEqual([p["id"] for p in d["plugins"]], ["p@m"])
            st, r = self.mudar("b@m", False)
            self.assertEqual(st, 409, ruim)
            self.assertEqual(ler(self.arq), ruim.encode())
            self.assertEqual((self.backups(), self.temps()), ([], []))

    # ---- POST
    def test_post_troca_so_o_booleano(self):
        escrever(self.arq, USUARIO)
        if not NT:
            os.chmod(self.arq, 0o644)
        habilidades._cache["x"] = (0, {})
        with mock.patch.object(self.app.estado, "invalidar") as inval:
            st, r = self.mudar("b@m", False)
        self.assertEqual((st, r["ok"], r["aviso"]), (200, True, "vale na próxima sessão"))
        self.assertTrue(inval.called)
        self.assertEqual(habilidades._cache, {})
        self.assertFalse({p["id"]: p for p in r["plugins"]}["b@m"]["ligado"])
        antes, depois = json.loads(USUARIO), json.loads(ler(self.arq).decode("utf-8"))
        antes["enabledPlugins"]["b@m"] = False
        self.assertEqual(antes, depois)
        self.assertEqual(list(depois), ["env", "model", "enabledPlugins", "z"])  # ordem mantida
        novo = ler(self.arq).decode("utf-8")
        self.assertIn('    "env": {\n        "ANTHROPIC_API_KEY": "%s",\n        "X": "ção"\n    }' % SEGREDO, novo)
        self.assertTrue(novo.endswith("}\n") and '        "b@m": false,' in novo)
        [bak] = self.backups()
        self.assertRegex(os.path.basename(bak), r"^settings\.json\.bak-\d{8}-\d{6}$")
        self.assertEqual(ler(bak), USUARIO.encode())
        self.assertEqual(self.temps(), [])
        if not NT:
            self.assertEqual(stat.S_IMODE(os.stat(self.arq).st_mode), 0o644)
            self.assertEqual(stat.S_IMODE(os.stat(bak).st_mode), 0o600)
        self.assertEqual(self.mudar("b@m", False)[0], 200)  # já está assim: não grava de novo
        self.assertEqual(len(self.backups()), 1)

    def test_post_corpo_errado_400_e_id_404(self):
        escrever(self.arq, USUARIO)
        for corpo in ({"id": "b@m", "enabled": "true"}, {"id": "b@m", "enabled": 1}, {"id": "b@m"},
                      {"enabled": True}, {"id": 1, "enabled": True}, {"id": "b@m", "enabled": True, "x": 1}):
            st, r = self.post("/api/plugins", corpo)
            self.assertEqual(st, 400, corpo)
            self.assertIsInstance(r["erro"], str)
        for pid in ("nada@m", "lista@m", "env", "b@m/../x", ""):
            self.assertEqual(self.mudar(pid, True)[0], 404, pid)
        self.assertEqual(ler(self.arq), USUARIO.encode())

    def test_post_recusa_o_proprio_tune_up(self):
        escrever(self.arq, USUARIO)
        st, r = self.mudar("tune-up@m", False)
        self.assertEqual(st, 409)
        self.assertEqual((ler(self.arq), self.backups()), (USUARIO.encode(), []))
        self.assertEqual(self.mudar("tune-up-mkt@m", False)[0], 200)  # nome exato, não pedaço

    def test_post_sem_chave_ou_origem_recusado(self):
        escrever(self.arq, USUARIO)
        for troca in ({"X-Painel-Token": None}, {"X-Painel-Token": "errado"}, {"Origin": None},
                      {"Origin": "http://evil.example"}, {"Sec-Fetch-Site": "cross-site"}, {"Host": "evil.example"}):
            st, r = self.mudar("b@m", False, **troca)
            self.assertIn(st, (403, 421), troca)
        self.assertEqual((ler(self.arq), self.backups()), (USUARIO.encode(), []))

    def test_post_guarda_so_3_backups(self):
        escrever(self.arq, USUARIO)
        escrever(os.path.join(self.pasta, "settings.json.bak-velho"), "x")
        escrever(os.path.join(self.pasta, "outro.json.bak-20200101-000000"), "x")
        carimbos = iter(["20260101-00000%d" % i for i in range(5)])
        with mock.patch.object(plugins, "_carimbo", lambda: next(carimbos)):
            for i in range(5):
                self.assertEqual(self.mudar("b@m", i % 2 == 1)[0], 200)
        self.assertEqual([os.path.basename(b) for b in self.backups()],
                         ["settings.json.bak-20260101-000002", "settings.json.bak-20260101-000003",
                          "settings.json.bak-20260101-000004", "settings.json.bak-velho"])
        self.assertTrue(os.path.exists(os.path.join(self.pasta, "outro.json.bak-20200101-000000")))

    def test_post_arquivo_mudou_no_meio_409(self):
        escrever(self.arq, USUARIO)
        if not NT:
            os.chmod(self.arq, 0o600)  # o temporário já tem o modo final antes de conferir; nunca mais aberto
        corrida = USUARIO.replace('"opus"', '"sonnet"')
        vistos = []

        def mexe(real):
            vistos.extend(self.temps())
            if not NT:
                vistos.extend(stat.S_IMODE(os.stat(t).st_mode) for t in self.temps())
            escrever(real, corrida)
        with mock.patch.object(plugins, "_antes_de_trocar", mexe):
            st, r = self.mudar("b@m", False)
        self.assertEqual(st, 409, r)
        self.assertEqual(len(vistos), 1 if NT else 2)  # havia um temporário (0600) na hora
        if not NT:
            self.assertEqual(vistos[1], 0o600)
        self.assertEqual((ler(self.arq), self.temps(), self.backups()), (corrida.encode(), [], []))

    @unittest.skipIf(NT, "modos de arquivo não valem no Windows")
    def test_post_nunca_abre_o_modo(self):
        escrever(self.arq, USUARIO)
        for antes, depois in ((0o600, 0o600), (0o640, 0o640), (0o666, 0o600)):
            os.chmod(self.arq, antes)
            self.assertEqual(self.mudar("b@m", not json.loads(ler(self.arq))["enabledPlugins"]["b@m"])[0], 200)
            self.assertEqual(stat.S_IMODE(os.stat(self.arq).st_mode), depois, oct(antes))

    def intacto(self, bruto, st, r, codigo):
        self.assertEqual((st, r.get("codigo")), (409, codigo), r)
        self.assertEqual((ler(self.arq), self.backups(), self.temps()), (bruto, [], []))

    def test_post_numero_ou_caractere_que_nao_regrava_409(self):  # B1, B2
        for extra in ('"n": 1e999', '"n": NaN', '"n": -Infinity', '"s": "a\\ud800b"'):
            bruto = ('{\n  %s,\n  "enabledPlugins": {"b@m": true}\n}\n' % extra).encode()
            escrever(self.arq, bruto, "wb")
            st, r = self.mudar("b@m", False)
            self.intacto(bruto, st, r, "ilegivel" if "ud800" in extra else "numero")
            self.assertNotIn("Infinity", r["erro"])

    def test_post_nao_le_separado_de_json_invalido(self):  # B3
        os.makedirs(self.arq)  # não é arquivo comum: OSError
        st, r = self.mudar("b@m", False)
        self.assertEqual((st, r["codigo"]), (409, "ilegivel"))
        self.assertRegex(r["erro"], r"\((OSError|PermissionError)\)")  # Windows não abre pasta: PermissionError
        self.assertNotIn("JSON", r["erro"])
        os.rmdir(self.arq)
        grande = ('{"enabledPlugins": {"b@m": true}, "x": "%s"}' % ("y" * plugins.LER_MAX)).encode()
        escrever(self.arq, grande, "wb")
        st, r = self.mudar("b@m", False)
        self.intacto(grande, st, r, "ilegivel")
        self.assertNotIn("JSON", r["erro"])
        self.assertNotIn("yyyy", r["erro"])
        escrever(self.arq, b"{x", "wb")
        st, r = self.mudar("b@m", False)
        self.intacto(b"{x", st, r, "ilegivel")
        self.assertIn("JSON inválido", r["erro"])

    def test_post_codigo_do_409(self):  # S3: corpo traz um codigo estável
        escrever(self.arq, USUARIO)
        self.assertEqual(self.mudar("tune-up@m", False)[1]["codigo"], "fixo")
        with mock.patch.object(plugins, "_antes_de_trocar", lambda real: escrever(real, USUARIO + " ")):
            self.assertEqual(self.mudar("b@m", False)[1]["codigo"], "mudou")

    def test_post_backup_antes_da_conferencia(self):  # B4: existe na hora de conferir; some se a conferência falha
        escrever(self.arq, USUARIO)
        vistos = []

        def mexe(real):
            vistos.extend(self.backups())
            escrever(real, USUARIO + " ")
        with mock.patch.object(plugins, "_antes_de_trocar", mexe):
            self.assertEqual(self.mudar("b@m", False)[0], 409)
        self.assertEqual((len(vistos), self.backups(), self.temps()), (1, [], []))

    def test_post_mesmo_segundo_nao_sobrescreve_backup(self):  # B4
        escrever(self.arq, USUARIO)
        escrever(os.path.join(self.pasta, "settings.json.bak-20260101-000000-x"), "x")
        escrever(os.path.join(self.pasta, "outro.json.bak-20260101-000000-2"), "x")
        conteudos = []
        with mock.patch.object(plugins, "_carimbo", lambda: "20260101-000000"):
            for i in range(11):
                conteudos.append(ler(self.arq))
                self.assertEqual(self.mudar("b@m", i % 2 == 1)[0], 200)
                if i == 1:
                    b = os.path.join(self.pasta, "settings.json.bak-20260101-000000")
                    self.assertEqual((ler(b), ler(b + "-2")), (conteudos[0], conteudos[1]))
        nomes = [os.path.basename(b) for b in self.backups()]
        self.assertEqual(sorted(nomes), sorted(["settings.json.bak-20260101-000000-9", "settings.json.bak-20260101-000000-10",
                                                "settings.json.bak-20260101-000000-11", "settings.json.bak-20260101-000000-x"]))
        self.assertEqual(ler(os.path.join(self.pasta, "settings.json.bak-20260101-000000-11")), conteudos[10])
        self.assertTrue(os.path.exists(os.path.join(self.pasta, "outro.json.bak-20260101-000000-2")))

    def test_post_aviso_quando_o_projeto_ainda_decide(self):  # B5
        escrever(self.arq, USUARIO)
        for nome, rotulo in (("settings.json", "settings do projeto"), ("settings.local.json", "settings.local do projeto")):
            shutil.rmtree(self.proj, ignore_errors=True)
            escrever(os.path.join(self.proj, ".claude", nome), '{"enabledPlugins": {"b@m": false}}')
            ligar = not json.loads(ler(self.arq))["enabledPlugins"]["b@m"]
            st, r = self.mudar("b@m", ligar)
            self.assertEqual(st, 200, r)
            self.assertNotIn("próxima sessão", r["aviso"])
            self.assertIn(rotulo, r["aviso"])
            self.assertIn("neste projeto", r["aviso"])

    def test_post_atalho_grava_no_arquivo_real(self):
        alvo = os.path.join(self.tmp, "dotfiles", "settings.json")
        escrever(alvo, USUARIO)
        os.makedirs(self.pasta)
        try:
            os.symlink(alvo, self.arq)
        except (OSError, NotImplementedError):
            self.skipTest("sem permissão para criar atalho")
        self.assertEqual(self.mudar("b@m", False)[0], 200)
        self.assertTrue(os.path.islink(self.arq))
        self.assertFalse(json.loads(ler(alvo))["enabledPlugins"]["b@m"])
        self.assertEqual((len(self.backups(os.path.dirname(alvo))), self.backups()), (1, []))


if __name__ == "__main__":
    unittest.main()
