"""Travas de verdade das sessões que o painel dispara (não só frase no prompt). O núcleo não conhece ferramenta de projeto nenhum: as travas vêm do
JSON da ação, em "negar" e "permitir": ["<regra de permissão>" | {regra do gancho}].
- Texto vira regra de permissão do Claude Code (`permissions.deny`/`.allow`), ex. "mcp__x__y", "Bash(rm *)".
- Objeto vira regra do gancho PreToolUse que roda ESTE arquivo e olha o conteúdo da chamada: {"ferramenta": regex (nome inteiro), "campo"?: campo da
  entrada, "entrada"?: regex nesse campo (ou na entrada inteira em JSON), "decisao"?: "deny" | "ask" (padrão deny), "motivo"?: texto}. Uma regra de
  "permitir" que casa cala o gancho (antes das de "negar"); a proteção fixa abaixo vale sempre.
Proteção fixa do núcleo (toda ação): mexer em .claude/settings*.json, .claude/hooks|skills|plugins, CLAUDE.md, .mcp.json, no painel.json, no núcleo ou
no pacote do painel (menos <pacote>/dados/) nega em ação de risco leitura/rascunho e pergunta em código/crédito. No Bash de leitura/rascunho, só verbo
de leitura conhecido pode citar essas árvores. Ação com Bash no `permitir`: comando composto, código inline, heredoc ou script é negado antes do
`permitir`. A ferramenta PowerShell (Windows) é negada sempre; no Windows, chamar cmd, PowerShell, WSL ou .bat/.cmd pelo Bash cai na regra forte,
antes do `permitir`. Se o gancho falhar: nega em leitura/rascunho, pergunta no resto; se o processo nem rodar, sai com 2 (bloqueia). Deny de gancho
vence o "allow" de outro gancho. Conf "wsl" (sessão no WSL): sem caixa; nome 8.3, programa e segredo do Windows negados. Python 3.9, só stdlib; não
importa nada do painel."""
import base64
import contextlib
import fnmatch
import json
import ntpath
import os
import posixpath
import re
import sys
import time
import unicodedata

RISCO_LEVE = ("leitura", "rascunho")
DECISOES = ("deny", "ask")
NEGAR_LEVE = ["Edit(**/.claude/settings*.json)", "Write(**/.claude/settings*.json)", "MultiEdit(**/.claude/settings*.json)"]
_CONFIG = (r"(?i)(^|[/\s'\"=])\.claude/(settings[^/\s'\"]*\.json|(hooks|skills|plugins)\b)" r"|(^|[/\s'\"=])(claude(\.local)?\.md|\.mcp\.json)($|[/\s'\";|&)<>])"
           r"|(^|[/\s'\"=])\.tune-up/painel(\.json|[\w.-]*/%s)")
# <pacote>/dados/ fica de fora, menos o que é do dono; com `..` no Bash, a exceção `dados/` não vale
CAMINHO_CONFIG = re.compile(_CONFIG % r"((?!dados/)|dados/(estudio-dono\.json|aprovados)\b)")
CAMINHO_CONFIG_PP = re.compile(_CONFIG % "")
BASH_ESCREVE = re.compile(r">|\btee\b|\bsed\s+-i|\bmv\b|\bcp\b|\brm\b|\bchmod\b|\bln\b|\btouch\b|\btruncate\b")
# Bash por texto: o que mais escreve (verbo no início do comando, heredoc, find -delete...).
BASH_ESCREVE_MAIS = re.compile(r"(?i)<<|\s-(delete|exec|execdir|ok)\b|\bsort\b[^;|&]*\s-o|\b(perl|ruby)\b[^;|&]*\s-\w*i")
INTERPRETES = {"python", "py", "node", "perl", "ruby", "php", "bash", "sh", "zsh", "dash", "ksh", "fish", "pwsh", "powershell", "cmd", "deno", "bun", "osascript", "source", "."}
VERBOS_ESCRITA = INTERPRETES | set("dd install rsync unlink mkdir rmdir patch xargs copy xcopy robocopy move del erase ren rename rd md set-content "
                                   "add-content out-file remove-item copy-item move-item new-item rename-item sudo doas env eval exec git tar unzip "
                                   "ditto scp curl wget certutil bitsadmin esentutl start-bitstransfer".split())
VERBOS_LEITURA = set("cat ls head tail grep egrep fgrep rg wc stat file du diff cmp less more type dir findstr pwd cd echo printf test "
                     "true realpath readlink basename dirname tree jq md5 md5sum shasum sha256sum get-content get-childitem".split())
