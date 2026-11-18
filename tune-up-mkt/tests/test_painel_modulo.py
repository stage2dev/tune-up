"""Marketing tab of the panel (painel/modulos/mkt): every state of the Contas tab and the single-flight `conferir`.

The module is loaded by path, like the panel does. The process launcher, the pid check and the clock are fakes:
no test runs the real `contas.py status` or any CLI. The runner is driven with a harmless stand-in command.
"""
import importlib.util
import json
import os
import shutil
import stat
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASTA = os.path.join(RAIZ, "painel", "modulos", "mkt")
AGORA = datetime(2026, 1, 10, 12, 0, 0, tzinfo=timezone.utc)


def carregar(nome, arquivo):
    spec = importlib.util.spec_from_file_location(nome, os.path.join(PASTA, arquivo))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuneup-mkt-painel-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mkt = os.path.join(self.tmp, ".tune-up", "mkt")
        self.mod = carregar("mkt_modulo_teste", "modulo.py")
        self.C = self.mod.C
        self.chamadas = []
        self.vivos = {77}
        self.pid_novo = 4321
        self.mod.agora = lambda: AGORA
        self.mod.pid_vivo = lambda pid: pid in self.vivos
        self.mod.lancar = self.lancar

    def lancar(self, argv, fd, cwd):
        self.chamadas.append((argv, cwd))
        self.vivos.add(self.pid_novo)
        return self.pid_novo

    def gravar(self, nome, dado):
        os.makedirs(self.mkt, exist_ok=True)
        with open(os.path.join(self.mkt, nome), "w", encoding="utf-8") as f:
            f.write(dado if isinstance(dado, str) else json.dumps(dado))

    def ler(self, nome):
        with open(os.path.join(self.mkt, nome), encoding="utf-8") as f:
            return json.load(f)

    def montar(self):
        return self.mod.montar({"raiz": self.tmp})

    def agir(self, dados=None):
        return self.mod.agir({"raiz": self.tmp}, "conferir", {} if dados is None else dados)

    def textos(self, r):
        return [a["texto"] for a in r["alertas"]]

    def linhas(self, r):
        return {li["servico"]: li for li in r["abas"][0]["blocos"][1]["linhas"]}

    def contas(self, quando=AGORA - timedelta(hours=1), **servicos):
        base = {"chrome": "ligado", "composio": "ligado", "openseo": "ligado"}
        base.update(servicos)
        self.gravar("contas.json", {"versao": 1, "conferido_em": iso(quando) if quando else None, "servicos": {
            k: {"estado": v, "conta": "nao_se_aplica", "checagens": [
                {"tipo": "plugin", "via": "plugin", "estado": v, "detalhe": "enabled", "conferido_em": iso(AGORA)}]}
            for k, v in base.items()}})


