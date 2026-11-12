"""SessionStart do tune-up-vendas: UMA linha quando o projeto liga a tela Vendas e o WhatsApp ainda não está
preparado; nada em qualquer outro caso. Só lê arquivos (painel.json do projeto, a pasta de dados externa e o estado do
preparo); sem rede, sem banco, sem ler o .env. Qualquer erro = silêncio e saída 0. Python 3.9, só biblioteca padrão."""
import importlib.util
import json
import os
import sys

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LINHA = ("tune-up-vendas: o WhatsApp deste projeto ainda não está preparado. No painel, tela Vendas, aba Conexão, o "
         "botão \"Preparar tudo\" faz isso (ou use /tune-up-vendas:instalar).")
PAINEL_MAX = 64 * 1024


def _carregar(nome):
    spec = importlib.util.spec_from_file_location("tune_up_vendas_inicio_" + nome,
                                                  os.path.join(PLUGIN, "servico", nome + ".py"))
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def raiz_do_projeto(cwd):
    """Primeira pasta com .tune-up/painel.json subindo a partir do cwd, ou None."""
    atual = os.path.realpath(cwd)
    while True:
        if os.path.isfile(os.path.join(atual, ".tune-up", "painel.json")):
            return atual
        acima = os.path.dirname(atual)
        if acima == atual:
            return None
        atual = acima


def modulo_ligado(raiz):
    caminho = os.path.join(raiz, ".tune-up", "painel.json")
    if os.path.getsize(caminho) > PAINEL_MAX:
        return False
    with open(caminho, encoding="utf-8") as f:
        conf = json.load(f)
    lista = conf.get("modulos_de_plugins") if isinstance(conf, dict) else None
    return isinstance(lista, list) and any(isinstance(e, str) and e.startswith("tune-up-vendas@")
                                           and e.endswith(":vendas") for e in lista)


def preparado(raiz, base=None):
    """False se faltam os arquivos da Evolution ou se o último preparo parou (falhou, precisa do dono, interrompido).
    Um preparo rodando agora conta como preparado (não avisa no meio dele)."""
    pasta = _carregar("pasta").caminho_da_pasta(raiz, base)
    try:
        with open(os.path.join(pasta, "preparo.json"), encoding="utf-8") as f:
            estado = json.load(f)
    except (OSError, ValueError):
        estado = None
    final = estado.get("estado") if isinstance(estado, dict) else None
    if final == "rodando":
        if _carregar("preparo_sistema").pid_vivo(estado.get("pid")):
            return True
        return False   # o processo saiu no meio
    if not all(os.path.isfile(os.path.join(pasta, "evolution", n)) for n in ("compose.yml", ".env")):
        return False
    return final not in ("falhou", "precisa_do_dono")


def linha(entrada, base=None):
    """O texto a mostrar ("" = nada) para a entrada JSON do gancho. Nunca levanta."""
    try:
        dados = json.loads(entrada or "{}")
        cwd = dados.get("cwd") if isinstance(dados, dict) else None
        raiz = raiz_do_projeto(cwd if isinstance(cwd, str) and cwd else os.getcwd())
        if raiz is None or not modulo_ligado(raiz) or preparado(raiz, base):
            return ""
        return LINHA
    except Exception:   # o gancho nunca atrapalha a sessão
        return ""


def main():
    try:
        entrada = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read(1024 * 1024)
        texto = linha(entrada)
        if texto:
            print(texto)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.dont_write_bytecode = True
    sys.exit(main())
