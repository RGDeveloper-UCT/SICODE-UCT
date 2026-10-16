# SICODE-UCT | Control 09 — Equipos institucionales
Ruta: Coordinación → Control de Seguridad Informática.
Objetivo: mantener un registro maestro único de equipos con acceso a información institucional.
No se vincula a SP ni a expedientes: es un control de TI separado del flujo documental.
Campos de identificación: código obligatorio y único, serie e inventario únicos cuando existen.
Responsable: seleccionable de usuarios activos de SICODE, evitando duplicar nombres.
Edición: motivo obligatorio; valores anteriores y posteriores se registran en Bitácora en la misma transacción.
Baja: mediante estado BAJA, nunca eliminación física.
Constancia: PDF informativo bajo demanda, con advertencia de que no acredita por sí sola cumplimiento técnico.
Permisos: lectura con sesión activa; escritura solamente para usuarios con puede_modificar.
Pendientes de aceptación: migración Alembic sobre el head real, pruebas funcionales en PostgreSQL y despliegue institucional.
