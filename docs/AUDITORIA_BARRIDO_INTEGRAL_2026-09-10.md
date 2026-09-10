# SICODE-UCT — Barrido integral por capas

**Fecha:** 10 de septiembre de 2026  
**Rama de corrección:** `audit/barrido-integral-2026-09-10`  
**Base inicial revisada:** `9f1e5a2d7bdad6022c9ceb5f99bb05458076e2a1`  
**Estado de `main` durante el barrido:** avanzó posteriormente con cambios de edición de número de anexo; esos cambios se revisaron separadamente y no pisan los archivos corregidos en esta rama.

## Resultado ejecutivo

No se identificó un fallo P0 que evidencie corrupción general o caída estructural del sistema a partir del código, pruebas y workflows revisados. Sí se identificaron incidencias de seguridad, trazabilidad y despliegue que conviene resolver antes de declarar el sistema endurecido para operación institucional.

La revisión fue de repositorio, configuración, código, pruebas y CI. Los puntos que dependen del servidor físico, red LAN, certificados, permisos reales del sistema operativo y restauración sobre infraestructura institucional deben validarse además en el servidor.

## Barrido por capas

| Capa / módulo | Estado | Resultado principal |
|---|---|---|
| Configuración Flask | Conforme con observaciones | `SECRET_KEY` y `DATABASE_URL` obligatorios, CSRF global, sesión fuerte y cookies HttpOnly/SameSite. TLS sigue siendo un control de infraestructura pendiente. |
| Autenticación | Conforme | Rate limit, mensajes genéricos, logout POST y rechazo de usuarios inactivos. |
| Roles / permisos | Corregido | El rol Visor podía alcanzar SICODE.IA por una excepción global. Se bloqueó backend para `sicode_ia` y `sicode_ia_jobs`. |
| Dashboard | Sin incidencia nueva confirmada | No se observó mutación inesperada ni consulta crítica sin límite en la revisión actual. |
| Expedientes | Conforme | `No. SP` e identificadores mantienen restricciones e índices; disponibilidad física deriva de préstamos activos. |
| Índice documental / foliación | Conforme con deuda conocida | Validaciones y trazabilidad presentes. La edición reciente de número de anexo registra bitácora en la misma transacción. |
| Verificación física/digital | Conforme | Reglas de estado documental y rectificación se mantienen como fuente de control antes de préstamos/cargas. |
| Ubicación física | Sin incidencia nueva confirmada | Continúa integrada al expediente; requiere smoke test en servidor con datos reales. |
| Préstamos individuales | Corregido | Alta, traslado virtual y devolución hacían commit antes de auditar. Ahora dato y bitácora comparten transacción. |
| Préstamos grupales | Conforme | Ya utilizaban `flush`, `commit=False`, commit único y rollback. |
| Alertas | Conforme | La detección desde GET no crea alertas por defecto; se conserva lectura pura. |
| Búsqueda | Conforme | SQLAlchemy parametrizado y límites por grupo/resultado; no se encontró SQL crudo concatenado en el servicio revisado. |
| Reportes PDF/Excel | Sin incidencia nueva confirmada | Generación en memoria y auditoría presente en flujos revisados; validar muestra real en servidor. |
| Bitácora / auditoría | Corregido en préstamos | Servicio soporta `commit=False`; se alinearon movimientos individuales al patrón atómico. |
| Administración | Conforme con observaciones | Controles de último administrador y backups existentes. Se endurecieron permisos POSIX del backup. |
| Backups | Corregido en servidor local; pendiente copia externa | Directorio `0700`, dump `0600`, `UMask=0077`. Falta copia externa/cifrada en medio distinto. |
| Análisis documental temporal | Conforme | Directorio `0700`, archivos `0600`, limpieza y eliminación en `finally`; no se observó persistencia deliberada del PDF fuente. |
| SICODE.IA / RQ | Corregido | Se bloqueó Visor, se ocultó traceback al navegador y se corrigió la ruta del venv del worker. |
| Despliegue systemd/Nginx | Corregido parcialmente | El actualizador reinicia web y worker, valida dependencias y health. TLS institucional permanece pendiente. |
| CI / GitHub | Corregido parcialmente | La auditoría completa ahora también se ejecutará al llegar a `main`. Falta proteger `main` mediante configuración de repositorio/ruleset. |
| Base de datos / migraciones | Conforme con deuda planificada | CI valida cadena completa sobre PostgreSQL. La normalización futura de timestamps y algunos modelos históricos sigue como deuda de arquitectura, no como parche de emergencia. |

