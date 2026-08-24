#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/sicode/app}"
SERVICE="${SICODE_SERVICE:-sicode.service}"
NGINX_CONF="/etc/nginx/conf.d/sicode_analysis_timeout.conf"
SYSTEMD_DIR="/etc/systemd/system/${SERVICE}.d"
SYSTEMD_CONF="${SYSTEMD_DIR}/analysis-timeout.conf"
STAMP="$(date +%Y%m%d%H%M%S)"

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

# Si la configuración del virtual host de SICODE fija timeouts dentro de
# server/location, esos valores prevalecen sobre los definidos en http. Se
# localizan únicamente archivos que apuntan al Gunicorn local de SICODE y se
# actualizan los timeouts existentes, dejando una copia de seguridad.
mapfile -t SICODE_PROXY_FILES < <(
  grep -RlE 'proxy_pass[[:space:]]+http://(127\.0\.0\.1|localhost):8000' \
    /etc/nginx/nginx.conf /etc/nginx/conf.d 2>/dev/null || true
)

for proxy_file in "${SICODE_PROXY_FILES[@]:-}"; do
  [[ -f "${proxy_file}" ]] || continue
  backup="${proxy_file}.bak-sicode-analysis-${STAMP}"
  cp -a "${proxy_file}" "${backup}"

  sed -i -E \
    -e 's/^([[:space:]]*)proxy_connect_timeout[[:space:]]+[^;]+;/\1proxy_connect_timeout 60s;/' \
    -e 's/^([[:space:]]*)proxy_send_timeout[[:space:]]+[^;]+;/\1proxy_send_timeout 600s;/' \
    -e 's/^([[:space:]]*)proxy_read_timeout[[:space:]]+[^;]+;/\1proxy_read_timeout 600s;/' \
    -e 's/^([[:space:]]*)send_timeout[[:space:]]+[^;]+;/\1send_timeout 600s;/' \
    "${proxy_file}"

  echo "Timeouts ajustados en ${proxy_file} (backup: ${backup})."
done

if [[ "${#SICODE_PROXY_FILES[@]}" -eq 0 ]]; then
  echo "Aviso: no se encontró un proxy_pass directo a 127.0.0.1:8000; se mantiene el perfil global de 600 s." >&2
fi

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
printf '\n===== Nginx general =====\n'
nginx -T 2>/dev/null | grep -E 'client_max_body_size|proxy_(connect|send|read)_timeout|send_timeout' || true

if [[ "${#SICODE_PROXY_FILES[@]}" -gt 0 ]]; then
  printf '\n===== Virtual host SICODE =====\n'
  for proxy_file in "${SICODE_PROXY_FILES[@]}"; do
    echo "--- ${proxy_file}"
    grep -nE 'proxy_pass|proxy_(connect|send|read)_timeout|send_timeout' "${proxy_file}" || true
  done
fi

printf '\n===== Estado SICODE =====\n'
systemctl --no-pager --full status "${SERVICE}" | sed -n '1,18p'

echo
echo "Runtime de análisis documental configurado."
