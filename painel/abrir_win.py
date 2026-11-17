"""Windows: abre `claude attach <id>` numa aba do Windows Terminal ou numa janela nova do cmd.

Sem pipes de propósito: com capture_output, o cmd/wt passa as pontas de escrita para a
janela nova, o communicate() nunca vê o fim e o pedido HTTP fica preso até a pessoa fechar
a janela. Aqui o Popen não recebe stdin/stdout/stderr e usa close_fds=True (nada é herdado).
"""
import shutil
import subprocess

# cmd.exe relê a linha e o wt.exe separa subcomandos por ';'. Com qualquer um destes no
# caminho do claude, não abre: devolve o comando para a pessoa colar.
METACHAR_WIN = set('&|<>^%!"();')
CREATE_NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0x00000010)
ESPERA = 3  # segundos para o wt.exe/cmd devolver um erro imediato


def abrir_janela_padrao(args, cwd, nova_console):
    """Abre sem pipes e sem herdar handles. True se abriu (ou segue aberto depois da espera)."""
    try:
        p = subprocess.Popen(args, cwd=cwd, close_fds=True,
                             creationflags=CREATE_NEW_CONSOLE if nova_console else 0)
    except OSError:
        return False
    try:
        return p.wait(timeout=ESPERA) == 0
    except subprocess.TimeoutExpired:
        return True  # a janela do cmd /k fica aberta: é o esperado


def abrir(claude, exec_id, cwd, abrir_janela=abrir_janela_padrao, which=None):
    """True/False se tentou abrir; None se recusou por metacaractere."""
    if METACHAR_WIN & set(claude + exec_id):
        return None
    dentro = ["cmd", "/k", claude, "attach", exec_id]
    if (which or shutil.which)("wt.exe"):
        return abrir_janela(["wt.exe", "-w", "0", "new-tab"] + dentro, cwd, False)
    return abrir_janela(dentro, cwd, True)  # janela nova do cmd, sem o `start` no meio
