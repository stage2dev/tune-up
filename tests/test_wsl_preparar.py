"""scripts/wsl/preparar.sh run for real with bash, fake binaries on PATH and a test root (unittest, stdlib)."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WSL = os.path.join(RAIZ, "scripts", "wsl")
SCRIPT = os.path.join(WSL, "preparar.sh")
PASSWD_TUNEUP = "tuneup:x:1000:1000::/home/tuneup:/bin/bash"

# A fake download that is also a working fake `claude` (the same bytes serve every pinned file).
CONTEUDO = """#!/bin/sh
echo "claude $*" >> "$FAKE_LOG"
case "$1" in
  install) mkdir -p "$HOME/.local/bin"; cp "$0" "$HOME/.local/bin/claude"; [ -z "$FAKE_PERFIL" ] || echo x >> "$HOME/.bashrc" ;;
  --version) echo "$FAKE_CLAUDE_V (Claude Code)" ;;
  plugin)
    mkdir -p "$HOME/.claude/plugins"
    case "$2" in
      marketplace) echo '{"tune-up": {}}' > "$HOME/.claude/plugins/known_marketplaces.json" ;;
      install|update) printf '{"version": 2, "plugins": {"tune-up@tune-up": [{"scope": "user", "version": "%s"}]}}' \
        "${FAKE_PLUGIN_V:-2.19.0}" > "$HOME/.claude/plugins/installed_plugins.json" ;;
    esac ;;
