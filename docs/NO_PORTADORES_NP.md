# NO PORTADORES (NP) — Módulo autónomo de SICODE-UCT

## Propósito

Registrar a personas que no llegaron a tener instalación de dispositivo, sin confundirlas con sujetos portadores (SP). El identificador administrativo es **No. NP** (ejemplo `NP-0001`) y su código interno es propio.

## Principio de aislamiento

- Las tablas NP son independientes y no tienen relaciones con `expedientes.id`.
- Los registros NP no aparecen en la búsqueda global SP, listados SP, pagos SP, Coordinación SP ni importación de Portadores.
- Cada NP tiene sus documentos, anexos, verificaciones, alertas, préstamos y traslados virtuales en tablas `*_np`.
- La única integración transversal permitida es identificación de usuario (autorización) y bitácora estructurada con `entidad=NoPortador`, `entidad_id=<id>` y `expediente_id=NULL`. El backup PostgreSQL incluye las tablas NP automáticamente.
- No se admiten cargas de documentos ni se almacenan PDFs de expediente. Los PDF generados son comprobantes administrativos derivados de metadatos.

## Funciones incluidas en esta entrega

1. Alta y edición NP: identificación, motivo y fecha de no instalación, datos administrativos similares al maestro SP, existencia física y ubicación.
2. Búsqueda y filtros exclusivamente NP.
3. Índice documental y foliación NP: rangos positivos, totales calculados y rechazo de traslapes.
4. Anexos NP: datos administrativos de recepción y estado, con desactivación lógica.
5. Rectificación física de folios y anexos.
6. Historial de verificaciones físicas/documentales/integrales.
7. Préstamos físicos y devoluciones: solo si existe expediente físico y rectificación completa, una sola entrega activa por NP mediante índice único parcial PostgreSQL/SQLite.
8. Comprobante PDF de préstamo, ficha PDF, constancia de traslado virtual NP y exportación Excel del listado.
9. Alertas NP, con cierre auditado.
10. Bitácora de operaciones con entidad NP y controles de permiso (administrador y usuario autorizado editan; visor consulta).

## Pendientes de equivalencia funcional integral

Para igualar **todas** las herramientas específicas de SP y no solo su manejo de expediente, deben validarse y desarrollarse equivalentes NP de: préstamos grupales por rango, impresión de códigos de barras, importación masiva, verificación de índice integral de alta complejidad, controles automáticos de integridad, clasificación y vigencia de anexos, e integración NP de los flujos particulares de Coordinación, Reportes especializados y cualquier otra función SP que sea apropiada a un caso sin instalación. No reutilizar rutas SP; cada flujo NP tendrá almacenamiento y permisos independientes.

**No considerar esta primera entrega equivalencia total con SP ni habilitarla en producción sin completar el análisis funcional y las pruebas.**

## Pruebas

```bash
python -m compileall -q app migrations tests
pytest -q tests/test_no_portadores.py
python -m flask --app run.py db heads
```

Probar migración sobre base de pruebas; no ejecutar migraciones sin respaldo institucional.

## Procedimiento de actualización tras revisión y fusión a main

En el servidor institucional, después de aprobar el cambio y respaldar la base:

```bash
cd /opt/sicode/app
git status --short
# Debe estar limpio. De lo contrario, detenerse y revisar.
SICODE_BRANCH=main bash scripts/actualizar_servidor_seguro.sh
```

La secuencia segura efectúa copia de seguridad, actualización fast-forward, compilación, pruebas, migraciones, reinicio del servicio y comprobaciones de salud. Ejecutar adicionalmente `pytest -q tests/test_no_portadores.py` sobre base de pruebas para validar la nueva funcionalidad.

La migración de NP crea solo tablas nuevas, con antecedente `n7puct20261028`. No traslada ni altera los registros SP.

## Criterios de aceptación mínimos

- Registrar dos NP sin modificar conteos ni préstamos SP.
- No permitir NP duplicado; números NP normalizados.
- Crear, rectificar, prestar y devolver solo dentro de NP.
- Rechazar préstamos duplicados y rangos de folios superpuestos.
- Verificar comprobante PDF y registro de auditoría de NP sin `expediente_id` SP.
- Confirmar permisos de visor y que NP no aparece en Portadores/SP.
- Ejecutar respaldo y prueba de restauración en base temporal.
