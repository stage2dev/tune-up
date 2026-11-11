"""Lançador do painel: roda ações numa sessão do Claude Code em segundo plano.

O cliente só manda {acao, params}. O catálogo e a validação ficam em
catalogo.py. Aqui: dispara `claude --bg -n NOME PROMPT` com lista de argumentos,
sem shell e sem modo que pula permissão; guarda o registro em
<pacote>/dados/execucoes.json (0600, escrita atômica, trava de arquivo); cruza o registro
com `claude agents --json --all` para dizer o estado; para e abre no Terminal.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import threading
import time

from catalogo import (ErroAcao, RE_ID_ACAO, carregar_catalogo, catalogo_do_projeto, montar, nome_da_sessao,  # noqa: F401
                      publica, texto_livre, validar_params)
from habilidades import anexar as anexar_habilidades, pedido as pedido_com_habilidades
import mascara
import modulos
import teto
import trabalho
from estado_exec import GRACA, OCIOSO, mapear_estado  # noqa: F401
from modelos import Modelos
import pergunta
from pergunta import PERGUNTA_VALE  # noqa: F401
from registro import MAX_REGISTRO, PRAZO_OCUPADO, RE_ID_EXEC, Registro, agora_iso  # noqa: F401
from trava import PRAZO_TRAVA, _TravaArquivo  # noqa: F401
from travas import argv_travas

RE_SESSAO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
RE_SAIDA = re.compile(r"backgrounded\s*·\s*([0-9a-f]{6,16})\b")
RE_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
ATIVOS = ("rodando", "precisa_de_voce")
RESPONDIVEIS = ("terminou", "parada")  # a sessão acabou a vez dela: dá para mandar outra mensagem
TTL_AGENTES = 3
SCRIPT_TERMINAL = ["on run argv", 'tell application "Terminal"', "activate",
                   "do script (item 1 of argv)", "end tell", "end run"]


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
        self.dormir = time.sleep  # trocado nos testes
        self.registro = Registro(cfg["dados_dir"])
        self._trava = threading.Lock()
        self._trava_agentes = threading.Lock()
        self._agentes = (0.0, None)
        self._ultimo = {}
        self.modelos = Modelos(cfg, self.rodar, relogio)

    def status_modelos(self):
        """{apelido: sim|nao|verificando|nao_sei} dos modelos preferidos das ações (dispara a sonda)."""
        return self.modelos.resumo(self.catalogo()[0])

    def catalogo(self):
        return catalogo_do_projeto(self.cfg)

    def acoes(self):
        acoes, avisos = self.catalogo()
        return [publica(a) for a in acoes], avisos + modulos.negar_dos_modulos(self.cfg)[1]

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
        ocioso = ult = None
        sid = str((agente or {}).get("sessionId") or reg.get("sessao_id") or "")
        if agente and sid:
            try:
                import transcricao
                ult = transcricao.ultima_atividade(self.cfg["projects_dir"], sid, reg.get("cwd") or self.cfg["workspace"])
                ocioso = None if ult is None else time.time() - ult
            except Exception:
                ocioso = ult = None
        estado = mapear_estado(reg, agente, agora, ocioso)
        if reg.get("falha") and estado in ATIVOS:  # o painel já rodou `claude stop`; o CLI pode demorar a mostrar
            return "parada"
        # Acabou de receber uma resposta: o CLI ainda pode mostrar a linha velha (done/idle) por alguns segundos.
        # Vale só enquanto a conversa não andou depois da resposta; se já escreveu, o "terminou" é de verdade.
        respondida = float(reg.get("respondida_ts") or 0)
        # A linha velha também pode ser a da pergunta já respondida (blocked, sem processo depois do stop).
        sem_processo = not (agente or {}).get("status") and not (agente or {}).get("pid")
        velho = estado in RESPONDIVEIS or (estado == "precisa_de_voce" and sem_processo)
        if velho and agora - respondida < GRACA and (ult is None or ult <= respondida + 2):
            return "rodando"
        return estado

    def _regras_cabem(self, reg, caixa):  # negar dos módulos de agora já ia na sessão? erro ao ler = não
        if "regras" not in caixa:
            try:
                caixa["regras"] = modulos.regras_de_negar(self.cfg, tempo=2.0)
            except Exception:
                caixa["regras"] = None
        return caixa["regras"] is not None and set(caixa["regras"]) <= set(reg.get("negar_modulos") or [])

    def _como_execucao(self, reg, agentes, agora, caixa=None):
        if agentes is None:  # CLI falhou: mantém o último estado visto
            estado = self._ultimo.get(reg["id"], "rodando")
        else:
            estado = self._ultimo[reg["id"]] = self._estado(reg, agentes.get(reg["id"]), agora)
        out = {k: reg.get(k) for k in ("id", "nome", "acao", "titulo", "iniciada_em", "trabalho")}
        out["grupo"] = out["area"] = reg.get("grupo") or reg.get("area") or ""
        sid = reg.get("sessao_id") or ""
        # Responder acorda a sessão guardada pelo CLI (com as travas dela): só vale se ela ainda está na lista.
        # Sandbox não: --resume não leva o --settings com o bloco sandbox.
        linha = (agentes or {}).get(reg["id"])
        # Medido no CLI 2.1.322: a vez acabou com uma pergunta escrita -> state=blocked + status=idle (sem
        # waitingFor). É "precisa de você", mas a resposta é texto comum: vale como vez terminada.
        perguntou = (estado == "precisa_de_voce" and linha is not None and not linha.get("waitingFor")
                     and str(linha.get("status") or "").lower() == "idle")
        # As regras de negar dos módulos de agora têm de caber nas que a sessão levou (vale para os dois jeitos).
        acorda = bool(RE_SESSAO.match(sid)) and linha is not None and not reg.get("sandbox") and (
            (estado in RESPONDIVEIS or perguntou or estado in ATIVOS)
            and self._regras_cabem(reg, {} if caixa is None else caixa))
        responde = acorda and (estado in RESPONDIVEIS or perguntou)
        out.update(sessao_id=sid, params=reg.get("params") or {}, estado=estado,
                   comando_attach=self.comando_attach(reg["id"]), modelo=reg.get("modelo") or "",
                   esforco=reg.get("esforco") or "", pode_responder=responde, habilidades=reg.get("habilidades") or [],
                   # mandar mensagem com a sessão trabalhando ou esperando: para a vez dela e continua na mesma sessão
                   pode_interromper=acorda and estado in ATIVOS)
        # Espera presa no terminal (pedido de permissão): escrever no chat cancela o pedido, não o responde.
        out["espera_terminal"] = bool(estado == "precisa_de_voce" and not perguntou
                                      and linha is not None and linha.get("waitingFor"))
        achada = pergunta.ler(self.cfg, sid, reg) if responde else None
        if achada:
            out["pergunta"] = achada
        for k in ("fase", "parte", "falha"):
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
            if agentes is not None and teto.tem_teto(r):  # passou do tempo: `claude stop` e marca falha
                campos = teto.conferir(r, self._estado(r, agentes.get(r["id"]), agora), agora, self._parar_cli)
                if campos:
                    r.update(campos)
                    novos.setdefault(r["id"], {}).update(campos)
        if novos:
            if travado:
                self.registro.gravar(regs)
            else:
                with self.registro.trava():
                    atual = self.registro.ler()
                    for r in atual:
                        for k, v in novos.get(r["id"], {}).items():
                            if not r.get(k) or k in teto.SEMPRE:
                                r[k] = v
                    self.registro.gravar(atual)
        caixa = {}  # regras dos módulos: lidas no máximo uma vez por lista
        lista = [self._como_execucao(r, agentes, agora, caixa) for r in regs]
        return sorted(lista, key=lambda e: e["iniciada_em"] or "", reverse=True)

    def achar(self, exec_id):
        """Linha do registro (só execuções que o painel disparou) ou None."""
        if not isinstance(exec_id, str) or not RE_ID_EXEC.match(exec_id):
            return None
        return next((r for r in self.registro.ler() if r["id"] == exec_id), None)

    def execucao(self, exec_id):
        return next((e for e in self.execucoes() if e["id"] == exec_id), None)

    def iniciar(self, acao_id, params, habilidades=None):
        """Valida, confere duplicata e teto, dispara e registra. Levanta ErroAcao."""
        if not isinstance(acao_id, str) or not RE_ID_ACAO.match(acao_id):
            raise ErroAcao("Ação inválida.")
        acao = next((a for a in self.catalogo()[0] if a["id"] == acao_id), None)
        if acao is None:
            raise ErroAcao("Essa ação não existe.")
        precisa_estado = any(p["tipo"] in ("fase", "parte") for p in acao["params"])
        valores = validar_params(acao, params, self.obter_estado() if precisa_estado else {})
        mascarados = {k: mascara.mascarar(v) if isinstance(v, str) else v for k, v in valores.items()}
        # "trabalho" só para conferir aqui; dentro da trava o prompt é refeito com a pasta de verdade
        base, nome = trabalho.montar_prompt(acao, valores, "trabalho"), nome_da_sessao(acao, mascarados)
        prompt, nomes_hab = pedido_com_habilidades(self.cfg, acao["grupo"], base, habilidades)  # vazio: 400
        sufixo = prompt[len(base.rstrip()):] if nomes_hab else ""  # bloco das skills: volta no prompt refeito
        chave = json.dumps(valores, sort_keys=True, ensure_ascii=False)
        try:  # `requer` (aprovação do dono) e INFO["negar"] dos módulos; antes das travas, com tempo limite
            extra = modulos.antes_de_disparar(self.cfg, acao)
        except modulos.ErroModulo as e:  # módulo que não carrega: fecha, não dispara sem as regras
            raise ErroAcao(e.mensagem, e.codigo)
        if extra:
            trv = acao.get("_travas") or {}
            negar = list(trv.get("negar") or [])
            acao = dict(acao, _travas=dict(trv, negar=negar + [r for r in extra if r not in negar]))
        # Fora da trava: a primeira escolha pode sondar a licença (uns 10 s, uma vez por semana).
        modelo, _fora = self.modelos.escolher(acao.get("modelos") or [])
        esforco = acao.get("esforco") or ""
        with self._trava, self.registro.trava():
            ativas = [e for e in self.execucoes(forcar=True, travado=True) if e["estado"] in ATIVOS]
            igual = [e for e in ativas if e["acao"] == acao_id
                     and json.dumps(e["params"], sort_keys=True, ensure_ascii=False) == chave]
            if igual:
                raise ErroAcao("Essa ação já está rodando.", 409, igual[0]["id"])
            if len(ativas) >= self.cfg["max_execucoes"]:
                raise ErroAcao("Já tem %d rodando ao mesmo tempo. Espere uma acabar ou pare uma."
                               % len(ativas), 409, ativas[0]["id"])
            pasta = trabalho.nova_pasta(self.cfg["dados_dir"], acao)  # None: a ação não usa {trabalho}
            cwd = pasta if acao.get("sandbox") else self.cfg["workspace"]  # sandbox: cwd = pasta de trabalho
            if pasta:  # o id do trabalho fica fora de `valores` (a checagem de duplicata acima não o vê)
                prompt, acao = trabalho.montar_prompt(acao, valores, pasta), trabalho.resolver_travas(acao, pasta)
                prompt = prompt.rstrip() + sufixo if sufixo else prompt
            # travas de verdade (deny + gancho) no argv; o prompt vai por último, nunca começa com '-'
            # pular_permissoes: some so o pedido comum de permissao. Medido no CLI 2.1.322: regra de negar,
            # gancho que nega e gancho que pergunta continuam valendo com essa flag.
            pular = ["--dangerously-skip-permissions"] if self.cfg.get("pular_permissoes") else []
            # --effort aceita max (claude --help); a chave de esforço do --settings vai só até xhigh (não
            # medido aqui), então uma reserva pelo --settings não cobriria max. Esforço vai só pela opção.
            escolha = (["--model", modelo] if modelo else []) + (["--effort", esforco] if esforco else [])
            cmd = ([self.cfg["claude_bin"], "--bg", "-n", nome] + escolha + pular
                   + argv_travas(acao, self.cfg) + [prompt])
            try:
                trabalho.criar(pasta, acao, valores)
                cod, out, err = self.rodar(cmd, cwd, 60)
            except BaseException:
                trabalho.apagar(pasta)
                raise
            if cod != 0 or not (m := RE_SAIDA.search(RE_ANSI.sub("", out + "\n" + err))):
                trabalho.apagar(pasta)
                raise ErroAcao("Não consegui começar a sessão do Claude (%s). Veja se o comando claude funciona."
                               % mascara.primeira_linha(err + "\n" + out), 500)  # causa: workspace sem confiança...
            t = self.relogio()
            reg = {"id": m.group(1), "sessao_id": "", "nome": nome, "acao": acao_id, "grupo": acao["grupo"],
                   "titulo": acao["titulo"], "params": valores, "iniciada_em": agora_iso(t),
                   "iniciada_ts": t, "cwd": cwd, "risco": acao["risco"], "sandbox": bool(acao.get("sandbox")),
                   "modelo": modelo, "esforco": esforco, "negar_modulos": sorted(extra), "habilidades": nomes_hab,
                   "trabalho": os.path.basename(pasta) if pasta else "",
                   **{c: acao.get(c) for c in teto.CAMPOS}}
            for p in acao["params"]:
                if p["tipo"] in ("fase", "parte") and valores.get(p["nome"]):
                    reg[p["tipo"]] = valores[p["nome"]]
            self.registro.gravar([r for r in self.registro.ler() if r["id"] != reg["id"]] + [reg])
        self.esquecer_agentes()
        return self._como_execucao(reg, {}, t)

    def responder(self, exec_id, texto, interromper=False, habilidades=None):
        """Manda outra mensagem para a MESMA sessão. Levanta ErroAcao.

        Com `interromper`, vale também para sessão trabalhando ou esperando no terminal: a vez dela
        é parada (como um Esc) e a mensagem entra na mesma conversa (medido no CLI 2.1.322).

        Medido no CLI 2.1.322: `claude --bg --resume <sessionId> "texto"` SEM outras opções acorda a
        sessão com as opções guardadas (nome, modelo, esforço, travas) e o mesmo id. Com o processo
        antigo ainda vivo (terminou, mas ocioso) ou com qualquer opção a mais, o CLI abre uma CÓPIA
        com outro id. Por isso: para o processo antigo antes e não passa opção nenhuma. Se mesmo
        assim vier outro id, a cópia é parada e apagada (não há garantia de que leva as travas).
        """
        reg = self.achar(exec_id)
        if reg is None:
            raise ErroAcao("Não achei essa conversa.", 404)
        texto = anexar_habilidades(self.cfg, reg.get("grupo") or reg.get("area"), texto_livre(texto), habilidades)[0]
        try:  # a sessão acorda com as travas de quando começou: regra de módulo nova não entraria nela
            agora_negar = modulos.regras_de_negar(self.cfg)
        except modulos.ErroModulo as e:
            raise ErroAcao(e.mensagem, e.codigo)
        if not set(agora_negar) <= set(reg.get("negar_modulos") or []):
            raise ErroAcao("As regras das telas mudaram depois que esta conversa começou. "
                           "Comece uma conversa nova.", 409, exec_id)
        bin_, ws = self.cfg["claude_bin"], self.cfg["workspace"]
        with self._trava:
            todas = self.execucoes(forcar=True)
            ex = next((e for e in todas if e["id"] == exec_id), None)
            ativa = bool(ex) and ex["estado"] in ATIVOS
            if ex is None or not (ex["pode_responder"] or (interromper and ex["pode_interromper"])):
                estado = (ex or {}).get("estado")
                if estado in ATIVOS and (ex or {}).get("pode_interromper") is False:
                    raise ErroAcao("A sessão ainda está subindo. Tente de novo em alguns segundos.", 409, exec_id)
                if estado == "rodando":
                    raise ErroAcao("O Claude ainda está trabalhando. Espere ele terminar para responder.", 409, exec_id)
                if estado == "precisa_de_voce":
                    raise ErroAcao("O Claude fez uma pergunta no terminal. Abra a sessão para responder lá.",
                                   409, exec_id)
                raise ErroAcao("Esta conversa não pode mais ser continuada. Comece uma nova.", 409, exec_id)
            ativas = [e for e in todas if e["estado"] in ATIVOS]
            if not ativa and len(ativas) >= self.cfg["max_execucoes"]:  # a que já roda já ocupa a vaga dela
                raise ErroAcao("Já tem %d rodando ao mesmo tempo. Espere uma acabar ou pare uma."
                               % len(ativas), 409, ativas[0]["id"])
            cod, out, err = self.rodar([bin_, "stop", exec_id], ws, 20)
            if cod != 0 and "No job matching" not in err + out:
                raise ErroAcao("Não consegui preparar a sessão para continuar.", 500)
            for tentativa in (1, 2):
                self._esperar_processo_sair(exec_id)
                cod, out, err = self.rodar([bin_, "--bg", "--resume", ex["sessao_id"], texto], ws, 60)
                m = RE_SAIDA.search(RE_ANSI.sub("", out + "\n" + err))
                if cod != 0 or not m:
                    raise ErroAcao("Não consegui continuar a conversa. Veja se o comando claude funciona.", 500)
                if m.group(1) == exec_id:
                    break
                # Veio uma cópia (visto de verdade: o `stop` volta antes de o processo antigo sair).
                # A cópia não fica: para, apaga e tenta mais uma vez.
                parou = self.rodar([bin_, "stop", m.group(1)], ws, 20)[0] == 0
                self.rodar([bin_, "rm", m.group(1)], ws, 20)
                self.esquecer_agentes()
                if not parou:  # a cópia pode seguir viva: entra no registro para aparecer na tela e contar no teto
                    t = self.relogio()
                    orfa = dict(self.achar(exec_id) or {}, id=m.group(1), sessao_id="", iniciada_em=agora_iso(t),
                                iniciada_ts=t, nome="cópia de " + exec_id, titulo="Cópia que não parou",
                                terminou_em="", parada_pelo_painel=False)
                    with self.registro.trava():
                        self.registro.gravar([r for r in self.registro.ler() if r["id"] != orfa["id"]] + [orfa])
                    raise ErroAcao("O Claude abriu uma cópia desta conversa e eu não consegui parar. "
                                   "Pare a cópia na tela Execuções.", 500, m.group(1))
                if tentativa == 2:
                    raise ErroAcao("Não consegui continuar esta conversa do jeito seguro. Tente de novo em "
                                   "alguns segundos ou comece uma nova.", 500)
                self.dormir(2)
            t = self.relogio()
            self.registro.atualizar(exec_id, respondida_ts=t, terminou_em="", parada_pelo_painel=False,
                                    falha="", bloqueada_ts=0)
            try:
                os.unlink(pergunta.arquivo(self.cfg, ex["sessao_id"]))  # a pergunta foi respondida
            except OSError:
                pass
        self.esquecer_agentes()
        out = self._como_execucao(self.achar(exec_id), {}, t)
        out["estado"] = self._ultimo[exec_id] = "rodando"  # acabou de acordar; a lista do CLI ainda não foi relida
        return out

    def _esperar_processo_sair(self, exec_id, vezes=12, pausa=0.5):
        """Depois do `claude stop`: espera a linha da sessão ficar sem processo (sem pid e sem status).

        Medido no CLI 2.1.322: sessão viva tem `pid` e `status`; parada fica só com `state`.
        """
        for _ in range(vezes):
            linha = (self.agentes(forcar=True) or {}).get(exec_id)
            if linha is None or (not linha.get("pid") and not linha.get("status")):
                return True
            self.dormir(pausa)
        return False

    def _parar_cli(self, exec_id):
        cod, out, err = self.rodar([self.cfg["claude_bin"], "stop", exec_id], self.cfg["workspace"], 20)
        return cod == 0 or "No job matching" in err + out

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
