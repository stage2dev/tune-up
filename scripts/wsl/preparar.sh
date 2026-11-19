#!/usr/bin/env bash
# tune-up: allow-long one self-contained file the installer copies into the distro (a split adds a file to its copy list)
# preparar.sh: prepares the inside of the WSL distro for tune-up. The Windows installer copies it,
# medir.sh and fixados.env into /usr/local/lib/tune-up/ and runs, one mode per call:
#   wsl.exe -d tune-up -u <user> --exec bash /usr/local/lib/tune-up/preparar.sh <mode>
# (--exec: no login shell, no profile; nothing here relies on ~/.profile or ~/.bashrc.)
# Modes (exit 0 ok, 1 failed, 2 usage, 3 wrong user, 4 bad fixados.env, 5 download/hash,
#        6 uid 1000 taken, 7 interop on, 8 plugin not valid for the marker; --verificar: its report's code):
#   --raiz                                   root   packages, user, Node, FFmpeg, helpers, install-phase wsl.conf
#   --usuario --plugin <dir> [--sem-login]   tuneup Claude Code, plugin, Chrome, HyperFrames
#   --verificar --plugin <dir>               tuneup runs verificar_ambiente.py
#   --fechar                                 root   final wsl.conf (interop off); never writes the marker
#   --marcar --plugin-versao <x.y.z>         root   writes /etc/tune-up/pronto.json (only with interop off)
#   --abrir-interop                          root   deletes the marker, then install-phase wsl.conf
#   --versao-plugin                          tuneup prints only the installed tune-up@tune-up version (1: none)
# Tests only: TUNE_UP_RAIZ_TESTE=<dir> prefixes /etc, /usr, /run/WSL, /home and /var/tmp, and
# TUNE_UP_UID_TESTE stands in for the uid. Both are honoured only when the real uid is not 0.
set -euo pipefail
export LC_ALL=C
umask 022

# Builtins only until PATH is pinned: real run (or root) gets a fixed PATH before any external command,
# so root never picks a binary from /mnt (appendWindowsPath is on at first boot).
UID_REAL=$EUID
if [ -z "${TUNE_UP_RAIZ_TESTE:-}" ] || [ "$UID_REAL" = 0 ]; then
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    export PATH
fi
U=tuneup
AQUI=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
TMPD=""
trap 'if [ -n "$TMPD" ]; then rm -rf -- "$TMPD"; fi' EXIT

die() { printf 'preparar: %s\n' "$2" >&2; exit "$1"; }
msg() { printf '%s\n' "$*"; }

uso() {
    cat >&2 <<'FIM'
Uso: preparar.sh <modo>
  --raiz                                   (root) pacotes, usuário, Node, FFmpeg, ajudantes
  --usuario --plugin <pasta> [--sem-login] (tuneup) Claude Code, plugin, Chrome, HyperFrames
  --verificar --plugin <pasta>             (tuneup) confere o ambiente
  --fechar                                 (root) wsl.conf final, ponte com o Windows desligada
  --marcar --plugin-versao <x.y.z>         (root) grava /etc/tune-up/pronto.json
  --abrir-interop                          (root) apaga a marca e liga a ponte para o login
  --versao-plugin                          (tuneup) imprime só a versão instalada do plugin tune-up
FIM
    exit 2
}

R=""
EU=$UID_REAL
if [ -n "${TUNE_UP_RAIZ_TESTE:-}" ]; then
    [ "$UID_REAL" != 0 ] || die 3 "TUNE_UP_RAIZ_TESTE não vale para root; recusado."
    [[ $TUNE_UP_RAIZ_TESTE =~ ^/[A-Za-z0-9._/-]+$ ]] || die 3 "TUNE_UP_RAIZ_TESTE: caminho absoluto, sem espaço."
    R=$(cd "$TUNE_UP_RAIZ_TESTE" && pwd -P) || die 3 "TUNE_UP_RAIZ_TESTE não existe."
    [[ $R =~ ^/[A-Za-z0-9._/-]+$ ]] || die 3 "TUNE_UP_RAIZ_TESTE: caminho absoluto, sem espaço."
    EU=${TUNE_UP_UID_TESTE:-$UID_REAL}
fi
PY="$R/usr/bin/python3"
HOME_U="$R/home/$U"
MARCA="$R/etc/tune-up/pronto.json"
LIB="$R/usr/local/lib/tune-up"