SEP_BASH = re.compile(r"&&|\|\||\$\(|[;&|\n(){}`]")
META_BASH = re.compile(r";|&&|\|\||\||\$\(|`|<<|[<>]\(|\n|(?<![<>])&(?!>)")
CURINGA = re.compile(r"[*?\[{$`]")
NOMES_CONFIG = (".claude", ".tune-up", "claude.md", "claude.local.md", ".mcp.json")
DONO = ("estudio-dono.json", "aprovados", "extensoes.json",  # em <dados>: só o servidor grava (sandbox.DONO)
        "embutidos-ligados.json", "embutidos-ligados.json.gravando",  # o temporário também: nada plantado
        "estudio-node")  # o HyperFrames do Estúdio instalado do marketplace ({estudio_hf})
# escrita que cita esses nomes em qualquer caminho: `cd <dados> && echo > estudio-dono.json` não passa
RE_DONO = re.compile(r"(?i)(^|[/\s'\"=<>;|&()])(%s)($|[/\s'\";|&)<>])" % "|".join(re.escape(n) for n in DONO))
PONTO_PONTO = re.compile(r"(^|[/\s'\"=])\.\.($|[/\s'\";|&)<>])")
FERR_ARQUIVO, FERR_COMANDO = ("Edit", "Write", "MultiEdit", "NotebookEdit"), ("Bash",)
# PowerShell (ferramenta do Claude Code no Windows): negado inteiro no painel. A trava lê o texto do comando, e o
# PowerShell tem formas demais de montar caminho (aspas curvas, travessão, Join-String, iwr -OutFile, `\??\`...).
MOTIVO_PS = "no painel use o Bash (Git Bash); a ferramenta PowerShell fica de fora das sessões do painel"
# Windows, no Bash: outro shell (cmd expande %VAR%, PowerShell, WSL) ou .bat/.cmd: a trava não lê o que ele roda
RE_SHELL_WIN = re.compile(r"(?i)(^|[\s;&|(`=/])(cmd|command\.com|powershell(_ise)?|pwsh|wslg?|conhost|runas|cscript|wscript|mshta)(\.exe)?(?=$|[\s;&|)`])|comspec\b")
MOTIVO_SHELL = "no painel use o Bash direto: cmd, PowerShell, WSL e .bat/.cmd rodam fora do que a trava lê"
RE_UNIDADE = re.compile(r"^[A-Za-z]:")
RE_UNIDADE_REL = re.compile(r"(?i)(?<![\w$])[a-z]:(?![/\\])")  # `C:rel` = `rel` (cwd da unidade): variante a mais
# Windows: `\\?\C:\x`, `\\.\C:\x` e `\\?\UNC\srv\x` (= `\\srv\x`); /c/, /mnt/c/, /cygdrive/c/, //c/ do Git Bash/WSL
RE_PREFIXO_WIN = re.compile(r"(?i)^(?:[\\/]{2}[?.]|[\\/]\?\?)[\\/](unc[\\/])?")  # e o `\\??\\` do NT
RE_UNIDADE_BASH = re.compile(r"(?i)(^|[\s=<>;|&(])(?:/proc/cygdrive|/mnt|/cygdrive|/)?/([a-z])(?=/|$|[\s;|&)<>])")
RE_CURTO = re.compile(r"~\d")  # nome curto 8.3 (CLAUDE~1)
# rede/dispositivo (com `/`) que o gancho não resolve: \\?\GLOBALROOT, \\?\Volume{..}, \\localhost, `c$`; \\host + 8.3
RE_REDE = re.compile(r"(?i)^//(?![?.]/[a-z]:(/|$))")
RE_REDE_RUIM = re.compile(r"(?i)^//([?.]/(?!unc/|[a-z]:(/|$))|([?.]/unc/)?(localhost|127\.[\d.]+|\[?[0:]*:1\]?)(/|$)"
                          r"|([?.]/unc/)?[^/]+/[^/]*\$(/|$))|^/\?\?/(?![a-z]:(/|$))|^/proc/(?!cygdrive/)")
