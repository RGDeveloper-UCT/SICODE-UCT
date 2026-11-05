# Sincronización global en tiempo real — SICODE-UCT

## Objetivo

Un guardado confirmado en PostgreSQL produce una **invalidación** entre
sesiones autorizadas, sin recargar el documento completo ni transportar datos
sensibles en los eventos. El Tablón UCT usa nuevamente su API; las demás
vistas HTML revalidan y reconcilian su contenido conservando formularios,
diálogos, controles y posición de desplazamiento.

## Arquitectura implementada

1. SQLAlchemy detecta cambios de modelos durante el flush.
2. **Solo después de confirmar la transacción** publica el listado de módulos
   en el canal Redis `sicode:sincronizacion:v1`.
3. Cada navegador autenticado mantiene una conexión SSE a
   `GET /sincronizacion/eventos`.
4. El cliente recibe el evento y emite `sicode:actualizacion`. Agenda UCT
   consulta sus API y actualiza el tablón, calendario y notificaciones.
5. El cliente global reconcilia el HTML de lectura mediante GET autorizado,
   evitando F5, recarga completa, escritura de formularios y pérdida de scroll.
6. Si la sesión se desconecta, EventSource se reconecta y solicita una
   resincronización completa de la vista.
7. Las consultas de presencia y escrituras exclusivamente en bitácora no
   generan invalidaciones, para prevenir bucles por auditoría de lecturas.

### Alcance y precauciones

- Requiere Redis operativo: la configuración por defecto reutiliza
  `SICODE_REDIS_URL`, ya utilizado por trabajos de IA.
- El dato almacenado en PostgreSQL es siempre la fuente de verdad; SSE solo
  indica que una vista debe reconsultar información.
- No se distribuyen nombres, números de SP, valores de formulario, expedientes,
  identificadores personales ni contenido de documentos en Redis/SSE.
- El mecanismo cubre cambios hechos mediante **sesiones ORM de SQLAlchemy**.
  Las escrituras SQL directas no generan eventos automáticamente y deberán
  emitir una invalidación explícita si existieran en algún módulo.
- El frontend conserva formularios y diálogos abiertos; en pantallas de
  terceros o interacciones muy específicas debe comprobarse la reconciliación.
  Un conflicto del formulario Agenda devuelve HTTP 409 cuando recibe una
  revisión anterior. Los demás módulos requieren revisar individualmente
  sus reglas de edición concurrente para garantizar bloqueo optimista.

## Requisitos de producción

- Gunicorn con worker `gthread` (o equivalente asíncrono), para que una
  conexión SSE persistente no bloquee un worker exclusivo.
- Redis funcionando en el servidor local, sin exposición pública.
- Nginx con buffering desactivado para `/sincronizacion/eventos`.
- No se requieren migraciones de base de datos para esta funcionalidad.

### 1. Revisar servidor actual (sin modificar todavía)

```bash
cd /opt/sicode/app
git status --short
sudo systemctl cat sicode.service
sudo nginx -T | grep -n -A12 -B6 'proxy_pass\|server_name'
sudo systemctl status redis-server --no-pager
```

En caso de Redis con nombre de servicio `redis` usar ese nombre.

### 2. Gunicorn

Conservar el resto de argumentos del `ExecStart` actual y ajustar el worker,
por ejemplo:

```text
/opt/sicode/venv/bin/gunicorn --worker-class gthread --workers 2 --threads 32 --bind 127.0.0.1:8000 run:app
```

Es **solo un ejemplo**. Revisar primero la unidad instalada y sus variables,
usuario de servicio, WorkingDirectory y posibles opciones de timeout. No
sustituir la unidad a ciegas. Si se utiliza `systemctl edit sicode.service`,
un `ExecStart` nuevo exige limpiar el anterior con `ExecStart=` vacío.

### 3. Nginx

Incorporar al bloque `server` que atiende SICODE el contenido de
`deploy/nginx/sicode-realtime-sse.location.conf`. No borrar el bloque
`location /` existente. Validar y recargar:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 4. Variables de entorno

En `.env`, opcionalmente:

```env
SICODE_REALTIME_ENABLED=true
# Solo si se desea otro Redis/DB para este canal:
# SICODE_REALTIME_REDIS_URL=redis://127.0.0.1:6379/0
```

El servicio Redis debe estar disponible antes de activar SICODE. No mostrar
`.env` ni contraseñas en capturas de pantalla.

### 5. Validación antes del despliegue

```bash
source /opt/sicode/venv/bin/activate
python -m compileall -q app tests
pytest -q tests/test_sincronizacion_global.py tests/test_agenda_uct.py
node --check app/static/js/sicode_realtime.js
node --check app/static/js/agenda.js
python -m flask --app run.py db heads
```

Después del despliegue, al iniciar sesión desde el navegador debe aparecer
`● En tiempo real` en la barra superior. El endpoint
`/sincronizacion/estado` devuelve `{"conectado": true}` únicamente con
sesión iniciada y Redis operativo.

### 6. Prueba de dos computadoras

1. Abrir SICODE en dos navegadores diferentes con usuarios autorizados.
2. En B, mantener proyectado **Agenda UCT → Tablón**.
3. En A, cambiar el estado de una actividad institucional desde Agenda.
4. Verificar que B muestra el estado nuevo sin F5.
5. Repetir creando y eliminando actividades y desde el Dashboard.
6. Repetir para expedientes, anexos, préstamos, alertas y consultas disponibles,
   verificando las operaciones de cada módulo antes de habilitar producción.
7. Abrir el formulario de edición en B y cambiar esa tarea desde A. Al intentar
   guardar el formulario obsoleto en B, debe obtenerse un mensaje de conflicto
   HTTP 409 y no perder el texto escrito.
8. Cortar temporalmente la conexión de B y restablecerla. Debe aparecer
   `Reconectando…` y luego `En tiempo real`; la vista debe ponerse al día.
9. Comprobar en bitácora que las modificaciones se registran una sola vez.

### 7. Actualización en producción

Usar el procedimiento existente `scripts/actualizar_servidor_seguro.sh`,
que comprueba árbol limpio, backup, fast-forward, migraciones, pruebas y health.
**Primero revisar y fusionar el PR** de esta función en `main`. Después:

```bash
cd /opt/sicode/app
SICODE_BRANCH=main bash scripts/actualizar_servidor_seguro.sh
```

No ejecutar contra la base de producción mientras la rama esté en revisión.
