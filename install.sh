#!/bin/sh
set -eu

REPOSITORY="swetoast/play_presence"
BRANCH="main"
WORK="/tmp/play-presence.$$"
ARCHIVE="$WORK/play-presence.tar.gz"
SOURCE="$WORK/source"
APP="/opt/play-presence"
CONFIG_DIR="/etc/play-presence"
INSTALLED_CONFIG="$CONFIG_DIR/config.json"
INSTALLED_PASSWORD="$CONFIG_DIR/mqtt-password"
RUNTIME="/run/play-presence"
SERVICE="play-presence.service"
UNIT="/etc/systemd/system/$SERVICE"

cleanup() {
    PASSWORD=""
    rm -rf "$WORK"
}
trap cleanup EXIT INT TERM HUP

fail() {
    printf 'Play Presence: %s\n' "$1" >&2
    exit 1
}

prompt() {
    label=$1
    default=$2
    if [ -n "$default" ]; then
        printf '%s [%s]: ' "$label" "$default" > /dev/tty
    else
        printf '%s: ' "$label" > /dev/tty
    fi
    IFS= read -r value < /dev/tty || value=""
    [ -n "$value" ] || value=$default
    printf '%s' "$value"
}

require_root() {
    [ "$(id -u)" -eq 0 ] || fail "run this script as root"
}

usage() {
    cat <<'EOF'
Usage: ./install.sh [command]

Commands:
  install       Interactive installation or update. This is the default.
  uninstall     Completely remove Play Presence, including configuration and credentials.
  help          Show this help text.
EOF
}

confirm() {
    message=$1
    printf '%s [y/N]: ' "$message" > /dev/tty
    IFS= read -r answer < /dev/tty || answer=""
    case "$answer" in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

uninstall_play_presence() {
    require_root
    [ -r /dev/tty ] || fail "an interactive terminal is required"

    confirm "Completely remove Play Presence, including configuration and MQTT credentials?" || {
        echo "Uninstall cancelled."
        return 0
    }

    systemctl disable --now "$SERVICE" >/dev/null 2>&1 || true
    rm -f "$UNIT" "$UNIT.previous"
    systemctl daemon-reload
    systemctl reset-failed "$SERVICE" >/dev/null 2>&1 || true

    rm -rf "$APP" "$CONFIG_DIR" "$RUNTIME"

    echo "Play Presence has been completely removed."
}

download_source() {
    command -v python3 >/dev/null 2>&1 || fail "python3 is required"
    command -v tar >/dev/null 2>&1 || fail "tar is required"

    mkdir -p "$SOURCE"
    url="https://github.com/$REPOSITORY/archive/refs/heads/$BRANCH.tar.gz"
    printf 'Downloading Play Presence...\n'

    if command -v curl >/dev/null 2>&1; then
        curl -fL --retry 3 --connect-timeout 20 -o "$ARCHIVE" "$url" || fail "download failed"
    elif command -v wget >/dev/null 2>&1; then
        wget -O "$ARCHIVE" "$url" || fail "download failed"
    else
        fail "curl or wget is required"
    fi

    [ -s "$ARCHIVE" ] || fail "downloaded archive is empty"
    tar -xzf "$ARCHIVE" -C "$SOURCE" || fail "archive extraction failed"
    PROJECT=$(find "$SOURCE" -mindepth 1 -maxdepth 1 -type d | head -n 1)
    [ -n "$PROJECT" ] || fail "project directory was not found"
    [ -f "$PROJECT/deploy/install.py" ] || fail "deploy/install.py is missing"
    [ -f "$PROJECT/pyproject.toml" ] || fail "pyproject.toml is missing"
    [ -f "$PROJECT/config/config.example.json" ] || fail "config/config.example.json is missing"
}

read_installed_defaults() {
    DEFAULT_HOST="10.0.0.5"
    DEFAULT_PORT="1883"
    DEFAULT_USERNAME=""
    DEFAULT_TOPIC_PREFIX="rg40xxv"

    [ -f "$INSTALLED_CONFIG" ] || return 0
    eval "$(python3 - "$INSTALLED_CONFIG" <<'PY'
import json
import shlex
import sys
from pathlib import Path

try:
    mqtt = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")).get("mqtt", {})
except Exception:
    mqtt = {}

values = {
    "DEFAULT_HOST": str(mqtt.get("host", "10.0.0.5")),
    "DEFAULT_PORT": str(mqtt.get("port", 1883)),
    "DEFAULT_USERNAME": str(mqtt.get("username", "")),
    "DEFAULT_TOPIC_PREFIX": str(mqtt.get("topic_prefix", "rg40xxv")),
}
for key, value in values.items():
    print(f"{key}={shlex.quote(value)}")
PY
)"
}

