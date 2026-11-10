"""Lançador do painel: roda ações numa sessão do Claude Code em segundo plano.

O cliente só manda {acao, params}. O catálogo e a validação ficam em
catalogo.py. Aqui: dispara `claude --bg -n NOME PROMPT` com lista de argumentos,
sem shell e sem modo que pula permissão; guarda o registro em
<pacote>/dados/execucoes.json (0600, escrita atômica, trava de arquivo); cruza o registro
com `claude agents --json --all` para dizer o estado; para e abre no Terminal.
"""
import datetime
import fcntl
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import threading
import time

from catalogo import (ErroAcao, RE_ID_ACAO, carregar_catalogo, montar, nome_da_sessao,  # noqa: F401
                      publica, validar_params)
from travas import argv_travas

RE_ID_EXEC = re.compile(r"^[0-9a-f]{6,16}$")
RE_SESSAO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
RE_SAIDA = re.compile(r"backgrounded\s*·\s*([0-9a-f]{6,16})\b")
RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ATIVOS = ("rodando", "precisa_de_voce")
OCIOSO = 180        # s sem escrita na conversa (nem nos subagentes) com o CLI em "idle": parou de trabalhar
GRACA = 45          # s: sessão recém-disparada ainda pode não aparecer em `claude agents`
TTL_AGENTES = 3
MAX_REGISTRO = 200
SCRIPT_TERMINAL = ["on run argv", 'tell application "Terminal"', "activate",
                   "do script (item 1 of argv)", "end tell", "end run"]


def agora_iso(t):
    return datetime.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


class Registro:
    """dados/execucoes.json: lista de execuções. 0600, escrita atômica, trava de arquivo."""

    def __init__(self, pasta):
        self.pasta = pasta
        self.arquivo = os.path.join(pasta, "execucoes.json")
        self.arquivo_trava = os.path.join(pasta, "execucoes.lock")

    def trava(self):
        os.makedirs(self.pasta, mode=0o700, exist_ok=True)
        os.chmod(self.pasta, 0o700)
        return _TravaArquivo(self.arquivo_trava)

    def ler(self):
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                dado = json.load(f)
        except (OSError, ValueError):
            return []
        if not isinstance(dado, list):
            return []
        return [x for x in dado if isinstance(x, dict) and RE_ID_EXEC.match(str(x.get("id", "")))]

    def gravar(self, lista):
        """Chame com a trava na mão."""
        fd, tmp = tempfile.mkstemp(prefix=".execucoes-", dir=self.pasta)  # nasce 0600
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(lista[-MAX_REGISTRO:], f, ensure_ascii=False, indent=1)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.arquivo)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

    def atualizar(self, exec_id, **campos):
        with self.trava():
            lista = self.ler()
            for r in lista:
                if r["id"] == exec_id:
                    r.update(campos)
            self.gravar(lista)


class _TravaArquivo:
    """flock exclusivo: vale entre threads (fd próprio) e entre processos."""

    def __init__(self, caminho):
        self.caminho = caminho

    def __enter__(self):
        self.fd = os.open(self.caminho, os.O_RDWR | os.O_CREAT, 0o600)
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


def mapear_estado(reg, agente, agora, ocioso_ha=None):
    """Cruza o registro com uma linha de `claude agents --json --all`.

    Medido no CLI 2.1.322: recém-disparada state=working (status some, depois busy);
    pergunta pendente state=blocked + status=waiting; terminou state=done + status=idle
    (processo vivo) ou só state=done (depois de stop); parada no meio state=stopped;
    depois de `claude rm` a linha some.
    """
    if agente is None:
        if reg.get("terminou_em"):  # já tinha terminado; depois foi apagada (`claude rm`)
            return "terminou"
        if reg.get("parada_pelo_painel"):
            return "parada"
        return "rodando" if agora - float(reg.get("iniciada_ts") or 0) < GRACA else "sumiu"
    state = str(agente.get("state") or "").lower()
    status = str(agente.get("status") or "").lower()
    if state == "blocked" or status == "waiting":
        return "precisa_de_voce"
    if status == "busy":
        return "rodando"
    if state in ("working", "running", "busy", "active"):
        # Medido no 2.1.322: o CLI deixa state=working + status=idle por minutos depois de a
        # sessão responder. Sem escrita na conversa nem nos subagentes há OCIOSO s, parou.
        if status == "idle" and ocioso_ha is not None and ocioso_ha > OCIOSO:
            return "terminou"
        return "rodando"
    if state in ("done", "completed", "finished"):
        return "terminou"
    if state in ("stopped", "killed", "failed", "error", "exited"):
        return "parada"
    return "terminou" if status == "idle" else "rodando"


