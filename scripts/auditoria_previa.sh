#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${SICODE_APP_DIR:-/opt/sicode/app}"
VENV_DIR="${SICODE_VENV_DIR:-/opt/sicode/venv}"

cd "$APP_DIR"
source "$VENV_DIR/bin/activate"

printf '\n== SICODE-UCT · PREAUDITORÍA ==\n'
printf 'Commit: '
git rev-parse --short HEAD

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: el repositorio tiene cambios locales. Documente o limpie esos cambios antes de auditar."
  git status --short
  exit 2
fi

echo "[1/6] Variables críticas"
grep -q '^SECRET_KEY=.' .env || { echo 'FALTA SECRET_KEY'; exit 3; }
grep -q '^DATABASE_URL=.' .env || { echo 'FALTA DATABASE_URL'; exit 3; }

echo "[2/6] Compilación Python"
python -m compileall -q app migrations tests

echo "[3/6] Cadena de migraciones"
python -m flask --app run.py db current
python -m flask --app run.py db heads

echo "[4/6] Pruebas de hardening y regresión documental"
pytest -q \
  tests/test_auditoria_hardening.py \
  tests/test_indice_documental_foliacion_anexos.py \
  tests/test_monitoreo_anexos.py \
  tests/test_control_integridad.py \
  tests/test_backup.py

echo "[5/6] Control de Integridad sobre la base activa"
python - <<'PY'
from app import create_app
from app.services.integridad_service import ejecutar_control_integridad

app = create_app()
with app.app_context():
    control = ejecutar_control_integridad()
    print(f"Reglas: {control['total_reglas']}")
    print(f"Módulos correctos: {control['correctos']}")
    print(f"Errores: {control['errores']}")
    print(f"Advertencias: {control['advertencias']}")
    for item in control['hallazgos']:
        print(f"[{item.severidad.upper()}] {item.codigo} · {item.modulo} · {item.registro}: {item.descripcion}")
    if control['errores']:
        raise SystemExit(10)
PY

echo "[6/6] Servicios"
systemctl is-active --quiet sicode.service || { echo 'ERROR: sicode.service no está activo'; exit 11; }
systemctl is-active --quiet nginx || { echo 'ERROR: nginx no está activo'; exit 12; }
sudo nginx -t
curl --fail --silent --show-error http://127.0.0.1:8000/health
echo
curl --fail --silent --show-error http://127.0.0.1:8000/health/db
echo

echo "PREAUDITORÍA COMPLETADA SIN ERRORES BLOQUEANTES."
