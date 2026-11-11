"""Prova REAL do item 8.1b (C11): o fluxo da tela do estúdio pelo HTTP, como o navegador faria.

Não é teste de unidade (o unittest não descobre esta pasta): gasta 1 sessão de verdade (a ação
`estudio.post` com o modelo do catálogo), a menos que --sem-sessao.

  python3 -B painel/tests_reais/prova_estudio_tela.py --saida <pasta> [--mp4 <video.mp4>] [--sem-sessao]
      [--espera 900] [--segurar <arquivo>]

Cria um projeto descartável sem git em $HOME com o exemplo forno-miudo (sem as peças prontas) e um
.tune-up/painel.json com "modulos_de_plugins" e "acoes_de_plugins" do tune-up-studio. O plugin não
está instalado aqui: o painel sobe num processo filho (--servir) em que o registro de plugins
devolve a pasta tune-up-studio deste repo e a sessão ganha `--plugin-dir` dela (o mesmo artifício
de prova_post_bg.py). Porta livre em 127.0.0.1, nunca a 8787.

Depois, só HTTP com Sec-Fetch-Site same-origin, Origin e o token de /api/sessao:
marca.redescobrir -> marca.aprovar (com o sha curto que a aba Marca mostra) -> POST /api/execucoes
estudio.post -> espera um estado final -> galeria pela rota de mídia -> peca.aprovar (2ª vez = 409)
-> confere <dados>/aprovados/<id>/manifesto.json contra o sha256 dos arquivos. Com --mp4, copia o
vídeo para um trabalho de teste e pede a rota com e sem Range. Com --segurar, espera esse arquivo
existir antes de limpar (para tirar capturas da tela com o painel no ar). No fim: parar pela rota,
`claude rm`, derruba o painel e apaga o projeto. Sai com 1 se algum passo falhou.
"""
import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

PAINEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PAINEL)

import config  # noqa: E402
from prova_post_bg import BRIEFING, EXEMPLO, STUDIO  # noqa: E402

CHAVE = "tune-up-studio@tune-up"
FIM = ("terminou", "parada", "precisa_de_voce", "sumiu", "falhou", "parou")
FALHAS = []


def checar(ok, texto):
    print(("OK   " if ok else "FALHA ") + texto, flush=True)
    if not ok:
        FALHAS.append(texto)
    return ok


