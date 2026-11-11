"""Campo `sandbox` e `env` da ação: o que eles viram no `--settings` da sessão.

`"sandbox": true` liga o sandbox do Claude Code (só shell; nomes das chaves conferidos em
code.claude.com/docs, settings-reference): sem rede nenhuma, sem rodar fora do sandbox, falha
se o sandbox não subir. O Write/Edit fica preso às pastas de trabalho e a sessão dispara com
cwd = pasta de trabalho (lancador). Como o sandbox não cobre ferramenta do próprio Claude,
nega também WebFetch, WebSearch e todo MCP, e a leitura de arquivo de segredo do projeto.
`"sandbox": {"rede_local": true}` faz o mesmo e liga `network.allowLocalBinding` (só macOS; no
Linux não muda nada): o comando pode escutar e falar com QUALQUER porta de localhost desta máquina,
não só a dele (o render do hyperframes sobe um servidor local). A rede de fora continua fechada.
`"env"`: variáveis da sessão (texto curto); as que mexem no Claude ou no carregador são recusadas.
Python 3.9, só biblioteca padrão.
"""
import re

NEGAR = ["WebFetch", "WebSearch", "mcp__*"]
SEGREDOS = (".env*", "*.pem", "*.key")
DONO = ("estudio-dono.json", "aprovados")  # em <dados>: só o servidor grava
RE_ENV = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
ENV_PROIBIDO = re.compile(r"^(CLAUDE|ANTHROPIC|LD_|DYLD_)|^(PATH|HOME|TMPDIR|SHELL|NODE_OPTIONS|BASH_ENV|ENV)$")
MAX_ENV, MAX_VALOR = 20, 200


def validar(a):
    """{"sandbox": bool, "_env": {..}} (+ "_rede_local": True) ou ValueError."""
    sb, extra = a.get("sandbox", False), {}
    if isinstance(sb, dict) and list(sb) == ["rede_local"] and isinstance(sb["rede_local"], bool):
        sb, extra = True, ({"_rede_local": True} if sb["rede_local"] else {})
    if not isinstance(sb, bool):
        raise ValueError('sandbox precisa ser true, false ou {"rede_local": true/false}')
    env = a.get("env", {})
    if not isinstance(env, dict) or len(env) > MAX_ENV:
        raise ValueError("env precisa ser um objeto com até %d variáveis" % MAX_ENV)
    for k, v in env.items():
        if not RE_ENV.match(k) or ENV_PROIBIDO.search(k):
            raise ValueError("env: nome de variável não aceito: %s" % k[:40])
        if not isinstance(v, str) or len(v) > MAX_VALOR or re.search(r"[\x00-\x1f\x7f]", v):
            raise ValueError("env: valor de %s precisa ser texto curto numa linha" % k)
    return dict({"sandbox": sb, "_env": dict(env)}, **extra)


def _barra(p):
    return p.replace("\\", "/").rstrip("/")


def bloco(acao, workspace, dados_dir):
    """(chaves de topo do settings, regras extras de permissions.deny, chaves extras de permissions)."""
    topo, negar, perm = {}, [], {}
    if acao.get("_env"):
        topo["env"] = dict(acao["_env"])
    if not acao.get("sandbox"):
        return topo, negar, perm
    from trabalho import caminho_de_regra  # aqui dentro: trabalho importa o catálogo, que importa este
    ws, dados = _barra(workspace or ""), _barra(dados_dir or "")
    ler = [ws + "/" + x for x in SEGREDOS] + [ws + "/**/" + x for x in SEGREDOS] if ws else []
    fs = {"denyRead": ler}
    if dados:
        fs["denyWrite"] = [dados + "/" + x for x in DONO]
    topo["sandbox"] = {"enabled": True, "failIfUnavailable": True, "allowUnsandboxedCommands": False,
                       "network": {"strictAllowlist": True, "allowedDomains": []}, "filesystem": fs}
    if acao.get("_rede_local"):
        topo["sandbox"]["network"]["allowLocalBinding"] = True
    # o padrão "worktree" trava Write/Edit até EnterWorktree, que o bloqueio abaixo tira da sessão
    topo["worktree"] = {"bgIsolation": "none"}
    negar = list(NEGAR) + (["Read(%s/**/%s)" % (caminho_de_regra(ws), x) for x in SEGREDOS] if ws else [])
    perm["blockWritesOutsideWorkingDirectories"] = True
    return topo, negar, perm
