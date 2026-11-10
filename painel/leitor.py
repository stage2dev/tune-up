"""Leitor do painel tune-up: monta o estado das fases, PRs e sessões.

Módulo puro: não abre servidor, não escreve em disco. Só lê arquivos e roda
comandos de leitura (`guarda.py info`, `gh pr list`, `claude agents`) com lista
de argumentos e timeout. Tudo que não achar vira None e entra em `avisos`.
Python 3.9, só biblioteca padrão.
"""
import datetime
import json
import os
import re
import subprocess
import threading
import time

import config  # noqa: E402  caminhos vêm de <raiz>/.tune-up/painel.json ou dos padrões
import mascara  # noqa: E402
from leitor_md import (  # noqa: E402,F401  parte pura (texto dos planos), reexportada aqui
    NOMES_PADRAO, analisar_progress, contar_depois, parte_da_branch, parte_da_sessao, parte_do_item,
    parte_do_titulo_pr, partes_de_titulos, partes_do_goal, titulo_goal)

_CFG = []


def cfg_atual():
    """Config carregada uma vez (o painel passa a sua em montar_estado)."""
    if not _CFG:
        _CFG.append(config.carregar())
    return _CFG[0]


def names_json(cfg):
    """templates/names.json do plugin, ao lado do guarda.py."""
    guarda = cfg.get("guarda")
    return os.path.join(os.path.dirname(os.path.dirname(guarda)), "templates", "names.json") if guarda else None


# Nome de arquivo vindo do perfil (goal/progress/later): só nome simples, nunca caminho.
RE_NOME_SIMPLES = re.compile(r"^[A-Za-z0-9À-ÿ][A-Za-z0-9À-ÿ ._-]{0,79}$")
CHAVES_ARQUIVO = ("goal", "progress", "later")


LIMITE_ARQUIVO = 2 * 1024 * 1024
TTL_PRS = 60
TTL_SESSOES = 10
TTL_INFO = 300
FIM_SESSAO = {"done", "completed", "failed", "error", "stopped", "killed", "exited", "finished"}
RODANDO_SESSAO = {"running", "busy", "working", "active"}


# ---------------------------------------------------------------- utilidades

class Cache:
    """Cache em memória com validade por chave. Seguro entre threads."""

    def __init__(self, relogio=time.monotonic):
        self._dados = {}
        self._lock = threading.Lock()
        self._relogio = relogio

    def pegar(self, chave, ttl, funcao):
        agora = self._relogio()
        with self._lock:
            item = self._dados.get(chave)
            if item and agora - item[0] < ttl:
                return item[1]
        valor = funcao()
        with self._lock:
            self._dados[chave] = (self._relogio(), valor)
        return valor

    def esquecer(self, chave):
        with self._lock:
            self._dados.pop(chave, None)


