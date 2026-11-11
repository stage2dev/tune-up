"""Evolution API local (Docker): prepara compose.yml e .env na pasta de dados EXTERNA do projeto. Nunca roda o Docker.

    python3 -B <plugin>/servico/evolution_local.py preparar --projeto <raiz> [--porta 8791] [--porta-evolution 8080]

Chave da API e senha do Postgres são geradas na hora (nunca a chave padrão pública); .env sai 0600 e não é
sobrescrito sem --refazer. O serviço lê a URL e a chave desse .env quando o ambiente não traz as variáveis."""
import os
import sys

if __name__ == "__main__":
    sys.path[0] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.dont_write_bytecode = True

import argparse  # noqa: E402
import secrets  # noqa: E402
import shlex  # noqa: E402

from servico import pasta  # noqa: E402
from servico.conectores.evolution import VAR_CHAVE, VAR_URL  # noqa: E402

MODELO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evolution", "compose.exemplo.yml")
SERVICO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "servico.py")
SUBPASTA = "evolution"
ARQUIVO_COMPOSE = "compose.yml"
ARQUIVO_ENV = ".env"
PORTA_SERVICO = 8791
PORTA_EVOLUTION = 8080


class JaPreparado(RuntimeError):
    pass


def pasta_evolution(pasta_dados):
    return os.path.join(pasta_dados, SUBPASTA)


def _texto_env(chave, senha, porta_servico, porta_evolution):
    return "\n".join([
        "# Evolution local do tune-up-vendas, gerado por evolution_local.py preparar. Segredo: não copie para o projeto.",
        "SERVER_TYPE=http",
        "SERVER_PORT=8080",
        "SERVER_URL=http://127.0.0.1:%d" % porta_evolution,
        "AUTHENTICATION_API_KEY=%s" % chave,
        "AUTHENTICATION_EXPOSE_IN_FETCH_INSTANCES=false",
        "POSTGRES_PASSWORD=%s" % senha,
        "DATABASE_PROVIDER=postgresql",
        "DATABASE_CONNECTION_URI=postgresql://evolution:%s@postgres:5432/evolution?schema=public" % senha,
        "DATABASE_CONNECTION_CLIENT_NAME=evolution",
        "CACHE_REDIS_ENABLED=true",
        "CACHE_REDIS_URI=redis://redis:6379/6",
        "CACHE_LOCAL_ENABLED=false",
        "TELEMETRY_ENABLED=false",
        "WEBHOOK_GLOBAL_ENABLED=false",
        "# webhook por instância (o serviço registra, com o segredo no header): "
        "http://host.docker.internal:%d/webhook/<instancia>" % porta_servico,
        ""])


def texto_compose(nome, porta_servico, porta_evolution):
    with open(MODELO, encoding="utf-8") as f:
        modelo = f.read()
    return (modelo.replace("__NOME__", nome).replace("__PORTA_SERVICO__", str(porta_servico))
            .replace("__PORTA_EVOLUTION__", str(porta_evolution)))


def _gravar(caminho, texto, exclusivo):
    """Grava em arquivo 0600. exclusivo: falha (JaPreparado) se já existe; senão troca o arquivo inteiro de uma vez."""
    alvo = caminho if exclusivo else caminho + ".novo"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    try:
        fd = os.open(alvo, flags, 0o600)
    except FileExistsError:
        if exclusivo:
            raise JaPreparado("%s já existe; use --refazer para gerar chave e senha novas" % caminho)
        os.remove(alvo)  # sobra de uma tentativa que caiu
        fd = os.open(alvo, flags, 0o600)
    try:
        os.write(fd, texto.encode("utf-8"))
    finally:
        os.close(fd)
    if not exclusivo:
        os.replace(alvo, caminho)
    pasta.arquivo_privado(caminho)
    return caminho


