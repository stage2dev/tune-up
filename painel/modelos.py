"""Quais modelos a licença do Claude tem: sonda barata, guardada em disco.

Uma ação pode pedir modelos em ordem de preferência ("modelos": ["fable", "opus"]). A sessão
sai com o primeiro que a licença tem; o último da lista é a reserva e nunca é sondado.

A sonda é um `claude -p` mínimo (sem ferramentas, sem personalizações, sem guardar conversa,
uns 900 tokens: medido no CLI 2.1.322, cerca de 10 s). Resultado:
  - respondeu com o modelo pedido            -> tem (vale 7 dias)
  - "modelo não existe ou sem acesso" (4xx)  -> não tem (vale 1 dia)
  - qualquer outra coisa (rede, limite, CLI) -> não sei (tenta de novo depois de 10 min)

`modelos_disponiveis` no painel.json ({"fable": false}) vence a sonda. Python 3.9, só
biblioteca padrão.
"""
import json
import os
import re
import tempfile
import threading
import time

VALE_SIM = 7 * 24 * 3600
VALE_NAO = 24 * 3600
VALE_NAO_SEI = 600
TEMPO_SONDA = 90
STATUS = ("sim", "nao", "verificando", "nao_sei")
RE_SEM_ACESSO = re.compile(r"unrecognized_model|may not exist|not have access|model_not_found|invalid model", re.I)
APELIDOS = ("fable", "opus", "sonnet", "haiku")


def ler_resposta(codigo, saida):
    """Lê a saída do `claude -p --output-format json`. True = tem, False = não tem, None = não sei."""
    dado = None
    for linha in reversed((saida or "").splitlines()):
        linha = linha.strip()
        if linha.startswith("{") and linha.endswith("}"):
            try:
                dado = json.loads(linha)
            except ValueError:
                continue
            if isinstance(dado, dict) and "is_error" in dado:
                break
            dado = None
    if not isinstance(dado, dict):
        return False if RE_SEM_ACESSO.search(saida or "") else None
    if dado.get("is_error"):
        sem_acesso = dado.get("api_error_status") in (400, 403, 404) and RE_SEM_ACESSO.search(
            str(dado.get("result") or "") + " " + (saida or ""))
        return False if sem_acesso else None
    return True if codigo == 0 else None


def atendeu_com(dado_saida, apelido):
    """O CLI pode trocar de modelo calado. Para apelido conhecido, confere quem respondeu."""
    if apelido not in APELIDOS:
        return True
    try:
        linha = [x for x in dado_saida.splitlines() if x.strip().startswith("{")][-1]
        usados = json.loads(linha).get("modelUsage") or {}
    except (IndexError, ValueError, AttributeError):
        return True
    return any(apelido in str(nome) for nome in usados) if usados else True


