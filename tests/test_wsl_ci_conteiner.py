"""The --verificar gate of scripts/wsl/tests/ci_conteiner.sh (criterion C5), run for real with bash (unittest, stdlib)."""
import os
import subprocess
import tempfile
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT = os.path.join(RAIZ, "scripts", "wsl", "tests", "ci_conteiner.sh")

BOM = """[ok]    sistema: Ubuntu 24.04
[ok]    node: v22.12.0
[ok]    hyperframes: 0.9.6 instalado
[ok]    chrome: chrome-headless-shell 152.0.7977.30 no cache do HyperFrames
[ok]    ffprobe: encontrado
[ok]    ffmpeg: os 12 filtros usados estão presentes
[ok]    ffmpeg: encoder libx264 presente
[falta] bwrap: não encontrado
[aviso] socat: não encontrado
Não está pronto: 1 item(ns) acima precisam de ajuste.
"""


def checar(texto, codigo):
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write(texto)
    try:
        env = {k: v for k, v in os.environ.items() if k != "GITHUB_WORKSPACE"}
        p = subprocess.run(["bash", SCRIPT, "--checar-relatorio", f.name, str(codigo)],
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout + p.stderr
    finally:
        os.unlink(f.name)


class GateVerificar(unittest.TestCase):
    def test_relatorio_bom_passa_mesmo_com_sandbox_faltando(self):
        code, out = checar(BOM, 1)
        self.assertEqual(code, 0, out)

    def test_pronto_com_codigo_zero_passa(self):
        code, out = checar(BOM.replace("[falta] bwrap", "[ok]    bwrap").replace(
            "Não está pronto: 1 item(ns) acima precisam de ajuste.", "Pronto para o estúdio."), 0)
        self.assertEqual(code, 0, out)

    def test_die_sem_falta_reprova(self):
        code, _ = checar("tune-up: não consegui saber a pasta do HyperFrames.\n", 1)
        self.assertNotEqual(code, 0)

    def test_traceback_reprova(self):
        code, _ = checar("Traceback (most recent call last):\nModuleNotFoundError: No module named 'x'\n", 1)
        self.assertNotEqual(code, 0)

    def test_codigo_fora_de_0_1_reprova(self):
        for codigo in (2, 3, 127):
            code, _ = checar(BOM, codigo)
            self.assertNotEqual(code, 0, codigo)

    def test_sem_resumo_reprova(self):
        code, _ = checar(BOM.replace("Não está pronto: 1 item(ns) acima precisam de ajuste.\n", ""), 1)
        self.assertNotEqual(code, 0)

    def test_cada_item_essencial_ausente_reprova(self):
        for rotulo in ("node", "ffprobe", "ffmpeg", "hyperframes", "chrome"):
            texto = "\n".join(l for l in BOM.splitlines() if not l.startswith("[ok]    %s:" % rotulo)) + "\n"
            code, _ = checar(texto, 1)
            self.assertNotEqual(code, 0, rotulo)

    def test_item_essencial_em_falta_reprova(self):
        code, _ = checar(BOM + "[falta] ffmpeg: falta o encoder libx264\n", 1)
        self.assertNotEqual(code, 0)

    def test_chrome_em_aviso_reprova(self):
        texto = BOM.replace("[ok]    chrome: chrome-headless-shell 152.0.7977.30 no cache do HyperFrames",
                            "[aviso] chrome: usando CHROME_PATH (não é o Chrome fixado do HyperFrames)")
        code, _ = checar(texto, 1)
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