esac
"""

FAKES = {
    "curl": 'o=""; while [ $# -gt 0 ]; do [ "$1" = -o ] && o=$2; shift; done; printf "%s" "$FAKE_CONTEUDO" > "$o"',
    "tar": ('d=.; n=""; for a in "$@"; do case "$n" in C) d=$a; n=""; continue;; f) n=""; continue;; esac\n'
            'case "$a" in -C) n=C;; -xJf) n=f;; -*) ;; *) mkdir -p "$d/$(dirname "$a")"; '
            'printf "#!/bin/sh\\necho fake\\n" > "$d/$a"; chmod +x "$d/$a";; esac; done'),
    "unzip": ('d=""; n=""; for a in "$@"; do [ "$n" = d ] && d=$a; n=""; [ "$a" = -d ] && n=d; done\n'
              'mkdir -p "$d/chrome-headless-shell-linux64"; printf "#!/bin/sh\\n" > "$d/chrome-headless-shell-linux64/chrome-headless-shell"\n'
              'chmod +x "$d/chrome-headless-shell-linux64/chrome-headless-shell"'),
    "apt-get": 'exit "${FAKE_APT_RC:-0}"',
    "dpkg-query": ('[ -n "$FAKE_DPKG_OK" ] || exit 1\n'
                   'for a in "$@"; do case "$a" in -*) ;; *) echo "install ok installed";; esac; done'),
    "getent": 'printf "%s\\n" "$FAKE_PASSWD" | awk -F: -v k="$2" \'$1==k || $3==k\' | grep . || exit 2',
    "useradd": "", "userdel": "", "usermod": "",
}


def ler_fixados():
    vals = {}
    with open(os.path.join(WSL, "fixados.env"), encoding="utf-8") as f:
        for linha in f.read().splitlines():
            if linha and not linha.startswith("#"):
                k, v = linha.split("=", 1)
                vals[k] = v
    return vals


@unittest.skipIf(sys.platform == "win32" or os.geteuid() == 0, "needs bash and a non-root uid")
class Preparar(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp(prefix="tuprep"))
        self.r = os.path.join(self.tmp, "raiz")
        self.lib = os.path.join(self.tmp, "lib")
        self.bin = os.path.join(self.tmp, "bin")
        self.log = os.path.join(self.tmp, "log")
        for d in (self.r, self.lib, self.bin):
            os.makedirs(d)
        shutil.copy(SCRIPT, self.lib)
        self.fix = ler_fixados()
        sha = hashlib.sha256(CONTEUDO.encode()).hexdigest()
        for k in list(self.fix):
            if k.endswith("_SHA256"):
                self.fix[k] = sha
        self.escrever_fixados()
        for nome, corpo in FAKES.items():
            p = os.path.join(self.bin, nome)
            with open(p, "w") as f:
                f.write('#!/bin/sh\necho "%s $*" >> "$FAKE_LOG"\n%s\n' % (nome, corpo))
            os.chmod(p, 0o755)
        self.env = {
            "PATH": self.bin + ":/usr/bin:/bin:/usr/sbin:/sbin", "HOME": os.path.join(self.tmp, "fora"),
            "TUNE_UP_RAIZ_TESTE": self.r, "TUNE_UP_UID_TESTE": "0", "FAKE_LOG": self.log,
            "FAKE_CONTEUDO": CONTEUDO, "FAKE_PASSWD": "", "FAKE_CLAUDE_V": self.fix["CLAUDE_VERSAO"],
        }
        self.plugin = os.path.join(self.tmp, "plugin")
        os.makedirs(os.path.join(self.plugin, ".claude-plugin"))
        os.makedirs(os.path.join(self.plugin, "tune-up-studio", "scripts"))
        with open(os.path.join(self.plugin, ".claude-plugin", "plugin.json"), "w") as f:
            f.write('{"name": "tune-up", "version": "2.19.0"}')
        for nome in ("preparar_estudio.py", "verificar_ambiente.py"):
            with open(os.path.join(self.plugin, "tune-up-studio", "scripts", nome), "w") as f:
                f.write("import sys\nopen(%r, 'a').write('%s ' + ' '.join(sys.argv[1:]) + '\\n')\n"
                        "print('/n/d' if '--onde' in sys.argv else 'relatorio ok')\n" % (self.log, nome))
        os.makedirs(os.path.join(self.r, "usr", "bin"))
        os.symlink(sys.executable, os.path.join(self.r, "usr", "bin", "python3"))

    def tearDown(self):
        for raiz, dirs, _ in os.walk(self.tmp):
            for d in dirs:
                if not os.path.islink(os.path.join(raiz, d)):
                    os.chmod(os.path.join(raiz, d), 0o755)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def escrever_fixados(self, texto=None):
        if texto is None:
            texto = "# test\n" + "".join("%s=%s\n" % kv for kv in self.fix.items())
        with open(os.path.join(self.lib, "fixados.env"), "w", newline="") as f:
            f.write(texto)

    def rodar(self, *args, **env):
        e = dict(self.env, **env)
        return subprocess.run(["bash", os.path.join(self.lib, "preparar.sh")] + list(args), env=e,
                              capture_output=True, text=True, timeout=60)

    def chamadas(self, nome=None):
        try:
            with open(self.log) as f:
                linhas = f.read().splitlines()
        except OSError:
            return []
        return [l for l in linhas if nome is None or l.split(" ", 1)[0] == nome]

    def p(self, *partes):
        return os.path.join(self.r, *partes)

    def marcar(self, conteudo="{}"):
        os.makedirs(self.p("etc", "tune-up"), exist_ok=True)
        with open(self.p("etc", "tune-up", "pronto.json"), "w") as f:
            f.write(conteudo)


class Fixados(Preparar):
    def recusa(self, texto):
        self.escrever_fixados(texto)
        r = self.rodar("--raiz")
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertEqual(self.chamadas("curl"), [])
        self.assertEqual(self.chamadas("apt-get"), [])

    def base(self):
        return "".join("%s=%s\n" % kv for kv in self.fix.items())

    def test_chave_desconhecida(self):
        self.recusa(self.base() + "OUTRA=1\n")

    def test_substituicao_de_comando(self):
        self.recusa(self.base().replace("DISTRO=tune-up", "DISTRO=$(touch /tmp/x)"))

    def test_cr(self):
        self.recusa(self.base().replace("\n", "\r\n"))

    def test_falta_chave(self):
        self.recusa(self.base().replace("DISTRO=tune-up\n", ""))

    def test_repetida(self):
        self.recusa(self.base() + "DISTRO=tune-up\n")

    def test_linha_sem_igual(self):
        self.recusa(self.base() + "export X\n")


class Raiz(Preparar):
    def test_nao_root_sem_raiz_de_teste_recusa(self):
        env = dict(self.env)
        del env["TUNE_UP_RAIZ_TESTE"]
        r = subprocess.run(["bash", os.path.join(self.lib, "preparar.sh"), "--raiz"], env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertIn("root", r.stderr)

    def test_nao_root_com_raiz_de_teste_recusa(self):
        r = self.rodar("--raiz", TUNE_UP_UID_TESTE="1000")
        self.assertEqual(r.returncode, 3, r.stderr)

    def test_completo_e_segunda_vez_nao_baixa(self):
        r = self.rodar("--raiz")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.chamadas("curl")), 2)
        tar = self.chamadas("tar")
        self.assertIn("--strip-components=1", tar[0])
        self.assertIn("-linux-x64/bin", tar[0])
        self.assertTrue(os.access(self.p("usr", "local", "bin", "ffprobe"), os.X_OK))
        self.assertEqual(self.chamadas("useradd"), ["useradd -u 1000 -m -s /bin/bash tuneup"])
        with open(self.p("etc", "wsl.conf")) as f:
            conf = f.read()
        self.assertIn("[interop]\nenabled=true\nappendWindowsPath=false", conf)
        self.assertIn("default=tuneup", conf)
        self.assertIn("systemd=false", conf)
        for nome in ("node", "ffmpeg", "ffprobe"):  # plant the installed versions, then run again
            with open(self.p("usr", "local", "bin", nome), "w") as f:
                f.write("#!/bin/sh\necho v%s\n" % self.fix["NODE_VERSAO"])
            os.chmod(self.p("usr", "local", "bin", nome), 0o755)
        os.remove(self.log)
        r = self.rodar("--raiz", FAKE_DPKG_OK="1", FAKE_PASSWD=PASSWD_TUNEUP)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.chamadas("curl"), [])
        self.assertEqual(self.chamadas("apt-get"), [])
        self.assertEqual(self.chamadas("useradd"), [])
        self.assertEqual(os.listdir(self.p("var", "tmp")), [])

    def test_hash_errado_apaga_e_nao_extrai(self):
        r = self.rodar("--raiz", FAKE_CONTEUDO="outro conteudo")
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertIn("sha256", r.stderr)
        self.assertEqual(self.chamadas("tar"), [])
        self.assertEqual(os.listdir(self.p("var", "tmp")), [])
        self.assertFalse(os.path.exists(self.p("usr", "local", "bin", "ffmpeg")))

    def test_uid_1000_de_outro_usuario_para(self):
        r = self.rodar("--raiz", FAKE_PASSWD="ubuntu:x:1000:1000::/home/ubuntu:/bin/bash")
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertIn("ubuntu", r.stderr)
        for nome in ("useradd", "userdel", "usermod", "curl"):
            self.assertEqual(self.chamadas(nome), [], nome)

    def test_apaga_marca_antes_de_tudo(self):
        self.marcar()
        r = self.rodar("--raiz", FAKE_APT_RC="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.p("etc", "tune-up", "pronto.json")))
        self.marcar()
        self.escrever_fixados("RUIM\n")  # even a broken fixados.env leaves the marker deleted
        self.assertEqual(self.rodar("--raiz").returncode, 4)
        self.assertFalse(os.path.exists(self.p("etc", "tune-up", "pronto.json")))


class Exec(Preparar):
    def setUp(self):
        super().setUp()
        self.assertEqual(self.rodar("--raiz").returncode, 0)
        self.exe = self.p("usr", "local", "bin", "tune-up-exec")
        self.limpo = {"PATH": "/usr/bin:/bin"}

    def run_exec(self, env, *args):
        return subprocess.run([self.exe] + list(args), env=env, capture_output=True, text=True)

    def test_recusa_sem_marca(self):
        r = self.run_exec(self.limpo, "true")
        self.assertEqual(r.returncode, 97)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1)

    def test_recusa_com_wsl_interop(self):
        self.marcar()
        self.assertEqual(self.run_exec(dict(self.limpo, WSL_INTEROP=""), "true").returncode, 97)

    def test_recusa_com_arquivo_interop(self):
        self.marcar()
        os.makedirs(self.p("run", "WSL"))
        open(self.p("run", "WSL", "1_interop"), "w").close()
        self.assertEqual(self.run_exec(self.limpo, "true").returncode, 97)

    def test_executa_com_argumentos_intactos(self):
        self.marcar()
        args = ["R$99", "$(id)", "a b", "q\"'", "`id`", ""]
        r = self.run_exec(self.limpo, sys.executable, "-c", "import sys,json;print(json.dumps(sys.argv[1:]))", *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), args)

    def test_abrir_tem_3_linhas(self):
        with open(self.p("usr", "local", "bin", "tune-up-abrir")) as f:
            self.assertEqual(f.read().splitlines()[2], 'exec /mnt/c/Windows/explorer.exe "$1"')


class FecharAbrir(Preparar):
    def test_fechar_so_escreve_wslconf(self):
        r = self.rodar("--fechar")
        self.assertEqual(r.returncode, 0, r.stderr)
        arquivos = [os.path.relpath(os.path.join(a, n), self.r) for a, _, ns in os.walk(self.r) for n in ns]
        self.assertEqual(sorted(arquivos), ["etc/wsl.conf", "usr/bin/python3"])
        with open(self.p("etc", "wsl.conf")) as f:
            self.assertIn("[interop]\nenabled=false\nappendWindowsPath=false", f.read())

    def test_fechar_nao_root_recusa(self):
        self.assertEqual(self.rodar("--fechar", TUNE_UP_UID_TESTE="1000").returncode, 3)

    def test_abrir_interop_apaga_marca_primeiro(self):
        self.marcar()
        os.chmod(self.p("etc"), 0o555)  # writing wsl.conf fails: the marker must already be gone
        r = self.rodar("--abrir-interop")
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.p("etc", "tune-up", "pronto.json")))
        os.chmod(self.p("etc"), 0o755)
        self.marcar()
        self.assertEqual(self.rodar("--abrir-interop").returncode, 0)
        self.assertFalse(os.path.exists(self.p("etc", "tune-up", "pronto.json")))
        with open(self.p("etc", "wsl.conf")) as f:
            self.assertIn("[interop]\nenabled=true", f.read())


class Marcar(Preparar):
    def setUp(self):
        super().setUp()
        self.plugins = self.p("home", "tuneup", ".claude", "plugins")
        self.dir = os.path.join(self.plugins, "cache", "tune-up", "tune-up", "2.19.0")
        os.makedirs(os.path.join(self.dir, "tune-up-studio", "scripts"))
        open(os.path.join(self.dir, "tune-up-studio", "scripts", "qa_video.py"), "w").close()
        self.instalado(self.dir)

    def instalado(self, caminho, versao="2.19.0"):
        with open(os.path.join(self.plugins, "installed_plugins.json"), "w") as f:
            json.dump({"version": 2, "plugins": {"tune-up@tune-up": [
                {"scope": "user", "installPath": caminho, "version": versao}]}}, f)

    def recusa(self, codigo=8, **env):
        r = self.rodar("--marcar", "--plugin-versao", "2.19.0", **env)
        self.assertEqual(r.returncode, codigo, r.stderr)
        self.assertEqual(len(r.stderr.strip().splitlines()), 1, r.stderr)
        self.assertFalse(os.path.lexists(self.p("etc", "tune-up", "pronto.json")))

    def test_grava_json_valido(self):
        r = self.rodar("--marcar", "--plugin-versao", "2.19.0")
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(self.p("etc", "tune-up", "pronto.json")) as f:
            d = json.load(f)
        self.assertEqual(d["versao"], 1)
        self.assertEqual(d["plugin"], "2.19.0")
        self.assertEqual(d["usuario"], "tuneup")
        self.assertEqual(d["plugin_dir"], os.path.realpath(self.dir))
        self.assertTrue(d["claude_bin"].endswith("/home/tuneup/.local/bin/claude"))
        self.assertRegex(d["feito_em"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(sorted(d["fixados"]), sorted(k for k in self.fix if k.endswith("_SHA256")))
        self.assertEqual(len(d["fixados"]), 5)
        self.assertEqual(os.stat(self.p("etc", "tune-up", "pronto.json")).st_mode & 0o777, 0o644)

    def test_recusa_wsl_interop(self):
        self.recusa(7, WSL_INTEROP="/run/WSL/1_interop")

    def test_recusa_arquivo_interop(self):
        os.makedirs(self.p("run", "WSL"))
        open(self.p("run", "WSL", "8_interop"), "w").close()
        self.recusa(7)

    def test_recusa_fora_do_cache(self):
        fora = os.path.join(self.tmp, "fora_plugin")
        shutil.copytree(self.dir, fora)
        self.instalado(fora)
        self.recusa()

    def test_recusa_ponto_ponto(self):
        self.instalado(os.path.join(self.plugins, "cache", "..", "cache", "tune-up", "tune-up", "2.19.0"))
        self.recusa()

    def test_recusa_link_que_escapa(self):
        fora = os.path.join(self.tmp, "fora_plugin")
        shutil.copytree(self.dir, fora)
        link = os.path.join(self.plugins, "cache", "link")
        os.symlink(fora, link)
        self.instalado(link)
        self.recusa()

    def test_recusa_pasta_acima_como_link(self):  # cache or ~/.claude replaced by a user-owned symlink
        for i, partes in enumerate(((".claude", "plugins", "cache"), (".claude",))):
            with self.subTest(partes=partes):
                origem, fora = os.path.join(self.p("home", "tuneup"), *partes), os.path.join(self.tmp, "mnt%d" % i)
                shutil.copytree(origem, fora, symlinks=True)
                shutil.rmtree(origem)
                os.symlink(fora, origem)
                self.recusa()

    def test_recusa_sem_qa_video(self):
        os.remove(os.path.join(self.dir, "tune-up-studio", "scripts", "qa_video.py"))
        self.recusa()

    def test_recusa_versao_diferente(self):
        self.instalado(self.dir, "2.18.0")
        self.recusa()

    def test_recusa_destino_link(self):
        os.makedirs(self.p("etc", "tune-up"))
        os.symlink(os.path.join(self.tmp, "alvo"), self.p("etc", "tune-up", "pronto.json"))
        r = self.rodar("--marcar", "--plugin-versao", "2.19.0")
        self.assertEqual(r.returncode, 8, r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "alvo")))

    def test_recusa_json_invalido(self):
        with open(os.path.join(self.plugins, "installed_plugins.json"), "w") as f:
            f.write("$(id)")
        self.recusa()

    def test_versao_mal_formada(self):
        self.assertEqual(self.rodar("--marcar", "--plugin-versao", "1;id").returncode, 2)


class Usuario(Preparar):
    def setUp(self):
        super().setUp()
        self.env.update(TUNE_UP_UID_TESTE="1000", FAKE_PASSWD=PASSWD_TUNEUP)
        os.makedirs(self.p("home", "tuneup"))

    def test_root_recusa(self):
        r = self.rodar("--usuario", "--plugin", self.plugin, TUNE_UP_UID_TESTE="0")
        self.assertEqual(r.returncode, 3, r.stderr)
        self.assertEqual(self.chamadas("curl"), [])

    def test_plugin_com_ponto_ponto(self):
        r = self.rodar("--usuario", "--plugin", self.plugin + "/../plugin")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertEqual(self.rodar("--usuario", "--plugin", "rel/plugin").returncode, 2)

    def test_completo_e_segunda_vez_nao_baixa(self):
        r = self.rodar("--usuario", "--sem-login", "--plugin", self.plugin)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(len(self.chamadas("curl")), 2)
        cl = self.chamadas("claude")
        self.assertIn("claude install " + self.fix["CLAUDE_VERSAO"], cl)
        self.assertIn("claude plugin marketplace add " + self.plugin, cl)
        self.assertIn("claude plugin install tune-up@tune-up --scope user", cl)
        exe = self.p("home", "tuneup", ".cache", "hyperframes", "chrome", "chrome-headless-shell",
                     "linux-" + self.fix["CHROME_VERSAO"], "chrome-headless-shell-linux64", "chrome-headless-shell")
        self.assertTrue(os.access(exe, os.X_OK))
        self.assertFalse(os.stat(self.p("home", "tuneup", ".cache")).st_mode & 0o020)
        self.assertEqual(self.chamadas("preparar_estudio.py"), ["preparar_estudio.py --so-instalar"])
        os.remove(self.log)
        r = self.rodar("--usuario", "--sem-login", "--plugin", self.plugin)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.chamadas("curl"), [])
        self.assertEqual([c for c in self.chamadas("claude") if c.startswith("claude plugin")], [])

    def test_verificar(self):
        r = self.rodar("--verificar", "--plugin", self.plugin)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("relatorio ok", r.stdout)
        self.assertIn("verificar_ambiente.py --projeto %s --node-dir /n/d" % self.p("home", "tuneup"),
                      self.chamadas("verificar_ambiente.py"))


class Geral(Preparar):
    def test_modo_desconhecido_ou_sem_argumento(self):
        for args in ([], ["--x"], ["--usuario"], ["--marcar"], ["--raiz", "--plugin", "/x"], ["--plugin"]):
            r = self.rodar(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("Uso:", r.stderr)

    def test_raiz_de_teste_com_caractere_ruim(self):
        self.assertEqual(self.rodar("--fechar", TUNE_UP_RAIZ_TESTE=self.r + "/a b").returncode, 3)

    def test_sem_sudo_source_eval(self):
        for raiz, _, nomes in os.walk(WSL):
            for nome in nomes:
                with open(os.path.join(raiz, nome), encoding="utf-8", errors="replace") as f:
                    self.assertIsNone(re.search(r"\bsudo\b", f.read()), nome)
        with open(SCRIPT, encoding="utf-8") as f:
            texto = f.read()
        self.assertNotRegex(texto, r"(?m)^\s*(source|\.|eval)\s")
        self.assertNotRegex(texto, r"https?://")


if __name__ == "__main__":
    unittest.main()
