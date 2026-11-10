"""Banco SQLite do serviço (WAL, chaves estrangeiras ligadas, espera de trava), migrado por PRAGMA user_version.
Toda escrita confere as linhas afetadas: escrita sem efeito vira erro, nunca sucesso falso."""
import datetime
import os
import re
import sqlite3

from servico import pasta, telefone

ARQUIVO = "vendas.db"
ESPERA_MS = 5000
ESTADOS_ENVIO = ("pendente", "enviado", "falhou", "negado", "incerto")

MIGRACOES = [
    # 1: esquema inicial
    [
        """CREATE TABLE contatos (
            id INTEGER PRIMARY KEY,
            telefone TEXT NOT NULL UNIQUE,
            telefone_alt TEXT UNIQUE,
            nome TEXT,
            origem TEXT,
            base_legal TEXT,
            optout_em TEXT,
            criado_em TEXT NOT NULL)""",
        """CREATE TABLE conversas (
            id INTEGER PRIMARY KEY,
            contato_id INTEGER NOT NULL UNIQUE REFERENCES contatos(id),
            modo TEXT NOT NULL DEFAULT 'ia' CHECK (modo IN ('ia', 'humano')),
            pausada_ate TEXT,
            estado TEXT,
            precisa_de_voce INTEGER NOT NULL DEFAULT 0 CHECK (precisa_de_voce IN (0, 1)),
            criado_em TEXT NOT NULL)""",
        """CREATE TABLE mensagens (
            id INTEGER PRIMARY KEY,
            conversa_id INTEGER NOT NULL REFERENCES conversas(id),
            id_externo TEXT UNIQUE,
            direcao TEXT NOT NULL CHECK (direcao IN ('entrada', 'saida')),
            tipo TEXT NOT NULL DEFAULT 'texto',
            texto TEXT,
            criado_em TEXT NOT NULL)""",
        """CREATE TABLE envios (
            id INTEGER PRIMARY KEY,
            chave_dedupe TEXT NOT NULL,
            contato_id INTEGER REFERENCES contatos(id),
            estado TEXT NOT NULL
                CHECK (estado IN ('pendente', 'enviado', 'falhou', 'negado', 'incerto')),
            origem TEXT NOT NULL,
            motivo TEXT,
            id_externo TEXT,
            criado_em TEXT NOT NULL)""",
        "CREATE UNIQUE INDEX envios_chave_dedupe ON envios(chave_dedupe) WHERE estado <> 'negado'",
        """CREATE TABLE campanhas (
            id INTEGER PRIMARY KEY,
            nome TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT 'rascunho',
            criado_em TEXT NOT NULL)""",
        """CREATE TABLE campanha_contatos (
            campanha_id INTEGER NOT NULL REFERENCES campanhas(id),
            contato_id INTEGER NOT NULL REFERENCES contatos(id),
            passo INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'pendente',
            PRIMARY KEY (campanha_id, contato_id))""",
        """CREATE TABLE eventos (
            id INTEGER PRIMARY KEY,
            tipo TEXT NOT NULL,
            dados TEXT,
            criado_em TEXT NOT NULL)""",
        "CREATE TABLE config (chave TEXT PRIMARY KEY, valor TEXT)",
        "CREATE TABLE batimento (id INTEGER PRIMARY KEY CHECK (id = 1), pid INTEGER, em TEXT NOT NULL)",
    ],
    # 2: o portão guarda destino e conteúdo do envio (para o dono reenviar a MESMA linha) e conta por tempo
    [
        "ALTER TABLE envios ADD COLUMN telefone TEXT",
        "ALTER TABLE envios ADD COLUMN tipo TEXT",
        "ALTER TABLE envios ADD COLUMN conteudo TEXT",
        "CREATE INDEX envios_criado_em ON envios(criado_em)",
    ],
]
VERSAO = len(MIGRACOES)
PARECE_SEGREDO = re.compile(r"chave|senha|token|segredo|secret|key|password", re.I)


