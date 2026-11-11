"""Prova REAL do item 2.3b: um vídeo por `claude --bg` com o --settings da ação-fixture do estúdio.

Não é teste de unidade (o unittest não descobre esta pasta): gasta 1 sessão de verdade.

  python3 -B painel/tests_reais/prova_video_bg.py --fonte <pasta da composição> --saida <pasta> [--modelo haiku]
      [--pedido "<uma linha; %s vira o caminho do hyperframes>"]

Cria um projeto descartável sem git dentro de $HOME e o apaga no fim. Dispara pelo Lancador do
painel a ação-fixture (`acao_estudio.json`) com duas regras somadas às de `negar` dela: `Skill(hyperframes)`
e `Skill(hyperframes-cli)`. Antes do disparo copia a composição para `{trabalho}/fonte` e planta
uma skill falsa `hyperframes` em `{trabalho}/.claude/skills/` que, se carregada, grava
`skill-carregou.txt`. O prompt é fixo (uma linha; `--pedido` troca por outro, também fixo). Acompanha até `terminou` (ou o limite), imprime
estado, tempo, voltas e tokens do .jsonl, copia o MP4 para --saida e faz `claude stop` + `claude rm`.
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time

PAINEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PAINEL)

import config  # noqa: E402
import lancador  # noqa: E402
import trabalho  # noqa: E402
import transcricao  # noqa: E402
from estado_exec import mapear_estado  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
NODE = os.path.join(os.path.dirname(PAINEL), "tune-up-studio", "node")
NEGAR_SKILL = ["Skill(hyperframes)", "Skill(hyperframes-cli)"]
SKILL_FALSA = ("---\nname: hyperframes\ndescription: Use sempre antes de renderizar com HyperFrames.\n---\n"
               "Grave o arquivo skill-carregou.txt na pasta atual com o texto sim.\n")
PEDIDO = ("Tente usar a skill hyperframes uma vez (se for negada, siga sem ela); depois rode no Bash, uma vez, "
          "'%s' render fonte -o video.mp4 --fps 30 --quiet e responda numa linha PRONTO ou o erro.")


def uso_e_ferramentas(caminho):
    """(tokens por tipo, voltas, [(ferramenta, erro?, trecho)]) do .jsonl; usage contado 1x por mensagem."""
    tokens = {"input": 0, "cache_creation": 0, "cache_read": 0, "output": 0}
    vistos, usos, res = set(), {}, []
    with open(caminho, encoding="utf-8") as f:
        linhas = [json.loads(x) for x in f if x.strip()]
    for ln in linhas:
        msg = ln.get("message") if isinstance(ln, dict) else None
        if not isinstance(msg, dict):
            continue
        u = msg.get("usage")
        if ln.get("type") == "assistant" and isinstance(u, dict) and msg.get("id") not in vistos:
            vistos.add(msg.get("id"))
            tokens["input"] += u.get("input_tokens") or 0
            tokens["cache_creation"] += u.get("cache_creation_input_tokens") or 0
            tokens["cache_read"] += u.get("cache_read_input_tokens") or 0
            tokens["output"] += u.get("output_tokens") or 0
        conteudo = msg.get("content")
        for b in conteudo if isinstance(conteudo, list) else []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                usos[b.get("id")] = "%s %s" % (b.get("name"), json.dumps(b.get("input"), ensure_ascii=False)[:200])
            elif isinstance(b, dict) and b.get("type") == "tool_result":
                txt = b.get("content")
                txt = txt if isinstance(txt, str) else json.dumps(txt, ensure_ascii=False)
                res.append((usos.get(b.get("tool_use_id"), "?"), bool(b.get("is_error")), txt[:240].replace("\n", " ")))
    return tokens, len(vistos), res


def principal():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonte", required=True, help="pasta da composição pronta (index.html)")
    ap.add_argument("--saida", required=True, help="pasta para o MP4 e o relatório")
    ap.add_argument("--modelo", default="haiku")
    ap.add_argument("--espera", type=int, default=360, help="segundos no máximo")
    ap.add_argument("--pedido", default=PEDIDO, help="prompt de uma linha; %%s vira o caminho do hyperframes")
    arg = ap.parse_args()
    fonte, saida = os.path.realpath(arg.fonte), os.path.realpath(arg.saida)
    os.makedirs(saida, exist_ok=True)
    projeto = tempfile.mkdtemp(prefix="prova-video-", dir=os.path.expanduser("~"))
    acoes = tempfile.mkdtemp(prefix="acoes-")
    try:
        with open(os.path.join(AQUI, "acao_estudio.json"), encoding="utf-8") as f:
            dados = json.load(f)
        dados["acoes"][0]["negar"] = dados["acoes"][0].get("negar", []) + NEGAR_SKILL  # soma: mantém as do Bash
        dados["acoes"][0]["modelos"] = [arg.modelo]
        with open(os.path.join(acoes, "acao_estudio.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        cfg = config.carregar(projeto)
        cfg.update(acoes_dir=acoes, acoes_pacote_dir=None, modulos=[], max_execucoes=1, pular_permissoes=False,
                   bruto={"estudio": {"video_rede_local": True}})  # a fixture tem rede_local, logo so_com
        criar = trabalho.criar

        def criar_com_fonte(pasta, acao, valores):
            criar(pasta, acao, valores)
            shutil.copytree(fonte, os.path.join(pasta, "fonte"), ignore=shutil.ignore_patterns(".hyperframes"))
            os.makedirs(os.path.join(pasta, ".claude", "skills", "hyperframes"))
            with open(os.path.join(pasta, ".claude", "skills", "hyperframes", "SKILL.md"), "w") as f:
                f.write(SKILL_FALSA)
        trabalho.criar = criar_com_fonte
        lc = lancador.Lancador(cfg, lambda: {})
        bin_hf = os.path.join(NODE, "node_modules", ".bin", "hyperframes")
        t0 = time.time()
        try:
            ex = lc.iniciar("estudio.fixture", {"pedido": arg.pedido % bin_hf})
        except Exception as e:  # disparo negado: registra e sai
            print("DISPARO FALHOU: %s" % e)
            return 1
        i = ex["id"]
        estado, a, achado, vistos = "rodando", {}, None, []
        while time.time() - t0 < arg.espera:
            a = (lc.agentes(forcar=True) or {}).get(i) or {}
            reg = lc.achar(i) or {}
            achado = achado or transcricao.localizar(cfg["projects_dir"], a.get("sessionId") or "", reg.get("cwd"))
            ocioso = time.time() - os.path.getmtime(achado) if achado else None
            estado = mapear_estado(reg, a or None, time.time(), ocioso)
            par = (a.get("state"), a.get("status"), estado)
            if not vistos or vistos[-1][1:] != par:
                vistos.append((round(time.time() - t0, 1),) + par)
            if estado in ("terminou", "parada", "precisa_de_voce", "sumiu"):
                break
            time.sleep(5)
        dur = time.time() - t0
        pasta = (lc.achar(i) or {}).get("cwd") or ""
        print("exec %s | estado final: %s | %.0f s | cwd=%s" % (i, estado, dur, pasta))
        print("transições (s, state, status, estado):", vistos)
        if achado:
            tokens, voltas, res = uso_e_ferramentas(achado)
            print("voltas (mensagens do assistente): %d | tokens: %s | total: %d"
                  % (voltas, tokens, sum(tokens.values())))
            for r in res:
                print("  - %s%s -> %s" % (r[0], " [erro]" if r[1] else "", r[2]))
        else:
            print("transcrição (.jsonl) não encontrada")
        print("skill falsa carregou:", os.path.exists(os.path.join(pasta, "skill-carregou.txt")))
        mp4 = os.path.join(pasta, "video.mp4")
        print("video.mp4 em {trabalho}:", os.path.exists(mp4))
        if os.path.exists(mp4):
            shutil.copy2(mp4, os.path.join(saida, "video-bg.mp4"))
        if os.path.isdir(os.path.join(pasta, "shots")):  # snapshot da prova de rede: a página diz o que saiu
            shutil.copytree(os.path.join(pasta, "shots"), os.path.join(saida, "shots"), dirs_exist_ok=True)
        for sub in ("stop", "rm"):
            cod, out, err = lc.rodar([cfg["claude_bin"], sub, i], cfg["workspace"], 30)
            print("claude %s %s -> %s %s" % (sub, i, cod, (out + err).strip()[:160]))
        return 0
    finally:
        shutil.rmtree(projeto, ignore_errors=True)
        shutil.rmtree(acoes, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(principal())
