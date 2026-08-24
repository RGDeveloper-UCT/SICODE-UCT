#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/sicode/app}"
SERVICE="${SICODE_SERVICE:-sicode.service}"
SYSTEMD_DIR="/etc/systemd/system/${SERVICE}.d"
SYSTEMD_CONF="${SYSTEMD_DIR}/analysis-timeout.conf"
# Archivo creado por una versión anterior del instalador. Puede colisionar con
# sicode_timeout.conf si ambos declaran proxy_*_timeout en el contexto http.
LEGACY_NGINX_CONF="/etc/nginx/conf.d/sicode_analysis_timeout.conf"
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

# No instalamos un segundo bloque global de proxy timeouts. En instalaciones
# existentes SICODE puede tener /etc/nginx/conf.d/sicode_timeout.conf y Nginx
# rechaza dos directivas iguales en el mismo contexto. Si quedó el archivo
# administrado por una versión anterior, lo retiramos conservando backup.
if [[ -f "${LEGACY_NGINX_CONF}" ]]; then
  legacy_backup="${LEGACY_NGINX_CONF}.bak-${STAMP}"
  cp -a "${LEGACY_NGINX_CONF}" "${legacy_backup}"
  rm -f "${LEGACY_NGINX_CONF}"
  echo "Se retiró ${LEGACY_NGINX_CONF} para evitar directivas duplicadas (backup: ${legacy_backup})."
fi

# Detecta exclusivamente configuraciones activas de Nginx (.conf y nginx.conf),
# nunca copias .bak, que apunten al Gunicorn local de SICODE.
SICODE_PROXY_FILES=()
CANDIDATOS=(/etc/nginx/nginx.conf)
while IFS= read -r archivo; do
  CANDIDATOS+=("${archivo}")
done < <(find /etc/nginx/conf.d -maxdepth 1 -type f -name '*.conf' -print 2>/dev/null | sort)

for candidato in "${CANDIDATOS[@]}"; do
  [[ -f "${candidato}" ]] || continue
  if grep -qE 'proxy_pass[[:space:]]+http://(127\.0\.0\.1|localhost):8000' "${candidato}"; then
    SICODE_PROXY_FILES+=("${candidato}")
  fi
done

# Los timeouts dentro del server/location de SICODE tienen precedencia sobre un
# valor global. Solo modificamos directivas que ya existen en el virtual host,
# dejando una copia de seguridad antes del cambio.
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
  echo "Aviso: no se encontró un proxy_pass directo a 127.0.0.1:8000/localhost:8000." >&2
  echo "No se modificaron timeouts de Nginx; revise el virtual host de SICODE manualmente." >&2
fi

# Mantiene el límite de subida existente si ya fue configurado. Se usa grep
# directo porque nginx -T no es fiable mientras exista una configuración previa
# inválida que justamente este script intenta reparar.
if ! grep -RqsE '^[[:space:]]*client_max_body_size[[:space:]]+' /etc/nginx/nginx.conf /etc/nginx/conf.d 2>/dev/null; then
  cat > /etc/nginx/conf.d/sicode_upload.conf <<'EOF'
client_max_body_size 50M;
EOF
fi

# No reiniciamos nada hasta confirmar que la configuración de Nginx es válida.
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
