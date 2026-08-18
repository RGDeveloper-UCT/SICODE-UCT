# Auditoría integral SICODE-UCT — Resultado técnico

Fecha de auditoría: 2026-08-18  
Alcance: arquitectura, backend, base de datos, seguridad, UX, integraciones, QA, rendimiento, auditoría, backups, documentación y mantenibilidad.  
Método: **ANALIZAR → PROPONER → MODIFICAR → PROBAR → VALIDAR → DOCUMENTAR**.  

> Regla aplicada durante toda la auditoría: reutilizar e integrar antes de crear. No se realizó una reescritura de SICODE ni se cambió Flask/PostgreSQL porque la arquitectura actual es adecuada para el tamaño y entorno institucional.

## 1. Estado general

Calificación posterior a las correcciones implementadas:

| Área | Nota /100 | Evaluación |
|---|---:|---|
| Arquitectura | 91 | Monolito Flask modular apropiado; responsabilidades más claras y sin reescritura innecesaria. |
| Backend | 89 | Rutas/servicios reforzados; todavía existen controladores históricos grandes que conviene seguir reduciendo gradualmente. |
| Base de datos | 91 | Nuevos constraints, índices, FK e invariantes; se preservó compatibilidad con datos históricos. |
| Seguridad | 91 | CSRF global, permisos, sesiones, contraseña temporal obligatoria, rate limit, logout POST y secretos endurecidos. |
| UX | 88 | Dashboard accionable, búsqueda global, expediente integral, recepción integrada y navegación simplificada. |
| Integraciones | 92 | SP–Expediente–Coordinación–Anexo–Índice–Préstamos–Verificaciones–Bitácora conectados donde corresponde. |
| QA | 90 | pytest + SQLite + PostgreSQL real en CI + migraciones + backup/restauración de integración. |
| Rendimiento | 84 | Índices y paginación en áreas de crecimiento; faltan métricas prolongadas con volumen productivo real. |
| Auditoría/trazabilidad | 92 | Bitácora estructurada con entidad, antes/después, IP y user-agent, manteniendo compatibilidad histórica. |
| Backups/recuperación | 89 | Generación segura, validación básica y restauración CI; la restauración productiva debe ensayarse periódicamente en ventana controlada. |
| Documentación | 91 | README y runbook de servidor actualizados; la documentación debe mantenerse en cada PR futuro. |
| Mantenibilidad | 89 | Servicios compartidos, checks modulares y tests; quedan archivos históricos grandes para refactor incremental, no urgente. |

**Evaluación global orientativa: 90/100.**

No se confirmó ningún hallazgo **P0 crítico** durante la auditoría. Los hallazgos P1/P2 identificados fueron corregidos o mitigados de forma compatible con los datos existentes.

---

## 2. Hallazgos

### QA-001
**Prioridad:** P1  
**Módulo:** Seguridad / acciones mutantes  
**Archivo(s):** `app/__init__.py`, templates con formularios POST  
**Función/clase/ruta:** operaciones POST de Expedientes, Alertas, Índice, Coordinación y Administración  
**Problema:** FlaskForm protegía algunos flujos, pero no existía CSRF global para POST manuales.  
**Cómo reproducirlo:** enviar POST autenticado a una operación mutante sin token CSRF.  
**Resultado actual original:** algunas acciones podían aceptar POST sin garantía CSRF central.  
**Resultado esperado:** toda mutación exige token CSRF válido.  
**Causa probable:** crecimiento incremental con mezcla de FlaskForm y formularios HTML manuales.  
**Impacto:** acción administrativa inducida desde un origen externo mientras el usuario está autenticado.  
**Solución propuesta:** `CSRFProtect` global y token en cada formulario manual.  
**Riesgo de modificarlo:** Medio.  
**Módulos afectados:** todos los módulos mutantes.  
**Pruebas necesarias:** POST sin token=400; POST con token funciona; regresión por módulo.  
**Estado:** Corregido / validación automatizada incorporada.

