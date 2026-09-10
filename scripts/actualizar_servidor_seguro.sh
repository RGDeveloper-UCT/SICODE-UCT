#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${SICODE_APP_DIR:-/opt/sicode/app}"
VENV_DIR="${SICODE_VENV_DIR:-/opt/sicode/venv}"
BRANCH="${SICODE_BRANCH:-main}"
RUN_TESTS="${SICODE_RUN_TESTS:-1}"
SERVICE="${SICODE_SERVICE:-sicode.service}"
IA_WORKER_SERVICE="${SICODE_IA_WORKER_SERVICE:-sicode-ia-worker.service}"

cd "$APP_DIR"
source "$VENV_DIR/bin/activate"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: existen cambios locales en $APP_DIR. No se actualizará el servidor."
  git status --short
  exit 2
fi

PREVIOUS_COMMIT="$(git rev-parse HEAD)"
echo "Commit actual: $PREVIOUS_COMMIT"

echo "[1/10] Verificando configuración crítica"
grep -q '^SECRET_KEY=.' .env || { echo 'FALTA SECRET_KEY'; exit 3; }
grep -q '^DATABASE_URL=.' .env || { echo 'FALTA DATABASE_URL'; exit 3; }

echo "[2/10] Generando backup PostgreSQL antes de tocar código o migraciones"
BACKUP_PATH="$(python - <<'PY'
from app import create_app
from app.services.backup_service import generar_backup

app = create_app()
with app.app_context():
    ruta = generar_backup(app.config['SQLALCHEMY_DATABASE_URI'])
    print(ruta)
PY
)"
[[ -s "$BACKUP_PATH" ]] || { echo "ERROR: backup inválido: $BACKUP_PATH"; exit 4; }
echo "Backup validado: $BACKUP_PATH"

echo "[3/10] Actualizando código con fast-forward únicamente"
git fetch --prune origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"
NEW_COMMIT="$(git rev-parse HEAD)"
echo "Nuevo commit: $NEW_COMMIT"

echo "[4/10] Instalando y validando dependencias"
python -m pip install --disable-pip-version-check -r requirements.txt
python -m pip check

echo "[5/10] Compilando y validando cabeza de migraciones"
python -m compileall -q app migrations tests
python -m flask --app run.py db heads

if [[ "$RUN_TESTS" == "1" ]]; then
  echo "[6/10] Ejecutando pruebas de regresión antes de migrar producción"
  # tests/conftest.py impide utilizar la DATABASE_URL productiva y deriva pytest a una BD de pruebas.
  pytest -q \
    tests/test_auditoria_hardening.py \
    tests/test_indice_documental_foliacion_anexos.py \
    tests/test_estado_documental.py \
    tests/test_security.py \
    tests/test_visor_solo_lectura.py \
    tests/test_monitoreo_anexos.py \
    tests/test_anexos_inteligentes.py \
    tests/test_admin_anexos_asistidos.py \
    tests/test_control_integridad.py \
    tests/test_backup.py
else
  echo "[6/10] Pruebas omitidas por SICODE_RUN_TESTS=$RUN_TESTS"
fi

echo "[7/10] Estado de migraciones antes del cambio"
python -m flask --app run.py db current

echo "[8/10] Aplicando migraciones"
python -m flask --app run.py db upgrade
python -m flask --app run.py db current

echo "[9/10] Validando Nginx y reiniciando servicios SICODE"
sudo nginx -t
sudo systemctl restart "$SERVICE"
sleep 2
systemctl is-active --quiet "$SERVICE" || {
  echo "ERROR: $SERVICE no arrancó."
  echo "Commit previo: $PREVIOUS_COMMIT"
  echo "Backup previo: $BACKUP_PATH"
  echo "No ejecute db downgrade a ciegas. Revise journalctl y el procedimiento de rollback."
  systemctl status "$SERVICE" --no-pager || true
  exit 20
}

if systemctl cat "$IA_WORKER_SERVICE" >/dev/null 2>&1; then
  sudo systemctl restart "$IA_WORKER_SERVICE"
  sleep 1
  systemctl is-active --quiet "$IA_WORKER_SERVICE" || {
    echo "ERROR: $IA_WORKER_SERVICE no arrancó después de actualizar el código."
    systemctl status "$IA_WORKER_SERVICE" --no-pager || true
    exit 21
  }
  echo "$IA_WORKER_SERVICE reiniciado correctamente."
else
  echo "Aviso: $IA_WORKER_SERVICE no está instalado; se omite su reinicio."
fi

echo "[10/10] Health checks"
curl --fail --silent --show-error http://127.0.0.1:8000/health
echo
curl --fail --silent --show-error http://127.0.0.1:8000/health/db
echo

echo "Actualización completada correctamente."
echo "Commit anterior: $PREVIOUS_COMMIT"
echo "Commit activo:   $NEW_COMMIT"
echo "Backup previo:   $BACKUP_PATH"
