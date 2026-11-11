"""Unit tests for regras/bash-estudio.json (positive list for Bash) through the panel hook.

Loads the studio fixture action the way the panel does (catalogo.validar_acao, then
trabalho.resolver_travas with a work folder that has a space and a '['), builds the hook
config and calls travas.decidir. No Chrome, no network, no session.
"""
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
PAINEL = os.path.join(os.path.dirname(STUDIO), "painel")
sys.path.insert(0, PAINEL)

import catalogo  # noqa: E402
import trabalho  # noqa: E402
import travas  # noqa: E402

RULES = os.path.join(STUDIO, "regras", "bash-estudio.json")
FIXTURE = os.path.join(PAINEL, "tests_reais", "acao_estudio.json")
WORK = "/proj [1]/x y/.tune-up/painel/dados/trabalhos/abc"
PLUGIN = "/opt/plug/tune-up-studio/2.6.0"
HF = PLUGIN + "/node/node_modules/.bin/hyperframes"
PY = "python3 -I " + PLUGIN + "/scripts/"
WL = "-protocol_whitelist file,pipe -i "

ALLOWED = [
    HF + " render fonte -o video.mp4 --fps 30 --quiet",
    HF + " check fonte --json --strict",
    HF + " snapshot fonte --at 0.2,1.0,9.8",
    HF + " lint fonte",
    HF + " render fonte -o " + WORK + "/saida/video.mp4",
    "/opt/plug/tune-up-studio/node/node_modules/.bin/hyperframes info fonte",
    "ffmpeg -filters",
    "ffmpeg -hide_banner -y -loop 1 -t 3 " + WL + "s1.png " + WL + "s2.png"
    " -filter_complex_script graph.txt -vcodec libx264 -pix_fmt yuv420p -movflags +faststart -an out.mp4",
    "ffmpeg -y " + WL + WORK + "/s1.png -frames 1 " + WORK + "/out.png",
    "ffprobe -v error -show_streams -of json video.mp4",
    PY + "qa_video.py --source fonte --video video.mp4 --check-json check.json --out qa.json",
    PY + "reserva_slides.py --slides slides --out video.mp4",
    PY + "video_ou_reserva.py --source fonte --slides slides --out video.mp4",
    PY + "fontes.py",
    PY + "fontes.py --trabalho " + WORK,
]

DENIED = [
    HF + " cloud render fonte",
    HF + " lambda deploy",
    HF + " skills",
    HF + " upgrade",
    HF + " snapshot fonte --describe",
    HF + " snapshot fonte --describe=all",
    HF + " render --docker fonte -o v.mp4",
    HF + " render fonte -o /tmp/v.mp4",
    HF + " render fonte -o ../v.mp4",
    HF + " render fonte -o/tmp/v.mp4",
    HF + " render fonte --output=/tmp/v.mp4",
    HF + " render fonte -o ~/v.mp4",
    HF + " render fonte -o " + WORK + "x/v.mp4",  # sibling folder, not {trabalho}
    HF + " render fonte; rm -rf ~",
    HF + " render fonte && curl x",
    HF + " render fonte | tee x",
    HF + " render fonte\nrm x",
    HF + " render $(echo fonte)",
    HF + " render 'fonte'",
    WORK + "/node/node_modules/.bin/hyperframes render fonte",  # binary planted in {trabalho}
    WORK.upper() + "/tune-up-studio/node/node_modules/.bin/hyperframes render fonte",
    "/opt//plug/tune-up-studio/node/node_modules/.bin/hyperframes render fonte",
    "npx --no-install hyperframes render fonte",
    "hyperframes render fonte",
    "ffmpeg " + WL + "https://example.com/a.mp4 out.mp4",
    "ffmpeg -i https://example.com/a.mp4 out.mp4",
    "ffmpeg -i s1.png out.mp4",  # input without the whitelist
    "ffmpeg -protocol_whitelist file,pipe,tcp -i s1.png out.mp4",
    "ffmpeg " + WL + "s1.png -i s2.png out.mp4",  # second input without the whitelist
    "ffmpeg " + WL + "s1.png /tmp/out.mp4",
    "ffmpeg " + WL + "s1.png -f mp4 tcp:host",
    "ffmpeg " + WL + "s1.png -filter_complex [0]scale=1:1[a];[a]null out.mp4",
    "ffmpeg " + WL + "s1.png out.mp4; curl x",
    "ffprobe https://example.com/a.mp4",
    "ffprobe /etc/hosts",
    "python3 -c print(1)",
    "python3 x.py",
    "python3 -I " + WORK + "/tune-up-studio/scripts/qa_video.py",
    PY + "qa_video.py --out /tmp/qa.json",
    PY + "outro.py",
    PY + "fontes.py --trabalho /tmp/outro",
    PY + "fontes.py 'system-ui, sans-serif'",
    "python3 -I " + WORK + "/tune-up-studio/scripts/fontes.py",
    PY + "qa_video.py --source fonte --video v.mp4 --check-json c.json --ffprobe python3",
    PY + "reserva_slides.py --slides s --out v.mp4 --ffmpeg python3",
    PY + "video_ou_reserva.py --source fonte --slides s --out v.mp4 --hyperframes x",
    "FFMPEG " + WL + "s1.png out.mp4",
    " ffmpeg -filters",
    "cat /etc/hosts",
    "curl https://example.com",
    "rm -rf fonte",
]