class Modelos:
    def __init__(self, cfg, rodar, relogio=time.time):
        self.cfg, self.rodar, self.relogio = cfg, rodar, relogio
        self.arquivo = os.path.join(cfg["dados_dir"], "modelos.json")
        self._trava = threading.Lock()
        self._por_modelo = {}
        self._sondando = set()
        self._nao_sei = {}

    # ---------------------------------------------------------------- disco
    def _ler(self):
        try:
            with open(self.arquivo, encoding="utf-8") as f:
                dado = json.load(f)
        except (OSError, ValueError):
            return {}
        return dado if isinstance(dado, dict) else {}

    def _gravar(self, apelido, tem):
        pasta = os.path.dirname(self.arquivo)
        try:
            os.makedirs(pasta, mode=0o700, exist_ok=True)
            dado = self._ler()
            dado[apelido] = {"tem": bool(tem), "em": self.relogio()}
            fd, tmp = tempfile.mkstemp(prefix=".modelos-", dir=pasta)  # nasce 0600
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dado, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.arquivo)
        except OSError:
            pass  # sem disco a sonda só vale até o painel reiniciar

    # ---------------------------------------------------------------- consulta
    def conhecido(self, apelido):
        """True/False se já sei (painel.json ou sonda ainda válida); None se não sei."""
        forcado = (self.cfg.get("modelos_disponiveis") or {}).get(apelido)
        if isinstance(forcado, bool):
            return forcado
        item = self._ler().get(apelido)
        if isinstance(item, dict) and isinstance(item.get("tem"), bool):
            try:
                idade = self.relogio() - float(item.get("em") or 0)
            except (TypeError, ValueError):
                return None
            if 0 <= idade < (VALE_SIM if item["tem"] else VALE_NAO):
                return item["tem"]
        return None

    def status(self, apelido):
        sei = self.conhecido(apelido)
        if sei is not None:
            return "sim" if sei else "nao"
        with self._trava:
            if apelido in self._sondando:
                return "verificando"
        return "nao_sei"

    # ---------------------------------------------------------------- sonda
    def _comando(self, apelido):
        return [self.cfg["claude_bin"], "-p", "--safe-mode", "--no-session-persistence", "--system-prompt", "ok",
                "--tools", "", "--model", apelido, "--output-format", "json", "ok"]

    def sondar(self, apelido):
        """Pergunta ao CLI (uma sonda por modelo por vez). True, False ou None (não sei)."""
        with self._trava:
            trava = self._por_modelo.setdefault(apelido, threading.Lock())
        try:
            with trava:
                sei = self.conhecido(apelido)  # outra chamada pode ter acabado de sondar
                if sei is not None:
                    return sei
                with self._trava:
                    if self.relogio() - self._nao_sei.get(apelido, -VALE_NAO_SEI) < VALE_NAO_SEI:
                        return None
                    self._sondando.add(apelido)
                tem = self._perguntar(apelido)
                if tem is None:
                    with self._trava:
                        self._nao_sei[apelido] = self.relogio()
                else:
                    self._gravar(apelido, tem)
                return tem
        finally:
            with self._trava:
                self._sondando.discard(apelido)

    def _perguntar(self, apelido):
        try:
            pasta = tempfile.mkdtemp(prefix="painel-sonda-")
            try:
                cod, out, err = self.rodar(self._comando(apelido), pasta, TEMPO_SONDA)
            finally:
                try:
                    os.rmdir(pasta)
                except OSError:
                    pass
            tem = ler_resposta(cod, (out or "") + "\n" + (err or ""))
            return False if tem and not atendeu_com(out or "", apelido) else tem
        except Exception:
            return None

    def sondar_em_fundo(self, apelidos):
        for apelido in apelidos:
            if self.status(apelido) != "nao_sei":
                continue
            with self._trava:
                if self.relogio() - self._nao_sei.get(apelido, -VALE_NAO_SEI) < VALE_NAO_SEI:
                    continue
                self._sondando.add(apelido)  # a tela já vê "verificando" antes de a thread subir
            threading.Thread(target=self.sondar, args=(apelido,), daemon=True).start()

    # ---------------------------------------------------------------- escolha
    def escolher(self, lista):
        """(modelo para o --model, [preferidos que ficaram de fora]). Lista vazia -> ("", [])."""
        if not lista:
            return "", []
        fora = []
        for apelido in lista[:-1]:
            sei = self.conhecido(apelido)
            if sei is None:
                sei = self.sondar(apelido)
            if sei:
                return apelido, fora
            fora.append(apelido)
        return lista[-1], fora

    def resumo(self, catalogo):
        """{apelido: status} dos modelos que são preferência (não reserva) de alguma ação; dispara a sonda."""
        apelidos = []
        for acao in catalogo:
            for apelido in (acao.get("modelos") or [])[:-1]:
                if apelido not in apelidos:
                    apelidos.append(apelido)
        self.sondar_em_fundo(apelidos)
        return {a: self.status(a) for a in apelidos}