def servir(projeto, porta):
    """Processo filho: o painel de verdade, com o tune-up-studio deste repo no lugar do instalado."""
    import lancador
    import painel
    with open(os.path.join(STUDIO, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
        versao = json.load(f).get("version")
    original = config.entrada_do_plugin
    config.entrada_do_plugin = lambda chave, home=None: (
        {"installPath": STUDIO, "version": versao} if chave == CHAVE else original(chave, home))
    argv = lancador.argv_travas
    lancador.argv_travas = lambda a, c=None: argv(a, c) + ["--plugin-dir", STUDIO]
    painel.main(["--projeto", projeto, "--port", str(porta)])


def porta_livre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        p = s.getsockname()[1]
    return p if p != 8787 else porta_livre()


class Tela:
    """Pedidos como o fetch da tela: same-origin, Origin do painel e o token da sessão."""

    def __init__(self, base):
        self.base, self.token = base, None

    def pedir(self, metodo, caminho, corpo=None, cab=None):
        h = {"Sec-Fetch-Site": "same-origin"}
        dado = None
        if corpo is not None:
            dado = json.dumps(corpo).encode("utf-8")
            h.update({"Content-Type": "application/json", "Origin": self.base, "X-Painel-Token": self.token or ""})
        h.update(cab or {})
        req = urllib.request.Request(self.base + caminho, data=dado, method=metodo, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def json(self, metodo, caminho, corpo=None):
        cod, _, bruto = self.pedir(metodo, caminho, corpo)
        try:
            return cod, json.loads(bruto.decode("utf-8"))
        except ValueError:
            return cod, {"bruto": bruto[:200].decode("utf-8", "replace")}

    def modulo(self, acao, dados):
        return self.json("POST", "/api/modulos/estudio/acao", {"acao": acao, "dados": dados})

    def abas(self):
        _, m = self.json("GET", "/api/modulos/estudio?fresco=1")
        return {a.get("id"): a.get("blocos") or [] for a in m.get("abas") or []}


def _blocos(abas, aba, tipo):
    return [b for b in abas.get(aba, []) if b.get("tipo") == tipo]


def aprovar_marca(tela):
    cod, r = tela.modulo("marca.redescobrir", {"confirmar": True})
    checar(cod == 200 and (r.get("resultado") or {}).get("feito"), "marca.redescobrir -> %s %s"
           % (cod, json.dumps(r, ensure_ascii=False)[:160]))
    forms = [b for b in _blocos(tela.abas(), "marca", "formulario") if b.get("acao") == "marca.aprovar"]
    sha = ((forms[0].get("dados_fixos") or {}).get("sha256") if forms else "") or ""
    checar(len(sha) == 12, "aba Marca mostra o sha curto %r" % sha)
    cod, r = tela.modulo("marca.aprovar", {"confirmar": True, "sha256": "0" * 12})
    checar(not (r.get("resultado") or {}).get("feito"), "marca.aprovar com sha errado não aprova")
    cod, r = tela.modulo("marca.aprovar", {"confirmar": True, "sha256": sha})
    checar(cod == 200 and (r.get("resultado") or {}).get("feito"), "marca.aprovar -> %s %s"
           % (cod, json.dumps(r, ensure_ascii=False)[:160]))


def disparar(tela, espera):
    _, a = tela.json("GET", "/api/acoes")
    ids = [x.get("id") for x in a.get("acoes") or []]
    checar("estudio.post" in ids, "catálogo da tela tem estudio.post (%s)" % [i for i in ids if "estudio" in str(i)])
    for aviso in a.get("avisos") or []:
        print("  aviso do catálogo:", aviso)
    params = {"briefing": BRIEFING, "formato": "post 4:5", "quadros": "1"}
    cod, r = tela.json("POST", "/api/execucoes", {"acao": "estudio.post", "params": params})
    ex = r.get("execucao") or {}
    if not checar(cod == 201 and ex.get("id"), "POST /api/execucoes -> %s %s" % (cod, json.dumps(r, ensure_ascii=False)[:200])):
        return None
    t0, estado, vistos = time.time(), "", []
    while time.time() - t0 < espera:
        _, lst = tela.json("GET", "/api/execucoes")
        atual = next((e for e in lst.get("execucoes") or [] if e.get("id") == ex["id"]), {})
        estado = atual.get("estado") or "?"
        if not vistos or vistos[-1][1] != estado:
            vistos.append((round(time.time() - t0), estado))
        if estado in FIM:
            break
        time.sleep(10)
    print("exec %s | trabalho %s | %.0f s | estados %s" % (ex["id"], ex.get("trabalho"), time.time() - t0, vistos))
    checar(estado in FIM, "a sessão chegou a um estado final (%s)" % estado)
    return ex


def galeria(tela, tid, saida):
    abas = tela.abas()
    itens = [i for b in _blocos(abas, "galeria", "galeria") for i in b.get("itens") or []
             if i.get("arquivo", "").startswith("trabalhos/%s/" % tid)]
    checar(bool(itens), "galeria lista arquivos do trabalho %s (%d)" % (tid, len(itens)))
    for i in itens:
        cod, cab, corpo = tela.pedir("GET", "/api/modulos/estudio/arquivo?c=" + urllib.parse.quote(i["arquivo"]))
        tipo = cab.get("Content-Type")
        checar(cod == 200 and len(corpo) == int(cab.get("Content-Length") or -1)
               and (corpo[:8] == b"\x89PNG\r\n\x1a\n" or tipo != "image/png"),
               "rota de mídia %s -> %s %s %d bytes, selo %s" % (i["arquivo"], cod, tipo, len(corpo),
                                                                (i.get("selo") or {}).get("texto")))
        with open(os.path.join(saida, "tela-" + os.path.basename(i["arquivo"])), "wb") as f:
            f.write(corpo)
    for b in abas.get("fila", []):
        for it in b.get("itens") or []:
            print("  fila: %s | %s | %s" % (it.get("titulo"), (it.get("selo") or {}).get("texto"),
                                           str(it.get("detalhe"))[:160]))


def aprovar_peca(tela, tid, dados):
    cod, r = tela.modulo("peca.aprovar", {"trabalho": tid, "confirmar": True})
    checar(cod == 200 and (r.get("resultado") or {}).get("feito"), "peca.aprovar -> %s %s"
           % (cod, json.dumps(r, ensure_ascii=False)[:200]))
    cod, r = tela.modulo("peca.aprovar", {"trabalho": tid, "confirmar": True})
    checar(cod == 409, "peca.aprovar de novo -> %s (esperado 409)" % cod)
    pasta = os.path.join(dados, "aprovados", tid)
    try:
        with open(os.path.join(pasta, "manifesto.json"), encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, ValueError) as e:
        return checar(False, "manifesto.json legível (%s)" % e)
    print("  manifesto:", json.dumps({k: man.get(k) for k in ("trabalho", "acao", "plataforma", "selo")},
                                     ensure_ascii=False)[:300])
    for a in man.get("arquivos") or []:
        with open(os.path.join(pasta, a["nome"]), "rb") as f:
            sha = hashlib.sha256(f.read()).hexdigest()
        checar(sha == a.get("sha256"), "sha256 de %s bate com o manifesto (%s)" % (a["nome"], sha[:16]))
    checar(bool(man.get("arquivos")), "manifesto lista arquivos")


def mp4_com_range(tela, dados, mp4):
    tid = "0123456789ab"
    pasta = os.path.join(dados, "trabalhos", tid)
    os.makedirs(pasta, exist_ok=True)
    shutil.copy2(mp4, os.path.join(pasta, "video.mp4"))
    total = os.path.getsize(mp4)
    c = "/api/modulos/estudio/arquivo?c=" + urllib.parse.quote("trabalhos/%s/video.mp4" % tid)
    cod, cab, corpo = tela.pedir("GET", c)
    checar(cod == 200 and len(corpo) == total and cab.get("Content-Type") == "video/mp4"
           and cab.get("Accept-Ranges") == "bytes", "MP4 inteiro -> %s %s %d bytes, Accept-Ranges %s, CSP %s"
           % (cod, cab.get("Content-Type"), len(corpo), cab.get("Accept-Ranges"), cab.get("Content-Security-Policy")))
    with open(mp4, "rb") as f:
        bruto = f.read()
    for faixa, ini, fim in (("bytes=0-1", 0, 1), ("bytes=1000-", 1000, total - 1), ("bytes=-500", total - 500, total - 1)):
        cod, cab, corpo = tela.pedir("GET", c, cab={"Range": faixa})
        checar(cod == 206 and corpo == bruto[ini:fim + 1] and cab.get("Content-Range") == "bytes %d-%d/%d" % (ini, fim, total),
               "Range %s -> %s %s %d bytes" % (faixa, cod, cab.get("Content-Range"), len(corpo)))
    cod, cab, _ = tela.pedir("GET", c, cab={"Range": "bytes=%d-" % (total + 10)})
    checar(cod == 416, "Range fora do arquivo -> %s %s" % (cod, cab.get("Content-Range")))
    return tid


def principal():
    ap = argparse.ArgumentParser()
    ap.add_argument("--saida", required=True)
    ap.add_argument("--mp4", default=None, help="vídeo para provar a rota com Range")
    ap.add_argument("--sem-sessao", action="store_true", help="não dispara a sessão real (sem cota)")
    ap.add_argument("--espera", type=int, default=900, help="segundos no máximo para a sessão")
    ap.add_argument("--segurar", default=None, help="espera este arquivo existir antes de limpar")
    ap.add_argument("--servir", nargs=2, metavar=("PROJETO", "PORTA"), help=argparse.SUPPRESS)
    arg = ap.parse_args()
    if arg.servir:
        return servir(arg.servir[0], int(arg.servir[1]))
    saida = os.path.realpath(arg.saida)
    os.makedirs(saida, exist_ok=True)
    projeto = tempfile.mkdtemp(prefix="prova-tela-", dir=os.path.expanduser("~"))
    proc, ex, tela = None, None, None
    try:
        shutil.copytree(EXEMPLO, projeto, dirs_exist_ok=True,  # sem as peças prontas; a marca vem pela tela
                        ignore=shutil.ignore_patterns("post-4x5", "video-9x16", "reserva-9x16", ".hyperframes"))
        os.makedirs(os.path.join(projeto, ".tune-up", config.PACOTE_PADRAO), exist_ok=True)
        with open(os.path.join(projeto, ".tune-up", "painel.json"), "w", encoding="utf-8") as f:
            json.dump({"modulos_de_plugins": [CHAVE + ":estudio"], "acoes_de_plugins": [CHAVE],
                       "max_execucoes": 1}, f)
        dados = config.carregar(projeto)["dados_dir"]
        porta = porta_livre()
        log = open(os.path.join(saida, "painel.log"), "wb")
        proc = subprocess.Popen([sys.executable, "-B", os.path.abspath(__file__), "--saida", saida,
                                 "--servir", projeto, str(porta)], stdin=subprocess.DEVNULL, stdout=log, stderr=log)
        tela = Tela("http://127.0.0.1:%d" % porta)
        for _ in range(50):
            try:
                cod, s = tela.json("GET", "/api/sessao")
                break
            except OSError:
                time.sleep(0.2)
        else:
            return checar(False, "painel não subiu (veja painel.log)") and 1
        tela.token = s.get("token")
        print("painel:", tela.base, "| projeto:", projeto)
        cod2, _, _ = tela.pedir("GET", "/api/sessao", cab={"Sec-Fetch-Site": "cross-site"})
        checar(bool(tela.token) and cod2 == 403, "token só sai com same-origin (cross-site -> %s)" % cod2)
        _, mods = tela.json("GET", "/api/modulos")
        checar("estudio" in json.dumps(mods), "módulo estudio ligado pelo painel.json")
        checar(set(tela.abas()) == {"novo", "fila", "galeria", "aprovacao", "marca", "ambiente"}, "6 abas do estúdio")
        aprovar_marca(tela)
        if not arg.sem_sessao:
            ex = disparar(tela, arg.espera)
            if ex and ex.get("trabalho"):
                galeria(tela, ex["trabalho"], saida)
                aprovar_peca(tela, ex["trabalho"], dados)
        if arg.mp4:
            mp4_com_range(tela, dados, arg.mp4)
        if arg.segurar:
            print("painel no ar em %s; crie %s para limpar" % (tela.base, arg.segurar), flush=True)
            while not os.path.exists(arg.segurar):
                time.sleep(2)
    finally:
        if ex and tela:
            cod, r = tela.json("POST", "/api/execucoes/%s/parar" % ex["id"], {})
            print("parar ->", cod, json.dumps(r, ensure_ascii=False)[:160])
            r = subprocess.run(["claude", "rm", ex["id"]], capture_output=True, text=True, timeout=60)
            print("claude rm ->", r.returncode, (r.stdout + r.stderr).strip()[:160])
        if proc:
            proc.terminate()
            proc.wait(timeout=20)
        shutil.rmtree(projeto, ignore_errors=True)
        print("projeto apagado:", not os.path.exists(projeto))
    print("FALHAS:", FALHAS or "nenhuma")
    return 1 if FALHAS else 0


if __name__ == "__main__":
    sys.exit(principal())