FIM_LIB = "/\\ \t\n'\""  # depois do liberado: separador, espaço, aspas ou fim (dadosx/ não é dados/)
# com sandbox o QA confia nos relatórios em <fonte>/.hyperframes/ (com `.` ou ` ` no fim, no Windows): só o Bash do hyperframes
# grava lá. Pelo gancho, não por regra: `Write(**/.hyperframes/**)` não barrou; `Edit(...)` cala o sandbox.
SCRIPTS_ESTUDIO = "qa_video qa_imagem reserva_slides video_ou_reserva fontes anuncio fotos montar".split()  # bash-estudio.json
RE_HF = re.compile(r"(^|/)\.hyperframes[. ]*(/|$)")
MOTIVO_HF = "relatório do hyperframes (.hyperframes/) só o próprio hyperframes grava"
WIN_WSL, SEGREDOS_WSL = (".claude", ".ssh", "appdata", ".aws", ".config", ".gnupg"), (".env*", "*.pem", "*.key")  # sandbox
RE_WIN_WSL = re.compile(r"(?i)^/mnt/[a-z]/(windows|users/[^/]+/(%s))(/|$)" % "|".join(map(re.escape, WIN_WSL)))


def _dobrado(texto):
    """NFKC + casefold p/ RE_HF/RE_DONO (o APFS dobra `ſ` em `s`; `(?i)` não dobra ligadura `ﬆ`). Só soma proteção."""
    return unicodedata.normalize("NFKC", texto).casefold()


def __getattr__(nome):
    """Só o painel usa estes (o gancho, com -I, nem acha travas_sessao): importa na primeira vez."""
    if nome in ("config_gancho", "_codificar", "settings_da_sessao", "argv_travas"):
        import travas_sessao
        return getattr(travas_sessao, nome)
    raise AttributeError("module %r has no attribute %r" % (__name__, nome))


def _decodificar(texto):
    conf = json.loads(base64.urlsafe_b64decode(texto.encode("ascii")).decode("utf-8"))
    if not isinstance(conf, dict) or conf.get("v") != 1:
        raise ValueError("configuração da trava inválida")
    return conf


def _sem_caixa(texto):
    """No Windows e no macOS (ou com cara de caminho do Windows) o disco não diferencia maiúsculas."""
    return os.name == "nt" or sys.platform == "darwin" or "\\" in texto or RE_UNIDADE.match(texto) is not None


def _barra(texto, sem_caixa):
    texto = texto.replace("\\", "/")
    return texto.lower() if sem_caixa else texto


def _win_limpo(caminho):
    """Como o Win32 lê: sem prefixo `\\\\?\\`/`\\\\.\\`, fluxo NTFS (`x::$DATA`) nem pontos/espaços no fim do pedaço."""
    m = RE_PREFIXO_WIN.match(caminho)
    t = (("//" if m.group(1) else "") + caminho[m.end():] if m else caminho).replace("\\", "/")
    unidade, t = (t[:2], t[2:]) if RE_UNIDADE.match(t) else ("", t)
    pedacos = [p.split(":", 1)[0] for p in t.split("/")]
    return unidade + "/".join(p if p in (".", "..") else p.rstrip(". ") for p in pedacos)


def caminho_comparavel(caminho, sem_caixa, nt=False):
    """Forma única de comparar: `\\`->`/`, `..` resolvido (posixpath), minúsculas se sem caixa; nt: _win_limpo."""
    if nt:
        caminho, sem_caixa = _win_limpo(caminho), True
    return posixpath.normpath(_barra(caminho, sem_caixa))


def _reais_win(caminho, cwd, realpath=None):
    """Windows, 8.3 (`CLAUDE~1` = `.claude`): realpath do caminho e da pasta + folha. Erro só tira a forma."""
    realpath = realpath or os.path.realpath
    alvo = _win_limpo(ntpath.join(cwd if isinstance(cwd, str) else "", caminho))
    if RE_REDE.match(caminho.replace("\\", "/")) or alvo.startswith("//"):
        return []  # rede ou dispositivo: nunca vai à rede (decidir já pergunta/nega pelo _escondido)
    out = []
    for fazer in (lambda: realpath(alvo), lambda: ntpath.join(realpath(ntpath.dirname(alvo)), ntpath.basename(alvo))):
        with contextlib.suppress(OSError, ValueError):
            out.append(fazer())
    return out


def _liberado(texto, i, libs):
    """No Windows `\\` e `/` são o mesmo separador, sem caixa: o liberado (os.path.join) casa o caminho com `/`."""
    for lib in libs:
        fim = i + len(lib)
        igual = texto.startswith(lib, i) or os.name == "nt" and _barra(texto[i:fim], True) == _barra(lib, True)
        if igual and (fim == len(texto) or texto[fim] in FIM_LIB):
            return True
    return False


