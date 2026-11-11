"""Máscara de segredos e dados pessoais para textos que saem do servidor.

`mascarar(texto)` é idempotente e nunca levanta: em qualquer erro devolve um
texto fixo, nunca o original. Python 3.9, só biblioteca padrão.
"""
import re

OCULTO = "[texto ocultado]"
# valor: entre aspas até a aspa de fechamento (aceita espaço, vírgula etc.); sem aspas até espaço/aspa
_NOME_VAL = r"(\s*[\"']?\s*[=:]\s*)(\"[^\"\n]*\"?|'[^'\n]*'?|[^\s\"']+)"


def _nome_valor(m):
    v = m.group(3)
    q = v[0] if v[0] in "\"'" else ""
    return m.group(1) + m.group(2) + q + "***" + (q if q and len(v) > 1 and v[-1] == q else "")


# Ordem importa: os específicos antes do genérico "chave=valor".
SEGREDOS = [
    # Authorization: [esquema] credencial inteira (Digest leva espaços e vírgulas: vai até o fim da linha)
    (re.compile(r"(?i)\b((?:proxy-)?authorization)([\"']?\s*[=:]\s*[\"']?)(?:digest\s+[^\n]*|(?:(?:basic|bearer|token)\s*)?[^\s\"',;&]+)"),
     r"\1\2***"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=\-]{6,}"), "Bearer ***"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(-----END [A-Z ]*PRIVATE KEY-----|$)"), "***chave privada***"),
    (re.compile(r"(?i)(aws_secret_access_key[\s\"':=]+)[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])"), r"\1***"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"), "sk-***"),
    (re.compile(r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{16,}"), r"\1_***"),
    (re.compile(r"\bsbp_[A-Za-z0-9]{20,}"), "sbp_***"),
    (re.compile(r"\bEAA[A-Za-z0-9]{17,}"), "EAA***"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"), "xox-***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA***"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "AIza***"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}"), "***jwt***"),
    # nome terminado em _KEY/_TOKEN/_SECRET/_PASSWORD (ou parecido): NAME=v, NAME: v, "NAME": "v"
    # sem prefixo no nome (o prefixo fica no texto) e sufixo limitado: tempo linear
    (re.compile(r"(?i)((?:senha|password|passwd|pwd|secret|segredo|token|api[_\-]?key|apikey"
                r"|access[_\-]?key|chave|private[_\-]?key|client[_\-]?secret|_key)[a-z0-9_\-]{0,40})"
                + _NOME_VAL), _nome_valor),
    (re.compile(r"(?i)(://[^/\s:@]*:)[^@\s/]+@"), r"\1***@"),
    # curl: -u user:pass / --user user:pass (uid:gid numérico do docker fica)
    (re.compile(r"(?<![\w-])(-u(?=[\w.@+]+:)|-u\s+|--user\s+|--user=)(?!\d+:\d+(?:\s|$))\S*:\S*"), r"\1***"),
    (re.compile(r"(?<![\w-])(--(?:password|passwd|senha))(\s+)(?:'[^']*'|\"[^\"]*\"|\S+)"), r"\1\2***"),
    # -p só com valor entre aspas, ou depois de mysql/sshpass (em 'uv run -p 3.13' é versão)
    (re.compile(r"(?<![\w-])-p(\s*)(?:'[^']*'|\"[^\"]*\")"), "-p ***"),
    (re.compile(r"(\b(?:mysql\w*|sshpass)\b[^\n|;&]*?\s)-p\s*(?!-)\S+"), r"\1-p ***"),
]
RE_EMAIL = re.compile(r"(?<![\w.+\-])[\w.+\-]+@([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+)")
# Celular BR colado (11 dígitos, 55 opcional; fixo colado de 10 dígitos colide com epoch) ou formatado com parênteses/hífen.
RE_TEL_COLADO = re.compile(r"(?<![\w.:/+\-])\+?(?<!\d)(?:55)?\d{2}9\d{8}(?![\w\-])")
RE_TEL_FORMATADO = re.compile(r"(?<![\w.:/\-])(?:\+?55[\s\-]?)?0?(?:\(\d{2}\)|\d{2})[\s\-]?9?\d{4}-(\d{4})(?![\w\-])")
# Só com espaços: "19 99999 8888", "19 3456 7890", "55 19 999998888".
RE_TEL_ESPACO = re.compile(r"(?<![\w.:/+\-])\+?(?:55\s)?0?\d{2}\s(?:9\d{8}|9?\d{4}\s\d{4})(?![\w\-])")
RE_HEX = re.compile(r"(?<![0-9A-Za-z_])(?<!commit )[0-9a-fA-F]{32,}(?![0-9A-Za-z_])")
# Sequência longa com letra maiúscula, minúscula e dígito: cara de chave (hash hex puro cai em RE_HEX).
RE_LONGO = re.compile(r"[A-Za-z0-9_\-+/]{40,}")


def _longo(m):
    s = m.group(0)
    tem = re.search(r"[A-Z]", s) and re.search(r"[a-z]", s) and re.search(r"\d", s)
    return "***" if tem and "/" not in s.strip("/") else s


def _tel(m):
    return "***" + re.sub(r"\D", "", m.group(0))[-4:]


def _uma_passada(texto):
    for regex, troca in SEGREDOS:
        texto = regex.sub(troca, texto)
    texto = RE_EMAIL.sub(r"***@\1", texto)
    texto = RE_HEX.sub("***", texto)
    texto = RE_TEL_FORMATADO.sub(_tel, texto)
    texto = RE_TEL_ESPACO.sub(_tel, texto)
    texto = RE_TEL_COLADO.sub(_tel, texto)
    return RE_LONGO.sub(_longo, texto)


def mascarar(texto):
    if not texto:
        return ""
    try:
        texto = str(texto)
        for _ in range(3):  # repete até estabilizar: uma regra pode expor o que outra mascara
            novo = _uma_passada(texto)
            if novo == texto:
                break
            texto = novo
        return texto
    except Exception:  # nunca devolve o original
        return OCULTO


def primeira_linha(texto, limite=200):
    """1ª linha não vazia (sem cor ANSI), mascarada e curta: a causa de um erro do CLI sem vazar segredo."""
    linhas = [x.strip() for x in re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", texto or "").splitlines() if x.strip()]
    return mascarar(linhas[0])[:limite] if linhas else "sem saída"
