from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.verificacion_form import VerificacionExpedienteForm
from app.models.alerta import Alerta
from app.models.expediente import Expediente
from app.models.verificacion import VerificacionExpediente
from app.services.alertas_service import crear_alerta_si_no_existe
from app.services.bitacora_service import registrar_bitacora
from app.services.estado_documental_service import calcular_estado_documental


verificaciones_bp = Blueprint("verificaciones", __name__, url_prefix="/expedientes")


@verificaciones_bp.route("/<int:expediente_id>/verificaciones", methods=["GET", "POST"])
@login_required
def expediente(expediente_id):
    expediente = Expediente.query.get_or_404(expediente_id)

    if not expediente.expediente_fisico_registrado:
        flash("No puede registrar una verificación hasta confirmar la existencia del expediente físico.", "warning")
        return redirect(url_for("expedientes.detalle", expediente_id=expediente.id))

    form = VerificacionExpedienteForm()
    if form.validate_on_submit():
        estado_anterior = expediente.estado_fisico_documental
        resultado = form.resultado.data

        verificacion = VerificacionExpediente(
            expediente_id=expediente.id,
            usuario_id=current_user.id,
            tipo=form.tipo.data,
            resultado=resultado,
            folios_verificados=form.folios_verificados.data,
            observaciones=form.observaciones.data,
            origen="MANUAL",
        )
        db.session.add(verificacion)

        # La columna anterior se conserva como espejo histórico por
        # compatibilidad. El estado vigente lo calcula EstadoDocumentalService.
        expediente.estado_fisico_documental = resultado
        db.session.flush()

        # La relación pudo haberse cargado al calcular estado_anterior. Se
        # expira para que el cálculo canónico incluya la verificación recién
        # registrada antes de decidir alertas o bitácora.
        db.session.expire(expediente, ["verificaciones"])
        resumen_nuevo = calcular_estado_documental(expediente)
        estado_nuevo = resumen_nuevo["estado"]

        if estado_nuevo == "Verificado":
            alertas_revision = Alerta.query.filter(
                Alerta.expediente_id == expediente.id,
                Alerta.tipo_alerta.in_(["REVISION_EXPEDIENTE", "REVISION_INDICE_DOCUMENTAL"]),
                Alerta.estado.in_(["Abierta", "En revisión"]),
            ).all()
            for alerta in alertas_revision:
                alerta.estado = "Corregida"
        else:
            crear_alerta_si_no_existe(
                expediente_id=expediente.id,
                tipo_alerta="REVISION_EXPEDIENTE",
                titulo=f"Expediente requiere revisión: {expediente.no_sp}",
                descripcion=(
                    f"Verificación {form.tipo.data.lower()} con resultado '{resultado}'. "
                    f"Estado documental derivado: '{estado_nuevo}'. "
                    f"Observaciones: {form.observaciones.data or 'Sin observaciones adicionales.'}"
                ),
                gravedad="Alta" if resultado == "No localizado" else "Media",
                usuario_id=current_user.id,
                commit=False,
            )

        registrar_bitacora(
            accion="REGISTRAR_VERIFICACION_EXPEDIENTE",
            modulo="Verificaciones",
            descripcion=(
                f"Se registró verificación {verificacion.tipo} del SP {expediente.no_sp}; "
                f"resultado declarado: {resultado}; estado documental derivado: {estado_nuevo}."
            ),
            usuario_id=current_user.id,
            expediente_id=expediente.id,
            entidad="VerificacionExpediente",
            entidad_id=verificacion.id,
            datos_anteriores={"estado_documental_derivado": estado_anterior},
            datos_posteriores={
                "estado_documental_derivado": estado_nuevo,
                "resultado_verificacion": resultado,
                "tipo": verificacion.tipo,
                "folios_verificados": verificacion.folios_verificados,
                "verificacion_vigente": resumen_nuevo["verificacion_vigente"],
                "incidencias": resumen_nuevo["incidencias"],
            },
            commit=False,
        )
        db.session.commit()

        flash(
            f"Verificación registrada. Estado documental actual: {estado_nuevo}.",
            "success",
        )
        return redirect(url_for("verificaciones.expediente", expediente_id=expediente.id))

    historial = (
        VerificacionExpediente.query
        .filter_by(expediente_id=expediente.id)
        .order_by(VerificacionExpediente.creado_en.desc())
        .all()
    )

    return render_template(
        "expedientes/verificaciones.html",
        expediente=expediente,
        form=form,
        historial=historial,
    )