CHAVES="UBUNTU_URL UBUNTU_SHA256 NODE_VERSAO NODE_URL NODE_SHA256 FFMPEG_URL FFMPEG_SHA256 \
CLAUDE_VERSAO CLAUDE_URL CLAUDE_SHA256 CHROME_VERSAO CHROME_URL CHROME_SHA256 DISTRO USUARIO"

# Strict reader of fixados.env: never sourced. Closed key list, KEY=value, # comments, blank lines.
ler_fixados() {
    local arq="$AQUI/fixados.env" linha chave valor n=0 re='^[A-Za-z0-9._:/+-]*$' k
    [ -f "$arq" ] || die 4 "fixados.env não encontrado ao lado do script."
    if LC_ALL=C grep -q "$(printf '\r')" "$arq"; then die 4 "fixados.env tem fim de linha do Windows (CR); recusado."; fi
    # shellcheck disable=SC2086
    unset $CHAVES
    while IFS= read -r linha || [ -n "$linha" ]; do
        n=$((n + 1))
        case "$linha" in '' | '#'*) continue ;; esac
        chave=${linha%%=*}
        valor=${linha#*=}
        [ "$chave" != "$linha" ] || die 4 "fixados.env linha $n: não é CHAVE=valor."
        [[ $chave =~ ^[A-Z0-9_]+$ ]] || die 4 "fixados.env linha $n: chave inválida."
        case " $CHAVES " in
            *" $chave "*) ;;
            *) die 4 "fixados.env linha $n: chave desconhecida." ;;
        esac
        [[ $valor =~ $re ]] || die 4 "fixados.env linha $n: valor com caractere não aceito."
        [ -z "${!chave+x}" ] || die 4 "fixados.env linha $n: chave $chave repetida."
        printf -v "$chave" '%s' "$valor"
    done <"$arq"
    for k in $CHAVES; do
        [ -n "${!k:-}" ] || die 4 "fixados.env: falta a chave $k."
        case "$k" in
            *_SHA256) [[ ${!k} =~ ^[0-9a-f]{64}$ ]] || die 4 "fixados.env: $k não é um sha256." ;;
            *_URL) case "${!k}" in https:*) ;; *) die 4 "fixados.env: $k não é https." ;; esac ;;
        esac
    done
    [ "$USUARIO" = "$U" ] || die 4 "fixados.env: USUARIO precisa ser $U."
}

pasta_temp() {
    if [ -z "$TMPD" ]; then
        [ -z "$R" ] || mkdir -p "$R/var/tmp"
        TMPD=$(mktemp -d "$R/var/tmp/tune-up.XXXXXXXX")
    fi
}

# Download into the temp dir and check the pinned sha256 before anything else touches the file.
baixar() {
    local url=$1 sha=$2 dest got
    pasta_temp
    dest="$TMPD/$3"
    msg "Baixando $3..."
    if ! curl -fL --proto '=https' --proto-redir '=https' --tlsv1.2 --retry 2 -sS \
        --connect-timeout 30 --speed-limit 1024 --speed-time 60 -o "$dest" "$url"; then
        rm -f -- "$dest"
        die 5 "não consegui baixar $3; confira a internet e rode de novo."
    fi
    got=$(sha256sum -- "$dest")
    got=${got%% *}
    if [ "$got" != "$sha" ]; then
        rm -f -- "$dest"
        die 5 "$3 não confere com o sha256 fixado (esperado $sha, veio $got); arquivo apagado, nada instalado."
    fi
}

# Copy src to dest atomically with a mode (root:root on a real run).
por() {
    local tmp="$2.tmp.$$"
    cp -- "$1" "$tmp"
    chmod "$3" "$tmp"
    if [ -z "$R" ]; then chown root:root "$tmp"; fi
    mv -f -- "$tmp" "$2"
}

# Write stdin to dest atomically with a mode (root:root on a real run).
escrever() {
    local tmp
    tmp=$(mktemp "$1.XXXXXX")
    cat >"$tmp"
    chmod "$2" "$tmp"
    if [ -z "$R" ]; then chown root:root "$tmp"; fi
    mv -f -- "$tmp" "$1"
}

