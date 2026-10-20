"""tune-up: Supabase de produção, Postgres remoto, SQL por statement e evento prod."""
import re
from .mensagens import msg
from .sessao import decisao_pre, ler_sessao


SUPABASE_REMOTO = {("db", "push"), ("db", "reset"), ("db", "query"), ("db", "execute"),
                 ("migration", "up"), ("migration", "repair"), ("migration", "squash"),
                 ("functions", "deploy"), ("functions", "delete"), ("secrets", "set"),
                 ("secrets", "unset")}
SUPABASE_FLAG_VALOR = {"--workdir", "--project-ref", "-o", "--output", "--profile", "--network-id",
                       "--dns-resolver"}
RE_PG_URL = re.compile(r"postgres(ql)?://", re.I)
RE_PG_VAR = re.compile(r"\$\{?(DATABASE_URL|SUPABASE_DB_URL|PG\w+)\b")
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1", ""}


def supabase_remoto(args):
    """args = tokens depois de `supabase`. Devolve o rótulo se mexe em prod/remoto."""
    a, pular = [], False
    for t in args:
        if pular:
            pular = False
        elif t in SUPABASE_FLAG_VALOR:
            pular = True
        elif not t.startswith("-"):
            a.append(t)
    if any(t == "--linked" or t == "--db-url" or t.startswith("--db-url=") for t in args):
        return "supabase --linked/--db-url"
    if tuple(a[:2]) in SUPABASE_REMOTO:
        return "supabase " + " ".join(a[:2])
    if tuple(a[:2]) == ("db", "dump") and "--data-only" in args:
        return "supabase db dump --data-only"
    return None


def pg_remoto(args):
    """psql/pg_dump/pg_restore apontando para URL, variável de conexão ou host não-local."""
    for j, t in enumerate(args):
        if RE_PG_URL.search(t) or RE_PG_VAR.search(t):
            return True
        host = None
        if t in ("-h", "--host") and j + 1 < len(args):
            host = args[j + 1]
        elif t.startswith("--host="):
            host = t.split("=", 1)[1]
        elif t.startswith("-h") and len(t) > 2 and not t.startswith("--"):
            host = t[2:]
        if host is not None and host not in HOSTS_LOCAIS and not host.startswith("/"):
            return True
    return False


RE_PG_ATRIB = re.compile(r"(?:^|[\s;&|(])(?:export\s+|declare\s+-x\s+)?(PG[A-Z_]+|DATABASE_URL|SUPABASE_DB_URL)=")
RE_CONNINFO = re.compile(r"(?:^|[\s\"'])(host|hostaddr|service)\s*=\s*'?([^\s'\"]*)")


def pg_remoto_no_texto(texto):
    """`PG*=`/`DATABASE_URL=` assigned in the command (prefix or `export`), or a conninfo with a
    non-local `host=` or any `service=`: the connection target is not visibly local."""
    if RE_PG_ATRIB.search(texto):
        return True
    for chave, valor in RE_CONNINFO.findall(texto):
        if chave == "service" or (valor not in HOSTS_LOCAIS and not valor.startswith("/")):
            return True
    return False


# ---------------------------------------------------------------- prod

LEITURA_MCP = {"search_docs", "generate_typescript_types"}
SQL_MAX = 100 * 1024
RE_DOLAR = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)?\$")
SQL_LEITURA_INICIO = {"select", "with", "show", "explain", "table", "values"}
SQL_FUNC_LEITURA = {
    "count", "sum", "avg", "min", "max", "array_agg", "string_agg", "json_agg", "jsonb_agg",
    "bool_and", "bool_or", "coalesce", "nullif", "greatest", "least", "lower", "upper", "trim",
    "length", "substr", "substring", "split_part", "replace", "concat", "format", "to_char",
    "to_jsonb", "to_json", "jsonb_build_object", "json_build_object", "jsonb_array_length",
    "jsonb_typeof", "date_trunc", "extract", "now", "age", "current_setting", "pg_relation_size",
    "row_number", "rank", "dense_rank", "lag", "lead", "exists", "unnest", "generate_series",
    "gen_random_uuid", "md5", "abs", "round", "floor", "ceil", "cast",
    "jsonb_object_keys", "row_to_json", "to_timestamp", "to_date", "to_number", "timezone",
    "char_length", "octet_length", "position", "left", "right", "lpad", "rpad", "initcap",
    "string_to_array", "array_length", "array_to_string", "cardinality", "version", "date_part",
    "make_interval", "make_date"}
SQL_FUNC_AUTH = {"auth.uid", "auth.role", "auth.jwt"}
RE_FUNC_LEITURA = re.compile(r"pg_get_\w+|pg_\w*size\w*|has_\w+_privilege|"
                             r"jsonb?_array_elements(_text)?|jsonb_each(_text)?|jsonb_extract_path(_text)?|"
                             r"jsonb_path_query\w*|regexp_\w+")