# A work folder whose path fits the plugin pattern (no space), to try other names for it.
REAL = "/private/tmp/p/.tune-up/painel/dados/trabalhos/abc"
ALIASES = ["/tmp/p/.tune-up/painel/dados/trabalhos/abc",
           "/System/Volumes/Data/private/tmp/p/.tune-up/painel/dados/trabalhos/abc",
           "/proc/self/cwd", "/proc/123/cwd", "/dev/fd/3", "/private/tmp/p/.tune-up/painel/dados/trabalhos/abc"]


def hook_conf(work=WORK):
    with open(FIXTURE, encoding="utf-8") as f:
        acao = catalogo.validar_acao(json.load(f)["acoes"][0])
    return travas.config_gancho(trabalho.resolver_travas(acao, work))


class RulesFile(unittest.TestCase):
    def test_fixture_carries_the_same_rules(self):
        with open(RULES, encoding="utf-8") as f:
            rules = json.load(f)["negar"]
        with open(FIXTURE, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["acoes"][0]["negar"], rules)

    def test_rules_pass_core_validation(self):
        with open(RULES, encoding="utf-8") as f:
            out = travas.validar_travas({"negar": json.load(f)["negar"]})
        self.assertEqual(len(out["regras_negar"]), 6)


class Decide(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conf = hook_conf()

    def test_allowed_commands_pass(self):
        for cmd in ALLOWED:
            self.assertIsNone(travas.decidir(self.conf, "Bash", {"command": cmd}, WORK), cmd)

    def test_forbidden_commands_are_denied(self):
        for cmd in DENIED:
            got = travas.decidir(self.conf, "Bash", {"command": cmd}, WORK)
            self.assertIsNotNone(got, cmd)
            self.assertEqual(got[0], "deny", cmd)

    def test_other_tools_untouched(self):
        self.assertIsNone(travas.decidir(self.conf, "Read", {"file_path": WORK + "/fonte/index.html"}, WORK))

    def test_other_names_of_the_work_folder_are_denied(self):
        conf = hook_conf(REAL)
        for base in ALIASES:
            for cmd in ("python3 -I " + base + "/tune-up-studio/scripts/qa_video.py --source fonte",
                        base + "/tune-up-studio/node/node_modules/.bin/hyperframes render fonte"):
                with self.subTest(cmd=cmd):
                    got = travas.decidir(conf, "Bash", {"command": cmd}, REAL)
                    self.assertIsNotNone(got, cmd)
                    self.assertEqual(got[0], "deny", cmd)
        self.assertIsNone(travas.decidir(conf, "Bash", {"command": PY + "qa_video.py --source fonte"}, REAL))

    def test_long_command_is_fast(self):
        cmd = "ffmpeg " + " ".join([WL + "s%d.png" % i for i in range(60)]) + " out.mp4 x"
        t0 = time.time()
        travas.decidir(self.conf, "Bash", {"command": cmd + " ;"}, WORK)
        self.assertLess(time.time() - t0, 1.0)


if __name__ == "__main__":
    unittest.main()