def preparar(raiz, base=None, porta_servico=PORTA_SERVICO, porta_evolution=PORTA_EVOLUTION, refazer=False):
    """Grava compose.yml e .env na pasta de dados externa. Devolve {"pasta", "compose", "env"}.
    Recusa (pasta.PastaRecusada) pasta dentro do projeto ou sincronizada; .env existente sem refazer = JaPreparado."""
    for p in (porta_servico, porta_evolution):
        if not 1024 <= p <= 65535:
            raise ValueError("porta inválida: %d (use 1024 a 65535)" % p)
    raiz = os.path.realpath(raiz)
    if not os.path.isdir(raiz):
        raise ValueError("a raiz do projeto %s não existe" % raiz)
    pasta_dados = pasta.pasta_de_dados(raiz, base=base)
    destino = pasta_evolution(pasta_dados)
    pasta.validar(destino, raiz)
    os.makedirs(destino, mode=0o700, exist_ok=True)
    if os.name != "nt":
        os.chmod(destino, 0o700)
    env, compose = os.path.join(destino, ARQUIVO_ENV), os.path.join(destino, ARQUIVO_COMPOSE)
    if os.path.exists(env) and not refazer:
        raise JaPreparado("%s já existe; use --refazer para gerar chave e senha novas" % env)
    nome = "tune-up-vendas-%s" % os.path.basename(pasta_dados).lower()
    _gravar(compose, texto_compose(nome, porta_servico, porta_evolution), exclusivo=False)  # sem segredo
    chave, senha = secrets.token_hex(32), secrets.token_hex(24)
    _gravar(env, _texto_env(chave, senha, porta_servico, porta_evolution), exclusivo=not refazer)
    return {"pasta": destino, "compose": compose, "env": env}


def ler_ambiente(pasta_dados):
    """{VAR_URL, VAR_CHAVE} lidos do .env gerado, ou {} se não há .env completo. Para o serviço, nunca para a tela."""
    caminho = os.path.join(pasta_evolution(pasta_dados), ARQUIVO_ENV)
    try:
        with open(caminho, encoding="utf-8") as f:
            linhas = f.read().splitlines()
    except FileNotFoundError:
        return {}
    valores = {}
    for linha in linhas:
        chave, igual, valor = linha.partition("=")
        if igual and not chave.startswith("#"):
            valores[chave.strip()] = valor.strip()
    url, chave = valores.get("SERVER_URL"), valores.get("AUTHENTICATION_API_KEY")
    return {VAR_URL: url, VAR_CHAVE: chave} if url and chave else {}


def argumentos(argv):
    p = argparse.ArgumentParser(prog="evolution_local.py", description="Evolution API local do tune-up-vendas.")
    sub = p.add_subparsers(dest="comando", required=True)
    prep = sub.add_parser("preparar", help="grava compose.yml e .env na pasta de dados externa (não roda o Docker)")
    prep.add_argument("--projeto", required=True, help="raiz do projeto")
    prep.add_argument("--porta", type=int, default=PORTA_SERVICO, help="porta do serviço de Vendas (webhook)")
    prep.add_argument("--porta-evolution", type=int, default=PORTA_EVOLUTION, help="porta da Evolution em 127.0.0.1")
    prep.add_argument("--refazer", action="store_true", help="gera chave e senha novas sobre um .env existente")
    prep.add_argument("--base", default=None, help="pasta base dos dados (só para testes)")
    return p.parse_args(argv)


def main(argv, avisar=print):
    args = argumentos(argv)
    try:
        feito = preparar(args.projeto, args.base, args.porta, args.porta_evolution, args.refazer)
    except (ValueError, pasta.PastaRecusada, JaPreparado) as e:
        avisar("vendas: não preparei: %s" % e, file=sys.stderr)
        return 2
    avisar("Pronto: compose.yml e .env (0600) em %s. Não copie esses arquivos para o projeto." % feito["pasta"])
    if args.refazer:
        avisar("Chave e senha novas: um Postgres já criado guarda a senha antiga; apague o volume dele antes de subir.")
    avisar("Para ligar a Evolution, rode num terminal (este comando não roda o Docker por você):")
    avisar("  docker compose -f %s up -d" % shlex.quote(feito["compose"]))
    avisar("Depois ligue o serviço de Vendas na mesma porta do webhook:")
    avisar("  python3 -B %s --projeto %s --porta %d" % (shlex.quote(SERVICO), shlex.quote(os.path.realpath(
        args.projeto)), args.porta))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