class TesteEstados(Base):
    def test_sem_contas_json(self):
        r = self.montar()
        self.assertEqual(r["alertas"], [{"nivel": "info",
                                         "texto": "Ainda não houve conferência. Clique em Conferir contas."}])
        aba = r["abas"][0]
        self.assertEqual(aba["id"], "contas")
        self.assertNotIn("atualizar_em", r)
        self.assertEqual({li["estado"] for li in self.linhas(r).values()}, {"nunca conferido"})
        self.assertEqual([c["rotulo"] for c in aba["blocos"][1]["colunas"]],
                         ["Serviço", "Para que serve", "Estado", "Conferido em", "Próximo passo"])
        self.assertEqual(aba["blocos"][0]["acao"], "conferir")

    def test_arquivo_ilegivel_ou_invalido(self):
        for ruim in ("{nao json", "[]", '{"servicos": []}'):
            with self.subTest(ruim=ruim):
                self.gravar("contas.json", ruim)
                r = self.montar()
                self.assertEqual([a["nivel"] for a in r["alertas"]], ["atencao"])
                self.assertIn("não abre", r["alertas"][0]["texto"])

    def test_mais_de_24h_usa_o_conferido_em_do_topo(self):
        self.contas(quando=AGORA - timedelta(hours=25))
        self.assertTrue([t for t in self.textos(self.montar()) if "mais de 24 h" in t])
        self.contas(quando=None)  # only `marcar` ran: falta also refuses
        self.assertTrue([t for t in self.textos(self.montar()) if "mais de 24 h" in t])
        self.contas(quando=AGORA - timedelta(hours=23))
        self.assertEqual(self.montar()["alertas"], [])

    def test_mesmo_limite_do_falta(self):
        spec = importlib.util.spec_from_file_location("contas_cli_teste", os.path.join(RAIZ, "scripts", "contas.py"))
        contas = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(contas)
        self.assertEqual(self.mod.IDADE, contas.IDADE_FALTA)

    def test_base_sem_ligar_avisa_com_o_proximo_passo(self):
        self.contas(composio="falta_autenticar", openseo="nao_instalado", higgsfield="nao_instalado")
        r = self.montar()
        catalogo = {s["id"]: s for s in self.mod._catalogo()}
        textos = self.textos(r)
        self.assertEqual(len(textos), 2, textos)  # higgsfield is optional: row only, no alert
        self.assertIn(catalogo["composio"]["nome"], textos[0])
        self.assertIn(catalogo["composio"]["autenticar"]["pt"], textos[0])
        self.assertIn(catalogo["openseo"]["nome"], textos[1])
        self.assertIn(catalogo["openseo"]["instalar"][0], textos[1])
        linhas = self.linhas(r)
        self.assertEqual(linhas[catalogo["composio"]["nome"]]["estado"], "falta autenticar")
        self.assertEqual(linhas[catalogo["openseo"]["nome"]]["estado"], "não instalado")
        self.assertEqual(linhas[catalogo["chrome"]["nome"]]["passo"], "")
        self.assertTrue(linhas[catalogo["chrome"]["nome"]]["conferido_em"])
        self.assertEqual(linhas[catalogo["elevenlabs"]["nome"]]["estado"], "nunca conferido")

    def test_estado_desconhecido_vira_nao_sei(self):
        self.contas(chrome="qualquer coisa")
        catalogo = {s["id"]: s for s in self.mod._catalogo()}
        self.assertEqual(self.linhas(self.montar())[catalogo["chrome"]["nome"]]["estado"], "não sei")

    def test_conferindo(self):
        self.gravar("conferindo.json", {"inicio": iso(AGORA - timedelta(seconds=20)), "pid": 77, "id": "a"})
        r = self.montar()
        self.assertIn("Conferindo as contas... a tela se atualiza sozinha.", self.textos(r))
        self.assertEqual(r["atualizar_em"], 3)

    def test_terminada_aparece_por_pouco_tempo(self):
        self.contas()
        self.gravar("conferencia.json", {"id": "a", "inicio": iso(AGORA - timedelta(seconds=30)),
                                         "fim": iso(AGORA - timedelta(seconds=10)), "codigo": 0})
        r = self.montar()
        self.assertEqual(self.textos(r), ["Conferência terminada."])
        self.assertEqual(r["atualizar_em"], 15)  # re-read so the notice goes away
        self.mod.agora = lambda: AGORA + timedelta(minutes=2)
        r = self.montar()
        self.assertEqual(self.textos(r), [])
        self.assertNotIn("atualizar_em", r)

    def test_terminada_com_erro_nunca_vira_sucesso(self):
        self.contas()
        self.gravar("conferencia.json", {"id": "a", "inicio": iso(AGORA), "fim": iso(AGORA), "codigo": 1})
        textos = self.textos(self.montar())
        self.assertNotIn("Conferência terminada.", textos)
        self.assertTrue([t for t in textos if "deu erro" in t], textos)

    def test_marcador_morto_sem_resultado(self):
        self.gravar("conferindo.json", {"inicio": iso(AGORA - timedelta(seconds=20)), "pid": 99, "id": "a"})
        r = self.montar()
        self.assertTrue([t for t in self.textos(r) if "parou sem terminar" in t])
        self.assertNotIn("atualizar_em", r)
        self.gravar("conferindo.json", {"inicio": iso(AGORA - timedelta(minutes=6)), "pid": 77, "id": "a"})
        self.assertTrue([t for t in self.textos(self.montar()) if "parou sem terminar" in t])  # too old

    def test_nada_de_conta_chave_nem_saida(self):
        self.gravar("contas.json", {"versao": 1, "conferido_em": iso(AGORA), "servicos": {"chrome": {
            "estado": "ligado", "conta": "rotulo-secreto-x", "marca": {"via": "manual", "prova": "manual"},
            "checagens": [{"detalhe": "saida-crua-y", "conferido_em": iso(AGORA)}], "saida": "Bearer zzz"}}})
        self.gravar("config.json", {"indexnow_key": "chave-indexnow-w", "site": "https://u:p@exemplo.test"})
        texto = json.dumps(self.montar(), ensure_ascii=False)
        for segredo in ("rotulo-secreto-x", "saida-crua-y", "Bearer", "chave-indexnow-w", "u:p@", "manual"):
            self.assertNotIn(segredo, texto)

    @unittest.skipIf(os.name == "nt", "symlink needs privileges on Windows")
    def test_atalho_recusado(self):
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(fora)
        os.makedirs(os.path.dirname(self.mkt))
        os.symlink(fora, self.mkt)
        self.assertEqual([a["nivel"] for a in self.montar()["alertas"]], ["critico"])
        r = self.agir()
        self.assertIs(r["ok"], False)
        self.assertEqual(self.chamadas, [])
        self.assertEqual(os.listdir(fora), [])