### QA-002
**Prioridad:** P1  
**Módulo:** Autenticación  
**Archivo(s):** `app/__init__.py`, `app/models/usuario.py`  
**Función/clase/ruta:** `load_user`, `Usuario.is_active`  
**Problema:** un usuario desactivado podía conservar una sesión ya abierta.  
**Cómo reproducirlo:** login, desactivar la cuenta desde otra sesión, continuar navegando.  
**Resultado actual original:** `user_loader` resolvía la cuenta por ID sin validar `activo`.  
**Resultado esperado:** la revocación debe surtir efecto en la siguiente petición.  
**Causa probable:** `activo=True` solo se comprobaba al iniciar sesión.  
**Impacto:** revocación de acceso incompleta.  
**Solución propuesta:** `is_active` institucional + `user_loader` que rechaza inactivos.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** todo SICODE.  
**Pruebas necesarias:** sesión activa, desactivación, siguiente petición, reactivación.  
**Estado:** Corregido / validación automatizada incorporada.

### QA-003
**Prioridad:** P1  
**Módulo:** Portadores  
**Archivo(s):** `app/routes/portadores.py`, `app/security.py`  
**Función/clase/ruta:** importación/confirmación de manta  
**Problema:** la sincronización masiva estaba disponible para cualquier usuario autenticado.  
**Cómo reproducirlo:** acceder como `usuario_autorizado` a la ruta de importación.  
**Resultado actual original:** operación masiva sin permiso administrativo.  
**Resultado esperado:** solo rol autorizado puede sincronizar datos maestros.  
**Causa probable:** importador agregado después del esquema inicial de permisos.  
**Impacto:** actualización masiva accidental/no autorizada.  
**Solución propuesta:** decorador administrativo compartido y ocultar acción en UI a no administradores.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** Expedientes, Coordinación.  
**Pruebas necesarias:** admin permitido; usuario normal rechazado.  
**Estado:** Corregido / validación automatizada incorporada.

### QA-004
**Prioridad:** P2  
**Módulo:** Login  
**Archivo(s):** `app/routes/auth.py`, `app/security.py`  
**Función/clase/ruta:** parámetro `next`  
**Problema:** se aceptaba un destino externo posterior al login.  
**Cómo reproducirlo:** `/login?next=https://...`.  
**Resultado actual original:** posible redirección externa.  
**Resultado esperado:** solo destinos internos seguros.  
**Causa probable:** validación incompleta del patrón `next`.  
**Impacto:** open redirect/phishing.  
**Solución propuesta:** validar host/esquema antes de redirigir.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** autenticación.  
**Pruebas necesarias:** ruta interna y URL externa.  
**Estado:** Corregido / validación automatizada incorporada.

### QA-005
**Prioridad:** P1  
**Módulo:** Configuración  
**Archivo(s):** `config.py`  
**Función/clase/ruta:** `SECRET_KEY`, `DATABASE_URL`  
**Problema:** existía fallback conocido para `SECRET_KEY`.  
**Cómo reproducirlo:** iniciar sin variable de entorno.  
**Resultado actual original:** aplicación podía arrancar con secreto predecible.  
**Resultado esperado:** fallar de forma segura si falta configuración crítica.  
**Causa probable:** fallback de desarrollo conservado.  
**Impacto:** seguridad de sesiones/CSRF.  
**Solución propuesta:** configuración obligatoria, cookies endurecidas y límites configurables.  
**Riesgo de modificarlo:** Bajo si producción tiene `.env` correcto.  
**Módulos afectados:** aplicación completa.  
**Pruebas necesarias:** arranque con y sin variables.  
**Estado:** Corregido; el runbook exige verificar variables antes del despliegue.

### QA-006
**Prioridad:** P2  
**Módulo:** Health check  
**Archivo(s):** `app/__init__.py`, `app/services/version_service.py`  
**Función/clase/ruta:** `/health`, `/health/db`  
**Problema:** el endpoint DB podía devolver texto de excepción.  
**Cómo reproducirlo:** provocar error de DB y consultar health.  
**Resultado actual original:** posible exposición de detalles técnicos.  
**Resultado esperado:** estado mínimo sin secretos.  
**Causa probable:** endpoint creado para despliegue inicial.  
**Impacto:** fuga de información técnica.  
**Solución propuesta:** respuesta genérica y versión no sensible; detalle técnico al log/panel admin.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** DevOps.  
**Pruebas necesarias:** app sana, DB sana/caída.  
**Estado:** Corregido.

