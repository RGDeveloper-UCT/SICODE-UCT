# Auditoría integral SICODE-UCT

Estado: EN CURSO  
Rama documental: `audit/auditoria-integral-2026-08`  
Base auditada inicial: `main` @ `9f0b68c8c941aeb6d2e09fb4fadb9a1a2756b42a`

## Alcance y método

Auditoría incremental según el criterio: ANALIZAR → PROPONER → MODIFICAR → PROBAR → VALIDAR → DOCUMENTAR.

No se realizan cambios funcionales desde esta rama. Cada corrección se implementará posteriormente en un PR pequeño y reversible.

## Mapa arquitectónico inicial

- Flask application factory: `app/__init__.py`.
- Persistencia: PostgreSQL + SQLAlchemy + Flask-Migrate.
- Autenticación: Flask-Login + hashes Werkzeug.
- Modelos núcleo: Usuario, Expediente, UbicacionFisica, DocumentoExpediente, PrestamoExpediente, Alerta, Bitacora.
- Operación diaria: RegistroCoordinacion y detalles especializados para Pago, Movimiento, Anexo, Monitoreo, Documento emitido, Actividad y Remisión.
- Importaciones: Coordinación histórica `.xlsx` y Portadores `.xls`.
- Salidas: PDF y Excel.
- Administración: usuarios, backups y estado básico del sistema.
- CI actual: smoke tests de Coordinación y Portadores sobre SQLite temporal.

## Hallazgos iniciales

### QA-001
**Prioridad:** P1  
**Módulo:** Seguridad / acciones de escritura  
**Archivo(s):** `app/__init__.py`, templates con formularios POST directos (`expedientes/detalle.html`, alertas, remisiones, índice documental)  
**Función/clase/ruta:** acciones POST que no pasan por `FlaskForm.validate_on_submit()`  
**Problema:** Flask-WTF está instalado y los formularios FlaskForm incluyen CSRF, pero no existe `CSRFProtect(app)` global. Los POST manuales no quedan protegidos automáticamente.  
**Cómo reproducirlo:** enviar una petición POST autenticada a una ruta de cambio de estado/anulación/desactivación sin token CSRF.  
**Resultado actual:** la protección depende de que cada flujo use un FlaskForm; las acciones POST directas carecen de garantía global.  
**Resultado esperado:** toda operación mutante debe exigir un token CSRF válido.  
**Causa probable:** crecimiento incremental del sistema con formularios manuales además de FlaskForm.  
**Impacto:** un usuario autenticado puede ser inducido desde otra página a ejecutar una acción no deseada dentro de la LAN.  
**Solución propuesta:** inicializar `flask_wtf.CSRFProtect` a nivel de aplicación y agregar tokens a formularios POST manuales; probar todas las acciones existentes.  
**Riesgo de modificarlo:** Medio; puede romper POST existentes hasta añadir los tokens faltantes.  
**Módulos afectados:** Expedientes, Alertas, Índice documental, Coordinación, Préstamos, Administración.  
**Pruebas necesarias:** POST válido con token, POST sin token=400, regresión de cada acción mutante.  
**Estado:** Detectado

### QA-002
**Prioridad:** P1  
**Módulo:** Autenticación / sesiones  
**Archivo(s):** `app/__init__.py`, `app/models/usuario.py`  
**Función/clase/ruta:** `load_user()` / `Usuario`  
**Problema:** el `user_loader` devuelve el usuario por ID sin comprobar `activo`; el modelo usa un campo `activo`, pero no sobreescribe `UserMixin.is_active`.  
**Cómo reproducirlo:** iniciar sesión con un usuario, desactivarlo desde otro usuario administrador y continuar navegando con la sesión ya abierta.  
**Resultado actual:** la sesión existente puede seguir resolviendo un usuario válido por ID.  
**Resultado esperado:** un usuario desactivado debe perder acceso en la siguiente petición o al menos en un intervalo explícito.  
**Causa probable:** validación de `activo=True` solo en el login inicial.  
**Impacto:** revocación de acceso incompleta.  
**Solución propuesta:** hacer que `load_user` devuelva `None` para usuarios inactivos y/o implementar `is_active` sobre el campo institucional; agregar prueba de revocación.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** todo SICODE.  
**Pruebas necesarias:** login activo, desactivación en sesión, reactivación, sesión expirada.  
**Estado:** Detectado

