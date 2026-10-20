"""Helpers comuns dos testes do tune-up (unittest, só stdlib)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "guarda.py")

IS_WIN = os.name == "nt"
SEM_MODOS = "Windows has no POSIX permission bits (mode, owner, group)"


def sh_path(p):
    """The spelling a Bash command uses for `p`: on Windows (Git Bash) an unquoted backslash is an
    escape character, so `C:\\x` must be written `C:/x`."""
    return p.replace("\\", "/") if IS_WIN else p


def mkdtemp(prefix="tuneup-teste-"):
    """Real path of a fresh temp dir that is NOT under /tmp or /private/tmp on POSIX, nor under
    %TEMP% on Windows.

    The guard treats /tmp (Windows: %TEMP%, Git Bash's /tmp) as free scratch space in research
    mode, so a test tree there (the default on Linux and Windows) would hide the decisions the
    tests want to see.
    """
    base = None
    if IS_WIN:
        base = os.path.realpath(os.path.expanduser("~"))
    else:
        padrao = os.path.realpath(tempfile.gettempdir())
        if any(padrao == r or padrao.startswith(r + os.sep) for r in ("/tmp", "/private/tmp")):
            base = os.path.realpath(os.path.expanduser("~"))
    return os.path.realpath(tempfile.mkdtemp(prefix=prefix, dir=base))


def rmtree(caminho):
    """rmtree that also removes read-only entries (needed on Windows)."""
    def _forcar(func, path, _exc):
        try:
            os.chmod(path, 0o700)
            func(path)
        except OSError:
            pass
    shutil.rmtree(caminho, onerror=_forcar)


def symlink(alvo, link, dir_=False):
    """os.symlink, or skip the test when the platform/account cannot create symlinks."""
    try:
        os.symlink(alvo, link, target_is_directory=dir_)
    except (OSError, NotImplementedError) as e:
        raise unittest.SkipTest("cannot create symlinks here: %s" % e)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = mkdtemp("tuneup-teste-")
        self.dados = os.path.join(self.tmp, "dados")
        self.cwd = os.path.join(self.tmp, "proj")
        os.makedirs(self.cwd)
        self.env = {k: v for k, v in os.environ.items()
                    if not k.startswith("TUNEUP_") and k not in ("CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_DATA")}
        self.env.update({"TUNEUP_TESTE": "1", "CLAUDE_PLUGIN_DATA": self.dados, "HOME": self.tmp,
                         "USERPROFILE": self.tmp,  # os.path.expanduser reads this one on Windows
                         "TUNEUP_FAKE_BRANCH": "feat/x", "TUNEUP_FAKE_GH_MERGED": ""})
        if self.USER_JSON is not None:  # old classes assert pt-BR texts
            self.user_json(self.USER_JSON)

    USER_JSON = {"language": "pt-BR", "owner": "Dono", "reply_style": "summary"}

    def user_json(self, dados):
        p = os.path.join(self.tmp, "user.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dados, f)
        self.env["TUNEUP_USER_JSON"] = p
        return p

    def tearDown(self):
        for raiz, dirs, _ in os.walk(self.tmp):
            for x in dirs:
                try:
                    os.chmod(os.path.join(raiz, x), 0o755)
                except OSError:
                    pass
        rmtree(self.tmp)

    def rodar(self, evento, entrada, env=None, bruto=None):
        e = dict(self.env)
        e.update(env or {})
        if bruto is None:
            dados = {"session_id": "s1", "prompt_id": "p1", "cwd": self.cwd}
            dados.update(entrada)
            bruto = json.dumps(dados)
        r = subprocess.run([sys.executable, SCRIPT, evento], input=bruto, capture_output=True,
                           text=True, encoding="utf-8", env=e, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def confiar(self, caminho):
        r = subprocess.run([sys.executable, SCRIPT, "confiar", caminho], capture_output=True,
                           text=True, encoding="utf-8", env=self.env, timeout=20)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r

    def sessao(self, **campos):
        p = os.path.join(self.dados, "sessoes")
        os.makedirs(p, exist_ok=True)
        d = {"auth_prompt_id": None, "modo_pesquisa": False, "atualizado": 0}
        d.update(campos)
        with open(os.path.join(p, "s1.json"), "w", encoding="utf-8") as f:
            json.dump(d, f)

    def ler_sessao(self):
        with open(os.path.join(self.dados, "sessoes", "s1.json"), encoding="utf-8") as f:
            return json.load(f)

    # asserts
    def decisao(self, saida):
        if not saida:
            return None
        h = saida["hookSpecificOutput"]
        if "permissionDecision" in h:
            return {"deny": "bloquear", "ask": "perguntar"}[h["permissionDecision"]]
        if "updatedInput" in h:
            return "corrigir"
        return "avisar"

    def bash(self, cmd, env=None):
        return self.decisao(self.rodar("bash", {"tool_name": "Bash", "tool_input": {"command": cmd}}, env))


class AgentBase(Base):
    def agent(self, ti, extra=None):
        e = {"tool_name": "Agent", "tool_input": ti}
        e.update(extra or {})
        return self.rodar("agent", e)

    def transcript(self, modelo):
        p = os.path.join(self.tmp, "t.jsonl")
        with open(p, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "user", "message": {"content": "oi"}}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {"model": modelo}}) + "\n")
            f.write(json.dumps({"type": "system", "subtype": "x"}) + "\n")
        return p


class PromptBase(Base):
    def prompt(self, texto):
        return self.rodar("prompt", {"prompt": texto, "hook_event_name": "UserPromptSubmit"})

    def ctx(self, s):
        return s["hookSpecificOutput"]["additionalContext"] if s else ""


class FakeBin(Base):
    def fake(self, nome, corpo):
        if IS_WIN:  # the guard runs `git`/`gh` without a shell: CreateProcess only finds real .exe files
            raise unittest.SkipTest("a sh-script fake of %s cannot be found on PATH on Windows" % nome)
        b = os.path.join(self.tmp, "bin")
        os.makedirs(b, exist_ok=True)
        p = os.path.join(b, nome)
        with open(p, "w", newline="\n", encoding="utf-8") as f:
            f.write("#!/bin/sh\necho \"$@\" >> %s/%s.chamadas\n%s\n" % (self.tmp, nome, corpo))
        os.chmod(p, 0o755)
        self.env["PATH"] = b + os.pathsep + self.env.get("PATH", "")

    def chamadas(self, nome):
        try:
            with open(os.path.join(self.tmp, nome + ".chamadas"), encoding="utf-8") as f:
                return f.read().splitlines()
        except OSError:
            return []