class TesteConferir(Base):
    def test_comeca_em_segundo_plano(self):
        r = self.agir()
        self.assertIs(r["ok"], True, r)
        argv, cwd = self.chamadas[0]
        self.assertEqual(argv, [sys.executable, "-I", os.path.join(PASTA, "rodar_conferencia.py"), "--raiz",
                                self.tmp, "--id", self.ler("conferindo.json")["id"]])
        self.assertEqual(cwd, self.tmp)
        self.assertEqual(self.ler("conferindo.json")["pid"], self.pid_novo)
        if os.name != "nt":
            for nome in ("conferindo.json", "conferencia.log"):
                self.assertEqual(stat.S_IMODE(os.stat(os.path.join(self.mkt, nome)).st_mode), 0o600, nome)
        self.assertEqual(self.montar()["atualizar_em"], 3)

    def test_segundo_clique_recusa(self):
        self.agir()
        r = self.agir()
        self.assertEqual(r["codigo"], 409)
        self.assertIn("Já está conferindo", r["mensagem"])
        self.assertEqual(len(self.chamadas), 1)

    def test_pid_morto_e_trocado(self):
        self.gravar("conferindo.json", {"inicio": iso(AGORA - timedelta(seconds=20)), "pid": 99, "id": "velho"})
        self.assertIs(self.agir()["ok"], True)
        self.assertEqual(len(self.chamadas), 1)
        self.assertNotEqual(self.ler("conferindo.json")["id"], "velho")

    def test_marcador_velho_e_trocado(self):
        self.gravar("conferindo.json", {"inicio": iso(AGORA - timedelta(minutes=6)), "pid": 77, "id": "velho"})
        self.assertIs(self.agir()["ok"], True)
        self.assertEqual(len(self.chamadas), 1)

    def test_marcador_ilegivel_e_trocado(self):
        self.gravar("conferindo.json", "")
        self.assertIs(self.agir()["ok"], True)

    def test_dois_cliques_juntos_um_comeca(self):
        def devagar(argv, fd, cwd):
            time.sleep(0.3)
            return self.lancar(argv, fd, cwd)
        self.mod.lancar = devagar
        saidas, porta = [], threading.Barrier(2)

        def clicar():
            porta.wait()
            saidas.append(self.agir())
        ts = [threading.Thread(target=clicar) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(10)
        self.assertEqual(len(self.chamadas), 1)
        self.assertEqual(sorted(str(s.get("codigo") or s.get("ok")) for s in saidas), ["409", "True"])

    def test_corpo_com_campo_recusado(self):
        r = self.agir({"raiz": "/outra"})
        self.assertIs(r["ok"], False)
        self.assertEqual(self.chamadas, [])
        self.assertEqual(self.mod.INFO["esquemas"], {"conferir": {}})

    def test_falha_ao_lancar_libera_o_proximo(self):
        def quebra(argv, fd, cwd):
            raise OSError("sem python")
        self.mod.lancar = quebra
        self.assertIs(self.agir()["ok"], False)
        self.assertFalse(os.path.exists(os.path.join(self.mkt, "conferindo.json")))
        self.mod.lancar = self.lancar
        self.assertIs(self.agir()["ok"], True)

    def test_pid_vivo_real(self):
        self.assertTrue(self.C.pid_vivo(os.getpid()))
        for ruim in (0, -1, None, True, "12"):
            self.assertFalse(self.C.pid_vivo(ruim))


class TesteRunner(Base):
    """rodar_conferencia.main with a stand-in command: result written, marker removed, whatever the exit code."""

    def rodar(self, codigo):
        self.mod.agora = self.C.agora
        self.assertIs(self.agir()["ok"], True)
        ident = self.ler("conferindo.json")["id"]
        runner = carregar("mkt_runner_teste", "rodar_conferencia.py")
        cmd = [sys.executable, "-c", "raise SystemExit(%d)" % codigo]
        self.assertEqual(runner.main(["--raiz", self.tmp, "--id", ident], comando=cmd), 0 if codigo == 0 else 1)
        self.assertFalse(os.path.exists(os.path.join(self.mkt, "conferindo.json")))
        self.assertEqual((self.ler("conferencia.json")["id"], self.ler("conferencia.json")["codigo"]), (ident, codigo))
        return self.textos(self.montar())

    def test_sucesso(self):
        self.assertIn("Conferência terminada.", self.rodar(0))

    def test_erro(self):
        textos = self.rodar(3)
        self.assertNotIn("Conferência terminada.", textos)
        self.assertTrue([t for t in textos if "deu erro" in t], textos)

    def test_nao_apaga_marcador_de_outro(self):
        self.gravar("conferindo.json", {"inicio": iso(AGORA), "pid": 77, "id": "outro"})
        runner = carregar("mkt_runner_teste", "rodar_conferencia.py")
        runner.main(["--raiz", self.tmp, "--id", "meu"], comando=[sys.executable, "-c", "pass"])
        self.assertEqual(self.ler("conferindo.json")["id"], "outro")

    def test_argumentos_ruins(self):
        runner = carregar("mkt_runner_teste", "rodar_conferencia.py")
        for argv in ([], ["--raiz", "relativo", "--id", "x"], ["--id", "x", "--raiz", self.tmp]):
            self.assertEqual(runner.main(argv, comando=[sys.executable, "-c", "raise SystemExit(9)"]), 2)
        self.assertFalse(os.path.exists(self.mkt))


if __name__ == "__main__":
    unittest.main()