def _protegido(texto, conf, forma=None, sem_lib=False):
    """`forma` (opcional) normaliza protegidos e liberados do mesmo jeito que o texto."""
    if (CAMINHO_CONFIG_PP if sem_lib else CAMINHO_CONFIG).search(texto):
        return True
    libs = [] if sem_lib else [forma(x) if forma else x for x in conf.get("lib") or []]
    for p in conf.get("prot") or []:
        p = forma(p) if forma else p
        libs_p = [lib for lib in libs if not p.startswith(lib)]  # protegido dentro do liberado vale
        i = texto.find(p)
        while i >= 0:
            if not _liberado(texto, i, libs_p):
                return True
            i = texto.find(p, i + 1)
    return False


def _bash_comparavel(cmd, sc, escape=False):
    """Sem aspas ("/a"'b' = /ab), `\\` -> `/` (escape=True: `\\x` -> `x`, como no POSIX), `/./` e `//` colapsados."""
    t = re.sub(r"[\"']", "", cmd)
    t = re.sub(r"/\.(?=/)", "", _barra(re.sub(r"\\(.)", r"\1", t) if escape else t, sc))
    return re.sub(r"(?<=[^\s=<>;|&(])/{2,}", "/", t)


def _palavras_win(t):
    """Cada palavra e o que o Win32 lê nela: sem `-Param:`/`FileSystem::`, itens com vírgula e `c:/..` no meio."""
    out = []
    for w in re.split(r"[\s=<>;|&()]+", t):
        s = re.sub(r"(?i)^-[\w-]*:|^(microsoft\.powershell\.core/)?filesystem::", "", w)
        out += [w] + s.split(",") + re.findall(r"(?i)(?<![a-z])[a-z]:/[^\s'\",;|&()<>{}]*", w)
    return [w for w in out if w]


def _bash_win(norm, cwd="", realpath=None):
    """Windows: /c/, /mnt/c/, /cygdrive/c/, //c/ viram `c:/`; soma cada palavra como o Win32 lê e, com 8.3, a forma
    longa (realpath). (texto, solto): solto = pasta `X~1/` que o realpath não expandiu (base fora do cwd)."""
    t = RE_UNIDADE_BASH.sub(lambda m: m.group(1) + m.group(2).lower() + ":", norm)
    comido = re.sub(r"(?<=[^\s/.=<>;|&(])[. ]+(?=/)", "", t)  # `.claude. /x` (aspas já saíram); variante, não troca
    limpas = list(dict.fromkeys(_win_limpo(w) for w in _palavras_win(t) + _palavras_win(comido)))
    reais = {w: _reais_win(w, cwd, realpath) for w in limpas if RE_CURTO.search(w)}
    solto = any(re.search(r"~\d+(\.[^/:]{1,3})?/", w) and all(RE_CURTO.search(r) for r in reais.get(_win_limpo(w), ()))
                for w in _palavras_win(t) if not re.match(r"(?i)-|.*(,|::)", w))  # HEAD~1:x não; -P:, x,y já soltos
    return " ".join([t, comido] + limpas + [caminho_comparavel(r, True, True) for v in reais.values() for r in v]), solto


def _disfarcado(norm, conf, forma):
    """Palavra com curinga ou variável que o shell pode expandir para dentro de uma árvore protegida."""
    prots = [forma(p) for p in conf.get("prot") or []]
    for tok in re.split(r"[\s=<>;|&()]+", norm):
        m = CURINGA.search(tok)
        if not m:
            continue
        fixo, ultimo = tok[:m.start()], tok[:m.start()].rsplit("/", 1)[-1].lower()
        if (tok[m.start()] in "$`" and "/" in tok[m.start():]  # $X/y, `pwd`/y: o shell decide o caminho
                or (fixo.startswith("/") or RE_UNIDADE.match(fixo)) and any(p.startswith(fixo) for p in prots)):
            return True
        if ultimo and any(n.startswith(ultimo) for n in NOMES_CONFIG + DONO) or re.search(r"(?i)\.(claude|tune-up)/", fixo):
            return True
    return False


