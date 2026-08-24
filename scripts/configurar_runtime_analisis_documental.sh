#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/sicode/app}"
SERVICE="${SICODE_SERVICE:-sicode.service}"
NGINX_CONF="/etc/nginx/conf.d/sicode_analysis_timeout.conf"
SYSTEMD_DIR="/etc/systemd/system/${SERVICE}.d"
SYSTEMD_CONF="${SYSTEMD_DIR}/analysis-timeout.conf"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Ejecute este script con sudo." >&2
  exit 1
fi

if [[ ! -d "${APP_DIR}" ]]; then
  echo "No existe ${APP_DIR}." >&2
  exit 1
fi

mkdir -p "${SYSTEMD_DIR}"
install -m 0644 "${APP_DIR}/deploy/systemd/sicode-analysis-timeout.conf" "${SYSTEMD_CONF}"
install -m 0644 "${APP_DIR}/deploy/nginx/sicode-analysis-timeout.conf" "${NGINX_CONF}"

# Mantiene el límite de subida existente si ya fue configurado. Si no existe,
# crea uno separado para que PDFs de hasta 40 MB lleguen a Flask.
if ! nginx -T 2>/dev/null | grep -qE '^[[:space:]]*client_max_body_size[[:space:]]+'; then
  cat > /etc/nginx/conf.d/sicode_upload.conf <<'EOF'
client_max_body_size 50M;
EOF
fi

nginx -t
systemctl daemon-reload
systemctl restart "${SERVICE}"
systemctl reload nginx

printf '\n===== Gunicorn =====\n'
systemctl show "${SERVICE}" -p Environment
printf '\n===== Nginx =====\n'
nginx -T 2>/dev/null | grep -E 'client_max_body_size|proxy_(connect|send|read)_timeout|send_timeout' || true
printf '\n===== Estado SICODE =====\n'
systemctl --no-pager --full status "${SERVICE}" | sed -n '1,18p'

echo
echo "Runtime de análisis documental configurado."
