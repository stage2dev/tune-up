"""Pergunta de múltipla escolha que uma sessão do chat quis fazer (o gancho em travas.py grava em
<dados>/perguntas/<sessao>.json). Saiu de lancador.py (tamanho).
"""
import json
import os
import stat

import mascara
import transcricao
from travas import limpar_perguntas

PERGUNTA_MAX = 64 * 1024
PERGUNTA_VALE = 120  # s: quanto a conversa pode andar depois da pergunta sem ela ficar para trás


def arquivo(cfg, sid):
    return os.path.join(cfg["dados_dir"], "perguntas", sid + ".json")


def ler(cfg, sid, reg=None):
    """Pergunta de múltipla escolha que a sessão quis fazer (gravada pelo gancho em travas.py).

    O arquivo mora numa pasta em que a sessão pode escrever: é lido como dado não confiável
    (só arquivo comum, sem bloquear, até 64 KB, forma conferida, texto mascarado) e qualquer
    problema vira "sem pergunta". Pergunta velha não volta: tem de ser mais nova que o começo
    da vez (início ou última resposta) e a conversa não pode ter seguido muito depois dela.
    """
    try:
        arq = arquivo(cfg, sid)
        fd = os.open(arq, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as f:
            info = os.fstat(f.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > PERGUNTA_MAX:
                return None
            dado = json.loads(f.read(PERGUNTA_MAX + 1).decode("utf-8"))
        comeco = max(float((reg or {}).get("iniciada_ts") or 0), float((reg or {}).get("respondida_ts") or 0))
        if info.st_mtime < comeco - 2:
            return None
        ult = transcricao.ultima_atividade(cfg["projects_dir"], sid, cfg["workspace"])
        if ult is not None and ult > info.st_mtime + PERGUNTA_VALE:
            return None  # a sessão seguiu trabalhando depois de perguntar: a pergunta ficou para trás
        lista = dado.get("perguntas") if isinstance(dado, dict) else None
        perguntas = limpar_perguntas({"questions": [
            {"question": q.get("pergunta"), "header": q.get("cabecalho"), "multiSelect": q.get("multipla"),
             "options": [{"label": o.get("rotulo"), "description": o.get("descricao")}
                         for o in (q.get("opcoes") if isinstance(q.get("opcoes"), list) else [])
                         if isinstance(o, dict)]}
            for q in (lista if isinstance(lista, list) else []) if isinstance(q, dict)]})
        for q in perguntas:  # mesma máscara de tudo que a tela mostra de uma sessão
            q["pergunta"], q["cabecalho"] = mascara.mascarar(q["pergunta"]), mascara.mascarar(q["cabecalho"])
            for o in q["opcoes"]:
                o["rotulo"], o["descricao"] = mascara.mascarar(o["rotulo"]), mascara.mascarar(o["descricao"])
    except Exception:  # arquivo ausente, ruim ou trocado por outra coisa
        return None
    return {"perguntas": perguntas} if perguntas else None