class EscritaSemEfeito(RuntimeError):
    pass


def agora():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _exigir(cur, esperado=1):
    if cur.rowcount != esperado:
        raise EscritaSemEfeito("esperava %d linha(s) afetada(s), vieram %d" % (esperado, cur.rowcount))


def _unico(erro):
    return isinstance(erro, sqlite3.IntegrityError) and "UNIQUE" in str(erro)


def abrir(pasta_dados):
    """Abre (e migra) o banco da pasta de dados. A pasta já deve ter passado por pasta.pasta_de_dados."""
    caminho = pasta.arquivo_privado(os.path.join(pasta_dados, ARQUIVO))
    con = sqlite3.connect(caminho, timeout=ESPERA_MS / 1000.0, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = %d" % ESPERA_MS)
    modo = con.execute("PRAGMA journal_mode = WAL").fetchone()[0]
    if modo.lower() != "wal":
        con.close()
        raise RuntimeError("o SQLite não aceitou o modo WAL (veio %r)" % modo)
    con.execute("PRAGMA foreign_keys = ON")
    migrar(con)  # -wal e -shm herdam o modo 0600 do arquivo do banco (o SQLite copia)
    return con


def migrar(con):
    """Aplica as migrações que faltam, cada uma numa transação com a versão; rodar de novo não muda nada."""
    while True:
        con.execute("BEGIN IMMEDIATE")
        try:
            versao = con.execute("PRAGMA user_version").fetchone()[0]
            if versao > VERSAO:
                raise RuntimeError("banco na versão %d, este serviço só conhece até %d" % (versao, VERSAO))
            if versao == VERSAO:
                con.execute("COMMIT")
                return versao
            for comando in MIGRACOES[versao]:
                con.execute(comando)
            con.execute("PRAGMA user_version = %d" % (versao + 1))
            con.execute("COMMIT")
        except BaseException:
            con.execute("ROLLBACK")
            raise


def buscar_contato(con, numero):
    """Contato por qualquer variante do 9º dígito, ou None."""
    v = telefone.variantes(numero)
    marcas = ",".join("?" * len(v))
    return con.execute("SELECT * FROM contatos WHERE telefone IN (%s) OR telefone_alt IN (%s)" % (marcas, marcas),
                       v + v).fetchone()


def salvar_contato(con, numero, nome=None, origem=None, base_legal=None):
    """Cria o contato (ou devolve o que já existe por qualquer variante). Devolve o id."""
    existente = buscar_contato(con, numero)
    if existente is not None:
        return existente["id"]
    v = telefone.variantes(numero)
    cur = con.execute("INSERT INTO contatos (telefone, telefone_alt, nome, origem, base_legal, criado_em) "
                      "VALUES (?, ?, ?, ?, ?, ?)", (v[0], v[1] if len(v) > 1 else None, nome, origem, base_legal,
                                                    agora()))
    _exigir(cur)
    return cur.lastrowid


def marcar_optout(con, numero, quando=None):
    """Marca a saída do contato (cria o contato se não existir). Mantém a 1ª data de saída."""
    contato_id = salvar_contato(con, numero)
    cur = con.execute("UPDATE contatos SET optout_em = COALESCE(optout_em, ?) WHERE id = ?",
                      (quando or agora(), contato_id))
    _exigir(cur)
    return contato_id


def em_optout(con, numero):
    contato = buscar_contato(con, numero)
    return contato is not None and contato["optout_em"] is not None


def abrir_conversa(con, contato_id):
    """Conversa única do contato; cria se faltar. Devolve o id."""
    linha = con.execute("SELECT id FROM conversas WHERE contato_id = ?", (contato_id,)).fetchone()
    if linha is not None:
        return linha["id"]
    cur = con.execute("INSERT INTO conversas (contato_id, criado_em) VALUES (?, ?)", (contato_id, agora()))
    _exigir(cur)
    return cur.lastrowid


def registrar_mensagem(con, conversa_id, direcao, texto, id_externo=None, tipo="texto"):
    """Grava a mensagem. Devolve o id, ou None se o id_externo já existe (webhook repetido)."""
    try:
        cur = con.execute("INSERT INTO mensagens (conversa_id, id_externo, direcao, tipo, texto, criado_em) "
                          "VALUES (?, ?, ?, ?, ?, ?)", (conversa_id, id_externo, direcao, tipo, texto, agora()))
    except sqlite3.IntegrityError as erro:
        if _unico(erro):
            return None
        raise
    _exigir(cur)
    return cur.lastrowid


def registrar_envio(con, chave_dedupe, origem, estado="pendente", motivo=None, contato_id=None, telefone=None,
                    tipo=None, conteudo=None, quando=None):
    """Grava o envio. Devolve o id, ou None se a chave já está ocupada por um envio não negado.
    Um 'negado' nunca ocupa a chave (índice único parcial)."""
    if estado not in ESTADOS_ENVIO:
        raise ValueError("estado de envio inválido: %r" % estado)
    try:
        cur = con.execute("INSERT INTO envios (chave_dedupe, contato_id, estado, origem, motivo, telefone, tipo, "
                          "conteudo, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                          (chave_dedupe, contato_id, estado, origem, motivo, telefone, tipo, conteudo,
                           quando or agora()))
    except sqlite3.IntegrityError as erro:
        if _unico(erro):
            return None
        raise
    _exigir(cur)
    return cur.lastrowid