def _resolvidos(norm, cwd, sc):
    """Cada palavra relativa resolvida contra o cwd da sessão (`../../x` a partir de {trabalho})."""
    base = caminho_comparavel(cwd, sc)
    return " ".join(posixpath.normpath(posixpath.join(base, tok)) for tok in re.split(r"[\s=<>;|&()]+", norm)
                    if tok and not tok.startswith(("/", "-", "~", "$")) and not RE_UNIDADE.match(tok))


def _protegido_normal(texto, conf, comando, cwd="", nt=False, realpath=None):
    """Mesma checagem com `\\` -> `/` e `..` resolvido; só soma. Bash: aspas, `//`, `/./`, `\\x`, curinga/variável não disfarçam; com `..` a exceção `dados` cai; relativo
    vale contra o cwd. `nt=True` soma as formas do Windows (_win_limpo, _bash_win, sem unidade: `\\Users\\..`, `-o/c/..`, `{x,/c/..}`; `%VAR%/`, `!VAR!/`), nunca no lugar."""
    sc = nt or conf.get("wsl") is True or _sem_caixa(texto) or _sem_caixa(cwd)  # WSL: /mnt/<letra>/ sem caixa
    forma = lambda p: caminho_comparavel(p, sc)  # noqa: E731
    win = lambda p: caminho_comparavel(p, True, True)  # noqa: E731
    if not comando:
        return any(_protegido(n, conf, f) or CAMINHO_CONFIG.search(RE_UNIDADE.sub("", n)) is not None
                   or RE_DONO.search(_dobrado(n)) is not None for f in (forma, win)[:1 + nt] for n in [f(texto)])
    def visto(norm, f):
        pp = PONTO_PONTO.search(norm) is not None
        return (_protegido(norm, conf, f, sem_lib=pp) or _disfarcado(norm, conf, f) or RE_DONO.search(_dobrado(norm))
                or cwd and _protegido(_resolvidos(norm, cwd, sc), conf, f,
                                      sem_lib=pp and re.search(r"\b(cd|pushd)\b", norm)))
    base = {_bash_comparavel(x, sc, e) for x in [texto] + [RE_UNIDADE_REL.sub("", texto)] * nt for e in (False, True)}
    if any(visto(n, forma) for n in base):
        return True
    for n in base if nt else ():  # realpath só se o texto cru não decidiu
        norm, solto = _bash_win(n, cwd, realpath)
        if solto or re.search(r"%[^%\s/]+%/|![^!\s/]+!/", norm) or visto(norm, win) or visto(norm, lambda p: RE_UNIDADE.sub("", win(p))):
            return True
    return False


def _verbos(cmd):
    """Primeira palavra de cada comando (pula VAR=valor), em minúsculas, sem pasta, `.exe` nem versão."""
    out = []
    for seg in SEP_BASH.split(cmd):
        w = next((w for w in (x.strip("\"'") for x in seg.split()) if not re.match(r"^[A-Za-z_]\w*=", w)), None)
        if w is not None:
            v = re.sub(r"\.exe$", "", posixpath.basename(w.replace("\\", "/")).lower())
            out.append((w, re.sub(r"^(python|node|perl|ruby|php|pwsh)[\d.]*$", r"\1", v)))
    return out


def _escreve(cmd, verbos):
    return bool(BASH_ESCREVE.search(cmd) or BASH_ESCREVE_MAIS.search(cmd) or any(v in VERBOS_ESCRITA for _, v in verbos))


def _composto_ou_script(cmd, verbos):
    """Metacaractere de shell, código inline, heredoc ou script executado (gravado antes ou não)."""
    return bool(META_BASH.search(cmd)) or any(v in INTERPRETES or w.startswith(("./", ".\\", "/", "~")) or RE_UNIDADE.match(w)
                                              or re.search(r"(?i)\.(sh|bash|zsh|py|js|mjs|pl|rb|php|ps1|bat|cmd)$", w) for w, v in verbos)


def _casa(regra, ferramenta, entrada):
    ok = re.fullmatch(regra["ferramenta"], ferramenta) is not None
    if not ok or "entrada" not in regra:
        return ok
    valor = entrada.get(regra["campo"]) if "campo" in regra else entrada
    if valor is None:
        return False
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False, sort_keys=True)
    return re.search(regra["entrada"], texto) is not None


def _em_hyperframes(caminho, cwd):
    """Pelo texto (`..` resolvido, sem caixa) e pelo caminho real (link simbólico para dentro também vale)."""
    alvos = [caminho]
    with contextlib.suppress(OSError, ValueError):
        alvos.append(os.path.realpath(os.path.join(cwd if isinstance(cwd, str) else "", caminho)))
    return any(RE_HF.search(caminho_comparavel(_dobrado(a), True)) for a in alvos)