### QA-007
**Prioridad:** P1  
**Módulo:** Bitácora / Exportación  
**Archivo(s):** `app/routes/bitacora.py`  
**Función/clase/ruta:** exportación Excel  
**Problema:** la ruta utilizaba `registrar_bitacora()` sin importarlo.  
**Cómo reproducirlo:** exportar Bitácora a Excel.  
**Resultado actual original:** posible `NameError` al exportar.  
**Resultado esperado:** exportación exitosa y auditada.  
**Causa probable:** import faltante en una ruta histórica.  
**Impacto:** rompe una función administrativa y su trazabilidad.  
**Solución propuesta:** importar servicio, compartir filtros y cubrir regresión.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** Bitácora, Reportes.  
**Pruebas necesarias:** filtro, paginación y exportación.  
**Estado:** Corregido.

### QA-008
**Prioridad:** P1  
**Módulo:** Usuarios / Contraseñas  
**Archivo(s):** `app/models/usuario.py`, `app/routes/cuenta.py`, `app/routes/admin.py`  
**Función/clase/ruta:** credencial temporal  
**Problema:** una contraseña temporal común podía permanecer indefinidamente.  
**Cómo reproducirlo:** administrador asigna contraseña y usuario continúa usándola.  
**Resultado actual original:** no existía indicador ni bloqueo de cambio obligatorio.  
**Resultado esperado:** credencial asignada por administración debe cambiarse por el usuario.  
**Causa probable:** fase inicial de despliegue.  
**Impacto:** exposición por credenciales compartidas/reutilizadas.  
**Solución propuesta:** `debe_cambiar_password`, bloqueo transversal y rechazo de reutilizar la misma contraseña.  
**Riesgo de modificarlo:** Medio operativo: todos los usuarios activos deberán cambiarla una vez.  
**Módulos afectados:** Login, Mi cuenta, Administración.  
**Pruebas necesarias:** login temporal, bloqueo, cambio propio, continuidad.  
**Estado:** Corregido; migración obliga cambio a usuarios activos.

### QA-009
**Prioridad:** P2  
**Módulo:** Autenticación  
**Archivo(s):** `app/routes/auth.py`, `app/templates/base.html`  
**Función/clase/ruta:** logout  
**Problema:** cierre de sesión era una operación GET.  
**Cómo reproducirlo:** visitar/enlazar `/logout`.  
**Resultado actual original:** una navegación GET mutaba estado de sesión.  
**Resultado esperado:** logout deliberado por POST+CSRF.  
**Causa probable:** implementación inicial simple.  
**Impacto:** cierre de sesión inducido.  
**Solución propuesta:** POST+CSRF y limpiar sesión.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** autenticación/UI.  
**Pruebas necesarias:** GET=405, POST sin token=400, POST válido funciona.  
**Estado:** Corregido.

### QA-010
**Prioridad:** P2  
**Módulo:** Login  
**Archivo(s):** `app/routes/auth.py`  
**Función/clase/ruta:** control de intentos  
**Problema:** no existía límite de intentos fallidos.  
**Cómo reproducirlo:** enviar credenciales incorrectas repetidamente.  
**Resultado actual original:** intentos ilimitados.  
**Resultado esperado:** bloqueo temporal explicable y auditable.  
**Causa probable:** entorno LAN asumido como suficiente control.  
**Impacto:** facilita fuerza bruta interna.  
**Solución propuesta:** ventana temporal por usuario y, cuando la IP real es confiable, por IP.  
**Riesgo de modificarlo:** Bajo/Medio; evitar bloquear a todos detrás de Nginx.  
**Módulos afectados:** autenticación/bitácora.  
**Pruebas necesarias:** cinco fallos/usuario y posterior 429.  
**Estado:** Corregido.

