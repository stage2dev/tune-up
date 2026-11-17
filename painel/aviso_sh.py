"""Aviso do painel: Windows sem Git Bash (cópia de scripts/tuneup/gitbash.py; o painel não importa o plugin)."""
import ntpath
import os
import shutil

# bash.exe aqui é o lançador do WSL, não o Git Bash.
_WSL = ("\\windows\\system32\\", "\\windowsapps\\")


def sem_git_bash(nt=None, which=shutil.which, env=None, isfile=os.path.isfile):
    """True no Windows sem sh/Git Bash utilizável. Injetável, para testar em qualquer sistema."""
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


AVISO = ("Git Bash não encontrado: as travas do tune-up estão desligadas nas sessões do Claude. "
         "Instale o Git for Windows ou defina CLAUDE_CODE_GIT_BASH_PATH.")


def somar(avisos, **kw):
    """Põe o aviso no topo de `avisos` (vai para a tela e para o stderr do painel) quando falta o Git Bash."""
    if sem_git_bash(**kw):
        avisos.insert(0, AVISO)
