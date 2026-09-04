#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${SICODE_APP_DIR:-/opt/sicode/app}"
VENV_DIR="${SICODE_VENV_DIR:-/opt/sicode/venv}"
SICODE_USER="${SICODE_SERVICE_USER:-$(stat -c '%U' "$APP_DIR")}" 
PYTHON_BIN="${SICODE_PYTHON:-$VENV_DIR/bin/python}"

[[ -d "$APP_DIR" ]] || { echo "ERROR: no existe $APP_DIR"; exit 2; }
[[ -x "$PYTHON_BIN" ]] || { echo "ERROR: no existe Python ejecutable en $PYTHON_BIN"; exit 3; }
[[ -f "$APP_DIR/.env" ]] || { echo "ERROR: falta $APP_DIR/.env"; exit 4; }

SERVICE_TEMPLATE="$APP_DIR/deploy/systemd/sicode-backup.service.template"
TIMER_TEMPLATE="$APP_DIR/deploy/systemd/sicode-backup.timer.template"
[[ -f "$SERVICE_TEMPLATE" && -f "$TIMER_TEMPLATE" ]] || { echo "ERROR: faltan plantillas de systemd"; exit 5; }

TMP_SERVICE="$(mktemp)"
TMP_TIMER="$(mktemp)"
trap 'rm -f "$TMP_SERVICE" "$TMP_TIMER"' EXIT

sed \
  -e "s|__SICODE_USER__|$SICODE_USER|g" \
  -e "s|__SICODE_APPDIR__|$APP_DIR|g" \
  -e "s|__SICODE_PYTHON__|$PYTHON_BIN|g" \
  "$SERVICE_TEMPLATE" > "$TMP_SERVICE"
cp "$TIMER_TEMPLATE" "$TMP_TIMER"

sudo install -o root -g root -m 0644 "$TMP_SERVICE" /etc/systemd/system/sicode-backup.service
sudo install -o root -g root -m 0644 "$TMP_TIMER" /etc/systemd/system/sicode-backup.timer
sudo systemctl daemon-reload

# Ejecutar una vez antes de programar: si el backup falla, no dejamos un timer
# que aparente estar configurado correctamente.
sudo systemctl start sicode-backup.service
sudo systemctl is-failed --quiet sicode-backup.service && {
  sudo systemctl status sicode-backup.service --no-pager || true
  exit 6
}

sudo systemctl enable --now sicode-backup.timer

echo "Backup programado instalado correctamente."
echo "Usuario del servicio: $SICODE_USER"
echo "Python: $PYTHON_BIN"
systemctl list-timers sicode-backup.timer --no-pager
