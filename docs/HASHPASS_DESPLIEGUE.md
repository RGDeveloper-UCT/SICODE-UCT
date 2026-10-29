# HashPass — Instalación verificable en SICODE-UCT

**Estado:** código de revisión en el PR #83, módulo apagado por defecto. No usar con claves reales hasta que se completen HTTPS, pruebas, respaldo cifrado, controles institucionales y evaluación de seguridad. No es cifrado extremo a extremo.

## Por qué no se ve tras aprobar pytest

`~/hashpass-staging` es una **copia independiente** del repositorio; sus pruebas no cambian el código ejecutado por `sicode.service` desde `/opt/sicode/app`. Además, el enlace a la bóveda se presenta únicamente a usuarios con permiso y cuando el módulo está activado, migrado y servido por HTTPS seguro. La casilla para otorgar permisos sólo aparece en Administración → Usuarios cuando estas condiciones se cumplen.

El menú de **Administración → HashPass · permisos** siempre lleva a un panel informativo (una vez desplegado el código), incluso si el módulo está apagado. No da acceso a secretos.

## 1. Comprobar situación actual (lectura solamente)

```bash
cd /opt/sicode/app
git status --short
git branch --show-current
git log -1 --oneline
sudo systemctl show sicode.service -p WorkingDirectory -p FragmentPath
sudo systemctl status sicode.service --no-pager
```

No pegue `.env` ni información de sesión en chats/tickets.

## 2. Pruebas de código aisladas (sin tocar la BD ni el venv institucional)

```bash
cd /opt/sicode/app
git fetch origin
# Si ya existe este worktree, omita la línea de creación.
git worktree add --detach "$HOME/hashpass-staging" origin/feature/hashpass-hp001-np-compatible
cd "$HOME/hashpass-staging"
mkdir -p "$HOME/.venvs"
python3 -m venv "$HOME/.venvs/hashpass-staging"
source "$HOME/.venvs/hashpass-staging/bin/activate"
python -m pip install -r requirements.txt
SECRET_KEY=solo-pruebas-no-productivo \
DATABASE_URL=sqlite:////tmp/sicode_hashpass_tests.sqlite3 \
DOCUMENT_ANALYSIS_AI_TIMEOUT=75 \
python -m pytest -q tests/test_hashpass.py tests/test_config_analisis_documental_runtime.py
SECRET_KEY=solo-pruebas-no-productivo \
DATABASE_URL=sqlite:////tmp/sicode_hashpass_heads.sqlite3 \
python -m flask --app run.py db heads
```

Resultado esperado: `hp00120261029 (head)`. **No** usar `db stamp` ni `db downgrade` para resolver revisiones ausentes. Para ejecutar el flujo completo de migraciones use una BD **PostgreSQL** de pruebas, respaldada y autorizada, no la productiva.

## 3. Requisitos de infraestructura ANTES de activar

- Nginx debe aceptar HTTPS en puerto 443 con certificado institucional confiable y redireccionar HTTP → HTTPS.
- Gunicorn debe escuchar **solo** `127.0.0.1:8000`, y Nginx ser el único proxy de confianza.
- En el location de Nginx hacia Gunicorn: `proxy_set_header X-Forwarded-Proto $scheme;`.
- Verifique `sudo nginx -t`, redirección desde un PC cliente y candado/certificado confiable antes de conectar credenciales.
- Configure protección de respaldos PostgreSQL y controles de acceso al servidor; las claves de bóveda están cifradas, pero un backup y la infraestructura siguen siendo sensibles.
- La contraseña maestra se procesa en memoria del backend al utilizar la bóveda: no es equivalente a KeePass/KDBX ni seguro ante control total del servidor.
- Revisión institucional de la nueva clase de información sensible, auditoría de seguridad y recuperación.