### QA-003
**Prioridad:** P1  
**Módulo:** Expedientes / Portadores  
**Archivo(s):** `app/routes/portadores.py`  
**Función/clase/ruta:** `/expedientes/portadores/importar` y `/importar/confirmar`  
**Problema:** la sincronización masiva de la manta está protegida por `login_required`, pero no por rol administrativo o permiso específico.  
**Cómo reproducirlo:** iniciar sesión como `usuario_autorizado` y acceder a la importación de Portadores.  
**Resultado actual:** cualquier usuario autenticado puede potencialmente crear/actualizar cientos de registros maestros.  
**Resultado esperado:** una operación masiva de sincronización debe estar restringida a un permiso explícito.  
**Causa probable:** el importador se integró después del esquema original de roles.  
**Impacto:** modificación masiva accidental o no autorizada de datos maestros.  
**Solución propuesta:** reutilizar un decorador de permisos centralizado; inicialmente administrador, o rol/permiso `importar_portadores` si se formaliza una matriz de permisos.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** Expedientes, Coordinación.  
**Pruebas necesarias:** administrador permitido; usuario autorizado denegado; importación válida; bitácora.  
**Estado:** Detectado

### QA-004
**Prioridad:** P2  
**Módulo:** Autenticación  
**Archivo(s):** `app/routes/auth.py`  
**Función/clase/ruta:** `login()`  
**Problema:** el parámetro `next` se usa directamente en `redirect(siguiente)` sin validar que sea una URL interna.  
**Cómo reproducirlo:** abrir `/login?next=https://sitio-externo.example` y autenticarse.  
**Resultado actual:** el navegador puede ser redirigido a un destino externo.  
**Resultado esperado:** solo rutas locales/seguras deben aceptarse como destino posterior al login.  
**Causa probable:** implementación estándar incompleta de `next`.  
**Impacto:** riesgo de open redirect/phishing.  
**Solución propuesta:** validar esquema/host o aceptar únicamente paths relativos internos.  
**Riesgo de modificarlo:** Bajo.  
**Módulos afectados:** autenticación.  
**Pruebas necesarias:** next interno válido; URL externa rechazada; ausencia de next.  
**Estado:** Detectado

### QA-005
**Prioridad:** P1  
**Módulo:** Configuración / sesiones  
**Archivo(s):** `config.py`  
**Función/clase/ruta:** `Config.SECRET_KEY`  
**Problema:** si `SECRET_KEY` no existe en el entorno se utiliza el valor fijo `clave_temporal`.  
**Cómo reproducirlo:** iniciar la aplicación sin `SECRET_KEY`.  
**Resultado actual:** la aplicación arranca con una clave conocida.  
**Resultado esperado:** producción debe fallar de forma segura si no existe una clave secreta robusta.  
**Causa probable:** fallback de desarrollo conservado.  
**Impacto:** si el entorno productivo pierde la variable, sesiones y tokens CSRF pueden quedar comprometidos.  
**Solución propuesta:** eliminar fallback inseguro en configuración de producción y validar variables críticas al iniciar.  
**Riesgo de modificarlo:** Bajo, siempre que se verifique primero que producción ya tiene `SECRET_KEY`.  
**Módulos afectados:** autenticación y todos los FlaskForm.  
**Pruebas necesarias:** arranque con secreto, fallo controlado sin secreto, CI con secreto de prueba.  
**Estado:** Detectado

