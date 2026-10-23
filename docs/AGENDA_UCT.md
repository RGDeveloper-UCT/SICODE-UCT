# Agenda UCT — implementación colaborativa

La Agenda UCT es interna y no utiliza Todoist ni Google Calendar: implementa tareas, subtareas, colaboración, eventos, mantenimientos, capacitaciones, gestiones, recurrencia básica, cumpleaños voluntarios, notificaciones, confirmaciones y exportación CSV.

## Reglas
- Usuarios con rol administrador o usuario_autorizado pueden crear y asignar tareas. Los visores solo consultan las actividades institucionales.
- Las tareas personales solo se muestran a creador, responsable o participante.
- La finalización comunica al creador y a los participantes; las tareas con revisión quedan En revisión hasta que el creador las valida.
- Las alertas rojas y amarillas pendientes se muestran 5 segundos después del Dashboard tras iniciar sesión. La confirmación registra fecha y usuario. Las verdes no interrumpen.
- Los avisos confirmados de un vencimiento no se repiten salvo que se cambie la fecha.
- Cumpleaños: voluntarios, por día/mes, visibilidad configurable.
- Fechas de agenda en hora local Guatemala; el servidor debe mantener NTP y zona horaria configurada coherentemente.
- No ingresar documentos sensibles ni copias de expedientes.
- URL del módulo: /agenda/; API bajo /agenda/api/.

## Verificación previa a producción
```bash
python -m compileall -q app migrations tests
pytest -q tests/test_agenda_uct.py
python -m flask --app run.py db heads
```

## Despliegue
Consultar docs/OPERACION_SERVIDOR.md. Realizar backup PostgreSQL comprobado antes de `flask db upgrade`. No aplicar cambios productivos sin revisar pruebas.