**Nunca establecer `HASHPASS_REQUIRE_HTTPS=false` ni `SESSION_COOKIE_SECURE=false` en producción.** El código bloquea HashPass si cualquiera de estas condiciones no es segura.

## 4. Integración tras aprobación y fusión del PR #83

Con respaldo de BD reciente y restauración probada, y sólo durante ventana autorizada:

```bash
cd /opt/sicode/app
git status --short
git switch main
git fetch origin
git pull --ff-only origin main
source /opt/sicode/venv/bin/activate
python -m pip install -r requirements.txt
python -m flask --app run.py db current
python -m flask --app run.py db heads
# Solo después de comprobar respaldo, base correcta y cadena de migraciones:
python -m flask --app run.py db upgrade
python -m flask --app run.py db current
python -m flask --app run.py hashpass-status
```

HashPass comenzará **deshabilitado**. Su configuración no se activa por las pruebas de CI ni por instalar dependencias.

Con HTTPS comprobado, edite el `.env` que carga realmente `sicode.service` y añada:

```dotenv
HASHPASS_ENABLED=true
HASHPASS_REQUIRE_HTTPS=true
SESSION_COOKIE_SECURE=true
# SOLO si Gunicorn está en loopback y Nginx es el único proxy:
HASHPASS_PROXY_PROTO_COUNT=1
```

Luego:

```bash
cd /opt/sicode/app
source /opt/sicode/venv/bin/activate
python -m flask --app run.py hashpass-status
sudo systemctl restart sicode.service
sudo systemctl status sicode.service --no-pager
curl --fail --silent http://127.0.0.1:8000/health
```

El diagnóstico muestra indicadores, no secretos. **No valida TLS**: también compruébelo desde el navegador cliente, con HTTPS real y certificado confiable.

## 5. Comprobar aparición y funcionamiento

1. Entre **por HTTPS** al SICODE que corre en el servidor institucional.
2. Como administrador, vaya a **Administración → HashPass · permisos**. El panel explica si falta activación, migración o HTTPS.
3. En **Administración → Usuarios** conceda permiso HashPass al usuario deseado. Para usar una bóveda propia, conceda permiso también a su cuenta de administrador.
4. Cierre sesión y vuelva a entrar. En **Módulos SICODE** verá **HashPass** si tiene autorización.
5. Abra HashPass y confirme que aparece la explicación sobre **Argon2id**, **AES-256-GCM**, límites y ausencia de recuperación automática.
6. Cree una maestra ficticia distinta a la contraseña SICODE. Registre, revele, cambie y archive una credencial **de prueba**. Revise eventos de la Bitácora.
7. Revocar permiso debe quitar la entrada al módulo e impedir abrir la URL directa; no elimina la bóveda cifrada.

## 6. Si el botón no aparece

```bash
cd /opt/sicode/app
git log -1 --oneline
git branch --show-current
source /opt/sicode/venv/bin/activate
python -m flask --app run.py hashpass-status
python -m flask --app run.py db current
python -m flask --app run.py db heads
```

- Comando `hashpass-status` no reconocido: el servicio/código aún no contiene la revisión HashPass.
- `HASHPASS_ENABLED=False`: la variable no está activada en el proceso correcto.
- `Tablas HashPass presentes=False`: falta migración o se usa otra BD.
- `SESSION_COOKIE_SECURE=False`, `HASHPASS_REQUIRE_HTTPS=False` o navegador HTTP: se bloquea por seguridad.
- Usuario sin permiso: menú de bóveda oculto por diseño; use Administración → Usuarios.
- Si SICODE está atendido por otro código, verifique `WorkingDirectory` de systemd; una copia bajo `$HOME` no sustituye al servicio.

## Rollback seguro

Para bloquear acceso sin eliminar datos: configurar `HASHPASS_ENABLED=false` y reiniciar el servicio. No hacer `flask db downgrade` con bóvedas existentes ni borrar manualmente tablas. Conserva el backup anterior y el estado actual para diagnóstico.