## Incidencias registradas

### INC-AUD-2026-001 — Visor podía acceder a SICODE.IA
- **Fecha:** 2026-09-10
- **Módulo:** Seguridad / SICODE.IA
- **Gravedad:** Alta
- **Estado:** Corregido en rama de auditoría
- **Descripción:** el guard global de solo lectura exceptuaba completamente los blueprints `sicode_ia` y `sicode_ia_jobs`, permitiendo a un Visor abrir el flujo de análisis y alcanzar endpoints que cargan PDF y crean trabajos.
- **Causa probable:** excepción agregada para permitir navegación de IA sin diferenciar consulta de procesamiento.
- **Solución aplicada:** bloqueo backend de ambos blueprints para Visor y defensa adicional en `sicode_ia_jobs._exigir_modificacion()` mediante `puede_modificar`.
- **Evidencia:** prueba `test_visor_no_puede_acceder_a_sicode_ia`.

### INC-AUD-2026-002 — Préstamo/devolución no atómicos con bitácora
- **Fecha:** 2026-09-10
- **Módulo:** Préstamos / Bitácora
- **Gravedad:** Alta
- **Estado:** Corregido en rama de auditoría
- **Descripción:** el movimiento se confirmaba en BD antes de registrar la bitácora; un fallo posterior podía dejar un préstamo, traslado o devolución sin evidencia de auditoría.
- **Causa probable:** patrón histórico anterior al soporte `registrar_bitacora(..., commit=False)`.
- **Solución aplicada:** `flush` cuando se necesita ID, bitácora con `commit=False` y un único `db.session.commit()` al final. La devolución incorpora datos anteriores/posteriores estructurados.
- **Evidencia:** `tests/test_prestamos_atomicidad.py`.

### INC-AUD-2026-003 — Permisos POSIX de backups no fijados explícitamente
- **Fecha:** 2026-09-10
- **Módulo:** Backups / Servidor
- **Gravedad:** Alta
- **Estado:** Corregido en rama de auditoría
- **Descripción:** el directorio y los dumps dependían del umask del proceso.
- **Causa probable:** se priorizó validación del dump y ocultamiento de contraseña, dejando permisos al sistema operativo.
- **Solución aplicada:** directorio `0700`, archivos `0600` y `UMask=0077` en el servicio systemd de backup.
- **Evidencia:** `tests/test_backup.py`.

### INC-AUD-2026-004 — Worker SICODE.IA apuntaba a un venv distinto al institucional
- **Fecha:** 2026-09-10
- **Módulo:** SICODE.IA / systemd
- **Gravedad:** Media-Alta
- **Estado:** Corregido en rama de auditoría
- **Descripción:** la plantilla usaba `__SICODE_APPDIR__/.venv/bin/rq`, mientras la instalación institucional documentada usa un venv separado.
- **Solución aplicada:** marcador `__SICODE_VENV__` y `NoNewPrivileges=true`.

### INC-AUD-2026-005 — Actualizador no reiniciaba el worker SICODE.IA
- **Fecha:** 2026-09-10
- **Módulo:** Despliegue
- **Gravedad:** Media-Alta
- **Estado:** Corregido en rama de auditoría
- **Descripción:** después de actualizar código se reiniciaba únicamente `sicode.service`, por lo que RQ podía seguir con código antiguo cargado.
- **Solución aplicada:** reinicio condicional y health de `sicode-ia-worker.service`, más `pip check` y regresiones nuevas en predeploy.

