"""Erro com texto simples para a tela (sem dependências: catalogo.py e wsl.py importam daqui)."""


class ErroAcao(Exception):
    """Erro com texto simples para a tela e o código HTTP certo."""

    def __init__(self, mensagem, codigo=400, execucao_id=None):
        Exception.__init__(self, mensagem)
        self.mensagem, self.codigo, self.execucao_id = mensagem, codigo, execucao_id