### QA-011
**Prioridad:** P1  
**Módulo:** Backups  
**Archivo(s):** `app/routes/admin.py` original, `app/services/backup_service.py`  
**Función/clase/ruta:** `pg_dump`  
**Problema:** el `DATABASE_URL` completo podía terminar como argumento del proceso `pg_dump`, incluyendo contraseña.  
**Cómo reproducirlo:** inspeccionar argumentos del proceso mientras se genera backup.  
**Resultado actual original:** credencial potencialmente visible a nivel de sistema operativo.  
**Resultado esperado:** contraseña fuera de argv.  
**Causa probable:** uso directo de `--dbname DATABASE_URL`.  
**Impacto:** exposición local de credencial PostgreSQL.  
**Solución propuesta:** parsear URL y pasar contraseña mediante `PGPASSWORD`; validar dump y ocultar error sensible.  
**Riesgo de modificarlo:** Medio; requiere prueba real de backup.  
**Módulos afectados:** Administración/Backups.  
**Pruebas necesarias:** secreto ausente de argv; dump válido; restauración CI.  
**Estado:** Corregido; prueba automatizada + ciclo CI PostgreSQL.

### QA-012
**Prioridad:** P2  
**Módulo:** Administración de usuarios  
**Archivo(s):** `app/routes/admin.py`  
**Función/clase/ruta:** editar/desactivar administrador  
**Problema:** era posible dejar el sistema sin administrador activo mediante cambio de rol/desactivación.  
**Cómo reproducirlo:** degradar/desactivar al último administrador.  
**Resultado actual original:** no existía guardia de último administrador.  
**Resultado esperado:** mantener como mínimo un administrador activo.  
**Causa probable:** controles de usuario separados.  
**Impacto:** bloqueo administrativo.  
**Solución propuesta:** validación compartida antes de desactivar/degradar.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** Usuarios.  
**Pruebas necesarias:** último admin bloqueado; dos admins permiten cambio controlado.  
**Estado:** Corregido.

### QA-013
**Prioridad:** P2  
**Módulo:** Manejo de errores  
**Archivo(s):** `app/__init__.py`, `app/templates/errores/*`  
**Función/clase/ruta:** 403/404/500  
**Problema:** no existía una política uniforme de error institucional.  
**Cómo reproducirlo:** forzar recurso inexistente/operación prohibida/excepción.  
**Resultado actual original:** experiencia y diagnóstico dependían del error/ruta.  
**Resultado esperado:** mensaje comprensible, rollback y log técnico.  
**Causa probable:** crecimiento incremental.  
**Impacto:** mala UX y riesgo de diagnóstico insuficiente.  
**Solución propuesta:** handlers centralizados y rollback en 500.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** todos.  
**Pruebas necesarias:** 403/404/500 sin stack trace al usuario.  
**Estado:** Corregido.

---

## 3. Inconsistencias de datos

### DATA-001
**Prioridad:** P1  
**Tablas involucradas:** `expedientes`, `prestamos_expedientes`  
**Registros afectados:** expedientes con préstamos  
**Regla violada:** disponibilidad tenía dos fuentes editables: préstamo y estado administrativo.  
**Causa probable:** el estado se copió al expediente para mostrarlo rápidamente.  
**Forma de detectar casos adicionales:** préstamos activos sin disponibilidad derivada y viceversa.  
**Estrategia de corrección:** `PrestamoExpediente` es fuente de verdad; disponibilidad es propiedad derivada.  
**Validación futura necesaria:** índice único parcial para un préstamo activo.  
**Estado:** Corregido.

### DATA-002
**Prioridad:** P2  
**Tablas involucradas:** `prestamos_expedientes`, `alertas`  
**Registros afectados:** devoluciones de préstamos anteriormente vencidos  
**Regla violada:** alerta vencida podía quedar abierta después de devolver.  
**Causa probable:** creación y resolución de alertas estaban desacopladas.  
**Forma de detectar casos adicionales:** alerta abierta sin préstamo vencido actual.  
**Estrategia de corrección:** al devolver, marcar alerta como `Corregida`; el motor también detecta alertas huérfanas lógicas.  
**Validación futura necesaria:** prueba vencido→devolución→alerta corregida.  
**Estado:** Corregido.

