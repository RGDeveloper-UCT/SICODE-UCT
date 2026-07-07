from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models.expediente import Expediente
from app.models.bitacora import Bitacora

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
@login_required
def inicio():
    total_expedientes = Expediente.query.count()
    expedientes_activos = Expediente.query.filter_by(activo=True).count()
    expedientes_inactivos = Expediente.query.filter_by(activo=False).count()

    pendientes_verificacion = Expediente.query.filter_by(
        estado_fisico_documental="Pendiente de verificación"
    ).count()

    expedientes_verificados = Expediente.query.filter_by(
        estado_fisico_documental="Verificado"
    ).count()

    expedientes_con_observaciones = Expediente.query.filter_by(
        estado_fisico_documental="Con observaciones"
    ).count()

    ultimos_expedientes = (
        Expediente.query
        .order_by(Expediente.creado_en.desc())
        .limit(5)
        .all()
    )

    ultimos_eventos = (
        Bitacora.query
        .order_by(Bitacora.creado_en.desc())
        .limit(5)
        .all()
    )

    return render_template(
        "dashboard/inicio.html",
        usuario=current_user,
        total_expedientes=total_expedientes,
        expedientes_activos=expedientes_activos,
        expedientes_inactivos=expedientes_inactivos,
        pendientes_verificacion=pendientes_verificacion,
        expedientes_verificados=expedientes_verificados,
        expedientes_con_observaciones=expedientes_con_observaciones,
        ultimos_expedientes=ultimos_expedientes,
        ultimos_eventos=ultimos_eventos,
    )