collect_mqtt_configuration() {
    read_installed_defaults
    printf '\nMQTT configuration\n'
    MQTT_HOST=$(prompt "MQTT host" "$DEFAULT_HOST")
    MQTT_PORT=$(prompt "MQTT port" "$DEFAULT_PORT")
    MQTT_USERNAME=$(prompt "MQTT username" "$DEFAULT_USERNAME")
    MQTT_TOPIC_PREFIX=$(prompt "MQTT topic prefix" "$DEFAULT_TOPIC_PREFIX")

    [ -n "$MQTT_HOST" ] || fail "MQTT host cannot be empty"
    [ -n "$MQTT_USERNAME" ] || fail "MQTT username cannot be empty"
    [ -n "$MQTT_TOPIC_PREFIX" ] || fail "MQTT topic prefix cannot be empty"
    case "$MQTT_PORT" in
        ''|*[!0-9]*) fail "MQTT port must be a number" ;;
    esac
    [ "$MQTT_PORT" -ge 1 ] && [ "$MQTT_PORT" -le 65535 ] || fail "MQTT port must be between 1 and 65535"

    printf 'MQTT password: ' > /dev/tty
    stty -echo < /dev/tty 2>/dev/null || true
    IFS= read -r PASSWORD < /dev/tty || PASSWORD=""
    stty echo < /dev/tty 2>/dev/null || true
    printf '\n' > /dev/tty
    [ -n "$PASSWORD" ] || fail "MQTT password cannot be empty"

    umask 077
    TEMP_PASSWORD="$WORK/mqtt-password"
    printf '%s\n' "$PASSWORD" > "$TEMP_PASSWORD"
    PASSWORD=""

    TEMP_CONFIG="$WORK/config.json"
    BASE_CONFIG="$PROJECT/config/config.example.json"
    [ ! -f "$INSTALLED_CONFIG" ] || BASE_CONFIG="$INSTALLED_CONFIG"

    MQTT_HOST="$MQTT_HOST" \
    MQTT_PORT="$MQTT_PORT" \
    MQTT_USERNAME="$MQTT_USERNAME" \
    MQTT_TOPIC_PREFIX="$MQTT_TOPIC_PREFIX" \
    python3 - "$BASE_CONFIG" "$TEMP_CONFIG" <<'PY'
import json
import os
import sys
from pathlib import Path

source = Path(sys.argv[1])
target = Path(sys.argv[2])
data = json.loads(source.read_text(encoding="utf-8"))
mqtt = data.setdefault("mqtt", {})
mqtt["host"] = os.environ["MQTT_HOST"]
mqtt["port"] = int(os.environ["MQTT_PORT"])
mqtt["username"] = os.environ["MQTT_USERNAME"]
mqtt["password_file"] = "/etc/play-presence/mqtt-password"
mqtt["client_id"] = "play-presence"
mqtt["topic_prefix"] = os.environ["MQTT_TOPIC_PREFIX"].strip("/")
mqtt.setdefault("keepalive_seconds", 60)
target.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
PY
}

install_play_presence() {
    require_root
    [ -r /dev/tty ] || fail "an interactive terminal is required"
    download_source
    collect_mqtt_configuration

    printf '\nInstalling Play Presence...\n'
    cd "$PROJECT"
    python3 deploy/install.py --config "$TEMP_CONFIG" --password-file "$TEMP_PASSWORD"

    printf '\nPlay Presence installation complete.\n'
    PYTHONPATH="$APP/src" python3 -m play_presence --version
    systemctl --no-pager --full status "$SERVICE" 2>/dev/null | sed -n '1,10p' || true
}

command=${1:-install}
case "$command" in
    install) install_play_presence ;;
    uninstall) uninstall_play_presence ;;
    help|-h|--help) usage ;;
    *) usage >&2; fail "unknown command: $command" ;;
esac
