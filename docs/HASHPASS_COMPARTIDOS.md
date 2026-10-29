# HashPass HP-002 — Bóveda institucional compartida

**Estado: PR de desarrollo / NO habilitado por defecto.** La clave custodial de la
bóveda compartida solo debe gestionarse tras aprobar el modelo de seguridad.
No almacenar contraseñas reales durante pruebas.

## Acceso y alcance

- Una credencial compartida está disponible para **todos los usuarios activos
  de SICODE con permiso HashPass** que hayan creado su propia contraseña
  maestra independiente.
- El administrador concede/revoca permisos; **no es una excepción**: requiere
  permiso HashPass y su propia maestra para consultar credenciales.
- Al otorgar permiso a nuevos usuarios, después de configurar su maestra,
  podrán acceder a todas las credenciales institucionales, incluso anteriores.
- Todos los autorizados pueden consultar y crear entradas. Únicamente el
  creador de cada credencial o un administrador que también tenga permiso
  HashPass puede modificarla o archivarla. Se audita el actor de cada acción. La revocación impide consultas futuras
  mediante la aplicación, pero no puede borrar secretos ya conocidos por alguien.
- NO comparta datos personales o ajenos a la política institucional.

## Cifrado y limitaciones

Los registros nuevos usan **AES-256-GCM** con nonce aleatorio por registro y
datos asociados vinculados al UUID. La clave institucional de 256 bits
se obtiene de `HASHPASS_SHARED_KEY_B64` (base64); la clave no debe almacenarse
en Git, SQL, logs ni respaldos accesibles a los usuarios.

La contraseña maestra individual sigue protegida por Argon2id y controla
el desbloqueo por petición. **La clave compartida es custodial del servidor:**
un intruso con acceso simultáneo a BD y clave institucional puede descifrar las
contraseñas sin las maestras. No es E2EE y no equivale a KeePass. Requiere
evaluación de riesgos, protección del servidor, backup cifrado, inventario
de custodios, plan de rotación de credenciales y pruebas de restauración.

**Pérdida o sustitución del secreto `HASHPASS_SHARED_KEY_B64`:**
las credenciales compartidas existentes pueden quedar irrecuperables.
Nunca regenere esta clave si ya existe información guardada. Debe protegerse
con custodia institucional independiente y respaldos recuperables, siguiendo
las políticas oficiales de gestión de claves. Este desarrollo **no incluye**
rotación de clave custodial ni recuperación ante pérdida; son bloqueadores
para uso productivo con secretos reales.

## Credenciales ya almacenadas en la versión HP-001

Los registros anteriores están cifrados con una DEK privada que únicamente
puede abrirse con la **contraseña maestra de su propietario**. No existe
migración SQL ni llave maestra administrativa que permita reusarlos sin esa
contraseña.

Una vez habilitada HP-002, el propietario autenticado abre
**HashPass → Compartir contraseñas que guardé antes**, introduce su maestra
y confirma. El sistema:
1. Recupera exclusivamente sus registros privados **no archivados**.
2. Los descifra transitoriamente en memoria con la maestra aportada.
3. Los cifra con la clave institucional para compartirlos.
4. Archiva el original y confirma todo en una transacción.
5. Registra cada publicación en bitácora, sin registrar el secreto.

El proceso es idempotente: no duplica registros si vuelve a ejecutarse.
Los registros privados ya archivados no se publican automáticamente.
Cada propietario debe ejecutar la operación para sus propios registros.
**La publicación hace visibles las contraseñas a todas las cuentas autorizadas
actuales y futuras.** Primero haga copia de seguridad probada.

## Pruebas en una copia aislada, sin afectar producción

```bash
cd /opt/sicode/app
git fetch origin
git worktree add --detach "$HOME/hashpass-shared-staging" \
  origin/feature/hashpass-hp002-boveda-compartida
mkdir -p "$HOME/.venvs"
python3 -m venv "$HOME/.venvs/hashpass-shared-staging"
source "$HOME/.venvs/hashpass-shared-staging/bin/activate"
cd "$HOME/hashpass-shared-staging"
python -m pip install -r requirements.txt
SECRET_KEY=solo-pruebas-hp002 \
DATABASE_URL=sqlite:////tmp/sicode_hp002_test.sqlite3 \
DOCUMENT_ANALYSIS_AI_TIMEOUT=75 \
python -m pytest -q tests/test_hashpass.py
SECRET_KEY=solo-pruebas-hp002 \
DATABASE_URL=sqlite:////tmp/sicode_hp002_test.sqlite3 \
python -m flask --app run.py db heads
```

Se espera cabeza única `hp00220261029`. Las pruebas incluyen aislamiento
de la maestra, compartición con usuarios distintos, nuevas altas, revocación,
publicación idempotente y falta de clave custodial.

## Despliegue institucional (solo tras aprobar PR y controles)

No usar `flask db stamp`, ni ejecutar migraciones en producción sin respaldo
de BD y prueba de restauración. HP-002 añade `hashpass_compartidos` sin
destruir `hashpass_registros`. Para actualizar, primero integre HP-002 a la
rama usada por el servicio, ejecute pruebas, revise `flask db heads` y aplique
`python -m flask --app run.py db upgrade` únicamente con ventana autorizada.

En producción debe mantenerse:
```dotenv
HASHPASS_ENABLED=true
HASHPASS_REQUIRE_HTTPS=true
SESSION_COOKIE_SECURE=true
HASHPASS_SHARED_ENABLED=true
HASHPASS_SHARED_KEY_B64=<valor custodiado de 32 bytes en base64>
```

El parámetro `HASHPASS_PROXY_PROTO_COUNT=1` solo es apto con Gunicorn ligado
a loopback y Nginx como único proxy de confianza, enviando
`X-Forwarded-Proto: $scheme`. El archivo `.env` pertenece a la
configuración del servicio, NO se sube a Git.

**No generar el secreto custodial hasta preparar el sistema de custodia y
recuperación.** No copiarlo en capturas, mensajes, terminales compartidos,
historial de comandos o logs. Tras integrar y desplegar, compruebe
`flask hashpass-status` (muestra booleanos, nunca la clave).

Para deshabilitar temporalmente la bóveda compartida sin borrar datos,
configure `HASHPASS_SHARED_ENABLED=false` y reinicie el servicio.
La clave no debe eliminarse ni cambiarse.