def _escondido(ferramenta, entrada, nt):
    """Windows: o texto não mostra o caminho (rede ou dispositivo que o gancho não resolve; //c/ do Git Bash é C:)."""
    c = entrada.get("file_path") or entrada.get("notebook_path") if ferramenta in FERR_ARQUIVO else None
    cmd = entrada.get("command") if ferramenta in FERR_COMANDO else None
    ws = [c.replace("\\", "/")] if isinstance(c, str) else [w for w in _palavras_win(re.sub(
        r"[\"']", "", cmd).replace("\\", "/")) if not re.match(r"(?i)^//[a-z](/|$)", w)] if isinstance(cmd, str) else []
    return bool(nt and any(RE_REDE_RUIM.match(p) or RE_REDE.match(p) and RE_CURTO.search(p) for p in ws))


def _shell_win(cmd, verbos):
    """Windows, no Bash: chama cmd, PowerShell, WSL (pelo nome, pelo caminho ou %COMSPEC%) ou roda .bat/.cmd."""
    return any(RE_SHELL_WIN.search(t) for t in [cmd] + [_bash_comparavel(cmd, True, e) for e in (False, True)]) or any(re.search(r"(?i)\.(bat|cmd)$", w) for w, _ in verbos)


def _sem_estudio(cmd, conf):
    """Com sandbox, só p/ checar caminho: tira o `exe` do Estúdio ou `<py>`+script após `python3 -I [-B] `."""
    for exe in (conf.get("exe") or []) if conf.get("sb") else []:
        if isinstance(exe, str) and exe and cmd.startswith(exe + " "):
            return cmd[len(exe):]
    py = conf.get("py") if conf.get("sb") else None
    m = isinstance(py, str) and py and re.match(r"python3 -I (-B )?(%s(%s)\.py)(?= |\Z)" % (re.escape(py), "|".join(SCRIPTS_ESTUDIO)), cmd)
    return cmd[:m.start(2)] + cmd[m.end(2):] if m else cmd


def decidir(conf, ferramenta, entrada, cwd="", nt=None, realpath=None):
    """(decisão, motivo) ou None. cwd: o da sessão; nt/realpath: testes. _escondido só sobe a decisão (antes do permitir)."""
    if ferramenta == "PowerShell":
        return "deny", MOTIVO_PS
    nt, forte = os.name == "nt" if nt is None else nt, conf.get("forte") if conf.get("forte") in DECISOES else "deny"
    entrada, cwd = entrada if isinstance(entrada, dict) else {}, cwd if isinstance(cwd, str) else ""
    if conf.get("wsl") is True and _wsl(conf, ferramenta, entrada, cwd):  # antes do resto e do `permitir`
        return "deny", "no WSL ficam de fora: nome curto 8.3 (X~1), programa do Windows (.exe, cmd...), segredo (.env...) e curinga que chegue a eles"
    r = _decidir(conf, ferramenta, entrada, cwd, nt, realpath, forte)
    return (forte, "caminho que a trava não vê") if (r is None or r[0] != "deny") and _escondido(ferramenta, entrada, nt) else r


