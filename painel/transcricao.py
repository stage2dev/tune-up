"""Lê a conversa de uma sessão do Claude Code (.jsonl) aos pedaços.

O cursor `desde` é a posição em bytes no arquivo: cada chamada lê só o que
entrou depois e devolve `proximo` para a próxima. Só linhas completas são lidas
(a última, ainda sendo escrita, fica para depois). Devolve eventos simples:
fala do usuário, fala do assistente, uso de ferramenta, resultado com erro e
subagente disparado. Blocos de sistema e anexos ficam de fora. Textos são
cortados e o que parece segredo é mascarado. Python 3.9, só biblioteca padrão.
"""
import glob
import json
import os
import re

from mascara import mascarar

RE_SESSAO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
CORTE = 600
CORTE_INTEIRO = 12000  # falas do chat (?inteiro=1)
CORTE_ALVO = 160
LER_POR_VEZ = 4 * 1024 * 1024
LINHA_MAX = 2 * 1024 * 1024
MAX_EVENTOS = 300
FERRAMENTAS_SUBAGENTE = ("Task", "Agent")

RE_LEMBRETE = re.compile(r"<system-reminder>[\s\S]*?(</system-reminder>|$)")
RE_TAG = re.compile(r"<(command-name|command-args|command-message|local-command-stdout|local-command-stderr)>"
                    r"([\s\S]*?)</\1>")
# Mensagem inteira dentro de uma tag (<browser_instruction>...</browser_instruction>): bloco do sistema.
RE_BLOCO_INTEIRO = re.compile(r"^\s*<([A-Za-z_][\w\-]*)(\s[^>]*)?>[\s\S]*</\1>\s*$")


def cortar(texto, n=CORTE):
    texto = mascarar((texto or "")[:n * 6]).strip()
    return texto if len(texto) <= n else texto[:n - 1].rstrip() + "…"


def pasta_do_projeto(cwd):
    """~/.claude/projects/<cwd com tudo que não é letra ou número trocado por '-'>."""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd or "")


def localizar(projects_dir, sessao_id, cwd=None):
    """Caminho do .jsonl da sessão, ou None. Só aceita sessionId no formato UUID."""
    if not isinstance(sessao_id, str) or not RE_SESSAO.match(sessao_id):
        return None
    if cwd:
        cand = os.path.join(projects_dir, pasta_do_projeto(cwd), sessao_id + ".jsonl")
        if os.path.isfile(cand):
            return cand
    achados = glob.glob(os.path.join(projects_dir, "*", sessao_id + ".jsonl"))
    return achados[0] if achados else None


def ultima_atividade(projects_dir, sessao_id, cwd=None, max_arquivos=400):
    """Hora (epoch) da última escrita na conversa ou nos subagentes dela; None se não achar."""
    caminho = localizar(projects_dir, sessao_id, cwd)
    if not caminho:
        return None
    try:
        ultimo = os.path.getmtime(caminho)
    except OSError:
        return None
    vistos = 0
    for raiz, _dirs, nomes in os.walk(caminho[:-len(".jsonl")]):  # <sessionId>/subagents/...
        for nome in nomes:
            vistos += 1
            if vistos > max_arquivos:
                return ultimo
            try:
                ultimo = max(ultimo, os.path.getmtime(os.path.join(raiz, nome)))
            except OSError:
                pass
    return ultimo