apagar_marca() {
    rm -f -- "$MARCA" || die 1 "não consegui apagar $MARCA."
    if [ -e "$MARCA" ] || [ -L "$MARCA" ]; then die 1 "não consegui apagar $MARCA."; fi
}

interop_ligado() {
    local f
    if [ -n "${WSL_INTEROP+x}" ]; then return 0; fi
    for f in "$R"/run/WSL/*_interop; do
        if [ -e "$f" ] || [ -L "$f" ]; then return 0; fi
    done
    return 1
}

escrever_wslconf() { # $1: true (install phase) or false (final)
    mkdir -p "$R/etc"
    escrever "$R/etc/wsl.conf" 0644 <<FIM
[user]
default=$U

[boot]
systemd=false

[interop]
enabled=$1
appendWindowsPath=false

[automount]
enabled=true
FIM
}

ser_root() { [ "$EU" = 0 ] || die 3 "$1 precisa rodar como root (wsl.exe -u root)."; }

ser_usuario() {
    local uid_u
    [ "$EU" != 0 ] || die 3 "$1 não roda como root; use wsl.exe -u $U."
    uid_u=$(getent passwd "$U" | cut -d: -f3) || true
    [ -n "$uid_u" ] && [ "$EU" = "$uid_u" ] || die 3 "$1 precisa rodar como o usuário $U."
}

validar_plugin() {
    [ -n "$PLUGIN" ] || uso
    case "$PLUGIN" in /*) ;; *) die 2 "--plugin precisa ser um caminho absoluto." ;; esac
    case "/$PLUGIN/" in */../* | */./*) die 2 "--plugin não aceita '..' nem '.'." ;; esac
    case "$PLUGIN" in *$'\n'*) die 2 "--plugin com quebra de linha." ;; esac
    [ -f "$PLUGIN/.claude-plugin/plugin.json" ] || die 2 "--plugin: $PLUGIN não tem .claude-plugin/plugin.json."
}

# ---- --raiz -------------------------------------------------------------------------------------

# libatomic1: the Node 26 binary links libatomic.so.1 (observed missing on a bare ubuntu:24.04).
PACOTES="bubblewrap socat python3 ca-certificates curl unzip xz-utils gnupg libatomic1
libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libdrm2 libxkbcommon0 libatspi2.0-0t64
libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2t64
fonts-liberation fonts-noto-color-emoji"

criar_usuario() {
    local linha uid dono
    linha=$(getent passwd "$U") || true
    if [ -n "$linha" ]; then
        uid=$(printf '%s' "$linha" | cut -d: -f3)
        [ "$uid" = 1000 ] || die 6 "o usuário $U já existe com uid $uid (esperado 1000); nada alterado."
        msg "Usuário $U já existe."
        return
    fi
    dono=$(getent passwd 1000) || true
    if [ -n "$dono" ]; then
        die 6 "o uid 1000 já é do usuário ${dono%%:*}; não apago ninguém. Use uma distro nova."
    fi
    # No password (account stays locked) and no extra group.
    useradd -u 1000 -m -s /bin/bash "$U" || die 1 "não consegui criar o usuário $U."
    msg "Usuário $U criado."
}

instalar_pacotes() {
    local n ok
    # shellcheck disable=SC2086
    n=$(echo $PACOTES | wc -w | tr -d ' ')
    # shellcheck disable=SC2086,SC2016
    ok=$(dpkg-query -W -f='${Status}\n' $PACOTES 2>/dev/null | grep -cx 'install ok installed') || true
    if [ "$ok" = "$n" ]; then
        msg "Pacotes do sistema já instalados."
        return
    fi
    msg "Instalando pacotes do sistema..."
    apt-get update -q || die 1 "apt-get update falhou; confira a internet e rode de novo."
    # shellcheck disable=SC2086
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q --no-install-recommends $PACOTES ||
        die 1 "apt-get install falhou."
}

instalar_node() {
    local atual="" nome
    if [ -x "$R/usr/local/bin/node" ]; then atual=$("$R/usr/local/bin/node" --version 2>/dev/null) || true; fi
    if [ "$atual" = "v$NODE_VERSAO" ]; then
        msg "Node $atual já instalado."
        return
    fi
    baixar "$NODE_URL" "$NODE_SHA256" node.tar.xz
    nome=${NODE_URL##*/}
    nome=${nome%.tar.xz}
    mkdir -p "$R/usr/local"
    tar -xJf "$TMPD/node.tar.xz" -C "$R/usr/local" --strip-components=1 --no-same-owner \
        "$nome/bin" "$nome/lib" "$nome/include" "$nome/share" || die 1 "não consegui extrair o Node."
    msg "Node v$NODE_VERSAO instalado."
}