def _wsl(conf, ferramenta, entrada, cwd):
    """WSL (/mnt/<letra>/ = disco do Windows): nome 8.3, programa ou segredo do Windows e segredo da sessão, sem caixa, no Bash, no
    caminho e no glob do Glob/Grep, com curinga e `{a,b}`. 2ª camada: as barreiras são o denyRead do sandbox e o interop desligado."""
    cmd, g = entrada.get("command"), entrada.get({"Glob": "pattern", "Grep": "glob"}.get(ferramenta, ""))
    cam = [v for k, v in entrada.items() if k in ("file_path", "notebook_path", "path") and isinstance(v, str)]
    ts = [x for t in cam + [cmd] * isinstance(cmd, str) for x in [t] + [_bash_comparavel(t, True, e) for e in (False, True)] + [_resolvidos(t, cwd, True)]]
    pal = [w for t in [_bash_comparavel(cmd, True, e) for e in (False, True) if isinstance(cmd, str)] + [g] * isinstance(g, str) for w in re.split(r"[\s=<>;|&()`]+", t)]
    for _ in range(64):  # `{a,b}` do bash expandido (passou de ~1 MB: `/*`, que nega); o que sobra (`{a..z}`) vale `*`
        ms = [(w, re.search(r"\{([^{}]*,[^{}]*)\}", w)) for w in pal]
        pal = ["/*"] if sum(len(w) * (m.group(1).count(",") + 1 if m else 1) for w, m in ms) > 10 ** 6 else [
            x for w, m in ms for x in ([w[:m.start()] + alt + w[m.end():] for alt in m.group(1).split(",")] if m else [re.sub(r"\{[^{}]*\}", "*", w)])]
    raiz = next((p.lower()[:-21].split("/") for p in conf.get("prot") or [] if p.endswith("/.tune-up/painel.json")), None)
    ped = [c for p in cam + pal for q in [p.replace("\\", "/").split("/")] for c in [x for x in q[:-1] if x.strip("*")] + q[-1:]]
    base = entrada["path"] if ferramenta in ("Glob", "Grep") and entrada.get("path") in cam else cwd  # `~`: 1 ou 2 níveis
    cur = [posixpath.normpath(posixpath.join(base or "/", re.sub(r"^~[^/]*", "/*/*", p))).lower().split("/") for p in pal if re.search(r"[*?[]", p)]
    return (any(RE_CURTO.search(t) for t in ts) or any(_cruza(c, s) for c in ped for s in SEGREDOS_WSL) or isinstance(cmd, str) and _shell_win(cmd, _verbos(cmd))
            or any(RE_WIN_WSL.match(posixpath.normpath(w)) for t in ts + pal for w in re.split(r"[\s=<>;|&()]+", t) if w[:1] == "/")
            or any(_cruza(p.rsplit("/", 1)[-1], x) for p in pal for x in ("cmd", "powershell", "pwsh", "wsl", "*.exe", "*.bat", "*.cmd", "*.com", "*.ps1"))
            or any(_cruza(a[1], "mnt") and (not raiz or a[:len(raiz)] != raiz or len(a) > 5 and _cruza(a[3], "users") and any(_cruza(a[5], x) for x in WIN_WSL)) for a in cur))


def _cruza(a, b):
    """Algum nome (até 255) casa o glob `a` e o `b` (`x`, `x*` ou `*x`)? `[..]` vale `?`, sem caixa; curinga no início de `a` não pega `.`."""
    a, b = (re.sub(r"\[[^\]/]*\]?", "?", x.lower()) for x in (a, b))
    cortes = [a[:k] for k in range(len(a) + 1)] if b[-1:] == "*" else [a[k:] for k in range(len(a) + 1)] if b[:1] == "*" else [a]
    return re.search(r"[*?]", a) is not None if len(a) > 255 else not (a[:1] in ("*", "?") and b[:1] == ".") and any(fnmatch.fnmatchcase(b.strip("*"), x) for x in cortes)


def _decidir(conf, ferramenta, entrada, cwd, nt, realpath, forte):
    if ferramenta in FERR_ARQUIVO:
        caminho = str(entrada.get("file_path") or entrada.get("notebook_path") or "")
        if caminho and conf.get("sb") and any(_em_hyperframes(c, cwd) for c in [caminho] + [_win_limpo(caminho)] * nt):
            return "deny", MOTIVO_HF  # nem "ask": o dono não deve aprovar relatório forjado
        if caminho and (_protegido(caminho, conf) or _protegido(os.path.normpath(caminho), conf) or _protegido_normal(caminho, conf, False, nt=nt)
                        or nt and any(_protegido_normal(r, conf, False, nt=True) for r in _reais_win(caminho, cwd, realpath))):
            return forte, "mexer nas regras do Claude ou do painel"
    if ferramenta in FERR_COMANDO:
        cmd = entrada.get("command")
        if not isinstance(cmd, str):
            return forte, "comando ilegível"
        verbos, resto = _verbos(cmd), _sem_estudio(cmd, conf)
        # leitura/rascunho: só verbo de leitura conhecido pode citar árvore protegida
        if (_protegido(resto, conf) or _protegido_normal(resto, conf, True, cwd, nt, realpath)) and (
                _escreve(cmd, verbos) or conf.get("leve") and any(v not in VERBOS_LEITURA for _, v in verbos)):
            return forte, "mexer nas regras do Claude ou do painel"
        if nt and _shell_win(cmd, verbos):  # antes do permitir: o que o outro shell roda a trava não lê
            return forte, MOTIVO_SHELL
        if conf.get("bash") and _composto_ou_script(cmd, verbos):  # antes do permitir
            return "deny", "comando composto, código inline ou script numa ação com Bash liberado"
    for regra in conf.get("p") or []:
        if _casa(regra, ferramenta, entrada):
            return None
    for regra in conf.get("n") or []:
        if _casa(regra, ferramenta, entrada):
            return regra.get("decisao") if regra.get("decisao") in DECISOES else "deny", regra.get("motivo") or "regra"
    return None