### DATA-003
**Prioridad:** P1  
**Tablas involucradas:** `expedientes`  
**Registros afectados:** SP creados desde Portadores  
**Regla violada:** conocer un SP no prueba que el expediente físico exista en la UCT.  
**Causa probable:** `Expediente` cumplía simultáneamente funciones de maestro SP y expediente físico.  
**Forma de detectar casos adicionales:** SP importados sin ubicación/verificación física.  
**Estrategia de corrección:** mantener una sola entidad para no duplicar el maestro, pero añadir `expediente_fisico_registrado` y un flujo explícito para materializarlo posteriormente.  
**Validación futura necesaria:** bloquear préstamo/foliación si no existe físico.  
**Estado:** Corregido.

### DATA-004
**Prioridad:** P2  
**Tablas involucradas:** `expedientes`, `verificaciones_expediente`  
**Registros afectados:** expedientes cuyo estado fue definido antes de existir historial formal de verificaciones  
**Regla violada:** un estado documental histórico no permitía reconstruir quién/cuándo verificó.  
**Causa probable:** el sistema guardaba estado actual, no el evento histórico.  
**Forma de detectar casos adicionales:** expediente físico sin verificaciones registradas.  
**Estrategia de corrección:** tabla de eventos `VerificacionExpediente`; no inventar eventos históricos ausentes.  
**Validación futura necesaria:** el motor advierte si falta historial o si el estado actual no coincide con la última verificación.  
**Estado:** Corregido para datos futuros; históricos sin fuente quedan señalados para revisión humana.

### DATA-005
**Prioridad:** P2  
**Tablas involucradas:** `registros_coordinacion` y detalles  
**Registros afectados:** recepciones antiguas  
**Regla violada:** no existía una estructura común para quién entrega/remite y folios recibidos.  
**Causa probable:** recepción se discutió después de crear los subtipos operativos.  
**Forma de detectar casos adicionales:** registros manuales entrantes sin esos metadatos.  
**Estrategia de corrección:** integrar recepción en `RegistroCoordinacion`; backfill de folios existentes sin inventar persona de entrega.  
**Validación futura necesaria:** Control de Integridad `COORD-RECEP-001`.  
**Estado:** Corregido para registros nuevos; históricos incompletos se conservan como tales.

---

## 4. Duplicidades

### DUP-001
**Prioridad:** P2  
**Qué está duplicado:** `DocumentoExpediente.total_folios` es derivable; `es_anexo` solapa parcialmente con `tipo_documento`.  
**Dónde:** `app/models/documento_expediente.py`  
**Por qué representa duplicidad:** pueden divergir si se editan independientemente.  
**Cuál implementación debería sobrevivir:** rango `folio_inicio/folio_fin` como fuente de verdad.  
**Qué debe reutilizarse:** validación de rango/traslape existente.  
**Qué debe eliminarse:** nada de forma destructiva por ahora; las columnas se conservan por compatibilidad.  
**Cómo migrar sin perder información:** constraint obliga total correcto; futuras migraciones podrán retirar duplicidad después de medir dependencias.  
**Estado:** Mitigado/Corregido sin pérdida de compatibilidad.

### DUP-002
**Prioridad:** P2  
**Qué está duplicado:** estado de disponibilidad `En préstamo/Devuelto` en expediente y estado real del préstamo.  
**Dónde:** `expedientes.estado_administrativo`, `prestamos_expedientes.estado`  
**Por qué representa duplicidad:** dos campos editables podían contradecirse.  
**Cuál implementación debería sobrevivir:** préstamo activo como fuente de verdad de disponibilidad.  
**Qué debe reutilizarse:** relación `Expediente.prestamos`.  
**Qué debe eliminarse:** los valores de disponibilidad dejan de pertenecer al catálogo administrativo; no se elimina la columna administrativa.  
**Cómo migrar sin perder información:** migración convierte valores legacy a `Activo` y la UI muestra disponibilidad derivada.  
**Estado:** Corregido.