### INC-AUD-2026-006 — Traceback de RQ expuesto al navegador
- **Fecha:** 2026-09-10
- **Módulo:** SICODE.IA / Seguridad
- **Gravedad:** Media
- **Estado:** Corregido en rama de auditoría
- **Descripción:** el endpoint de estado incluía una porción de `job.exc_info` cuando fallaba un trabajo.
- **Riesgo:** exposición de rutas, librerías y detalles internos del servidor.
- **Solución aplicada:** respuesta genérica al usuario y referencia al administrador/worker; el diagnóstico permanece en logs/cola.

### INC-AUD-2026-007 — Auditoría completa no corría en cada push a `main`
- **Fecha:** 2026-09-10
- **Módulo:** CI / QA
- **Gravedad:** Alta
- **Estado:** Corregido en código; falta activar protección de rama
- **Descripción:** `Validar Auditoria` ejecutaba la suite completa en pull request/manual, mientras los pushes a `main` ejecutaban un workflow más acotado.
- **Solución aplicada:** trigger `push` a `main` y `pip check` en los jobs SQLite/PostgreSQL.
- **Pendiente:** proteger `main` para impedir pushes directos que eludan revisión obligatoria.

### INC-AUD-2026-008 — `main` sin protección de rama
- **Fecha:** 2026-09-10
- **Módulo:** Gobierno de código / GitHub
- **Gravedad:** Alta
- **Estado:** Pendiente de configuración del repositorio
- **Descripción:** la rama permite cambios directos sin exigir PR/checks.
- **Mitigación requerida:** ruleset/branch protection con PR obligatorio, checks de auditoría y bloqueo de force-push/deletion.

### INC-AUD-2026-009 — Respaldo concentrado en el mismo servidor
- **Fecha:** 2026-09-10
- **Módulo:** Continuidad / Backups
- **Gravedad:** Alta
- **Estado:** Pendiente de infraestructura
- **Descripción:** existe backup automático/local, pero falta una copia cifrada en un medio distinto del disco del servidor.
- **Mitigación requerida:** segunda copia cifrada, rotación y prueba periódica de restauración.

### INC-AUD-2026-010 — Transporte LAN HTTP
- **Fecha:** 2026-09-10
- **Módulo:** Red / Sesiones
- **Gravedad:** Alta
- **Estado:** Pendiente de infraestructura institucional
- **Descripción:** la operación documentada usa Nginx por HTTP en LAN y `SESSION_COOKIE_SECURE` no puede activarse mientras no exista HTTPS.
- **Riesgo:** credenciales/cookies no quedan cifradas en tránsito dentro de la LAN.
- **Mitigación requerida:** certificado institucional/interno, HTTPS en Nginx y `SESSION_COOKIE_SECURE=true`; validar manejo seguro de `X-Forwarded-Proto` antes de habilitar HSTS detrás de proxy.

## Deudas técnicas que no deben mezclarse con incidencias urgentes

- Normalización futura de `DateTime` naive a una estrategia timezone-aware consistente.
- Convergencia de modelos históricos de anexos cuando exista ventana de migración controlada.
- Reducción progresiva de controladores históricos grandes.
- Política CSP: introducir primero `Content-Security-Policy-Report-Only`, corregir scripts inline y después hacerla obligatoria.
- Escaneo SCA de dependencias (`pip-audit` o equivalente) como control periódico, sin convertir una base de advisories externa en bloqueo improvisado de producción.

## Criterio de cierre

Las incidencias corregidas en código se consideran listas para cierre únicamente cuando el PR pase la suite completa SQLite/PostgreSQL y luego el servidor institucional pase: backup previo, migraciones, health de web/BD, worker IA activo y smoke tests manuales de login, Visor, expediente, índice, préstamo/devolución, exportaciones y SICODE.IA con usuario autorizado.
