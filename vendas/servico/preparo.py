"""Preparo em um passo: Docker, Evolution e o serviço de Vendas, numa sequência que pode ser refeita sem medo.

    python3 -B <plugin>/servico/preparo.py rodar   --projeto <raiz> [--painel URL] [--porta N] [--porta-evolution N]
    python3 -B <plugin>/servico/preparo.py iniciar --projeto <raiz> [...]   (o mesmo, destacado; volta na hora)
    python3 -B <plugin>/servico/preparo.py estado  --projeto <raiz>         (estado em JSON)

Cada passo confere antes de agir e não faz nada quando já está pronto, então rodar de novo retoma do primeiro passo
que falta. Estado (JSON, 0600) e log (0600) ficam na pasta de dados EXTERNA, nunca no projeto; a chave da Evolution
e a senha do Postgres saem mascaradas de tudo. Um preparo por projeto (trava não bloqueante)."""
import os
import sys

if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.dont_write_bytecode = True

import argparse  # noqa: E402
import datetime  # noqa: E402
import json  # noqa: E402
import secrets  # noqa: E402

from servico import evolution_local, pasta, preparo_docker, preparo_evolution, travas  # noqa: E402
from servico.preparo_sistema import Sistema, falhou, mascarar  # noqa: E402

PASSOS = (
    ("docker_instalado", "Instalar o Docker", preparo_docker.docker_instalado),
    ("docker_ligado", "Ligar o Docker", preparo_docker.docker_ligado),
    ("evolution_preparada", "Preparar a Evolution", preparo_evolution.evolution_preparada),
    ("evolution_no_ar", "Ligar a Evolution", preparo_evolution.evolution_no_ar),
    ("servico_ligado", "Ligar o serviço de Vendas", preparo_evolution.servico_ligado),
)
ARQUIVO_ESTADO = "preparo.json"
ARQUIVO_LOG = "preparo.log"
ARQUIVO_TRAVA = "preparo.trava"
LOG_SERVICO = "servico.log"
LOG_MAXIMO = 2 * 1024 * 1024
PAINEL = "http://127.0.0.1:8787"
PORTA_SERVICO = evolution_local.PORTA_SERVICO
PORTA_EVOLUTION = evolution_local.PORTA_EVOLUTION
ESPERA_INICIAR = 15


def agora():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def caminhos(pasta_dados):
    return {nome: os.path.join(pasta_dados, arquivo) for nome, arquivo in
            (("estado", ARQUIVO_ESTADO), ("log", ARQUIVO_LOG), ("servico", LOG_SERVICO))}


def segredos(pasta_dados):
    """Chave da API e senha do Postgres do .env gerado (para mascarar), ou [] sem .env."""
    try:
        valores = evolution_local._ler_env(evolution_local.caminho_env(pasta_dados)) or {}
    except (OSError, UnicodeDecodeError):
        return []
    return [valores.get("AUTHENTICATION_API_KEY"), valores.get("POSTGRES_PASSWORD")]


def ler_estado(pasta_dados, sistema=None):
    """Estado do último preparo, ou None. "rodando" com o processo morto vira "interrompido"."""
    try:
        with open(caminhos(pasta_dados)["estado"], encoding="utf-8") as f:
            estado = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(estado, dict):
        return None
    if estado.get("estado") == "rodando" and not (sistema or Sistema()).pid_vivo(estado.get("pid")):
        estado["estado"] = "interrompido"
        for passo in estado.get("passos") or []:
            if passo.get("estado") == "rodando":
                passo.update(estado="falhou", mensagem="O preparo parou no meio deste passo (o processo saiu). "
                                                       "Clique de novo para continuar daqui.")
    return estado