### QA-006
**Prioridad:** P2  
**Módulo:** Health check  
**Archivo(s):** `app/__init__.py`  
**Función/clase/ruta:** `/health/db`  
**Problema:** endpoint público y, ante error, devuelve el texto de la excepción de PostgreSQL al cliente.  
**Cómo reproducirlo:** provocar indisponibilidad o error de conexión de DB y consultar `/health/db` sin autenticación.  
**Resultado actual:** puede exponer detalles técnicos de conexión.  
**Resultado esperado:** endpoint público mínimo (`ok/degraded`) o panel detallado solo para administrador.  
**Causa probable:** health check creado para despliegue inicial.  
**Impacto:** fuga de información técnica y ausencia de un health check integral.  
**Solución propuesta:** separar `/health` no sensible de diagnóstico administrativo autenticado.  
**Riesgo de modificarlo:** Bajo; mantener compatibilidad con monitoreo/Nginx si existe.  
**Módulos afectados:** DevOps/Administración.  
**Pruebas necesarias:** DB sana, DB caída, usuario anónimo, administrador.  
**Estado:** Detectado

### DATA-001
**Prioridad:** P1  
**Módulo:** Préstamos / Expedientes  
**Tablas involucradas:** `prestamos_expedientes`, `expedientes`  
**Registros afectados:** potencialmente cualquier expediente con préstamo  
**Regla violada:** el estado operativo de préstamo tiene dos fuentes editables: `PrestamoExpediente.estado` y `Expediente.estado_administrativo`.  
**Causa probable:** se copió el estado del movimiento al expediente para facilitar visualización.  
**Forma de detectar casos adicionales:** buscar préstamos `En préstamo` cuyo expediente no esté `En préstamo`, y expedientes `En préstamo` sin préstamo activo.  
**Estrategia de corrección:** definir el préstamo activo como fuente de verdad del estado de disponibilidad; el expediente puede exponer un estado derivado o sincronizado bajo reglas, no editable libremente cuando contradiga movimientos.  
**Validación futura necesaria:** constraint/regla de consistencia y prueba de integración préstamo→devolución.  
**Estado:** Detectado

### DATA-002
**Prioridad:** P2  
**Módulo:** Préstamos / Alertas  
**Tablas involucradas:** `prestamos_expedientes`, `alertas`  
**Registros afectados:** préstamos vencidos posteriormente devueltos  
**Regla violada:** una alerta `PRESTAMO_VENCIDO` se crea automáticamente, pero la devolución no cierra/corrige esa alerta de manera automática.  
**Causa probable:** la generación y el cierre de alertas se diseñaron como flujos separados.  
**Forma de detectar casos adicionales:** alertas abiertas `PRESTAMO_VENCIDO` cuyo préstamo ya esté `Devuelto`.  
**Estrategia de corrección:** al devolver, marcar la alerta asociada como `Corregida` o resolverla mediante motor de reglas; conservar historial.  
**Validación futura necesaria:** prueba vencido→alerta→devolución→alerta corregida.  
**Estado:** Detectado

### DUP-001
**Prioridad:** P2  
**Módulo:** Índice documental  
**Qué está duplicado:** `DocumentoExpediente.total_folios` duplica el valor calculable `folio_fin - folio_inicio + 1`; `es_anexo` duplica parcialmente `tipo_documento == 'Anexo'`.  
**Dónde:** `app/models/documento_expediente.py`  
**Por qué representa duplicidad:** ambos valores pueden derivarse de campos ya almacenados y no existe constraint de DB que garantice coherencia permanente.  
**Cuál implementación debería sobrevivir:** los rangos de folios deben ser la fuente de verdad; para anexo debe definirse una sola semántica (tipo o bandera).  
**Qué debe reutilizarse:** validación de traslape ya implementada en `indice_documental.py`.  
**Qué debe eliminarse:** no eliminar columnas todavía; primero medir usos y migrar de forma compatible.  
**Cómo migrar sin perder información:** añadir checks de consistencia, detectar divergencias, corregir datos y luego evaluar convertir a propiedades/valores derivados.  
**Estado:** Detectado