### DUP-003
**Prioridad:** P2  
**Qué está duplicado:** se propuso conceptualmente un panel independiente de Recepción, pero pagos/instalaciones/desinstalaciones/anexos/monitoreo ya representan la operación recibida.  
**Dónde:** flujo funcional de Coordinación.  
**Por qué representa duplicidad:** un panel separado obligaría a registrar SP, fecha y datos comunes dos veces.  
**Cuál implementación debería sobrevivir:** `RegistroCoordinacion` como cabecera transversal.  
**Qué debe reutilizarse:** usuario actual, fecha, SP, RC/providencia y subtipo.  
**Qué debe eliminarse:** no se crea tabla/panel `Recepcion` redundante.  
**Cómo migrar sin perder información:** se añaden campos comunes `persona_entrega` y `folios_recepcion`; folios legacy se copian de forma no destructiva.  
**Estado:** Resuelto por integración, no por creación de otro módulo.

---

## 5. Mejoras implementadas

### MEJ-001 — Anexo recibido → Índice documental
**Situación actual original:** recepción y foliación del anexo estaban desconectadas.  
**Propuesta:** conservar ambas entidades pero enlazarlas con FK.  
**Beneficio:** no reescribir el mismo anexo; puede saberse cuál recibido ya se incorporó.  
**Esfuerzo:** Medio.  
**Prioridad:** P2.  
**Riesgo:** Medio por históricos incompletos.  
**Módulos involucrados:** Coordinación, Expedientes, Índice, Alertas.  
**Estado:** Implementado.

### MEJ-002 — Detección sin efectos secundarios en GET
**Situación actual original:** abrir Dashboard/Préstamos podía crear alertas vencidas.  
**Propuesta:** consultas GET puras y detección en Control de Integridad/reglas explícitas.  
**Beneficio:** navegación predecible y auditable.  
**Esfuerzo:** Bajo/Medio.  
**Prioridad:** P2.  
**Riesgo:** Bajo.  
**Módulos involucrados:** Dashboard, Préstamos, Alertas.  
**Estado:** Implementado.

### MEJ-003 — Suite QA real
**Situación actual original:** smoke tests embebidos en YAML y SQLite.  
**Propuesta:** `tests/` + pytest + PostgreSQL real + migraciones + backup/restauración.  
**Beneficio:** regresión reproducible y constraints validados en el motor real.  
**Esfuerzo:** Medio.  
**Prioridad:** P2.  
**Riesgo:** Bajo.  
**Módulos involucrados:** todos.  
**Estado:** Implementado.

### MEJ-004 — Documentación viva
**Situación actual original:** README decía que Portadores aún no estaba integrado.  
**Propuesta:** actualizar README y runbook de producción.  
**Beneficio:** código, BD y operación alineados.  
**Esfuerzo:** Bajo.  
**Prioridad:** P3.  
**Riesgo:** Ninguno.  
**Módulos involucrados:** documentación/DevOps.  
**Estado:** Implementado.

### MEJ-005 — Control de Integridad
**Situación actual:** no existía una vista central de inconsistencias.  
**Propuesta:** reglas modulares determinísticas en `app/checks/` y panel admin.  
**Beneficio:** SICODE detecta anomalías sin autocorregir datos.  
**Esfuerzo:** Medio.  
**Prioridad:** P2.  
**Riesgo:** Bajo.  
**Módulos involucrados:** Expedientes, Folios, Préstamos, Coordinación, Usuarios, Backups.  
**Estado:** Implementado.

### MEJ-006 — Búsqueda global
**Situación actual:** búsqueda distribuida por panel.  
**Propuesta:** `/buscar` con servicios existentes.  
**Beneficio:** localizar SP, documento, préstamo, ubicación, verificación o operación sin navegar módulo a módulo.  
**Esfuerzo:** Medio.  
**Prioridad:** P2.  
**Riesgo:** Bajo.  
**Módulos involucrados:** todos los módulos de consulta.  
**Estado:** Implementado.

