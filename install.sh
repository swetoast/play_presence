#!/bin/sh
set -eu

REPOSITORY="swetoast/play_presence"
BRANCH="main"
WORK="/tmp/play-presence-install.$$"
ARCHIVE="$WORK/play-presence.tar.gz"
SOURCE="$WORK/source"

cleanup() {
    rm -rf "$WORK"
}
trap cleanup EXIT INT TERM HUP

fail() {
    printf 'Play Presence install failed: %s\n' "$1" >&2
    exit 1
}

[ "$(id -u)" -eq 0 ] || fail "run this installer as root"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
command -v tar >/dev/null 2>&1 || fail "tar is required"

mkdir -p "$SOURCE"
URL="https://github.com/$REPOSITORY/archive/refs/heads/$BRANCH.tar.gz"

printf 'Downloading Play Presence...\n'
if command -v curl >/dev/null 2>&1; then
    curl -fL --retry 3 --connect-timeout 20 -o "$ARCHIVE" "$URL" || fail "download failed"
elif command -v wget >/dev/null 2>&1; then
    wget -O "$ARCHIVE" "$URL" || fail "download failed"
else
    fail "curl or wget is required"
fi

[ -s "$ARCHIVE" ] || fail "downloaded archive is empty"
tar -xzf "$ARCHIVE" -C "$SOURCE" || fail "archive extraction failed"
PROJECT=$(find "$SOURCE" -mindepth 1 -maxdepth 1 -type d | head -n 1)
[ -n "$PROJECT" ] || fail "project directory was not found"
[ -f "$PROJECT/deploy/install.py" ] || fail "deploy/install.py is missing from the repository"
[ -f "$PROJECT/pyproject.toml" ] || fail "pyproject.toml is missing from the repository"

set -- "$@"
PASSWORD_FILE="/etc/rg40xx-game-presence/mqtt-password"
HAS_PASSWORD_ARGUMENT=0
for argument in "$@"; do
    [ "$argument" = "--password-file" ] && HAS_PASSWORD_ARGUMENT=1
done

if [ ! -s "$PASSWORD_FILE" ] && [ "$HAS_PASSWORD_ARGUMENT" -eq 0 ]; then
    [ -r /dev/tty ] || fail "first installation needs --password-file"
    TEMP_PASSWORD="$WORK/mqtt-password"
    printf 'MQTT password: ' > /dev/tty
    stty -echo < /dev/tty 2>/dev/null || true
    IFS= read -r PASSWORD < /dev/tty || PASSWORD=""
    stty echo < /dev/tty 2>/dev/null || true
    printf '\n' > /dev/tty
    [ -n "$PASSWORD" ] || fail "MQTT password cannot be empty"
    umask 077
    printf '%s\n' "$PASSWORD" > "$TEMP_PASSWORD"
    PASSWORD=""
    set -- --password-file "$TEMP_PASSWORD" "$@"
fi

printf 'Installing Play Presence...\n'
cd "$PROJECT"
python3 deploy/install.py "$@"

printf 'Play Presence installation complete.\n'
PYTHONPATH=/opt/rg40xx-game-presence/src python3 -m rg40xx_game_presence --version
systemctl --no-pager --full status rg40xx-game-presence.service 2>/dev/null | sed -n '1,8p' || true
