"""tune-up: detect a Windows machine without Git Bash (hooks run through `sh`)."""
import ntpath
import os
import shutil

# bash.exe here is the WSL launcher, not Git Bash.
_WSL = ("\\windows\\system32\\", "\\windowsapps\\")


def sem_git_bash(nt=None, which=shutil.which, env=None, isfile=os.path.isfile):
    """True when on Windows and no usable sh/Git Bash is found. Injectable, so any OS can test it."""
    if not (os.name == "nt" if nt is None else nt):
        return False
    env = os.environ if env is None else env
    forcado = env.get("CLAUDE_CODE_GIT_BASH_PATH")
    if forcado and isfile(forcado):
        return False
    for nome in ("sh", "bash"):
        achado = which(nome)
        if achado and not any(p in achado.replace("/", "\\").lower() for p in _WSL):
            return False
    raizes = []
    git = which("git")  # Claude Code finds Git Bash from git.exe: <git root>\bin\bash.exe
    if git and ntpath.isabs(git.replace("/", "\\")):  # `git.exe`, `.\git.exe`: no root
        raizes.append(ntpath.dirname(ntpath.dirname(git.replace("/", "\\"))))
    for var, rel in (("ProgramFiles", "Git"), ("ProgramW6432", "Git"), ("ProgramFiles(x86)", "Git"),
                     ("LocalAppData", "Programs\\Git")):
        if env.get(var):
            raizes.append(ntpath.join(env[var], rel))
    for raiz in raizes:
        for rel in ("bin\\bash.exe", "usr\\bin\\bash.exe", "usr\\bin\\sh.exe"):
            if isfile(ntpath.join(raiz, rel)):
                return False
    return True
