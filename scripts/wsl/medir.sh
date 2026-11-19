#!/usr/bin/env bash
# medir.sh: in-distro measurements M3..M8 of the tune-up WSL real-machine proof. Records only: it never edits
# wsl.conf, never terminates anything and never writes the marker. The Windows installer copies it to
# /usr/local/lib/tune-up/ and runs, as the tuneup user:
#   wsl.exe -d tune-up -u tuneup --exec /bin/bash /usr/local/lib/tune-up/medir.sh <mode> --plugin <dir>
# Modes (one per measurement group): --bwrap (M3, M4), --interop (M5), --sistema (M6 kernel, M7, M8), --tudo.
# Every result is one line `M<n>: <OK|FALHOU|REGISTRO> - <text>`, detail lines start with two spaces.
# Exit: 0 recorded, 2 usage, 3 wrong user, 9 M5 failed (cmd.exe ran: STOP).
# Tests only: TUNE_UP_RAIZ_TESTE=<dir> prefixes /etc, /run/WSL, /proc/sys and /mnt (and TUNE_UP_UID_TESTE stands
# in for the uid); both are honoured only when the real uid is not 0, like preparar.sh.
set -euo pipefail
export LC_ALL=C
umask 077

UID_REAL=$EUID
if [ -z "${TUNE_UP_RAIZ_TESTE:-}" ] || [ "$UID_REAL" = 0 ]; then
    PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
    export PATH
fi
TMPD=""
trap 'if [ -n "$TMPD" ]; then rm -rf -- "$TMPD"; fi' EXIT
die() { printf 'medir: %s\n' "$2" >&2; exit "$1"; }
linha() { printf 'M%s: %s\n' "$1" "$2"; }
detalhe() { printf '  %s\n' "$*"; }

R=""
EU=$UID_REAL
if [ -n "${TUNE_UP_RAIZ_TESTE:-}" ] && [ "$UID_REAL" != 0 ]; then
    [[ $TUNE_UP_RAIZ_TESTE =~ ^/[A-Za-z0-9._/-]+$ ]] || die 3 "TUNE_UP_RAIZ_TESTE: caminho absoluto, sem espaço."
    R=$(cd "$TUNE_UP_RAIZ_TESTE" && pwd -P) || die 3 "TUNE_UP_RAIZ_TESTE não existe."
    EU=${TUNE_UP_UID_TESTE:-$UID_REAL}
fi
[ "$EU" != 0 ] || die 3 "medir.sh não roda como root; use o usuário tuneup."

uso() {
    cat >&2 <<'FIM'
Uso: medir.sh <--bwrap|--interop|--sistema|--tudo> --plugin <pasta absoluta do plugin>
FIM
    exit 2
}

