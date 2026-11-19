"""Ponte com o WSL (wsl.py, wsl_ancora.py): roda em qualquer sistema, com rodar/relógio/popen falsos."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402

import wsl  # noqa: E402
import wsl_ancora  # noqa: E402
from catalogo import ErroAcao  # noqa: E402

EXE = wsl.exe_wsl()
MARCA = {"versao": 1, "plugin": "2.26.0", "usuario": "tuneup", "claude_bin": "/home/tuneup/.local/bin/claude",
         "plugin_dir": "/home/tuneup/.claude/plugins/cache/tune-up/tune-up/2.26.0"}
SEM_RUN_WSL = "/usr/bin/find: '/run/WSL': No such file or directory\n"


class Relogio:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class RodarFalso:
    """Responde por comando; confere que recebe lista, sem `--` e com timeout."""

    def __init__(self, **troca):
        self.resp = {"-l": (0, "Ubuntu\r\ntune-up\r\n", ""), "cat": (0, json.dumps(MARCA), ""),
                     "printenv": (1, "", ""), "find": (0, "", "")}
        self.resp.update(troca)
        self.chamadas = []

    def __call__(self, cmd, timeout, env=None):
        assert isinstance(cmd, list), cmd
        assert "--" not in cmd, cmd
        assert timeout and timeout <= 20
        self.chamadas.append((cmd, env))
        chave = "-l" if cmd[1] == "-l" else cmd[cmd.index("--exec") + 1].rsplit("/", 1)[-1]
        r = self.resp[chave]
        if isinstance(r, Exception):
            raise r
        return r


def sonda(rodar=None, relogio=None, versao="2.26.0", plataforma="win32"):
    return wsl.Sonda(rodar=rodar or RodarFalso(), relogio=relogio or Relogio(), versao_plugin=lambda: versao,
                     plataforma=plataforma)


class TestParaWsl(unittest.TestCase):
    def p(self, c):
        return wsl.para_wsl(c, unidade_de_rede=lambda letra: False)

    def test_formas(self):
        self.assertEqual(self.p("C:\\a\\b"), "/mnt/c/a/b")
        self.assertEqual(self.p("D:/a/b/"), "/mnt/d/a/b")
        self.assertEqual(self.p("e:\\"), "/mnt/e")
        self.assertEqual(self.p("C:\\Users\\João Silva\\x"), "/mnt/c/Users/João Silva/x")
        self.assertEqual(self.p("C:\\a/b\\\\c"), "/mnt/c/a/b/c")

    def test_recusas(self):
        for c in ["", "\\\\srv\\share\\x", "//srv/share", "\\\\?\\C:\\a", "\\\\.\\C:\\a", "//?/C:/a", "a\\b", "\\a",
                  "C:foo", "C:", "C:\\a\x00b", "C:\\a\nb", "C:\\a\\..\\b", "C:/..", None]:
            with self.assertRaises(ErroAcao, msg=repr(c)):
                self.p(c)
        for c in ["\\\\srv\\share\\x", "//srv/share"]:
            with self.assertRaises(ErroAcao) as e:
                self.p(c)
            self.assertIn("rede", e.exception.mensagem)

    def test_rede(self):
        vistas = []
        with self.assertRaises(ErroAcao):
            wsl.para_wsl("Z:\\x", unidade_de_rede=lambda letra: vistas.append(letra) or True)
        self.assertEqual(vistas, ["Z"])

    def test_rede_padrao_fora_do_windows(self):
        if sys.platform != "win32":
            self.assertEqual(wsl.para_wsl("C:\\x"), "/mnt/c/x")


class TestArgv(unittest.TestCase):
    def test_exe(self):
        self.assertEqual(wsl.exe_wsl({"SystemRoot": "D:\\Win"}), "D:\\Win\\System32\\wsl.exe")
        self.assertEqual(wsl.exe_wsl({}), "C:\\Windows\\System32\\wsl.exe")
        self.assertEqual(wsl.exe_wsl({"SystemRoot": "relativo"}), "C:\\Windows\\System32\\wsl.exe")

    def test_lista_exata(self):
        self.assertEqual(wsl.argv("/mnt/c/p", ["claude", "-p", "oi"]),
                         [EXE, "-d", "tune-up", "--cd", "/mnt/c/p", "--exec", "/usr/local/bin/tune-up-exec",
                          "claude", "-p", "oi"])
        self.assertEqual(wsl.argv_cru(["/usr/bin/true"]), [EXE, "-d", "tune-up", "--exec", "/usr/bin/true"])
        self.assertEqual(wsl.argv_cru(["/usr/bin/true"], usuario="tuneup"),
                         [EXE, "-d", "tune-up", "-u", "tuneup", "--exec", "/usr/bin/true"])

    def test_prompt_fica_um_elemento(self):
        prompt = "custa R$99 e $(id) `whoami` 'x' \"y\""
        a = wsl.argv("/mnt/c/p", ["claude", "-p", prompt])
        self.assertEqual(a[-1], prompt)
        self.assertNotIn("--", a)

    def test_recusas(self):
        for cwd, cmd in [("/x", []), ("/x", "claude -p"), ("/x", ["claude", "--", "x"]), ("/x", ["a\x00b"]),
                         ("x", ["claude"]), ("/x\x00", ["claude"]), ("/x", ["claude", 3]), ("/x", [""])]:
            with self.assertRaises(ErroAcao, msg=repr((cwd, cmd))):
                wsl.argv(cwd, cmd)
        for cmd, u in [(["--"], None), ([], None), (["/usr/bin/id"], "root; x"), (["/usr/bin/id"], "")]:
            with self.assertRaises(ErroAcao):
                wsl.argv_cru(cmd, usuario=u)

    def test_limite_30000(self):
        base = len(wsl.argv("/x", ["a"]))  # list length with a 1-char last element
        fixo = sum(len(s) for s in wsl.argv("/x", ["a"])) + base - 1 - 1
        self.assertEqual(len(wsl.argv("/x", ["a" * (30000 - fixo)])[-1]), 30000 - fixo)
        with self.assertRaises(ErroAcao) as c:
            wsl.argv("/x", ["a" * (30001 - fixo)])
        self.assertEqual(c.exception.mensagem, "comando grande demais para o Windows")


class TestSonda(unittest.TestCase):
    def nao(self, rodar=None, versao="2.26.0", trecho=""):
        r = sonda(rodar, versao=versao).ler()
        self.assertFalse(r["pronta"], r)
        self.assertIn(trecho, r["motivo"])
        return r

    def test_tudo_certo(self):
        rodar = RodarFalso()
        r = sonda(rodar).ler()
        self.assertEqual(r, {"pronta": True, "motivo": "pronta", "marcador": MARCA})
        self.assertEqual(rodar.chamadas[0], ([EXE, "-l", "-q"], {"WSL_UTF8": "1"}))
        self.assertEqual(rodar.chamadas[3][0], wsl.argv_cru(["/usr/bin/find", "/run/WSL", "-maxdepth", "1", "-name",
                                                              "*_interop"]))

    def test_lista_utf16_com_nul(self):
        self.assertTrue(sonda(RodarFalso(**{"-l": (0, "\ufefft\x00u\x00n\x00e\x00-\x00u\x00p\x00\r\x00\n\x00", "")}))
                        .ler()["pronta"])

    def test_cada_passo_falhando(self):
        casos = [({"-l": (0, "Ubuntu\ntune-up-velha\n", "")}, "não está instalada"),
                 ({"-l": (124, "", "")}, "demorou"),
                 ({"-l": (127, "", "")}, "wsl.exe"),
                 ({"cat": (1, "", "No such file")}, "não terminou"),
                 ({"cat": (0, "{x", "")}, "JSON"),
                 ({"cat": (0, "[1]", "")}, "formato"),
                 ({"cat": (0, json.dumps(dict(MARCA, versao=2)), "")}, "formato"),
                 ({"cat": (0, json.dumps(dict(MARCA, plugin="2.25.0")), "")}, "2.25.0"),
                 ({"cat": (0, json.dumps(dict(MARCA, usuario="root")), "")}, "usuário"),
                 ({"cat": (0, json.dumps(dict(MARCA, plugin_dir=MARCA["plugin_dir"] + "/../../x")), "")}, "pasta"),
                 ({"cat": (0, json.dumps(dict(MARCA, plugin_dir="/tmp/x")), "")}, "pasta"),
                 ({"printenv": (0, "/run/WSL/1_interop\n", "")}, "interop"),
                 ({"printenv": (124, "", "")}, "demorou"),
                 ({"printenv": (2, "", "")}, "código 2"),
                 ({"find": (0, "/run/WSL/12_interop\n", "")}, "interop"),
                 ({"find": (1, "", "find: '/run/WSL': Permission denied")}, "código 1"),
                 ({"find": (124, "", "")}, "demorou"),
                 ({"find": OSError("x")}, "OSError")]
        for troca, trecho in casos:
            with self.subTest(troca=troca):
                self.nao(RodarFalso(**troca), trecho=trecho)

    def test_sem_pasta_run_wsl_e_sem_interop(self):
        self.assertTrue(sonda(RodarFalso(find=(1, "", SEM_RUN_WSL))).ler()["pronta"])

    def test_versao_ilegivel(self):
        self.nao(versao=None, trecho="versão do plugin")

    def test_plugin_dir_valido(self):
        self.assertTrue(wsl.plugin_dir_valido(MARCA["plugin_dir"]))
        for p in [None, "/home/tuneup/.claude/plugins/cache/", "/home/tuneup/.claude/plugins/cache/a/../../b",
                  "/home/tuneup/.claude/plugins/cache/a/", "/home/tuneup/.claude/plugins/cache//a",
                  "/home/tuneup/.claude/plugins/cache/a\nb", "/home/outro/.claude/plugins/cache/a"]:
            self.assertFalse(wsl.plugin_dir_valido(p), p)

    def test_cache_60_15_forcar_zerar(self):
        rel, rodar = Relogio(), RodarFalso()
        s = sonda(rodar, rel)
        s.ler()
        n = len(rodar.chamadas)
        rel.t += 59
        s.ler()
        self.assertEqual(len(rodar.chamadas), n)
        rel.t += 1
        s.ler()
        self.assertEqual(len(rodar.chamadas), 2 * n)
        s.ler(forcar=True)
        self.assertEqual(len(rodar.chamadas), 3 * n)
        s.zerar()
        s.ler()
        self.assertEqual(len(rodar.chamadas), 4 * n)
        rodar.resp["-l"] = (0, "", "")
        s.zerar()
        s.ler()
        rel.t += 14
        s.ler()
        self.assertEqual(len(rodar.chamadas), 4 * n + 1)
        rel.t += 1
        s.ler()
        self.assertEqual(len(rodar.chamadas), 4 * n + 2)

    def test_fora_do_windows_nao_roda(self):
        rodar = RodarFalso()
        s = sonda(rodar, plataforma="darwin")
        self.assertEqual(s.ler(), {"pronta": False, "motivo": "só no Windows", "marcador": {}})
        self.assertEqual(s.valor_atual()["motivo"], "só no Windows")
        self.assertEqual(rodar.chamadas, [])

    def test_valor_atual_nao_espera(self):
        solta, entrou = threading.Event(), threading.Event()
        base = RodarFalso()

        def rodar(cmd, timeout, env=None):
            entrou.set()
            solta.wait(10)
            return base(cmd, timeout, env)
        s = sonda(rodar)
        self.assertEqual(s.valor_atual()["motivo"], "conferindo o WSL...")
        self.assertTrue(entrou.wait(5))
        fio = s._fio
        self.assertEqual(s.valor_atual()["motivo"], "conferindo o WSL...")
        self.assertIs(s._fio, fio)  # one background refresh at a time
        solta.set()
        fio.join(5)
        self.assertTrue(s.valor_atual()["pronta"])

    def test_duas_threads_uma_sonda(self):
        solta, entrou, base, contagem = threading.Event(), threading.Event(), RodarFalso(), []

        def rodar(cmd, timeout, env=None):
            if cmd[1] == "-l":
                contagem.append(1)
                entrou.set()
                solta.wait(10)
            return base(cmd, timeout, env)
        s = sonda(rodar)
        fios = [threading.Thread(target=s.ler, kwargs={"forcar": True}) for _ in range(2)]
        fios[0].start()
        self.assertTrue(entrou.wait(5))
        fios[1].start()
        time.sleep(0.2)  # the second thread is now waiting for the running probe
        solta.set()
        for f in fios:
            f.join(5)
        self.assertEqual(len(contagem), 1)


class TestAuxiliares(unittest.TestCase):
    def test_caminho_hf(self):
        self.assertEqual(wsl.caminho_hf("0123456789ab"),
                         "/home/tuneup/.local/share/tune-up/estudio-node/0123456789ab/node/node_modules/.bin/hyperframes")

    def test_hf_pronto(self):
        vistos, rel, cache = [], Relogio(), {}

        def rodar(cmd, timeout):
            vistos.append(cmd)
            return (0 if "aaaaaaaaaaaa" in cmd[-1] else 1), "", ""
        self.assertTrue(wsl.hf_pronto(rodar, "aaaaaaaaaaaa", relogio=rel, cache=cache))
        self.assertEqual(vistos[0], [EXE, "-d", "tune-up", "-u", "tuneup", "--exec", "/usr/bin/test", "-x",
                                     wsl.caminho_hf("aaaaaaaaaaaa")])
        self.assertFalse(wsl.hf_pronto(rodar, "bbbbbbbbbbbb", relogio=rel, cache=cache))
        rel.t += 14
        wsl.hf_pronto(rodar, "aaaaaaaaaaaa", relogio=rel, cache=cache)
        wsl.hf_pronto(rodar, "bbbbbbbbbbbb", relogio=rel, cache=cache)
        self.assertEqual(len(vistos), 2)
        rel.t += 1
        wsl.hf_pronto(rodar, "bbbbbbbbbbbb", relogio=rel, cache=cache)
        self.assertEqual(len(vistos), 3)
        for ruim in ["ABCDEF012345", "abc", "../../etc/xx", "0123456789abc"]:
            with self.assertRaises(ErroAcao):
                wsl.hf_pronto(rodar, ruim, relogio=rel, cache=cache)
        self.assertEqual(len(vistos), 3)

    def test_projects_dir(self):
        local = "\\\\wsl.localhost\\tune-up\\home\\tuneup\\.claude\\projects"
        velho = "\\\\wsl$\\tune-up\\home\\tuneup\\.claude\\projects"
        self.assertEqual(wsl.projects_dir_wsl(existe=lambda p: True), local)
        self.assertEqual(wsl.projects_dir_wsl(existe=lambda p: p == velho), velho)
        self.assertIsNone(wsl.projects_dir_wsl(existe=lambda p: False))

    def test_agora_wsl(self):
        self.assertEqual(wsl.agora_wsl(lambda c, t: (0, "1763400000\n", "")), 1763400000)
        self.assertIsNone(wsl.agora_wsl(lambda c, t: (0, "x", "")))
        self.assertIsNone(wsl.agora_wsl(lambda c, t: (124, "", "")))

    def test_medir_argv_fora_do_windows(self):
        if sys.platform != "win32":
            self.assertEqual(wsl.medir_argv(), 2)


class Filho:
    def __init__(self):
        self.vivo, self.terminado = True, False

    def poll(self):
        return None if self.vivo else 0

    def terminate(self):
        self.vivo, self.terminado = False, True

    def wait(self, timeout=None):
        return 0


class SondaFixa:
    def __init__(self, pronta):
        self.pronta, self.chamadas = pronta, []

    def ler(self, forcar=False):
        self.chamadas.append(forcar)
        return {"pronta": self.pronta}


class TestAncora(unittest.TestCase):
    def ancora(self, pronta=True, job=lambda p: "job"):
        self.rel, self.sonda, self.filhos, self.avisos = Relogio(), SondaFixa(pronta), [], []

        def popen(cmd):
            assert isinstance(cmd, list) and "--" not in cmd
            self.cmd = cmd
            self.filhos.append(Filho())
            return self.filhos[-1]
        return wsl_ancora.Ancora(self.sonda, popen=popen, relogio=self.rel, job=job, avisar=self.avisos.append)

    def test_nao_sobe_sem_pronta_e_esperas_crescem(self):
        a = self.ancora(pronta=False)
        momentos = []
        for t in range(0, 400):
            self.rel.t = 1000 + t
            n = len(self.sonda.chamadas)
            a.garantir()
            if len(self.sonda.chamadas) > n:
                momentos.append(t)
        self.assertEqual(momentos, [0, 5, 35, 155, 275, 395])
        self.assertEqual(self.filhos, [])
        self.assertTrue(all(self.sonda.chamadas))  # always a fresh probe

    def test_sobe_uma_vez_e_respeita_espera(self):
        a = self.ancora()
        self.assertTrue(a.garantir())
        self.assertTrue(a.garantir())
        self.assertEqual(len(self.filhos), 1)
        self.assertEqual(self.cmd, [EXE, "-d", "tune-up", "--exec", "/usr/bin/sleep", "infinity"])
        self.filhos[0].vivo = False
        self.rel.t += 4
        self.assertFalse(a.garantir())
        self.assertEqual(len(self.filhos), 1)
        self.rel.t += 1
        self.assertTrue(a.garantir())
        self.assertEqual(len(self.filhos), 2)
        self.filhos[1].vivo = False
        self.rel.t += 29
        self.assertFalse(a.garantir())
        self.rel.t += 1
        self.assertTrue(a.garantir())
        self.rel.t += 300  # lived 300 s: back to the first wait
        self.filhos[2].vivo = False
        self.assertTrue(a.garantir())
        self.assertEqual(len(self.filhos), 4)
        self.filhos[3].vivo = False
        self.rel.t += 5  # first wait again, not 120 s
        self.assertTrue(a.garantir())
        self.assertEqual(len(self.filhos), 5)

    def test_parar(self):
        a = self.ancora()
        a.garantir()
        a.parar()
        self.assertTrue(self.filhos[0].terminado)
        a.parar()  # nothing left to stop

    def test_job_falhando_nao_derruba(self):
        def job(p):
            raise OSError("sem job")
        a = self.ancora(job=job)
        self.assertTrue(a.garantir())
        self.assertEqual(len(self.avisos), 1)
        self.assertTrue(self.filhos[0].vivo)

    def test_job_padrao_fora_do_windows(self):
        if sys.platform != "win32":
            self.assertIsNone(wsl_ancora.job_padrao(object()))


if __name__ == "__main__":
    unittest.main()
