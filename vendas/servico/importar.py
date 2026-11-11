"""Importa um CSV de leads no serviço que está rodando (grande demais para colar na tela; até 2 MB):

    python3 -B <plugin>/servico/importar.py --projeto <raiz> arquivo.csv --origem <origem> --base-legal <base>

Fala com o serviço DESTE projeto pela porta gravada no banco e pelo token da pasta de dados (arquivo 0600); recusa
se o serviço estiver parado. Mostra só contagens e o número das linhas recusadas (nunca o telefone)."""
import os
import sys

if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.dont_write_bytecode = True

import argparse  # noqa: E402
import datetime  # noqa: E402
import http.client  # noqa: E402
import json  # noqa: E402
import pathlib  # noqa: E402
import sqlite3  # noqa: E402
import urllib.parse  # noqa: E402

from servico import banco, leads, pasta  # noqa: E402

VIVO_S = 15
ARQUIVO_TOKEN = "token_envio"


class Falha(Exception):
    pass


def _config(arquivo):
    if not os.path.isfile(arquivo) or not os.path.exists(arquivo + "-shm"):
        raise Falha("O serviço de Vendas deste projeto está parado. Ligue-o num terminal e tente de novo.")
    try:
        con = sqlite3.connect(pathlib.Path(os.path.abspath(arquivo)).as_uri() + "?mode=ro", uri=True, timeout=2)
        try:
            bate = con.execute("SELECT em FROM batimento WHERE id = 1").fetchone()
            conf = dict(con.execute("SELECT chave, valor FROM config WHERE chave IN ('servico_porta', "
                                    "'servico_marca')").fetchall())
        finally:
            con.close()
        quando = datetime.datetime.fromisoformat(bate[0]) if bate else None
    except (sqlite3.Error, ValueError, TypeError):
        raise Falha("Não consegui ler o banco do serviço de Vendas deste projeto.")
    agora = datetime.datetime.now(datetime.timezone.utc)
    if quando is None or abs((agora - quando).total_seconds()) > VIVO_S:
        raise Falha("O serviço de Vendas deste projeto está parado. Ligue-o num terminal e tente de novo.")
    return conf


def _pedir(porta, metodo, caminho, corpo=None, cab=None):
    con = http.client.HTTPConnection("127.0.0.1", porta, timeout=30)
    try:
        con.request(metodo, caminho, body=corpo, headers=dict(cab or {}))
        r = con.getresponse()
        bruto = r.read().decode("utf-8", "replace")
        return r.status, json.loads(bruto or "{}")
    except (OSError, ValueError, http.client.HTTPException):
        raise Falha("O serviço de Vendas não respondeu.")
    finally:
        con.close()


def enviar(raiz, arquivo_csv, origem, base_legal, base_legal_texto=None, base=None):
    """Devolve o resumo do serviço. Falha (Falha) com mensagem em pt-BR; nunca ecoa conteúdo do arquivo."""
    leads.base_legal(base_legal, base_legal_texto)  # confere antes de qualquer pedido
    try:
        if os.path.getsize(arquivo_csv) > leads.ARQUIVO_MAX:
            raise Falha("Arquivo grande demais (máximo 2 MB). Divida o arquivo.")
        with open(arquivo_csv, "rb") as f:
            corpo = f.read()
    except OSError:
        raise Falha("Não consegui ler o arquivo.")
    dados = pasta.caminho_da_pasta(raiz, base)
    conf = _config(os.path.join(dados, banco.ARQUIVO))
    porta = conf.get("servico_porta") or ""
    if conf.get("servico_marca") != os.path.basename(dados) or not porta.isdigit():
        raise Falha("O serviço de Vendas deste projeto não registrou a porta. Reinicie-o e tente de novo.")
    codigo, saude = _pedir(int(porta), "GET", "/saude")
    if codigo != 200 or saude.get("marca") != os.path.basename(dados):
        raise Falha("A porta %s responde por OUTRO projeto. Nada foi feito." % porta)
    try:
        with open(os.path.join(dados, ARQUIVO_TOKEN), encoding="utf-8") as f:
            token = f.read().strip()
    except OSError:
        raise Falha("Não achei o token do serviço na pasta de dados.")
    consulta = {"origem": origem or "", "base_legal": base_legal}
    if base_legal_texto:
        consulta["base_legal_texto"] = base_legal_texto
    codigo, r = _pedir(int(porta), "POST", "/leads/importar?" + urllib.parse.urlencode(consulta), corpo,
                       {"X-Vendas-Token": token, "Content-Type": "text/csv; charset=utf-8",
                        "Content-Length": str(len(corpo))})
    if codigo != 200:
        raise Falha(str(r.get("erro") or "O serviço recusou a importação (%d)." % codigo))
    return r


def resumo(r):
    linhas = ["Importados: %d. Já existiam ou repetidos (mesclados): %d. Recusados: %d." % (
        r["importados"], r["mesclados"], r["recusados"])]
    linhas += ["  linha %d: %s" % (m["linha"], m["motivo"]) for m in r["motivos"]]
    if r.get("motivos_cortados"):
        linhas.append("  (só as primeiras %d recusas aparecem)" % leads.MOTIVOS_MAX)
    return "\n".join(linhas)


def main(argv=None):
    p = argparse.ArgumentParser(description="Importa um CSV de leads (nome, telefone, origem).")
    p.add_argument("arquivo")
    p.add_argument("--projeto", required=True)
    p.add_argument("--origem", help="origem das linhas sem valor na coluna origem (sem ela, essas linhas são recusadas)")
    p.add_argument("--base-legal", required=True, choices=leads.BASES_LEGAIS)
    p.add_argument("--base-legal-texto", help="obrigatório com --base-legal outro")
    p.add_argument("--base", help=argparse.SUPPRESS)  # só testes: outra base da pasta de dados
    a = p.parse_args(argv)
    try:
        print(resumo(enviar(a.projeto, a.arquivo, a.origem, a.base_legal, a.base_legal_texto, a.base)))
    except (Falha, leads.Recusa) as e:
        print("Erro: %s" % e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
