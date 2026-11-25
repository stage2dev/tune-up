"""Fake `claude`, `git` and `node` for test_preparar.py; PATH has only the fakes."""
import json
import os
import subprocess
import sys
import time

from base import FakeBin, IS_WIN, SCRIPT

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import preparar  # noqa: E402

PINS = {f["nome"]: f["commit"] for f in preparar.FONTES}

# Stateful `claude plugin`: mundo.json = {"mkts": {name: {...}}, "plugins": {id: {...}}, "quebra": [first words]}
FAKE_CLAUDE = r'''
import json, os, sys
mundo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mundo.json")
with open(mundo) as f:
    m = json.load(f)
cfg = os.environ["CLAUDE_CONFIG_DIR"]
a = [x for x in sys.argv[2:] if x != "--json"]
def env_tem():
    try:
        with open(os.path.join(cfg, "settings.json")) as f:
            return "PONYTAIL_SUBAGENT_MATCHER" in json.load(f).get("env", {})
    except OSError:
        return False
def fim(rc=0):
    with open(mundo, "w") as f:
        json.dump(m, f)
    sys.exit(rc)
for q in m["quebra"]:
    if " ".join(a).startswith(q):
        sys.exit(1)
if a == ["list"]:
    print(json.dumps([dict(p, id=i) for i, p in m["plugins"].items()]))
elif a == ["marketplace", "list"]:
    print(json.dumps([dict(x, name=n) for n, x in m["mkts"].items()]))
elif a[:2] == ["marketplace", "add"]:
    repo, _, ref = a[2].partition("#")
    nome = {"affaan-m/ecc": "ecc"}.get(repo, repo.split("/")[1])
    loc = os.path.join(cfg, "plugins", "marketplaces", nome)
    os.makedirs(os.path.join(loc, ".git"), exist_ok=True)
    with open(os.path.join(loc, ".git", "HEAD"), "w") as f:
        f.write(m["commits"][nome])
    m["mkts"][nome] = {"repo": repo, "ref": ref, "installLocation": loc}
elif a[:2] == ["marketplace", "remove"]:
    m["mkts"].pop(a[2])
elif a[0] == "install":
    nome = a[1].split("@")[0]
    cave = os.path.join(os.environ["XDG_CONFIG_HOME"], "caveman", "config.json")
    m["limites"][nome] = {"ponytail": env_tem(), "caveman": os.path.isfile(cave)}.get(nome, True)
    cache = os.path.join(cfg, "plugins", "cache", nome)
    if nome == "ecc":
        for s in ("python-patterns", "react-patterns"):
            os.makedirs(os.path.join(cache, "skills", s), exist_ok=True)
            with open(os.path.join(cache, "skills", s, "SKILL.md"), "w") as f:
                f.write("---\nname: %s\ndescription: x\n---\n" % s)
    m["plugins"][a[1]] = {"enabled": True, "installPath": cache}
    if m.get("move"):
        with open(os.path.join(m["mkts"][nome]["installLocation"], ".git", "HEAD"), "w") as f:
            f.write("f" * 40)
elif a[0] == "disable":
    m["plugins"][a[1]]["enabled"] = False
elif a[0] == "uninstall":
    if a[1] not in m["plugins"]:
        fim(1)
    del m["plugins"][a[1]]
fim()
'''


class PrepararBase(FakeBin):
    def setUp(self):
        super().setUp()
        self.cfg, self.conf = os.path.join(self.tmp, "cfg"), os.path.join(self.tmp, "conf")
        os.makedirs(self.cfg)
        os.makedirs(self.conf)
        self.env.update({"CLAUDE_CONFIG_DIR": self.cfg, "XDG_CONFIG_HOME": os.path.join(self.tmp, "xdg"),
                         "TUNEUP_USER_JSON": os.path.join(self.conf, "user.json")})
        for k in ("TUNEUP_TESTE", "CI", preparar.RECURSAO):
            self.env.pop(k, None)
        self.usuario({})
        with open(os.path.join(self.tmp, "fake.py"), "w") as f:
            f.write(FAKE_CLAUDE)
        self.mundo(mkts={}, plugins={}, quebra=[], limites={}, commits=dict(PINS))
        if not IS_WIN:
            self.fake("claude", 'exec "%s" "%s/fake.py" "$@"' % (sys.executable, self.tmp))
            self.fake("git", 'IFS= read -r x < "$2/HEAD" || :; printf "%s\\n" "$x"')
            self.fake("node", "exit 0")
            self.env["PATH"] = os.path.join(self.tmp, "bin")  # nothing real can be reached

    def usuario(self, d):
        with open(os.path.join(self.conf, "user.json"), "w") as f:
            json.dump(d, f)

    def mundo(self, **novo):
        p = os.path.join(self.tmp, "mundo.json")
        m = {}
        if os.path.exists(p):
            with open(p) as f:
                m = json.load(f)
        m.update(novo)
        with open(p, "w") as f:
            json.dump(m, f)
        return m

    def ler(self, nome):
        try:
            with open(os.path.join(self.conf, nome)) as f:
                return json.load(f)
        except OSError:
            return None

    def grava(self, nome, d):
        with open(os.path.join(self.conf, nome), "w") as f:
            json.dump(d, f)

    def settings(self, d=None):
        p = os.path.join(self.cfg, "settings.json")
        if d is not None:
            with open(p, "w") as f:
                json.dump(d, f)
        try:
            with open(p) as f:
                return json.load(f)
        except OSError:
            return None

    def mexeu(self):
        """`claude plugin` calls that change something."""
        return [c for c in self.chamadas("claude") if "list" not in c.split()]

    def preparar(self, token="t1"):
        """The body of the detached process, run here and now."""
        with open(os.path.join(self.conf, "preparo.lock"), "w") as f:
            f.write(token)
        r = subprocess.run(preparar.argv_filho(token), env=self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual((r.returncode, r.stderr), (0, ""))
        self.assertFalse(os.path.exists(os.path.join(self.conf, "preparo.lock")))
        return self.ler("preparo.resultado.json")

    def inicio(self, source="startup"):
        s = self.rodar("inicio", {"source": source})
        return (s or {}).get("systemMessage", "")

    def espera(self, nome):
        fim = time.time() + 30
        while time.time() < fim and (self.ler(nome) is None or os.path.exists(os.path.join(self.conf, "preparo.lock"))):
            time.sleep(0.05)
        return self.ler(nome)