### MEJ-001
**Prioridad:** P2  
**Situación actual:** Anexo recibido en Coordinación (`AnexoCoordinacion`) y anexo documental (`DocumentoExpediente.es_anexo`) son conceptos relacionados pero no existe FK ni flujo explícito entre ambos.  
**Propuesta:** conservar ambas entidades por sus propósitos distintos (recepción vs índice), pero crear relación/control de incorporación al expediente cuando corresponda.  
**Beneficio:** evita volver a escribir SP, anexo y foliación; permite saber qué anexo recibido ya fue incorporado físicamente al índice.  
**Esfuerzo:** Medio.  
**Prioridad:** P2.  
**Riesgo:** Medio por datos históricos incompletos.  
**Módulos involucrados:** Coordinación, Expedientes, Índice documental, Alertas.  
**Estado:** Detectado

### MEJ-002
**Prioridad:** P2  
**Situación actual:** el dashboard y el listado de préstamos ejecutan `detectar_prestamos_vencidos()` durante una petición GET.  
**Propuesta:** centralizar detección en el futuro Motor de Integridad o tarea programada; las vistas GET deberían principalmente consultar.  
**Beneficio:** elimina efectos secundarios al abrir pantallas y evita lógica duplicada de disparo.  
**Esfuerzo:** Bajo/Medio.  
**Prioridad:** P2.  
**Riesgo:** Bajo si se mantiene una ejecución periódica fiable.  
**Módulos involucrados:** Dashboard, Préstamos, Alertas.  
**Estado:** Detectado

### MEJ-003
**Prioridad:** P2  
**Situación actual:** existe `pytest` como dependencia pero no hay una suite de pruebas versionada; CI ejecuta smoke tests embebidos en YAML y utiliza SQLite, no PostgreSQL.  
**Propuesta:** crear `tests/` y mover progresivamente verificaciones a pytest; mantener smoke tests, incorporar PostgreSQL de CI para constraints/migraciones críticas.  
**Beneficio:** regresión reproducible y pruebas reales de integridad PostgreSQL.  
**Esfuerzo:** Medio.  
**Prioridad:** P2.  
**Riesgo:** Bajo.  
**Módulos involucrados:** todos.  
**Estado:** Detectado

### MEJ-004
**Prioridad:** P3  
**Situación actual:** `README.md` todavía indica que Portadores no se importa desde el sistema, pero la funcionalidad ya está integrada en `main`.  
**Propuesta:** actualizar documentación después de cerrar el diseño definitivo del flujo SP/expediente.  
**Beneficio:** alinea código, base de datos y manual técnico.  
**Esfuerzo:** Bajo.  
**Prioridad:** P3.  
**Riesgo:** Ninguno.  
**Módulos involucrados:** documentación / Expedientes.  
**Estado:** Detectado

## Observaciones en investigación

1. Definir formalmente si `Expediente` representa un caso lógico por SP o exclusivamente un expediente físico. La manta de Portadores actualmente crea registros en `expedientes`; antes de proponer una tabla nueva se evaluará si basta con distinguir explícitamente `SP conocido` de `expediente físico recibido`.
2. Revisar atomicidad de bitácora: muchos flujos hacen commit de negocio y luego un segundo commit de auditoría.
3. Revisar permisos por operación: actualmente la mayor parte de módulos no administrativos usan solamente `login_required`.
4. Revisar seguridad real de backups en el servidor (permisos de directorio/archivo, credenciales en proceso, restauración probada).
5. Revisar paginación y límites silenciosos en listados.
6. Revisar cierre automático de alertas cuando se corrige la causa.
7. Revisar integridad de folios con constraints de PostgreSQL, no solo validación de aplicación.

## Próximas fases de inspección

- Completar mapa de rutas/roles/permisos.
- Auditar migraciones y constraints PostgreSQL.
- Auditar transacciones y bitácora.
- Auditar importaciones y deduplicación.
- Auditar UX/dashboard/búsqueda.
- Auditar configuración productiva Nginx/Gunicorn/systemd y backups.
- Diseñar pruebas de integración antes de aplicar correcciones P1.