def rodar(cmd, cwd, timeout):
    """Roda `cmd` (lista, sem shell). Devolve (ok, stdout, motivo)."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, shell=False)
    except FileNotFoundError:
        return False, "", "comando não encontrado: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return False, "", "passou de %s s" % timeout
    except OSError as e:
        return False, "", "erro ao rodar: %s" % e
    if r.returncode != 0:
        erro = (r.stderr or r.stdout or "").strip().splitlines()
        return False, r.stdout, "saiu com código %s%s" % (r.returncode, (": " + erro[-1][:160]) if erro else "")
    return True, r.stdout, None


def dentro_de(caminho, raiz):
    """O caminho real (seguindo atalhos) fica dentro da raiz real?"""
    real, base = os.path.realpath(caminho), os.path.realpath(raiz)
    return real == base or real.startswith(base.rstrip(os.sep) + os.sep)


def ler_texto(caminho, avisos=None, raiz=None):
    if not os.path.isfile(caminho):
        return None
    if raiz and not dentro_de(caminho, raiz):
        if avisos is not None:
            avisos.append("ignorei %s: é um atalho para fora de %s" % (os.path.basename(caminho), raiz))
        return None
    try:
        with open(caminho, "rb") as f:
            dados = f.read(LIMITE_ARQUIVO + 1)
    except OSError as e:
        if avisos is not None:
            avisos.append("não consegui ler %s: %s" % (caminho, e))
        return None
    if len(dados) > LIMITE_ARQUIVO and avisos is not None:
        avisos.append("%s passou de 2 MB; li só o começo" % caminho)
    return dados[:LIMITE_ARQUIVO].decode("utf-8", errors="replace")



# ---------------------------------------------------------------- fontes externas

def ler_info(cwd=None, timeout=8, guarda=None):
    cfg = cfg_atual()
    guarda = guarda or cfg.get("guarda")
    if not guarda:
        return None, "plugin tune-up não encontrado: nomes de marcador padrão"
    ok, out, motivo = rodar(["python3", guarda, "info"], cwd or cfg["workspace"], timeout)
    if not ok:
        return None, "guarda.py info falhou (%s)" % motivo
    try:
        dado = json.loads(out)
    except ValueError:
        return None, "guarda.py info não devolveu JSON"
    return (dado, None) if isinstance(dado, dict) else (None, "guarda.py info devolveu formato inesperado")


def _so_nomes_simples(nomes, avisos):
    """goal/progress/later viram nome de arquivo: caminho, '..' ou atalho volta ao padrão."""
    for k in CHAVES_ARQUIVO:
        v = nomes.get(k)
        if not isinstance(v, str) or not RE_NOME_SIMPLES.match(v) or ".." in v:
            avisos.append("nome de arquivo '%s' do perfil recusado (não é nome simples); usei %s"
                          % (str(v)[:40], NOMES_PADRAO[k]))
            nomes[k] = NOMES_PADRAO[k]
    return nomes


def nomes_de(info, avisos, cfg=None):
    nomes = dict(NOMES_PADRAO)
    if info and isinstance(info.get("names"), dict):
        nomes.update({k: v for k, v in info["names"].items() if isinstance(v, str)})
        return _so_nomes_simples(nomes, avisos)
    caminho = names_json(cfg or cfg_atual())
    texto = ler_texto(caminho) if caminho else None
    try:
        todos = json.loads(texto) if texto else {}
        nomes.update(todos.get("en") or {})
        nomes.update(todos.get("pt-BR") or {})
        if texto:
            avisos.append("nomes lidos direto do names.json (pt-BR)")
    except (ValueError, AttributeError):
        avisos.append("names.json ilegível; usei os nomes padrão")
    return _so_nomes_simples(nomes, avisos)


def resolver_plans(info, plans_cli, avisos, cfg=None):
    cfg = cfg or cfg_atual()
    if plans_cli:
        return os.path.realpath(plans_cli), "--plans-dir"
    if cfg.get("plans_origem") == "painel.json":
        return cfg["plans_dir"], "painel.json"
    if info and isinstance(info.get("plans_dir"), str):
        cand = info["plans_dir"]
        if os.path.isdir(os.path.join(cand, "phases")):
            return cand, "guarda.py info"
        avisos.append("guarda.py info apontou %s, que não tem phases/; usei o padrão" % cand)
    return cfg["plans_dir"], "padrão"


def ler_prs(repo):
    if not repo or not os.path.isdir(repo):
        return [], "PRs: repositório não encontrado (%s)" % repo
    ok, out, motivo = rodar(["gh", "pr", "list", "--state", "all", "--limit", "40", "--json",
                             "number,title,state,headRefName,url,updatedAt"], repo, 8)
    if not ok:
        return [], "PRs não lidas: gh pr list %s" % motivo
    try:
        lista = json.loads(out)
    except ValueError:
        return [], "PRs não lidas: gh devolveu algo que não é JSON"
    prs = []
    for p in lista if isinstance(lista, list) else []:
        if isinstance(p, dict) and isinstance(p.get("number"), int):
            url = str(p.get("url") or "")
            prs.append({"numero": p["number"], "titulo": str(p.get("title") or ""),
                        "estado": str(p.get("state") or "").upper(), "branch": str(p.get("headRefName") or ""),
                        "url": url if url.startswith("https://") else "", "atualizada": str(p.get("updatedAt") or "")})
    return prs, None


def ler_sessoes(cwd=None, claude_bin=None):
    cfg = cfg_atual()
    ok, out, motivo = rodar([claude_bin or cfg["claude_bin"], "agents", "--json", "--all"],
                            cwd or cfg["workspace"], 5)
    if not ok:
        return [], "sessões não lidas: claude agents %s" % motivo
    try:
        lista = json.loads(out)
    except ValueError:
        return [], "sessões não lidas: claude agents não devolveu JSON"
    out_l = []
    for s in lista if isinstance(lista, list) else []:
        if not isinstance(s, dict):
            continue
        estado = str(s.get("state") or s.get("status") or "").lower()
        inicio = s.get("startedAt")
        try:
            inicio_iso = datetime.datetime.fromtimestamp(inicio / 1000).isoformat(timespec="minutes") if inicio else None
        except (TypeError, ValueError, OverflowError, OSError):
            inicio_iso = None
        out_l.append({"id": str(s.get("id") or s.get("sessionId") or ""),
                      "sessao_id": str(s.get("sessionId") or ""),
                      "nome": mascara.mascarar(str(s.get("name") or "")),
                      "tipo": str(s.get("kind") or ""), "estado": estado, "cwd": str(s.get("cwd") or ""),
                      "inicio": inicio_iso, "ativa": estado not in FIM_SESSAO,
                      "rodando": estado in RODANDO_SESSAO})
    return out_l, None



# ---------------------------------------------------------------- montagem

def _status_da_parte(pid, fech, precisa, sess, abertas, nomes):
    if fech:
        return "fechada", "%s linha %s: %s" % (nomes["progress"], fech["linha"], fech["trecho"])
    if precisa:
        return "precisa_de_voce", "%s linha %s: marcador '%s'" % (nomes["progress"], precisa[-1]["linha"],
                                                                 nomes["need_you"])
    if sess:
        return "rodando", "sessão ativa '%s' (%s)" % (sess[0]["nome"], sess[0]["estado"])
    if abertas:
        return "rodando", "PR #%s aberta na branch %s" % (abertas[0]["numero"], abertas[0]["branch"])
    return "pendente", "sem marcador de fechada, sem sessão ativa e sem PR aberta da Parte"


def _pr_da_parte(minhas_prs, citadas, prs):
    if minhas_prs:
        return minhas_prs[0]
    if not citadas:
        return None
    num = citadas[-1]
    achada = [x for x in prs if x["numero"] == num]
    return achada[0] if achada else {"numero": num, "titulo": "", "estado": "?", "branch": "", "url": "",
                                     "atualizada": ""}


def _lista_de_partes(goal, progress, nomes):
    for texto, fonte in ((goal, nomes["goal"] + " (tabela)"), (progress, nomes["progress"] + " (tabela)")):
        partes = partes_do_goal(texto)
        if partes:
            return partes, fonte
    partes = partes_de_titulos(goal)
    return (partes, nomes["goal"] + " (títulos)") if partes else ([], None)


def ler_fase(pasta, nomes, prs, sessoes, avisos, raiz=None):
    base = os.path.basename(pasta)
    m = re.match(r"^(\d+)-?(.*)$", base)
    numero, slug = m.group(1), m.group(2)
    raiz = raiz or os.path.dirname(os.path.dirname(os.path.abspath(pasta)))  # <plans>/phases/NNN
    goal = ler_texto(os.path.join(pasta, nomes["goal"]), avisos, raiz)
    progress = ler_texto(os.path.join(pasta, nomes["progress"]), avisos, raiz)
    depois = ler_texto(os.path.join(pasta, nomes["later"]), avisos, raiz)
    fase = {"numero": numero, "slug": slug, "pasta": base, "titulo": titulo_goal(goal),
            "arquivos": {"goal": goal is not None, "progress": progress is not None, "depois": depois is not None},
            "acompanhada": progress is not None, "partes": [], "partes_fonte": None,
            "depois_abertos": None, "depois_formato": None, "perguntas_abertas": [], "precisa": [],
            "completa": False}
    fase["depois_abertos"], fase["depois_formato"] = contar_depois(depois)
    if progress is None:
        return fase

    partes, fonte = _lista_de_partes(goal, progress, nomes)
    ids = [p["id"] for p in partes]
    analise = analisar_progress(progress, ids, nomes)
    if not partes and analise["fechadas"]:
        partes = [{"id": pid, "itens_plano": None, "prerequisito": None, "comando_plano": None}
                  for pid in analise["fechadas"]]
        fonte = nomes["progress"] + " (marcadores)"
    if not partes:
        avisos.append("fase %s: não achei a lista de Partes (sem tabela 'Parte', títulos ou marcadores)" % numero)
    fase["partes_fonte"] = fonte
    if analise["ids_vistos"]:
        avisos.append("fase %s: marcador de Parte fechada para id fora da lista: %s"
                      % (numero, ", ".join(analise["ids_vistos"][:6])))
    if fase["depois_formato"] == "sem_caixas":
        avisos.append("fase %s: %s sem caixas '- [ ]'; abertos = null" % (numero, nomes["later"]))

    ids = [p["id"] for p in partes]
    prs_fase = [(parte_da_branch(pr["branch"], numero, ids) or parte_do_titulo_pr(pr["titulo"], numero, ids), pr)
                for pr in prs]
    sess_fase = [(parte_da_sessao(s["nome"], numero, ids), s) for s in sessoes if s["ativa"]]

    for p in partes:
        pid = p["id"]
        fech = analise["fechadas"].get(pid)
        precisa = [x for x in analise["precisa"] if x["parte"] == pid]
        sess = [s for (q, s) in sess_fase if q == pid]
        minhas_prs = sorted([pr for (q, pr) in prs_fase if q == pid],
                            key=lambda x: (x["estado"] == "OPEN", x["atualizada"]), reverse=True)
        abertas = [pr for pr in minhas_prs if pr["estado"] == "OPEN"]
        status, origem = _status_da_parte(pid, fech, precisa, sess, abertas, nomes)
        itens = []
        for it in analise["itens"].values():
            if it["parte"] == pid:
                voltas = [it["voltas"][k] for k in sorted(it["voltas"])]
                itens.append({"id": it["id"], "voltas": voltas,
                              "teve_achado": any(v["critico"] or v["alto"] for v in voltas)})
        p.update({"status": status, "origem": origem, "parcial": bool(fech and fech.get("parcial")),
                  "pr": _pr_da_parte(minhas_prs, analise["prs_citadas"].get(pid), prs), "itens": itens,
                  "comando_copiar": 'claude --bg "/tune-up:part %s %s"' % (numero, pid)})
        fase["partes"].append(p)

    comecou = any(p["status"] != "pendente" for p in fase["partes"])  # só plano: ALTO é da revisão do plano
    if comecou and analise["tem_alto_no_texto"] and not any(i["teve_achado"] for p in fase["partes"] for i in p["itens"]):
        avisos.append("fase %s: %s cita CRÍTICO/ALTO, mas nenhum item saiu com achado (formato não reconhecido?)"
                      % (numero, nomes["progress"]))
    fechadas = set(x["id"] for x in fase["partes"] if x["status"] == "fechada")
    fase["completa"] = bool(fase["partes"]) and len(fechadas) == len(fase["partes"])
    if not fase["completa"]:
        fase["perguntas_abertas"] = analise["perguntas"]
        fase["precisa"] = [x for x in analise["precisa"] if x["parte"] not in fechadas]
    return fase


def listar_fases(plans_dir, avisos):
    raiz = os.path.join(plans_dir, "phases")
    try:
        nomes_pastas = os.listdir(raiz)
    except OSError as e:
        avisos.append("não consegui listar %s: %s" % (raiz, e))
        return []
    pastas = [os.path.join(raiz, n) for n in nomes_pastas
              if re.match(r"^\d+", n) and os.path.isdir(os.path.join(raiz, n))]
    fora = [p for p in pastas if not dentro_de(p, plans_dir)]
    if fora:
        avisos.append("ignorei %d pasta(s) de fase que são atalho para fora de %s" % (len(fora), plans_dir))
        pastas = [p for p in pastas if p not in fora]
    return sorted(pastas, key=lambda p: (int(re.match(r"^(\d+)", os.path.basename(p)).group(1)),
                                         os.path.basename(p)), reverse=True)


def _pendencias(abertas, nomes):
    out = []
    for f in abertas:
        for x in f["precisa"]:
            out.append({"fase": f["numero"], "parte": x["parte"], "tipo": "marcador", "texto": x["texto"],
                        "origem": "%s/%s linha %s" % (f["pasta"], nomes["progress"], x["linha"])})
        for q in f["perguntas_abertas"]:
            out.append({"fase": f["numero"], "parte": None, "tipo": "pergunta", "texto": q["texto"],
                        "origem": "%s/%s linha %s" % (f["pasta"], nomes["progress"], q["linha"])})
    return out


def montar_estado(plans_cli=None, cache=None, rodar_externos=True, cfg=None):
    """Estado completo para /api/estado. Nunca levanta exceção por causa dos dados."""
    cfg = cfg or cfg_atual()
    workspace = cfg["workspace"]
    cache = cache or Cache()
    avisos = []
    if rodar_externos:
        info, erro_info = cache.pegar("info", TTL_INFO, lambda: ler_info(workspace, guarda=cfg.get("guarda")))
        if erro_info:
            avisos.append(erro_info)
    else:
        info = None
    nomes = nomes_de(info, avisos, cfg)
    plans_dir, plans_origem = resolver_plans(info, plans_cli, avisos, cfg)
    pai = os.path.dirname(plans_dir)
    repo = pai if os.path.exists(os.path.join(pai, ".git")) else None
    if repo is None and not plans_cli and cfg.get("repo"):
        repo = cfg["repo"]
    if rodar_externos:
        prs, erro_prs = cache.pegar("prs:%s" % repo, TTL_PRS, lambda: ler_prs(repo))
        sessoes, erro_ses = cache.pegar("sessoes", TTL_SESSOES,
                                        lambda: ler_sessoes(workspace, cfg.get("claude_bin")))
        avisos.extend(e for e in (erro_prs, erro_ses) if e)
    else:
        prs, sessoes = [], []
    sessoes_proj = [{k: v for k, v in s.items() if k != "cwd"} for s in sessoes
                    if s["cwd"] == workspace or s["cwd"].startswith(workspace + os.sep)]

    fases = []
    for pasta in listar_fases(plans_dir, avisos):
        try:
            fases.append(ler_fase(pasta, nomes, prs, sessoes_proj, avisos, plans_dir))
        except Exception as e:  # o leitor nunca quebra por causa de uma fase
            avisos.append("fase %s: erro ao ler (%s: %s)" % (os.path.basename(pasta), type(e).__name__, e))
    sem_progress = [f["numero"] for f in fases if not f["acompanhada"]]
    if sem_progress:
        avisos.append("%d fases sem %s (formato antigo ou não começadas): fora da contagem"
                      % (len(sem_progress), nomes["progress"]))

    acomp = [f for f in fases if f["acompanhada"]]
    abertas = [f for f in acomp if f["partes"] and not f["completa"]]
    precisa = _pendencias(abertas, nomes)
    partes = [p for f in acomp for p in f["partes"]]
    return {
        "gerado_em": datetime.datetime.now().isoformat(timespec="seconds"),
        "plans_dir": plans_dir,
        "plans_origem": plans_origem,
        "repo": repo,
        "nomes": {k: nomes.get(k) for k in ("goal", "progress", "later", "need_you", "part_closed")},
        "resumo": {
            "fases_total": len(fases),
            "fases_acompanhadas": len(acomp),
            "fases_abertas": len(abertas),
            "partes_fechadas": sum(1 for p in partes if p["status"] == "fechada"),
            "partes_total": len(partes),
            "pendencias_dono": len(precisa),
            "prs_abertas": sum(1 for p in prs if p["estado"] == "OPEN"),
            "sessoes_rodando": sum(1 for s in sessoes_proj if s["rodando"]),
            "sessoes_ativas": sum(1 for s in sessoes_proj if s["ativa"]),
        },
        "precisa_de_voce": precisa,
        "fases": fases,
        "prs": prs,
        "sessoes": [s for s in sessoes_proj if s["ativa"]],
        "avisos": avisos,
    }
