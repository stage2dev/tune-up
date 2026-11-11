"""Prova REAL do item 9.1: a ação `estudio.anuncio` por `claude --bg` num projeto-exemplo.

Não é teste de unidade (o unittest não descobre esta pasta): gasta 1 sessão de verdade.

  python3 -B painel/tests_reais/prova_anuncio_bg.py --saida <pasta> [--modelo haiku] [--plataforma google]
      [--url https://...] [--briefing "..."]

Mesmo preparo de prova_post_bg.py (projeto descartável sem git em $HOME, marca descoberta e aprovada pelo
módulo real). Dispara pelo Lancador a ação real (só o modelo trocado), acompanha até o fim, imprime estado,
tempo, voltas e tokens e o selo do SERVIDOR (selo.py), copia PNGs, textos.json, a planilha, final.json e
resultado.md para --saida e faz `claude stop` + `claude rm`. Apaga o projeto. Nada é publicado.
"""
import argparse
import glob
import hashlib
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
import modulos  # noqa: E402
import transcricao  # noqa: E402
from estado_exec import mapear_estado  # noqa: E402
from prova_post_bg import STUDIO, preparar  # noqa: E402
from prova_video_bg import uso_e_ferramentas  # noqa: E402

BRIEFING = ("Anuncio da padaria do bairro: pao de fermentacao natural assado de manha cedo, fornadas pequenas; "
            "publico: quem mora perto; acao: reservar o pao de amanha pelo WhatsApp. Sem preco e sem promocao.")
FIM = ("terminou", "parada", "precisa_de_voce", "sumiu")


def principal():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", required=True)
    ap.add_argument("--modelo", default="haiku")
    ap.add_argument("--plataforma", default="google", choices=["google", "meta"])
    ap.add_argument("--url", default="https://exemplo.test/reserva")
    ap.add_argument("--espera", type=int, default=900, help="segundos no máximo")
    ap.add_argument("--briefing", default=BRIEFING)
    arg = ap.parse_args()
    saida = os.path.realpath(arg.saida)
    os.makedirs(saida, exist_ok=True)
    projeto = tempfile.mkdtemp(prefix="prova-anuncio-", dir=os.path.expanduser("~"))
    acoes = tempfile.mkdtemp(prefix="acoes-")
    try:
        preparar(projeto)
        with open(os.path.join(STUDIO, "painel", "acoes", "estudio.json"), encoding="utf-8") as f:
            dados = json.load(f)
        for a in dados["acoes"]:
            a["modelos"] = [arg.modelo] if a["id"] == "estudio.anuncio" else a["modelos"]
        with open(os.path.join(acoes, "estudio.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        cfg = config.carregar(projeto)
        cfg.update(acoes_dir=acoes, acoes_pacote_dir=None, modulos=["estudio"], max_execucoes=1,
                   pular_permissoes=False)
        with open(os.path.join(projeto, ".tune-up", "estudio", "marca", "marca.json"), "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()  # o comando exige o sha256 que a tela mostra
        cod, d = modulos.agir(cfg, "estudio", "marca.aprovar", {"confirmar": True, "sha256": sha[:12]})
        print("marca.aprovar ->", cod, json.dumps(d.get("resultado"), ensure_ascii=False)[:160])
        original = lancador.argv_travas
        lancador.argv_travas = lambda a, c: original(a, c) + ["--plugin-dir", STUDIO]
        lc = lancador.Lancador(cfg, lambda: {})
        cfg["_execucoes"] = lc.execucoes
        t0 = time.time()
        try:
            ex = lc.iniciar("estudio.anuncio", {"briefing": arg.briefing, "plataforma": arg.plataforma, "url": arg.url})
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
        print("exec %s | modelo %s | estado final: %s | %.0f s" % (i, arg.modelo, estado, dur))
        print("transições (s, state, status, estado):", vistos)
        if achado:
            tokens, voltas, res = uso_e_ferramentas(achado)
            print("voltas: %d | tokens: %s | total: %d" % (voltas, tokens, sum(tokens.values())))
            for r in res:
                print("  - %s%s -> %s" % (r[0][:140], " [erro]" if r[1] else "", r[2][:160]))
        else:
            print("transcrição (.jsonl) não encontrada")
        cod, corpo = modulos.montar(cfg, "estudio", usar_cache=False)
        fila = [a for a in (corpo.get("abas") or []) if a["id"] == "fila"]
        print("selo do servidor (fila):", json.dumps(fila[0]["blocos"][0].get("itens") if fila else corpo,
                                                     ensure_ascii=False)[:400])
        for png in sorted(glob.glob(os.path.join(pasta, "a*", "snap", "frame-00-at-0s.png"))):
            a = os.path.basename(os.path.dirname(os.path.dirname(png)))
            shutil.copy2(png, os.path.join(saida, "%s-%s.png" % (arg.modelo, a)))
        for rel in ("resultado.md", "textos.json", "final.json", os.path.join("export", "google-ads-editor.csv"),
                    os.path.join("export", "meta-experimental.csv")):
            if os.path.exists(os.path.join(pasta, rel)):
                shutil.copy2(os.path.join(pasta, rel), os.path.join(saida, "%s-%s" % (arg.modelo, os.path.basename(rel))))
        print("copiado para:", saida, sorted(os.listdir(saida)))
        for sub in ("stop", "rm"):
            cod, out, err = lc.rodar([cfg["claude_bin"], sub, i], cfg["workspace"], 30)
            print("claude %s %s -> %s %s" % (sub, i, cod, (out + err).strip()[:160]))
        return 0 if estado in FIM else 2  # 2 = estourou a espera
    finally:
        shutil.rmtree(projeto, ignore_errors=True)
        shutil.rmtree(acoes, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(principal())
