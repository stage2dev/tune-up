"""scripts/wsl/fixados.env: the pinned downloads of the WSL installer (unittest, stdlib only)."""
import os
import re
import shutil
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WSL = os.path.join(RAIZ, "scripts", "wsl")
FIXADOS = os.path.join(WSL, "fixados.env")
VERIFICAR = os.path.join(RAIZ, "tune-up-studio", "scripts", "verificar_ambiente.py")

CHAVES = (
    "UBUNTU_URL", "UBUNTU_SHA256",
    "NODE_VERSAO", "NODE_URL", "NODE_SHA256",
    "FFMPEG_URL", "FFMPEG_SHA256",
    "CLAUDE_VERSAO", "CLAUDE_URL", "CLAUDE_SHA256",
    "CHROME_VERSAO", "CHROME_URL", "CHROME_SHA256",
    "DISTRO", "USUARIO",
)
VALOR = re.compile(r"^[A-Za-z0-9._:/+-]*$")
LINHA = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


def ler_fixados(caminho):
    """Strict parser: KEY=value, # comments and blank lines; closed key list; raises ValueError."""
    with open(caminho, "rb") as f:
        bruto = f.read()
    if bruto.startswith(b"\xef\xbb\xbf"):
        raise ValueError("BOM")
    if b"\r" in bruto:
        raise ValueError("CR line ending")
    vals = {}
    for n, linha in enumerate(bruto.decode("utf-8").split("\n"), 1):
        if linha == "" or linha.startswith("#"):
            continue
        m = LINHA.match(linha)
        if not m:
            raise ValueError("line %d: not KEY=value" % n)
        chave, valor = m.groups()
        if chave not in CHAVES:
            raise ValueError("line %d: unknown key %s" % (n, chave))
        if chave in vals:
            raise ValueError("line %d: duplicate key %s" % (n, chave))
        if not VALOR.match(valor):
            raise ValueError("line %d: bad value for %s" % (n, chave))
        vals[chave] = valor
    faltam = [c for c in CHAVES if c not in vals]
    if faltam:
        raise ValueError("missing keys: %s" % ", ".join(faltam))
    return vals


class TestFixados(unittest.TestCase):
    def setUp(self):
        self.v = ler_fixados(FIXADOS)

    def test_exatamente_as_chaves(self):
        self.assertEqual(sorted(self.v), sorted(CHAVES))

    def test_urls(self):
        for chave in [c for c in CHAVES if c.endswith("_URL")]:
            url = self.v[chave]
            self.assertTrue(url.startswith("https://"), chave)
            self.assertNotRegex(url.lower(), r"latest|current", chave)
            self.assertRegex(url, r"\d+\.\d+", chave + " has no version")
            versao = chave[:-4] + "_VERSAO"
            if versao in self.v:
                self.assertIn(self.v[versao], url, chave)

    def test_cada_url_tem_sha256(self):
        for chave in [c for c in CHAVES if c.endswith("_URL")]:
            self.assertRegex(self.v[chave[:-4] + "_SHA256"], HEX64, chave)

    def test_chrome_igual_ao_verificar_ambiente(self):
        with open(VERIFICAR, encoding="utf-8") as f:
            m = re.search(r'^CHROME_VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
        self.assertIsNotNone(m)
        self.assertEqual(self.v["CHROME_VERSAO"], m.group(1))

    def test_distro_e_usuario(self):
        self.assertEqual(self.v["DISTRO"], "tune-up")
        self.assertEqual(self.v["USUARIO"], "tuneup")

    def test_lf_sem_bom(self):
        with open(FIXADOS, "rb") as f:
            bruto = f.read()
        self.assertFalse(bruto.startswith(b"\xef\xbb\xbf"))
        self.assertNotIn(b"\r", bruto)


class TestScriptsWsl(unittest.TestCase):
    def _arquivos(self):
        for raiz, _, nomes in os.walk(WSL):
            for nome in nomes:
                caminho = os.path.join(raiz, nome)
                with open(caminho, "rb") as f:
                    yield caminho, f.read().decode("utf-8", "replace")

    def test_url_so_no_fixados(self):
        for caminho, texto in self._arquivos():
            if os.path.abspath(caminho) == os.path.abspath(FIXADOS) or caminho.endswith(".md"):
                continue
            self.assertNotRegex(texto, r"https?://", caminho)

    def test_sem_curl_ou_wget_no_shell(self):
        for caminho, texto in self._arquivos():
            self.assertNotRegex(texto, r"(curl|wget)[^\n|]*\|\s*(ba)?sh", caminho)


class TestParser(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="tuneup-fixados-")
        with open(FIXADOS, "rb") as f:
            self.base = f.read()

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def _ler(self, conteudo):
        caminho = os.path.join(self.dir, "f.env")
        with open(caminho, "wb") as f:
            f.write(conteudo)
        return ler_fixados(caminho)

    def test_aceita_o_arquivo_real(self):
        self.assertEqual(self._ler(self.base)["DISTRO"], "tune-up")

    def test_rejeita(self):
        casos = {
            "export": b"export DISTRO=tune-up\n",
            "aspas": b'DISTRO="tune-up"\n',
            "espaco antes": b"DISTRO =tune-up\n",
            "espaco depois": b"DISTRO= tune-up\n",
            "subshell": b"DISTRO=$(x)\n",
            "crase": b"DISTRO=`x`\n",
            "chave desconhecida": b"OUTRA=1\n",
            "duplicada": b"DISTRO=tune-up\n",
        }
        # Without its DISTRO line the base is valid only once DISTRO=tune-up is added back, so each
        # case is rejected by its own rule, not as a duplicate.
        sem_distro = self.base.replace(b"DISTRO=tune-up\n", b"")
        self.assertEqual(self._ler(sem_distro + b"DISTRO=tune-up\n")["DISTRO"], "tune-up")
        for nome, extra in casos.items():
            with self.subTest(nome):
                base = self.base if nome == "duplicada" else sem_distro
                with self.assertRaises(ValueError):
                    self._ler(base + extra)

    def test_rejeita_crlf_bom_e_falta(self):
        with self.assertRaises(ValueError):
            self._ler(self.base.replace(b"\n", b"\r\n"))
        with self.assertRaises(ValueError):
            self._ler(b"\xef\xbb\xbf" + self.base)
        with self.assertRaises(ValueError):
            self._ler(self.base.replace(b"USUARIO=tuneup\n", b""))


if __name__ == "__main__":
    unittest.main()
