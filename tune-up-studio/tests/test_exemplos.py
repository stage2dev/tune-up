"""The Forno Miúdo example pieces pass the attention checks (scripts/qa_atencao.py). No Chrome, no network.

The pieces are copied into a throwaway project laid out as a studio job:
<tmp>/.tune-up/estudio/marca/marca.json (colors from gabarito.json) and
<tmp>/.tune-up/estudio/trabalhos/<job>/ with entrada.md (= briefing.md), estrategia.md,
copy.md and q1/fonte for the post, fonte for the reel.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
EXEMPLO = os.path.join(STUDIO, "exemplos", "forno-miudo")
sys.path.insert(0, os.path.join(STUDIO, "scripts"))

POST = os.path.join(EXEMPLO, "post-4x5")
VIDEO = os.path.join(EXEMPLO, "video-9x16", "fonte")
QUADROS = ["q1"]  # frames of the post job, as checar_peca_post takes them
CLIP_RE = re.compile(r'<(?:p|div|img|svg)\b[^>]*\bid="([^"]+)"[^>]*\bdata-start="([\d.]+)"[^>]*'
                     r'\bdata-duration="([\d.]+)"', re.S)


def ignorar(_pasta, nomes):
    return [n for n in nomes if n.startswith(".hyperframes")]


def falhas(checks):
    return [(c["name"], c["details"]) for c in checks if not c["ok"]]


class Exemplos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="exemplos-")
        marca = os.path.join(cls.tmp, ".tune-up", "estudio", "marca")
        os.makedirs(marca)
        with open(os.path.join(EXEMPLO, "gabarito.json"), encoding="utf-8") as f:
            gabarito = json.load(f)
        campos = {"cores.%s" % k: {"valor": v} for k, v in gabarito["colors"].items()}
        campos["nome"] = {"valor": gabarito["name"]}
        with open(os.path.join(marca, "marca.json"), "w", encoding="utf-8") as f:
            json.dump({"campos": campos}, f, ensure_ascii=False)
        trabalhos = os.path.join(cls.tmp, ".tune-up", "estudio", "trabalhos")
        cls.post, cls.video = os.path.join(trabalhos, "post"), os.path.join(trabalhos, "video")
        for job in (cls.post, cls.video):
            os.makedirs(job)
            shutil.copy(os.path.join(EXEMPLO, "briefing.md"), os.path.join(job, "entrada.md"))
            shutil.copy(os.path.join(EXEMPLO, "estrategia.md"), os.path.join(job, "estrategia.md"))
        shutil.copytree(os.path.join(POST, "fonte"), os.path.join(cls.post, "q1", "fonte"), ignore=ignorar)
        shutil.copy(os.path.join(POST, "copy.md"), os.path.join(cls.post, "copy.md"))
        shutil.copytree(VIDEO, os.path.join(cls.video, "fonte"), ignore=ignorar)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_post_frame_passes_attention(self):
        import qa_atencao
        checks = qa_atencao.checar_quadro(os.path.join(self.post, "q1", "fonte"))
        self.assertTrue(checks)
        self.assertEqual(falhas(checks), [])

    def test_post_piece_passes_attention(self):
        import qa_atencao
        checks = qa_atencao.checar_peca_post(self.post, QUADROS)
        self.assertTrue(checks)
        self.assertEqual(falhas(checks), [])

    def test_video_passes_attention(self):
        import qa_atencao
        checks = qa_atencao.checar_video(os.path.join(self.video, "fonte"), 10, "hyperframes")
        self.assertTrue(checks)
        self.assertEqual(falhas(checks), [])
        self.assertIn("transicoes", [c["name"] for c in checks])


class DoKit(unittest.TestCase):
    """The example pieces are what the kit writes from the example's own `peca.json` and `heroi.svg`."""

    def test_inputs_of_the_kit_are_in_the_example(self):
        for nome in ("heroi.svg", os.path.join("post-4x5", "peca.json"), os.path.join("video-9x16", "peca.json")):
            self.assertTrue(os.path.isfile(os.path.join(EXEMPLO, nome)), nome)
        with open(os.path.join(VIDEO, "index.html"), encoding="utf-8") as f:
            video = f.read()
        import qa_script
        self.assertEqual(qa_script.checar(video), [])  # the engine pasted whole + recipe calls only
        self.assertIn('id="heroi_quadro"', video)       # one hero for the whole reel
        with open(os.path.join(POST, "fonte", "index.html"), encoding="utf-8") as f:
            self.assertNotIn("<script", f.read())


class VideoTiming(unittest.TestCase):
    """Without qa_atencao: the example reel keeps the scene timing the skill and --tempos use."""

    def setUp(self):
        with open(os.path.join(VIDEO, "index.html"), encoding="utf-8") as f:
            self.html = f.read()
        self.clips = {i: (float(s), float(d)) for i, s, d in CLIP_RE.findall(self.html)}

    def test_scenes_are_contiguous_and_match_the_reserve_pattern(self):
        scenes = {}
        for cid, timing in self.clips.items():
            m = re.match(r"s(\d+)_", cid)
            if m:
                scenes.setdefault(int(m.group(1)), set()).add(timing)
        self.assertEqual(sorted(scenes), [1, 2, 3, 4])
        self.assertTrue(all(len(t) == 1 for t in scenes.values()), scenes)  # one timing per scene
        timing = [scenes[n].pop() for n in sorted(scenes)]
        # round 6: cuts off the 0.25 s grid, so a sampled frame never lands on a transition (kit_video.TEMPOS)
        self.assertEqual([d for _, d in timing], [1.875, 2.5, 2.5, 3.125])
        self.assertEqual([s for s, _ in timing], [0, 1.875, 4.375, 6.875])
        for cid in ("tr1", "tr2", "tr3"):
            start, dur = self.clips[cid]
            self.assertIn(round(start + dur / 2, 3), (1.875, 4.375, 6.875))
        self.assertEqual(self.clips["deco1"], (0.0, 10.0))

    def test_cover_has_no_logo_and_every_title_names_an_arrangement(self):
        self.assertNotIn("s1_logo", self.clips)
        self.assertNotIn("s1_marca", self.clips)
        found = re.findall(r'id="s(\d)_titulo" class="clip (l-[a-z]+)"', self.html)
        self.assertEqual([n for n, _ in found], ["1", "2", "3", "4"])
        names = [lay for _, lay in found]
        self.assertTrue(all(a != b for a, b in zip(names, names[1:])), names)
        self.assertNotIn("animation-delay", self.html)
        self.assertNotIn("border-radius", self.html)


if __name__ == "__main__":
    unittest.main()
