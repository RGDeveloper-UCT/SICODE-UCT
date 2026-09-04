# SICODE-UCT — Hardening previo a auditoría institucional

Fecha: 2026-09-04  
PR de implementación: **#64 — Hardening integral de SICODE-UCT para auditoría**  
Rama de trabajo: `audit/hardening-integridad-2026-09-04`

## 1. Propósito

Este documento es un addendum verificable al resultado de auditoría de agosto. Su objetivo es que las afirmaciones de seguridad e integridad correspondan al código efectivamente desplegado y a pruebas reproducibles.

No debe presentarse una corrección como instalada en producción hasta que el PR #64 esté fusionado, el servidor haya sido actualizado mediante el procedimiento seguro y la preauditoría productiva termine sin errores bloqueantes.

## 2. Reglas documentales corregidas

### Foliación

- El **cuerpo principal** del expediente comparte una sola foliación general.
- **Cada anexo posee foliación independiente**.
- Un anexo puede iniciar en folio 1 aunque el cuerpo principal u otro anexo ya utilicen ese número.
- Los controles de traslape y salto se ejecutan únicamente dentro de la foliación general.
- El detector de traslapes conserva el máximo folio cubierto para detectar rangos anidados, por ejemplo `1-100`, `2-3`, `4-5`.

La regla está centralizada en `app/services/foliacion_service.py` y es reutilizada por el Índice, Estado Documental y Control de Integridad.

### Incidencias del índice

Los estados `Mal foliado`, `Anexo pendiente` y `Con observaciones` no pueden sobrescribirse mediante verificación rápida.

Para resolverlos se requiere:

1. usuario con permiso de modificación;
2. acción POST protegida por CSRF;
3. motivo explícito de resolución;
4. transición del documento a `Verificado`;
5. corrección coherente de la alerta relacionada;
6. evento de bitácora con estado anterior/posterior y motivo;
7. un único commit transaccional.

### Anulación de anexos indexados

Al anular un documento que proviene de `AnexoCoordinacion`, SICODE libera el vínculo `documento_expediente_id`. El registro anulado permanece para trazabilidad y el anexo vuelve a estar disponible para una reincorporación correcta.

## 3. Concurrencia e integridad de anexos

La validación de aplicación se complementa en PostgreSQL mediante un **advisory lock transaccional por expediente** antes de individualizar un anexo.

Escenario cubierto:

1. estación A y estación B consultan el mismo siguiente número;
2. ambas intentan guardar simultáneamente;
3. PostgreSQL serializa la sección crítica por expediente;
4. una transacción guarda;
5. la segunda revalida después del lock y se rechaza como duplicado;
6. el rollback impide que la segunda operación modifique la secuencia maestra.

Existe una prueba PostgreSQL con dos hilos/sesiones que exige exactamente un alta exitosa y un rechazo por duplicado.

## 4. Control de Integridad ampliado

El módulo de integridad incorpora reglas específicas de Anexos:

| Código | Control |
|---|---|
| `ANX-DUP-001` | mismo número individualizado más de una vez para el mismo expediente |
| `ANX-NUM-001/002` | número no normalizable o fuera del rango operativo |
| `ANX-VINC-001` | vínculo hacia documento inexistente |
| `ANX-VINC-002` | vínculo hacia documento anulado |
| `ANX-VINC-003` | vínculo de anexo hacia documento no clasificado como anexo |
| `ANX-SEQ-001` | total rectificado inferior a evidencia individualizada existente |
| `ANX-ALERTA-001` | documento `Verificado` con alerta documental todavía abierta |

Estas reglas no corrigen datos silenciosamente. Detectan y recomiendan revisión contra el expediente/File Server para preservar la trazabilidad.

## 5. Seguridad aplicada