instalar_ffmpeg() {
    local selo="$LIB/ffmpeg.sha256" nome b
    if [ -x "$R/usr/local/bin/ffmpeg" ] && [ -x "$R/usr/local/bin/ffprobe" ] &&
        [ "$(cat "$selo" 2>/dev/null)" = "$FFMPEG_SHA256" ]; then
        msg "FFmpeg já instalado."
        return
    fi
    baixar "$FFMPEG_URL" "$FFMPEG_SHA256" ffmpeg.tar.xz
    nome=${FFMPEG_URL##*/}
    nome=${nome%.tar.xz}
    mkdir -p "$TMPD/ff" "$R/usr/local/bin" "$LIB"
    tar -xJf "$TMPD/ffmpeg.tar.xz" -C "$TMPD/ff" --no-same-owner "$nome/bin/ffmpeg" "$nome/bin/ffprobe" ||
        die 1 "não consegui extrair o FFmpeg."
    for b in ffmpeg ffprobe; do por "$TMPD/ff/$nome/bin/$b" "$R/usr/local/bin/$b" 0755; done
    printf '%s\n' "$FFMPEG_SHA256" | escrever "$selo" 0644
    msg "FFmpeg instalado."
}

instalar_ajudantes() {
    mkdir -p "$R/usr/local/bin"
    escrever "$R/usr/local/bin/tune-up-abrir" 0755 <<'FIM'
#!/bin/sh
# Used only as BROWSER during the login step (interop on).
exec /mnt/c/Windows/explorer.exe "$1"
FIM
    # The gate every panel-launched command goes through: checks in its own process, builtins only.
    escrever "$R/usr/local/bin/tune-up-exec" 0755 <<FIM
#!/bin/sh
# tune-up-exec: runs the command only while WSL interop is off and the install is marked done.
ligada=\${WSL_INTEROP+1}
for f in $R/run/WSL/*_interop; do
    if [ -e "\$f" ] || [ -L "\$f" ]; then ligada=1; fi
done
if [ -n "\$ligada" ]; then
    echo "tune-up-exec: a ponte com o Windows (interop) está ligada; recusado." >&2
    exit 97
fi
if [ ! -f $R/etc/tune-up/pronto.json ]; then
    echo "tune-up-exec: a preparação não terminou (falta /etc/tune-up/pronto.json); recusado." >&2
    exit 97
fi
if [ \$# -eq 0 ]; then
    echo "tune-up-exec: falta o comando." >&2
    exit 2
fi
exec "\$@"
FIM
}

modo_raiz() {
    ser_root --raiz
    apagar_marca # interop is on in this phase: the marker goes before anything else
    ler_fixados
    criar_usuario
    instalar_pacotes
    instalar_node
    instalar_ffmpeg
    instalar_ajudantes
    escrever_wslconf true
    msg "Parte de root pronta."
}

# ---- --usuario / --verificar --------------------------------------------------------------------

claude_na_versao() { # `claude --version` prints "<version> (Claude Code)"
    local v=""
    if [ -x "$HOME/.local/bin/claude" ]; then v=$("$HOME/.local/bin/claude" --version 2>/dev/null) || true; fi
    case "$v" in "$CLAUDE_VERSAO" | "$CLAUDE_VERSAO "*) return 0 ;; esac
    return 1
}

# One line per profile: its hash, or sha256sum's error when missing (so created/deleted also differs).
hash_perfis() { sha256sum -- "$HOME/.profile" "$HOME/.bashrc" 2>&1 || true; }

instalar_claude() {
    if claude_na_versao; then
        msg "Claude Code $CLAUDE_VERSAO já instalado."
        return
    fi
    local antes
    baixar "$CLAUDE_URL" "$CLAUDE_SHA256" claude
    chmod 0755 "$TMPD/claude"
    antes=$(hash_perfis)
    # Last step of the official installer, run on the verified binary; install.sh is never fetched.
    # NOT documented whether `install` downloads again by itself: the real-machine test records it.
    "$TMPD/claude" install "$CLAUDE_VERSAO" || die 1 "a instalação do Claude Code falhou."
    # Whether `install` edits shell profiles is not documented: detect it, restore nothing, leave a log line.
    [ "$(hash_perfis)" = "$antes" ] ||
        msg "Aviso: a instalação do Claude Code alterou ~/.profile ou ~/.bashrc; nada foi desfeito."
    claude_na_versao || die 1 "o Claude Code instalado não responde a versão $CLAUDE_VERSAO."
    msg "Claude Code $CLAUDE_VERSAO instalado."
}

# True when the JSON file has the key at the top level or under "plugins" (read defensively).
json_tem() {
    [ -f "$1" ] || return 1
    "$PY" -I -c '
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        d = json.load(f)
except (OSError, ValueError):
    sys.exit(1)
p = d.get("plugins") if isinstance(d, dict) else None
sys.exit(0 if isinstance(d, dict) and (sys.argv[2] in d or (isinstance(p, dict) and sys.argv[2] in p)) else 1)
' "$1" "$2"
}

# Prints a version (manifest "version", or the single user-scope tune-up@tune-up entry); exit 1 otherwise.
VERSAO_PY='
import json, re, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        d = json.load(f)
except (OSError, ValueError):
    sys.exit(1)
if sys.argv[2] == "manifesto":
    v = d.get("version") if isinstance(d, dict) else None
else:
    pl = d.get("plugins") if isinstance(d, dict) else None
    e = pl.get("tune-up@tune-up") if isinstance(pl, dict) else None
    e = [e] if isinstance(e, dict) else e if isinstance(e, list) else []
    e = [x for x in e if isinstance(x, dict) and x.get("scope", "user") == "user"]
    v = e[0].get("version") if len(e) == 1 else None
if not isinstance(v, str) or not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}", v):
    sys.exit(1)
print(v)
'
versao_json() { "$PY" -I -c "$VERSAO_PY" "$1" "$2"; }

# Skips only when the installed version equals the manifest's (the manifest "version" wins in Claude
# Code's computed version: code.claude.com/docs/en/plugins/loading#how-claude-code-computes-the-version).
instalar_plugin() {
    local c="$HOME/.local/bin/claude" pasta="$HOME/.claude/plugins" quer tem
    quer=$(versao_json "$PLUGIN/.claude-plugin/plugin.json" manifesto) ||
        die 1 "$PLUGIN/.claude-plugin/plugin.json sem version válida."
    if json_tem "$pasta/known_marketplaces.json" tune-up; then
        msg "Marketplace tune-up já cadastrado."
    else
        "$c" plugin marketplace add "$PLUGIN" || die 1 "não consegui cadastrar o marketplace do plugin."
    fi
    tem=$(versao_json "$pasta/installed_plugins.json" instalado) || tem=""
    if [ "$tem" = "$quer" ]; then
        msg "Plugin tune-up $quer já instalado."
        return
    fi
    if [ -z "$tem" ]; then
        "$c" plugin install tune-up@tune-up --scope user || die 1 "não consegui instalar o plugin tune-up."
    else
        msg "Plugin tune-up $tem instalado; atualizando para $quer..."
        # Assumption: the marketplace was added from this same --plugin folder (update re-reads its source).
        "$c" plugin marketplace update tune-up || die 1 "não consegui atualizar o marketplace do plugin."
        "$c" plugin update tune-up@tune-up --scope user || die 1 "não consegui atualizar o plugin tune-up."
    fi
    tem=$(versao_json "$pasta/installed_plugins.json" instalado) || tem=""
    [ "$tem" = "$quer" ] || die 1 "o plugin tune-up ficou na versão ${tem:-nenhuma}, esperado $quer."
    msg "Plugin tune-up $quer instalado."
}

instalar_chrome() {
    local d="$HOME/.cache/hyperframes/chrome/chrome-headless-shell/linux-$CHROME_VERSAO" nome selo
    nome=${CHROME_URL##*/}
    nome=${nome%.zip}
    selo="$d/.tune-up.sha256"
    if [ -x "$d/$nome/chrome-headless-shell" ] && [ "$(cat "$selo" 2>/dev/null)" = "$CHROME_SHA256" ]; then
        msg "Chrome $CHROME_VERSAO já instalado."
        return
    fi
    baixar "$CHROME_URL" "$CHROME_SHA256" chrome.zip
    mkdir -p "$TMPD/chrome" "$d"
    unzip -q -o "$TMPD/chrome.zip" -d "$TMPD/chrome" || die 1 "não consegui extrair o Chrome."
    [ -x "$TMPD/chrome/$nome/chrome-headless-shell" ] || die 1 "o zip do Chrome não tem $nome/chrome-headless-shell."
    chmod go-w "$HOME/.cache" "$HOME/.cache/hyperframes" "$HOME/.cache/hyperframes/chrome" \
        "$HOME/.cache/hyperframes/chrome/chrome-headless-shell" "$d"
    rm -rf -- "${d:?}/$nome"
    mv -- "$TMPD/chrome/$nome" "$d/$nome"
    printf '%s\n' "$CHROME_SHA256" >"$selo"
    msg "Chrome $CHROME_VERSAO instalado."
}