### MEJ-007 — Paginación
**Situación actual:** listados de crecimiento podían cargar todos los registros.  
**Propuesta:** paginar Coordinación y Bitácora; conservar filtros.  
**Beneficio:** tiempo/memoria más estables a medida que crece la base.  
**Esfuerzo:** Bajo.  
**Prioridad:** P2.  
**Riesgo:** Bajo.  
**Módulos involucrados:** Coordinación, Bitácora.  
**Estado:** Implementado.

---

## 6. Mapa de integración resultante

```text
Manta Portadores (.xls)
        │
        ▼
SP maestro / Expediente
        │
        ├── expediente_fisico_registrado ──► Ubicación física
        │                                 ├──► Verificaciones históricas
        │                                 ├──► Índice documental / Folios
        │                                 └──► Préstamos / Devoluciones
        │
        ├──► Coordinación
        │     ├── Recepción transversal (recibe, entrega/remite, folios, fecha)
        │     ├── Pagos
        │     ├── Instalación / Desinstalación
        │     ├── Anexos ────────────────► Índice documental
        │     ├── Monitoreos
        │     ├── Documentos emitidos
        │     ├── Actividades
        │     └── Remisiones
        │
        ├──► Alertas
        └──► Bitácora estructurada

Todo lo anterior ──► Dashboard / Búsqueda global / Control de Integridad / Reportes
```

Relaciones que **no se fuerzan**: actividades personales y documentos emitidos pueden existir sin SP cuando funcionalmente no corresponda asociarlos.

---

## 7. Propuesta de interfaz aplicada

### Paneles que se mantienen
- Dashboard.
- SP / Expedientes.
- Coordinación.
- Préstamos.
- Alertas.
- Bitácora.
- Administración / Sistema.

### Integraciones realizadas en vez de nuevos paneles
- **Recepción** se integra dentro de cada operación entrante de Coordinación; no se crea un módulo duplicado.
- **Portadores** se importa desde SP/Expedientes; no existe un segundo maestro de sujetos.
- **Anexos** conservan recepción e índice como procesos distintos, pero quedan relacionados.
- **Verificaciones** son historial del expediente y se acceden desde su ficha.
- **Control de Integridad** es una subvista de Sistema, no un segundo dashboard.

### Ficha de expediente
Funciona como centro de información relacionado, no como tabla gigante duplicada. Muestra maestro SP, existencia física, ubicación, folios, verificaciones, Coordinación, alertas y préstamos mediante relaciones.

---

## 8. Motor de Control de Integridad

Diseño modular implementado:

```text
app/checks/
├── expedientes.py
├── folios.py
├── prestamos.py
├── coordinacion.py
├── usuarios.py
└── backups.py
```

Cada hallazgo devuelve código, severidad, módulo, entidad, registro, descripción y recomendación.

Reglas iniciales incluyen:
- SP lógicamente duplicado.
- SP sin expediente físico.
- expediente físico sin ubicación.
- expediente sin historial de verificación.
- estado actual incompatible con última verificación.
- rangos de folios inválidos, total inconsistente, traslape y saltos.
- préstamo activo sin expediente físico/inactivo/múltiple/vencido.
- alerta de vencimiento sin vencimiento real actual.
- Coordinación pendiente o SP-vínculo inconsistente.
- recepción manual incompleta.
- anexo recibido pendiente de incorporar o vinculado a otro expediente.
- remisión con SP/vínculo incoherente.
- rol de usuario no válido / ausencia de admin activo.
- ausencia, antigüedad, tamaño/formato básico del último backup.

El motor **no autocorrige** datos.

---

## 9. Pruebas incorporadas

Cobertura automática por categorías del mandato de QA:

- Happy path: creación/recepción/verificación/préstamo y consultas.
- Negative: CSRF ausente, URL externa, SP sin expediente físico, total de folios inconsistente.
- Edge: representación SP `SP01/SP-001/001/1`.
- Permissions: importación Portadores no administradora.
- Duplicate: préstamo activo único y SP único por remisión.
- Relation: foliación/préstamo requieren expediente físico.
- State: devolución corrige alerta vencida; verificación actualiza estado.
- Audit: operaciones registran bitácora.
- Database: checks/constraints y migraciones.
- UI: rutas/templates principales cargan en pruebas y smoke tests.
- Backup/restore: CI PostgreSQL genera dump real, restaura en otra base y consulta tablas críticas.

