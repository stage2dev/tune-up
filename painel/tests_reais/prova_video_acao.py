"""Prova REAL do item 6.1: as ações `estudio.video` (reserva) e `estudio.video-motion` por `claude --bg`.

Não é teste de unidade (o unittest não descobre esta pasta): gasta 1 sessão de verdade.

  python3 -B painel/tests_reais/prova_video_acao.py --saida <pasta> [--acao estudio.video] [--duracao 10]
      [--modelo haiku] [--rede-local] [--briefing "..."]

Igual a `prova_post_bg.py` (projeto descartável sem git em $HOME com o exemplo forno-miudo, marca
descoberta e aprovada pelo comando de módulo, ação real com `--plugin-dir`), com a chave do projeto:
`--rede-local` grava `{"estudio": {"video_rede_local": true}}` no painel.json do projeto. Imprime as
ações de vídeo que o catálogo do projeto mostra (a `-motion` só aparece com a chave), estado, tempo,
voltas e tokens; copia MP4, folha de quadros, contact sheet, qa.json, roteiro e resultado para
--saida; faz `claude stop` + `claude rm` e apaga o projeto. Sai com 2 se a espera acabou.
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

import catalogo  # noqa: E402
import config  # noqa: E402
import lancador  # noqa: E402
import modulos  # noqa: E402
import transcricao  # noqa: E402
from estado_exec import mapear_estado  # noqa: E402
from prova_post_bg import STUDIO, preparar  # noqa: E402
from prova_video_bg import uso_e_ferramentas  # noqa: E402

FIM = ("terminou", "parada", "precisa_de_voce", "sumiu")
BRIEFING = ("Video da padaria para o Reels: pao de fermentacao natural, massa descansa de vespera, "
            "fornadas pequenas saindo as 6h; publico do bairro; acao: reservar o pao de amanha pelo WhatsApp.")
COPIAR = ("video.mp4", "folha.png", "qa.json", "roteiro.md", "resultado.md", "snap/contact-sheet.jpg")


def principal():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", required=True)
    ap.add_argument("--acao", default="estudio.video", choices=("estudio.video", "estudio.video-motion"))
    ap.add_argument("--duracao", default="10", choices=("10", "15"))
    ap.add_argument("--modelo", default="haiku")
    ap.add_argument("--rede-local", action="store_true", help="liga estudio.video_rede_local no painel.json")
    ap.add_argument("--espera", type=int, default=900, help="segundos no máximo")
    ap.add_argument("--briefing", default=BRIEFING)
    arg = ap.parse_args()
    saida = os.path.realpath(arg.saida)
    os.makedirs(saida, exist_ok=True)
    projeto = tempfile.mkdtemp(prefix="prova-video-", dir=os.path.expanduser("~"))
    acoes = tempfile.mkdtemp(prefix="acoes-")
    try:
        preparar(projeto)
        if arg.rede_local:
            with open(os.path.join(projeto, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
                json.dump({"estudio": {"video_rede_local": True}}, f)
        with open(os.path.join(STUDIO, "painel", "acoes", "estudio.json"), encoding="utf-8") as f:
            dados = json.load(f)
        for a in dados["acoes"]:
            a["modelos"] = [arg.modelo]
        with open(os.path.join(acoes, "estudio.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        cfg = config.carregar(projeto)
        cfg.update(acoes_dir=acoes, acoes_pacote_dir=None, modulos=["estudio"], max_execucoes=1,
                   pular_permissoes=False)
        print("ações do catálogo do projeto:", [a["id"] for a in catalogo.catalogo_do_projeto(cfg)[0]])
        cod, d = modulos.agir(cfg, "estudio", "marca.aprovar", {"confirmar": True})
        print("marca.aprovar ->", cod, json.dumps(d.get("resultado"), ensure_ascii=False)[:160])
        original = lancador.argv_travas
        lancador.argv_travas = lambda a, c: original(a, c) + ["--plugin-dir", STUDIO]
        lc = lancador.Lancador(cfg, lambda: {})
        t0 = time.time()
        try:
            ex = lc.iniciar(arg.acao, {"briefing": arg.briefing, "duracao": arg.duracao})
        except Exception as e:  # disparo negado: registra e sai
            print("DISPARO FALHOU: %s" % getattr(e, "mensagem", e))
            return 1
        i = ex["id"]
        estado, achado, vistos = "rodando", None, []
        while time.time() - t0 < arg.espera:
            a = (lc.agentes(forcar=True) or {}).get(i) or {}
            reg = lc.achar(i) or {}
            achado = achado or transcricao.localizar(cfg["projects_dir"], a.get("sessionId") or "", reg.get("cwd"))
            ocioso = time.time() - os.path.getmtime(achado) if achado else None
            estado = mapear_estado(reg, a or None, time.time(), ocioso)
            par = (a.get("state"), a.get("status"), estado)
            if not vistos or vistos[-1][1:] != par:
                vistos.append((round(time.time() - t0, 1),) + par)
            if estado in FIM:
                break
            time.sleep(5)
        dur = time.time() - t0
        pasta = (lc.achar(i) or {}).get("cwd") or ""
        print("exec %s | %s | modelo %s | estado final: %s | %.0f s" % (i, arg.acao, arg.modelo, estado, dur))
        print("transições (s, state, status, estado):", vistos)
        if achado:
            tokens, voltas, res = uso_e_ferramentas(achado)
            print("voltas: %d | tokens: %s | total: %d" % (voltas, tokens, sum(tokens.values())))
            for r in res:
                print("  - %s%s -> %s" % (r[0][:140], " [erro]" if r[1] else "", r[2][:160]))
        else:
            print("transcrição (.jsonl) não encontrada")
        prefixo = "%s-%ss-%s-" % (arg.acao.replace("estudio.", ""), arg.duracao, arg.modelo)
        for nome in COPIAR:
            if os.path.exists(os.path.join(pasta, nome)):
                shutil.copy2(os.path.join(pasta, nome), os.path.join(saida, prefixo + nome.replace("/", "-")))
        try:
            with open(os.path.join(pasta, "qa.json"), encoding="utf-8") as f:
                print("linha do qa:", json.load(f).get("linha"))
        except (OSError, ValueError) as e:
            print("qa.json ilegível ou ausente:", e)
        print("copiado para:", saida)
        for sub in ("stop", "rm"):
            cod, out, err = lc.rodar([cfg["claude_bin"], sub, i], cfg["workspace"], 30)
            print("claude %s %s -> %s %s" % (sub, i, cod, (out + err).strip()[:160]))
        return 0 if estado in FIM else 2  # 2 = estourou a espera
    finally:
        shutil.rmtree(projeto, ignore_errors=True)
        shutil.rmtree(acoes, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(principal())