modo_usuario() {
    ser_usuario --usuario
    validar_plugin
    ler_fixados
    export HOME="$HOME_U"
    cd "$HOME"
    instalar_claude
    # Plugin commands are kept with --sem-login too (see the container log in the handoff).
    instalar_plugin
    instalar_chrome
    "$PY" -I "$PLUGIN/tune-up-studio/scripts/preparar_estudio.py" --so-instalar ||
        die 1 "a instalação do HyperFrames falhou."
    msg "Parte do usuário pronta."
}

modo_verificar() {
    local nd
    ser_usuario --verificar
    validar_plugin
    export HOME="$HOME_U"
    cd "$HOME"
    nd=$("$PY" -I "$PLUGIN/tune-up-studio/scripts/preparar_estudio.py" --onde) ||
        die 1 "não consegui saber a pasta do HyperFrames."
    case "$nd" in /*) ;; *) die 1 "pasta do HyperFrames inválida: $nd" ;; esac
    exec "$PY" -I "$PLUGIN/tune-up-studio/scripts/verificar_ambiente.py" --projeto "$HOME" --node-dir "$nd"
}

# ---- --marcar -----------------------------------------------------------------------------------

# Runs as root on a file the user can write: no eval, no symlinked file, size cap, prefix checks.
MARCAR_PY='
import datetime, json, os, stat, sys, tempfile
fonte, prefixo, versao, destino, claude_bin, chown = sys.argv[1:7]
hashes = sys.argv[7:12]
def sair(m):
    print("preparar: " + m, file=sys.stderr)
    sys.exit(8)
# Anchor on the literal prefix: realpath(prefixo) would follow a user-owned symlink above it
# (~/.claude or cache -> /mnt/c/...), so any symlink on the prefix itself is refused.
if os.path.realpath(prefixo) != os.path.normpath(prefixo):
    sair("%s contém um link; recusado." % prefixo)
base = os.path.dirname(prefixo.rstrip("/"))
if not os.path.realpath(fonte).startswith(base + os.sep):
    sair("installed_plugins.json fora da pasta do usuário; recusado.")
try:
    fd = os.open(fonte, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as f:
        st = os.fstat(f.fileno())
        if not stat.S_ISREG(st.st_mode) or st.st_size > 1048576:
            sair("installed_plugins.json não é um arquivo comum pequeno.")
        dados = json.loads(f.read().decode("utf-8"))
except (OSError, ValueError):
    sair("não consegui ler installed_plugins.json.")
pl = dados.get("plugins") if isinstance(dados, dict) else None
ents = pl.get("tune-up@tune-up") if isinstance(pl, dict) else None
if isinstance(ents, dict):
    ents = [ents]
if not isinstance(ents, list):
    sair("o plugin tune-up@tune-up não está instalado.")
ents = [e for e in ents if isinstance(e, dict) and e.get("scope", "user") == "user"]
if len(ents) != 1:
    sair("esperava uma instalação de tune-up@tune-up no escopo do usuário.")
cam, ver = ents[0].get("installPath"), ents[0].get("version")
if not isinstance(cam, str) or not isinstance(ver, str) or any(ord(c) < 32 for c in cam):
    sair("installed_plugins.json sem installPath/version válidos.")
if not cam.startswith(prefixo) or ".." in cam.split("/"):
    sair("a pasta do plugin está fora de %s." % prefixo)
real, raiz = os.path.realpath(cam), os.path.normpath(prefixo)
if not real.startswith(raiz + os.sep) or not os.path.isdir(real):
    sair("a pasta do plugin sai de %s (link) ou não existe." % prefixo)
qa = os.path.join(real, "tune-up-studio", "scripts", "qa_video.py")
if not os.path.isfile(qa) or not os.path.realpath(qa).startswith(raiz + os.sep):
    sair("a pasta do plugin não tem tune-up-studio/scripts/qa_video.py.")
if ver != versao:
    sair("o plugin instalado é %s, esperado %s." % (ver, versao))
pasta = os.path.dirname(destino)
os.makedirs(pasta, 0o755, exist_ok=True)
if os.path.islink(pasta) or os.path.islink(destino):
    sair("%s é um link; recusado." % destino)
nomes = ("UBUNTU_SHA256", "NODE_SHA256", "FFMPEG_SHA256", "CLAUDE_SHA256", "CHROME_SHA256")
doc = {"versao": 1, "plugin": versao, "plugin_dir": real, "usuario": "tuneup", "claude_bin": claude_bin,
       "feito_em": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
       "fixados": dict(zip(nomes, hashes))}
fd, tmp = tempfile.mkstemp(dir=pasta, prefix=".pronto.")
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(doc, f, indent=2)
    f.write("\n")
os.chmod(tmp, 0o644)
if chown == "1":
    os.chown(tmp, 0, 0)
os.replace(tmp, destino)
'

modo_marcar() {
    ser_root --marcar
    [[ $PVERSAO =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die 2 "--plugin-versao precisa ser x.y.z."
    if interop_ligado; then die 7 "a ponte com o Windows (interop) está ligada; rode --fechar e reinicie a distro."; fi
    ler_fixados
    local chown=0
    if [ -z "$R" ]; then chown=1; fi
    "$PY" -I -c "$MARCAR_PY" "$HOME_U/.claude/plugins/installed_plugins.json" "$HOME_U/.claude/plugins/cache/" \
        "$PVERSAO" "$MARCA" "$HOME_U/.local/bin/claude" "$chown" \
        "$UBUNTU_SHA256" "$NODE_SHA256" "$FFMPEG_SHA256" "$CLAUDE_SHA256" "$CHROME_SHA256"
    msg "Marca gravada em /etc/tune-up/pronto.json."
}

# ---- main ---------------------------------------------------------------------------------------

MODO=${1:-}
[ $# -eq 0 ] || shift
PLUGIN=""
SEM_LOGIN=0
PVERSAO=""
while [ $# -gt 0 ]; do
    case "$1" in
        --plugin) [ $# -ge 2 ] || uso; PLUGIN=$2; shift 2 ;;
        --sem-login) SEM_LOGIN=1; shift ;;
        --plugin-versao) [ $# -ge 2 ] || uso; PVERSAO=$2; shift 2 ;;
        *) uso ;;
    esac
done
case "$MODO" in
    --raiz | --fechar | --abrir-interop) [ -z "$PLUGIN$PVERSAO" ] && [ "$SEM_LOGIN" = 0 ] || uso ;;
    --usuario) [ -n "$PLUGIN" ] && [ -z "$PVERSAO" ] || uso ;;
    --verificar) [ -n "$PLUGIN" ] && [ -z "$PVERSAO" ] && [ "$SEM_LOGIN" = 0 ] || uso ;;
    --marcar) [ -n "$PVERSAO" ] && [ -z "$PLUGIN" ] && [ "$SEM_LOGIN" = 0 ] || uso ;;
    --versao-plugin) [ -z "$PLUGIN$PVERSAO" ] && [ "$SEM_LOGIN" = 0 ] || uso ;;
    *) uso ;;
esac
case "$MODO" in
    --raiz) modo_raiz ;;
    --usuario) modo_usuario ;;
    --verificar) modo_verificar ;;
    --fechar) ser_root --fechar; escrever_wslconf false; msg "wsl.conf final gravado (ponte desligada)." ;;
    --marcar) modo_marcar ;;
    --abrir-interop) ser_root --abrir-interop; apagar_marca; escrever_wslconf true; msg "Ponte ligada para o login." ;;
    --versao-plugin) ser_usuario --versao-plugin; versao_json "$HOME_U/.claude/plugins/installed_plugins.json" instalado || exit 1 ;;
esac
