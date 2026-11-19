#!/usr/bin/env bash
# CI proof (criterion C5): runs preparar.sh inside a bare ubuntu:24.04 container, as root then as tuneup.
# Needs GITHUB_WORKSPACE (the plugin checkout). CI_SO_RAIZ=1 stops after the first --raiz (local dry run).
set -euo pipefail
falhar() { echo "::error::$*"; exit 1; }

# Gate on the --verificar report: require each essential item to be [ok], not just "no [falta]",
# so a die/traceback before verificar_ambiente.py prints anything cannot pass. Args: report file, exit code.
checar_relatorio() {
    local r=$1 c=$2 item
    case "$c" in 0|1) ;; *) falhar "--verificar saiu com codigo $c (esperado 0 ou 1)" ;; esac
    grep -Eq '^(Pronto para o estúdio\.|Não está pronto:)' "$r" || falhar "--verificar sem linha de resumo"
    # bwrap/socat/sandbox lines may be [falta] in a container: printed, not fatal.
    if grep -Ei '^\[falta\].*(node|ffmpeg|ffprobe|hyperframes|chrome)' "$r"; then
        falhar "--verificar: item essencial faltando (linhas acima)"
    fi
    for item in node ffprobe ffmpeg hyperframes chrome; do
        grep -Eq "^\[ok\] +$item:" "$r" || falhar "--verificar: sem linha [ok] para $item"
    done
}
if [ "${1:-}" = --checar-relatorio ]; then checar_relatorio "$2" "$3"; echo "relatorio OK"; exit 0; fi

W=${GITHUB_WORKSPACE:?GITHUB_WORKSPACE nao definido}
L=/usr/local/lib/tune-up
LOG=$(mktemp -d)

# The image ships an "ubuntu" user on uid 1000; preparar.sh needs that uid for tuneup.
if id ubuntu >/dev/null 2>&1; then userdel -r ubuntu; fi

# Same copy the Windows installer does: root-owned, not writable by the user.
install -D -o root -g root -m 0755 "$W/scripts/wsl/preparar.sh" "$L/preparar.sh"
install -D -o root -g root -m 0755 "$W/scripts/wsl/medir.sh" "$L/medir.sh"
install -D -o root -g root -m 0644 "$W/scripts/wsl/fixados.env" "$L/fixados.env"

# The checkout is made by root; uid 1000 must read it (and traverse every parent).
chmod -R a+rX "$W"
d=$W; while [ "$d" != / ]; do chmod a+rx "$d"; d=$(dirname "$d"); done

raiz() { bash "$L/preparar.sh" --raiz; }
usuario() {
    setpriv --reuid 1000 --regid 1000 --init-groups \
        env HOME=/home/tuneup PATH=/usr/local/bin:/usr/bin:/bin \
        bash "$L/preparar.sh" --usuario --sem-login --plugin "$W"
}

raiz 2>&1 | tee "$LOG/raiz1.txt"
[ "${CI_SO_RAIZ:-0}" = 1 ] && { echo "parou apos --raiz (CI_SO_RAIZ=1)"; exit 0; }
usuario 2>&1 | tee "$LOG/usuario1.txt"

echo "== --verificar =="
set +e
setpriv --reuid 1000 --regid 1000 --init-groups \
    env HOME=/home/tuneup PATH=/usr/local/bin:/usr/bin:/bin \
    bash "$L/preparar.sh" --verificar --plugin "$W" >"$LOG/verificar.txt" 2>&1
VC=$?
set -e
cat "$LOG/verificar.txt"
checar_relatorio "$LOG/verificar.txt" "$VC"

echo "== idempotencia =="
raiz 2>&1 | tee "$LOG/raiz2.txt"
usuario 2>&1 | tee "$LOG/usuario2.txt"
for f in raiz2 usuario2; do
    ! grep -q Baixando "$LOG/$f.txt" || falhar "$f baixou de novo (nao idempotente)"
done

echo "== ldd do chrome =="
CH=$(find /home/tuneup/.cache/hyperframes/chrome -type f -name chrome-headless-shell | head -1)
[ -n "$CH" ] || falhar "chrome-headless-shell nao encontrado"
LDD=$(ldd "$CH" 2>&1) || true
echo "$LDD"
! grep -q "not found" <<<"$LDD" || falhar "chrome-headless-shell com bibliotecas faltando"
echo "conteiner OK"