def rodar_padrao(cmd, cwd, timeout):
    """subprocess com lista, sem shell. Devolve (codigo, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, shell=False)
    except FileNotFoundError:
        return 127, "", "comando não encontrado"
    except subprocess.TimeoutExpired:
        return 124, "", "demorou demais"
    except OSError as e:
        return 126, "", str(e)
    return r.returncode, r.stdout or "", r.stderr or ""


class Lancador:
    def __init__(self, cfg, obter_estado, rodar=rodar_padrao, relogio=time.time, plataforma=None):
        self.cfg, self.obter_estado, self.rodar, self.relogio = cfg, obter_estado, rodar, relogio
        self.plataforma = plataforma or sys.platform
        self.registro = Registro(cfg["dados_dir"])
        self._trava = threading.Lock()
        self._trava_agentes = threading.Lock()
        self._agentes = (0.0, None)
        self._ultimo = {}

    def catalogo(self):
        return carregar_catalogo([self.cfg["acoes_dir"], self.cfg.get("acoes_pacote_dir")])

    def acoes(self):
        acoes, avisos = self.catalogo()
        return [publica(a) for a in acoes], avisos

    def agentes(self, forcar=False):
        """{id: linha} de `claude agents --json --all` (cache curto) ou None se o CLI falhar."""
        with self._trava_agentes:
            quando, dado = self._agentes
            if not forcar and dado is not None and self.relogio() - quando < TTL_AGENTES:
                return dado
            cod, out, _err = self.rodar([self.cfg["claude_bin"], "agents", "--json", "--all"],
                                        self.cfg["workspace"], 8)
            try:
                lista = json.loads(out) if cod == 0 else None
            except ValueError:
                lista = None
            if not isinstance(lista, list):
                return None
            dado = {str(a.get("id")): a for a in lista if isinstance(a, dict) and a.get("id")}
            self._agentes = (self.relogio(), dado)
            return dado

    def esquecer_agentes(self):
        with self._trava_agentes:
            self._agentes = (0.0, None)

    def comando_attach(self, exec_id):
        return "%s attach %s" % (shlex.quote(self.cfg["claude_bin"]), exec_id)

    def _estado(self, reg, agente, agora):
        ocioso = None
        sid = str((agente or {}).get("sessionId") or reg.get("sessao_id") or "")
        if agente and sid:
            try:
                import transcricao
                ult = transcricao.ultima_atividade(self.cfg["projects_dir"], sid, self.cfg["workspace"])
                ocioso = None if ult is None else time.time() - ult
            except Exception:
                ocioso = None
        return mapear_estado(reg, agente, agora, ocioso)

    def _como_execucao(self, reg, agentes, agora):
        if agentes is None:  # CLI falhou: mantém o último estado visto
            estado = self._ultimo.get(reg["id"], "rodando")
        else:
            estado = self._ultimo[reg["id"]] = self._estado(reg, agentes.get(reg["id"]), agora)
        out = {k: reg.get(k) for k in ("id", "nome", "acao", "titulo", "iniciada_em")}
        out["grupo"] = out["area"] = reg.get("grupo") or reg.get("area") or ""
        out.update(sessao_id=reg.get("sessao_id") or "", params=reg.get("params") or {}, estado=estado,
                   comando_attach=self.comando_attach(reg["id"]))
        for k in ("fase", "parte"):
            if reg.get(k):
                out[k] = reg[k]
        return out

    def execucoes(self, forcar=False, travado=False):
        """Todas as execuções do registro, mais novas primeiro, com o estado de agora.

        `travado=True` quando quem chama já segura a trava do registro (flock não é reentrante).
        """
        regs = self.registro.ler()
        agentes = self.agentes(forcar)
        agora = self.relogio()
        novos = {}
        for r in regs:  # aprende o sessionId completo e quando terminou (sobrevive ao `claude rm`)
            a = (agentes or {}).get(r["id"]) or {}
            sid = str(a.get("sessionId") or "")
            if not r.get("sessao_id") and RE_SESSAO.match(sid) and sid.startswith(r["id"]):
                r["sessao_id"] = novos.setdefault(r["id"], {})["sessao_id"] = sid
            if a and not r.get("terminou_em") and self._estado(r, a, agora) == "terminou":
                r["terminou_em"] = novos.setdefault(r["id"], {})["terminou_em"] = agora_iso(agora)
        if novos:
            if travado:
                self.registro.gravar(regs)
            else:
                with self.registro.trava():
                    atual = self.registro.ler()
                    for r in atual:
                        for k, v in novos.get(r["id"], {}).items():
                            if not r.get(k):
                                r[k] = v
                    self.registro.gravar(atual)
        lista = [self._como_execucao(r, agentes, agora) for r in regs]
        return sorted(lista, key=lambda e: e["iniciada_em"] or "", reverse=True)

    def achar(self, exec_id):
        """Linha do registro (só execuções que o painel disparou) ou None."""
        if not isinstance(exec_id, str) or not RE_ID_EXEC.match(exec_id):
            return None
        return next((r for r in self.registro.ler() if r["id"] == exec_id), None)

    def execucao(self, exec_id):
        return next((e for e in self.execucoes() if e["id"] == exec_id), None)

    def iniciar(self, acao_id, params):
        """Valida, confere duplicata e teto, dispara e registra. Levanta ErroAcao."""
        if not isinstance(acao_id, str) or not RE_ID_ACAO.match(acao_id):
            raise ErroAcao("Ação inválida.")
        acao = next((a for a in self.catalogo()[0] if a["id"] == acao_id), None)
        if acao is None:
            raise ErroAcao("Essa ação não existe.")
        precisa_estado = any(p["tipo"] in ("fase", "parte") for p in acao["params"])
        valores = validar_params(acao, params, self.obter_estado() if precisa_estado else {})
        prompt, nome = montar(acao["_prompt"], valores), nome_da_sessao(acao, valores)
        if not prompt or prompt.startswith("-"):
            raise ErroAcao("O pedido ficou vazio.")
        chave = json.dumps(valores, sort_keys=True, ensure_ascii=False)
        with self._trava, self.registro.trava():
            ativas = [e for e in self.execucoes(forcar=True, travado=True) if e["estado"] in ATIVOS]
            igual = [e for e in ativas if e["acao"] == acao_id
                     and json.dumps(e["params"], sort_keys=True, ensure_ascii=False) == chave]
            if igual:
                raise ErroAcao("Essa ação já está rodando.", 409, igual[0]["id"])
            if len(ativas) >= self.cfg["max_execucoes"]:
                raise ErroAcao("Já tem %d rodando ao mesmo tempo. Espere uma acabar ou pare uma."
                               % len(ativas), 409, ativas[0]["id"])
            # travas de verdade (deny + gancho) no argv; o prompt vai por último, nunca começa com '-'
            # pular_permissoes: some so o pedido comum de permissao. Medido no CLI 2.1.322: regra de negar,
            # gancho que nega e gancho que pergunta continuam valendo com essa flag.
            pular = ["--dangerously-skip-permissions"] if self.cfg.get("pular_permissoes") else []
            cmd = [self.cfg["claude_bin"], "--bg", "-n", nome] + pular + argv_travas(acao, self.cfg) + [prompt]
            cod, out, err = self.rodar(cmd, self.cfg["workspace"], 60)
            m = RE_SAIDA.search(RE_ANSI.sub("", out + "\n" + err))
            if cod != 0 or not m:
                raise ErroAcao("Não consegui começar a sessão do Claude. Veja se o comando claude funciona.", 500)
            t = self.relogio()
            reg = {"id": m.group(1), "sessao_id": "", "nome": nome, "acao": acao_id, "grupo": acao["grupo"],
                   "titulo": acao["titulo"], "params": valores, "iniciada_em": agora_iso(t),
                   "iniciada_ts": t, "cwd": self.cfg["workspace"], "risco": acao["risco"]}
            for p in acao["params"]:
                if p["tipo"] in ("fase", "parte") and valores.get(p["nome"]):
                    reg[p["tipo"]] = valores[p["nome"]]
            self.registro.gravar([r for r in self.registro.ler() if r["id"] != reg["id"]] + [reg])
        self.esquecer_agentes()
        return self._como_execucao(reg, {}, t)

    def parar(self, exec_id):
        if self.achar(exec_id) is None:
            raise ErroAcao("Não achei essa execução.", 404)
        antes = (self.execucao(exec_id) or {}).get("estado")
        cod, out, err = self.rodar([self.cfg["claude_bin"], "stop", exec_id], self.cfg["workspace"], 20)
        if cod != 0 and "No job matching" not in err + out:
            raise ErroAcao("Não consegui parar a sessão.", 500)
        if antes in ATIVOS:  # parar uma que já terminou não muda o que ela foi
            self.registro.atualizar(exec_id, parada_pelo_painel=True)
        self.esquecer_agentes()
        return {"ok": True}

    def abrir(self, exec_id):
        """Abre o Terminal em `claude attach <id>`. O AppleScript é fixo; o comando vai como argv."""
        if self.achar(exec_id) is None:
            raise ErroAcao("Não achei essa execução.", 404)
        comando = self.comando_attach(exec_id)
        if self.plataforma != "darwin":
            return {"ok": False, "comando": comando}
        args = ["osascript"]
        for linha in SCRIPT_TERMINAL:
            args += ["-e", linha]
        cod, _out, _err = self.rodar(args + [comando], self.cfg["workspace"], 15)
        return {"ok": cod == 0, "comando": comando}