MODO=${1:-}
[ $# -ge 1 ] || uso
shift
PLUGIN=""
while [ $# -gt 0 ]; do
    case "$1" in
        --plugin) [ $# -ge 2 ] || uso; PLUGIN=$2; shift 2 ;;
        *) uso ;;
    esac
done
case "$MODO" in --bwrap | --interop | --sistema | --tudo) ;; *) uso ;; esac
case "$PLUGIN" in /*) ;; *) die 2 "--plugin precisa ser um caminho absoluto." ;; esac
case "/$PLUGIN/" in */../* | */./*) die 2 "--plugin não aceita '..' nem '.'." ;; esac
[ -d "$PLUGIN" ] || die 2 "--plugin: $PLUGIN não é uma pasta."
TMPD=$(mktemp -d)

CMD_EXE="$R/mnt/c/Windows/System32/cmd.exe"
# Sandbox shape shared by M4 and M5: read-only root, writable project dir (the cwd), no network namespace tricks.
sandbox() { bwrap --unshare-user --ro-bind / / --dev /dev --proc /proc --bind "$PLUGIN" "$PLUGIN" --chdir "$PLUGIN" "$@"; }

medir_bwrap() {
    local rc=0 sys="ausente" perfil="nao" saida
    bwrap --unshare-user true >/dev/null 2>&1 || rc=$?
    if v=$(sysctl -n kernel.apparmor_restrict_unprivileged_userns 2>/dev/null); then sys=$v; fi
    [ ! -e "$R/etc/apparmor.d/bwrap" ] || perfil="sim"
    if [ "$rc" = 0 ]; then st=OK; else st=FALHOU; fi
    linha 3 "$st - bwrap --unshare-user true saiu com $rc; sysctl apparmor_restrict_unprivileged_userns=$sys; perfil /etc/apparmor.d/bwrap: $perfil (só anotado, nada aplicado)"
    # M4: the full Claude-sandbox variant (settings sandbox + cwd on /mnt/c) is covered by the Part C proof;
    # here bwrap is used directly with the project dir (on /mnt/c in a real run) bound and as cwd.
    saida=$(sandbox /bin/echo ok 2>&1) && rc=0 || rc=$?
    if [ "$rc" = 0 ] && [ "$saida" = ok ]; then
        linha 4 "OK - comando no sandbox com cwd em $PLUGIN rodou echo ok"
    else
        linha 4 "FALHOU - sandbox com cwd em $PLUGIN saiu com $rc"
    fi
}

medir_interop() {
    local rc_env=0 n=0 f rc_fora=0 rc_dentro=0 binfmt=nao
    printenv WSL_INTEROP >/dev/null 2>&1 || rc_env=$?
    for f in "$R"/run/WSL/*_interop; do [ -e "$f" ] && n=$((n + 1)); done
    [ ! -e "$R/proc/sys/fs/binfmt_misc/WSLInterop" ] || binfmt=sim
    "$CMD_EXE" /c echo x >/dev/null 2>&1 || rc_fora=$?
    sandbox "$CMD_EXE" /c echo x >/dev/null 2>&1 || rc_dentro=$?
    detalhe "printenv WSL_INTEROP saiu com $rc_env (esperado 1); arquivos *_interop em /run/WSL: $n (esperado 0)"
    detalhe "binfmt_misc/WSLInterop existe: $binfmt (só anotado; no WSL2 existe sempre, não é sinal)"
    if [ "$rc_fora" = 0 ] || [ "$rc_dentro" = 0 ]; then
        linha 5 "FALHOU - PARE: cmd.exe RODOU (fora do sandbox: $rc_fora, dentro: $rc_dentro; 0 = rodou)"
        return 9
    fi
    linha 5 "OK - cmd.exe falhou fora ($rc_fora) e dentro do sandbox ($rc_dentro); WSL_INTEROP rc=$rc_env; *_interop=$n"
}

medir_sistema() {
    linha 6 "REGISTRO - kernel $(uname -r)"
    local base="$PLUGIN/tune-up-studio/node" t0 rc=0 outros
    if [ -f "$base/package-lock.json" ] && [ -f "$base/package.json" ]; then
        cp -- "$base/package.json" "$base/package-lock.json" "$TMPD/"
        # npm writes its cache under HOME by default; keep every write inside the temp dir.
        t0=$SECONDS
        (cd "$TMPD" && npm_config_cache="$TMPD/cache" npm_config_update_notifier=false \
            npm ci --ignore-scripts --no-audit --no-fund >/dev/null 2>&1) || rc=$?
        if [ "$rc" = 0 ]; then
            linha 7 "REGISTRO - npm ci no disco Linux levou $((SECONDS - t0)) s"
        else
            linha 7 "FALHOU - npm ci saiu com $rc depois de $((SECONDS - t0)) s (rede ou lockfile?)"
        fi
    else
        linha 7 "FALHOU - não achei package.json e package-lock.json em $base"
    fi
    outros=$(awk -F: '$3 == 1000 && $1 != "tuneup" { printf "%s ", $1 }' "$R/etc/passwd" 2>/dev/null || true)
    if [ -z "$outros" ]; then
        linha 8 "OK - nenhum usuário com uid 1000 além de tuneup em /etc/passwd"
    else
        linha 8 "FALHOU - o rootfs já traz usuário com uid 1000: ${outros% } (vira ajuste antes da Parte C)"
    fi
}

rc_final=0
case "$MODO" in
    --bwrap) medir_bwrap ;;
    --interop) medir_interop || rc_final=$? ;;
    --sistema) medir_sistema ;;
    --tudo) medir_bwrap; medir_interop || rc_final=$?; medir_sistema ;;
esac
exit "$rc_final"
