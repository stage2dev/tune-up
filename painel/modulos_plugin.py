"""Módulos de tela que vêm de plugins instalados (opt-in por projeto).

painel.json "modulos_de_plugins": ["plugin@marketplace:modulo"]. A forma completa só existe no
painel.json; rotas, menu e API usam o id curto (o último trecho). O arquivo é
<installPath>/painel/modulos/<id>/modulo.py, com a mesma checagem de caminho real dos módulos do
pacote. Ligar um módulo de plugin roda o código Python do plugin dentro do painel.
Python 3.9, só biblioteca padrão.
"""
import os
import re

import config

RE_NOME = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
RE_ID = re.compile(r"^[a-z0-9_-]{1,40}$")


def ligados(cfg):
    """({id curto: "plugin@marketplace"}, avisos). Entrada ruim, repetida ou com id igual ao de um
    módulo do pacote é recusada com aviso; o resto segue."""
    lista = (cfg.get("bruto") or {}).get("modulos_de_plugins")
    if lista is None or lista == []:
        return {}, []
    if not isinstance(lista, list):
        return {}, ["painel.json: modulos_de_plugins precisa ser uma lista; ignorei"]
    mapa, avisos = {}, []
    for entrada in lista:
        txt = str(entrada)[:80]
        chave, _, mid = entrada.rpartition(":") if isinstance(entrada, str) else ("", "", "")
        plugin, _, mkt = chave.partition("@")
        if not (RE_NOME.match(plugin) and RE_NOME.match(mkt) and RE_ID.match(mid)):
            avisos.append("painel.json: módulo de plugin %r ignorado (use plugin@marketplace:modulo)" % txt)
        elif mid in (cfg.get("modulos") or []):
            avisos.append("módulo de plugin %r recusado: o id %s já é um módulo do projeto" % (txt, mid))
        elif mid in mapa:
            avisos.append("módulo de plugin %r recusado: o id %s já veio de %s" % (txt, mid, mapa[mid]))
        else:
            mapa[mid] = chave
    return mapa, avisos


def caminho(cfg, mid, chave):
    """Caminho real de modulo.py do plugin, ou (None, aviso)."""
    base = config.achar_plugin(chave, cfg.get("home"))
    if not base:
        return None, "plugin %s não está instalado; módulo %s recusado" % (chave, mid)
    pasta = os.path.join(os.path.realpath(base), "painel", "modulos", mid)
    real = os.path.realpath(os.path.join(pasta, "modulo.py"))
    if not real.startswith(os.path.realpath(pasta).rstrip(os.sep) + os.sep) \
            or os.path.realpath(pasta) != pasta or not os.path.isfile(real):
        return None, ("plugin %s: painel/modulos/%s/modulo.py não encontrado (ou é atalho para fora "
                      "da pasta do módulo)" % (chave, mid))
    return real, None
