from datetime import date

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models.expediente import Expediente
from app.models.bitacora import Bitacora
from app.models.alerta import Alerta
from app.models.prestamo import PrestamoExpediente
from app.services.alertas_service import detectar_prestamos_vencidos
from app.services.bitacora_service import registrar_bitacora

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.route("/dashboard")
@login_required
def inicio():
    alertas_generadas = detectar_prestamos_vencidos(usuario_id=current_user.id)

    if alertas_generadas:
        registrar_bitacora(
            accion="GENERAR_ALERTA_PRESTAMO_VENCIDO",
            modulo="Alertas",
            descripcion=f"Se generaron {len(alertas_generadas)} alerta(s) automática(s) por préstamo vencido.",
            usuario_id=current_user.id,
        )

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

    alertas_abiertas = Alerta.query.filter_by(estado="Abierta").count()
    alertas_en_revision = Alerta.query.filter_by(estado="En revisión").count()
    alertas_corregidas = Alerta.query.filter_by(estado="Corregida").count()
    alertas_cerradas = Alerta.query.filter_by(estado="Cerrada").count()
    alertas_alta = Alerta.query.filter_by(gravedad="Alta").count()

    prestamos_activos = PrestamoExpediente.query.filter_by(estado="En préstamo").count()
    prestamos_devueltos = PrestamoExpediente.query.filter_by(estado="Devuelto").count()

    prestamos_vencidos = (
        PrestamoExpediente.query
        .filter(
            PrestamoExpediente.estado == "En préstamo",
            PrestamoExpediente.fecha_estimada_devolucion != None,
            PrestamoExpediente.fecha_estimada_devolucion < date.today(),
        )
        .count()
    )

    ultimos_expedientes = (
        Expediente.query
        .order_by(Expediente.creado_en.desc())
        .limit(5)
        .all()
    )

    ultimas_alertas = (
        Alerta.query
        .order_by(Alerta.creado_en.desc())
        .limit(5)
        .all()
    )

    ultimos_prestamos = (
        PrestamoExpediente.query
        .order_by(PrestamoExpediente.fecha_prestamo.desc())
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
        alertas_abiertas=alertas_abiertas,
        alertas_en_revision=alertas_en_revision,
        alertas_corregidas=alertas_corregidas,
        alertas_cerradas=alertas_cerradas,
        alertas_alta=alertas_alta,
        prestamos_activos=prestamos_activos,
        prestamos_devueltos=prestamos_devueltos,
        prestamos_vencidos=prestamos_vencidos,
        ultimos_expedientes=ultimos_expedientes,
        ultimas_alertas=ultimas_alertas,
        ultimos_prestamos=ultimos_prestamos,
        ultimos_eventos=ultimos_eventos,
    )