- CSRF global se mantiene activo.
- Logout se realiza únicamente mediante `POST` + CSRF; `GET /logout` debe responder `405`.
- Login limita temporalmente intentos repetidos por usuario y origen y registra el bloqueo en Bitácora.
- Se mantienen mensajes genéricos para credenciales incorrectas.
- `/health` publica únicamente `{ "status": "ok" }`.
- Respuestas autenticadas llevan `Cache-Control: no-store, private`.
- Cabeceras adicionales: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` y `Permissions-Policy`.
- HSTS se emite únicamente cuando la solicitud llega por HTTPS.
- El rol visor continúa rechazando mutaciones y ahora contempla también endpoints de resolución.

## 6. Trazabilidad transaccional

Los flujos críticos modificados en este hardening registran el dato de negocio y su bitácora dentro de la misma transacción. Se corrigió expresamente el cambio de estado de Alertas y los flujos nuevos del Índice.

El objetivo institucional es: **dato + evidencia de auditoría, o rollback de ambos**.

El código histórico restante debe continuar migrándose gradualmente a este patrón cuando se intervenga cada módulo; no se debe realizar una reescritura masiva inmediatamente antes de auditoría si incrementa el riesgo operativo.

## 7. Backup y recuperación

### Antes de cada actualización

`scripts/actualizar_servidor_seguro.sh` genera y valida un `pg_dump` antes de actualizar código o ejecutar migraciones.

### Backup programado

Se incorporan:

- `scripts/backup_programado.py`;
- `deploy/systemd/sicode-backup.service.template`;
- `deploy/systemd/sicode-backup.timer.template`.

El timer está diseñado para ejecución diaria alrededor de las 02:15, con retraso aleatorio de hasta 15 minutos y persistencia si el servidor estaba apagado.

La retención local predeterminada es 14 días (`SICODE_BACKUP_RETENTION_DAYS`). Solo se eliminan archivos que coincidan con el patrón propio `backup_sicode_uct_*.sql` y únicamente después de generar correctamente el nuevo dump.

**Control pendiente de infraestructura, no de aplicación:** mantener además una copia externa/cifrada en un dispositivo o destino distinto al disco del servidor.

### Restauración

El workflow `Validar Auditoria` ejecuta una restauración real en una base PostgreSQL separada: genera dump, crea una base limpia, restaura con `ON_ERROR_STOP` y consulta tablas críticas.

Para producción se recomienda documentar al menos un simulacro de restauración controlado antes de una auditoría formal anual.

## 8. QA y evidencia reproducible

El PR debe aprobar como mínimo:

- suite completa `pytest -q` en SQLite;
- suite completa `pytest -q` en PostgreSQL 16;
- compilación de aplicación/migraciones/tests;
- cadena Alembic;
- prueba de concurrencia de anexos;
- pruebas de foliación independiente;
- resolución trazable de incidencias;
- seguridad de login/logout/health/cabeceras;
- backup y restauración real de integración.

No fusionar ni desplegar si alguno de los workflows requeridos termina en rojo.

## 9. Verificación del servidor antes de recibir al auditor

Ejecutar:

```bash
cd /opt/sicode/app
bash scripts/auditoria_previa.sh
```

El script aborta si:

- existen cambios locales no documentados;
- faltan variables críticas;
- falla compilación;
- falla alguna regresión crítica;
- el Control de Integridad encuentra errores;
- SICODE/Nginx no están activos;
- `nginx -t` falla;
- fallan `/health` o `/health/db`.

Las advertencias del Control de Integridad deben revisarse y documentarse, aunque no sean necesariamente bloqueantes.

## 10. Actualización segura del servidor

Después de fusionar el PR a `main`:

```bash
cd /opt/sicode/app
bash scripts/actualizar_servidor_seguro.sh
```

El procedimiento realiza: configuración → backup validado → `git pull --ff-only` → dependencias → compilación → pruebas sobre BD aislada → estado Alembic → migraciones → `nginx -t` → reinicio del servicio → health checks.

Si el servicio no arranca, el script informa commit anterior y ruta del backup y **no ejecuta un `db downgrade` automático**. El rollback de esquema debe decidirse a partir de la migración concreta y del respaldo disponible.

## 11. Evidencia sugerida para la visita

Tener disponible, sin revelar secretos:

1. PR #64 y sus checks verdes;
2. salida de `git rev-parse --short HEAD`;
3. `flask db current` y `flask db heads`;
4. salida de `scripts/auditoria_previa.sh`;
5. panel Administración → Control de Integridad sin errores bloqueantes;
6. fecha/tamaño del último backup;
7. evidencia del timer `systemctl list-timers | grep sicode-backup` una vez instalado;
8. bitácora mostrando login, cambios documentales y resoluciones de incidencias;
9. demostración controlada de rol visor vs. usuario autorizado/admin;
10. documentación de ubicación de `.env` sin mostrar su contenido.

## 12. Límites y riesgos aceptados

- El sistema sigue siendo un monolito Flask modular; es apropiado para el entorno actual y no se recomienda reescribirlo antes de la auditoría.
- Algunos controladores históricos siguen siendo grandes. Es deuda de mantenibilidad, no un defecto que justifique una reescritura inmediata.
- `AnexoRectificado` y `AnexoCoordinacion` cumplen funciones históricas diferentes; su convergencia a un modelo canónico único debe hacerse mediante una migración funcional planificada, no inmediatamente antes de auditoría sin un estudio de datos productivos.
- Los timestamps históricos siguen siendo `DateTime` sin una migración global a zona horaria. Cambiar toda la semántica temporal requiere una migración de datos y se considera mejora planificada, no parche seguro de última hora.
- `SESSION_COOKIE_SECURE` debe habilitarse cuando la instalación opere efectivamente detrás de HTTPS; forzarlo en una LAN HTTP impediría el envío normal de la cookie.

La prioridad de este hardening es eliminar inconsistencias demostrables, elevar controles preventivos y producir evidencia auditable sin introducir cambios de alto riesgo que no puedan validarse con datos productivos reales.