def mudar_envio(con, envio_id, estado, motivo=None, id_externo=None):
    if estado not in ESTADOS_ENVIO:
        raise ValueError("estado de envio inválido: %r" % estado)
    cur = con.execute("UPDATE envios SET estado = ?, motivo = COALESCE(?, motivo), "
                      "id_externo = COALESCE(?, id_externo) WHERE id = ?", (estado, motivo, id_externo, envio_id))
    _exigir(cur)


def registrar_evento(con, tipo, dados=None):
    cur = con.execute("INSERT INTO eventos (tipo, dados, criado_em) VALUES (?, ?, ?)", (tipo, dados, agora()))
    _exigir(cur)
    return cur.lastrowid


def ler_config(con, chave, padrao=None):
    linha = con.execute("SELECT valor FROM config WHERE chave = ?", (chave,)).fetchone()
    return padrao if linha is None else linha["valor"]


def gravar_config(con, chave, valor):
    """Config comum. Segredo NUNCA vai para o banco: nome com cara de segredo é recusado."""
    if PARECE_SEGREDO.search(chave):
        raise ValueError("config %r parece segredo; segredo não vai para o banco" % chave)
    cur = con.execute("INSERT INTO config (chave, valor) VALUES (?, ?) "
                      "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor", (chave, valor))
    _exigir(cur)


def somar_config(con, chave, n=1):
    """Soma n a um contador em config numa instrução só (sem ler e regravar). Devolve o valor novo."""
    if PARECE_SEGREDO.search(chave):
        raise ValueError("config %r parece segredo; segredo não vai para o banco" % chave)
    cur = con.execute("INSERT INTO config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE "
                      "SET valor = CAST(COALESCE(valor, '0') AS INTEGER) + ?", (chave, str(n), n))
    _exigir(cur)
    return int(ler_config(con, chave))


def bater(con, pid=None):
    """Batimento do serviço: uma linha só, atualizada a cada volta."""
    cur = con.execute("INSERT INTO batimento (id, pid, em) VALUES (1, ?, ?) "
                      "ON CONFLICT(id) DO UPDATE SET pid = excluded.pid, em = excluded.em",
                      (os.getpid() if pid is None else pid, agora()))
    _exigir(cur)


def parar_batimento(con, pid=None):
    """Apaga o batimento deste processo na saída limpa. Devolve quantas linhas saíram (0 se outro já bateu)."""
    cur = con.execute("DELETE FROM batimento WHERE id = 1 AND pid = ?", (os.getpid() if pid is None else pid,))
    return cur.rowcount
