# SICODE-UCT

**Sistema de Control y Ordenamiento de Expedientes de la Unidad de Control Telemático.**

Aplicación web institucional interna para registrar, localizar, relacionar y auditar metadatos administrativos de sujetos portadores y expedientes físicos. El sistema no debe almacenar copias completas de expedientes ni documentos sensibles.

## Principios de diseño

- Una sola fuente de verdad por dato.
- No. de SP como identificador administrativo; ID interno de base de datos como relación técnica estable.
- Un SP puede existir antes de que el expediente físico esté recibido/localizado.
- Los movimientos especializados se relacionan con el expediente; no copian su información maestra.
- Las operaciones importantes quedan trazadas en Bitácora.
- Las verificaciones automáticas detectan y recomiendan; no realizan correcciones destructivas.

## Tecnología

- Python / Flask
- PostgreSQL
- SQLAlchemy / Flask-Migrate (Alembic)
- Flask-Login / Flask-WTF
- Gunicorn + Nginx en la instalación institucional
- ReportLab / openpyxl / xlrd para PDF y Excel
- GitHub Actions + pytest

## Módulos

- **Dashboard:** pendientes y accesos accionables.
- **Búsqueda global:** SP, nombre, documentos, préstamos, ubicaciones y actividad de Coordinación.
- **SP / Expedientes:** maestro de sujetos portadores, existencia del expediente físico, estado y ubicación.
- **Importación de Portadores:** sincronización diaria de la manta `.xls` con previsualización y reconciliación de vínculos.
- **Índice documental:** documentos, anexos y rangos de folios; evita traslapes y valida totales.
- **Coordinación:** pagos, instalaciones, desinstalaciones, anexos, monitoreos, documentos emitidos, actividades y remisiones.
- **Préstamos:** entrega, devolución, vencimientos y comprobantes.
- **Alertas:** control de observaciones e incidencias.
- **Bitácora:** auditoría legible y campos estructurados de trazabilidad.
- **UO · Usuarios Online:** panel exclusivo de administración para consultar presencias activas, página actual, última actividad y sesiones concurrentes sin exponer tokens ni credenciales.
- **Administración:** usuarios, backups, estado técnico y Control de Integridad.
- **Control de Integridad:** reglas determinísticas para SP, expedientes, ubicación, folios, préstamos, Coordinación, usuarios y backups.

## Variables de entorno obligatorias

```env
SECRET_KEY=<secreto-aleatorio-largo>
DATABASE_URL=postgresql://usuario:password@host/base
```

Opcionales:

```env
SESSION_HOURS=8
SESSION_COOKIE_SECURE=false
MAX_UPLOAD_MB=16
SICODE_VERSION=
UO_ONLINE_TTL_SECONDS=75
PG_DUMP_PATH=
```

`PG_DUMP_PATH` normalmente puede dejarse vacío. SICODE busca `pg_dump` en el `PATH` y también en instalaciones Linux versionadas como `/usr/lib/postgresql/<version>/bin/pg_dump`. Úselo únicamente si el servidor tiene PostgreSQL Client instalado en una ruta no estándar.

En producción, `SECRET_KEY` y `DATABASE_URL` son obligatorias. SICODE no arranca con una clave secreta de respaldo conocida.

## Contraseñas temporales

Las contraseñas asignadas por administración o por `seed.py` se consideran temporales. El usuario debe cambiarlas en su siguiente acceso antes de continuar en otros módulos.

## Migraciones

Nunca cree tablas manualmente en producción. Utilice Alembic:

```bash
python -m flask --app run.py db current
python -m flask --app run.py db heads
python -m flask --app run.py db upgrade
```

Las migraciones de integridad se detienen si detectan inconsistencias que podrían hacer inseguro aplicar un constraint. No fuerce una migración fallida; revise primero el mensaje y los datos afectados.

## QA

```bash
pytest -q
python -m compileall -q app migrations tests
python -m flask --app run.py db heads
```

GitHub Actions ejecuta smoke tests de Coordinación y Portadores, además de la suite pytest de auditoría.

## Producción institucional

El procedimiento documentado está en [`docs/OPERACION_SERVIDOR.md`](docs/OPERACION_SERVIDOR.md). Incluye backup, actualización Git, dependencias, migración, reinicio y rollback.

## Estado del desarrollo

La arquitectura Flask/PostgreSQL actual se mantiene. No existe justificación técnica para reescribir SICODE en otro framework. Las mejoras futuras deben priorizar integración y simplificación sobre nuevos módulos redundantes.