RE_SESSAO_GANCHO = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
FERR_PERGUNTA = "AskUserQuestion"
MOTIVO_PERGUNTA = ("esta sessão roda no chat do painel, sem terminal. Não use AskUserQuestion: escreva a pergunta como texto na sua "
                   "resposta (com as opções numeradas, a recomendada primeiro) e TERMINE a vez. O dono responde pelo chat e a conversa continua")


def limpar_perguntas(entrada):
    """Entrada do AskUserQuestion -> lista curta e limpa para a tela."""
    out = []
    for q in (entrada.get("questions") if isinstance(entrada, dict) else None) or []:
        if not isinstance(q, dict) or not isinstance(q.get("question"), str) or not q["question"].strip():
            continue
        opcoes = [{"rotulo": o["label"].strip()[:120], "descricao": str(o.get("description") or "").strip()[:300]}
                  for o in q.get("options") or [] if isinstance(o, dict) and isinstance(o.get("label"), str) and o["label"].strip()]
        out.append({"pergunta": q["question"].strip()[:500], "cabecalho": str(q.get("header") or "").strip()[:40],
                    "multipla": q.get("multiSelect") is True, "opcoes": opcoes[:6]})
    return out[:4]


def guardar_pergunta(pasta, sessao_id, entrada, win=False):
    """Grava <pasta>/<sessionId>.json (0600, troca atômica). Falha aqui nunca libera a ferramenta."""
    perguntas = limpar_perguntas(entrada)
    if not perguntas or not isinstance(sessao_id, str) or not RE_SESSAO_GANCHO.match(sessao_id):
        return False
    try:
        os.makedirs(pasta, mode=0o700, exist_ok=True)
        tmp = os.path.join(pasta, ".%s.%d.tmp" % (sessao_id, os.getpid()))
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"perguntas": perguntas}, f, ensure_ascii=False)
        _insistir(lambda: os.replace(tmp, os.path.join(pasta, sessao_id + ".json")), win)
        return True
    except OSError:
        return False


def _insistir(fazer, win=False):
    """Windows (ou disco dele pelo WSL, `win`): arquivo aberto por outro dá PermissionError por um instante."""
    limite = time.monotonic() + (2 if win or os.name == "nt" else 0)
    while True:
        try:
            return fazer()
        except PermissionError:
            if time.monotonic() >= limite:
                raise
            time.sleep(0.05)


def esquecer_pergunta(pasta, sessao_id, win=False):
    if isinstance(sessao_id, str) and RE_SESSAO_GANCHO.match(sessao_id):
        with contextlib.suppress(OSError):
            _insistir(lambda: os.unlink(os.path.join(pasta, sessao_id + ".json")), win)


def principal(argv, stdin, stdout):
    falha = "deny"
    try:
        conf = _decodificar(argv[1] if len(argv) > 1 else "")
        falha = conf.get("falha") if conf.get("falha") in DECISOES else "deny"
        dados = json.load(stdin)
        resposta = decidir(conf, str(dados.get("tool_name") or ""), dados.get("tool_input") or {}, dados.get("cwd"))
        if isinstance(conf.get("perg"), str) and conf["perg"]:
            if dados.get("tool_name") == FERR_PERGUNTA:
                guardar_pergunta(conf["perg"], dados.get("session_id"), dados.get("tool_input") or {}, conf.get("wsl") is True)
                resposta = "deny", MOTIVO_PERGUNTA
            else:  # usou outra ferramenta: seguiu em frente, a pergunta antiga não vale mais
                esquecer_pergunta(conf["perg"], dados.get("session_id"), conf.get("wsl") is True)
    except Exception as erro:  # nunca libera no escuro
        resposta = falha, "a trava do painel falhou: " + type(erro).__name__
    if resposta:
        stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": resposta[0],
                                                         "permissionDecisionReason": "Trava do painel: " + resposta[1]}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(principal(sys.argv, sys.stdin, sys.stdout))
