from datetime import date

from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.models.alerta import Alerta
from app.models.bitacora import Bitacora
from app.models.coordinacion import AnexoCoordinacion, RegistroCoordinacion
from app.models.expediente import Expediente
from app.models.prestamo import PrestamoExpediente


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", strict_slashes=False)
@login_required
def inicio():
    total_sp = Expediente.query.count()
    expedientes_fisicos = Expediente.query.filter_by(expediente_fisico_registrado=True).count()
    sp_sin_expediente = Expediente.query.filter_by(expediente_fisico_registrado=False).count()

    # El estado documental vigente ya no se cuenta desde la columna histórica.
    # Se deriva del árbol de cada SP para evitar diferencias entre módulos.
    expedientes_fisicos_obj = Expediente.query.filter_by(expediente_fisico_registrado=True).all()
    estados_pendientes = {
        "Pendiente de indexación",
        "Pendiente de verificación",
        "Verificación desactualizada",
    }
    pendientes_verificacion = sum(
        1
        for expediente in expedientes_fisicos_obj
        if expediente.estado_fisico_documental in estados_pendientes
    )

    coordinacion_pendiente = RegistroCoordinacion.query.filter(RegistroCoordinacion.estado != "Completo").count()
    anexos_pendientes = (
        AnexoCoordinacion.query
        .join(RegistroCoordinacion, AnexoCoordinacion.registro_id == RegistroCoordinacion.id)
        .filter(
            RegistroCoordinacion.expediente_id.isnot(None),
            AnexoCoordinacion.documento_expediente_id.is_(None),
        )
        .count()
    )

    alertas_pendientes = Alerta.query.filter(Alerta.estado.in_(["Abierta", "En revisión"])).count()
    alertas_altas = Alerta.query.filter(
        Alerta.estado.in_(["Abierta", "En revisión"]),
        Alerta.gravedad == "Alta",
    ).count()

    prestamos_activos = PrestamoExpediente.query.filter_by(estado="En préstamo", activo=True).count()
    prestamos_vencidos = PrestamoExpediente.query.filter(
        PrestamoExpediente.estado == "En préstamo",
        PrestamoExpediente.activo.is_(True),
        PrestamoExpediente.fecha_estimada_devolucion.isnot(None),
        PrestamoExpediente.fecha_estimada_devolucion < date.today(),
    ).count()

    recientes_coord = RegistroCoordinacion.query.order_by(RegistroCoordinacion.creado_en.desc()).limit(6).all()
    ultimos_eventos = Bitacora.query.order_by(Bitacora.creado_en.desc()).limit(6).all()

    return render_template(
        "dashboard/inicio.html",
        usuario=current_user,
        total_sp=total_sp,
        expedientes_fisicos=expedientes_fisicos,
        sp_sin_expediente=sp_sin_expediente,
        pendientes_verificacion=pendientes_verificacion,
        coordinacion_pendiente=coordinacion_pendiente,
        anexos_pendientes=anexos_pendientes,
        alertas_pendientes=alertas_pendientes,
        alertas_altas=alertas_altas,
        prestamos_activos=prestamos_activos,
        prestamos_vencidos=prestamos_vencidos,
        recientes_coord=recientes_coord,
        ultimos_eventos=ultimos_eventos,
    )