CI mantiene SQLite por rapidez y añade PostgreSQL 16 para semántica real de constraints/migraciones.

---

## 10. Plan de corrección

### P0
No se confirmó ningún P0.

### P1
Corregidos: QA-001, QA-002, QA-003, QA-005, QA-007, QA-008, QA-011, DATA-001, DATA-003.

### P2
Corregidos/mitigados: QA-004, QA-006, QA-009, QA-010, QA-012, QA-013, DATA-002, DATA-004, DATA-005, DUP-001/002/003, MEJ-001/002/003/005/006/007.

### P3
Documentación/orden visual actualizados de forma incremental. No se realizó rediseño cosmético masivo.

---

## 11. Deuda técnica

### Conviene mantener bajo seguimiento ahora
1. Resultados del Control de Integridad sobre **datos productivos reales** después del despliegue.
2. Ensayo periódico de restauración en una base temporal institucional, no solamente CI.
3. Medir tiempos reales con crecimiento de Coordinación/Bitácora/Búsqueda antes de añadir más optimizaciones.

### Puede esperar
1. Separar controladores históricos muy grandes en más servicios, siempre que exista beneficio y tests.
2. Eliminar definitivamente columnas legacy de folios/total derivado únicamente después de comprobar que ningún reporte/dependencia las necesita.
3. Catálogos administrables para listas que hoy son constantes pequeñas; no justifican otra tabla todavía.

---

## 12. Limitaciones de evidencia / datos históricos

### Hoja histórica `VERIFICACIONES`
La auditoría confirma que el sistema necesitaba historial formal y ya lo implementa para registros nuevos. Sin embargo, **no se dispone en las fuentes auditadas del formato/columnas verificables de la hoja histórica `VERIFICACIONES`**. Por lo tanto no se creó un importador adivinando columnas ni se inventaron fechas/usuarios/resultados históricos.

Cuando se disponga del archivo/hoja fuente, podrá añadirse un importador con previsualización y deduplicación, siguiendo el patrón ya probado de Portadores/Coordinación.

### Recepciones históricas
Se migran folios que ya existían. No se inventa quién entregó documentación en filas históricas donde ese dato nunca fue registrado.

---

## 13. Roadmap

### AHORA
- Desplegar las migraciones de auditoría con backup previo.
- Atender cualquier migración detenida por inconsistencia real; no forzarla.
- Todos los usuarios activos cambian su contraseña temporal/actual una vez.
- Ejecutar Control de Integridad contra la base productiva y revisar rojos/amarillos.

### DESPUÉS
- Medir rendimiento real y ajustar índices/paginación solo con evidencia.
- Realizar restauración institucional en base temporal y documentar fecha/resultado.
- Importar `VERIFICACIONES` histórica únicamente cuando se entregue su formato fuente verificable.

### FUTURO
- Integración DigitalPersona cuando se entreguen físicamente los dispositivos y puedan probarse drivers/SDK en el entorno institucional.
- Chatbot/IA local únicamente si existe un caso de uso medible; primero se mantiene el Motor de Integridad determinístico como mecanismo de control confiable.
- Automatizaciones programadas de salud/alertas cuando exista una necesidad operacional y mecanismo institucional de ejecución.

---

## Conclusión

SICODE debe continuar sobre Flask/PostgreSQL. La auditoría no encontró una razón técnica para reescribirlo. La mejora principal consiste en convertir las piezas existentes en un sistema conectado: **un maestro de SP, expediente físico explícito, operaciones relacionadas, historial verificable, bitácora estructurada, reglas de integridad y búsqueda transversal**.

La política futura de desarrollo debe permanecer: **preservar lo que funciona, integrar antes de duplicar, automatizar solo lo determinístico, mantener trazabilidad y no modificar datos reales destructivamente sin backup y validación.**