def _texto_usuario(conteudo):
    if isinstance(conteudo, list):
        conteudo = "\n".join(b.get("text", "") for b in conteudo
                             if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(conteudo, str):
        return ""
    texto = RE_LEMBRETE.sub("", conteudo)
    tags = dict((m.group(1), m.group(2).strip()) for m in RE_TAG.finditer(texto))
    if "command-name" in tags:  # comando de barra: '/tune-up:part 187 A'
        return (tags["command-name"] + " " + tags.get("command-args", "")).strip()
    if tags or RE_BLOCO_INTEIRO.match(texto):  # saída de comando local ou bloco injetado: sistema, não fala
        return ""
    return texto.strip()


def _alvo(entrada):
    """Resumo curto do que a ferramenta mexe: comando, arquivo, padrão, endereço..."""
    if not isinstance(entrada, dict):
        return ""
    for chave in ("description", "command", "file_path", "notebook_path", "path", "pattern", "url",
                  "query", "skill", "subagent_type", "prompt"):
        v = entrada.get(chave)
        if isinstance(v, str) and v.strip():
            return cortar(re.sub(r"\s+", " ", v), CORTE_ALVO)
    return ""


def _texto_resultado(conteudo):
    if isinstance(conteudo, list):
        conteudo = " ".join(b.get("text", "") for b in conteudo if isinstance(b, dict))
    return conteudo if isinstance(conteudo, str) else ""


def eventos_da_linha(obj, corte_fala=CORTE):
    """Uma linha do .jsonl -> lista de (tipo, texto, extras). `corte_fala` vale só para as falas."""
    if not isinstance(obj, dict) or obj.get("isSidechain") or obj.get("isMeta"):
        return []
    tipo = obj.get("type")
    msg = obj.get("message") if isinstance(obj.get("message"), dict) else {}
    conteudo = msg.get("content")
    out = []
    if tipo == "user":
        if isinstance(conteudo, list):
            for b in conteudo:
                if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("is_error"):
                    out.append(("resultado", cortar(_texto_resultado(b.get("content"))) or "deu erro",
                                {"erro": True}))
        texto = _texto_usuario(conteudo)
        if texto:
            out.append(("usuario", cortar(texto, corte_fala), {}))
    elif tipo == "assistant" and isinstance(conteudo, list):
        for b in conteudo:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "text" and str(b.get("text") or "").strip():
                out.append(("assistente", cortar(b["text"], corte_fala), {}))
            elif b.get("type") == "tool_use":
                nome = str(b.get("name") or "?")[:60]
                entrada = b.get("input") if isinstance(b.get("input"), dict) else {}
                if nome in FERRAMENTAS_SUBAGENTE:
                    quem = str(entrada.get("subagent_type") or "subagente")[:40]
                    desc = _alvo({"description": entrada.get("description")}) or _alvo(entrada)
                    out.append(("subagente", cortar("%s: %s" % (quem, desc) if desc else quem), {"ferramenta": nome}))
                else:
                    out.append(("ferramenta", _alvo(entrada) or nome, {"ferramenta": nome}))
    elif tipo == "system" and (obj.get("level") == "error" or obj.get("subtype") == "api_error"):
        texto = obj.get("content") if isinstance(obj.get("content"), str) else "a API devolveu erro"
        out.append(("sistema", cortar(texto), {"erro": True}))
    return out


def ler(caminho, desde=0, max_eventos=MAX_EVENTOS, corte_fala=CORTE):
    """{eventos, proximo}. Arquivo inexistente -> nada e o mesmo cursor. Linha quebrada é pulada."""
    try:
        desde = max(0, int(desde))
    except (TypeError, ValueError):
        desde = 0
    if not caminho or not os.path.isfile(caminho):
        return {"eventos": [], "proximo": desde}
    try:
        tamanho = os.path.getsize(caminho)
        if desde > tamanho:  # arquivo trocado ou encolheu: recomeça
            desde = 0
        with open(caminho, "rb") as f:
            f.seek(desde)
            bloco = f.read(LER_POR_VEZ)
    except OSError:
        return {"eventos": [], "proximo": desde}
    eventos, pos = [], 0
    while pos < len(bloco) and len(eventos) < max_eventos:
        fim = bloco.find(b"\n", pos)
        if fim < 0:
            if len(bloco) - pos > LINHA_MAX:  # linha gigante sem fim: pula o pedaço lido
                pos = len(bloco)
            break
        linha, inicio, pos = bloco[pos:fim], desde + pos, fim + 1
        if not linha.strip() or len(linha) > LINHA_MAX:
            continue
        try:
            obj = json.loads(linha.decode("utf-8", errors="replace"))
        except ValueError:
            continue
        ts = str(obj.get("timestamp") or "") if isinstance(obj, dict) else ""
        for k, (tipo, texto, extras) in enumerate(eventos_da_linha(obj, corte_fala)):
            ev = {"n": inicio + k, "ts": ts, "tipo": tipo, "texto": texto}
            ev.update(extras)
            eventos.append(ev)
    return {"eventos": eventos, "proximo": desde + pos}
