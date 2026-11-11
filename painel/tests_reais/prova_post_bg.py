"""Prova REAL do item 5.1: a ação `estudio.post` por `claude --bg` num projeto-exemplo.

Não é teste de unidade (o unittest não descobre esta pasta): gasta 1 sessão de verdade.

  python3 -B painel/tests_reais/prova_post_bg.py --saida <pasta> [--modelo haiku] [--formato "post 4:5"] [--quadros 1]

Cria um projeto descartável sem git dentro de $HOME com o exemplo forno-miudo (sem as peças prontas),
descobre a marca (descobrir_marca.py) e a aprova pelo comando de módulo `marca.aprovar` (módulo
estudio real, por um módulo-ponte no pacote do projeto). Dispara pelo Lancador a ação real
(`tune-up-studio/painel/acoes/estudio.json`, só o modelo trocado) com `--plugin-dir` do tune-up-studio
(o plugin não está instalado aqui). Acompanha até o fim, imprime estado, tempo, voltas e tokens,
copia PNG, qa.json e resultado.md para --saida e faz `claude stop` + `claude rm`. Apaga o projeto.
"""
import argparse
import glob
import json
import os
import shutil
import subprocess
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
from prova_video_bg import uso_e_ferramentas  # noqa: E402

STUDIO = os.path.join(os.path.dirname(PAINEL), "tune-up-studio")
EXEMPLO = os.path.join(STUDIO, "exemplos", "forno-miudo")
PONTE = ("import importlib.util\n_s = importlib.util.spec_from_file_location('estudio_real', %r)\n"
         "_m = importlib.util.module_from_spec(_s)\n_s.loader.exec_module(_m)\n"
         "INFO = _m.INFO\nmontar = _m.montar\nagir = _m.agir\n"
         % os.path.join(STUDIO, "painel", "modulos", "estudio", "modulo.py"))
BRIEFING = ("Post da padaria para o feed: pao de fermentacao natural assado de manha cedo, fornadas pequenas; "
            "publico do bairro; acao: reservar o pao de amanha pelo WhatsApp.")


def preparar(projeto):
    shutil.copytree(EXEMPLO, projeto, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("post-4x5", "video-9x16", "reserva-9x16", ".hyperframes"))
    r = subprocess.run([sys.executable, "-I", os.path.join(STUDIO, "scripts", "descobrir_marca.py"),
                        "--projeto", projeto], capture_output=True, text=True, timeout=60)
    print("descobrir_marca ->", r.returncode, (r.stdout + r.stderr).strip()[:200])
    pasta = os.path.join(projeto, ".tune-up", "painel-projeto", "modulos", "estudio")
    os.makedirs(pasta)
    with open(os.path.join(pasta, "modulo.py"), "w", encoding="utf-8") as f:
        f.write(PONTE)


def principal():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", required=True)
    ap.add_argument("--modelo", default="haiku")
    ap.add_argument("--formato", default="post 4:5")
    ap.add_argument("--quadros", default="1")
    ap.add_argument("--espera", type=int, default=900, help="segundos no máximo")
    arg = ap.parse_args()
    saida = os.path.realpath(arg.saida)
    os.makedirs(saida, exist_ok=True)
    projeto = tempfile.mkdtemp(prefix="prova-post-", dir=os.path.expanduser("~"))
    acoes = tempfile.mkdtemp(prefix="acoes-")
    try:
        preparar(projeto)
        with open(os.path.join(STUDIO, "painel", "acoes", "estudio.json"), encoding="utf-8") as f:
            dados = json.load(f)
        dados["acoes"][0]["modelos"] = [arg.modelo]
        with open(os.path.join(acoes, "estudio.json"), "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False)
        cfg = config.carregar(projeto)
        cfg.update(acoes_dir=acoes, acoes_pacote_dir=None, modulos=["estudio"], max_execucoes=1,
                   pular_permissoes=False)
        print("pacote_ok:", cfg.get("pacote_ok"))
        cod, d = modulos.agir(cfg, "estudio", "marca.aprovar", {"confirmar": True})
        print("marca.aprovar ->", cod, json.dumps(d.get("resultado"), ensure_ascii=False)[:160])
        original = lancador.argv_travas
        lancador.argv_travas = lambda a, c: original(a, c) + ["--plugin-dir", STUDIO]
        lc = lancador.Lancador(cfg, lambda: {})
        t0 = time.time()
        try:
            ex = lc.iniciar("estudio.post", {"briefing": BRIEFING, "formato": arg.formato, "quadros": arg.quadros})
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
            if estado in ("terminou", "parada", "precisa_de_voce", "sumiu"):
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
        for png in sorted(glob.glob(os.path.join(pasta, "q*", "snap", "frame-00-at-0s.png"))):
            q = os.path.basename(os.path.dirname(os.path.dirname(png)))
            shutil.copy2(png, os.path.join(saida, "%s-%s.png" % (arg.modelo, q)))
            qa = os.path.join(pasta, q, "qa.json")
            if os.path.exists(qa):
                shutil.copy2(qa, os.path.join(saida, "%s-%s-qa.json" % (arg.modelo, q)))
        for nome in ("resultado.md", "copy.md"):
            if os.path.exists(os.path.join(pasta, nome)):
                shutil.copy2(os.path.join(pasta, nome), os.path.join(saida, "%s-%s" % (arg.modelo, nome)))
        print("copiado para:", saida, sorted(os.listdir(saida)))
        for sub in ("stop", "rm"):
            cod, out, err = lc.rodar([cfg["claude_bin"], sub, i], cfg["workspace"], 30)
            print("claude %s %s -> %s %s" % (sub, i, cod, (out + err).strip()[:160]))
        return 0
    finally:
        shutil.rmtree(projeto, ignore_errors=True)
        shutil.rmtree(acoes, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(principal())