class Execucao:
    """Um preparo: estado, log e o contexto que os passos usam (sistema, pasta de dados, portas, dados)."""

    def __init__(self, raiz, base=None, painel=PAINEL, porta=None, porta_evolution=PORTA_EVOLUTION, sistema=None,
                 avisar=print):
        self.raiz = os.path.realpath(raiz)
        if not os.path.isdir(self.raiz):
            raise ValueError("a raiz do projeto %s não existe" % self.raiz)
        self.base, self.painel, self.porta_evolution = base, painel, porta_evolution
        self.porta_pedida = porta
        self.sistema = sistema or Sistema()
        self.avisar = avisar
        self.pasta_dados = pasta.pasta_de_dados(self.raiz, base)
        arquivos = caminhos(self.pasta_dados)
        self.caminho_estado, self.caminho_log = arquivos["estado"], arquivos["log"]
        self.caminho_log_servico = arquivos["servico"]
        anterior = ler_estado(self.pasta_dados, self.sistema) or {}
        self.portas = dict(anterior.get("portas") or {})
        self.dados = {}
        self.atual = None
        self.estado = {"id": secrets.token_hex(6), "pid": os.getpid(), "estado": "rodando", "inicio": agora(),
                       "atualizado": agora(), "fim": None, "log": self.caminho_log, "portas": self.portas,
                       "passos": [{"nome": n, "titulo": t, "estado": "pendente", "mensagem": None, "comando": None,
                                   "detalhe": None} for n, t, _ in PASSOS]}

    def porta_servico(self):
        return self.porta_pedida or self.portas.get("servico") or PORTA_SERVICO

    def _limpo(self, texto):
        return mascarar(texto, segredos(self.pasta_dados))

    def gravar(self):
        self.estado["atualizado"] = agora()
        travas.gravar_segredo(self.caminho_estado, self._limpo(json.dumps(self.estado, ensure_ascii=False,
                                                                           indent=1)))

    def registrar(self, texto):
        """Linha(s) no log do preparo (0600, mascarado). Nunca no estado nem na tela inteira."""
        if not texto:
            return
        fd = os.open(self.caminho_log, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, ("%s %s\n" % (agora(), self._limpo(texto).rstrip())).encode("utf-8"))
        finally:
            os.close(fd)

    def progresso(self, detalhe):
        if self.atual is not None:
            self.atual["detalhe"] = self._limpo(detalhe)
            self.gravar()
        self.avisar(self._limpo("  ... %s" % detalhe), flush=True)

    def _girar_log(self):
        try:
            if os.path.getsize(self.caminho_log) > LOG_MAXIMO:
                travas.substituir(self.caminho_log, self.caminho_log + ".1")
        except OSError:
            pass

    def rodar(self):
        """Roda os passos em ordem; para no primeiro que não ficou pronto. Devolve o estado final."""
        self._girar_log()
        pasta.arquivo_privado(self.caminho_log)
        self.gravar()
        self.registrar("preparo %s começou (pid %d)" % (self.estado["id"], os.getpid()))
        final = "feito"
        for (nome, titulo, passo), registro in zip(PASSOS, self.estado["passos"]):
            self.atual = registro
            registro["estado"] = "rodando"
            self.gravar()
            self.avisar("%s..." % titulo, flush=True)
            try:
                r = passo(self)
            except Exception as e:  # um erro inesperado vira falha do passo, nunca um preparo "rodando" para sempre
                r = falhou("Erro inesperado neste passo.", ("%s: %s" % (type(e).__name__, e))[:300])
            registro.update({k: self._limpo(v) if isinstance(v, str) else v for k, v in r.items()})
            self.registrar("%s: %s %s" % (nome, registro["estado"], registro["detalhe"] or ""))
            self.avisar("  %s: %s" % (registro["estado"], registro["mensagem"]), flush=True)
            if registro.get("comando"):
                self.avisar("  comando: %s" % registro["comando"], flush=True)
            if r["estado"] != "feito":
                final = r["estado"]
                break
        self.atual = None
        self.estado.update(estado=final, fim=agora())
        self.gravar()
        self.registrar("preparo %s terminou: %s" % (self.estado["id"], final))
        return self.estado


