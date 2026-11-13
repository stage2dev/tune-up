"""Studio skills are loaded by the core plugin as /tune-up:*."""
import glob
import json
import os
import re
import sys
import unittest

STUDIO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(STUDIO)
sys.path.insert(0, os.path.join(STUDIO, "painel"))
sys.path.insert(0, os.path.join(ROOT, "painel"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
SKILLS = ["post", "video", "anuncio", "marca", "marca-ler"]
# node/: o hyperframes mora em tune-up-studio/node (ou em <dados>/estudio-node, vindo do painel)
BARE = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/(scripts|referencias|formatos\.json|kit|node/)")


class SkillsNucleo(unittest.TestCase):
    def test_disable_model_invocation(self):
        for s in SKILLS:
            txt = open(os.path.join(STUDIO, "skills", s, "SKILL.md"), encoding="utf-8").read()
            front = txt.split("---")[1]
            self.assertIn("disable-model-invocation: true", front.splitlines(), s)

    def test_manifest(self):
        with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
            m = json.load(f)
        self.assertIn("./tune-up-studio/skills", m["skills"])
        self.assertNotIn("agents", m)

    def test_paths_have_studio_prefix(self):
        files = glob.glob(os.path.join(STUDIO, "skills", "*", "SKILL.md"))
        files += glob.glob(os.path.join(STUDIO, "referencias", "*"))
        for f in files:
            if os.path.isfile(f):
                self.assertIsNone(BARE.search(open(f, encoding="utf-8").read()), f)

    def test_sandbox_accepts_core_install_path(self):
        import test_regras_bash as t
        cmd = "python3 -I /opt/plug/tune-up/tune-up/2.11.0/tune-up-studio/scripts/qa_imagem.py x"
        got = t.travas.decidir(t.hook_conf(), "Bash", {"command": cmd}, t.WORK)
        self.assertIsNone(got, got)


if __name__ == "__main__":
    unittest.main()
