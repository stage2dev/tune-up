"""Atalhos para testes. Só pulam (SkipTest) onde a conta do Windows não pode criar symlink (WinError 1314)
ou a plataforma não tem symlink; qualquer outro erro sobe, como no os.symlink puro."""
import os
import subprocess
import unittest


def _sem_privilegio(e):
    return isinstance(e, NotImplementedError) or (os.name == "nt" and getattr(e, "winerror", None) == 1314)


def symlink(alvo, link, dir_=False):
    """os.symlink; pula o teste só quando a conta/plataforma não cria symlink."""
    try:
        os.symlink(alvo, link, target_is_directory=dir_)
    except (OSError, NotImplementedError) as e:
        if not _sem_privilegio(e):
            raise
        raise unittest.SkipTest("cannot create symlinks here: %s" % e)


def link_dir(alvo, link):
    """Atalho para PASTA. Fora do Windows é exatamente um symlink. No Windows sem privilégio vira junction
    (mklink /J, não pede privilégio); se a junction falhar, o teste dá erro (não pula calado)."""
    try:
        os.symlink(alvo, link, target_is_directory=True)
        return
    except (OSError, NotImplementedError) as e:
        if os.name != "nt" or not _sem_privilegio(e):
            raise
    r = subprocess.run([os.environ.get("COMSPEC") or "cmd", "/c", "mklink", "/J", os.path.abspath(link),
                        os.path.abspath(alvo)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
    if r.returncode != 0:
        raise OSError("mklink /J failed (%s): %r" % (r.returncode, r.stderr))