def rodar(args, sistema=None, avisar=print):
    """Roda em primeiro plano. 0 = tudo pronto; 1 = parou num passo; 2 = argumento ou pasta recusada; 3 = já roda."""
    try:
        ex = Execucao(args.projeto, args.base, args.painel, args.porta, args.porta_evolution, sistema, avisar)
    except (ValueError, OSError, pasta.PastaRecusada) as e:
        avisar("vendas: não preparei: %s" % e, file=sys.stderr)
        return 2
    trava = travas.TravaDoProcesso(ex.pasta_dados, ARQUIVO_TRAVA)
    try:
        trava.pegar()
    except travas.TravaOcupada:
        avisar("vendas: já há um preparo rodando para este projeto; acompanhe com: preparo.py estado",
               file=sys.stderr)
        return 3
    try:
        return 0 if ex.rodar()["estado"] == "feito" else 1
    finally:
        trava.soltar()


def iniciar(args, sistema=None):
    """Começa o preparo destacado e volta logo com o estado. Se um preparo vivo já roda, devolve o dele."""
    sistema = sistema or Sistema()
    raiz = os.path.realpath(args.projeto)
    if not os.path.isdir(raiz):
        raise ValueError("a raiz do projeto %s não existe" % raiz)
    pasta_dados = pasta.pasta_de_dados(raiz, args.base)
    antes = ler_estado(pasta_dados, sistema)
    if antes and antes.get("estado") == "rodando":
        return antes
    argv = [sys.executable, "-B", os.path.abspath(__file__), "rodar", "--projeto", raiz, "--painel", args.painel,
            "--porta-evolution", str(args.porta_evolution)]
    if args.porta:
        argv += ["--porta", str(args.porta)]
    if args.base:
        argv += ["--base", args.base]
    processo = sistema.soltar(argv, caminhos(pasta_dados)["log"])
    id_antes = (antes or {}).get("id")
    inicio = sistema.relogio()
    while sistema.relogio() - inicio < ESPERA_INICIAR:
        atual = ler_estado(pasta_dados, sistema)
        if atual and atual.get("id") != id_antes:
            return atual   # o nosso, ou o de um `iniciar` que ganhou a corrida pela trava
        if processo.poll() not in (None, 3):
            break
        sistema.dormir(0.2)
    atual = ler_estado(pasta_dados, sistema)
    if atual and atual.get("id") != id_antes:
        return atual
    return {"estado": "falhou", "mensagem": "O preparo não começou; veja o log.", "log": caminhos(pasta_dados)["log"]}


def estado(args, sistema=None):
    raiz = os.path.realpath(args.projeto)
    return ler_estado(pasta.caminho_da_pasta(raiz, args.base), sistema) or {"estado": "nunca_rodou"}


def argumentos(argv):
    p = argparse.ArgumentParser(prog="preparo.py", description="Prepara Docker, Evolution e o serviço de Vendas.")
    sub = p.add_subparsers(dest="comando", required=True)
    for nome, ajuda in (("rodar", "roda os passos aqui, mostrando cada um"),
                        ("iniciar", "começa o preparo destacado e volta na hora"),
                        ("estado", "mostra o estado do último preparo em JSON")):
        s = sub.add_parser(nome, help=ajuda)
        s.add_argument("--projeto", required=True, help="raiz do projeto")
        s.add_argument("--painel", default=PAINEL, help="origem exata do painel (esquema://host:porta)")
        s.add_argument("--porta", type=int, default=None, help="porta do serviço de Vendas (padrão %d)"
                       % PORTA_SERVICO)
        s.add_argument("--porta-evolution", type=int, default=PORTA_EVOLUTION, help="porta da Evolution em 127.0.0.1")
        s.add_argument("--base", default=None, help="pasta base dos dados (só para testes)")
    return p.parse_args(argv)


def main(argv, sistema=None, avisar=print):
    args = argumentos(argv)
    for p in (args.porta, args.porta_evolution):
        if p is not None and not 1024 <= p <= 65535:
            avisar("vendas: porta inválida: %d (use 1024 a 65535)" % p, file=sys.stderr)
            return 2
    if args.comando == "rodar":
        return rodar(args, sistema, avisar)
    try:
        resposta = iniciar(args, sistema) if args.comando == "iniciar" else estado(args, sistema)
    except (ValueError, OSError, pasta.PastaRecusada) as e:
        avisar("vendas: não preparei: %s" % e, file=sys.stderr)
        return 2
    avisar(json.dumps(resposta, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
