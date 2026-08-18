from collections import defaultdict
from datetime import date

from app.checks import HallazgoIntegridad
from app.models.alerta import Alerta
from app.models.prestamo import PrestamoExpediente


def ejecutar():
    hallazgos = []
    activos_por_expediente = defaultdict(list)
    hoy = date.today()

    prestamos = PrestamoExpediente.query.all()
    for prestamo in prestamos:
        if prestamo.activo and prestamo.estado == "En préstamo":
            activos_por_expediente[prestamo.expediente_id].append(prestamo)
            expediente = prestamo.expediente

            if not expediente.expediente_fisico_registrado:
                hallazgos.append(HallazgoIntegridad(
                    codigo="PRE-FISICO-001",
                    severidad="error",
                    modulo="Préstamos",
                    entidad="PrestamoExpediente",
                    registro=prestamo.numero_control,
                    descripcion="Existe un préstamo activo para un SP sin expediente físico registrado.",
                    recomendacion="Verificar el movimiento y la existencia física del expediente antes de corregir estados.",
                ))
            if not expediente.activo:
                hallazgos.append(HallazgoIntegridad(
                    codigo="PRE-INACTIVO-001",
                    severidad="error",
                    modulo="Préstamos",
                    entidad="PrestamoExpediente",
                    registro=prestamo.numero_control,
                    descripcion="El expediente está inactivo pero mantiene un préstamo activo.",
                    recomendacion="Revisar el préstamo o reactivar formalmente el expediente según corresponda.",
                ))
            if prestamo.fecha_estimada_devolucion and prestamo.fecha_estimada_devolucion < hoy:
                hallazgos.append(HallazgoIntegridad(
                    codigo="PRE-VENCIDO-001",
                    severidad="advertencia",
                    modulo="Préstamos",
                    entidad="PrestamoExpediente",
                    registro=prestamo.numero_control,
                    descripcion=f"Préstamo vencido desde {prestamo.fecha_estimada_devolucion.strftime('%d/%m/%Y')}.",
                    recomendacion="Gestionar la devolución o actualizar formalmente el movimiento.",
                ))

    for expediente_id, registros in activos_por_expediente.items():
        if len(registros) > 1:
            hallazgos.append(HallazgoIntegridad(
                codigo="PRE-MULTI-001",
                severidad="error",
                modulo="Préstamos",
                entidad="Expediente",
                registro=f"Expediente ID {expediente_id}",
                descripcion=f"Existen {len(registros)} préstamos activos simultáneos.",
                recomendacion="Revisar el historial y conservar un único movimiento activo válido.",
            ))

    alertas_vencidas = Alerta.query.filter(
        Alerta.tipo_alerta == "PRESTAMO_VENCIDO",
        Alerta.estado.in_(["Abierta", "En revisión"]),
    ).all()
    for alerta in alertas_vencidas:
        activos = activos_por_expediente.get(alerta.expediente_id, [])
        hay_vencido = any(
            p.fecha_estimada_devolucion and p.fecha_estimada_devolucion < hoy
            for p in activos
        )
        if not hay_vencido:
            hallazgos.append(HallazgoIntegridad(
                codigo="PRE-ALERTA-001",
                severidad="advertencia",
                modulo="Préstamos",
                entidad="Alerta",
                registro=f"Alerta {alerta.id}",
                descripcion="Alerta de préstamo vencido permanece abierta sin un préstamo actualmente vencido.",
                recomendacion="Revisar y marcar la alerta como corregida/cerrada si el movimiento ya fue resuelto.",
            ))

    return hallazgos
