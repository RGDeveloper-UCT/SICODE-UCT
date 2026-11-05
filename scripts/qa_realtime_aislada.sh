#!/usr/bin/env bash
# QA aislada para sincronización SICODE: NO usa PostgreSQL productivo.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "$ROOT" == "/opt/sicode/app" || "$ROOT" == /opt/sicode/app/* ]]; then
  echo "ERROR: no ejecutar pruebas aisladas en la ruta de producción."
  exit 2
fi
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "ERROR: falta .venv. Cree el entorno de pruebas e instale requirements.txt."
  exit 2
fi
if [[ "$(id -u)" == "0" ]]; then
  echo "ERROR: ejecutar como usuario normal, nunca con sudo."
  exit 2
fi
cd "$ROOT"
QA_DIR="$HOME/sicode-realtime-qa"
mkdir -p -m 700 "$QA_DIR"
chmod 700 "$QA_DIR"
export DATABASE_URL="sqlite:///$QA_DIR/sicode-qa.sqlite3"
export SECRET_KEY="$( "$ROOT/.venv/bin/python" -c 'import secrets; print(secrets.token_hex(32))' )"
export SESSION_COOKIE_SECURE=false
export SICODE_REALTIME_ENABLED=true
export SICODE_REALTIME_REDIS_URL="redis://127.0.0.1:6379/0"
export SICODE_REALTIME_CHANNEL="sicode:qa:${USER:-operador}:uct"
export HASHPASS_ENABLED=false
export HASHPASS_SHARED_ENABLED=false
export AI_SEARCH_ENABLED=false
export DOCUMENT_ANALYSIS_AI_ENABLED=false
export QA_PASS="$( "$ROOT/.venv/bin/python" -c 'import secrets; print(secrets.token_urlsafe(14))' )"

# Verifica configuración y detiene si Valkey no responde.
"$ROOT/.venv/bin/python" - <<'PY'
import os
from pathlib import Path
from redis import Redis
ruta = str(Path.home() / "sicode-realtime-qa" / "sicode-qa.sqlite3")
assert os.environ["DATABASE_URL"] == "sqlite:///" + ruta, "Base QA incorrecta"
assert os.environ["SICODE_REALTIME_CHANNEL"].startswith("sicode:qa:")
cliente = Redis.from_url(os.environ["SICODE_REALTIME_REDIS_URL"], socket_timeout=2)
assert cliente.ping(), "Valkey no responde"
cliente.close()
PY

# Base SQLite exclusivamente de pruebas, sin apuntar al PostgreSQL de producción.
"$ROOT/.venv/bin/python" - <<'PY'
import os
from werkzeug.security import generate_password_hash
from app import create_app, db
from app.models.usuario import Usuario
app = create_app()
app.config["TESTING"] = True  # La carga inicial no publica eventos.
with app.app_context():
    db.create_all()
    for login, nombre in (
        ("qa_realtime_uno", "QA RealTime Uno"),
        ("qa_realtime_dos", "QA RealTime Dos"),
    ):
        user = Usuario.query.filter_by(usuario=login).first()
        if user is None:
            user = Usuario(
                usuario=login, nombre=nombre,
                correo=login + "@uct.invalid",
                rol="usuario_autorizado", activo=True,
                debe_cambiar_password=False,
            )
            db.session.add(user)
        user.password_hash = generate_password_hash(
            os.environ["QA_PASS"], method="pbkdf2:sha256"
        )
        user.activo = True
        user.debe_cambiar_password = False
    db.session.commit()
print("\n=== ENTORNO DEMO (sin datos reales) ===")
print("URL: http://127.0.0.1:8101")
print("Usuarios: qa_realtime_uno / qa_realtime_dos")
print("Contraseña QA (válida hasta reiniciar este proceso):", os.environ["QA_PASS"])
print("Canal aislado:", os.environ["SICODE_REALTIME_CHANNEL"])
print("Para detener QA: Ctrl+C")
PY

exec "$ROOT/.venv/bin/python" -m gunicorn \
    --workers 1 --worker-class gthread --threads 16 \
    --bind 127.0.0.1:8101 --timeout 120 \
    --access-logfile - --error-logfile - run:app