# palavras do SQL que vêm antes de "(" sem ser chamada de função
SQL_PALAVRAS = {
    "in", "exists", "as", "from", "over", "values", "filter", "any", "all", "some", "not", "and",
    "or", "select", "where", "on", "join", "using", "when", "then", "else", "distinct", "by",
    "lateral", "array", "row", "group", "is", "like", "ilike", "between", "case", "with", "union",
    "intersect", "except", "having", "limit", "offset", "recursive", "materialized", "cube",
    "rollup", "grouping", "sets", "numeric", "decimal", "varchar", "char", "character", "varying",
    "timestamp", "timestamptz", "time", "interval", "bit", "float", "within", "partition", "order",
    "end", "asc", "desc", "nulls", "first", "last", "only", "inner", "left", "right", "full",
    "outer", "cross", "natural"}
RE_SQL_FUNC = re.compile(r"(?<![\w.$])([a-z_][\w.]*)\s*\(")
RE_SQL_FOR = re.compile(r"\bfor\s+(update|share|no\s+key\s+update|key\s+share)\b")
RE_SQL_DML = re.compile(r"\b(insert|update|delete|merge)\b")
RE_EXPLAIN = re.compile(r"explain\b((?:\s*\([^)]*\)|\s+(?:analyze|analyse|verbose|costs|buffers|"
                        r"settings|wal|timing|summary))*)")


def sql_statements(sql):
    """Uma passada: tira strings ('', E'', $tag$), identificadores com aspas e comentários
    (-- e /* */ aninhado); separa por ';' fora deles. Devolve statements em minúsculas."""
    out, atual = [], []
    i, n = 0, len(sql)
    while i < n:
        c = sql[i]
        if c == "-" and sql.startswith("--", i):
            j = sql.find("\n", i)
            i = n if j < 0 else j
            atual.append(" ")
        elif c == "/" and sql.startswith("/*", i):
            prof, i = 1, i + 2
            while i < n and prof:
                if sql.startswith("/*", i):
                    prof, i = prof + 1, i + 2
                elif sql.startswith("*/", i):
                    prof, i = prof - 1, i + 2
                else:
                    i += 1
            atual.append(" ")
        elif c == "'":
            escape = i > 0 and sql[i - 1] in "eE" and (i < 2 or not (sql[i - 2].isalnum() or sql[i - 2] in "_$"))
            i += 1
            while i < n:
                if escape and sql[i] == "\\":
                    i += 2
                elif sql[i] == "'":
                    if i + 1 < n and sql[i + 1] == "'":
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            if escape and atual:
                atual.pop()  # o E do E'...'
            atual.append(" '' ")
        elif c == '"':
            j = i + 1
            while j < n:
                if sql[j] == '"':
                    if j + 1 < n and sql[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
            atual.append(" x ")
        elif c == "$" and not (i > 0 and (sql[i - 1].isalnum() or sql[i - 1] == "_")):
            m = RE_DOLAR.match(sql, i)
            if m:
                j = sql.find(m.group(0), m.end())
                i = n if j < 0 else j + len(m.group(0))
                atual.append(" '' ")
            else:
                atual.append(c)
                i += 1
        elif c == ";":
            out.append("".join(atual))
            atual = []
            i += 1
        else:
            atual.append(c)
            i += 1
    out.append("".join(atual))
    return [x.strip().lower() for x in out if x.strip()]


def funcao_de_leitura(nome):
    if nome in SQL_FUNC_AUTH:
        return True
    if "." in nome:
        schema, nome = nome.rsplit(".", 1)
        if schema not in ("pg_catalog", "information_schema"):
            return False
    return nome in SQL_FUNC_LEITURA or bool(RE_FUNC_LEITURA.fullmatch(nome))


def select_escreve(st):
    if re.search(r"\binto\b", st) or RE_SQL_FOR.search(st):
        return True
    for m in RE_SQL_FUNC.finditer(st):
        nome = m.group(1)
        if nome in SQL_PALAVRAS:
            continue
        if not funcao_de_leitura(nome):
            return True
    return False


def statement_escreve(st):
    st = st.lstrip("( \t\r\n")
    m = re.match(r"[a-z_]+", st)
    if not m:
        return True
    w = m.group(0)
    if w not in SQL_LEITURA_INICIO:
        return True
    if w == "explain":
        e = RE_EXPLAIN.match(st)
        if e and "analy" in e.group(1):
            return statement_escreve(st[e.end():])
        return False
    if w == "show":
        return False
    if w == "with" and RE_SQL_DML.search(st):
        return True
    return select_escreve(st)


def sql_escreve(sql):
    if len(sql) > SQL_MAX:
        return True
    return any(statement_escreve(st) for st in sql_statements(sql))


def ev_prod(d, cfg):
    if cfg.get("supabase_guard") is False:  # only from a trusted config (AFROUXAM)
        return None
    nome = str(d.get("tool_name") or "")
    curto = nome.rsplit("__", 1)[-1]
    ti = d.get("tool_input") or {}
    if curto == "execute_sql":
        sql = ti.get("query") or ti.get("sql") or ""
        if not sql_escreve(str(sql)):
            return None
        sess = ler_sessao(d.get("session_id"))
        pid = d.get("prompt_id")
        if pid and sess.get("auth_prompt_id") == pid:
            return None
        return decisao_pre("perguntar", msg("prod", curto))
    if curto.startswith("list_") or curto.startswith("get_") or curto in LEITURA_MCP:
        return None
    return decisao_pre("perguntar", msg("prod_mcp", curto))
